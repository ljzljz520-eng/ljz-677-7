"""本地课程目录（培训机构的课程库）。

max_hours: 单条学时记录的本地校验上限。
"""

COURSES = {
    "AQ-101": {"name": "安全生产法规", "max_hours": 8},
    "AQ-102": {"name": "高处作业安全", "max_hours": 16},
    "AQ-103": {"name": "有限空间作业", "max_hours": 12},
    "AQ-104": {"name": "电气安全基础", "max_hours": 8},
    "AQ-105": {"name": "应急救援演练", "max_hours": 6},
    "AQ-106": {"name": "职业健康培训", "max_hours": 8},  # 本地新课，行业平台尚未收录
}

# 单条学时记录的硬性上限（防呆）
MAX_HOURS_PER_RECORD = 45
