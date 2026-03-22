"""교육과정 적용 규칙 테스트."""

from __future__ import annotations

import pytest

from src.curriculum_advisor import CurriculumAdvisor
from src.models import StudentInfo


# 테스트용 교육과정 규칙
SAMPLE_RULES: dict = {
    "4년단위_적용원칙": {
        "2020-2023": {"입학년도": [2020, 2021, 2022, 2023]},
        "2024-2027": {"입학년도": [2024, 2025, 2026, 2027]},
    },
    "2026년_적용": {
        "1-3학년": "2024-2027",
        "4-5학년_건축학부": "2020-2023_전공",
    },
    "학적변동_규칙": "복학 등 학적변동 발생 시, 학적변동 이후 학년·학기에 해당하는 교육과정 적용",
}


def _make_student(
    student_id: str = "2024012345",
    grade: int = 1,
    semester: int = 1,
    department: str = "컴퓨터소프트웨어학부",
) -> StudentInfo:
    return StudentInfo(
        student_id=student_id,
        grade=grade,
        semester=semester,
        is_graduating=False,
        is_extended=False,
        is_2026_freshman=False,
        department=department,
        has_multiple_major=False,
    )


class TestGetCurriculum:
    """get_curriculum 메서드 테스트."""

    def setup_method(self) -> None:
        self.advisor = CurriculumAdvisor(SAMPLE_RULES)

    # --- 4년 단위 사이클 기본 테스트 ---

    def test_2020_admission_grade4(self) -> None:
        """2020 입학 4학년 비건축학부 → 2020-2023."""
        student = _make_student(student_id="2020012345", grade=4)
        assert self.advisor.get_curriculum(student) == "2020-2023"

    def test_2023_admission_grade4(self) -> None:
        """2023 입학 4학년 비건축학부 → 2020-2023."""
        student = _make_student(student_id="2023012345", grade=4)
        assert self.advisor.get_curriculum(student) == "2020-2023"

    def test_2024_admission_grade4(self) -> None:
        """2024 입학 4학년 비건축학부 → 2024-2027."""
        student = _make_student(student_id="2024012345", grade=4)
        assert self.advisor.get_curriculum(student) == "2024-2027"

    # --- 2026학년도 기준: 1~3학년 → 2024-2027 ---

    def test_grade1_uses_2024_2027(self) -> None:
        """1학년 → 2024-2027."""
        student = _make_student(grade=1)
        assert self.advisor.get_curriculum(student) == "2024-2027"

    def test_grade2_uses_2024_2027(self) -> None:
        """2학년 → 2024-2027."""
        student = _make_student(grade=2)
        assert self.advisor.get_curriculum(student) == "2024-2027"

    def test_grade3_uses_2024_2027(self) -> None:
        """3학년 → 2024-2027."""
        student = _make_student(grade=3)
        assert self.advisor.get_curriculum(student) == "2024-2027"

    # --- 2026학년도 기준: 4~5학년 건축학부 → 2020-2023 ---

    def test_grade4_architecture_uses_2020_2023(self) -> None:
        """4학년 건축학부 → 2020-2023."""
        student = _make_student(
            student_id="2022012345", grade=4, department="건축학부"
        )
        assert self.advisor.get_curriculum(student) == "2020-2023"

    def test_grade5_architecture_uses_2020_2023(self) -> None:
        """5학년 건축학부 → 2020-2023."""
        student = _make_student(
            student_id="2021012345", grade=5, department="건축학부"
        )
        assert self.advisor.get_curriculum(student) == "2020-2023"

    # --- 입학년도 추출 ---

    def test_admission_year_extraction(self) -> None:
        """학번 앞 4자리에서 입학년도 추출."""
        assert self.advisor._extract_admission_year("2024012345") == 2024
        assert self.advisor._extract_admission_year("2020999999") == 2020

    def test_invalid_student_id_short(self) -> None:
        """학번이 4자리 미만이면 ValueError."""
        with pytest.raises(ValueError, match="유효하지 않은 학번"):
            self.advisor._extract_admission_year("202")

    def test_invalid_student_id_non_numeric(self) -> None:
        """학번 앞 4자리가 숫자가 아니면 ValueError."""
        with pytest.raises(ValueError, match="유효하지 않은 학번"):
            self.advisor._extract_admission_year("ABCD12345")

    def test_unknown_cycle_raises(self) -> None:
        """알 수 없는 입학년도 사이클이면 ValueError."""
        student = _make_student(student_id="2019012345", grade=4)
        with pytest.raises(ValueError, match="해당하는 교육과정 사이클이 없습니다"):
            self.advisor.get_curriculum(student)


class TestGetCurriculumChanges:
    """get_curriculum_changes 메서드 테스트."""

    def setup_method(self) -> None:
        self.advisor = CurriculumAdvisor(SAMPLE_RULES)

    def test_no_history_returns_empty(self) -> None:
        """이력 없으면 빈 리스트."""
        student = _make_student()
        assert self.advisor.get_curriculum_changes(student, []) == []

    def test_leave_notice(self) -> None:
        """휴학 이력 → 안내 메시지 포함."""
        student = _make_student(student_id="2022012345", grade=3)
        history = [{"type": "휴학", "year": 2025, "semester": 1}]
        result = self.advisor.get_curriculum_changes(student, history)
        assert len(result) == 1
        assert "휴학" in result[0]
        assert "복학 시" in result[0]

    def test_return_with_curriculum_change(self) -> None:
        """복학 시 교육과정 변동 → 변경 안내."""
        # 2020 입학(원래 2020-2023), 복학 시 2학년 → 2024-2027로 변경
        student = _make_student(student_id="2020012345", grade=2)
        history = [
            {"type": "복학", "year": 2026, "semester": 1, "grade_at_change": 2}
        ]
        result = self.advisor.get_curriculum_changes(student, history)
        assert len(result) == 1
        assert "2020-2023" in result[0]
        assert "2024-2027" in result[0]

    def test_return_with_no_curriculum_change(self) -> None:
        """복학 시 교육과정 유지 → 유지 안내."""
        # 2024 입학, 복학 시 2학년 → 여전히 2024-2027
        student = _make_student(student_id="2024012345", grade=2)
        history = [
            {"type": "복학", "year": 2026, "semester": 1, "grade_at_change": 2}
        ]
        result = self.advisor.get_curriculum_changes(student, history)
        assert len(result) == 1
        assert "유지" in result[0]
        assert "2024-2027" in result[0]

    def test_return_grade4_architecture(self) -> None:
        """건축학부 4학년 복학 → 2020-2023 적용."""
        student = _make_student(
            student_id="2022012345", grade=4, department="건축학부"
        )
        history = [
            {"type": "복학", "year": 2026, "semester": 1, "grade_at_change": 4}
        ]
        result = self.advisor.get_curriculum_changes(student, history)
        assert len(result) == 1
        assert "2020-2023" in result[0]

    def test_multiple_history_entries(self) -> None:
        """여러 이력 항목 처리."""
        student = _make_student(student_id="2022012345", grade=3)
        history = [
            {"type": "휴학", "year": 2024, "semester": 2},
            {"type": "복학", "year": 2026, "semester": 1, "grade_at_change": 3},
        ]
        result = self.advisor.get_curriculum_changes(student, history)
        assert len(result) == 2
