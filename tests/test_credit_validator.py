"""학점 검증기 단위 테스트."""

from __future__ import annotations

import pytest

from src.credit_validator import CreditValidator
from src.models import Course, CreditValidationResult, StudentInfo, TimeSlot


# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------

def _make_student(**overrides) -> StudentInfo:
    defaults = dict(
        student_id="2024012345",
        grade=2,
        semester=1,
        is_graduating=False,
        is_extended=False,
        is_2026_freshman=False,
        department="컴퓨터소프트웨어학부",
        has_multiple_major=False,
    )
    defaults.update(overrides)
    return StudentInfo(**defaults)


def _make_course(name: str = "과목A", credits: int = 3, category: str = "전공필수",
                 department: str = "컴퓨터소프트웨어학부") -> Course:
    return Course(
        course_id="C001",
        name=name,
        credits=credits,
        time_slots=[],
        category=category,
        department=department,
        enrollment_count=30,
        is_english_only=False,
        is_ic_pbl=False,
        is_smart=False,
    )


EMPTY_RULES: dict = {}


# ---------------------------------------------------------------------------
# 최소학점 테스트
# ---------------------------------------------------------------------------

class TestMinCredits:
    """_calculate_min_credits 테스트."""

    def test_regular_student_min_10(self):
        """1-1 ~ 4-1 일반 학생: min 10."""
        v = CreditValidator(EMPTY_RULES)
        for grade in range(1, 5):
            for sem in (1, 2):
                if grade == 4 and sem == 2:
                    continue
                s = _make_student(grade=grade, semester=sem)
                assert v._calculate_min_credits(s) == 10

    def test_graduating_4_2_min_3(self):
        """4-2 졸업예정: min 3."""
        v = CreditValidator(EMPTY_RULES)
        s = _make_student(grade=4, semester=2, is_graduating=True)
        assert v._calculate_min_credits(s) == 3

    def test_extended_min_1(self):
        """9학기 이상 학업연장: min 1."""
        v = CreditValidator(EMPTY_RULES)
        s = _make_student(grade=5, semester=1, is_extended=True)
        assert v._calculate_min_credits(s) == 1

    def test_extended_takes_priority_over_graduating(self):
        """학업연장이 졸업예정보다 우선."""
        v = CreditValidator(EMPTY_RULES)
        s = _make_student(grade=4, semester=2, is_graduating=True, is_extended=True)
        assert v._calculate_min_credits(s) == 1


# ---------------------------------------------------------------------------
# 최대학점 테스트
# ---------------------------------------------------------------------------

