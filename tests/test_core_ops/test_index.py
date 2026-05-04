from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np


class TestIndexChunks:
    def test_index_chunks_creates_and_indexes(self):
        from src.core.ops.index import index_chunks

        mock_embedder = MagicMock()
        mock_embedder.embed_texts.return_value = np.ones((2, 128), dtype=np.float32)
        mock_embedder.get_embedding_dimension.return_value = 128

        chunks = [
            {"text": "chunk1", "metadata": {"source": "a.pdf"}},
            {"text": "chunk2", "metadata": {"source": "b.pdf"}},
        ]

        mock_indexer = MagicMock()
        mock_indexer.get_collection_info.return_value = {"points_count": 0}

        with patch("src.core.ops.index.VectorIndexer", return_value=mock_indexer):
            result = index_chunks(chunks, mock_embedder, collection_name="test_col")

        assert result == 2
        mock_indexer.create_collection.assert_called_once()
        mock_indexer.close.assert_called_once()

    def test_index_chunks_empty_list(self):
        from src.core.ops.index import index_chunks

        result = index_chunks([], MagicMock())
        assert result == 0


class TestDeleteSourceAndReindex:
    def test_delete_and_reindex(self):
        from src.core.ops.index import delete_source_and_reindex

        mock_embedder = MagicMock()
        mock_embedder.embed_texts.return_value = np.ones((1, 128), dtype=np.float32)
        mock_embedder.get_embedding_dimension.return_value = 128

        mock_indexer = MagicMock()

        new_chunks = [{"text": "new chunk", "metadata": {"source": "a.pdf"}}]

        with patch("src.core.ops.index.VectorIndexer", return_value=mock_indexer):
            result = delete_source_and_reindex(
                "a.pdf", new_chunks, mock_embedder, collection_name="test_col"
            )

        assert result == 1
        mock_indexer.delete_by_source.assert_called_once_with("a.pdf")
        mock_indexer.upsert_chunks.assert_called_once()
        mock_indexer.close.assert_called_once()

    def test_delete_and_reindex_no_new_chunks(self):
        from src.core.ops.index import delete_source_and_reindex

        mock_embedder = MagicMock()
        mock_indexer = MagicMock()

        with patch("src.core.ops.index.VectorIndexer", return_value=mock_indexer):
            result = delete_source_and_reindex(
                "a.pdf", [], mock_embedder, collection_name="test_col"
            )

        assert result == 0
        mock_indexer.delete_by_source.assert_called_once_with("a.pdf")
        mock_indexer.close.assert_called_once()
