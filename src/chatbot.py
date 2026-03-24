"""의도 분류기 및 챗봇.

사용자 입력의 의도를 분류하고, 적절한 핸들러로 라우팅하는 모듈.
세션 기반 멀티턴 대화를 지원하여 시간표 추천 시 정보를 순차 수집한다.
"""

from __future__ import annotations

import re
import os
import sys
from enum import Enum
from dataclasses import dataclass, field

from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

from src.models import Course, ParsedData, StudentInfo


class Intent(Enum):
    """사용자 입력 의도 분류."""

    REGULATION_QA = "regulation_qa"
    SCHEDULE_RECOMMEND = "schedule"
    SCHEDULE_INFO = "schedule_info"
    CREDIT_CHECK = "credit_check"
    DROP_CHECK = "drop_check"
    RETAKE_INFO = "retake_info"
    FREE_DAY_SCHEDULE = "free_day_schedule"
    DIFFICULTY_CHECK = "difficulty_check"


# 의도별 키워드 매핑 (우선순위 순서대로 매칭)
_INTENT_KEYWORDS: list[tuple[Intent, list[str]]] = [
    (Intent.SCHEDULE_INFO, ["수강신청 일정", "신청 일정", "언제 신청", "수강신청 날짜"]),
    (Intent.FREE_DAY_SCHEDULE, ["공강", "꿀강", "빈 요일", "쉬는 날"]),
    (Intent.DIFFICULTY_CHECK, ["난이도", "경쟁률", "수강신청 난이도", "인기 과목", "마감"]),
    (Intent.SCHEDULE_RECOMMEND, ["시간표 추천", "시간표 짜", "시간표", "추천", "플랜"]),
    (Intent.CREDIT_CHECK, ["학점", "몇 학점", "최대 학점", "최소 학점"]),
    (Intent.DROP_CHECK, ["수강포기", "포기", "드롭"]),
    (Intent.RETAKE_INFO, ["재수강", "성적상승", "재수강 규칙"]),
]


_INTENT_CLASSIFY_PROMPT = """당신은 한양대학교 수강신청 도우미 챗봇의 의도 분류기입니다.
사용자 입력을 아래 의도 중 하나로 분류하세요.

의도 목록:
- schedule_info: 수강신청 일정, 날짜, 기간 문의 (예: "수강신청 언제야?", "신청 기간 알려줘")
- free_day_schedule: 공강/꿀강 지정 시간표 추천 (예: "금요일 비워줘", "공강 만들어줘", "꿀강 추천")
- difficulty_check: 수강신청 난이도/경쟁률 분석 (예: "이 과목 경쟁 심해?", "마감 빠른 과목", "인기 과목")
- schedule: 시간표 추천/생성 (예: "시간표 짜줘", "추천해줘", "플랜 B", "다른 조합")
- credit_check: 학점 관련 문의 (예: "최대 몇 학점?", "학점 제한")
- drop_check: 수강포기 관련 (예: "수강포기 하고 싶어", "드롭 가능?")
- retake_info: 재수강 관련 (예: "재수강 규칙", "성적 올리려면")
- regulation_qa: 위에 해당하지 않는 학사 규정/일반 질문

반드시 위 의도 이름 중 하나만 출력하세요. 다른 텍스트는 출력하지 마세요.

사용자 입력: {user_input}
의도:"""

# 의도 문자열 → Intent enum 매핑
_INTENT_NAME_MAP: dict[str, Intent] = {
    "regulation_qa": Intent.REGULATION_QA,
    "schedule": Intent.SCHEDULE_RECOMMEND,
    "schedule_info": Intent.SCHEDULE_INFO,
    "credit_check": Intent.CREDIT_CHECK,
    "drop_check": Intent.DROP_CHECK,
    "retake_info": Intent.RETAKE_INFO,
    "free_day_schedule": Intent.FREE_DAY_SCHEDULE,
    "difficulty_check": Intent.DIFFICULTY_CHECK,
}


