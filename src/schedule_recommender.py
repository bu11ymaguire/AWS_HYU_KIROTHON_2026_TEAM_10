"""시간표 추천기 모듈.

학점 검증, 시간 충돌 검증, 선수-후수 검증, 폐강 위험 판정, 동일/대치 교과목 확인을
통합 수행하여 추천 시간표를 생성한다.
공강 지정, 플랜 B/C 대안 시간표, 수강신청 난이도 분석을 지원한다.
"""

from __future__ import annotations

import itertools
from datetime import time

from src.cancellation_checker import CancellationChecker
from src.conflict_checker import ConflictChecker
from src.credit_validator import CreditValidator
from src.equivalent_manager import EquivalentManager
from src.models import (
    CancellationResult,
    ConflictResult,
    Course,
    CreditValidationResult,
    DepartmentInfo,
    ScheduleResult,
    StudentInfo,
)
from src.prerequisite_checker import PrerequisiteChecker

# 요일 목록 (월~금)
_DAYS = ["월", "화", "수", "목", "금"]

# 교시별 시간 매핑 (1교시~15교시)
_PERIOD_TIMES: list[tuple[time, time]] = [
    (time(9, 0), time(10, 0)),    # 1교시
    (time(10, 0), time(11, 0)),   # 2교시
    (time(11, 0), time(12, 0)),   # 3교시
    (time(12, 0), time(13, 0)),   # 4교시
    (time(13, 0), time(14, 0)),   # 5교시
    (time(14, 0), time(15, 0)),   # 6교시
    (time(15, 0), time(16, 0)),   # 7교시
    (time(16, 0), time(17, 0)),   # 8교시
    (time(17, 0), time(18, 0)),   # 9교시
    (time(18, 0), time(19, 0)),   # 10교시
    (time(19, 0), time(20, 0)),   # 11교시
    (time(20, 0), time(21, 0)),   # 12교시
    (time(21, 0), time(22, 0)),   # 13교시
    (time(22, 0), time(23, 0)),   # 14교시
    (time(23, 0), time(23, 59)),  # 15교시
]

_NUM_PERIODS = len(_PERIOD_TIMES)
_NUM_DAYS = len(_DAYS)


