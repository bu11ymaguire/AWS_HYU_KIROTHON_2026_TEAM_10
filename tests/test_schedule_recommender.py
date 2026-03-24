"""시간표 추천기 단위 테스트."""

from __future__ import annotations

from datetime import time

import pytest

from src.cancellation_checker import CancellationChecker
from src.conflict_checker import ConflictChecker
from src.credit_validator import CreditValidator
from src.equivalent_manager import EquivalentManager
from src.models import (
    Course,
    EquivalentCourse,
    PrerequisiteRule,
    StudentInfo,
    TimeSlot,
)
from src.prerequisite_checker import PrerequisiteChecker
from src.schedule_recommender import ScheduleRecommender


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------

@pytest.fixture
def student() -> StudentInfo:
    return StudentInfo(
        student_id="2024012345",
        grade=2,
        semester=1,
        is_graduating=False,
        is_extended=False,
        is_2026_freshman=False,
        department="컴퓨터소프트웨어학부",
        has_multiple_major=False,
    )


@pytest.fixture
def credit_validator() -> CreditValidator:
    return CreditValidator(credit_rules={})


@pytest.fixture
def conflict_checker() -> ConflictChecker:
    return ConflictChecker()


@pytest.fixture
def prerequisite_checker() -> PrerequisiteChecker:
    rules = [
        PrerequisiteRule(
            prerequisite="기초학술영어",
            subsequent="전문학술영어",
            exemption_grades=["A", "B"],
        ),
    ]
    return PrerequisiteChecker(rules)


@pytest.fixture
def cancellation_checker() -> CancellationChecker:
    return CancellationChecker(cancel_rules={})


@pytest.fixture
def equivalent_manager() -> EquivalentManager:
    equivalents = [
        EquivalentCourse(
            old_course_id="DIS1025",
            old_name="Basic Quantitative Methods",
            new_course_id="FUT1007",
            new_name="데이터과학트렌드",
            relation_type="동일",
        ),
    ]
    return EquivalentManager(equivalents)


@pytest.fixture
def recommender(
    credit_validator: CreditValidator,
    conflict_checker: ConflictChecker,
    prerequisite_checker: PrerequisiteChecker,
    cancellation_checker: CancellationChecker,
    equivalent_manager: EquivalentManager,
) -> ScheduleRecommender:
    return ScheduleRecommender(
        credit_validator=credit_validator,
        conflict_checker=conflict_checker,
        prerequisite_checker=prerequisite_checker,
        cancellation_checker=cancellation_checker,
        equivalent_manager=equivalent_manager,
    )


def _make_course(
    name: str,
    course_id: str = "C001",
    credits: int = 3,
    time_slots: list[TimeSlot] | None = None,
    category: str = "전공필수",
    department: str = "컴퓨터소프트웨어학부",
    enrollment_count: int = 30,
    capacity: int = 40,
    is_english_only: bool = False,
    is_ic_pbl: bool = False,
    is_smart: bool = False,
) -> Course:
    return Course(
        course_id=course_id,
        name=name,
        credits=credits,
        time_slots=time_slots or [],
        category=category,
        department=department,
        enrollment_count=enrollment_count,
        capacity=capacity,
        is_english_only=is_english_only,
        is_ic_pbl=is_ic_pbl,
        is_smart=is_smart,
    )


# ------------------------------------------------------------------
# Tests: 통합 검증 수행 확인
# ------------------------------------------------------------------

