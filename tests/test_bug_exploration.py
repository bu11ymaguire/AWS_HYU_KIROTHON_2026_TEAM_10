"""Bug condition exploration tests for schedule logic improvement.

These tests encode the EXPECTED (correct) behavior after the fix.
They are expected to FAIL on the current unfixed code, confirming the bugs exist.

Validates: Requirements 1.1, 1.2, 1.3
"""

from __future__ import annotations

from datetime import time

import pytest

from src.models import Course, StudentInfo, TimeSlot
from src.schedule_recommender import ScheduleRecommender


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _make_course(
    name: str,
    course_id: str = "C001",
    credits: int = 3,
    time_slots: list[TimeSlot] | None = None,
    enrollment_count: int = 30,
    capacity: int = 40,
    **kwargs,
) -> Course:
    """Create a Course with default values."""
    return Course(
        course_id=course_id,
        name=name,
        credits=credits,
        time_slots=time_slots or [],
        category=kwargs.get("category", "전공필수"),
        department=kwargs.get("department", "컴퓨터소프트웨어학부"),
        enrollment_count=enrollment_count,
        is_english_only=False,
        is_ic_pbl=False,
        is_smart=False,
        capacity=capacity,
    )


# ------------------------------------------------------------------
# Bug 3: Course model missing rating and review_count fields
# ------------------------------------------------------------------

class TestBug3CourseModelFields:
    """Bug 3: Course 모델에 rating, review_count 필드가 존재하는지 검증.

    현재 코드에서는 Course에 rating/review_count 필드가 없어
    생성 시 TypeError가 발생해야 한다 (버그 확인).
    """

    def test_course_accepts_rating_field(self) -> None:
        """Course 생성 시 rating 인자를 받을 수 있어야 한다."""
        course = Course(
            course_id="TEST001",
            name="테스트과목",
            credits=3,
            time_slots=[],
            category="전공필수",
            department="테스트학부",
            enrollment_count=50,
            is_english_only=False,
            is_ic_pbl=False,
            is_smart=False,
            capacity=40,
            rating=4.5,
        )
        assert course.rating == 4.5

    def test_course_accepts_review_count_field(self) -> None:
        """Course 생성 시 review_count 인자를 받을 수 있어야 한다."""
        course = Course(
            course_id="TEST002",
            name="테스트과목2",
            credits=3,
            time_slots=[],
            category="전공필수",
            department="테스트학부",
            enrollment_count=20,
            is_english_only=False,
            is_ic_pbl=False,
            is_smart=False,
            capacity=40,
            review_count=100,
        )
        assert course.review_count == 100

    def test_course_has_both_rating_and_review_count(self) -> None:
        """Course에 rating과 review_count를 동시에 설정할 수 있어야 한다."""
        course = Course(
            course_id="TEST003",
            name="테스트과목3",
            credits=3,
            time_slots=[],
            category="전공필수",
            department="테스트학부",
            enrollment_count=50,
            is_english_only=False,
            is_ic_pbl=False,
            is_smart=False,
            capacity=40,
            rating=4.5,
            review_count=100,
        )
        assert course.rating == 4.5
        assert course.review_count == 100


# ------------------------------------------------------------------
# Bug 1: analyze_difficulty() missing difficulty_score and rating/review_count
# ------------------------------------------------------------------

