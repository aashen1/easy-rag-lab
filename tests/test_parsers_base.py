from __future__ import annotations

import pytest

from src.parsers.base import BaseParser, ParsedPage, ParseResult
from src.parsers.registry import ParserRegistry


class TestParsedPage:
    def test_default_construction(self) -> None:
        page = ParsedPage(page_number=1, text="Hello")
        assert page.page_number == 1
        assert page.text == "Hello"
        assert page.metadata == {}

    def test_with_metadata(self) -> None:
        page = ParsedPage(page_number=3, text="Content", metadata={"source": "test.pdf"})
        assert page.metadata == {"source": "test.pdf"}


class TestParseResult:
    def test_default_construction(self) -> None:
        result = ParseResult()
        assert result.pages == []
        assert result.metadata == {}

    def test_with_pages(self) -> None:
        pages = [ParsedPage(page_number=1, text="A"), ParsedPage(page_number=2, text="B")]
        result = ParseResult(pages=pages, metadata={"page_count": 2})
        assert len(result.pages) == 2
        assert result.metadata["page_count"] == 2


class TestParserRegistry:
    def test_list_names_includes_builtins(self) -> None:
        names = ParserRegistry.list_names()
        assert "pymupdf4llm" in names
        assert "fitz_pdfplumber" in names

    def test_get_unknown_raises_value_error(self) -> None:
        with pytest.raises(ValueError) as exc_info:
            ParserRegistry.get("unknown_parser")
        assert "unknown_parser" in str(exc_info.value)

    def test_register_custom_parser(self) -> None:
        class CustomParser(BaseParser):
            def __init__(self, config: dict | None = None):
                self._config = config or {}

            @property
            def name(self) -> str:
                return "custom"

            def parse(self, pdf_path: str) -> ParseResult:
                return ParseResult()

        ParserRegistry.register("custom_test", CustomParser)
        assert "custom_test" in ParserRegistry.list_names()

        parser = ParserRegistry.get("custom_test")
        assert isinstance(parser, CustomParser)
        assert parser.name == "custom"

    def test_register_non_subclass_raises_type_error(self) -> None:
        with pytest.raises(TypeError):
            ParserRegistry.register("bad", object)
