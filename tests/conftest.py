import os
import sys
import tempfile
from pathlib import Path

# 必须在导入 app 之前指向独立的测试数据目录
os.environ["TRAINING_IMPORT_HOME"] = tempfile.mkdtemp(prefix="ti_test_")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
