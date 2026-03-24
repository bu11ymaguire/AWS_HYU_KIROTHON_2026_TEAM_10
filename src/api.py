"""FastAPI 서버 — 프론트엔드(HY-Plan)와 백엔드(RAG 챗봇) 연동 API.

세션 기반 멀티턴 대화를 지원한다.
실행: uvicorn src.api:app --reload --port 8000
"""

from __future__ import annotations

import os
import traceback
import uuid
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.cancellation_checker import CancellationChecker
from src.chatbot import ChatBot
from src.conflict_checker import ConflictChecker
from src.course_loader import load_sample_courses
from src.credit_validator import CreditValidator
from src.equivalent_manager import EquivalentManager
from src.main import _load_equivalent_courses, _load_prerequisite_rules
from src.models import ParsedData
from src.preprocessor import DataParser, PageParser
from src.prerequisite_checker import PrerequisiteChecker
from src.rag_pipeline import RAGPipeline
from src.schedule_recommender import ScheduleRecommender

_DATA_FILE = "data.md"
_VECTOR_DB_PATH = "data/chroma_db"

_chatbot: ChatBot | None = None


def _init_chatbot() -> ChatBot:
    """ChatBot 인스턴스를 생성한다."""
    load_dotenv()

    with open(_DATA_FILE, "r", encoding="utf-8") as f:
        raw_text = f.read()

    pages = PageParser().parse_pages(raw_text)
    parsed_data: ParsedData = DataParser().parse(pages)

    rag_pipeline = RAGPipeline(vector_db_path=_VECTOR_DB_PATH)
    rag_pipeline.index(pages)

    credit_validator = CreditValidator(parsed_data.credit_rules)
    conflict_checker = ConflictChecker()
    prerequisite_checker = PrerequisiteChecker(
        _load_prerequisite_rules(parsed_data.prerequisites)
    )
    cancellation_checker = CancellationChecker(parsed_data.cancel_rules)
    equivalent_manager = EquivalentManager(
        _load_equivalent_courses(parsed_data.equivalent_courses)
    )

    schedule_recommender = ScheduleRecommender(
        credit_validator=credit_validator,
        conflict_checker=conflict_checker,
        prerequisite_checker=prerequisite_checker,
        cancellation_checker=cancellation_checker,
        equivalent_manager=equivalent_manager,
    )

    # 강의 데이터 로드 (실제 CSV 우선, 없으면 샘플)
    courses_csv = os.environ.get("COURSES_CSV_PATH", "lec/hanyang-sugang.csv")
    if os.path.exists(courses_csv):
        from src.course_loader import load_from_csv
        available_courses = load_from_csv(courses_csv)
    else:
        available_courses = load_sample_courses()

    return ChatBot(
        rag_pipeline=rag_pipeline,
        schedule_recommender=schedule_recommender,
        credit_validator=credit_validator,
        parsed_data=parsed_data,
        available_courses=available_courses,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """서버 시작 시 챗봇 초기화, 종료 시 정리."""
    global _chatbot
    _chatbot = _init_chatbot()
    yield
    _chatbot = None


app = FastAPI(title="HY-Plan API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request / Response 스키마 ──

class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None


class ChatResponse(BaseModel):
    answer: str
    session_id: str
    sources: list[dict] | None = None


# ── 엔드포인트 ──

@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """프론트엔드에서 보낸 메시지를 챗봇에 전달하고 응답을 반환한다.

    session_id가 없으면 새로 생성하여 반환한다.
    """
    if _chatbot is None:
        return ChatResponse(
            answer="서버가 아직 초기화 중입니다. 잠시 후 다시 시도해주세요.",
            session_id=req.session_id or str(uuid.uuid4()),
        )

    session_id = req.session_id or str(uuid.uuid4())

    try:
        answer = _chatbot.handle_input(req.message, session_id=session_id)
    except Exception as e:
        traceback.print_exc()
        # 사용자 친화적 에러 메시지
        answer = "죄송합니다. 요청을 처리하는 중 문제가 발생했습니다. 잠시 후 다시 시도해주세요."

    return ChatResponse(answer=answer, session_id=session_id)