class TestMaxCredits:
    """_calculate_max_credits 테스트."""

    def test_regular_student_max_20(self):
        """일반 학생: max 20."""
        v = CreditValidator(EMPTY_RULES)
        s = _make_student()
        assert v._calculate_max_credits(s, []) == 20

    def test_2026_freshman_grade_1_2_max_20(self):
        """2026 신입생 1~2학년: max 20."""
        v = CreditValidator(EMPTY_RULES)
        for grade in (1, 2):
            s = _make_student(grade=grade, is_2026_freshman=True)
            assert v._calculate_max_credits(s, []) == 20

    def test_2026_freshman_grade_3_plus_max_18(self):
        """2026 신입생 3학년 이상(건축학부 제외): max 18."""
        v = CreditValidator(EMPTY_RULES)
        s = _make_student(grade=3, is_2026_freshman=True)
        assert v._calculate_max_credits(s, []) == 18

    def test_2026_freshman_architecture_grade_3_max_20(self):
        """2026 신입생 건축학부 3학년: max 20."""
        v = CreditValidator(EMPTY_RULES)
        s = _make_student(grade=3, is_2026_freshman=True, department="건축학부")
        assert v._calculate_max_credits(s, []) == 20

    def test_extra_credits_career_courses(self):
        """커리어개발/사회봉사/군사학 추가학점 최대 2."""
        v = CreditValidator(EMPTY_RULES)
        s = _make_student()
        courses = [
            _make_course(name="커리어개발Ⅰ", credits=1),
            _make_course(name="사회봉사", credits=1),
            _make_course(name="군사학", credits=1),
        ]
        # 3학점 중 최대 2학점만 추가
        assert v._calculate_max_credits(s, courses) == 22

    def test_extra_credits_multi_major(self):
        """다전공자 타전공 일반선택 추가학점 최대 3."""
        v = CreditValidator(EMPTY_RULES)
        s = _make_student(has_multiple_major=True)
        courses = [
            _make_course(name="타전공과목A", credits=3, category="일반선택", department="경영학과"),
            _make_course(name="타전공과목B", credits=3, category="일반선택", department="경영학과"),
        ]
        # 6학점 중 최대 3학점만 추가
        assert v._calculate_max_credits(s, courses) == 23

    def test_extra_credits_combined(self):
        """커리어개발 + 다전공 추가학점 합산."""
        v = CreditValidator(EMPTY_RULES)
        s = _make_student(has_multiple_major=True)
        courses = [
            _make_course(name="커리어개발Ⅰ", credits=1),
            _make_course(name="사회봉사", credits=1),
            _make_course(name="타전공과목", credits=3, category="일반선택", department="경영학과"),
        ]
        # base 20 + career 2 + multi 3 = 25
        assert v._calculate_max_credits(s, courses) == 25


# ---------------------------------------------------------------------------
# validate 통합 테스트
# ---------------------------------------------------------------------------

class TestValidate:
    """validate 메서드 테스트."""

    def test_valid_credits(self):
        """범위 내 학점: is_valid=True."""
        v = CreditValidator(EMPTY_RULES)
        s = _make_student()
        courses = [_make_course(credits=3) for _ in range(5)]  # 15학점
        result = v.validate(s, courses)
        assert result.is_valid is True
        assert result.current_credits == 15
        assert result.min_credits == 10
        assert result.max_credits == 20
        assert result.warnings == []

    def test_below_min_credits(self):
        """최소학점 미달: is_valid=False, 경고 포함."""
        v = CreditValidator(EMPTY_RULES)
        s = _make_student()
        courses = [_make_course(credits=3)]  # 3학점 < min 10
        result = v.validate(s, courses)
        assert result.is_valid is False
        assert any("학점 범위 위반" in w for w in result.warnings)

    def test_above_max_credits(self):
        """최대학점 초과: is_valid=False, 경고 포함."""
        v = CreditValidator(EMPTY_RULES)
        s = _make_student()
        courses = [_make_course(credits=3) for _ in range(8)]  # 24학점 > max 20
        result = v.validate(s, courses)
        assert result.is_valid is False
        assert any("학점 범위 위반" in w for w in result.warnings)

    def test_warning_includes_range(self):
        """경고 메시지에 허용 범위 포함."""
        v = CreditValidator(EMPTY_RULES)
        s = _make_student()
        courses = [_make_course(credits=3)]  # 3학점
        result = v.validate(s, courses)
        warning = result.warnings[0]
        assert "10" in warning and "20" in warning

    def test_graduating_student_low_credits_valid(self):
        """졸업예정 학생 3학점: 유효."""
        v = CreditValidator(EMPTY_RULES)
        s = _make_student(grade=4, semester=2, is_graduating=True)
        courses = [_make_course(credits=3)]
        result = v.validate(s, courses)
        assert result.is_valid is True
        assert result.min_credits == 3

    def test_extra_credits_in_result(self):
        """추가학점이 결과에 반영."""
        v = CreditValidator(EMPTY_RULES)
        s = _make_student()
        courses = [
            _make_course(credits=3) for _ in range(6)
        ] + [
            _make_course(name="커리어개발Ⅰ", credits=1),
        ]
        result = v.validate(s, courses)
        assert result.extra_credits == 1
        assert result.max_credits == 21
