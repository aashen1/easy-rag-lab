from unittest.mock import MagicMock

import pytest

from src.exceptions import RetrievalError
from src.retriever import Retriever


@pytest.mark.unit
class TestRetriever:
    def _make_mock_indexer(self, mock_qdrant_client):
        indexer = MagicMock()
        indexer.client = mock_qdrant_client
        indexer.collection_name = "test_collection"
        return indexer

    def test_retrieve_success(self, mock_embedder, mock_qdrant_client):
        indexer = self._make_mock_indexer(mock_qdrant_client)

        mock_point = MagicMock()
        mock_point.payload = {
            "chunk_id": "c1",
            "text": "test text",
            "metadata": {"source": "doc.pdf"},
        }
        mock_point.score = 0.95
        mock_result = MagicMock()
        mock_result.points = [mock_point]
        mock_qdrant_client.query_points.return_value = mock_result

        retriever = Retriever(indexer=indexer, embedder=mock_embedder, top_k=5)
        results = retriever.retrieve("test query")

        assert len(results) == 1
        assert results[0]["chunk_id"] == "c1"
        assert results[0]["text"] == "test text"
        assert results[0]["metadata"] == {"source": "doc.pdf"}
        assert results[0]["score"] == 0.95

    def test_retrieve_empty_query(self, mock_embedder, mock_qdrant_client):
        indexer = self._make_mock_indexer(mock_qdrant_client)
        retriever = Retriever(indexer=indexer, embedder=mock_embedder, top_k=5)

        with pytest.raises(RetrievalError, match="Query must be a non-empty string"):
            retriever.retrieve("")

    def test_retrieve_non_string_query(self, mock_embedder, mock_qdrant_client):
        indexer = self._make_mock_indexer(mock_qdrant_client)
        retriever = Retriever(indexer=indexer, embedder=mock_embedder, top_k=5)

        with pytest.raises(RetrievalError, match="Query must be a non-empty string"):
            retriever.retrieve(123)

    def test_retrieve_qdrant_error(self, mock_embedder, mock_qdrant_client):
        indexer = self._make_mock_indexer(mock_qdrant_client)
        mock_qdrant_client.query_points.side_effect = Exception("connection lost")

        retriever = Retriever(indexer=indexer, embedder=mock_embedder, top_k=5)

        with pytest.raises(RetrievalError, match="Failed to retrieve results"):
            retriever.retrieve("test query")

    def test_retrieve_result_payload_extraction(
        self, mock_embedder, mock_qdrant_client
    ):
        indexer = self._make_mock_indexer(mock_qdrant_client)

        point1 = MagicMock()
        point1.payload = {
            "chunk_id": "chunk_a",
            "text": "first chunk",
            "metadata": {"source": "a.pdf", "page": 1},
        }
        point1.score = 0.9

        point2 = MagicMock()
        point2.payload = {
            "chunk_id": "chunk_b",
            "text": "second chunk",
            "metadata": {"source": "b.pdf", "page": 2},
        }
        point2.score = 0.7

        mock_result = MagicMock()
        mock_result.points = [point1, point2]
        mock_qdrant_client.query_points.return_value = mock_result

        retriever = Retriever(indexer=indexer, embedder=mock_embedder, top_k=5)
        results = retriever.retrieve("test query")

        assert len(results) == 2

        assert results[0]["chunk_id"] == "chunk_a"
        assert results[0]["text"] == "first chunk"
        assert results[0]["metadata"] == {"source": "a.pdf", "page": 1}
        assert results[0]["score"] == 0.9

        assert results[1]["chunk_id"] == "chunk_b"
        assert results[1]["text"] == "second chunk"
        assert results[1]["metadata"] == {"source": "b.pdf", "page": 2}
        assert results[1]["score"] == 0.7

    def test_retrieve_missing_payload_fields(self, mock_embedder, mock_qdrant_client):
        indexer = self._make_mock_indexer(mock_qdrant_client)
        mock_point = MagicMock()
        mock_point.payload = {}
        mock_point.score = 0.5
        mock_result = MagicMock()
        mock_result.points = [mock_point]
        mock_qdrant_client.query_points.return_value = mock_result
        retriever = Retriever(indexer=indexer, embedder=mock_embedder, top_k=5)
        results = retriever.retrieve("test query")
        assert results[0]["chunk_id"] == ""
        assert results[0]["text"] == ""
        assert results[0]["metadata"] == {}

    def test_score_threshold_zero_does_not_filter(
        self, mock_embedder, mock_qdrant_client
    ):
        indexer = self._make_mock_indexer(mock_qdrant_client)

        point1 = MagicMock()
        point1.payload = {"chunk_id": "c1", "text": "low score", "metadata": {}}
        point1.score = 0.1

        point2 = MagicMock()
        point2.payload = {"chunk_id": "c2", "text": "high score", "metadata": {}}
        point2.score = 0.9

        mock_result = MagicMock()
        mock_result.points = [point1, point2]
        mock_qdrant_client.query_points.return_value = mock_result

        retriever = Retriever(
            indexer=indexer, embedder=mock_embedder, top_k=5, score_threshold=0
        )
        results = retriever.retrieve("test query")

        assert len(results) == 2

    def test_score_threshold_filters_low_scores(
        self, mock_embedder, mock_qdrant_client
    ):
        indexer = self._make_mock_indexer(mock_qdrant_client)

        point1 = MagicMock()
        point1.payload = {"chunk_id": "c1", "text": "high score", "metadata": {}}
        point1.score = 0.8

        point2 = MagicMock()
        point2.payload = {"chunk_id": "c2", "text": "medium score", "metadata": {}}
        point2.score = 0.4

        point3 = MagicMock()
        point3.payload = {"chunk_id": "c3", "text": "low score", "metadata": {}}
        point3.score = 0.1

        mock_result = MagicMock()
        mock_result.points = [point1, point2, point3]
        mock_qdrant_client.query_points.return_value = mock_result

        retriever = Retriever(
            indexer=indexer, embedder=mock_embedder, top_k=5, score_threshold=0.5
        )
        results = retriever.retrieve("test query")

        assert len(results) == 1
        assert results[0]["chunk_id"] == "c1"
        assert results[0]["score"] == 0.8

    def test_score_threshold_filters_all_results(
        self, mock_embedder, mock_qdrant_client
    ):
        indexer = self._make_mock_indexer(mock_qdrant_client)

        point1 = MagicMock()
        point1.payload = {"chunk_id": "c1", "text": "low score", "metadata": {}}
        point1.score = 0.1

        point2 = MagicMock()
        point2.payload = {"chunk_id": "c2", "text": "also low", "metadata": {}}
        point2.score = 0.2

        mock_result = MagicMock()
        mock_result.points = [point1, point2]
        mock_qdrant_client.query_points.return_value = mock_result

        retriever = Retriever(
            indexer=indexer, embedder=mock_embedder, top_k=5, score_threshold=0.5
        )
        results = retriever.retrieve("test query")

        assert len(results) == 0

    def test_score_threshold_boundary_inclusive(
        self, mock_embedder, mock_qdrant_client
    ):
        indexer = self._make_mock_indexer(mock_qdrant_client)

        point1 = MagicMock()
        point1.payload = {"chunk_id": "c1", "text": "exact threshold", "metadata": {}}
        point1.score = 0.5

        point2 = MagicMock()
        point2.payload = {"chunk_id": "c2", "text": "below threshold", "metadata": {}}
        point2.score = 0.49

        mock_result = MagicMock()
        mock_result.points = [point1, point2]
        mock_qdrant_client.query_points.return_value = mock_result

        retriever = Retriever(
            indexer=indexer, embedder=mock_embedder, top_k=5, score_threshold=0.5
        )
        results = retriever.retrieve("test query")

        assert len(results) == 1
        assert results[0]["chunk_id"] == "c1"
        assert results[0]["score"] == 0.5
