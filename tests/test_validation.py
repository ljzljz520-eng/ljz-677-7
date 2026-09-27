"""校验规则单元测试。"""
from datetime import date

from app.validation import (
    compute_id_check_code,
    validate_course,
    validate_hours,
    validate_id_number,
    validate_name,
    validate_row,
    validate_train_date,
)

TODAY = date(2026, 9, 26)


def make_id(body17: str) -> str:
    return body17 + compute_id_check_code(body17)


class TestIdNumber:
    def test_valid(self):
        assert validate_id_number(make_id("11010119900307751"), TODAY) is None

    def test_valid_with_x_check_code(self):
        body = next(b for b in (f"11010119900307{i:03d}" for i in range(1000))
                    if compute_id_check_code(b) == "X")
        assert validate_id_number(make_id(body), TODAY) is None
        assert validate_id_number(make_id(body)[:-1] + "x", TODAY) is None  # 小写 x 也接受

    def test_empty(self):
        assert "空" in validate_id_number("", TODAY)

    def test_wrong_length(self):
        assert "18位" in validate_id_number("1101011990030775", TODAY)

    def test_wrong_check_code(self):
        good = make_id("11010119900307751")
        bad = good[:-1] + ("0" if good[-1] != "0" else "1")
        assert "校验码" in validate_id_number(bad, TODAY)

    def test_invalid_birth_month(self):
        assert "出生日期无效" in validate_id_number(make_id("11010119991307751"), TODAY)

    def test_future_birth(self):
        assert "不合理" in validate_id_number(make_id("11010120300107751"), TODAY)


class TestName:
    def test_valid(self):
        assert validate_name("张伟") is None
        assert validate_name("Anna") is None
        assert validate_name("阿不都·外力") is None

    def test_empty(self):
        assert "空" in validate_name("")

    def test_too_short(self):
        assert validate_name("李") is not None

    def test_too_long(self):
        assert validate_name("张" * 31) is not None

    def test_illegal_chars(self):
        assert validate_name("张三123") is not None


class TestCourse:
    def test_valid(self):
        assert validate_course("AQ-101", "安全生产法规") is None

    def test_unknown_code(self):
        assert "不存在" in validate_course("AQ-999", "未知课程")

    def test_name_mismatch(self):
        assert "不匹配" in validate_course("AQ-101", "高处作业安全")

    def test_empty(self):
        assert "空" in validate_course("", "安全生产法规")


class TestHours:
    def test_valid(self):
        assert validate_hours("4", "AQ-101") is None
        assert validate_hours("4.5", "AQ-101") is None
        assert validate_hours("16", "AQ-102") is None

    def test_not_number(self):
        assert "数字" in validate_hours("abc", "AQ-101")

    def test_zero_and_negative(self):
        assert "大于0" in validate_hours("0", "AQ-101")
        assert "大于0" in validate_hours("-2", "AQ-101")

    def test_hard_limit(self):
        assert "45" in validate_hours("45.5", "AQ-102")

    def test_too_many_decimals(self):
        assert "1位小数" in validate_hours("4.55", "AQ-101")

    def test_course_limit(self):
        assert "课程上限" in validate_hours("9", "AQ-101")   # AQ-101 上限 8
        assert validate_hours("9", "AQ-102") is None        # AQ-102 上限 16


class TestTrainDate:
    def test_valid(self):
        assert validate_train_date("2026-09-25", TODAY) is None
        assert validate_train_date("2026-09-26", TODAY) is None  # 当天可以

    def test_bad_format(self):
        assert "YYYY-MM-DD" in validate_train_date("2026/09/01", TODAY)

    def test_invalid_date(self):
        assert "有效日期" in validate_train_date("2026-02-30", TODAY)

    def test_future(self):
        assert "晚于今天" in validate_train_date("2027-01-01", TODAY)


class TestRow:
    def test_all_valid(self):
        row = {"name": "张伟", "id_number": make_id("11010119900307751"),
               "course_code": "AQ-101", "course_name": "安全生产法规",
               "hours": "4", "train_date": "2026-09-10"}
        assert validate_row(row, TODAY) == []

    def test_multiple_errors(self):
        row = {"name": "", "id_number": "123", "course_code": "AQ-999",
               "course_name": "无", "hours": "0", "train_date": "2027-01-01"}
        errors = validate_row(row, TODAY)
        assert len(errors) == 5
