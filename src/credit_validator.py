"""학점 검증기 모듈.

학년, 학기, 졸업예정 여부, 학업연장 여부, 2026 신입생 여부에 따른
수강신청 학점 상한/하한을 검증한다.
"""

from __future__ import annotations

from src.models import CreditValidationResult, Course, StudentInfo

# 추가학점 대상 과목명
_EXTRA_CREDIT_COURSES = {"커리어개발Ⅰ", "커리어개발Ⅱ", "사회봉사", "군사학"}
_EXTRA_CREDIT_MAX = 2

# 다전공 타전공 일반선택 추가학점 상한
_MULTI_MAJOR_EXTRA_MAX = 3


class CreditValidator:
    """학점 범위 검증기."""

    def __init__(self, credit_rules: dict) -> None:
        """credit_rules JSON 딕셔너리를 로드한다."""
        self.credit_rules = credit_rules

    # ------------------------------------------------------------------
    # 최소학점 계산
    # ------------------------------------------------------------------
    def _calculate_min_credits(self, student: StudentInfo) -> int:
        """학기별 최소학점을 반환한다.

        - 9학기 이상(학업연장재수강자): 1
        - 4-2 졸업예정: 3
        - 그 외(1-1 ~ 4-1): 10
        """
        if student.is_extended:
            return 1
        if student.grade == 4 and student.semester == 2 and student.is_graduating:
            return 3
        return 10

    # ------------------------------------------------------------------
    # 최대학점 계산
    # ------------------------------------------------------------------
    def _calculate_max_credits(
        self, student: StudentInfo, courses: list[Course]
    ) -> int:
        """기본 최대학점 + 추가학점을 계산한다.

        기본 최대학점:
          - 2026 신입생 3학년 이상(건축학부 제외): 18
          - 그 외: 20

        추가학점:
          - 커리어개발Ⅰ/Ⅱ, 사회봉사, 군사학: 해당 과목 학점 합산, 최대 2학점
          - 다전공자 타전공 일반선택: 해당 과목 학점 합산, 최대 3학점
        """
        # 기본 최대학점 결정
        base_max = self._get_base_max(student)

        # 추가학점 계산
        extra = self._calculate_extra_credits(student, courses)

        return base_max + extra

    def _get_base_max(self, student: StudentInfo) -> int:
        """기본 최대학점을 반환한다."""
        if student.is_2026_freshman and student.grade >= 3:
            if student.department != "건축학부":
                return 18
        return 20

    def _calculate_extra_credits(
        self, student: StudentInfo, courses: list[Course]
    ) -> int:
        """추가학점을 계산한다."""
        extra = 0

        # 커리어개발Ⅰ/Ⅱ, 사회봉사, 군사학 추가학점 (최대 2)
        extra_course_credits = sum(
            c.credits for c in courses if c.name in _EXTRA_CREDIT_COURSES
        )
        extra += min(extra_course_credits, _EXTRA_CREDIT_MAX)

        # 다전공자 타전공 일반선택 추가학점 (최대 3)
        if student.has_multiple_major:
            multi_major_credits = sum(
                c.credits
                for c in courses
                if c.category == "일반선택" and c.department != student.department
            )
            extra += min(multi_major_credits, _MULTI_MAJOR_EXTRA_MAX)

        return extra

    # ------------------------------------------------------------------
    # 검증
    # ------------------------------------------------------------------
    def validate(
        self, student: StudentInfo, courses: list[Course]
    ) -> CreditValidationResult:
        """총 학점이 허용 범위 내인지 검증하고 CreditValidationResult를 반환한다."""
        min_credits = self._calculate_min_credits(student)
        extra = self._calculate_extra_credits(student, courses)
        max_credits = self._calculate_max_credits(student, courses)

        current_credits = sum(c.credits for c in courses)

        warnings: list[str] = []
        is_valid = True

        if current_credits < min_credits or current_credits > max_credits:
            is_valid = False
            warnings.append(
                f"학점 범위 위반: 현재 {current_credits}학점 "
                f"(허용 범위: {min_credits}~{max_credits}학점)"
            )

        return CreditValidationResult(
            is_valid=is_valid,
            min_credits=min_credits,
            max_credits=max_credits,
            current_credits=current_credits,
            extra_credits=extra,
            warnings=warnings,
        )
