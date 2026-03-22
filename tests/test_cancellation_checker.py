"""폐강 판정기 테스트.

CancellationChecker의 별도기준 면제, 일반기준 적용, 통합 판정 로직을 검증한다.
"""

from __future__ import annotations

from datetime import time

import pytest

from src.cancellation_checker import CancellationChecker
from src.models import CancellationResult, Course, DepartmentInfo, TimeSlot


# ------------------------------------------------------------------
# 헬퍼
# ------------------------------------------------------------------
def _make_course(
    name: str = "일반과목",
    category: str = "전공필수",
    enrollment_count: int = 15,
    is_english_only: bool = False,
    is_ic_pbl: bool = False,
    is_smart: bool = False,
    department: str = "컴퓨터소프트웨어학부",
) -> Course:
    return Course(
        course_id="CSE1001",
        name=name,
        credits=3,
        time_slots=[],
        category=category,
        department=department,
        enrollment_count=enrollment_count,
        is_english_only=is_english_only,
        is_ic_pbl=is_ic_pbl,
        is_smart=is_smart,
    )


def _make_dept(total: int) -> DepartmentInfo:
    """단일 학년에 total 명의 재학인원을 가진 학과 생성."""
    return DepartmentInfo(name="컴퓨터소프트웨어학부", enrollment_by_grade={1: total})


def _checker() -> CancellationChecker:
    return CancellationChecker(cancel_rules={})


# ==================================================================
# 별도기준 면제 테스트
# ==================================================================
class TestSpecialExempt:
    """별도기준 대상 과목은 항상 폐강 위험 False."""

    @pytest.mark.parametrize(
        "name",
        [
            "커리어개발Ⅰ",
            "커리어개발Ⅱ",
            "종합설계",
            "캡스톤디자인",
            "실용공학연구",
            "사회봉사",
            "교직",
            "연구실현장실습",
            "실용연구심화",
            "ROTC",
        ],
    )
    def test_special_exempt_courses_never_at_risk(self, name: str) -> None:
        checker = _checker()
        course = _make_course(name=name, enrollment_count=0)
        dept = _make_dept(100)
        result = checker.check(course, dept)
        assert result.is_at_risk is False
        assert result.applied_rule == "별도기준"

    def test_special_exempt_category_virtual_campus(self) -> None:
        checker = _checker()
        course = _make_course(
            name="가상대학과목A",
            category="핵심교양_가상대학영역",
            enrollment_count=0,
        )
        dept = _make_dept(100)
        result = checker.check(course, dept)
        assert result.is_at_risk is False
        assert result.applied_rule == "별도기준"

    def test_special_exempt_priority_over_general(self) -> None:
        """별도기준 대상이면 일반기준에 해당해도 폐강 위험 False."""
        checker = _checker()
        # 수강인원 0명이지만 별도기준 대상
        course = _make_course(name="캡스톤디자인", enrollment_count=0)
        dept = _make_dept(100)
        result = checker.check(course, dept)
        assert result.is_at_risk is False
        assert result.applied_rule == "별도기준"


# ==================================================================
# 일반기준: 재학인원 25명 이상
# ==================================================================
class TestGeneralRuleHighEnrollment:
    """재학인원 25명 이상 + 일반교과목/핵심교양: 수강인원 10명 미만이면 폐강 위험."""

    def test_at_risk_when_below_10(self) -> None:
        checker = _checker()
        course = _make_course(enrollment_count=9)
        dept = _make_dept(30)
        result = checker.check(course, dept)
        assert result.is_at_risk is True
        assert result.applied_rule == "일반기준"

    def test_safe_when_at_10(self) -> None:
        checker = _checker()
        course = _make_course(enrollment_count=10)
        dept = _make_dept(30)
        result = checker.check(course, dept)
        assert result.is_at_risk is False

    def test_safe_when_above_10(self) -> None:
        checker = _checker()
        course = _make_course(enrollment_count=25)
        dept = _make_dept(50)
        result = checker.check(course, dept)
        assert result.is_at_risk is False

    def test_boundary_enrollment_25(self) -> None:
        checker = _checker()
        course = _make_course(enrollment_count=9)
        dept = _make_dept(25)
        result = checker.check(course, dept)
        assert result.is_at_risk is True


