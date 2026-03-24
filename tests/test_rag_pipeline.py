"""RAG 파이프라인 단위 테스트.

외부 API 호출 없이 RAG 파이프라인의 핵심 로직을 검증한다.
임베딩과 LLM은 모킹하여 청크 분할, 메타데이터 보존, 응답 구조를 테스트한다.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from src.models import Page, RAGResponse, ChunkSource
from src.rag_pipeline import RAGPipeline, _NO_EVIDENCE_ANSWER


@pytest.fixture
def temp_db_path():
    """임시 벡터 DB 경로를 생성하고 테스트 후 정리한다."""
    path = tempfile.mkdtemp(prefix="test_chroma_")
    yield path
    shutil.rmtree(path, ignore_errors=True)


@pytest.fixture
def sample_pages():
    """테스트용 Page 객체 리스트."""
    return [
        Page(
            page_number=1,
            content="수강신청 가능학점은 최소 10학점, 최대 20학점입니다.",
            metadata={"section": "학점규정"},
        ),
        Page(
            page_number=2,
            content="폐강 기준: 재학인원 25명 이상 학과의 일반 교과목은 수강인원 10명 미만 시 폐강됩니다.",
            metadata={"section": "폐강기준"},
        ),
        Page(
            page_number=3,
            content="선수과목: 기초학술영어를 이수해야 전문학술영어를 수강할 수 있습니다.",
            metadata={"section": "선수후수"},
        ),
    ]


class TestRAGPipelineInit:
    """RAGPipeline 초기화 테스트."""

    @patch("src.rag_pipeline.HuggingFaceEmbeddings")
    @patch("src.rag_pipeline.ChatGoogleGenerativeAI")
    def test_init_creates_instance(self, mock_llm, mock_embeddings, temp_db_path):
        """RAGPipeline 인스턴스가 정상적으로 생성된다."""
        pipeline = RAGPipeline(vector_db_path=temp_db_path, llm_model="gemini-2.5-flash")
        assert pipeline._vector_db_path == temp_db_path
        assert pipeline._llm_model == "gemini-2.5-flash"
        assert pipeline._vectorstore is None

    @patch("src.rag_pipeline.HuggingFaceEmbeddings")
    @patch("src.rag_pipeline.ChatGoogleGenerativeAI")
    def test_init_default_model(self, mock_llm, mock_embeddings, temp_db_path):
        """기본 LLM 모델이 gemini-2.5-flash로 설정된다."""
        pipeline = RAGPipeline(vector_db_path=temp_db_path)
        assert pipeline._llm_model == "gemini-2.5-flash"


class TestRAGPipelineIndex:
    """RAGPipeline.index() 테스트."""

    @patch("src.rag_pipeline.Chroma")
    @patch("src.rag_pipeline.HuggingFaceEmbeddings")
    @patch("src.rag_pipeline.ChatGoogleGenerativeAI")
    def test_index_creates_documents_with_page_metadata(
        self, mock_llm, mock_embeddings, mock_chroma, temp_db_path, sample_pages
    ):
        """인덱싱 시 각 청크에 page_number 메타데이터가 포함된다."""
        mock_chroma.from_documents.return_value = MagicMock()

        pipeline = RAGPipeline(vector_db_path=temp_db_path)
        pipeline.index(sample_pages)

        call_args = mock_chroma.from_documents.call_args
        documents = call_args.kwargs.get("documents") or call_args[1].get("documents")
        if documents is None:
            documents = call_args[0][0]

        assert len(documents) > 0
        for doc in documents:
            assert "page_number" in doc.metadata
            assert doc.metadata["page_number"] in [1, 2, 3]
            assert doc.metadata["source"] == "data.md"

    @patch("src.rag_pipeline.Chroma")
    @patch("src.rag_pipeline.HuggingFaceEmbeddings")
    @patch("src.rag_pipeline.ChatGoogleGenerativeAI")
    def test_index_empty_pages(
        self, mock_llm, mock_embeddings, mock_chroma_cls, temp_db_path
    ):
        """빈 페이지 리스트 인덱싱 시 빈 벡터스토어가 생성된다."""
        pipeline = RAGPipeline(vector_db_path=temp_db_path)
        pipeline.index([])

        mock_chroma_cls.assert_called_once()
        mock_chroma_cls.from_documents.assert_not_called()

    @patch("src.rag_pipeline.Chroma")
    @patch("src.rag_pipeline.HuggingFaceEmbeddings")
    @patch("src.rag_pipeline.ChatGoogleGenerativeAI")
    def test_index_skips_empty_content_pages(
        self, mock_llm, mock_embeddings, mock_chroma, temp_db_path
    ):
        """빈 content를 가진 페이지는 건너뛴다."""
        pages = [
            Page(page_number=1, content="", metadata={}),
            Page(page_number=2, content="   ", metadata={}),
            Page(page_number=3, content="실제 내용", metadata={}),
        ]

        mock_chroma.from_documents.return_value = MagicMock()

        pipeline = RAGPipeline(vector_db_path=temp_db_path)
        pipeline.index(pages)

        call_args = mock_chroma.from_documents.call_args
        documents = call_args.kwargs.get("documents") or call_args[1].get("documents")
        if documents is None:
            documents = call_args[0][0]

        assert len(documents) >= 1
        for doc in documents:
            assert doc.metadata["page_number"] == 3


class TestRAGPipelineQuery:
    """RAGPipeline.query() 테스트."""

    @patch("src.rag_pipeline.HuggingFaceEmbeddings")
    @patch("src.rag_pipeline.ChatGoogleGenerativeAI")
    def test_query_without_index_returns_no_evidence(
        self, mock_llm, mock_embeddings, temp_db_path
    ):
        """인덱싱 없이 쿼리하면 '해당 정보를 찾을 수 없습니다'를 반환한다."""
        pipeline = RAGPipeline(vector_db_path=temp_db_path)
        result = pipeline.query("최대 학점은?")

        assert isinstance(result, RAGResponse)
        assert result.answer == _NO_EVIDENCE_ANSWER
        assert result.sources == []
        assert result.has_evidence is False

    @patch("src.rag_pipeline.HuggingFaceEmbeddings")
    @patch("src.rag_pipeline.ChatGoogleGenerativeAI")
    def test_query_no_relevant_results_returns_no_evidence(
        self, mock_llm_cls, mock_embeddings, temp_db_path
    ):
        """유사도가 낮은 결과만 있으면 '해당 정보를 찾을 수 없습니다'를 반환한다."""
        pipeline = RAGPipeline(vector_db_path=temp_db_path)

        mock_vectorstore = MagicMock()
        mock_vectorstore.similarity_search_with_relevance_scores.return_value = []
        pipeline._vectorstore = mock_vectorstore

        result = pipeline.query("관련 없는 질문")

        assert result.answer == _NO_EVIDENCE_ANSWER
        assert result.has_evidence is False
        assert result.sources == []

    @patch("src.rag_pipeline.HuggingFaceEmbeddings")
    @patch("src.rag_pipeline.ChatGoogleGenerativeAI")
    def test_query_with_relevant_results_returns_answer(
        self, mock_llm_cls, mock_embeddings, temp_db_path
    ):
        """관련 청크가 있으면 LLM 답변과 출처를 반환한다."""
        from langchain_core.documents import Document
        from langchain_core.messages import AIMessage

        mock_llm_instance = MagicMock()
        mock_llm_instance.invoke.return_value = AIMessage(
            content="최대 20학점까지 수강 가능합니다."
        )
        mock_llm_cls.return_value = mock_llm_instance

        pipeline = RAGPipeline(vector_db_path=temp_db_path)

        mock_vectorstore = MagicMock()
        mock_vectorstore.similarity_search_with_relevance_scores.return_value = [
            (
                Document(
                    page_content="수강신청 가능학점은 최소 10학점, 최대 20학점입니다.",
                    metadata={"page_number": 1},
                ),
                0.85,
            ),
        ]
        pipeline._vectorstore = mock_vectorstore

        result = pipeline.query("최대 학점은?")

        assert isinstance(result, RAGResponse)
        assert "20학점" in result.answer
        assert result.has_evidence is True
        assert len(result.sources) == 1
        assert result.sources[0].page_number == 1
        assert result.sources[0].similarity_score == 0.85

    @patch("src.rag_pipeline.HuggingFaceEmbeddings")
    @patch("src.rag_pipeline.ChatGoogleGenerativeAI")
    def test_query_sources_contain_page_numbers(
        self, mock_llm_cls, mock_embeddings, temp_db_path
    ):
        """쿼리 결과의 sources에 페이지 번호가 포함된다."""
        from langchain_core.documents import Document
        from langchain_core.messages import AIMessage

        mock_llm_instance = MagicMock()
        mock_llm_instance.invoke.return_value = AIMessage(content="답변 내용")
        mock_llm_cls.return_value = mock_llm_instance

        pipeline = RAGPipeline(vector_db_path=temp_db_path)

        mock_vectorstore = MagicMock()
        mock_vectorstore.similarity_search_with_relevance_scores.return_value = [
            (
                Document(page_content="페이지 5 내용", metadata={"page_number": 5}),
                0.9,
            ),
            (
                Document(page_content="페이지 12 내용", metadata={"page_number": 12}),
                0.7,
            ),
        ]
        pipeline._vectorstore = mock_vectorstore

        result = pipeline.query("질문")

        page_numbers = [s.page_number for s in result.sources]
        assert 5 in page_numbers
        assert 12 in page_numbers

    @patch("src.rag_pipeline.HuggingFaceEmbeddings")
    @patch("src.rag_pipeline.ChatGoogleGenerativeAI")
    def test_query_filters_low_relevance_results(
        self, mock_llm_cls, mock_embeddings, temp_db_path
    ):
        """유사도가 임계값 미만인 결과는 필터링된다."""
        from langchain_core.documents import Document

        pipeline = RAGPipeline(vector_db_path=temp_db_path)

        mock_vectorstore = MagicMock()
        mock_vectorstore.similarity_search_with_relevance_scores.return_value = [
            (
                Document(page_content="관련 없는 내용", metadata={"page_number": 1}),
                0.1,
            ),
        ]
        pipeline._vectorstore = mock_vectorstore

        result = pipeline.query("질문")

        assert result.answer == _NO_EVIDENCE_ANSWER
        assert result.has_evidence is False

    @patch("src.rag_pipeline.HuggingFaceEmbeddings")
    @patch("src.rag_pipeline.ChatGoogleGenerativeAI")
    def test_query_llm_returns_no_evidence_text(
        self, mock_llm_cls, mock_embeddings, temp_db_path
    ):
        """LLM이 '해당 정보를 찾을 수 없습니다'를 포함한 답변을 반환하면 has_evidence=False."""
        from langchain_core.documents import Document
        from langchain_core.messages import AIMessage

        mock_llm_instance = MagicMock()
        mock_llm_instance.invoke.return_value = AIMessage(
            content="해당 정보를 찾을 수 없습니다"
        )
        mock_llm_cls.return_value = mock_llm_instance

        pipeline = RAGPipeline(vector_db_path=temp_db_path)

        mock_vectorstore = MagicMock()
        mock_vectorstore.similarity_search_with_relevance_scores.return_value = [
            (
                Document(page_content="일부 내용", metadata={"page_number": 1}),
                0.5,
            ),
        ]
        pipeline._vectorstore = mock_vectorstore

        result = pipeline.query("질문")

        assert result.has_evidence is False