class TestRecommendIntegration:
    """recommend()가 모든 검증을 수행하고 ScheduleResult를 반환하는지 확인."""

    def test_returns_schedule_result(
        self, recommender: ScheduleRecommender, student: StudentInfo
    ) -> None:
        courses = [
            _make_course("자료구조", course_id="CS201", credits=3, time_slots=[
                TimeSlot(day="월", start_time=time(9, 0), end_time=time(10, 30)),
            ]),
            _make_course("알고리즘", course_id="CS301", credits=3, time_slots=[
                TimeSlot(day="화", start_time=time(13, 0), end_time=time(14, 30)),
            ]),
        ]
        result = recommender.recommend(student, [], courses)

        assert result.timetable is not None
        assert result.credit_info is not None
        assert result.conflicts is not None
        assert isinstance(result.warnings, list)

    def test_credit_validation_performed(
        self, recommender: ScheduleRecommender, student: StudentInfo
    ) -> None:
        """학점 검증이 수행되어 credit_info에 결과가 포함된다."""
        courses = [_make_course("자료구조", credits=3)]
        result = recommender.recommend(student, [], courses)

        assert result.credit_info.current_credits == 3
        assert result.credit_info.min_credits == 10
        # 3학점 < 10학점 최소이므로 is_valid=False
        assert result.credit_info.is_valid is False

    def test_conflict_checking_performed(
        self, recommender: ScheduleRecommender, student: StudentInfo
    ) -> None:
        """시간 충돌 검증이 수행된다."""
        slot = TimeSlot(day="월", start_time=time(9, 0), end_time=time(10, 30))
        courses = [
            _make_course("자료구조", course_id="CS201", time_slots=[slot]),
            _make_course("운영체제", course_id="CS301", time_slots=[slot]),
        ]
        result = recommender.recommend(student, [], courses)

        assert result.conflicts.has_conflict is True
        assert any("시간 충돌" in w for w in result.warnings)


class TestPrerequisiteWarnings:
    """선수과목 미이수 경고가 warnings에 포함되는지 확인."""

    def test_missing_prerequisite_warning(
        self, recommender: ScheduleRecommender, student: StudentInfo
    ) -> None:
        courses = [
            _make_course("전문학술영어", course_id="ENG201", credits=3),
        ]
        result = recommender.recommend(student, [], courses)

        assert any("선수과목 미이수 경고" in w for w in result.warnings)

    def test_no_warning_when_prerequisite_completed(
        self, recommender: ScheduleRecommender, student: StudentInfo
    ) -> None:
        courses = [
            _make_course("전문학술영어", course_id="ENG201", credits=3),
        ]
        result = recommender.recommend(student, ["기초학술영어"], courses)

        assert not any("선수과목 미이수 경고" in w for w in result.warnings)

    def test_no_warning_with_english_grade_exemption(
        self, recommender: ScheduleRecommender, student: StudentInfo
    ) -> None:
        courses = [
            _make_course("전문학술영어", course_id="ENG201", credits=3),
        ]
        result = recommender.recommend(student, [], courses, english_grade="A")

        assert not any("선수과목 미이수 경고" in w for w in result.warnings)


class TestCancellationWarnings:
    """폐강 위험 경고가 warnings에 포함되는지 확인."""

    def test_at_risk_course_warning(
        self, recommender: ScheduleRecommender, student: StudentInfo
    ) -> None:
        """수강인원이 적은 과목은 폐강 위험 경고가 추가된다."""
        courses = [
            _make_course("특수과목", course_id="SP001", enrollment_count=5),
        ]
        result = recommender.recommend(student, [], courses)

        assert any("폐강 위험" in w for w in result.warnings)

    def test_no_cancellation_warning_for_safe_course(
        self, recommender: ScheduleRecommender, student: StudentInfo
    ) -> None:
        courses = [
            _make_course("자료구조", course_id="CS201", enrollment_count=30),
        ]
        result = recommender.recommend(student, [], courses)

        assert not any("폐강 위험" in w for w in result.warnings)


class TestEquivalentCourseAdvice:
    """동일/대치 교과목 안내가 warnings에 포함되는지 확인."""

    def test_equivalent_course_advice(
        self, recommender: ScheduleRecommender, student: StudentInfo
    ) -> None:
        courses = [
            _make_course("데이터과학트렌드", course_id="FUT1007"),
        ]
        completed = ["Basic Quantitative Methods"]
        result = recommender.recommend(student, completed, courses)

        assert any("동일/대치 교과목 안내" in w for w in result.warnings)