# ==================================================================
# 일반기준: 재학인원 15~24명
# ==================================================================
class TestGeneralRuleMidEnrollment:
    """재학인원 15~24명 + 일반교과목: 수강인원 < 재학인원의 40%이면 폐강 위험."""

    def test_at_risk_below_40_percent(self) -> None:
        checker = _checker()
        # 재학인원 20명 → 40% = 8명, 수강인원 7명 → 위험
        course = _make_course(enrollment_count=7)
        dept = _make_dept(20)
        result = checker.check(course, dept)
        assert result.is_at_risk is True

    def test_safe_at_40_percent(self) -> None:
        checker = _checker()
        # 재학인원 20명 → 40% = 8명, 수강인원 8명 → 안전
        course = _make_course(enrollment_count=8)
        dept = _make_dept(20)
        result = checker.check(course, dept)
        assert result.is_at_risk is False

    def test_boundary_enrollment_15(self) -> None:
        checker = _checker()
        # 재학인원 15명 → 40% = 6명, 수강인원 5명 → 위험
        course = _make_course(enrollment_count=5)
        dept = _make_dept(15)
        result = checker.check(course, dept)
        assert result.is_at_risk is True

    def test_boundary_enrollment_24(self) -> None:
        checker = _checker()
        # 재학인원 24명 → 40% = 9.6 → ceil = 10명, 수강인원 9명 → 위험
        course = _make_course(enrollment_count=9)
        dept = _make_dept(24)
        result = checker.check(course, dept)
        assert result.is_at_risk is True


# ==================================================================
# 일반기준: 재학인원 14명 이하
# ==================================================================
class TestGeneralRuleLowEnrollment:
    """재학인원 14명 이하: 수강인원 6명 미만이면 폐강 위험."""

    def test_at_risk_below_6(self) -> None:
        checker = _checker()
        course = _make_course(enrollment_count=5)
        dept = _make_dept(10)
        result = checker.check(course, dept)
        assert result.is_at_risk is True

    def test_safe_at_6(self) -> None:
        checker = _checker()
        course = _make_course(enrollment_count=6)
        dept = _make_dept(10)
        result = checker.check(course, dept)
        assert result.is_at_risk is False

    def test_boundary_enrollment_14(self) -> None:
        checker = _checker()
        course = _make_course(enrollment_count=5)
        dept = _make_dept(14)
        result = checker.check(course, dept)
        assert result.is_at_risk is True


# ==================================================================
# 영어전용 / IC-PBL 기준
# ==================================================================
class TestEnglishAndICPBL:
    """영어전용/제2외국어전용/IC-PBL: 수강인원 8명 미만이면 폐강 위험."""

    def test_english_only_at_risk(self) -> None:
        checker = _checker()
        course = _make_course(is_english_only=True, enrollment_count=7)
        dept = _make_dept(100)
        result = checker.check(course, dept)
        assert result.is_at_risk is True

    def test_english_only_safe(self) -> None:
        checker = _checker()
        course = _make_course(is_english_only=True, enrollment_count=8)
        dept = _make_dept(100)
        result = checker.check(course, dept)
        assert result.is_at_risk is False

    def test_ic_pbl_at_risk(self) -> None:
        checker = _checker()
        course = _make_course(is_ic_pbl=True, enrollment_count=7)
        dept = _make_dept(100)
        result = checker.check(course, dept)
        assert result.is_at_risk is True

    def test_ic_pbl_safe(self) -> None:
        checker = _checker()
        course = _make_course(is_ic_pbl=True, enrollment_count=8)
        dept = _make_dept(100)
        result = checker.check(course, dept)
        assert result.is_at_risk is False


# ==================================================================
# 전공심화 스마트교과 기준
# ==================================================================
class TestSmartCourse:
    """전공심화 스마트교과: 수강인원 6명 미만이면 폐강 위험."""

    def test_smart_at_risk(self) -> None:
        checker = _checker()
        course = _make_course(
            category="전공심화", is_smart=True, enrollment_count=5
        )
        dept = _make_dept(100)
        result = checker.check(course, dept)
        assert result.is_at_risk is True

    def test_smart_safe(self) -> None:
        checker = _checker()
        course = _make_course(
            category="전공심화", is_smart=True, enrollment_count=6
        )
        dept = _make_dept(100)
        result = checker.check(course, dept)
        assert result.is_at_risk is False

    def test_smart_non_전공심화_uses_general_rule(self) -> None:
        """is_smart=True이지만 category가 전공심화가 아니면 일반기준 적용."""
        checker = _checker()
        course = _make_course(
            category="전공필수", is_smart=True, enrollment_count=5
        )
        dept = _make_dept(10)  # 14명 이하 → 6명 미만 기준
        result = checker.check(course, dept)
        assert result.is_at_risk is True
