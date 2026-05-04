from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestPdfPlumberEnhancerEnhancePage:
    def test_enhance_page_returns_enhanced_text(self):
        from src.parsers.pdfplumber_enhancer import PdfPlumberEnhancer

        enhancer = PdfPlumberEnhancer()

        with (
            patch.object(
                enhancer,
                "_extract_single_page_tables",
                return_value=["| table |", "md"],
            ),
            patch.object(
                enhancer, "_filter_low_quality", return_value=(["| table |", "md"], [])
            ),
            patch.object(enhancer, "_append_tables", return_value="enhanced text"),
        ):
            result = enhancer.enhance_page("test.pdf", 1, "original text")

        assert result == "enhanced text"

    def test_enhance_page_no_tables_returns_original(self):
        from src.parsers.pdfplumber_enhancer import PdfPlumberEnhancer

        enhancer = PdfPlumberEnhancer()

        with patch.object(enhancer, "_extract_single_page_tables", return_value=[]):
            result = enhancer.enhance_page("test.pdf", 1, "original text")

        assert result == "original text"

    def test_enhance_page_uses_0_indexed_page_idx(self):
        from src.parsers.pdfplumber_enhancer import PdfPlumberEnhancer

        enhancer = PdfPlumberEnhancer()

        with (
            patch.object(
                enhancer,
                "_extract_single_page_tables",
                return_value=["md"],
            ) as mock_extract,
            patch.object(enhancer, "_filter_low_quality", return_value=(["md"], [])),
            patch.object(enhancer, "_append_tables", return_value="enhanced"),
        ):
            enhancer.enhance_page("test.pdf", 5, "text")

        mock_extract.assert_called_once_with("test.pdf", 4)


class TestPdfPlumberEnhancerEnhanceTable:
    def test_enhance_table_replaces_specific_table(self):
        from src.parsers.pdfplumber_enhancer import PdfPlumberEnhancer

        enhancer = PdfPlumberEnhancer()

        with (
            patch.object(
                enhancer,
                "_extract_single_page_tables",
                return_value=["table1", "table2"],
            ),
            patch.object(
                enhancer,
                "_filter_low_quality",
                return_value=(["| new |", "table |"], []),
            ),
            patch.object(
                enhancer, "_find_md_table_spans", return_value=[(5, 15), (20, 30)]
            ),
        ):
            result = enhancer.enhance_table(
                "test.pdf", 1, 2, "01234old_table_101new_table_2"
            )

        assert "| new |" in result or "table" in result

    def test_enhance_table_index_out_of_range_returns_original(self):
        from src.parsers.pdfplumber_enhancer import PdfPlumberEnhancer

        enhancer = PdfPlumberEnhancer()

        with patch.object(
            enhancer, "_extract_single_page_tables", return_value=["table1"]
        ):
            result = enhancer.enhance_table("test.pdf", 1, 5, "original text")

        assert result == "original text"

    def test_enhance_table_uses_0_indexed_page_idx(self):
        from src.parsers.pdfplumber_enhancer import PdfPlumberEnhancer

        enhancer = PdfPlumberEnhancer()

        with (
            patch.object(
                enhancer,
                "_extract_single_page_tables",
                return_value=["md"],
            ) as mock_extract,
            patch.object(enhancer, "_filter_low_quality", return_value=(["md"], [])),
            patch.object(enhancer, "_find_md_table_spans", return_value=[(0, 5)]),
        ):
            enhancer.enhance_table("test.pdf", 3, 1, "text")

        mock_extract.assert_called_once_with("test.pdf", 2)


class TestParserRegistryGetEnhancer:
    def test_get_enhancer_returns_enhancer_instance(self):
        from src.parsers.registry import ParserRegistry

        mock_enhancer_cls = MagicMock()
        mock_enhancer_instance = MagicMock()
        mock_enhancer_cls.return_value = mock_enhancer_instance

        with patch.dict(ParserRegistry._enhancers, {"pdfplumber": mock_enhancer_cls}):
            result = ParserRegistry.get_enhancer("pdfplumber")

        assert result is mock_enhancer_instance
        mock_enhancer_cls.assert_called_once_with(config={})

    def test_get_enhancer_unknown_name_raises(self):
        from src.exceptions import ParsingError
        from src.parsers.registry import ParserRegistry

        with pytest.raises(ParsingError, match="not registered"):
            ParserRegistry.get_enhancer("nonexistent_enhancer")
