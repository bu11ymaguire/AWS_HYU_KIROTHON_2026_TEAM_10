"""RAG 파이프라인 모듈.

LangChain 프레임워크 기반으로 Chroma 벡터 DB와 OpenAI 임베딩/LLM을 사용하여
학사안내 데이터에 대한 질의응답을 수행한다.
"""

from __future__ import annotations

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_community.vectorstores import Chroma
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

_RELEVANCE_THRESHOLD = 0.3


class RAGPipeline:
    """RAG 기반 학사 규정 Q&A 파이프라인.

    Chroma 벡터 DB에 학사안내 페이지를 인덱싱하고,
    사용자 질문에 대해 유사도 검색 후 LLM으로 답변을 생성한다.
    """

    def __init__(self, vector_db_path: str, llm_model: str = "gpt-4o") -> None:
        """RAG 파이프라인 초기화.

        Args:
            vector_db_path: Chroma 벡터 DB 저장 경로.
            llm_model: 사용할 OpenAI LLM 모델명.
        """
        self._vector_db_path = vector_db_path
        self._llm_model = llm_model

        self._embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
        self._llm = ChatOpenAI(model=llm_model, temperature=0)

        self._text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=800,
            chunk_overlap=200,
            separators=["\n\n", "\n", ".", " "],
        )

        self._vectorstore: Chroma | None = None

    def index(self, pages: list[Page]) -> None:
        """페이지를 의미 단위 청크로 분할하여 Chroma 벡터 DB에 저장한다.

        각 청크에는 원본 페이지 번호 메타데이터가 포함된다.

        Args:
            pages: 인덱싱할 Page 객체 리스트.
        """
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
            )
            return

        self._vectorstore = Chroma.from_documents(
            documents=documents,
            embedding=self._embeddings,
            persist_directory=self._vector_db_path,
            collection_name="hanyang_schedule",
        )

    def query(self, question: str, top_k: int = 5) -> RAGResponse:
        """질문에 대해 관련 청크를 검색하고 LLM으로 답변을 생성한다.

        Args:
            question: 사용자 질문 텍스트.
            top_k: 검색할 유사 청크 수.

        Returns:
            RAGResponse: 답변 텍스트, 출처(페이지 번호), 근거 존재 여부.
        """
        if self._vectorstore is None:
            return RAGResponse(
                answer=_NO_EVIDENCE_ANSWER,
                sources=[],
                has_evidence=False,
            )

        results = self._vectorstore.similarity_search_with_relevance_scores(
            question, k=top_k
        )

        relevant_results = [
            (doc, score)
            for doc, score in results
            if score >= _RELEVANCE_THRESHOLD
        ]

        if not relevant_results:
            return RAGResponse(
                answer=_NO_EVIDENCE_ANSWER,
                sources=[],
                has_evidence=False,
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
            answer=answer,
            sources=sources,
            has_evidence=has_evidence,
        )
