"""폐강 판정기 모듈.

수강인원 기준에 따라 폐강 위험 여부를 판정한다.
별도기준 대상 과목은 항상 폐강 위험 없음으로 처리하며,
일반기준은 학과 재학인원 구간별로 적용한다.
"""

from __future__ import annotations

import math

from src.models import CancellationResult, Course, DepartmentInfo

# 별도기준 면제 대상 과목명 / 키워드
_SPECIAL_EXEMPT_NAMES = {
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
}

# 핵심교양 가상대학영역은 카테고리 기반으로 판별
_SPECIAL_EXEMPT_CATEGORY = "핵심교양_가상대학영역"


class CancellationChecker:
    """폐강 위험 여부 판정기."""

    def __init__(self, cancel_rules: dict) -> None:
        """cancel_rules JSON 딕셔너리를 로드한다."""
        self.cancel_rules = cancel_rules

    # ------------------------------------------------------------------
    # 별도기준 대상 여부 확인
    # ------------------------------------------------------------------
    def _is_special_exempt(self, course: Course) -> bool:
        """별도기준 대상 과목인지 확인한다.

        별도기준 대상:
          커리어개발Ⅰ/Ⅱ, 종합설계, 캡스톤디자인, 실용공학연구,
          사회봉사, 교직, 연구실현장실습, 실용연구심화,
          핵심교양_가상대학영역, ROTC
        """
        if course.name in _SPECIAL_EXEMPT_NAMES:
            return True
        # 과목명에 별도기준 키워드가 포함된 경우도 처리
        for name in _SPECIAL_EXEMPT_NAMES:
            if name in course.name:
                return True
        # 핵심교양 가상대학영역 카테고리
        if course.category == _SPECIAL_EXEMPT_CATEGORY:
            return True
        return False

    # ------------------------------------------------------------------
    # 일반기준 적용
    # ------------------------------------------------------------------
    def _apply_general_rule(
        self, course: Course, dept: DepartmentInfo
    ) -> CancellationResult:
        """재학인원 구간별 폐강 기준을 적용한다.

        우선순위:
        1. 영어전용/제2외국어전용/IC-PBL → 수강인원 8명 미만이면 폐강 위험
        2. 전공심화 스마트교과 → 수강인원 6명 미만이면 폐강 위험
        3. 재학인원 기반 일반 규칙:
           - 25명 이상 + 일반교과목/핵심교양 → 수강인원 10명 미만
           - 15~24명 + 일반교과목 → 수강인원 < 재학인원의 40%
           - 14명 이하 → 수강인원 6명 미만
        """
        enrollment = course.enrollment_count

        # 영어전용 / 제2외국어전용 / IC-PBL 별도 기준
        if course.is_english_only or course.is_ic_pbl:
            if enrollment < 8:
                return CancellationResult(
                    is_at_risk=True,
                    reason=f"수강인원 {enrollment}명 < 8명 (영어전용/제2외국어전용/IC-PBL 기준)",
                    applied_rule="일반기준",
                )
            return CancellationResult(
                is_at_risk=False,
                reason=f"수강인원 {enrollment}명 ≥ 8명",
                applied_rule="일반기준",
            )

        # 전공심화 스마트교과
        if course.is_smart and course.category == "전공심화":
            if enrollment < 6:
                return CancellationResult(
                    is_at_risk=True,
                    reason=f"수강인원 {enrollment}명 < 6명 (전공심화 스마트교과 기준)",
                    applied_rule="일반기준",
                )
            return CancellationResult(
                is_at_risk=False,
                reason=f"수강인원 {enrollment}명 ≥ 6명",
                applied_rule="일반기준",
            )

        # 학과 재학인원 기반 일반 규칙
        # 과목의 학년 정보가 없으므로, 전체 재학인원 합산 사용
        total_enrollment = sum(dept.enrollment_by_grade.values())

        if total_enrollment >= 25:
            # 일반교과목 또는 핵심교양
            if enrollment < 10:
                return CancellationResult(
                    is_at_risk=True,
                    reason=f"수강인원 {enrollment}명 < 10명 (재학인원 {total_enrollment}명 ≥ 25명 기준)",
                    applied_rule="일반기준",
                )
            return CancellationResult(
                is_at_risk=False,
                reason=f"수강인원 {enrollment}명 ≥ 10명",
                applied_rule="일반기준",
            )

        if 15 <= total_enrollment <= 24:
            threshold = math.ceil(total_enrollment * 0.4)
            if enrollment < threshold:
                return CancellationResult(
                    is_at_risk=True,
                    reason=(
                        f"수강인원 {enrollment}명 < 재학인원의 40% "
                        f"({threshold}명, 재학인원 {total_enrollment}명)"
                    ),
                    applied_rule="일반기준",
                )
            return CancellationResult(
                is_at_risk=False,
                reason=f"수강인원 {enrollment}명 ≥ 재학인원의 40% ({threshold}명)",
                applied_rule="일반기준",
            )

        # 재학인원 14명 이하
        if enrollment < 6:
            return CancellationResult(
                is_at_risk=True,
                reason=f"수강인원 {enrollment}명 < 6명 (재학인원 {total_enrollment}명 ≤ 14명 기준)",
                applied_rule="일반기준",
            )
        return CancellationResult(
            is_at_risk=False,
            reason=f"수강인원 {enrollment}명 ≥ 6명",
            applied_rule="일반기준",
        )

    # ------------------------------------------------------------------
    # 폐강 위험 판정 (메인 진입점)
    # ------------------------------------------------------------------
    def check(
        self, course: Course, department: DepartmentInfo
    ) -> CancellationResult:
        """폐강 위험 여부를 판정한다.

        별도기준 대상 과목은 항상 폐강 위험 없음(False)으로 처리하며,
        별도기준이 일반기준보다 우선 적용된다.
        """
        # 별도기준 우선 적용
        if self._is_special_exempt(course):
            return CancellationResult(
                is_at_risk=False,
                reason="별도기준 대상 과목 (폐강기준 없음)",
                applied_rule="별도기준",
            )

        # 일반기준 적용
        return self._apply_general_rule(course, department)
