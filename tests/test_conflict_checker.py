"""시간표 충돌 검증기 단위 테스트."""

from datetime import time

import pytest

from src.conflict_checker import ConflictChecker
from src.models import Course, TimeSlot


def _make_course(
    course_id: str,
    name: str,
    time_slots: list[TimeSlot],
    credits: int = 3,
) -> Course:
    """테스트용 Course 헬퍼."""
    return Course(
        course_id=course_id,
        name=name,
        credits=credits,
        time_slots=time_slots,
        category="전공선택",
        department="컴퓨터소프트웨어학부",
        enrollment_count=30,
        is_english_only=False,
        is_ic_pbl=False,
        is_smart=False,
    )


class TestIsOverlapping:
    """_is_overlapping 메서드 테스트."""

    def test_same_day_overlapping(self):
        slot_a = TimeSlot(day="월", start_time=time(9, 0), end_time=time(10, 30))
        slot_b = TimeSlot(day="월", start_time=time(10, 0), end_time=time(11, 30))
        assert ConflictChecker._is_overlapping(slot_a, slot_b) is True

    def test_same_day_no_overlap(self):
        slot_a = TimeSlot(day="월", start_time=time(9, 0), end_time=time(10, 0))
        slot_b = TimeSlot(day="월", start_time=time(10, 0), end_time=time(11, 0))
        assert ConflictChecker._is_overlapping(slot_a, slot_b) is False

    def test_different_day_same_time(self):
        slot_a = TimeSlot(day="월", start_time=time(9, 0), end_time=time(10, 30))
        slot_b = TimeSlot(day="화", start_time=time(9, 0), end_time=time(10, 30))
        assert ConflictChecker._is_overlapping(slot_a, slot_b) is False

    def test_one_minute_overlap(self):
        slot_a = TimeSlot(day="수", start_time=time(9, 0), end_time=time(10, 1))
        slot_b = TimeSlot(day="수", start_time=time(10, 0), end_time=time(11, 0))
        assert ConflictChecker._is_overlapping(slot_a, slot_b) is True

    def test_contained_slot(self):
        slot_a = TimeSlot(day="목", start_time=time(9, 0), end_time=time(12, 0))
        slot_b = TimeSlot(day="목", start_time=time(10, 0), end_time=time(11, 0))
        assert ConflictChecker._is_overlapping(slot_a, slot_b) is True

    def test_adjacent_no_overlap(self):
        slot_a = TimeSlot(day="금", start_time=time(9, 0), end_time=time(10, 0))
        slot_b = TimeSlot(day="금", start_time=time(10, 0), end_time=time(11, 0))
        assert ConflictChecker._is_overlapping(slot_a, slot_b) is False


class TestCheckAllPairs:
    """check_all_pairs 메서드 테스트."""

    def test_no_conflict(self):
        checker = ConflictChecker()
        courses = [
            _make_course("C1", "과목A", [TimeSlot("월", time(9, 0), time(10, 30))]),
            _make_course("C2", "과목B", [TimeSlot("월", time(11, 0), time(12, 30))]),
        ]
        result = checker.check_all_pairs(courses)
        assert result.has_conflict is False
        assert len(result.conflicts) == 0

    def test_with_conflict(self):
        checker = ConflictChecker()
        courses = [
            _make_course("C1", "과목A", [TimeSlot("월", time(9, 0), time(10, 30))]),
            _make_course("C2", "과목B", [TimeSlot("월", time(10, 0), time(11, 30))]),
        ]
        result = checker.check_all_pairs(courses)
        assert result.has_conflict is True
        assert len(result.conflicts) == 1
        assert result.conflicts[0][0].course_id == "C1"
        assert result.conflicts[0][1].course_id == "C2"

    def test_empty_courses(self):
        checker = ConflictChecker()
        result = checker.check_all_pairs([])
        assert result.has_conflict is False
        assert len(result.conflicts) == 0

    def test_single_course(self):
        checker = ConflictChecker()
        courses = [
            _make_course("C1", "과목A", [TimeSlot("월", time(9, 0), time(10, 30))]),
        ]
        result = checker.check_all_pairs(courses)
        assert result.has_conflict is False

    def test_multiple_conflicts(self):
        checker = ConflictChecker()
        courses = [
            _make_course("C1", "과목A", [TimeSlot("월", time(9, 0), time(10, 30))]),
            _make_course("C2", "과목B", [TimeSlot("월", time(10, 0), time(11, 30))]),
            _make_course("C3", "과목C", [TimeSlot("월", time(10, 0), time(12, 0))]),
        ]
        result = checker.check_all_pairs(courses)
        assert result.has_conflict is True
        assert len(result.conflicts) >= 2


