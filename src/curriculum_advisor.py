"""교육과정 적용 규칙 모듈.

학번(입학년도)과 학년을 기반으로 적용 교육과정을 결정하고,
휴·복학 이력에 따른 교육과정 변동 사항을 안내한다.
"""

from __future__ import annotations

from src.models import StudentInfo


# 4년 단위 교육과정 사이클 정의
CURRICULUM_CYCLES: dict[str, range] = {
    "2020-2023": range(2020, 2024),
    "2024-2027": range(2024, 2028),
}


class CurriculumAdvisor:
    """교육과정 적용 규칙 판정기."""

    def __init__(self, curriculum_rules: dict) -> None:
        """교육과정 규칙을 로드한다.

        Args:
            curriculum_rules: 교육과정 적용 규칙 딕셔너리.
                예: {"4년단위_적용원칙": {...}, "2026년_적용": {...}, "학적변동_규칙": "..."}
        """
        self.curriculum_rules = curriculum_rules

    def _extract_admission_year(self, student_id: str) -> int:
        """학번에서 입학년도를 추출한다 (앞 4자리).

        Args:
            student_id: 학번 문자열 (예: "2024012345")

        Returns:
            입학년도 정수 (예: 2024)

        Raises:
            ValueError: 학번이 4자리 미만이거나 숫자가 아닌 경우
        """
        if len(student_id) < 4:
            raise ValueError(f"유효하지 않은 학번: {student_id}")
        try:
            return int(student_id[:4])
        except ValueError:
            raise ValueError(f"유효하지 않은 학번: {student_id}")

    def _get_cycle_for_year(self, admission_year: int) -> str | None:
        """입학년도에 해당하는 교육과정 사이클을 반환한다.

        Args:
            admission_year: 입학년도

        Returns:
            교육과정 사이클 문자열 (예: "2024-2027") 또는 None
        """
        for cycle_name, year_range in CURRICULUM_CYCLES.items():
            if admission_year in year_range:
                return cycle_name
        return None

    def get_curriculum(self, student: StudentInfo) -> str:
        """학번/학년 기반 적용 교육과정을 반환한다.

        4년 단위 교육과정 적용 원칙:
        - 2020-2023 입학 → "2020-2023"
        - 2024-2027 입학 → "2024-2027"

        2026학년도 기준 특례:
        - 1~3학년 → "2024-2027"
        - 4~5학년(건축학부) → "2020-2023" (전공 교육과정)

        Args:
            student: 학생 정보

        Returns:
            적용 교육과정 문자열 (예: "2024-2027")

        Raises:
            ValueError: 학번이 유효하지 않거나 해당하는 교육과정 사이클이 없는 경우
        """
        admission_year = self._extract_admission_year(student.student_id)

        # 2026학년도 기준 특례 적용
        if student.grade >= 4 and student.department == "건축학부":
            # 4~5학년 건축학부는 2020-2023 전공 교육과정 적용
            return "2020-2023"

        if student.grade <= 3:
            # 1~3학년은 2024-2027 교육과정 적용
            return "2024-2027"

        # 4학년 이상 비건축학부: 입학년도 기반 사이클 적용
        cycle = self._get_cycle_for_year(admission_year)
        if cycle is None:
            raise ValueError(
                f"해당하는 교육과정 사이클이 없습니다: 입학년도 {admission_year}"
            )
        return cycle

    def get_curriculum_changes(
        self, student: StudentInfo, leave_history: list[dict]
    ) -> list[str]:
        """휴·복학 이력에 따른 교육과정 변동 사항을 안내한다.

        학적변동 규칙: 복학 등 학적변동 발생 시,
        학적변동 이후 학년·학기에 해당하는 교육과정이 적용된다.

        Args:
            student: 학생 정보
            leave_history: 휴·복학 이력 리스트.
                각 항목은 {"type": "휴학"|"복학", "year": int, "semester": int,
                           "grade_at_change": int} 형태

        Returns:
            교육과정 변동 안내 메시지 리스트
        """
        if not leave_history:
            return []

        changes: list[str] = []
        admission_year = self._extract_admission_year(student.student_id)
        original_cycle = self._get_cycle_for_year(admission_year)

        for record in leave_history:
            record_type = record.get("type", "")
            year = record.get("year")
            semester = record.get("semester")
            grade_at_change = record.get("grade_at_change")

            if record_type == "복학" and grade_at_change is not None:
                # 복학 시점의 학년에 따라 적용 교육과정 결정
                if grade_at_change <= 3:
                    new_cycle = "2024-2027"
                elif student.department == "건축학부":
                    new_cycle = "2020-2023"
                else:
                    new_cycle = self._get_cycle_for_year(admission_year)
                    if new_cycle is None:
                        new_cycle = "알 수 없음"

                if new_cycle != original_cycle:
                    changes.append(
                        f"{year}년 {semester}학기 복학 시 "
                        f"{grade_at_change}학년 교육과정 적용: "
                        f"{original_cycle} → {new_cycle}"
                    )
                else:
                    changes.append(
                        f"{year}년 {semester}학기 복학 시 "
                        f"{grade_at_change}학년 교육과정 유지: {new_cycle}"
                    )

            elif record_type == "휴학":
                changes.append(
                    f"{year}년 {semester}학기 휴학: "
                    f"복학 시 해당 학년·학기의 교육과정이 적용됩니다"
                )

        return changes
