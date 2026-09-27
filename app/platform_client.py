"""模拟行业平台客户端。

真实环境中这里是对行业监管平台的 HTTP 调用；本项目用确定性规则模拟平台侧校验，
便于演示与测试：

- P3001 课程未收录：平台课程目录与本地不完全同步（如 AQ-106 平台尚未收录）
- P2001 学时超平台上限：部分课程平台上限低于本地（AQ-102 平台12 / AQ-105 平台4）
- P1001 学员未注册：演示规则——证件号第 17 位为 '9' 视为未在平台注册
- P2002 重复上报：平台台账已存在 同学员+同课程+同日期 的记录
"""
import time
from decimal import Decimal

from . import database as db

PLATFORM_COURSES = {
    "AQ-101": {"name": "安全生产法规", "max_hours": 8},
    "AQ-102": {"name": "高处作业安全", "max_hours": 12},   # 平台低于本地的 16
    "AQ-103": {"name": "有限空间作业", "max_hours": 12},
    "AQ-104": {"name": "电气安全基础", "max_hours": 8},
    "AQ-105": {"name": "应急救援演练", "max_hours": 4},    # 平台低于本地的 6
    # AQ-106 平台未收录
}

UNREGISTERED_SEQ_CHAR = "9"  # 演示规则：证件号第17位（顺序码末位）为 9 → 平台未注册

# 平台错误码说明（供前端/文档展示）
PLATFORM_ERROR_CODES = {
    "P1001": "学员未在行业平台注册",
    "P2001": "学时超过课程平台上限",
    "P2002": "平台已存在相同记录（重复上报）",
    "P3001": "平台未收录该课程",
}


class IndustryPlatformClient:
    def __init__(self, latency: float = 0.3):
        self.latency = latency  # 模拟网络往返延迟（秒/批）

    def _check(self, rec: dict) -> tuple[str, str] | None:
        course = PLATFORM_COURSES.get(rec["course_code"])
        if course is None:
            return "P3001", f"平台未收录课程 {rec['course_code']}（课程已停用或未同步）"
        if Decimal(rec["hours"]) > Decimal(str(course["max_hours"])):
            return "P2001", f"学时超过平台上限（{rec['course_code']} 平台上限 {course['max_hours']} 学时）"
        if len(rec["id_number"]) >= 17 and rec["id_number"][16] == UNREGISTERED_SEQ_CHAR:
            return "P1001", "学员未在行业平台注册"
        if db.platform_record_exists(rec["id_number"], rec["course_code"], rec["train_date"]):
            return "P2002", "平台已存在同学员同课程同日期的学时记录"
        return None

    def upload_batch(self, job_id: int, records: list[dict]) -> tuple[list[dict], list[dict]]:
        """上送一批记录，返回 (成功列表, 异常明细列表)。"""
        time.sleep(self.latency)
        accepted, rejected = [], []
        for rec in records:
            err = self._check(rec)
            if err is None and not db.insert_platform_record(job_id, rec):
                err = ("P2002", "平台已存在同学员同课程同日期的学时记录")
            if err:
                rejected.append({"row_no": rec["row_no"], "code": err[0],
                                 "message": err[1], "raw": rec})
            else:
                accepted.append(rec)
        return accepted, rejected