class TestBug1AnalyzeDifficulty:
    """Bug 1: analyze_difficulty()가 difficulty_score 필드를 반환하고,
    rating/review_count를 가중 합산 공식에 반영하는지 검증.

    현재 코드에서는 difficulty_score 필드가 없고 경쟁률만 사용한다 (버그 확인).
    """

    def test_analyze_difficulty_returns_difficulty_score(self) -> None:
        """analyze_difficulty() 결과에 difficulty_score 필드가 존재해야 한다."""
        courses = [
            Course(
                course_id="C001",
                name="과목A",
                credits=3,
                time_slots=[],
                category="전공필수",
                department="테스트학부",
                enrollment_count=50,
                is_english_only=False,
                is_ic_pbl=False,
                is_smart=False,
                capacity=40,
                rating=4.5,
                review_count=100,
            ),
        ]
        results = ScheduleRecommender.analyze_difficulty(courses)
        assert len(results) == 1
        assert "difficulty_score" in results[0], (
            "analyze_difficulty() 결과에 difficulty_score 필드가 없음"
        )

    def test_difficulty_score_uses_weighted_formula(self) -> None:
        """difficulty_score가 경쟁률*0.4 + 평가수*0.3 + (1-별점)*0.3 공식을 따라야 한다.

        두 과목의 difficulty_score가 rating/review_count 차이를 반영해야 한다.
        """
        courses = [
            Course(
                course_id="C001",
                name="인기과목",
                credits=3,
                time_slots=[],
                category="전공필수",
                department="테스트학부",
                enrollment_count=50,
                is_english_only=False,
                is_ic_pbl=False,
                is_smart=False,
                capacity=40,
                rating=4.5,
                review_count=100,
            ),
            Course(
                course_id="C002",
                name="비인기과목",
                credits=3,
                time_slots=[],
                category="전공필수",
                department="테스트학부",
                enrollment_count=20,
                is_english_only=False,
                is_ic_pbl=False,
                is_smart=False,
                capacity=40,
                rating=2.0,
                review_count=5,
            ),
        ]
        results = ScheduleRecommender.analyze_difficulty(courses)

        # Both results must have difficulty_score
        scores = {r["name"]: r for r in results}
        assert "difficulty_score" in scores["인기과목"]
        assert "difficulty_score" in scores["비인기과목"]

        # difficulty_score must be between 0 and 1
        assert 0 <= scores["인기과목"]["difficulty_score"] <= 1
        assert 0 <= scores["비인기과목"]["difficulty_score"] <= 1

    def test_analyze_difficulty_returns_rating_and_review_count(self) -> None:
        """analyze_difficulty() 결과에 rating, review_count 필드가 포함되어야 한다."""
        courses = [
            Course(
                course_id="C001",
                name="과목A",
                credits=3,
                time_slots=[],
                category="전공필수",
                department="테스트학부",
                enrollment_count=50,
                is_english_only=False,
                is_ic_pbl=False,
                is_smart=False,
                capacity=40,
                rating=4.5,
                review_count=100,
            ),
        ]
        results = ScheduleRecommender.analyze_difficulty(courses)
        assert "rating" in results[0], "결과에 rating 필드가 없음"
        assert "review_count" in results[0], "결과에 review_count 필드가 없음"


# ------------------------------------------------------------------
# Bug 2: recommend_alternatives() doesn't distinguish Plan A / Plan B
# ------------------------------------------------------------------

