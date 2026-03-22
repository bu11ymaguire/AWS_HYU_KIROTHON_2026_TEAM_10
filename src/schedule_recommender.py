"""시간표 추천기 모듈.

학점 검증, 시간 충돌 검증, 선수-후수 검증, 폐강 위험 판정, 동일/대치 교과목 확인을
통합 수행하여 추천 시간표를 생성한다.
"""

from __future__ import annotations

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
    ) -> ScheduleResult:
        """통합 검증 수행 후 추천 시간표를 생성한다.

        검증 순서:
          1. 학점 검증
          2. 시간 충돌 검증
          3. 선수-후수 검증
          4. 폐강 위험 판정
          5. 동일/대치 교과목 확인
          6. 시간표 2D 배열 생성
          7. 경고 메시지 취합

        Args:
            student: 학생 정보
            completed_courses: 이수 완료 과목명 리스트
            desired_courses: 수강 희망 과목 리스트
            english_grade: 영어기초학력평가 등급 (A, B, 또는 None)

        Returns:
            ScheduleResult (timetable, warnings, credit_info, conflicts)
        """
        warnings: list[str] = []

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

        # 4. 폐강 위험 판정 — DepartmentInfo 기본값 사용
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

        # 6. 시간표 2D 배열 생성 (rows=교시, cols=요일)
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

        Args:
            student: 학생 정보
            current_courses: 현재 수강 중인 과목 리스트
            drop_courses: 포기하려는 과목 리스트

        Returns:
            {"can_drop": bool, "reasons": list[str], "remaining_credits": int}
        """
        reasons: list[str] = []

        # 잔여학점 계산
        drop_names = {c.name for c in drop_courses}
        remaining_credits = sum(
            c.credits for c in current_courses if c.name not in drop_names
        )

        # 규칙 3: 학사학위취득유예자 포기 불가
        if student.is_extended:
            reasons.append("학사학위취득유예자는 수강포기가 불가합니다")

        # 규칙 2: 최대 2과목 제한
        if len(drop_courses) > 2:
            reasons.append(
                f"수강포기는 최대 2과목까지 가능합니다 (요청: {len(drop_courses)}과목)"
            )

        # 규칙 1: 잔여학점 >= 최소학점
        min_credits = self._credit_validator._calculate_min_credits(student)
        if remaining_credits < min_credits:
            reasons.append(
                f"수강포기 후 잔여학점({remaining_credits})이 "
                f"최소학점({min_credits}) 미만입니다"
            )

        can_drop = len(reasons) == 0

        return {
            "can_drop": can_drop,
            "reasons": reasons,
            "remaining_credits": remaining_credits,
        }


    # ------------------------------------------------------------------
    # 수강포기 가능 여부 검증
    # ------------------------------------------------------------------
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

        Args:
            student: 학생 정보
            current_courses: 현재 수강 중인 과목 리스트
            drop_courses: 포기하려는 과목 리스트

        Returns:
            {"can_drop": bool, "reasons": list[str], "remaining_credits": int}
        """
        reasons: list[str] = []

        # 잔여학점 계산
        drop_names = {c.name for c in drop_courses}
        remaining_credits = sum(
            c.credits for c in current_courses if c.name not in drop_names
        )

        # 규칙 3: 학사학위취득유예자 포기 불가
        if student.is_extended:
            reasons.append("학사학위취득유예자는 수강포기가 불가합니다")

        # 규칙 2: 최대 2과목 제한
        if len(drop_courses) > 2:
            reasons.append(
                f"수강포기는 최대 2과목까지 가능합니다 (요청: {len(drop_courses)}과목)"
            )

        # 규칙 1: 잔여학점 >= 최소학점
        min_credits = self._credit_validator._calculate_min_credits(student)
        if remaining_credits < min_credits:
            reasons.append(
                f"수강포기 후 잔여학점({remaining_credits})이 "
                f"최소학점({min_credits}) 미만입니다"
            )

        can_drop = len(reasons) == 0

        return {
            "can_drop": can_drop,
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
        """요일(월~금) × 교시 2D 배열을 생성한다.

        각 셀에는 해당 시간에 배치된 과목명이 들어가며,
        폐강 위험 과목에는 "[폐강 위험]", 선수과목 미이수 과목에는
        "[선수과목 미이수]" 접미사가 추가된다.
        빈 셀은 빈 문자열("")이다.

        Returns:
            list[list[str]] — rows: 교시(0~14), cols: 요일(0~4, 월~금)
        """
        # 빈 시간표 초기화
        timetable: list[list[str]] = [
            ["" for _ in range(_NUM_DAYS)] for _ in range(_NUM_PERIODS)
        ]

        for course in courses:
            # 과목명에 경고 접미사 추가
            label = course.name
            if course.name in at_risk_courses:
                label += " [폐강 위험]"
            if course.name in prereq_missing_courses:
                label += " [선수과목 미이수]"

            for slot in course.time_slots:
                if slot.day not in _DAYS:
                    continue
                col = _DAYS.index(slot.day)

                # 해당 시간대가 겹치는 교시를 찾아 배치
                for row, (period_start, period_end) in enumerate(_PERIOD_TIMES):
                    if slot.start_time < period_end and slot.end_time > period_start:
                        if timetable[row][col] == "":
                            timetable[row][col] = label
                        elif label not in timetable[row][col]:
                            timetable[row][col] += f" / {label}"

        return timetable

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

        Args:
            student: 학생 정보
            current_courses: 현재 수강 중인 과목 리스트
            drop_courses: 포기하려는 과목 리스트

        Returns:
            {"can_drop": bool, "reasons": list[str], "remaining_credits": int}
        """
        reasons: list[str] = []

        # 잔여학점 계산
        drop_names = {c.name for c in drop_courses}
        remaining_credits = sum(
            c.credits for c in current_courses if c.name not in drop_names
        )

        # 규칙 3: 학사학위취득유예자 포기 불가
        if student.is_extended:
            reasons.append("학사학위취득유예자는 수강포기가 불가합니다")

        # 규칙 2: 최대 2과목 제한
        if len(drop_courses) > 2:
            reasons.append(
                f"수강포기는 최대 2과목까지 가능합니다 (요청: {len(drop_courses)}과목)"
            )

        # 규칙 1: 잔여학점 >= 최소학점
        min_credits = self._credit_validator._calculate_min_credits(student)
        if remaining_credits < min_credits:
            reasons.append(
                f"수강포기 후 잔여학점({remaining_credits})이 "
                f"최소학점({min_credits}) 미만입니다"
            )

        can_drop = len(reasons) == 0

        return {
            "can_drop": can_drop,
            "reasons": reasons,
            "remaining_credits": remaining_credits,
        }