class IntentRouter:
    """LLM 기반 의도 분류기. Gemini로 1차 분류, 실패 시 키워드 폴백."""

    def __init__(self) -> None:
        self._llm = None

    def _get_llm(self):
        """Gemini LLM 인스턴스를 lazy-init한다."""
        if self._llm is None:
            try:
                from langchain_google_genai import ChatGoogleGenerativeAI
                self._llm = ChatGoogleGenerativeAI(
                    model="gemini-2.5-flash",
                    temperature=0,
                    google_api_key=os.environ.get("GOOGLE_API_KEY", ""),
                )
            except Exception:
                self._llm = None
        return self._llm

    def classify(self, user_input: str) -> Intent:
        """사용자 입력 의도를 분류한다. LLM 우선, 실패 시 키워드 폴백."""
        text = user_input.strip()
        if not text:
            return Intent.REGULATION_QA

        # 1차: LLM 분류
        llm = self._get_llm()
        if llm is not None:
            try:
                result = llm.invoke(_INTENT_CLASSIFY_PROMPT.format(user_input=text))
                intent_name = result.content.strip().lower()
                # 여러 줄이 오면 첫 줄만
                intent_name = intent_name.split("\n")[0].strip()
                if intent_name in _INTENT_NAME_MAP:
                    return _INTENT_NAME_MAP[intent_name]
            except Exception:
                pass  # LLM 실패 시 키워드 폴백

        # 2차: 키워드 폴백
        return self._keyword_fallback(text)

    @staticmethod
    def _keyword_fallback(text: str) -> Intent:
        """키워드 매칭 폴백 분류."""
        for intent, keywords in _INTENT_KEYWORDS:
            sorted_keywords = sorted(keywords, key=len, reverse=True)
            for keyword in sorted_keywords:
                if keyword in text:
                    return intent
        return Intent.REGULATION_QA


# ── 시간표 추천 세션 상태 ──

class ScheduleSessionStep(Enum):
    """시간표 추천 대화 단계."""
    IDLE = "idle"
    ASK_GRADE = "ask_grade"
    ASK_DEPARTMENT = "ask_department"
    ASK_COMPLETED = "ask_completed"
    ASK_FREE_DAYS = "ask_free_days"
    ASK_DESIRED = "ask_desired"
    DONE = "done"


@dataclass
class ScheduleSession:
    """시간표 추천 멀티턴 세션 상태."""
    step: ScheduleSessionStep = ScheduleSessionStep.IDLE
    grade: int | None = None
    department: str | None = None
    completed_courses: list[str] = field(default_factory=list)
    desired_course_names: list[str] = field(default_factory=list)
    free_days: list[str] = field(default_factory=list)

    def reset(self) -> None:
        self.step = ScheduleSessionStep.IDLE
        self.grade = None
        self.department = None
        self.completed_courses = []
        self.desired_course_names = []
        self.free_days = []


# 학년별 수강신청 일정 매핑
_GRADE_SCHEDULE_MAP: dict[str, list[str]] = {
    "4": ["4,5학년"],
    "5": ["4,5학년"],
    "3": ["3학년"],
    "2": ["2학년"],
    "1": ["신·편입생"],
}