class TestTimetableGeneration:
    """시간표 2D 배열 생성 테스트."""

    def test_timetable_dimensions(
        self, recommender: ScheduleRecommender, student: StudentInfo
    ) -> None:
        """시간표는 15교시 × 5요일 크기여야 한다."""
        result = recommender.recommend(student, [], [])

        assert len(result.timetable) == 15  # 교시
        for row in result.timetable:
            assert len(row) == 5  # 요일 (월~금)

    def test_course_placed_in_timetable(
        self, recommender: ScheduleRecommender, student: StudentInfo
    ) -> None:
        """과목이 올바른 교시/요일에 배치된다."""
        courses = [
            _make_course("자료구조", course_id="CS201", time_slots=[
                TimeSlot(day="월", start_time=time(9, 0), end_time=time(10, 0)),
            ]),
        ]
        result = recommender.recommend(student, [], courses)

        # 1교시(row=0), 월요일(col=0)
        assert "자료구조" in result.timetable[0][0]

    def test_at_risk_label_in_timetable(
        self, recommender: ScheduleRecommender, student: StudentInfo
    ) -> None:
        """폐강 위험 과목은 시간표에 [폐강 위험] 표시가 추가된다."""
        courses = [
            _make_course("특수과목", course_id="SP001", enrollment_count=5, time_slots=[
                TimeSlot(day="화", start_time=time(10, 0), end_time=time(11, 0)),
            ]),
        ]
        result = recommender.recommend(student, [], courses)

        # 2교시(row=1), 화요일(col=1)
        assert "[폐강 위험]" in result.timetable[1][1]

    def test_prereq_missing_label_in_timetable(
        self, recommender: ScheduleRecommender, student: StudentInfo
    ) -> None:
        """선수과목 미이수 과목은 시간표에 [선수과목 미이수] 표시가 추가된다."""
        courses = [
            _make_course("전문학술영어", course_id="ENG201", time_slots=[
                TimeSlot(day="수", start_time=time(13, 0), end_time=time(14, 0)),
            ]),
        ]
        result = recommender.recommend(student, [], courses)

        # 5교시(row=4), 수요일(col=2)
        assert "[선수과목 미이수]" in result.timetable[4][2]

    def test_empty_cells_are_empty_string(
        self, recommender: ScheduleRecommender, student: StudentInfo
    ) -> None:
        """과목이 없는 셀은 빈 문자열이다."""
        result = recommender.recommend(student, [], [])

        for row in result.timetable:
            for cell in row:
                assert cell == ""

    def test_multi_period_course(
        self, recommender: ScheduleRecommender, student: StudentInfo
    ) -> None:
        """2교시에 걸치는 과목이 올바르게 배치된다."""
        courses = [
            _make_course("자료구조", course_id="CS201", time_slots=[
                TimeSlot(day="목", start_time=time(9, 0), end_time=time(11, 0)),
            ]),
        ]
        result = recommender.recommend(student, [], courses)

        # 1교시(row=0)와 2교시(row=1), 목요일(col=3)
        assert "자료구조" in result.timetable[0][3]
        assert "자료구조" in result.timetable[1][3]


# ------------------------------------------------------------------
# Tests: 수강포기 가능 여부 검증 (check_drop_eligibility)
# ------------------------------------------------------------------

