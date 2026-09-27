"""行级数据校验：姓名、证件号（GB 11643 身份证校验码）、课程、学时数、培训日期。"""
import re
from datetime import date
from decimal import Decimal, InvalidOperation

from .courses import COURSES, MAX_HOURS_PER_RECORD

# GB 11643-1999：18 位身份证加权因子与校验码映射
_ID_WEIGHTS = [7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2]
_ID_CHECK_CODES = "10X98765432"

_NAME_RE = re.compile(r"^[一-龥A-Za-z·\s]{2,30}$")
_ID_RE = re.compile(r"^\d{17}[\dXx]$")


def compute_id_check_code(body17: str) -> str:
    """计算 17 位身份证本体的校验码（供测试/造数使用）。"""
    total = sum(int(body17[i]) * _ID_WEIGHTS[i] for i in range(17))
    return _ID_CHECK_CODES[total % 11]


def validate_name(name: str) -> str | None:
    if not name:
        return "姓名为空"
    if not _NAME_RE.match(name):
        return "姓名须为2-30个字符的中文或英文（可含·）"
    return None


def validate_id_number(id_number: str, today: date | None = None) -> str | None:
    today = today or date.today()
    if not id_number:
        return "证件号为空"
    if not _ID_RE.match(id_number):
        return "证件号须为18位居民身份证号（末位可为X）"
    try:
        birth = date(int(id_number[6:10]), int(id_number[10:12]), int(id_number[12:14]))
    except ValueError:
        return "证件号出生日期无效"
    if birth.year < 1900 or birth > today:
        return "证件号出生日期不合理"
    if compute_id_check_code(id_number[:17]) != id_number[17].upper():
        return "证件号校验码错误"
    return None


def validate_course(course_code: str, course_name: str) -> str | None:
    if not course_code:
        return "课程代码为空"
    course = COURSES.get(course_code)
    if course is None:
        return f"课程代码 {course_code} 不存在于课程目录"
    if not course_name:
        return "课程名称为空"
    if course_name != course["name"]:
        return f"课程名称与课程代码不匹配（{course_code} 应为：{course['name']}）"
    return None


def validate_hours(hours: str, course_code: str) -> str | None:
    if not hours:
        return "学时为空"
    try:
        value = Decimal(hours)
    except InvalidOperation:
        return "学时须为数字"
    if value.is_nan() or value.is_infinite():
        return "学时须为数字"
    if value <= 0:
        return "学时须大于0"
    if value > MAX_HOURS_PER_RECORD:
        return f"学时超过单次记录上限（{MAX_HOURS_PER_RECORD}学时）"
    if -value.as_tuple().exponent > 1:
        return "学时最多保留1位小数"
    course = COURSES.get(course_code)
    if course and value > Decimal(str(course["max_hours"])):
        return f"学时超过课程上限（{course_code} 上限 {course['max_hours']} 学时）"
    return None


def validate_train_date(train_date: str, today: date | None = None) -> str | None:
    today = today or date.today()
    if not train_date:
        return "培训日期为空"
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", train_date):
        return "培训日期格式须为 YYYY-MM-DD"
    try:
        d = date(*map(int, train_date.split("-")))
    except ValueError:
        return "培训日期不是有效日期"
    if d > today:
        return "培训日期不能晚于今天"
    return None


def validate_row(row: dict, today: date | None = None) -> list[str]:
    """校验一整行，返回错误消息列表（空列表表示通过）。"""
    errors = []
    for msg in (
        validate_name(row.get("name", "")),
        validate_id_number(row.get("id_number", ""), today),
        validate_course(row.get("course_code", ""), row.get("course_name", "")),
        validate_hours(row.get("hours", ""), row.get("course_code", "")),
        validate_train_date(row.get("train_date", ""), today),
    ):
        if msg:
            errors.append(msg)
    return errors
