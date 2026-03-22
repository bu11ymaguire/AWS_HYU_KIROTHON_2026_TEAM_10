"""선수-후수 검증기 단위 테스트."""

from src.models import PrerequisiteRule, PrerequisiteWarning
from src.prerequisite_checker import PrerequisiteChecker


def _english_rules() -> list[PrerequisiteRule]:
    """기초학술영어 → 전문학술영어 규칙."""
    return [
        PrerequisiteRule(
            prerequisite="기초학술영어",
            subsequent="전문학술영어",
            exemption_grades=["A", "B"],
        ),
    ]


def _multi_rules() -> list[PrerequisiteRule]:
    """여러 선수-후수 규칙."""
    return [
        PrerequisiteRule(
            prerequisite="기초학술영어",
            subsequent="전문학술영어",
            exemption_grades=["A", "B"],
        ),
        PrerequisiteRule(
            prerequisite="미적분학1",
            subsequent="미적분학2",
            exemption_grades=[],
        ),
    ]


class TestPrerequisiteCheckerBasic:
    """기본 선수-후수 검증 테스트."""

    def test_no_warning_when_prerequisite_completed(self):
        checker = PrerequisiteChecker(_english_rules())
        warnings = checker.check(
            desired_courses=["전문학술영어"],
            completed_courses=["기초학술영어"],
        )
        assert warnings == []

    def test_warning_when_prerequisite_missing(self):
        checker = PrerequisiteChecker(_english_rules())
        warnings = checker.check(
            desired_courses=["전문학술영어"],
            completed_courses=[],
        )
        assert len(warnings) == 1
        assert warnings[0].course_name == "전문학술영어"
        assert warnings[0].missing_prerequisite == "기초학술영어"

    def test_no_warning_when_subsequent_not_desired(self):
        checker = PrerequisiteChecker(_english_rules())
        warnings = checker.check(
            desired_courses=["기초학술영어"],
            completed_courses=[],
        )
        assert warnings == []

    def test_empty_desired_courses(self):
        checker = PrerequisiteChecker(_english_rules())
        warnings = checker.check(
            desired_courses=[],
            completed_courses=[],
        )
        assert warnings == []

    def test_empty_rules(self):
        checker = PrerequisiteChecker([])
        warnings = checker.check(
            desired_courses=["전문학술영어"],
            completed_courses=[],
        )
        assert warnings == []

    def test_multiple_rules_multiple_warnings(self):
        checker = PrerequisiteChecker(_multi_rules())
        warnings = checker.check(
            desired_courses=["전문학술영어", "미적분학2"],
            completed_courses=[],
        )
        assert len(warnings) == 2
        names = {w.course_name for w in warnings}
        assert names == {"전문학술영어", "미적분학2"}

    def test_multiple_rules_partial_completion(self):
        checker = PrerequisiteChecker(_multi_rules())
        warnings = checker.check(
            desired_courses=["전문학술영어", "미적분학2"],
            completed_courses=["미적분학1"],
        )
        assert len(warnings) == 1
        assert warnings[0].course_name == "전문학술영어"


class TestEnglishGradeExemption:
    """영어기초학력평가 등급 면제 테스트."""

    def test_grade_a_exempts_both(self):
        """A등급: 기초학술영어 + 전문학술영어 선수과목 면제."""
        rules = [
            PrerequisiteRule(
                prerequisite="기초학술영어",
                subsequent="전문학술영어",
                exemption_grades=["A", "B"],
            ),
        ]
        checker = PrerequisiteChecker(rules)
        warnings = checker.check(
            desired_courses=["전문학술영어"],
            completed_courses=[],
            english_grade="A",
        )
        assert warnings == []

    def test_grade_b_exempts_basic_english(self):
        """B등급: 기초학술영어 선수과목 면제."""
        rules = [
            PrerequisiteRule(
                prerequisite="기초학술영어",
                subsequent="전문학술영어",
                exemption_grades=["A", "B"],
            ),
        ]
        checker = PrerequisiteChecker(rules)
        warnings = checker.check(
            desired_courses=["전문학술영어"],
            completed_courses=[],
            english_grade="B",
        )
        assert warnings == []

    def test_grade_c_no_exemption(self):
        """C등급: 면제 없음."""
        rules = [
            PrerequisiteRule(
                prerequisite="기초학술영어",
                subsequent="전문학술영어",
                exemption_grades=["A", "B"],
            ),
        ]
        checker = PrerequisiteChecker(rules)
        warnings = checker.check(
            desired_courses=["전문학술영어"],
            completed_courses=[],
            english_grade="C",
        )
        assert len(warnings) == 1
        assert warnings[0].missing_prerequisite == "기초학술영어"

    def test_no_english_grade_no_exemption(self):
        """등급 없음: 면제 없음."""
        checker = PrerequisiteChecker(_english_rules())
        warnings = checker.check(
            desired_courses=["전문학술영어"],
            completed_courses=[],
            english_grade=None,
        )
        assert len(warnings) == 1

    def test_english_grade_does_not_affect_non_english_rules(self):
        """영어 등급은 영어 외 규칙에 영향 없음."""
        rules = [
            PrerequisiteRule(
                prerequisite="미적분학1",
                subsequent="미적분학2",
                exemption_grades=[],
            ),
        ]
        checker = PrerequisiteChecker(rules)
        warnings = checker.check(
            desired_courses=["미적분학2"],
            completed_courses=[],
            english_grade="A",
        )
        assert len(warnings) == 1
        assert warnings[0].missing_prerequisite == "미적분학1"


class TestWarningMessage:
    """경고 메시지 형식 테스트."""

    def test_warning_contains_course_info(self):
        checker = PrerequisiteChecker(_english_rules())
        warnings = checker.check(
            desired_courses=["전문학술영어"],
            completed_courses=[],
        )
        w = warnings[0]
        assert "전문학술영어" in w.message
        assert "기초학술영어" in w.message
