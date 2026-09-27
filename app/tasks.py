"""任务队列与导入流水线：解析 → 本地校验 → 分批上送行业平台。"""
import queue
import threading

from . import database as db
from . import importer, validation
from .platform_client import IndustryPlatformClient

BATCH_SIZE = 50          # 每批上送平台的记录数
PROGRESS_FLUSH_EVERY = 20  # 校验阶段每处理多少行刷一次进度


class JobQueue:
    """简单的内存任务队列 + 后台 worker 线程。"""

    def __init__(self, workers: int = 1):
        self._q: queue.Queue[int] = queue.Queue()
        self._workers = workers
        self._started = False
        self._lock = threading.Lock()

    def start(self) -> None:
        with self._lock:
            if self._started:
                return
            for i in range(self._workers):
                t = threading.Thread(target=self._loop, name=f"import-worker-{i}", daemon=True)
                t.start()
            self._started = True

    def submit(self, job_id: int) -> None:
        self._q.put(job_id)

    def pending(self) -> int:
        return self._q.qsize()

    def _loop(self) -> None:
        while True:
            job_id = self._q.get()
            try:
                process_job(job_id)
            except Exception as e:  # 兜底：任何未捕获异常都标记任务失败
                db.update_job(job_id, status="FAILED", error=f"{type(e).__name__}: {e}")
                db.add_log(job_id, "ERROR", f"任务异常终止：{type(e).__name__}: {e}")
            finally:
                self._q.task_done()


def _pct(part: int, whole: int, base: int, span: int) -> int:
    if whole <= 0:
        return base
    return base + int(span * part / whole)


def process_job(job_id: int) -> None:
    job = db.get_job(job_id)
    if not job:
        return
    log = lambda level, msg: db.add_log(job_id, level, msg)
    log("INFO", f"任务开始处理（文件：{job['filename']}）")

    # ---- 阶段1：解析 ----
    db.update_job(job_id, status="RUNNING", phase="PARSING", percent=2)
    try:
        result = importer.parse_file(job["stored_path"])
    except importer.ParseError as e:
        db.update_job(job_id, status="FAILED", phase=None, error=str(e), percent=100)
        log("ERROR", f"文件解析失败：{e}")
        return
    rows = result.rows
    mode = "CORRECTION" if result.is_correction else job["mode"]
    db.update_job(job_id, total_rows=len(rows), mode=mode, percent=5)
    log("INFO", f"解析完成，共 {len(rows)} 行数据"
                + ("（检测到修正模板格式，按修正数据重新校验）" if result.is_correction else ""))
    if not rows:
        db.update_job(job_id, status="DONE", phase=None, percent=100)
        log("WARN", "文件中没有数据行，任务结束")
        return

    # ---- 阶段2：本地校验 ----
    db.update_job(job_id, phase="VALIDATING")
    log("INFO", "开始本地校验：姓名 / 证件号 / 课程 / 学时数 / 培训日期")
    valid: list[dict] = []
    invalid = 0
    seen: dict[tuple, int] = {}
    for i, row in enumerate(rows, 1):
        errors = validation.validate_row(row)
        if not errors:
            key = (row["id_number"], row["course_code"], row["train_date"])
            if key in seen:
                errors = [f"文件内重复记录（与第 {seen[key]} 行重复）"]
            else:
                seen[key] = row["row_no"]
        if errors:
            invalid += 1
            db.add_error(job_id, row["row_no"], "LOCAL", "L1000", "；".join(errors), row)
        else:
            valid.append(row)
        if i % PROGRESS_FLUSH_EVERY == 0 or i == len(rows):
            db.update_job(job_id, processed_rows=i, invalid_rows=invalid,
                          percent=_pct(i, len(rows), 5, 45))
    db.update_job(job_id, valid_rows=len(valid), invalid_rows=invalid)
    log("INFO", f"本地校验完成：有效 {len(valid)} 行，无效 {invalid} 行")

    # ---- 阶段3：分批上送行业平台 ----
    uploaded = rejected = 0
    if valid:
        db.update_job(job_id, phase="UPLOADING", percent=50)
        client = IndustryPlatformClient()
        total_valid = len(valid)
        batches = (total_valid + BATCH_SIZE - 1) // BATCH_SIZE
        log("INFO", f"开始上送行业平台：{total_valid} 行，分 {batches} 批")
        for b, start in enumerate(range(0, total_valid, BATCH_SIZE), 1):
            batch = valid[start:start + BATCH_SIZE]
            accepted, rejects = client.upload_batch(job_id, batch)
            uploaded += len(accepted)
            for r in rejects:
                rejected += 1
                db.add_error(job_id, r["row_no"], "PLATFORM", r["code"], r["message"], r["raw"])
            done = start + len(batch)
            db.update_job(job_id, uploaded_rows=uploaded, rejected_rows=rejected,
                          percent=_pct(done, total_valid, 50, 50))
            log("INFO", f"批次 {b}/{batches} 上送完成：成功 {len(accepted)} 条，"
                        f"平台退回 {len(rejects)} 条（累计成功 {uploaded}，退回 {rejected}）")
    else:
        log("WARN", "没有有效数据可上送行业平台")

    # ---- 完成 ----
    has_errors = (invalid + rejected) > 0
    status = "DONE_WITH_ERRORS" if has_errors else "DONE"
    db.update_job(job_id, status=status, phase=None, percent=100)
    if has_errors:
        log("WARN", f"任务完成（含异常）：本地校验失败 {invalid} 行，平台退回 {rejected} 行，"
                    f"成功上送 {uploaded} 行。可下载修正模板修正后重新上传。")
    else:
        log("INFO", f"任务完成：{uploaded} 行全部成功上送行业平台。")


job_queue = JobQueue()