class TestCheckDropEligibility:
    """check_drop_eligibility() 검증 테스트."""

    def test_drop_allowed_when_all_conditions_met(
        self, recommender: ScheduleRecommender, student: StudentInfo
    ) -> None:
        """모든 조건 충족 시 수강포기 가능."""
        current = [
            _make_course("자료구조", credits=3),
            _make_course("알고리즘", credits=3),
            _make_course("운영체제", credits=3),
            _make_course("네트워크", credits=3),
            _make_course("데이터베이스", credits=3),
        ]
        drop = [_make_course("네트워크", credits=3)]
        result = recommender.check_drop_eligibility(student, current, drop)

        assert result["can_drop"] is True
        assert result["reasons"] == []
        assert result["remaining_credits"] == 12

    def test_drop_denied_when_remaining_below_min(
        self, recommender: ScheduleRecommender, student: StudentInfo
    ) -> None:
        """잔여학점이 최소학점 미만이면 포기 불가."""
        current = [
            _make_course("자료구조", credits=3),
            _make_course("알고리즘", credits=3),
            _make_course("운영체제", credits=3),
        ]
        drop = [_make_course("운영체제", credits=3)]
        # 잔여 6학점 < 최소 10학점
        result = recommender.check_drop_eligibility(student, current, drop)

        assert result["can_drop"] is False
        assert any("최소학점" in r for r in result["reasons"])
        assert result["remaining_credits"] == 6

    def test_drop_denied_when_more_than_two_courses(
        self, recommender: ScheduleRecommender, student: StudentInfo
    ) -> None:
        """3과목 이상 포기 시 불가."""
        current = [
            _make_course("자료구조", credits=3),
            _make_course("알고리즘", credits=3),
            _make_course("운영체제", credits=3),
            _make_course("네트워크", credits=3),
            _make_course("데이터베이스", credits=3),
        ]
        drop = [
            _make_course("자료구조", credits=3),
            _make_course("알고리즘", credits=3),
            _make_course("운영체제", credits=3),
        ]
        result = recommender.check_drop_eligibility(student, current, drop)

        assert result["can_drop"] is False
        assert any("최대 2과목" in r for r in result["reasons"])

    def test_drop_denied_for_extended_student(
        self, recommender: ScheduleRecommender
    ) -> None:
        """학사학위취득유예자(is_extended=True)는 포기 불가."""
        extended_student = StudentInfo(
            student_id="2020012345",
            grade=5,
            semester=1,
            is_graduating=False,
            is_extended=True,
            is_2026_freshman=False,
            department="컴퓨터소프트웨어학부",
            has_multiple_major=False,
        )
        current = [
            _make_course("자료구조", credits=3),
            _make_course("알고리즘", credits=3),
        ]
        drop = [_make_course("알고리즘", credits=3)]
        result = recommender.check_drop_eligibility(extended_student, current, drop)

        assert result["can_drop"] is False
        assert any("학사학위취득유예자" in r for r in result["reasons"])

    def test_drop_two_courses_allowed(
        self, recommender: ScheduleRecommender, student: StudentInfo
    ) -> None:
        """정확히 2과목 포기는 허용된다 (잔여학점 충분 시)."""
        current = [
            _make_course("자료구조", credits=3),
            _make_course("알고리즘", credits=3),
            _make_course("운영체제", credits=3),
            _make_course("네트워크", credits=3),
            _make_course("데이터베이스", credits=3),
        ]
        drop = [
            _make_course("자료구조", credits=3),
            _make_course("알고리즘", credits=3),
        ]
        # 잔여 9학점 < 최소 10학점 → 학점 미달로 불가
        result = recommender.check_drop_eligibility(student, current, drop)

        # 2과목 제한은 통과하지만 잔여학점 미달
        assert any("최소학점" in r for r in result["reasons"])
        assert not any("최대 2과목" in r for r in result["reasons"])

    def test_multiple_violations_reported(
        self, recommender: ScheduleRecommender
    ) -> None:
        """여러 규칙 위반 시 모든 사유가 포함된다."""
        extended_student = StudentInfo(
            student_id="2020012345",
            grade=5,
            semester=1,
            is_graduating=False,
            is_extended=True,
            is_2026_freshman=False,
            department="컴퓨터소프트웨어학부",
            has_multiple_major=False,
        )
        current = [
            _make_course("자료구조", credits=1),
            _make_course("알고리즘", credits=1),
            _make_course("운영체제", credits=1),
            _make_course("네트워크", credits=1),
        ]
        drop = [
            _make_course("자료구조", credits=1),
            _make_course("알고리즘", credits=1),
            _make_course("운영체제", credits=1),
        ]
        result = recommender.check_drop_eligibility(extended_student, current, drop)

        assert result["can_drop"] is False
        # 유예자 + 3과목 초과 + 잔여학점 미달(1 < 1은 아님, extended min=1)
        assert any("학사학위취득유예자" in r for r in result["reasons"])
        assert any("최대 2과목" in r for r in result["reasons"])