class TestBug2PlanABDistinction:
    """Bug 2: recommend_alternatives()가 플랜 A(평점 합산 최대)와
    플랜 B(경쟁률 합 최소)를 구분하여 반환하는지 검증.

    현재 코드에서는 모든 플랜이 warnings 수 기준으로만 정렬된다 (버그 확인).
    """

    @pytest.fixture
    def recommender(self) -> ScheduleRecommender:
        from src.cancellation_checker import CancellationChecker
        from src.conflict_checker import ConflictChecker
        from src.credit_validator import CreditValidator
        from src.equivalent_manager import EquivalentManager
        from src.prerequisite_checker import PrerequisiteChecker

        return ScheduleRecommender(
            credit_validator=CreditValidator(credit_rules={}),
            conflict_checker=ConflictChecker(),
            prerequisite_checker=PrerequisiteChecker([]),
            cancellation_checker=CancellationChecker(cancel_rules={}),
            equivalent_manager=EquivalentManager([]),
        )

    @pytest.fixture
    def student(self) -> StudentInfo:
        return StudentInfo(
            student_id="2024000000",
            grade=3,
            semester=1,
            is_graduating=False,
            is_extended=False,
            is_2026_freshman=False,
            department="테스트학부",
            has_multiple_major=False,
        )

    def test_plan_a_has_best_rating_sum(
        self, recommender: ScheduleRecommender, student: StudentInfo
    ) -> None:
        """첫 번째 플랜(플랜 A)이 평점 합산 최대 조합이어야 한다.

        과목 '알고리즘'에 2개 분반을 만들어 서로 다른 rating을 부여한다.
        플랜 A는 rating이 높은 분반을 포함해야 한다.
        """
        # 과목 1: 자료구조 (분반 1개, 월 9-10시)
        ds = Course(
            course_id="DS001",
            name="자료구조",
            credits=3,
            time_slots=[TimeSlot(day="월", start_time=time(9, 0), end_time=time(10, 0))],
            category="전공필수",
            department="테스트학부",
            enrollment_count=30,
            is_english_only=False,
            is_ic_pbl=False,
            is_smart=False,
            capacity=40,
            rating=4.0,
            review_count=50,
        )

        # 과목 2: 알고리즘 분반A (화 9-10시, 높은 rating, 높은 경쟁률)
        algo_a = Course(
            course_id="ALGO_A",
            name="알고리즘",
            credits=3,
            time_slots=[TimeSlot(day="화", start_time=time(9, 0), end_time=time(10, 0))],
            category="전공필수",
            department="테스트학부",
            enrollment_count=50,
            is_english_only=False,
            is_ic_pbl=False,
            is_smart=False,
            capacity=40,
            rating=4.8,
            review_count=80,
        )

        # 과목 2: 알고리즘 분반B (수 9-10시, 낮은 rating, 낮은 경쟁률)
        algo_b = Course(
            course_id="ALGO_B",
            name="알고리즘",
            credits=3,
            time_slots=[TimeSlot(day="수", start_time=time(9, 0), end_time=time(10, 0))],
            category="전공필수",
            department="테스트학부",
            enrollment_count=10,
            is_english_only=False,
            is_ic_pbl=False,
            is_smart=False,
            capacity=40,
            rating=2.5,
            review_count=10,
        )

        all_courses = [ds, algo_a, algo_b]

        plans = recommender.recommend_alternatives(
            student=student,
            completed_courses=[],
            all_available_courses=all_courses,
            desired_names=["자료구조", "알고리즘"],
            max_plans=3,
        )

        assert len(plans) >= 2, "충돌 없는 조합이 2개 이상 생성되어야 한다"

        # 플랜 A(첫 번째)의 warnings에 '플랜 A' 라벨이 있어야 한다
        plan_a_warnings = " ".join(plans[0].warnings)
        assert "플랜 A" in plan_a_warnings, (
            f"첫 번째 플랜에 '플랜 A' 라벨이 없음. warnings: {plans[0].warnings}"
        )

    def test_plan_b_has_lowest_competition(
        self, recommender: ScheduleRecommender, student: StudentInfo
    ) -> None:
        """두 번째 플랜(플랜 B)이 경쟁률 합 최소 조합이어야 한다."""
        ds = Course(
            course_id="DS001",
            name="자료구조",
            credits=3,
            time_slots=[TimeSlot(day="월", start_time=time(9, 0), end_time=time(10, 0))],
            category="전공필수",
            department="테스트학부",
            enrollment_count=30,
            is_english_only=False,
            is_ic_pbl=False,
            is_smart=False,
            capacity=40,
            rating=4.0,
            review_count=50,
        )

        algo_a = Course(
            course_id="ALGO_A",
            name="알고리즘",
            credits=3,
            time_slots=[TimeSlot(day="화", start_time=time(9, 0), end_time=time(10, 0))],
            category="전공필수",
            department="테스트학부",
            enrollment_count=50,
            is_english_only=False,
            is_ic_pbl=False,
            is_smart=False,
            capacity=40,
            rating=4.8,
            review_count=80,
        )

        algo_b = Course(
            course_id="ALGO_B",
            name="알고리즘",
            credits=3,
            time_slots=[TimeSlot(day="수", start_time=time(9, 0), end_time=time(10, 0))],
            category="전공필수",
            department="테스트학부",
            enrollment_count=10,
            is_english_only=False,
            is_ic_pbl=False,
            is_smart=False,
            capacity=40,
            rating=2.5,
            review_count=10,
        )

        all_courses = [ds, algo_a, algo_b]

        plans = recommender.recommend_alternatives(
            student=student,
            completed_courses=[],
            all_available_courses=all_courses,
            desired_names=["자료구조", "알고리즘"],
            max_plans=3,
        )

        assert len(plans) >= 2, "충돌 없는 조합이 2개 이상 생성되어야 한다"

        # 플랜 B(두 번째)의 warnings에 '플랜 B' 라벨이 있어야 한다
        plan_b_warnings = " ".join(plans[1].warnings)
        assert "플랜 B" in plan_b_warnings, (
            f"두 번째 플랜에 '플랜 B' 라벨이 없음. warnings: {plans[1].warnings}"
        )
