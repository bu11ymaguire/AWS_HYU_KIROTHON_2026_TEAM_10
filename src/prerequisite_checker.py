"""선수-후수 교과목 검증기.

희망 과목 중 선수과목을 이수하지 않은 항목에 대해 경고를 생성한다.
영어기초학력평가 등급에 따른 면제 규칙을 처리한다.
"""

from __future__ import annotations

from src.models import PrerequisiteRule, PrerequisiteWarning


class PrerequisiteChecker:
    """선수-후수 교과목 관계를 검증하는 클래스."""

    def __init__(self, rules: list[PrerequisiteRule]) -> None:
        """선수-후수 규칙 리스트를 로드한다.

        Args:
            rules: PrerequisiteRule 객체 리스트
        """
        self.rules = rules

    def check(
        self,
        desired_courses: list[str],
        completed_courses: list[str],
        english_grade: str | None = None,
    ) -> list[PrerequisiteWarning]:
        """희망 과목에 대해 선수과목 미이수 경고를 반환한다.

        Args:
            desired_courses: 수강 희망 과목명 리스트
            completed_courses: 이수 완료 과목명 리스트
            english_grade: 영어기초학력평가 등급 ("A", "B", 또는 None)

        Returns:
            선수과목 미이수 경고 리스트
        """
        warnings: list[PrerequisiteWarning] = []

        for rule in self.rules:
            # 후수과목이 희망 과목에 포함되지 않으면 검사 불필요
            if rule.subsequent not in desired_courses:
                continue

            # 선수과목을 이미 이수했으면 경고 불필요
            if rule.prerequisite in completed_courses:
                continue

            # 영어기초학력평가 등급에 따른 면제 처리
            if self._is_exempt(rule, english_grade):
                continue

            warnings.append(
                PrerequisiteWarning(
                    course_name=rule.subsequent,
                    missing_prerequisite=rule.prerequisite,
                    message=(
                        f"'{rule.subsequent}' 수강을 위해 "
                        f"선수과목 '{rule.prerequisite}'을(를) 먼저 이수해야 합니다."
                    ),
                )
            )

        return warnings

    def _is_exempt(
        self, rule: PrerequisiteRule, english_grade: str | None
    ) -> bool:
        """영어기초학력평가 등급에 따른 면제 여부를 판정한다.

        면제 규칙:
        - A등급: 기초학술영어 + 전문학술영어 선수과목 면제
        - B등급: 기초학술영어 선수과목 면제만 해당

        Args:
            rule: 선수-후수 규칙
            english_grade: 영어기초학력평가 등급

        Returns:
            면제 여부
        """
        if english_grade is None:
            return False

        return english_grade in rule.exemption_grades
