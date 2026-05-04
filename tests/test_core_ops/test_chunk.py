from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.parsers.base import ParsedPage, ParseResult


@pytest.fixture
def sample_parse_result():
    return ParseResult(
        pages=[
            ParsedPage(
                page_number=1, text="Page 1 text with some content about finance."
            ),
            ParsedPage(
                page_number=2, text="Page 2 text with more content about revenue."
            ),
        ],
        metadata={"source": "test.pdf", "total_pages": 2},
    )


class TestChunkParsed:
    def test_chunk_parsed_fixed_strategy(self, sample_parse_result):
        from src.core.ops.chunk import chunk_parsed

        with patch("src.core.ops.chunk.chunk_text") as mock_chunk:
            mock_chunk.return_value = [
                {"text": "chunk1", "metadata": {}},
                {"text": "chunk2", "metadata": {}},
            ]
            result = chunk_parsed(sample_parse_result, strategy="fixed", chunk_size=256)

        assert len(result) == 2
        mock_chunk.assert_called_once()

    def test_chunk_parsed_page_aware_strategy(self, sample_parse_result):
        from src.core.ops.chunk import chunk_parsed

        with patch("src.core.ops.chunk.chunk_text_page_aware") as mock_chunk:
            mock_chunk.return_value = [
                {"text": "chunk1", "metadata": {"source": "test.pdf"}},
            ]
            result = chunk_parsed(
                sample_parse_result, strategy="page_aware", chunk_size=512
            )

        assert len(result) == 1
        mock_chunk.assert_called_once()

    def test_chunk_parsed_semantic_strategy_requires_embedder(
        self, sample_parse_result
    ):
        from src.core.ops.chunk import chunk_parsed

        with pytest.raises(ValueError, match="embedder is required"):
            chunk_parsed(sample_parse_result, strategy="semantic")

    def test_chunk_parsed_semantic_strategy_with_embedder(self, sample_parse_result):
        from src.core.ops.chunk import chunk_parsed

        mock_embedder = MagicMock()
        with patch("src.core.ops.chunk.chunk_text_semantic") as mock_chunk:
            mock_chunk.return_value = [
                {"text": "chunk1", "metadata": {}},
            ]
            result = chunk_parsed(
                sample_parse_result, strategy="semantic", embedder=mock_embedder
            )

        assert len(result) == 1
        mock_chunk.assert_called_once()

    def test_chunk_parsed_unknown_strategy(self, sample_parse_result):
        from src.core.ops.chunk import chunk_parsed

        with pytest.raises(ValueError, match="Unknown chunking strategy"):
            chunk_parsed(sample_parse_result, strategy="nonexistent")

    def test_chunk_parsed_merges_source_metadata(self, sample_parse_result):
        from src.core.ops.chunk import chunk_parsed

        with patch("src.core.ops.chunk.chunk_text_page_aware") as mock_chunk:
            mock_chunk.return_value = [
                {"text": "chunk1", "metadata": {"page": 1}},
            ]
            result = chunk_parsed(sample_parse_result, strategy="page_aware")

        assert result[0]["metadata"]["source"] == "test.pdf"
        assert result[0]["metadata"]["page"] == 1

    def test_chunk_parsed_parent_chunk_config_warning(self, sample_parse_result):
        from src.core.ops.chunk import chunk_parsed

        with patch("src.core.ops.chunk.chunk_text_page_aware") as mock_chunk:
            mock_chunk.return_value = [{"text": "c1", "metadata": {}}]
            result = chunk_parsed(
                sample_parse_result,
                strategy="page_aware",
                parent_chunk_config={"enabled": True},
            )

        assert len(result) == 1
