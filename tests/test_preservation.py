"""Preservation property tests for schedule logic improvement.

These tests verify EXISTING behavior is maintained before and after the fix.
They MUST PASS on the current unfixed code.

Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import time

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from src.models import Course, StudentInfo, TimeSlot, ParsedData
from src.schedule_recommender import ScheduleRecommender
from src.cancellation_checker import CancellationChecker
from src.conflict_checker import ConflictChecker
from src.credit_validator import CreditValidator
from src.equivalent_manager import EquivalentManager
from src.prerequisite_checker import PrerequisiteChecker


# ------------------------------------------------------------------
# Strategies
# ------------------------------------------------------------------

@st.composite
def course_strategy(draw: st.DrawFn) -> Course:
    """Generate a Course with valid fields (NO rating/review_count — current model)."""
    enrollment = draw(st.integers(min_value=0, max_value=200))
    capacity = draw(st.integers(min_value=1, max_value=200))
    return Course(
        course_id=draw(st.text(min_size=1, max_size=8, alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")),
        name=draw(st.text(min_size=1, max_size=20, alphabet="가나다라마바사아자차카타파하과목수업")),
        credits=draw(st.integers(min_value=1, max_value=6)),
        time_slots=[],
        category=draw(st.sampled_from(["전공필수", "전공선택", "교양필수", "교양선택", "일반선택"])),
        department=draw(st.sampled_from(["컴퓨터소프트웨어학부", "융합전자공학부", "수학과", "물리학과"])),
        enrollment_count=enrollment,
        is_english_only=False,
        is_ic_pbl=False,
        is_smart=False,
        capacity=capacity,
    )


@st.composite
def course_with_positive_capacity_strategy(draw: st.DrawFn) -> Course:
    """Generate a Course with capacity > 0."""
    enrollment = draw(st.integers(min_value=0, max_value=200))
    capacity = draw(st.integers(min_value=1, max_value=200))
    return Course(
        course_id=draw(st.text(min_size=1, max_size=8, alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")),
        name=draw(st.text(min_size=1, max_size=20, alphabet="가나다라마바사아자차카타파하과목수업")),
        credits=draw(st.integers(min_value=1, max_value=6)),
        time_slots=[],
        category="전공필수",
        department="컴퓨터소프트웨어학부",
        enrollment_count=enrollment,
        is_english_only=False,
        is_ic_pbl=False,
        is_smart=False,
        capacity=capacity,
    )


_DAYS = ["월", "화", "수", "목", "금"]

# Fixed time slot pairs that don't overlap with each other
_NON_OVERLAPPING_SLOTS = [
    ("월", time(9, 0), time(10, 0)),
    ("화", time(9, 0), time(10, 0)),
    ("수", time(9, 0), time(10, 0)),
    ("목", time(9, 0), time(10, 0)),
    ("금", time(9, 0), time(10, 0)),
    ("월", time(14, 0), time(15, 0)),
    ("화", time(14, 0), time(15, 0)),
    ("수", time(14, 0), time(15, 0)),
]


def _make_course(
    name: str,
    course_id: str = "C001",
    credits: int = 3,
    time_slots: list[TimeSlot] | None = None,
    enrollment_count: int = 30,
    capacity: int = 40,
) -> Course:
    return Course(
        course_id=course_id,
        name=name,
        credits=credits,
        time_slots=time_slots or [],
        category="전공필수",
        department="컴퓨터소프트웨어학부",
        enrollment_count=enrollment_count,
        is_english_only=False,
        is_ic_pbl=False,
        is_smart=False,
        capacity=capacity,
    )


def _make_recommender() -> ScheduleRecommender:
    return ScheduleRecommender(
        credit_validator=CreditValidator(credit_rules={}),
        conflict_checker=ConflictChecker(),
        prerequisite_checker=PrerequisiteChecker([]),
        cancellation_checker=CancellationChecker(cancel_rules={}),
        equivalent_manager=EquivalentManager([]),
    )


def _make_student() -> StudentInfo:
    return StudentInfo(
        student_id="2024000000",
        grade=3,
        semester=1,
        is_graduating=False,
        is_extended=False,
        is_2026_freshman=False,
        department="컴퓨터소프트웨어학부",
        has_multiple_major=False,
    )


# ------------------------------------------------------------------
# Property 2.1: analyze_difficulty() returns correct fields for capacity > 0
# Validates: Requirements 3.1
# ------------------------------------------------------------------

class TestAnalyzeDifficultyPreservation:
    """analyze_difficulty()가 capacity > 0인 과목에 대해
    name, enrolled, capacity, ratio 필드를 반환하고
    ratio = enrollment_count / capacity 임을 검증한다."""

    @given(courses=st.lists(course_with_positive_capacity_strategy(), min_size=1, max_size=5))
    @settings(max_examples=50)
    def test_results_contain_required_fields(self, courses: list[Course]) -> None:
        """**Validates: Requirements 3.1**

        capacity > 0인 과목에 대해 결과에 name, enrolled, capacity, ratio 필드가 존재한다.
        """
        results = ScheduleRecommender.analyze_difficulty(courses)

        for r in results:
            assert "name" in r, f"결과에 'name' 필드가 없음: {r}"
            assert "enrolled" in r, f"결과에 'enrolled' 필드가 없음: {r}"
            assert "capacity" in r, f"결과에 'capacity' 필드가 없음: {r}"
            assert "ratio" in r, f"결과에 'ratio' 필드가 없음: {r}"

    @given(courses=st.lists(course_with_positive_capacity_strategy(), min_size=1, max_size=5))
    @settings(max_examples=50)
    def test_ratio_equals_enrollment_over_capacity(self, courses: list[Course]) -> None:
        """**Validates: Requirements 3.1**

        capacity > 0인 과목에 대해 모든 결과의 ratio = enrolled / capacity 이다.
        """
        results = ScheduleRecommender.analyze_difficulty(courses)

        for r in results:
            cap = r["capacity"]
            if isinstance(cap, int) and cap > 0:
                expected_ratio = round(r["enrolled"] / cap, 2)
                assert r["ratio"] == expected_ratio, (
                    f"ratio 불일치: expected {expected_ratio}, got {r['ratio']} "
                    f"for course {r['name']} (enrolled={r['enrolled']}, capacity={cap})"
                )


# ------------------------------------------------------------------
# Property 2.2: recommend_alternatives() excludes time-conflicting combos
# Validates: Requirements 3.2
# ------------------------------------------------------------------

class TestRecommendAlternativesConflictExclusion:
    """recommend_alternatives()가 시간 충돌 조합을 제외하는지 검증한다."""

    def test_conflicting_sections_excluded(self) -> None:
        """**Validates: Requirements 3.2**

        동일 시간대의 분반 조합은 결과에서 제외된다.
        """
        recommender = _make_recommender()
        student = _make_student()

        # 과목 A: 1개 분반 (월 9-10)
        course_a = _make_course(
            "자료구조", course_id="DS001",
            time_slots=[TimeSlot(day="월", start_time=time(9, 0), end_time=time(10, 0))],
        )

        # 과목 B 분반1: 월 9-10 (충돌!)
        course_b1 = _make_course(
            "알고리즘", course_id="ALGO1",
            time_slots=[TimeSlot(day="월", start_time=time(9, 0), end_time=time(10, 0))],
        )

        # 과목 B 분반2: 화 9-10 (충돌 없음)
        course_b2 = _make_course(
            "알고리즘", course_id="ALGO2",
            time_slots=[TimeSlot(day="화", start_time=time(9, 0), end_time=time(10, 0))],
        )

        all_courses = [course_a, course_b1, course_b2]

        plans = recommender.recommend_alternatives(
            student=student,
            completed_courses=[],
            all_available_courses=all_courses,
            desired_names=["자료구조", "알고리즘"],
            max_plans=5,
        )

        # 충돌 없는 조합만 반환되어야 함
        for plan in plans:
            assert not plan.conflicts.has_conflict, (
                "충돌이 있는 조합이 결과에 포함됨"
            )

    def test_all_conflicting_returns_empty(self) -> None:
        """**Validates: Requirements 3.2**

        모든 분반 조합이 충돌하면 빈 리스트를 반환한다.
        """
        recommender = _make_recommender()
        student = _make_student()

        # 두 과목 모두 월 9-10에만 분반이 있음 → 모든 조합 충돌
        course_a = _make_course(
            "자료구조", course_id="DS001",
            time_slots=[TimeSlot(day="월", start_time=time(9, 0), end_time=time(10, 0))],
        )
        course_b = _make_course(
            "알고리즘", course_id="ALGO1",
            time_slots=[TimeSlot(day="월", start_time=time(9, 0), end_time=time(10, 0))],
        )

        plans = recommender.recommend_alternatives(
            student=student,
            completed_courses=[],
            all_available_courses=[course_a, course_b],
            desired_names=["자료구조", "알고리즘"],
            max_plans=5,
        )

        assert len(plans) == 0, "모든 조합이 충돌하면 빈 리스트를 반환해야 함"


# ------------------------------------------------------------------
# Property 2.3: recommend_alternatives() applies free_days filter
# Validates: Requirements 3.2
# ------------------------------------------------------------------

class TestRecommendAlternativesFreeDaysFilter:
    """recommend_alternatives()가 공강 요일 필터를 적용하는지 검증한다."""

    def test_free_days_filter_excludes_sections(self) -> None:
        """**Validates: Requirements 3.2**

        공강 요일에 수업이 있는 분반은 제외된다.
        """
        recommender = _make_recommender()
        student = _make_student()

        # 과목 분반1: 월요일 수업
        section_mon = _make_course(
            "자료구조", course_id="DS_MON",
            time_slots=[TimeSlot(day="월", start_time=time(9, 0), end_time=time(10, 0))],
        )
        # 과목 분반2: 화요일 수업
        section_tue = _make_course(
            "자료구조", course_id="DS_TUE",
            time_slots=[TimeSlot(day="화", start_time=time(9, 0), end_time=time(10, 0))],
        )

        all_courses = [section_mon, section_tue]

        # 월요일 공강 지정
        plans = recommender.recommend_alternatives(
            student=student,
            completed_courses=[],
            all_available_courses=all_courses,
            desired_names=["자료구조"],
            free_days=["월"],
            max_plans=5,
        )

        # 월요일 분반은 제외되고 화요일 분반만 포함
        for plan in plans:
            timetable = plan.timetable
            # 월요일(col=0)에 자료구조가 없어야 함
            for row in timetable:
                assert "자료구조" not in row[0], (
                    "공강 요일(월)에 과목이 배치됨"
                )

    def test_all_sections_on_free_day_returns_empty(self) -> None:
        """**Validates: Requirements 3.2**

        모든 분반이 공강 요일에만 있으면 빈 리스트를 반환한다.
        """
        recommender = _make_recommender()
        student = _make_student()

        section1 = _make_course(
            "자료구조", course_id="DS1",
            time_slots=[TimeSlot(day="월", start_time=time(9, 0), end_time=time(10, 0))],
        )
        section2 = _make_course(
            "자료구조", course_id="DS2",
            time_slots=[TimeSlot(day="월", start_time=time(14, 0), end_time=time(15, 0))],
        )

        plans = recommender.recommend_alternatives(
            student=student,
            completed_courses=[],
            all_available_courses=[section1, section2],
            desired_names=["자료구조"],
            free_days=["월"],
            max_plans=5,
        )

        assert len(plans) == 0, "모든 분반이 공강 요일에 있으면 빈 리스트를 반환해야 함"


# ------------------------------------------------------------------
# Property 2.4: recommend_alternatives() returns at most max_plans results
# Validates: Requirements 3.2
# ------------------------------------------------------------------

class TestRecommendAlternativesMaxPlans:
    """recommend_alternatives()가 max_plans 이하로 결과를 반환하는지 검증한다."""

    @given(max_plans=st.integers(min_value=1, max_value=5))
    @settings(max_examples=10)
    def test_result_count_within_max_plans(self, max_plans: int) -> None:
        """**Validates: Requirements 3.2**

        결과 수가 max_plans 이하이다.
        """
        recommender = _make_recommender()
        student = _make_student()

        # 과목 A: 1개 분반
        course_a = _make_course(
            "자료구조", course_id="DS001",
            time_slots=[TimeSlot(day="월", start_time=time(9, 0), end_time=time(10, 0))],
        )

        # 과목 B: 여러 분반 (서로 다른 시간대)
        sections_b = []
        for i, (day, start, end) in enumerate(_NON_OVERLAPPING_SLOTS):
            sections_b.append(_make_course(
                "알고리즘", course_id=f"ALGO{i}",
                time_slots=[TimeSlot(day=day, start_time=start, end_time=end)],
            ))

        # 과목 A의 월 9-10과 충돌하는 분반 제거
        sections_b_no_conflict = [
            s for s in sections_b
            if not any(
                sl.day == "월" and sl.start_time < time(10, 0) and sl.end_time > time(9, 0)
                for sl in s.time_slots
            )
        ]

        all_courses = [course_a] + sections_b_no_conflict

        plans = recommender.recommend_alternatives(
            student=student,
            completed_courses=[],
            all_available_courses=all_courses,
            desired_names=["자료구조", "알고리즘"],
            max_plans=max_plans,
        )

        assert len(plans) <= max_plans, (
            f"결과 수({len(plans)})가 max_plans({max_plans})를 초과함"
        )


# ------------------------------------------------------------------
# Property 2.5: ChatBot session resets on '취소' input
# Validates: Requirements 3.5
# ------------------------------------------------------------------

class TestChatBotSessionReset:
    """멀티턴 세션에서 '취소' 입력 시 세션이 리셋되는지 검증한다."""

    def _make_chatbot(self):
        """Create a ChatBot with mock dependencies."""
        from src.chatbot import ChatBot

        @dataclass
        class _MockRAGResponse:
            answer: str = "테스트 답변"
            sources: list = field(default_factory=list)
            has_evidence: bool = True

        class _MockRAG:
            def query(self, q, top_k=5):
                return _MockRAGResponse()

        parsed_data = ParsedData(
            schedule={"수강신청_일정": []},
            credit_rules={},
            cancel_rules={},
            prerequisites={},
            equivalent_courses={},
            curriculum_rules={},
        )

        return ChatBot(
            rag_pipeline=_MockRAG(),
            schedule_recommender=None,
            credit_validator=None,
            parsed_data=parsed_data,
        )

    def test_cancel_resets_session(self) -> None:
        """**Validates: Requirements 3.5**

        시간표 추천 세션 중 '취소' 입력 시 세션이 리셋되고 취소 메시지를 반환한다.
        """
        from src.chatbot import ScheduleSessionStep

        bot = self._make_chatbot()
        sid = "test_cancel"

        # 시간표 추천 시작
        bot.handle_input("시간표 추천해줘", session_id=sid)
        session = bot._get_session(sid)
        assert session.step != ScheduleSessionStep.IDLE, "세션이 시작되어야 함"

        # 취소 입력
        result = bot.handle_input("취소", session_id=sid)
        assert "취소" in result, "취소 메시지가 반환되어야 함"
        assert session.step == ScheduleSessionStep.IDLE, "세션이 IDLE로 리셋되어야 함"

    def test_cancel_after_grade_input(self) -> None:
        """**Validates: Requirements 3.5**

        학년 입력 후 '취소' 시에도 세션이 리셋된다.
        """
        from src.chatbot import ScheduleSessionStep

        bot = self._make_chatbot()
        sid = "test_cancel_after_grade"

        bot.handle_input("시간표 추천해줘", session_id=sid)
        bot.handle_input("3", session_id=sid)

        session = bot._get_session(sid)
        assert session.step == ScheduleSessionStep.ASK_DEPARTMENT

        result = bot.handle_input("취소", session_id=sid)
        assert "취소" in result
        assert session.step == ScheduleSessionStep.IDLE
        assert session.grade is None, "학년 정보가 리셋되어야 함"
