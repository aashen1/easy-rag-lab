from __future__ import annotations

from unittest.mock import MagicMock, patch


class TestVectorIndexerDeleteBySource:
    def test_delete_by_source_returns_count(self):
        from src.indexer import VectorIndexer

        mock_client = MagicMock()
        count_result = MagicMock()
        count_result.count = 5
        mock_client.count.return_value = count_result

        with patch("src.indexer.QdrantClient", return_value=mock_client):
            indexer = VectorIndexer(collection_name="test_col")
            indexer.client = mock_client

            result = indexer.delete_by_source("test.pdf")

        assert result == 5
        mock_client.delete.assert_called_once()

    def test_delete_by_source_no_matching_points(self):
        from src.indexer import VectorIndexer

        mock_client = MagicMock()
        count_result = MagicMock()
        count_result.count = 0
        mock_client.count.return_value = count_result

        indexer = VectorIndexer(collection_name="test_col")
        indexer.client = mock_client

        result = indexer.delete_by_source("nonexistent.pdf")

        assert result == 0
        mock_client.delete.assert_not_called()


class TestVectorIndexerUpsertChunks:
    def test_upsert_chunks_generates_uuid_ids(self):
        import numpy as np

        from src.indexer import VectorIndexer

        mock_client = MagicMock()

        chunks = [
            {"text": "chunk1", "metadata": {"source": "a.pdf"}},
            {"text": "chunk2", "metadata": {"source": "a.pdf"}},
        ]
        embeddings = np.ones((2, 128), dtype=np.float32)

        indexer = VectorIndexer(collection_name="test_col")
        indexer.client = mock_client

        result = indexer.upsert_chunks(chunks, embeddings)

        assert result == 2
        mock_client.upsert.assert_called()
