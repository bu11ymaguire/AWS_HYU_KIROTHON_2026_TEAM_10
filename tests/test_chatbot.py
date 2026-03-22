"""의도 분류기 테스트."""

import pytest

from src.chatbot import Intent, IntentRouter


@pytest.fixture
def router() -> IntentRouter:
    return IntentRouter()


class TestIntentEnum:
    """Intent Enum 값 테스트."""

    def test_enum_values(self):
        assert Intent.REGULATION_QA.value == "regulation_qa"
        assert Intent.SCHEDULE_RECOMMEND.value == "schedule"
        assert Intent.SCHEDULE_INFO.value == "schedule_info"
        assert Intent.CREDIT_CHECK.value == "credit_check"
        assert Intent.DROP_CHECK.value == "drop_check"
        assert Intent.RETAKE_INFO.value == "retake_info"

    def test_enum_has_six_members(self):
        assert len(Intent) == 6


class TestIntentRouterScheduleRecommend:
    """시간표 추천 의도 분류 테스트."""

    @pytest.mark.parametrize("text", [
        "시간표 추천해줘",
        "시간표 짜줘",
        "시간표 보여줘",
        "과목 추천해줘",
    ])
    def test_schedule_recommend_keywords(self, router: IntentRouter, text: str):
        assert router.classify(text) == Intent.SCHEDULE_RECOMMEND


class TestIntentRouterScheduleInfo:
    """수강신청 일정 조회 의도 분류 테스트."""

    @pytest.mark.parametrize("text", [
        "수강신청 일정 알려줘",
        "신청 일정이 언제야?",
        "언제 신청해?",
        "수강신청 날짜 알려줘",
    ])
    def test_schedule_info_keywords(self, router: IntentRouter, text: str):
        assert router.classify(text) == Intent.SCHEDULE_INFO


class TestIntentRouterCreditCheck:
    """학점 확인 의도 분류 테스트."""

    @pytest.mark.parametrize("text", [
        "최대 학점이 몇이야?",
        "최소 학점 알려줘",
        "몇 학점까지 들을 수 있어?",
        "학점 제한이 어떻게 돼?",
    ])
    def test_credit_check_keywords(self, router: IntentRouter, text: str):
        assert router.classify(text) == Intent.CREDIT_CHECK


class TestIntentRouterDropCheck:
    """수강포기 의도 분류 테스트."""

    @pytest.mark.parametrize("text", [
        "수강포기 가능해?",
        "포기할 수 있어?",
        "드롭 가능한지 확인해줘",
    ])
    def test_drop_check_keywords(self, router: IntentRouter, text: str):
        assert router.classify(text) == Intent.DROP_CHECK


class TestIntentRouterRetakeInfo:
    """성적상승재수강 의도 분류 테스트."""

    @pytest.mark.parametrize("text", [
        "재수강 규칙 알려줘",
        "성적상승 재수강 가능해?",
        "재수강 하고 싶어",
    ])
    def test_retake_info_keywords(self, router: IntentRouter, text: str):
        assert router.classify(text) == Intent.RETAKE_INFO


class TestIntentRouterFallback:
    """폴백(REGULATION_QA) 테스트."""

    @pytest.mark.parametrize("text", [
        "졸업 요건이 뭐야?",
        "교양 필수 과목 알려줘",
        "",
        "   ",
        "안녕하세요",
    ])
    def test_fallback_to_regulation_qa(self, router: IntentRouter, text: str):
        assert router.classify(text) == Intent.REGULATION_QA


class TestIntentRouterPriority:
    """키워드 우선순위 테스트 — 더 구체적인 키워드가 우선."""

    def test_schedule_info_over_schedule_recommend(self, router: IntentRouter):
        """'수강신청 일정'은 SCHEDULE_INFO로 분류 (SCHEDULE_RECOMMEND보다 우선)."""
        assert router.classify("수강신청 일정 알려줘") == Intent.SCHEDULE_INFO


from dataclasses import dataclass, field

from src.chatbot import ChatBot
from src.models import ParsedData, ChunkSource, RAGResponse


# ------------------------------------------------------------------
# Mock / Stub helpers
# ------------------------------------------------------------------

@dataclass
class _MockRAGResponse:
    answer: str = "테스트 답변입니다."
    sources: list = field(default_factory=list)
    has_evidence: bool = True


class _MockRAGPipeline:
    """RAG 파이프라인 스텁."""

    def __init__(self, answer: str = "테스트 답변입니다.", sources: list | None = None):
        self._answer = answer
        self._sources = sources or []

    def query(self, question: str, top_k: int = 5):
        return _MockRAGResponse(
            answer=self._answer,
            sources=self._sources,
            has_evidence=bool(self._sources),
        )


class _ErrorRAGPipeline:
    """항상 예외를 발생시키는 RAG 스텁."""

    def query(self, question: str, top_k: int = 5):
        raise RuntimeError("API 오류")


def _make_parsed_data(**overrides) -> ParsedData:
    """테스트용 ParsedData 생성."""
    defaults = {
        "schedule": {
            "수강신청_일정": [
                {"대상": "4,5학년", "일자": "2026-02-09", "요일": "월", "시작시간": "11:00", "종료시간": "24:00", "비고": "온라인"},
                {"대상": "3학년", "일자": "2026-02-10", "요일": "화", "시작시간": "11:00", "종료시간": "24:00", "비고": "온라인"},
                {"대상": "2학년", "일자": "2026-02-11", "요일": "수", "시작시간": "11:00", "종료시간": "24:00", "비고": "온라인"},
                {"대상": "전체학년(2~5)", "일자": "2026-02-13", "요일": "금", "시작시간": "11:00", "종료시간": "24:00", "비고": ""},
                {"대상": "신·편입생", "일자": "2026-02-27", "요일": "금", "시작시간": "11:00", "종료시간": "24:00", "비고": "온라인"},
            ],
            "수강포기_일정": {
                "시작": "2026-03-23T09:00",
                "종료": "2026-03-24T24:00",
                "제한": ["학사학위취득유예자", "의과대학 의학과"],
                "최대과목수": 2,
                "조건": "수강포기 후 잔여학점이 수강신청 최소학점 이상",
            },
        },
        "credit_rules": {},
        "cancel_rules": {},
        "prerequisites": {},
        "equivalent_courses": {},
        "curriculum_rules": {},
    }
    defaults.update(overrides)
    return ParsedData(**defaults)


