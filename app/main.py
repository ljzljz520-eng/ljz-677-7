"""培训学时记录导入系统 —— FastAPI 入口。"""
import csv
import io
import re
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response

from . import config, database as db
from .courses import COURSES
from .platform_client import PLATFORM_COURSES, PLATFORM_ERROR_CODES
from .tasks import job_queue

STATIC_DIR = Path(__file__).resolve().parent / "static"
ALLOWED_SUFFIXES = {".csv", ".xlsx", ".xlsm"}


@asynccontextmanager
async def lifespan(app: FastAPI):
    config.ensure_dirs()
    db.init_db()
    job_queue.start()
    yield


app = FastAPI(title="培训学时记录导入系统", lifespan=lifespan)


# ---------------- 页面 ----------------

@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC_DIR / "index.html")


# ---------------- 任务接口 ----------------

@app.post("/api/jobs", status_code=201)
async def create_job(file: UploadFile = File(...)):
    """上传学时记录文件（.csv / .xlsx），创建导入任务并入队。"""
    filename = Path(file.filename or "upload.csv").name  # 防路径穿越
    if Path(filename).suffix.lower() not in ALLOWED_SUFFIXES:
        raise HTTPException(400, "仅支持 .csv / .xlsx 文件")
    content = await file.read()
    if not content:
        raise HTTPException(400, "文件内容为空")
    stored = config.UPLOAD_DIR / f"{int(time.time() * 1000)}_{filename}"
    stored.write_bytes(content)
    job_id = db.create_job(filename=filename, stored_path=str(stored))
    db.add_log(job_id, "INFO", f"文件已接收（{len(content)} 字节），任务进入队列")
    job_queue.submit(job_id)
    return {"job_id": job_id}


@app.get("/api/jobs")
def list_jobs():
    return {"jobs": db.list_jobs(), "queue_pending": job_queue.pending()}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: int):
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(404, "任务不存在")
    return job


@app.get("/api/jobs/{job_id}/logs")
def get_logs(job_id: int, after_id: int = 0):
    if not db.get_job(job_id):
        raise HTTPException(404, "任务不存在")
    return {"logs": db.get_logs(job_id, after_id)}


@app.get("/api/jobs/{job_id}/errors")
def get_errors(job_id: int):
    if not db.get_job(job_id):
        raise HTTPException(404, "任务不存在")
    return {"errors": db.get_errors(job_id)}


@app.get("/api/jobs/{job_id}/correction-template")
def download_correction_template(job_id: int):
    """下载修正模板：包含全部异常行（本地校验 + 平台退回）及原因，修正后可重新上传。"""
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(404, "任务不存在")
    errors = db.get_errors(job_id)
    if not errors:
        raise HTTPException(404, "该任务没有异常数据，无需修正模板")

    import json
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["原始行号", "姓名", "证件号", "课程代码", "课程名称",
                     "学时", "培训日期", "异常来源", "错误码", "错误原因"])
    source_name = {"LOCAL": "本地校验", "PLATFORM": "行业平台"}
    for e in errors:
        raw = json.loads(e["raw_json"])
        writer.writerow([
            e["row_no"], raw.get("name", ""), raw.get("id_number", ""),
            raw.get("course_code", ""), raw.get("course_name", ""),
            raw.get("hours", ""), raw.get("train_date", ""),
            source_name.get(e["source"], e["source"]), e["code"] or "", e["message"],
        ])
    # 带 BOM 的 UTF-8，保证 Excel 打开中文不乱码
    content = "﻿" + buf.getvalue()
    out_name = re.sub(r"[^\w.-]", "_", f"correction_template_job_{job_id}.csv")
    return Response(
        content=content.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={out_name}"},
    )


# ---------------- 元数据 ----------------

@app.get("/api/courses")
def get_courses():
    rows = []
    for code, c in COURSES.items():
        p = PLATFORM_COURSES.get(code)
        rows.append({
            "code": code, "name": c["name"],
            "local_max_hours": c["max_hours"],
            "platform_max_hours": p["max_hours"] if p else None,
        })
    return {"courses": rows, "platform_error_codes": PLATFORM_ERROR_CODES}


@app.exception_handler(Exception)
async def unhandled(request, exc):  # pragma: no cover
    return JSONResponse(status_code=500, content={"detail": f"服务器内部错误：{exc}"})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000)
