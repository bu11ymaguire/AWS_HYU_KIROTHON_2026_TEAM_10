"""동일/대치 교과목 관리기.

이수한 과목과 수강신청하려는 과목 간의 동일/대치 관계를 확인하고 안내 메시지를 반환한다.
"""

from __future__ import annotations

from src.models import EquivalentAdvice, EquivalentCourse


class EquivalentManager:
    """동일/대치 교과목 관계를 관리하고 안내를 제공한다."""

    def __init__(self, equivalents: list[EquivalentCourse]) -> None:
        self._equivalents = equivalents

    def check(
        self, desired_course: str, completed_courses: list[str]
    ) -> EquivalentAdvice | None:
        """동일/대치 관계 확인 및 안내 메시지 반환.

        desired_course가 EquivalentCourse의 old_name 또는 new_name과 일치하고,
        반대편 이름이 completed_courses에 포함되어 있으면 해당 관계에 맞는 안내를 반환한다.

        Args:
            desired_course: 수강신청하려는 과목명.
            completed_courses: 이미 이수한 과목명 리스트.

        Returns:
            관계가 있으면 EquivalentAdvice, 없으면 None.
        """
        for eq in self._equivalents:
            related: str | None = None

            if desired_course == eq.new_name and eq.old_name in completed_courses:
                related = eq.old_name
            elif desired_course == eq.old_name and eq.new_name in completed_courses:
                related = eq.new_name

            if related is None:
                continue

            if eq.relation_type == "동일":
                return EquivalentAdvice(
                    course_name=desired_course,
                    related_course=related,
                    relation_type="동일",
                    message="동일 교과목이므로 재수강으로만 신청 가능",
                )
            elif eq.relation_type == "대치":
                return EquivalentAdvice(
                    course_name=desired_course,
                    related_course=related,
                    relation_type="대치",
                    message="대치 교과목이므로 재수강 또는 일반수강 선택 가능",
                )

        return None