class ChatBot:
    """챗봇 메인 클래스.

    의도 분류 → 핸들러 라우팅 → 응답 생성을 수행한다.
    세션 기반 멀티턴 대화를 지원한다.
    """

    def __init__(
        self,
        rag_pipeline: object,
        schedule_recommender: object,
        credit_validator: object,
        parsed_data: ParsedData,
        available_courses: list[Course] | None = None,
    ) -> None:
        self._rag = rag_pipeline
        self._recommender = schedule_recommender
        self._credit_validator = credit_validator
        self._parsed_data = parsed_data
        self._router = IntentRouter()
        self._console = Console()
        self._available_courses: list[Course] = available_courses or []
        # 세션 관리: session_id → ScheduleSession
        self._sessions: dict[str, ScheduleSession] = {}

    def _get_session(self, session_id: str) -> ScheduleSession:
        """세션을 가져오거나 새로 생성한다."""
        if session_id not in self._sessions:
            self._sessions[session_id] = ScheduleSession()
        return self._sessions[session_id]

    def handle_input(self, user_input: str, session_id: str = "default") -> str:
        """사용자 입력을 처리하여 응답 문자열을 반환한다."""
        text = user_input.strip()
        if not text:
            return "질문을 입력해주세요."

        session = self._get_session(session_id)

        # 시간표 추천 세션이 진행 중이면 해당 세션 핸들러로 라우팅
        if session.step != ScheduleSessionStep.IDLE:
            # "취소" 또는 "처음으로" 입력 시 세션 리셋
            if text in ("취소", "처음으로", "다시"):
                session.reset()
                return "시간표 추천을 취소했습니다. 다른 질문이 있으시면 말씀해주세요."
            return self._handle_schedule_session(text, session)

        intent = self._router.classify(text)

        if intent == Intent.REGULATION_QA:
            return self._handle_regulation_qa(text)
        elif intent == Intent.SCHEDULE_RECOMMEND:
            return self._start_schedule_recommend(session)
        elif intent == Intent.FREE_DAY_SCHEDULE:
            return self._start_schedule_recommend(session, ask_free_days=True)
        elif intent == Intent.DIFFICULTY_CHECK:
            return self._handle_difficulty_check(text)
        elif intent == Intent.SCHEDULE_INFO:
            return self._handle_schedule_info(text)
        elif intent == Intent.CREDIT_CHECK:
            return self._handle_credit_check(text)
        elif intent == Intent.DROP_CHECK:
            return self._handle_drop_check()
        elif intent == Intent.RETAKE_INFO:
            return self._handle_retake_info()

        return self._handle_regulation_qa(text)

    def run(self) -> None:
        """CLI 메인 루프."""
        load_dotenv()

        self._console.print(
            "[bold green]한양대 서울캠퍼스 수강신청 도우미[/bold green] "
            "(종료: Ctrl+C)\n"
        )

        try:
            while True:
                user_input = input("질문> ")
                response = self.handle_input(user_input, session_id="cli")
                self._print_response(response)
        except KeyboardInterrupt:
            self._console.print("\n[bold yellow]챗봇을 종료합니다. 감사합니다![/bold yellow]")

    # ------------------------------------------------------------------
    # 시간표 추천 멀티턴 대화
    # ------------------------------------------------------------------

    def _start_schedule_recommend(self, session: ScheduleSession, ask_free_days: bool = False) -> str:
        """시간표 추천 세션을 시작한다."""
        session.reset()
        session.step = ScheduleSessionStep.ASK_GRADE
        session._ask_free_days = ask_free_days  # type: ignore[attr-defined]
        return (
            "📋 시간표 추천을 시작합니다!\n"
            "ℹ️ 졸업사정 분석 없이 시간표를 추천합니다.\n\n"
            "먼저 학년을 알려주세요. (1~5)\n"
            "(언제든 '취소'를 입력하면 추천을 중단합니다)"
        )

    def _handle_schedule_session(self, text: str, session: ScheduleSession) -> str:
        """시간표 추천 세션의 현재 단계에 따라 입력을 처리한다."""
        if session.step == ScheduleSessionStep.ASK_GRADE:
            return self._session_collect_grade(text, session)
        elif session.step == ScheduleSessionStep.ASK_DEPARTMENT:
            return self._session_collect_department(text, session)
        elif session.step == ScheduleSessionStep.ASK_COMPLETED:
            return self._session_collect_completed(text, session)
        elif session.step == ScheduleSessionStep.ASK_FREE_DAYS:
            return self._session_collect_free_days(text, session)
        elif session.step == ScheduleSessionStep.ASK_DESIRED:
            return self._session_collect_desired(text, session)
        else:
            session.reset()
            return "세션 오류가 발생했습니다. 다시 시도해주세요."

    def _session_collect_grade(self, text: str, session: ScheduleSession) -> str:
        """학년 수집."""
        match = re.search(r"([1-5])", text)
        if not match:
            return "학년을 1~5 사이의 숫자로 입력해주세요. (예: 3)"
        session.grade = int(match.group(1))
        session.step = ScheduleSessionStep.ASK_DEPARTMENT
        return f"✅ {session.grade}학년이시군요.\n\n학과(학부)를 입력해주세요. (예: 컴퓨터소프트웨어학부)"

    def _session_collect_department(self, text: str, session: ScheduleSession) -> str:
        """학과 수집. LLM으로 학과명을 정규화한다."""
        dept = text.strip()
        if len(dept) < 2:
            return "학과명을 정확히 입력해주세요. (예: 컴퓨터소프트웨어학부, 융합전자공학부)"

        # 사용 가능한 학과 목록 추출
        known_depts = sorted(set(c.department for c in self._available_courses)) if self._available_courses else []

        # LLM으로 학과명 정규화 시도
        resolved_dept = self._resolve_department(dept, known_depts)
        session.department = resolved_dept
        session.step = ScheduleSessionStep.ASK_COMPLETED
        return (
            f"✅ {session.department}\n\n"
            "이미 이수한 과목명을 쉼표(,)로 구분하여 입력해주세요.\n"
            "(없으면 '없음'이라고 입력해주세요)\n"
            "예: 자료구조, 운영체제, 기초학술영어"
        )

    def _resolve_department(self, user_input: str, known_depts: list[str]) -> str:
        """LLM으로 사용자 입력을 실제 학과명으로 매핑한다."""
        # 1차: 정확히 일치하면 바로 반환
        for d in known_depts:
            if user_input == d:
                return d

        # 2차: 부분 매칭
        for d in known_depts:
            if user_input in d or d in user_input:
                return d

        # 3차: LLM으로 fuzzy 매칭
        if not known_depts:
            return user_input

        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
            llm = ChatGoogleGenerativeAI(
                model="gemini-2.5-flash", temperature=0,
                google_api_key=os.environ.get("GOOGLE_API_KEY", ""),
            )
            dept_list = ", ".join(known_depts[:50])
            prompt = (
                f"사용자가 '{user_input}'이라고 입력했습니다. "
                f"아래 학과 목록에서 가장 일치하는 학과명을 하나만 출력하세요.\n"
                f"학과 목록: {dept_list}\n"
                f"일치하는 학과가 없으면 사용자 입력을 그대로 출력하세요.\n"
                f"학과명만 출력하세요."
            )
            result = llm.invoke(prompt)
            resolved = result.content.strip()
            # 결과가 실제 학과 목록에 있는지 확인
            for d in known_depts:
                if resolved == d or resolved in d or d in resolved:
                    return d
            return resolved if len(resolved) >= 2 else user_input
        except Exception:
            return user_input

    def _session_collect_completed(self, text: str, session: ScheduleSession) -> str:
        """이수 현황 수집. 짧은 입력은 LLM으로 의도를 확인한다."""
        stripped = text.strip()
        if stripped in ("없음", "없어", "없습니다", "x", "X", "없어요", "아직 없어", "없다"):
            session.completed_courses = []
        else:
            # 쉼표가 없고 짧은 입력이면 과목명인지 확인
            candidates = [c.strip() for c in text.split(",") if c.strip()]
            # 실제 과목명과 매칭 시도
            matched = []
            unmatched = []
            for name in candidates:
                found = any(name == c.name or name in c.name for c in self._available_courses)
                if found:
                    matched.append(name)
                else:
                    unmatched.append(name)
            session.completed_courses = candidates  # 일단 전부 저장

        # 공강 지정 모드면 공강 요일 질문
        if getattr(session, "_ask_free_days", False):
            session.step = ScheduleSessionStep.ASK_FREE_DAYS
            return (
                f"✅ 이수 과목 {len(session.completed_courses)}개 확인\n\n"
                "공강으로 지정할 요일을 입력해주세요.\n"
                "예: 월, 금  (쉼표로 구분)\n"
                "(공강 없이 진행하려면 '없음'을 입력해주세요)"
            )

        session.step = ScheduleSessionStep.ASK_DESIRED

        # 수강 가능한 과목 목록 안내
        available_msg = ""
        if self._available_courses:
            dept_courses = [
                c for c in self._available_courses
                if session.department and session.department in c.department
            ]
            if dept_courses:
                names = ", ".join(sorted(set(c.name for c in dept_courses))[:10])
                available_msg = f"\n\n📚 {session.department} 개설 과목 예시: {names}"
                if len(set(c.name for c in dept_courses)) > 10:
                    available_msg += f" 외 {len(set(c.name for c in dept_courses)) - 10}개"

        return (
            f"✅ 이수 과목 {len(session.completed_courses)}개 확인\n\n"
            "수강 희망 과목명을 쉼표(,)로 구분하여 입력해주세요.\n"
            "예: 집적회로소자, 전자회로1, 디지털신호처리1"
            + available_msg
        )

    def _session_collect_free_days(self, text: str, session: ScheduleSession) -> str:
        """공강 요일 수집."""
        _DAY_MAP = {"월": "월", "화": "화", "수": "수", "목": "목", "금": "금",
                     "월요일": "월", "화요일": "화", "수요일": "수", "목요일": "목", "금요일": "금"}
        if text.strip() in ("없음", "없어", "없습니다", "x", "X"):
            session.free_days = []
        else:
            days = []
            for part in re.split(r"[,\s]+", text):
                part = part.strip()
                if part in _DAY_MAP:
                    days.append(_DAY_MAP[part])
            session.free_days = days

        session.step = ScheduleSessionStep.ASK_DESIRED

        free_msg = ""
        if session.free_days:
            free_msg = f"✅ 공강 요일: {', '.join(session.free_days)}\n\n"
        else:
            free_msg = "✅ 공강 지정 없음\n\n"

        # 수강 가능한 과목 목록 안내
        available_msg = ""
        if self._available_courses:
            dept_courses = [
                c for c in self._available_courses
                if session.department and session.department in c.department
            ]
            if dept_courses:
                names = ", ".join(sorted(set(c.name for c in dept_courses))[:10])
                available_msg = f"\n\n📚 {session.department} 개설 과목 예시: {names}"

        return (
            free_msg
            + "수강 희망 과목명을 쉼표(,)로 구분하여 입력해주세요.\n"
            "예: 집적회로소자, 전자회로1, 디지털신호처리1"
            + available_msg
        )

    def _session_collect_desired(self, text: str, session: ScheduleSession) -> str:
        """희망 과목 수집 후 추천 실행 (플랜 A/B/C 포함)."""
        desired_names = [c.strip() for c in text.split(",") if c.strip()]
        if not desired_names:
            return "최소 1개 이상의 희망 과목을 입력해주세요."

        session.desired_course_names = desired_names

        # 희망 과목명으로 Course 객체 매칭 (fuzzy matching 포함)
        desired_courses: list[Course] = []
        not_found: list[str] = []

        dept_courses = [
            c for c in self._available_courses
            if session.department and session.department in c.department
        ] if self._available_courses else self._available_courses

        for name in desired_names:
            # 1차: 정확 매칭
            matched = [c for c in self._available_courses if c.name == name]
            if not matched:
                # 2차: 부분 매칭 (학과 내 우선)
                matched = [c for c in dept_courses if name in c.name]
            if not matched:
                # 3차: 전체 과목에서 부분 매칭
                matched = [c for c in self._available_courses if name in c.name]
            if matched:
                desired_courses.append(matched[0])
            else:
                not_found.append(name)

        # 못 찾은 과목이 있으면 LLM으로 매칭 시도
        if not_found and self._available_courses:
            resolved = self._resolve_course_names(not_found, dept_courses or self._available_courses)
            for original, resolved_course in resolved:
                not_found.remove(original)
                desired_courses.append(resolved_course)

        if not desired_courses:
            session.step = ScheduleSessionStep.ASK_DESIRED
            return (
                "입력하신 과목을 찾을 수 없습니다. "
                "정확한 과목명을 다시 입력해주세요.\n"
                "예: 집적회로소자, 전자회로1, 디지털신호처리1"
            )

        # StudentInfo 생성
        student = StudentInfo(
            student_id="2024000000",
            grade=session.grade or 3,
            semester=1,
            is_graduating=False,
            is_extended=False,
            is_2026_freshman=False,
            department=session.department or "",
            has_multiple_major=False,
        )

        free_days = session.free_days if session.free_days else None

        # 플랜 A/B/C 생성 시도
        try:
            plans = self._recommender.recommend_alternatives(
                student=student,
                completed_courses=session.completed_courses,
                all_available_courses=self._available_courses,
                desired_names=[c.name for c in desired_courses],
                free_days=free_days,
                max_plans=3,
            )
        except Exception:
            plans = []

        # 대안이 없으면 기본 추천 1개만
        if not plans:
            try:
                result = self._recommender.recommend(
                    student=student,
                    completed_courses=session.completed_courses,
                    desired_courses=desired_courses,
                    free_days=free_days,
                )
                plans = [result]
            except Exception:
                session.reset()
                return "시간표 추천 중 오류가 발생했습니다. 다시 시도해주세요."

        # 결과 포맷팅 (멀티 플랜)
        response = self._format_multi_plan_result(plans, not_found, free_days)
        session.reset()
        return response

    def _resolve_course_names(
        self, names: list[str], available: list[Course]
    ) -> list[tuple[str, Course]]:
        """LLM으로 과목명 fuzzy 매칭."""
        resolved: list[tuple[str, Course]] = []
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
            llm = ChatGoogleGenerativeAI(
                model="gemini-2.5-flash", temperature=0,
                google_api_key=os.environ.get("GOOGLE_API_KEY", ""),
            )
            course_list = ", ".join(sorted(set(c.name for c in available))[:60])
            for name in names:
                prompt = (
                    f"사용자가 '{name}'이라고 입력했습니다. "
                    f"아래 과목 목록에서 가장 일치하는 과목명을 하나만 출력하세요.\n"
                    f"과목 목록: {course_list}\n"
                    f"일치하는 과목이 없으면 'NONE'을 출력하세요.\n"
                    f"과목명만 출력하세요."
                )
                result = llm.invoke(prompt)
                matched_name = result.content.strip()
                if matched_name and matched_name != "NONE":
                    course = next((c for c in available if c.name == matched_name), None)
                    if course:
                        resolved.append((name, course))
        except Exception:
            pass
        return resolved

    def _format_schedule_result(
        self, result: object, courses: list[Course], not_found: list[str]
    ) -> str:
        """시간표 추천 결과를 텍스트로 포맷팅한다."""
        lines: list[str] = ["📅 시간표 추천 결과\n"]

        # 찾지 못한 과목 안내
        if not_found:
            lines.append(f"⚠️ 다음 과목은 찾을 수 없어 제외되었습니다: {', '.join(not_found)}\n")

        # 학점 정보
        ci = result.credit_info
        lines.append(f"📊 학점: {ci.current_credits}학점 (허용 범위: {ci.min_credits}~{ci.max_credits})")

        # 시간표 테이블 (마크다운)
        days = ["월", "화", "수", "목", "금"]
        lines.append("\n| 교시 | " + " | ".join(days) + " |")
        lines.append("|------|" + "|".join(["------"] * 5) + "|")

        for row_idx, row in enumerate(result.timetable):
            period = row_idx + 1
            start_h = 8 + row_idx
            cells = []
            for cell in row:
                cells.append(cell if cell else "")
            lines.append(f"| {period}({start_h}:00) | " + " | ".join(cells) + " |")

        # 경고 메시지
        if result.warnings:
            lines.append("\n⚠️ 주의사항:")
            for w in result.warnings:
                lines.append(f"  • {w}")

        lines.append("\n다른 시간표를 원하시면 '시간표 추천'을 다시 입력해주세요.")
        return "\n".join(lines)

    def _format_multi_plan_result(
        self, plans: list, not_found: list[str], free_days: list[str] | None
    ) -> str:
        """플랜 A/B/C 시간표 결과를 포맷팅한다."""
        plan_labels = ["A", "B", "C", "D", "E"]
        lines: list[str] = []

        if not_found:
            lines.append(f"⚠️ 다음 과목은 찾을 수 없어 제외되었습니다: {', '.join(not_found)}\n")

        if free_days:
            lines.append(f"🗓️ 공강 요일: {', '.join(free_days)}\n")

        for idx, plan in enumerate(plans):
            label = plan_labels[idx] if idx < len(plan_labels) else str(idx + 1)

            # warnings에서 플랜 라벨(📌)을 추출하여 제목에 사용
            plan_desc = ""
            display_warnings = []
            for w in plan.warnings:
                if w.startswith("📌"):
                    plan_desc = w.replace("📌 ", "")
                else:
                    display_warnings.append(w)

            if plan_desc:
                lines.append(f"## 📅 {plan_desc}\n")
            else:
                lines.append(f"## 📅 플랜 {label}\n")

            ci = plan.credit_info
            lines.append(f"📊 학점: {ci.current_credits}학점 (허용: {ci.min_credits}~{ci.max_credits})")

            days = ["월", "화", "수", "목", "금"]
            lines.append("\n| 교시 | " + " | ".join(days) + " |")
            lines.append("|------|" + "|".join(["------"] * 5) + "|")

            for row_idx, row in enumerate(plan.timetable):
                period = row_idx + 1
                start_h = 8 + row_idx
                cells = [cell if cell else "" for cell in row]
                lines.append(f"| {period}({start_h}:00) | " + " | ".join(cells) + " |")

            if display_warnings:
                lines.append("\n⚠️ 주의사항:")
                for w in display_warnings:
                    lines.append(f"  • {w}")

            lines.append("")  # 플랜 간 구분

        if len(plans) == 1:
            lines.append("ℹ️ 분반 조합이 1개뿐이라 대안 플랜을 생성할 수 없습니다.")

        lines.append("\n다른 시간표를 원하시면 '시간표 추천'을 다시 입력해주세요.")
        return "\n".join(lines)

    def _handle_difficulty_check(self, text: str) -> str:
        """수강신청 난이도 분석 핸들러."""
        from src.schedule_recommender import ScheduleRecommender

        # 텍스트에서 키워드를 먼저 제거한 뒤 과목명 추출
        keywords_to_remove = ["난이도", "경쟁률", "수강신청", "인기", "마감", "분석", "알려줘", "확인", "해줘", "해주세요", "좀", "과목"]
        cleaned = text
        for kw in keywords_to_remove:
            cleaned = cleaned.replace(kw, "")
        course_names = [c.strip() for c in re.split(r"[,，\s]+", cleaned) if len(c.strip()) >= 2]

        target_courses: list[Course] = []

        if course_names:
            # 특정 과목 난이도 분석
            for name in course_names:
                matched = [c for c in self._available_courses if name in c.name]
                target_courses.extend(matched)
        else:
            # 과목명 없으면 융합전자공학부 3학년 과목 기본 분석
            target_courses = [
                c for c in self._available_courses
                if "융합전자공학부" in c.department
            ]
            if not target_courses:
                # 전체 과목 중 경쟁률 높은 상위 10개
                target_courses = sorted(
                    [c for c in self._available_courses if c.capacity > 0],
                    key=lambda c: c.enrollment_count / max(c.capacity, 1),
                    reverse=True,
                )[:10]

        if not target_courses:
            return "분석할 과목을 찾을 수 없습니다. 과목명을 포함하여 다시 질문해주세요."

        results = ScheduleRecommender.analyze_difficulty(target_courses)

        lines = ["## 📊 수강신청 난이도 분석\n"]
        lines.append("| 과목명 | 수강인원 | 정원 | 경쟁률 | 평점 | 리뷰수 | 난이도 점수 | 난이도 | 팁 |")
        lines.append("|--------|----------|------|--------|------|--------|-------------|--------|-----|")
        for r in results:
            cap_str = str(r["capacity"]) if r["capacity"] != "정보없음" else "-"
            rating_str = f"{r['rating']:.1f}" if r["rating"] > 0 else "-"
            review_str = str(r["review_count"]) if r["review_count"] > 0 else "-"
            lines.append(
                f"| {r['name']} | {r['enrolled']} | {cap_str} | {r['ratio']} | {rating_str} | {review_str} | {r['difficulty_score']} | {r['level']} | {r['tip']} |"
            )

        lines.append("\n💡 난이도 점수가 높을수록 수강신청 경쟁이 치열합니다.")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # 기존 핸들러
    # ------------------------------------------------------------------

    def _handle_regulation_qa(self, question: str) -> str:
        """RAG 파이프라인을 사용하여 학사 규정 질문에 답변한다.
        RAG에서 근거를 찾지 못하면 LLM 직접 답변을 시도한다."""
        try:
            rag_response = self._rag.query(question)
            if rag_response.has_evidence:
                return rag_response.answer
            # RAG 근거 없으면 LLM 직접 답변 시도
            return self._llm_direct_answer(question)
        except Exception:
            return "일시적 오류가 발생했습니다. 잠시 후 다시 시도해주세요."

    def _llm_direct_answer(self, question: str) -> str:
        """RAG 근거가 없을 때 LLM으로 직접 답변한다."""
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
            from langchain_core.messages import HumanMessage, SystemMessage
            llm = ChatGoogleGenerativeAI(
                model="gemini-2.5-flash",
                temperature=0,
                google_api_key=os.environ.get("GOOGLE_API_KEY", ""),
            )
            messages = [
                SystemMessage(content=(
                    "당신은 한양대학교 서울캠퍼스 수강신청 도우미입니다. "
                    "학생의 질문에 친절하고 정확하게 답변하세요. "
                    "확실하지 않은 정보는 '정확한 정보는 학교 홈페이지를 확인해주세요'라고 안내하세요. "
                    "답변은 한국어로 작성하세요."
                )),
                HumanMessage(content=question),
            ]
            response = llm.invoke(messages)
            return response.content
        except Exception:
            return "해당 정보를 찾을 수 없습니다. 학교 홈페이지를 확인해주세요."

    def _handle_schedule_info(self, text: str) -> str:
        """학년별 수강신청 일정을 안내한다."""
        schedule = self._parsed_data.schedule
        registration = schedule.get("수강신청_일정", [])

        if not registration:
            return "수강신청 일정 정보를 찾을 수 없습니다."

        grade = self._extract_grade(text)
        if grade:
            return self._format_schedule_for_grade(grade, registration)
        return self._format_all_schedules(registration)

    def _handle_credit_check(self, question: str) -> str:
        """학점 관련 질문에 답변한다. (출처 페이지 표시 제거)"""
        try:
            rag_response = self._rag.query(question)
            return rag_response.answer
        except Exception:
            return "학점 정보 조회 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요."

    def _handle_drop_check(self) -> str:
        """수강포기 가능 여부 안내."""
        drop_info = self._parsed_data.schedule.get("수강포기_일정", {})
        lines = ["📋 수강포기 안내"]
        if drop_info:
            start = drop_info.get("시작", "미정")
            end = drop_info.get("종료", "미정")
            lines.append(f"• 기간: {start} ~ {end}")
            max_courses = drop_info.get("최대과목수", 2)
            lines.append(f"• 최대 포기 가능 과목 수: {max_courses}과목")
            condition = drop_info.get("조건", "")
            if condition:
                lines.append(f"• 조건: {condition}")
            restrictions = drop_info.get("제한", [])
            if restrictions:
                lines.append(f"• 포기 불가 대상: {', '.join(restrictions)}")
        else:
            lines.append("수강포기 일정 정보를 찾을 수 없습니다.")
        return "\n".join(lines)

    def _handle_retake_info(self) -> str:
        """성적상승재수강 규칙을 안내한다."""
        return (
            "📋 성적상승재수강 안내\n"
            "• 대상: C+ 이하 성적을 받은 교과목\n"
            "• 성적 제한: 재수강 시 최고 A0까지만 부여\n"
            "• 횟수 제한: 2025학번부터 과목당 최대 2회까지 재수강 가능\n"
            "• 기존 학번(2024학번 이전): 횟수 제한 없음"
        )

    # ------------------------------------------------------------------
    # 유틸리티
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_grade(text: str) -> str | None:
        """텍스트에서 학년 숫자를 추출한다."""
        match = re.search(r"(\d)\s*학년", text)
        if match:
            return match.group(1)
        match = re.search(r"\b([1-5])\b", text)
        if match:
            return match.group(1)
        return None

    def _format_schedule_for_grade(
        self, grade: str, registration: list[dict]
    ) -> str:
        """특정 학년의 수강신청 일정을 포맷팅한다."""
        target_labels = _GRADE_SCHEDULE_MAP.get(grade, [])
        target_labels = target_labels + ["전체학년(2~5)"]

        matched = [
            entry for entry in registration
            if any(label in entry.get("대상", "") for label in target_labels)
        ]

        if not matched:
            return f"{grade}학년 수강신청 일정 정보를 찾을 수 없습니다."

        lines = [f"📅 {grade}학년 수강신청 일정"]
        for entry in matched:
            target = entry.get("대상", "")
            date = entry.get("일자", "")
            day = entry.get("요일", "")
            start = entry.get("시작시간", "")
            end = entry.get("종료시간", "")
            note = entry.get("비고", "")
            line = f"• [{target}] {date}({day}) {start}~{end}"
            if note:
                line += f" — {note}"
            lines.append(line)
        return "\n".join(lines)

    def _format_all_schedules(self, registration: list[dict]) -> str:
        """전체 수강신청 일정을 포맷팅한다."""
        lines = ["📅 2026-1학기 수강신청 일정"]
        for entry in registration:
            target = entry.get("대상", "")
            date = entry.get("일자", "")
            day = entry.get("요일", "")
            start = entry.get("시작시간", "")
            end = entry.get("종료시간", "")
            note = entry.get("비고", "")
            line = f"• [{target}] {date}({day}) {start}~{end}"
            if note:
                line += f" — {note}"
            lines.append(line)
        return "\n".join(lines)

    def _print_response(self, response: str) -> None:
        """응답을 rich 테이블로 출력한다."""
        table = Table(show_header=True, header_style="bold cyan")
        table.add_column("응답", style="white", no_wrap=False)
        table.add_row(response)
        self._console.print(table)
        self._console.print()
