"""RAG 파이프라인 모듈.

로컬 sentence-transformers 임베딩 + Google Gemini LLM으로
학사안내 데이터에 대한 질의응답을 수행한다.
API 키: GOOGLE_API_KEY (Google AI Studio에서 무료 발급)
"""

from __future__ import annotations

import os

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_core.documents import Document
from langchain_core.messages import HumanMessage, SystemMessage

from src.models import Page, RAGResponse, ChunkSource


_SYSTEM_PROMPT = (
    "당신은 한양대학교 서울캠퍼스 학사안내 전문 도우미입니다. "
    "아래 제공된 참고 자료만을 근거로 질문에 답변하세요. "
    "참고 자료에 해당 정보가 없으면 반드시 '해당 정보를 찾을 수 없습니다'라고 답변하세요. "
    "답변은 한국어로 작성하세요."
)

_NO_EVIDENCE_ANSWER = "해당 정보를 찾을 수 없습니다"

_RELEVANCE_THRESHOLD = 0.15


class RAGPipeline:
    """RAG 기반 학사 규정 Q&A 파이프라인.

    임베딩: 로컬 sentence-transformers (API 키 불필요)
    LLM: Google Gemini (무료 티어)
    """

    def __init__(
        self,
        vector_db_path: str,
        llm_model: str = "gemini-2.5-flash",
    ) -> None:
        self._vector_db_path = vector_db_path
        self._llm_model = llm_model

        # 한국어 로컬 임베딩 — API 키 불필요
        self._embeddings = HuggingFaceEmbeddings(
            model_name="jhgan/ko-sroberta-multitask",
        )

        # Gemini LLM — GOOGLE_API_KEY 환경변수 필요
        self._llm = ChatGoogleGenerativeAI(
            model=llm_model,
            temperature=0,
            google_api_key=os.environ.get("GOOGLE_API_KEY", ""),
        )

        self._text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=800,
            chunk_overlap=200,
            separators=["\n\n", "\n", ".", " "],
        )

        self._vectorstore: Chroma | None = None

    def index(self, pages: list[Page]) -> None:
        """페이지를 청크로 분할하여 Chroma 벡터 DB에 저장한다."""
        documents: list[Document] = []

        for page in pages:
            if not page.content.strip():
                continue
            chunks = self._text_splitter.split_text(page.content)
            for chunk in chunks:
                doc = Document(
                    page_content=chunk,
                    metadata={
                        "page_number": page.page_number,
                        "source": "data.md",
                    },
                )
                documents.append(doc)

        if not documents:
            self._vectorstore = Chroma(
                persist_directory=self._vector_db_path,
                embedding_function=self._embeddings,
                collection_name="hanyang_schedule",
                collection_metadata={"hnsw:space": "cosine"},
            )
            return

        self._vectorstore = Chroma.from_documents(
            documents=documents,
            embedding=self._embeddings,
            persist_directory=self._vector_db_path,
            collection_name="hanyang_schedule",
            collection_metadata={"hnsw:space": "cosine"},
        )

    def query(self, question: str, top_k: int = 5) -> RAGResponse:
        """질문에 대해 관련 청크를 검색하고 Gemini로 답변을 생성한다."""
        if self._vectorstore is None:
            return RAGResponse(
                answer=_NO_EVIDENCE_ANSWER, sources=[], has_evidence=False,
            )

        results = self._vectorstore.similarity_search_with_relevance_scores(
            question, k=top_k
        )

        relevant_results = [
            (doc, score) for doc, score in results
            if score >= _RELEVANCE_THRESHOLD
        ]

        if not relevant_results:
            return RAGResponse(
                answer=_NO_EVIDENCE_ANSWER, sources=[], has_evidence=False,
            )

        sources: list[ChunkSource] = []
        context_parts: list[str] = []

        for doc, score in relevant_results:
            page_number = doc.metadata.get("page_number", 0)
            sources.append(
                ChunkSource(
                    page_number=page_number,
                    chunk_text=doc.page_content,
                    similarity_score=score,
                )
            )
            context_parts.append(
                f"[페이지 {page_number}]\n{doc.page_content}"
            )

        context = "\n\n---\n\n".join(context_parts)

        user_prompt = (
            f"참고 자료:\n{context}\n\n"
            f"질문: {question}\n\n"
            "위 참고 자료만을 근거로 답변하세요. "
            "근거가 없으면 '해당 정보를 찾을 수 없습니다'라고 답변하세요."
        )

        messages = [
            SystemMessage(content=_SYSTEM_PROMPT),
            HumanMessage(content=user_prompt),
        ]

        response = self._llm.invoke(messages)
        answer = response.content

        has_evidence = _NO_EVIDENCE_ANSWER not in answer

        return RAGResponse(
            answer=answer, sources=sources, has_evidence=has_evidence,
        )
