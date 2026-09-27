"""SQLite 持久化：任务、日志、行级错误、模拟平台台账。"""
import json
import sqlite3
import threading
from datetime import datetime

from . import config

_init_lock = threading.Lock()
_initialized = False


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(config.DB_PATH), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _now_ms() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def init_db() -> None:
    global _initialized
    with _init_lock:
        if _initialized:
            return
        config.ensure_dirs()
        with _conn() as c:
            c.execute("PRAGMA journal_mode = WAL")
            c.executescript(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    id             INTEGER PRIMARY KEY AUTOINCREMENT,
                    filename       TEXT NOT NULL,
                    stored_path    TEXT NOT NULL,
                    mode           TEXT NOT NULL DEFAULT 'NORMAL',   -- NORMAL / CORRECTION
                    status         TEXT NOT NULL DEFAULT 'PENDING',  -- PENDING/RUNNING/DONE/DONE_WITH_ERRORS/FAILED
                    phase          TEXT,                             -- PARSING/VALIDATING/UPLOADING
                    total_rows     INTEGER NOT NULL DEFAULT 0,
                    processed_rows INTEGER NOT NULL DEFAULT 0,
                    valid_rows     INTEGER NOT NULL DEFAULT 0,
                    invalid_rows   INTEGER NOT NULL DEFAULT 0,
                    uploaded_rows  INTEGER NOT NULL DEFAULT 0,
                    rejected_rows  INTEGER NOT NULL DEFAULT 0,
                    percent        INTEGER NOT NULL DEFAULT 0,
                    error          TEXT,
                    created_at     TEXT NOT NULL,
                    updated_at     TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS job_logs (
                    id      INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id  INTEGER NOT NULL,
                    ts      TEXT NOT NULL,
                    level   TEXT NOT NULL,
                    message TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_logs_job ON job_logs(job_id, id);
                CREATE TABLE IF NOT EXISTS row_errors (
                    id       INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id   INTEGER NOT NULL,
                    row_no   INTEGER NOT NULL,
                    source   TEXT NOT NULL,   -- LOCAL / PLATFORM
                    code     TEXT,
                    message  TEXT NOT NULL,
                    raw_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_errors_job ON row_errors(job_id, id);
                CREATE TABLE IF NOT EXISTS platform_records (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    id_number   TEXT NOT NULL,
                    course_code TEXT NOT NULL,
                    train_date  TEXT NOT NULL,
                    hours       TEXT NOT NULL,
                    name        TEXT,
                    job_id      INTEGER,
                    uploaded_at TEXT NOT NULL,
                    UNIQUE(id_number, course_code, train_date)
                );
                """
            )
        _initialized = True


# ---------- 任务 ----------

def create_job(filename: str, stored_path: str, mode: str = "NORMAL") -> int:
    now = _now()
    with _conn() as c:
        cur = c.execute(
            "INSERT INTO jobs(filename, stored_path, mode, status, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?)",
            (filename, stored_path, mode, "PENDING", now, now),
        )
        return cur.lastrowid


def update_job(job_id: int, **fields) -> None:
    if not fields:
        return
    fields["updated_at"] = _now()
    cols = ", ".join(f"{k} = ?" for k in fields)
    with _conn() as c:
        c.execute(f"UPDATE jobs SET {cols} WHERE id = ?", (*fields.values(), job_id))


def get_job(job_id: int) -> dict | None:
    with _conn() as c:
        row = c.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return dict(row) if row else None


def list_jobs() -> list[dict]:
    with _conn() as c:
        rows = c.execute("SELECT * FROM jobs ORDER BY id DESC").fetchall()
        return [dict(r) for r in rows]


# ---------- 日志 ----------

def add_log(job_id: int, level: str, message: str) -> None:
    with _conn() as c:
        c.execute(
            "INSERT INTO job_logs(job_id, ts, level, message) VALUES (?,?,?,?)",
            (job_id, _now_ms(), level, message),
        )
    print(f"[job {job_id}] {level}: {message}", flush=True)


def get_logs(job_id: int, after_id: int = 0) -> list[dict]:
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM job_logs WHERE job_id = ? AND id > ? ORDER BY id",
            (job_id, after_id),
        ).fetchall()
        return [dict(r) for r in rows]


# ---------- 行级错误 ----------

def add_error(job_id: int, row_no: int, source: str, code: str | None,
              message: str, raw: dict) -> None:
    with _conn() as c:
        c.execute(
            "INSERT INTO row_errors(job_id, row_no, source, code, message, raw_json)"
            " VALUES (?,?,?,?,?,?)",
            (job_id, row_no, source, code, message, json.dumps(raw, ensure_ascii=False)),
        )


def get_errors(job_id: int) -> list[dict]:
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM row_errors WHERE job_id = ? ORDER BY id", (job_id,)
        ).fetchall()
        return [dict(r) for r in rows]


# ---------- 模拟平台台账 ----------

def platform_record_exists(id_number: str, course_code: str, train_date: str) -> bool:
    with _conn() as c:
        row = c.execute(
            "SELECT 1 FROM platform_records WHERE id_number=? AND course_code=? AND train_date=?",
            (id_number, course_code, train_date),
        ).fetchone()
        return row is not None


def insert_platform_record(job_id: int, rec: dict) -> bool:
    """写入平台台账；重复返回 False。"""
    try:
        with _conn() as c:
            c.execute(
                "INSERT INTO platform_records(id_number, course_code, train_date, hours, name, job_id, uploaded_at)"
                " VALUES (?,?,?,?,?,?,?)",
                (rec["id_number"], rec["course_code"], rec["train_date"],
                 rec["hours"], rec.get("name"), job_id, _now()),
            )
        return True
    except sqlite3.IntegrityError:
        return False
