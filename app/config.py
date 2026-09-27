"""全局配置：数据目录（可通过环境变量 TRAINING_IMPORT_HOME 覆盖，便于测试）。"""
import os
from pathlib import Path

BASE_DIR = Path(
    os.environ.get("TRAINING_IMPORT_HOME")
    or (Path(__file__).resolve().parent.parent / "data")
)
UPLOAD_DIR = BASE_DIR / "uploads"
EXPORT_DIR = BASE_DIR / "exports"
DB_PATH = BASE_DIR / "app.db"


def ensure_dirs() -> None:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
