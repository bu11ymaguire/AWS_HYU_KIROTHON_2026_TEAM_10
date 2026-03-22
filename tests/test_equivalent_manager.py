"""동일/대치 교과목 관리기 테스트."""

from src.equivalent_manager import EquivalentManager
from src.models import EquivalentAdvice, EquivalentCourse


def _make_eq(old_name: str, new_name: str, relation: str) -> EquivalentCourse:
    return EquivalentCourse(
        old_course_id="OLD001",
        old_name=old_name,
        new_course_id="NEW001",
        new_name=new_name,
        relation_type=relation,
    )


class TestEquivalentManagerCheck:
    """EquivalentManager.check 메서드 테스트."""

    def test_identical_course_desired_is_new_name(self):
        """이수한 과목(old)의 동일 교과목(new)을 신청 → 재수강 안내."""
        eqs = [_make_eq("Basic Quantitative Methods", "데이터과학트렌드", "동일")]
        mgr = EquivalentManager(eqs)

        result = mgr.check("데이터과학트렌드", ["Basic Quantitative Methods"])

        assert result is not None
        assert result.relation_type == "동일"
        assert result.course_name == "데이터과학트렌드"
        assert result.related_course == "Basic Quantitative Methods"
        assert "재수강으로만 신청 가능" in result.message

    def test_identical_course_desired_is_old_name(self):
        """이수한 과목(new)의 동일 교과목(old)을 신청 → 재수강 안내."""
        eqs = [_make_eq("Basic Quantitative Methods", "데이터과학트렌드", "동일")]
        mgr = EquivalentManager(eqs)

        result = mgr.check("Basic Quantitative Methods", ["데이터과학트렌드"])

        assert result is not None
        assert result.relation_type == "동일"
        assert "재수강으로만 신청 가능" in result.message

    def test_substitute_course_desired_is_new_name(self):
        """이수한 과목(old)의 대치 교과목(new)을 신청 → 재수강/일반수강 안내."""
        eqs = [_make_eq("무대기술", "디자인실습1", "대치")]
        mgr = EquivalentManager(eqs)

        result = mgr.check("디자인실습1", ["무대기술"])

        assert result is not None
        assert result.relation_type == "대치"
        assert "재수강 또는 일반수강 선택 가능" in result.message

    def test_substitute_course_desired_is_old_name(self):
        """이수한 과목(new)의 대치 교과목(old)을 신청 → 재수강/일반수강 안내."""
        eqs = [_make_eq("무대기술", "디자인실습1", "대치")]
        mgr = EquivalentManager(eqs)

        result = mgr.check("무대기술", ["디자인실습1"])

        assert result is not None
        assert result.relation_type == "대치"
        assert "재수강 또는 일반수강 선택 가능" in result.message

    def test_no_relation_returns_none(self):
        """관계 없는 과목 → None 반환."""
        eqs = [_make_eq("무대기술", "디자인실습1", "대치")]
        mgr = EquivalentManager(eqs)

        result = mgr.check("알고리즘", ["자료구조"])

        assert result is None

    def test_desired_matches_but_completed_does_not(self):
        """desired가 매칭되지만 completed에 반대편이 없으면 None."""
        eqs = [_make_eq("무대기술", "디자인실습1", "대치")]
        mgr = EquivalentManager(eqs)

        result = mgr.check("디자인실습1", ["알고리즘"])

        assert result is None

    def test_empty_equivalents_returns_none(self):
        """빈 동일/대치 목록 → None."""
        mgr = EquivalentManager([])

        result = mgr.check("아무과목", ["다른과목"])

        assert result is None

    def test_empty_completed_courses_returns_none(self):
        """이수 과목이 비어있으면 None."""
        eqs = [_make_eq("무대기술", "디자인실습1", "대치")]
        mgr = EquivalentManager(eqs)

        result = mgr.check("디자인실습1", [])

        assert result is None

    def test_multiple_equivalents_first_match_wins(self):
        """여러 관계 중 첫 번째 매칭이 반환된다."""
        eqs = [
            _make_eq("과목A", "과목B", "동일"),
            _make_eq("과목A", "과목C", "대치"),
        ]
        mgr = EquivalentManager(eqs)

        result = mgr.check("과목A", ["과목B", "과목C"])

        assert result is not None
        assert result.relation_type == "동일"
        assert result.related_course == "과목B"
