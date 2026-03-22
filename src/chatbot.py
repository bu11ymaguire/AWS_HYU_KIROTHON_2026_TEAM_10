"""의도 분류기 및 CLI 챗봇.

사용자 입력의 의도를 분류하고, 적절한 핸들러로 라우팅하는 모듈.
"""

from __future__ import annotations

from enum import Enum


class Intent(Enum):
    """사용자 입력 의도 분류."""

    REGULATION_QA = "regulation_qa"       # 학사 규정 질문
    SCHEDULE_RECOMMEND = "schedule"       # 시간표 추천
    SCHEDULE_INFO = "schedule_info"       # 수강신청 일정 조회
    CREDIT_CHECK = "credit_check"        # 학점 확인
    DROP_CHECK = "drop_check"            # 수강포기 가능 여부
    RETAKE_INFO = "retake_info"          # 성적상승재수강 안내


# 의도별 키워드 매핑 (우선순위 순서대로 매칭)
_INTENT_KEYWORDS: list[tuple[Intent, list[str]]] = [
    (Intent.SCHEDULE_INFO, ["수강신청 일정", "신청 일정", "언제 신청", "수강신청 날짜"]),
    (Intent.SCHEDULE_RECOMMEND, ["시간표 추천", "시간표 짜", "시간표", "추천"]),
    (Intent.CREDIT_CHECK, ["학점", "몇 학점", "최대 학점", "최소 학점"]),
    (Intent.DROP_CHECK, ["수강포기", "포기", "드롭"]),
    (Intent.RETAKE_INFO, ["재수강", "성적상승", "재수강 규칙"]),
]


class IntentRouter:
    """사용자 입력의 의도를 키워드 매칭으로 분류."""

    def classify(self, user_input: str) -> Intent:
        """사용자 입력 의도를 분류한다.

        키워드 매칭을 사용하며, 더 긴(구체적인) 키워드를 우선 매칭한다.
        어떤 키워드에도 매칭되지 않으면 REGULATION_QA(RAG Q&A)로 폴백한다.

        Args:
            user_input: 사용자 입력 문자열.

        Returns:
            분류된 Intent.
        """
        text = user_input.strip()
        if not text:
            return Intent.REGULATION_QA

        for intent, keywords in _INTENT_KEYWORDS:
            # 긴 키워드부터 매칭 (더 구체적인 키워드 우선)
            sorted_keywords = sorted(keywords, key=len, reverse=True)
            for keyword in sorted_keywords:
                if keyword in text:
                    return intent

        return Intent.REGULATION_QA


import os
import re
import sys

from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

from src.models import ParsedData


# 학년별 수강신청 일정 매핑 (grade → list of schedule entries)
_GRADE_SCHEDULE_MAP: dict[str, list[str]] = {
    "4": ["4,5학년"],
    "5": ["4,5학년"],
    "3": ["3학년"],
    "2": ["2학년"],
    "1": ["신·편입생"],
}


class ChatBot:
    """CLI 챗봇 메인 클래스.

    의도 분류 → 핸들러 라우팅 → 응답 생성을 수행한다.
    """

    def __init__(
        self,
        rag_pipeline: object,
        schedule_recommender: object,
        credit_validator: object,
        parsed_data: ParsedData,
    ) -> None:
        self._rag = rag_pipeline
        self._recommender = schedule_recommender
        self._credit_validator = credit_validator
        self._parsed_data = parsed_data
        self._router = IntentRouter()
        self._console = Console()

    def handle_input(self, user_input: str) -> str:
        """사용자 입력을 처리하여 응답 문자열을 반환한다."""
        text = user_input.strip()
        if not text:
            return "질문을 입력해주세요"

        intent = self._router.classify(text)

        if intent == Intent.REGULATION_QA:
            return self._handle_regulation_qa(text)
        elif intent == Intent.SCHEDULE_RECOMMEND:
            return self._handle_schedule_recommend()
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

        api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            self._console.print(
                "[bold red]OPENAI_API_KEY가 설정되지 않았습니다. "
                ".env 파일에 OPENAI_API_KEY를 설정해주세요.[/bold red]"
            )
            sys.exit(1)

        self._console.print(
            "[bold green]한양대 서울캠퍼스 수강신청 도우미[/bold green] "
            "(종료: Ctrl+C)\n"
        )

        try:
            while True:
                user_input = input("질문> ")
                response = self.handle_input(user_input)
                self._print_response(response)
        except KeyboardInterrupt:
            self._console.print("\n[bold yellow]챗봇을 종료합니다. 감사합니다![/bold yellow]")

    # ------------------------------------------------------------------
    # 핸들러
    # ------------------------------------------------------------------

    def _handle_regulation_qa(self, question: str) -> str:
        """RAG 파이프라인을 사용하여 학사 규정 질문에 답변한다."""
        try:
            rag_response = self._rag.query(question)
        except Exception:
            return "일시적 오류가 발생했습니다. 다시 시도해주세요."

        answer = rag_response.answer
        if rag_response.sources:
            page_numbers = sorted({s.page_number for s in rag_response.sources})
            pages_str = ", ".join(str(p) for p in page_numbers)
            answer += f"\n\n📄 출처: 페이지 {pages_str}"

        return answer

    def _handle_schedule_recommend(self) -> str:
        """시간표 추천을 위한 정보를 순차 수집하고 추천 결과를 반환한다.

        CLI run() 루프에서 호출될 때는 input()으로 정보를 수집하지만,
        handle_input()에서 직접 호출될 때는 안내 메시지만 반환한다.
        """
        return (
            "시간표 추천을 위해 다음 정보가 필요합니다:\n"
            "1. 학번 (예: 2024012345)\n"
            "2. 학년 (1~5)\n"
            "3. 학과\n"
            "4. 이수 현황 (이수한 과목명, 쉼표 구분)\n"
            "5. 희망 과목 (과목명, 쉼표 구분)\n\n"
            "위 정보를 순서대로 입력해주세요."
        )

    def _handle_schedule_info(self, text: str) -> str:
        """학년별 수강신청 일정을 안내한다."""
        schedule = self._parsed_data.schedule
        registration = schedule.get("수강신청_일정", [])

        if not registration:
            return "수강신청 일정 정보를 찾을 수 없습니다."

        # 텍스트에서 학년 추출 시도
        grade = self._extract_grade(text)

        if grade:
            return self._format_schedule_for_grade(grade, registration)

        # 학년 미지정 시 전체 일정 반환
        return self._format_all_schedules(registration)

    def _handle_credit_check(self, question: str) -> str:
        """학점 관련 질문에 답변한다."""
        try:
            rag_response = self._rag.query(question)
            answer = rag_response.answer
            if rag_response.sources:
                page_numbers = sorted({s.page_number for s in rag_response.sources})
                pages_str = ", ".join(str(p) for p in page_numbers)
                answer += f"\n\n📄 출처: 페이지 {pages_str}"
            return answer
        except Exception:
            return "학점 정보 조회 중 오류가 발생했습니다. 다시 시도해주세요."

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
        # "N학년" 패턴이 없으면 단독 숫자도 시도
        match = re.search(r"\b([1-5])\b", text)
        if match:
            return match.group(1)
        return None

    def _format_schedule_for_grade(
        self, grade: str, registration: list[dict]
    ) -> str:
        """특정 학년의 수강신청 일정을 포맷팅한다."""
        target_labels = _GRADE_SCHEDULE_MAP.get(grade, [])
        # 전체학년 일정도 포함
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
