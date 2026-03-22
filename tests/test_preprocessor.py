"""전처리 모듈 단위 테스트."""

from __future__ import annotations

import pytest

from src.models import Page, PreprocessorWarning
from src.preprocessor import PageParser, TableNormalizer, generate_page_warnings


class TestPageParser:
    """PageParser 단위 테스트."""

    def setup_method(self):
        self.parser = PageParser()

    def test_parse_single_page(self):
        raw = "--- 페이지 1 ---\n내용입니다."
        pages = self.parser.parse_pages(raw)
        assert len(pages) == 1
        assert pages[0].page_number == 1
        assert pages[0].content == "내용입니다."

    def test_parse_multiple_pages(self):
        raw = (
            "--- 페이지 1 ---\n첫 번째 페이지\n"
            "--- 페이지 2 ---\n두 번째 페이지\n"
            "--- 페이지 3 ---\n세 번째 페이지"
        )
        pages = self.parser.parse_pages(raw)
        assert len(pages) == 3
        assert pages[0].page_number == 1
        assert pages[1].page_number == 2
        assert pages[2].page_number == 3
        assert "첫 번째" in pages[0].content
        assert "두 번째" in pages[1].content
        assert "세 번째" in pages[2].content

    def test_parse_skipped_page_numbers(self):
        """data.md처럼 페이지 번호가 건너뛰는 경우."""
        raw = (
            "--- 페이지 1 ---\n페이지1\n"
            "--- 페이지 3 ---\n페이지3\n"
            "--- 페이지 5 ---\n페이지5"
        )
        pages = self.parser.parse_pages(raw)
        assert len(pages) == 3
        assert [p.page_number for p in pages] == [1, 3, 5]

    def test_parse_empty_text(self):
        assert self.parser.parse_pages("") == []
        assert self.parser.parse_pages("   ") == []

    def test_parse_no_delimiter(self):
        """구분자가 없으면 전체를 page_number=0인 단일 페이지로 반환."""
        raw = "구분자 없는 텍스트입니다."
        pages = self.parser.parse_pages(raw)
        assert len(pages) == 1
        assert pages[0].page_number == 0
        assert pages[0].content == raw

    def test_parse_empty_page_content(self):
        """빈 페이지 처리."""
        raw = "--- 페이지 1 ---\n\n--- 페이지 2 ---\n내용"
        pages = self.parser.parse_pages(raw)
        assert len(pages) == 2
        assert pages[0].page_number == 1
        assert pages[0].content == ""
        assert pages[1].page_number == 2

    def test_parse_header_before_first_delimiter(self):
        """첫 구분자 앞의 헤더 텍스트는 무시된다."""
        raw = "# 제목\n\n--- 페이지 1 ---\n내용"
        pages = self.parser.parse_pages(raw)
        assert len(pages) == 1
        assert pages[0].page_number == 1

    def test_page_metadata_includes_page_number(self):
        raw = "--- 페이지 42 ---\n내용"
        pages = self.parser.parse_pages(raw)
        assert pages[0].metadata["page_number"] == 42

    def test_parse_delimiter_with_extra_spaces(self):
        """구분자에 여분의 공백이 있는 경우."""
        raw = "---  페이지  10  ---\n내용"
        pages = self.parser.parse_pages(raw)
        assert len(pages) == 1
        assert pages[0].page_number == 10


class TestTableNormalizer:
    """TableNormalizer 단위 테스트."""

    def setup_method(self):
        self.normalizer = TableNormalizer()

    def test_normalize_simple_table(self):
        raw = "이름  나이  학과\n홍길동  20  컴퓨터공학\n김철수  21  전자공학"
        result = self.normalizer.normalize(raw)
        assert len(result) == 2
        assert result[0]["이름"] == "홍길동"
        assert result[0]["나이"] == "20"
        assert result[1]["학과"] == "전자공학"

    def test_normalize_empty_input(self):
        assert self.normalizer.normalize("") == []
        assert self.normalizer.normalize("   ") == []

    def test_normalize_header_only(self):
        raw = "이름  나이  학과"
        result = self.normalizer.normalize(raw)
        assert result == []

    def test_normalize_broken_rows(self):
        """깨진 행이 이전 행에 이어붙여지는 경우."""
        raw = "구분  내용\n항목1  설명이\n길어서 이어짐"
        result = self.normalizer.normalize(raw)
        assert len(result) >= 1
        # 첫 행의 내용에 이어붙여진 텍스트가 포함되어야 함
        assert "설명이" in result[0]["내용"] or "설명이" in result[0].get("구분", "")

    def test_normalize_tab_separated(self):
        raw = "이름\t나이\n홍길동\t20"
        result = self.normalizer.normalize(raw)
        assert len(result) == 1
        assert result[0]["이름"] == "홍길동"

    def test_generate_warnings_column_mismatch(self):
        raw = "이름  나이  학과\n홍길동  20  컴공  추가열  또추가"
        warnings = self.normalizer.generate_warnings(raw, page_number=5, start_line=10)
        assert len(warnings) >= 1
        assert all(isinstance(w, PreprocessorWarning) for w in warnings)
        assert all(w.page_number == 5 for w in warnings)
        assert all(w.line_number >= 10 for w in warnings)

    def test_generate_warnings_empty_input(self):
        assert self.normalizer.generate_warnings("", page_number=1) == []


class TestGeneratePageWarnings:
    """generate_page_warnings 함수 테스트."""

    def test_no_warnings_for_normal_text(self):
        pages = [Page(page_number=1, content="정상적인 텍스트입니다.", metadata={})]
        warnings = generate_page_warnings(pages, "")
        assert warnings == []

    def test_warning_for_control_characters(self):
        pages = [Page(page_number=3, content="텍스트\x01제어문자", metadata={})]
        warnings = generate_page_warnings(pages, "")
        assert len(warnings) == 1
        assert warnings[0].page_number == 3
        assert warnings[0].line_number >= 1

    def test_warning_for_replacement_character(self):
        pages = [Page(page_number=5, content="깨진\ufffd인코딩", metadata={})]
        warnings = generate_page_warnings(pages, "")
        assert len(warnings) == 1
        assert warnings[0].page_number == 5

    def test_warning_includes_page_and_line_number(self):
        """경고에 반드시 page_number와 line_number가 포함되어야 한다."""
        pages = [Page(page_number=7, content="줄1\n줄2\n깨진\x02데이터", metadata={})]
        warnings = generate_page_warnings(pages, "")
        assert len(warnings) >= 1
        for w in warnings:
            assert hasattr(w, "page_number")
            assert hasattr(w, "line_number")
            assert w.page_number == 7
            assert w.line_number == 3  # 세 번째 줄