class TestFindConflictFreeCombinations:
    """find_conflict_free_combinations 메서드 테스트."""

    def test_all_compatible(self):
        checker = ConflictChecker()
        courses = [
            _make_course("C1", "과목A", [TimeSlot("월", time(9, 0), time(10, 0))]),
            _make_course("C2", "과목B", [TimeSlot("화", time(9, 0), time(10, 0))]),
            _make_course("C3", "과목C", [TimeSlot("수", time(9, 0), time(10, 0))]),
        ]
        combos = checker.find_conflict_free_combinations(courses)
        # 모든 3개 과목을 포함하는 조합이 존재해야 함
        full_combo = [c for c in combos if len(c) == 3]
        assert len(full_combo) == 1

    def test_two_conflicting(self):
        checker = ConflictChecker()
        courses = [
            _make_course("C1", "과목A", [TimeSlot("월", time(9, 0), time(10, 30))]),
            _make_course("C2", "과목B", [TimeSlot("월", time(10, 0), time(11, 30))]),
        ]
        combos = checker.find_conflict_free_combinations(courses)
        # 각 과목 단독 조합만 가능
        assert all(len(c) == 1 for c in combos)
        assert len(combos) == 2

    def test_empty_courses(self):
        checker = ConflictChecker()
        combos = checker.find_conflict_free_combinations([])
        assert combos == []

    def test_partial_conflicts(self):
        checker = ConflictChecker()
        courses = [
            _make_course("C1", "과목A", [TimeSlot("월", time(9, 0), time(10, 30))]),
            _make_course("C2", "과목B", [TimeSlot("월", time(10, 0), time(11, 30))]),
            _make_course("C3", "과목C", [TimeSlot("화", time(9, 0), time(10, 0))]),
        ]
        combos = checker.find_conflict_free_combinations(courses)
        # C1+C3, C2+C3 조합이 가능해야 함
        two_course_combos = [c for c in combos if len(c) == 2]
        assert len(two_course_combos) == 2


class TestSuggestMinimalRemoval:
    """suggest_minimal_removal 메서드 테스트."""

    def test_no_conflict_no_removal(self):
        checker = ConflictChecker()
        courses = [
            _make_course("C1", "과목A", [TimeSlot("월", time(9, 0), time(10, 0))]),
            _make_course("C2", "과목B", [TimeSlot("화", time(9, 0), time(10, 0))]),
        ]
        removed = checker.suggest_minimal_removal(courses)
        assert removed == []

    def test_one_removal_resolves(self):
        checker = ConflictChecker()
        courses = [
            _make_course("C1", "과목A", [TimeSlot("월", time(9, 0), time(10, 30))]),
            _make_course("C2", "과목B", [TimeSlot("월", time(10, 0), time(11, 30))]),
        ]
        removed = checker.suggest_minimal_removal(courses)
        assert len(removed) == 1

    def test_removes_most_conflicting(self):
        checker = ConflictChecker()
        # C2 conflicts with both C1 and C3
        courses = [
            _make_course("C1", "과목A", [TimeSlot("월", time(9, 0), time(10, 30))]),
            _make_course(
                "C2",
                "과목B",
                [
                    TimeSlot("월", time(10, 0), time(11, 30)),
                    TimeSlot("화", time(9, 0), time(10, 30)),
                ],
            ),
            _make_course("C3", "과목C", [TimeSlot("화", time(10, 0), time(11, 30))]),
        ]
        removed = checker.suggest_minimal_removal(courses)
        assert len(removed) == 1
        assert removed[0].course_id == "C2"

    def test_empty_courses(self):
        checker = ConflictChecker()
        removed = checker.suggest_minimal_removal([])
        assert removed == []