class ScheduleRecommender:
    """통합 검증 후 추천 시간표를 생성하는 클래스."""

    def __init__(
        self,
        credit_validator: CreditValidator,
        conflict_checker: ConflictChecker,
        prerequisite_checker: PrerequisiteChecker,
        cancellation_checker: CancellationChecker,
        equivalent_manager: EquivalentManager,
    ) -> None:
        self._credit_validator = credit_validator
        self._conflict_checker = conflict_checker
        self._prerequisite_checker = prerequisite_checker
        self._cancellation_checker = cancellation_checker
        self._equivalent_manager = equivalent_manager

    def recommend(
        self,
        student: StudentInfo,
        completed_courses: list[str],
        desired_courses: list[Course],
        english_grade: str | None = None,
        free_days: list[str] | None = None,
    ) -> ScheduleResult:
        """통합 검증 수행 후 추천 시간표를 생성한다.

        Args:
            free_days: 공강으로 지정할 요일 리스트 (예: ["월", "금"])
        """
        warnings: list[str] = []

        # 0. 공강 필터링
        if free_days:
            filtered: list[Course] = []
            for course in desired_courses:
                blocked = False
                for slot in course.time_slots:
                    if slot.day in free_days:
                        blocked = True
                        break
                if blocked:
                    warnings.append(
                        f"공강 충돌: '{course.name}'은(는) 공강 요일({', '.join(free_days)})에 수업이 있어 제외되었습니다."
                    )
                else:
                    filtered.append(course)
            desired_courses = filtered

        # 1. 학점 검증
        credit_info = self._credit_validator.validate(student, desired_courses)
        warnings.extend(credit_info.warnings)

        # 2. 시간 충돌 검증
        conflicts = self._conflict_checker.check_all_pairs(desired_courses)
        for course_a, course_b, slot in conflicts.conflicts:
            warnings.append(
                f"시간 충돌: '{course_a.name}'과(와) '{course_b.name}'이(가) "
                f"{slot.day} {slot.start_time.strftime('%H:%M')}~{slot.end_time.strftime('%H:%M')}에 겹칩니다."
            )

        # 3. 선수-후수 검증
        desired_names = [c.name for c in desired_courses]
        prereq_warnings = self._prerequisite_checker.check(
            desired_names, completed_courses, english_grade
        )
        prereq_missing_courses: set[str] = set()
        for pw in prereq_warnings:
            prereq_missing_courses.add(pw.course_name)
            warnings.append(f"선수과목 미이수 경고: {pw.message}")

        # 4. 폐강 위험 판정
        default_dept = DepartmentInfo(
            name=student.department,
            enrollment_by_grade={1: 50, 2: 50, 3: 50, 4: 50},
        )
        at_risk_courses: set[str] = set()
        for course in desired_courses:
            cancel_result: CancellationResult = self._cancellation_checker.check(
                course, default_dept
            )
            if cancel_result.is_at_risk:
                at_risk_courses.add(course.name)
                warnings.append(
                    f"폐강 위험: '{course.name}' — {cancel_result.reason}"
                )

        # 5. 동일/대치 교과목 확인
        for course in desired_courses:
            advice = self._equivalent_manager.check(course.name, completed_courses)
            if advice is not None:
                warnings.append(
                    f"동일/대치 교과목 안내: '{advice.course_name}' — {advice.message}"
                )

        # 6. 시간표 2D 배열 생성
        timetable = self._build_timetable(
            desired_courses, at_risk_courses, prereq_missing_courses
        )

        return ScheduleResult(
            timetable=timetable,
            warnings=warnings,
            credit_info=credit_info,
            conflicts=conflicts,
        )

    def check_drop_eligibility(
        self,
        student: StudentInfo,
        current_courses: list[Course],
        drop_courses: list[Course],
    ) -> dict:
        """수강포기 가능 여부를 검증한다.

        검증 규칙:
          1. 수강포기 후 잔여학점 >= 최소학점
          2. 최대 2과목까지만 포기 가능
          3. 학사학위취득유예자(is_extended=True)는 포기 불가
        """
        reasons: list[str] = []

        drop_names = {c.name for c in drop_courses}
        remaining_credits = sum(
            c.credits for c in current_courses if c.name not in drop_names
        )

        if student.is_extended:
            reasons.append("학사학위취득유예자는 수강포기가 불가합니다")

        if len(drop_courses) > 2:
            reasons.append(
                f"수강포기는 최대 2과목까지 가능합니다 (요청: {len(drop_courses)}과목)"
            )

        min_credits = self._credit_validator._calculate_min_credits(student)
        if remaining_credits < min_credits:
            reasons.append(
                f"수강포기 후 잔여학점({remaining_credits})이 "
                f"최소학점({min_credits}) 미만입니다"
            )

        return {
            "can_drop": len(reasons) == 0,
            "reasons": reasons,
            "remaining_credits": remaining_credits,
        }

    # ------------------------------------------------------------------
    # 시간표 2D 배열 생성
    # ------------------------------------------------------------------
    @staticmethod
    def _build_timetable(
        courses: list[Course],
        at_risk_courses: set[str],
        prereq_missing_courses: set[str],
    ) -> list[list[str]]:
        """요일(월~금) × 교시 2D 배열을 생성한다."""
        timetable: list[list[str]] = [
            ["" for _ in range(_NUM_DAYS)] for _ in range(_NUM_PERIODS)
        ]

        for course in courses:
            label = course.name
            if course.name in at_risk_courses:
                label += " [폐강 위험]"
            if course.name in prereq_missing_courses:
                label += " [선수과목 미이수]"

            for slot in course.time_slots:
                if slot.day not in _DAYS:
                    continue
                col = _DAYS.index(slot.day)

                for row, (period_start, period_end) in enumerate(_PERIOD_TIMES):
                    if slot.start_time < period_end and slot.end_time > period_start:
                        if timetable[row][col] == "":
                            timetable[row][col] = label
                        elif label not in timetable[row][col]:
                            timetable[row][col] += f" / {label}"

        return timetable

    # ------------------------------------------------------------------
    # 플랜 B/C: 대안 시간표 생성
    # ------------------------------------------------------------------
    def recommend_alternatives(
        self,
        student: StudentInfo,
        completed_courses: list[str],
        all_available_courses: list[Course],
        desired_names: list[str],
        free_days: list[str] | None = None,
        max_plans: int = 3,
    ) -> list[ScheduleResult]:
        """같은 과목의 다른 분반 조합으로 대안 시간표를 생성한다.

        Args:
            all_available_courses: 전체 개설 강의 목록
            desired_names: 희망 과목명 리스트
            free_days: 공강 요일
            max_plans: 최대 생성할 플랜 수

        Returns:
            충돌 없는 시간표 리스트 (최대 max_plans개)
        """
        # 과목명별 분반 그룹핑
        name_to_sections: dict[str, list[Course]] = {}
        for course in all_available_courses:
            if course.name in desired_names:
                if course.name not in name_to_sections:
                    name_to_sections[course.name] = []
                name_to_sections[course.name].append(course)

        # 공강 필터링
        if free_days:
            for name in name_to_sections:
                name_to_sections[name] = [
                    c for c in name_to_sections[name]
                    if not any(s.day in free_days for s in c.time_slots)
                ]

        # 찾을 수 없는 과목 처리
        found_names = [n for n in desired_names if name_to_sections.get(n)]
        missing_names = [n for n in desired_names if n not in found_names]

        if not found_names:
            return []

        # 분반 조합 생성 (과목별 분반 리스트의 카르테시안 곱)
        section_lists = [name_to_sections[n] for n in found_names]

        results: list[tuple[list[Course], ScheduleResult]] = []
        seen_combos: set[tuple[str, ...]] = set()

        for combo in itertools.product(*section_lists):
            combo_key = tuple(sorted(c.course_id + str(c.time_slots) for c in combo))
            if combo_key in seen_combos:
                continue
            seen_combos.add(combo_key)

            courses_list = list(combo)

            # 충돌 체크
            conflicts = self._conflict_checker.check_all_pairs(courses_list)
            if conflicts.has_conflict:
                continue

            result = self.recommend(
                student=student,
                completed_courses=completed_courses,
                desired_courses=courses_list,
                free_days=free_days,
            )

            # 충돌 없는 결과만 추가
            if not result.conflicts.has_conflict:
                results.append((courses_list, result))

        # 플랜 A/B 선별
        if not results:
            return []

        # 플랜 A: rating 합산 최대 (최적 조합)
        def _rating_sum(item: tuple[list[Course], ScheduleResult]) -> float:
            return sum(c.rating for c in item[0])

        # 플랜 B: 경쟁률 합 최소 (안전 조합)
        def _competition_sum(item: tuple[list[Course], ScheduleResult]) -> float:
            return sum(c.enrollment_count / max(c.capacity, 1) for c in item[0])

        best_rating = max(results, key=_rating_sum)
        lowest_competition = min(results, key=_competition_sum)

        plan_a = best_rating[1]
        plan_b = lowest_competition[1]

        # 플랜 라벨 추가
        plan_a.warnings.insert(0, "📌 플랜 A: 최적 조합 (평점 기준)")

        if best_rating is lowest_competition:
            # 동일 조합이면 플랜 A만 반환
            final_results = [plan_a]
        else:
            plan_b.warnings.insert(0, "📌 플랜 B: 안전 조합 (경쟁률 기준)")
            final_results = [plan_a, plan_b]

        # max_plans 제한 적용
        final_results = final_results[:max_plans]

        # 못 찾은 과목 경고 추가
        if missing_names:
            for r in final_results:
                r.warnings.insert(
                    0,
                    f"⚠️ 다음 과목은 개설 정보를 찾을 수 없습니다: {', '.join(missing_names)}"
                )

        return final_results

    # ------------------------------------------------------------------
    # 수강신청 난이도 분석
    # ------------------------------------------------------------------
    @staticmethod
    def analyze_difficulty(courses: list[Course]) -> list[dict]:
        """과목별 수강신청 난이도를 분석한다.

        경쟁률·평가수·별점의 가중 합산 공식으로 난이도를 산출한다.
        difficulty_score = ratio_norm * 0.4 + review_norm * 0.3 + (1 - rating_norm) * 0.3

        Returns:
            과목별 난이도 정보 리스트 (difficulty_score 높은 순 정렬)
        """
        # 1단계: 각 과목의 raw 값 계산
        raw_data: list[dict] = []
        for course in courses:
            enrolled = course.enrollment_count
            capacity = course.capacity
            if capacity > 0:
                ratio = enrolled / capacity
            else:
                ratio = enrolled / max(enrolled, 30)

            raw_data.append({
                "course": course,
                "enrolled": enrolled,
                "capacity": capacity,
                "ratio": ratio,
                "rating": course.rating,
                "review_count": course.review_count,
            })

        # 2단계: min-max 정규화
        if not raw_data:
            return []

        ratios = [d["ratio"] for d in raw_data]
        reviews = [d["review_count"] for d in raw_data]
        ratings = [d["rating"] for d in raw_data]

        ratio_min, ratio_max = min(ratios), max(ratios)
        review_min, review_max = min(reviews), max(reviews)
        rating_min, rating_max = min(ratings), max(ratings)

        def _normalize(value: float, min_val: float, max_val: float) -> float:
            if min_val == max_val:
                return 0.5
            return (value - min_val) / (max_val - min_val)

        # 3단계: 가중 합산 및 결과 생성
        results: list[dict] = []
        for d in raw_data:
            ratio_norm = _normalize(d["ratio"], ratio_min, ratio_max)
            review_norm = _normalize(d["review_count"], review_min, review_max)
            rating_norm = _normalize(d["rating"], rating_min, rating_max)

            difficulty_score = ratio_norm * 0.4 + review_norm * 0.3 + (1 - rating_norm) * 0.3

            if difficulty_score >= 0.75:
                level = "🔴 매우 높음"
                tip = "수강신청 시작 즉시 신청 필수, 새로고침 금지"
            elif difficulty_score >= 0.5:
                level = "🟠 높음"
                tip = "정원 초과 상태, 빠른 신청 권장"
            elif difficulty_score >= 0.3:
                level = "🟡 보통"
                tip = "여유 있지만 마감 가능성 있음"
            else:
                level = "🟢 낮음"
                tip = "여석 충분, 정정기간에도 가능"

            capacity = d["capacity"]
            results.append({
                "name": d["course"].name,
                "enrolled": d["enrolled"],
                "capacity": capacity if capacity > 0 else "정보없음",
                "ratio": round(d["ratio"], 2),
                "level": level,
                "tip": tip,
                "difficulty_score": round(difficulty_score, 4),
                "rating": d["rating"],
                "review_count": d["review_count"],
            })

        results.sort(key=lambda x: x["difficulty_score"], reverse=True)
        return results
