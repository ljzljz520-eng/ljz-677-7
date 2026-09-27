"""端到端：上传 → 本地校验 → 平台上送 → 异常明细 → 修正模板 → 修正重传 → 重复上报拦截。"""
import csv
import io
import time

from fastapi.testclient import TestClient

from app.main import app
from app.validation import compute_id_check_code

HEADER = ["姓名", "证件号", "课程代码", "课程名称", "学时", "培训日期"]


def make_id(body17: str) -> str:
    return body17 + compute_id_check_code(body17)


ID1 = make_id("11010119900307751")   # 张伟（成功）
ID2 = make_id("11010119850512482")   # 王芳（成功）
ID3 = make_id("11010119921206333")
ID4_BAD = "11010119881130414" + ("0" if compute_id_check_code("11010119881130414") != "0" else "1")
ID5 = make_id("11010119900715525")
ID6 = make_id("11010119860320636")
ID7 = make_id("11010119910218747")
ID8 = make_id("11010119870909858")
ID10 = make_id("11010119900523761")
ID11 = make_id("11010119900101999")  # 第17位为 9 → 平台视为未注册
ID12 = make_id("11010119881215672")

SAMPLE_ROWS = [
    ["张伟", ID1, "AQ-101", "安全生产法规", "4", "2026-09-10"],   # 行2  → 成功
    ["王芳", ID2, "AQ-104", "电气安全基础", "8", "2026-09-11"],   # 行3  → 成功
    ["", ID3, "AQ-101", "安全生产法规", "4", "2026-09-10"],       # 行4  → 本地：姓名为空
    ["李强", ID4_BAD, "AQ-101", "安全生产法规", "4", "2026-09-10"],  # 行5 → 本地：校验码错
    ["赵敏", ID5, "AQ-999", "未知课程", "4", "2026-09-10"],       # 行6  → 本地：课程不存在
    ["陈杰", ID6, "AQ-101", "安全生产法规", "0", "2026-09-10"],   # 行7  → 本地：学时≤0
    ["刘洋", ID7, "AQ-101", "安全生产法规", "9", "2026-09-10"],   # 行8  → 本地：超课程上限8
    ["孙丽", ID8, "AQ-102", "高处作业安全", "4", "2027-01-01"],   # 行9  → 本地：未来日期
    ["张伟", ID1, "AQ-101", "安全生产法规", "4", "2026-09-10"],   # 行10 → 本地：文件内重复
    ["周涛", ID10, "AQ-102", "高处作业安全", "14", "2026-09-12"],  # 行11 → 平台 P2001
    ["吴霞", ID11, "AQ-103", "有限空间作业", "6", "2026-09-13"],   # 行12 → 平台 P1001
    ["郑斌", ID12, "AQ-106", "职业健康培训", "4", "2026-09-14"],   # 行13 → 平台 P3001
]


def make_csv_bytes(rows) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(HEADER)
    w.writerows(rows)
    return buf.getvalue().encode("utf-8")


def upload(client, content: bytes, filename="records.csv") -> int:
    r = client.post("/api/jobs", files={"file": (filename, content, "text/csv")})
    assert r.status_code == 201, r.text
    return r.json()["job_id"]


def wait_done(client, job_id: int, timeout=30) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        j = client.get(f"/api/jobs/{job_id}").json()
        if j["status"] in ("DONE", "DONE_WITH_ERRORS", "FAILED"):
            return j
        time.sleep(0.2)
    raise TimeoutError(f"任务 {job_id} 超时未完成")