def _make_chatbot(
    rag=None, recommender=None, validator=None, parsed_data=None
) -> ChatBot:
    return ChatBot(
        rag_pipeline=rag or _MockRAGPipeline(),
        schedule_recommender=recommender,
        credit_validator=validator,
        parsed_data=parsed_data or _make_parsed_data(),
    )


# ------------------------------------------------------------------
# ChatBot.handle_input 테스트
# ------------------------------------------------------------------


class TestChatBotEmptyInput:
    """빈 입력 처리 테스트."""

    def test_empty_string(self):
        bot = _make_chatbot()
        assert bot.handle_input("") == "질문을 입력해주세요"

    def test_whitespace_only(self):
        bot = _make_chatbot()
        assert bot.handle_input("   ") == "질문을 입력해주세요"


class TestChatBotRegulationQA:
    """학사 규정 질문 핸들러 테스트."""

    def test_returns_rag_answer(self):
        bot = _make_chatbot(rag=_MockRAGPipeline(answer="졸업 요건은 130학점입니다."))
        result = bot.handle_input("졸업 요건이 뭐야?")
        assert "졸업 요건은 130학점입니다." in result

    def test_includes_page_sources(self):
        sources = [
            ChunkSource(page_number=5, chunk_text="...", similarity_score=0.9),
            ChunkSource(page_number=10, chunk_text="...", similarity_score=0.8),
        ]
        bot = _make_chatbot(rag=_MockRAGPipeline(answer="답변", sources=sources))
        result = bot.handle_input("교양 필수 과목 알려줘")
        assert "페이지 5" in result
        assert "페이지" in result

    def test_rag_error_returns_error_message(self):
        bot = _make_chatbot(rag=_ErrorRAGPipeline())
        result = bot.handle_input("졸업 요건이 뭐야?")
        assert "오류" in result


class TestChatBotScheduleInfo:
    """수강신청 일정 조회 핸들러 테스트."""

    def test_schedule_info_with_grade(self):
        bot = _make_chatbot()
        result = bot.handle_input("3학년 수강신청 일정 알려줘")
        assert "3학년" in result
        assert "2026-02-10" in result

    def test_schedule_info_all_grades(self):
        bot = _make_chatbot()
        result = bot.handle_input("수강신청 일정 알려줘")
        assert "수강신청 일정" in result

    def test_schedule_info_grade_4(self):
        bot = _make_chatbot()
        result = bot.handle_input("4학년 수강신청 일정")
        assert "4,5학년" in result
        assert "2026-02-09" in result

    def test_schedule_info_empty_schedule(self):
        pd = _make_parsed_data(schedule={"수강신청_일정": []})
        bot = _make_chatbot(parsed_data=pd)
        result = bot.handle_input("수강신청 일정 알려줘")
        assert "찾을 수 없습니다" in result


class TestChatBotDropCheck:
    """수강포기 핸들러 테스트."""

    def test_drop_check_returns_info(self):
        bot = _make_chatbot()
        result = bot.handle_input("수강포기 가능해?")
        assert "수강포기" in result
        assert "2과목" in result or "2" in result

    def test_drop_check_includes_restrictions(self):
        bot = _make_chatbot()
        result = bot.handle_input("수강포기 가능해?")
        assert "학사학위취득유예자" in result


class TestChatBotRetakeInfo:
    """성적상승재수강 핸들러 테스트."""

    def test_retake_info_c_plus(self):
        bot = _make_chatbot()
        result = bot.handle_input("재수강 규칙 알려줘")
        assert "C+" in result

    def test_retake_info_a0_limit(self):
        bot = _make_chatbot()
        result = bot.handle_input("재수강 규칙 알려줘")
        assert "A0" in result

    def test_retake_info_2025_limit(self):
        bot = _make_chatbot()
        result = bot.handle_input("재수강 규칙 알려줘")
        assert "2025" in result
        assert "2회" in result


class TestChatBotScheduleRecommend:
    """시간표 추천 핸들러 테스트."""

    def test_returns_info_collection_message(self):
        bot = _make_chatbot()
        result = bot.handle_input("시간표 추천해줘")
        assert "학번" in result
        assert "학년" in result
        assert "학과" in result


class TestChatBotCreditCheck:
    """학점 확인 핸들러 테스트."""

    def test_credit_check_uses_rag(self):
        bot = _make_chatbot(rag=_MockRAGPipeline(answer="최대 20학점입니다."))
        result = bot.handle_input("최대 학점이 몇이야?")
        assert "20학점" in result

    def test_credit_check_error(self):
        bot = _make_chatbot(rag=_ErrorRAGPipeline())
        result = bot.handle_input("최대 학점이 몇이야?")
        assert "오류" in result


class TestChatBotExtractGrade:
    """학년 추출 유틸리티 테스트."""

    @pytest.mark.parametrize("text,expected", [
        ("3학년 일정", "3"),
        ("4학년 수강신청", "4"),
        ("1학년 일정 알려줘", "1"),
        ("일정 알려줘", None),
    ])
    def test_extract_grade(self, text: str, expected: str | None):
        assert ChatBot._extract_grade(text) == expected
