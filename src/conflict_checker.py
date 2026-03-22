"""시간표 충돌 검증기.

희망 과목 간 시간 충돌을 검사하고, 충돌 없는 조합을 탐색하며,
충돌 최소화를 위한 제외 과목을 안내한다.
"""

from __future__ import annotations

from itertools import combinations

from src.models import ConflictResult, Course, TimeSlot


class ConflictChecker:
    """시간표 충돌 검증기."""

    @staticmethod
    def _is_overlapping(slot_a: TimeSlot, slot_b: TimeSlot) -> bool:
        """두 시간대가 동일 요일에서 1분이라도 겹치는지 판정.

        겹침 조건: 같은 요일 AND start_a < end_b AND start_b < end_a
        """
        if slot_a.day != slot_b.day:
            return False
        return slot_a.start_time < slot_b.end_time and slot_b.start_time < slot_a.end_time

    def check_all_pairs(self, courses: list[Course]) -> ConflictResult:
        """모든 과목 쌍의 시간 충돌 검사.

        각 과목 쌍에 대해 모든 TimeSlot 조합을 비교하여
        충돌이 발생하는 쌍과 겹치는 시간대를 반환한다.
        """
        conflicts: list[tuple[Course, Course, TimeSlot]] = []

        for course_a, course_b in combinations(courses, 2):
            for slot_a in course_a.time_slots:
                for slot_b in course_b.time_slots:
                    if self._is_overlapping(slot_a, slot_b):
                        conflicts.append((course_a, course_b, slot_a))

        return ConflictResult(
            has_conflict=len(conflicts) > 0,
            conflicts=conflicts,
        )

    def find_conflict_free_combinations(
        self, courses: list[Course]
    ) -> list[list[Course]]:
        """백트래킹 기반 충돌 없는 과목 조합 탐색.

        모든 유효한 부분집합(충돌 없는 조합)을 찾아 반환한다.
        빈 조합은 제외하고, 최소 1개 이상의 과목을 포함하는 조합만 반환한다.
        """
        results: list[list[Course]] = []

        def _has_conflict_with_selected(
            candidate: Course, selected: list[Course]
        ) -> bool:
            for existing in selected:
                for slot_a in candidate.time_slots:
                    for slot_b in existing.time_slots:
                        if self._is_overlapping(slot_a, slot_b):
                            return True
            return False

        def _backtrack(index: int, current: list[Course]) -> None:
            if current:
                results.append(list(current))

            for i in range(index, len(courses)):
                if not _has_conflict_with_selected(courses[i], current):
                    current.append(courses[i])
                    _backtrack(i + 1, current)
                    current.pop()

        _backtrack(0, [])
        return results

    def suggest_minimal_removal(self, courses: list[Course]) -> list[Course]:
        """충돌 최소화를 위해 제외할 과목 목록을 반환.

        그리디 방식으로 가장 많은 충돌에 관여하는 과목을 우선 제거하여
        모든 충돌이 해소될 때까지 반복한다.
        """
        remaining = list(courses)
        removed: list[Course] = []

        while True:
            result = self.check_all_pairs(remaining)
            if not result.has_conflict:
                break

            # 각 과목의 충돌 횟수 집계
            conflict_count: dict[str, int] = {}
            for course in remaining:
                conflict_count[course.course_id] = 0

            for course_a, course_b, _ in result.conflicts:
                conflict_count[course_a.course_id] = (
                    conflict_count.get(course_a.course_id, 0) + 1
                )
                conflict_count[course_b.course_id] = (
                    conflict_count.get(course_b.course_id, 0) + 1
                )

            # 가장 많은 충돌에 관여하는 과목 제거
            worst_id = max(conflict_count, key=lambda cid: conflict_count[cid])
            worst_course = next(c for c in remaining if c.course_id == worst_id)
            remaining.remove(worst_course)
            removed.append(worst_course)

        return removed