def test_full_import_and_correction_cycle():
    with TestClient(app) as client:
        # ---- 1. 上传原始文件 ----
        job1_id = upload(client, make_csv_bytes(SAMPLE_ROWS))
        j1 = wait_done(client, job1_id)
        assert j1["status"] == "DONE_WITH_ERRORS"
        assert j1["total_rows"] == 12
        assert j1["invalid_rows"] == 7      # 本地校验失败
        assert j1["valid_rows"] == 5
        assert j1["uploaded_rows"] == 2     # 平台接受
        assert j1["rejected_rows"] == 3     # 平台退回
        assert j1["percent"] == 100

        # ---- 2. 异常明细 ----
        errors = client.get(f"/api/jobs/{job1_id}/errors").json()["errors"]
        assert len(errors) == 10
        local = [e for e in errors if e["source"] == "LOCAL"]
        platform = [e for e in errors if e["source"] == "PLATFORM"]
        assert len(local) == 7 and len(platform) == 3
        assert {e["code"] for e in platform} == {"P2001", "P1001", "P3001"}
        dup = next(e for e in local if e["row_no"] == 10)
        assert "第 2 行重复" in dup["message"]

        # ---- 3. 日志 ----
        logs = client.get(f"/api/jobs/{job1_id}/logs").json()["logs"]
        messages = [l["message"] for l in logs]
        assert any("本地校验完成" in m for m in messages)
        assert any("上送行业平台" in m for m in messages)

        # ---- 4. 下载修正模板 ----
        r = client.get(f"/api/jobs/{job1_id}/correction-template")
        assert r.status_code == 200
        rows = list(csv.reader(io.StringIO(r.content.decode("utf-8-sig"))))
        tpl_header, tpl_rows = rows[0], rows[1:]
        assert tpl_header == ["原始行号", "姓名", "证件号", "课程代码", "课程名称",
                              "学时", "培训日期", "异常来源", "错误码", "错误原因"]
        assert len(tpl_rows) == 10

        # ---- 5. 在模板上修正并直接重新上传（附加列应被忽略） ----
        col = {h: i for i, h in enumerate(tpl_header)}
        fixes = {
            "4":  {"姓名": "王明"},
            "5":  {"证件号": make_id("11010119881130414")},
            "6":  {"课程代码": "AQ-101", "课程名称": "安全生产法规"},
            "7":  {"学时": "4"},
            "8":  {"学时": "6"},
            "9":  {"培训日期": "2026-09-15"},
            "10": {"培训日期": "2026-09-16"},   # 与原成功记录错开日期
            "11": {"学时": "10"},               # 降到平台上限 12 以内
            "12": {"证件号": make_id("11010119900101995")},  # 换成已注册证号
            "13": {"课程代码": "AQ-104", "课程名称": "电气安全基础"},
        }
        for row in tpl_rows:
            for field, value in fixes[row[0]].items():
                row[col[field]] = value
        buf = io.StringIO()
        csv.writer(buf).writerows([tpl_header] + tpl_rows)
        job2_id = upload(client, buf.getvalue().encode("utf-8-sig"),
                         filename="correction_template.csv")
        j2 = wait_done(client, job2_id)
        assert j2["mode"] == "CORRECTION"
        assert j2["status"] == "DONE"
        assert j2["total_rows"] == 10
        assert j2["invalid_rows"] == 0
        assert j2["uploaded_rows"] == 10
        assert j2["rejected_rows"] == 0


def test_duplicate_upload_rejected_by_platform():
    """同一条记录第二次上送时，平台应以 P2002 退回。"""
    new_id = make_id("11010119931215678")  # 出生日期 1993-12-15，第17位为 8
    row = ["测试员", new_id, "AQ-103", "有限空间作业", "4", "2026-09-18"]
    with TestClient(app) as client:
        j1 = wait_done(client, upload(client, make_csv_bytes([row])))
        assert j1["status"] == "DONE" and j1["uploaded_rows"] == 1

        j2 = wait_done(client, upload(client, make_csv_bytes([row])))
        assert j2["status"] == "DONE_WITH_ERRORS"
        assert j2["rejected_rows"] == 1
        errors = client.get(f"/api/jobs/{j2['id']}/errors").json()["errors"]
        assert errors[0]["source"] == "PLATFORM" and errors[0]["code"] == "P2002"


def test_bad_file_rejected():
    with TestClient(app) as client:
        r = client.post("/api/jobs", files={"file": ("a.txt", b"hello", "text/plain")})
        assert r.status_code == 400
        # 缺列文件 → 任务失败并带错误信息
        job_id = upload(client, "姓名,学时\n张三,4\n".encode("utf-8"))
        j = wait_done(client, job_id)
        assert j["status"] == "FAILED"
        assert "缺少必要列" in j["error"]
