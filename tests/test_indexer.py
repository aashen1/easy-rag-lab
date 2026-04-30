import json
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from src.exceptions import IndexingError
from src.indexer import VectorIndexer


@pytest.mark.unit
class TestVectorIndexer:
    @patch("src.indexer.QdrantClient")
    def test_create_collection_new(
        self, mock_qdrant_class, mock_qdrant_client, temp_project_dir
    ):
        mock_qdrant_class.return_value = mock_qdrant_client
        indexer = VectorIndexer(
            persist_dir=str(temp_project_dir / "data" / "vector_store")
        )
        indexer.create_collection(vector_size=1024)
        mock_qdrant_client.create_collection.assert_called_once()
        call_kwargs = mock_qdrant_client.create_collection.call_args.kwargs
        assert call_kwargs["collection_name"] == "financial_reports"
        assert call_kwargs["vectors_config"].size == 1024

    @patch("src.indexer.QdrantClient")
    def test_create_collection_exists_no_recreate(
        self, mock_qdrant_class, mock_qdrant_client, temp_project_dir
    ):
        mock_qdrant_class.return_value = mock_qdrant_client
        mock_collection = MagicMock()
        mock_collection.name = "financial_reports"
        mock_qdrant_client.get_collections.return_value.collections = [mock_collection]
        indexer = VectorIndexer(
            persist_dir=str(temp_project_dir / "data" / "vector_store")
        )
        indexer.create_collection(vector_size=1024, recreate=False)
        mock_qdrant_client.delete_collection.assert_not_called()
        mock_qdrant_client.create_collection.assert_not_called()

    @patch("src.indexer.QdrantClient")
    def test_create_collection_exists_recreate(
        self, mock_qdrant_class, mock_qdrant_client, temp_project_dir
    ):
        mock_qdrant_class.return_value = mock_qdrant_client
        mock_collection = MagicMock()
        mock_collection.name = "financial_reports"
        mock_qdrant_client.get_collections.return_value.collections = [mock_collection]
        indexer = VectorIndexer(
            persist_dir=str(temp_project_dir / "data" / "vector_store")
        )
        indexer.create_collection(vector_size=1024, recreate=True)
        mock_qdrant_client.delete_collection.assert_called_once_with(
            "financial_reports"
        )
        mock_qdrant_client.create_collection.assert_called_once()

    @patch("src.indexer.QdrantClient")
    def test_index_chunks_success(
        self, mock_qdrant_class, mock_qdrant_client, temp_project_dir
    ):
        mock_qdrant_class.return_value = mock_qdrant_client
        indexer = VectorIndexer(
            persist_dir=str(temp_project_dir / "data" / "vector_store")
        )
        chunks = [{"chunk_id": "c1", "text": "hello", "metadata": {}}]
        embeddings = np.array([[0.1, 0.2, 0.3]], dtype=np.float32)
        indexer.index_chunks(chunks, embeddings)
        mock_qdrant_client.upsert.assert_called_once()
        upsert_kwargs = mock_qdrant_client.upsert.call_args.kwargs
        assert upsert_kwargs["collection_name"] == "financial_reports"
        assert len(upsert_kwargs["points"]) == 1

    @patch("src.indexer.QdrantClient")
    def test_index_chunks_empty(
        self, mock_qdrant_class, mock_qdrant_client, temp_project_dir
    ):
        mock_qdrant_class.return_value = mock_qdrant_client
        indexer = VectorIndexer(
            persist_dir=str(temp_project_dir / "data" / "vector_store")
        )
        indexer.index_chunks([], np.array([]))
        mock_qdrant_client.upsert.assert_not_called()

    @patch("src.indexer.QdrantClient")
    def test_index_chunks_length_mismatch(
        self, mock_qdrant_class, mock_qdrant_client, temp_project_dir
    ):
        mock_qdrant_class.return_value = mock_qdrant_client
        indexer = VectorIndexer(
            persist_dir=str(temp_project_dir / "data" / "vector_store")
        )
        chunks = [{"text": "hello"}]
        embeddings = np.array([[0.1], [0.2]], dtype=np.float32)
        with pytest.raises(IndexingError, match="does not match"):
            indexer.index_chunks(chunks, embeddings)

    @patch("src.indexer.QdrantClient")
    def test_build_index_dir_not_exists(
        self, mock_qdrant_class, mock_qdrant_client, temp_project_dir
    ):
        mock_qdrant_class.return_value = mock_qdrant_client
        indexer = VectorIndexer(
            persist_dir=str(temp_project_dir / "data" / "vector_store")
        )
        with pytest.raises(IndexingError):
            indexer.build_index("/nonexistent/path", embedder=MagicMock())

    @patch("src.indexer.QdrantClient")
    def test_build_index_source_filter(
        self, mock_qdrant_class, mock_qdrant_client, temp_project_dir
    ):
        mock_qdrant_class.return_value = mock_qdrant_client
        indexer = VectorIndexer(
            persist_dir=str(temp_project_dir / "data" / "vector_store")
        )
        chunks_dir = temp_project_dir / "data" / "chunks"
        file_a = chunks_dir / "report_a.jsonl"
        file_b = chunks_dir / "report_b.jsonl"
        chunk_a = {"chunk_id": "c1", "text": "content a", "metadata": {}}
        with open(file_a, "w", encoding="utf-8") as f:
            f.write(json.dumps(chunk_a) + "\n")
        chunk_b = {"chunk_id": "c2", "text": "content b", "metadata": {}}
        with open(file_b, "w", encoding="utf-8") as f:
            f.write(json.dumps(chunk_b) + "\n")
        mock_embedder_inst = MagicMock()
        mock_embedder_inst.get_embedding_dimension.return_value = 1024
        mock_embedder_inst.embed_texts.return_value = np.random.randn(1, 1024).astype(
            np.float32
        )
        indexer.build_index(
            chunks_dir=str(chunks_dir),
            embedder=mock_embedder_inst,
            source_filter={"report_a.jsonl"},
        )
        mock_embedder_inst.embed_texts.assert_called_once()
        texts_arg = mock_embedder_inst.embed_texts.call_args[0][0]
        assert len(texts_arg) == 1
        assert texts_arg[0] == "content a"

    @patch("src.indexer.QdrantClient")
    def test_get_collection_info(
        self, mock_qdrant_class, mock_qdrant_client, temp_project_dir
    ):
        mock_qdrant_class.return_value = mock_qdrant_client
        indexer = VectorIndexer(
            persist_dir=str(temp_project_dir / "data" / "vector_store")
        )
        info = indexer.get_collection_info()
        assert info is not None
        assert info["points_count"] == 100
        assert info["status"] == "green"

    @patch("src.indexer.QdrantClient")
    def test_delete_collection(
        self, mock_qdrant_class, mock_qdrant_client, temp_project_dir
    ):
        mock_qdrant_class.return_value = mock_qdrant_client
        indexer = VectorIndexer(
            persist_dir=str(temp_project_dir / "data" / "vector_store")
        )
        indexer.delete_collection()
        mock_qdrant_client.delete_collection.assert_called_once_with(
            "financial_reports"
        )

    @patch("src.indexer.QdrantClient")
    def test_close(self, mock_qdrant_class, mock_qdrant_client, temp_project_dir):
        mock_qdrant_class.return_value = mock_qdrant_client
        indexer = VectorIndexer(
            persist_dir=str(temp_project_dir / "data" / "vector_store")
        )
        indexer.close()
        mock_qdrant_client.close.assert_called_once()

    @patch("src.indexer.QdrantClient")
    def test_get_collection_info_error(
        self, mock_qdrant_class, mock_qdrant_client, temp_project_dir
    ):
        mock_qdrant_class.return_value = mock_qdrant_client
        mock_qdrant_client.get_collection.side_effect = Exception(
            "Collection not found"
        )
        indexer = VectorIndexer(
            persist_dir=str(temp_project_dir / "data" / "vector_store")
        )
        info = indexer.get_collection_info()
        assert info is None

    @patch("src.indexer.QdrantClient")
    def test_build_index_corrupted_jsonl(
        self, mock_qdrant_class, mock_qdrant_client, temp_project_dir
    ):
        mock_qdrant_class.return_value = mock_qdrant_client
        chunks_dir = temp_project_dir / "data" / "chunks"
        bad_file = chunks_dir / "corrupted.jsonl"
        with open(bad_file, "w", encoding="utf-8") as f:
            f.write("not valid json\n")
        good_file = chunks_dir / "valid.jsonl"
        with open(good_file, "w", encoding="utf-8") as f:
            f.write(
                json.dumps({"chunk_id": "c1", "text": "valid", "metadata": {}}) + "\n"
            )
        mock_embedder_inst = MagicMock()
        mock_embedder_inst.get_embedding_dimension.return_value = 1024
        mock_embedder_inst.embed_texts.return_value = np.ones(
            (1, 1024), dtype=np.float32
        )
        indexer = VectorIndexer(
            persist_dir=str(temp_project_dir / "data" / "vector_store")
        )
        indexer.build_index(chunks_dir=str(chunks_dir), embedder=mock_embedder_inst)
        mock_embedder_inst.embed_texts.assert_called_once()
        texts_arg = mock_embedder_inst.embed_texts.call_args[0][0]
        assert len(texts_arg) == 1
        assert texts_arg[0] == "valid"

    @patch("src.indexer.QdrantClient")
    def test_init_client_failure_raises_indexing_error(
        self, mock_qdrant_class, temp_project_dir
    ):
        mock_qdrant_class.side_effect = RuntimeError("Qdrant init failed")
        with pytest.raises(IndexingError, match="Failed to initialize Qdrant client"):
            VectorIndexer(persist_dir=str(temp_project_dir / "data" / "vector_store"))

    @patch("src.indexer.QdrantClient")
    def test_create_collection_failure_raises_indexing_error(
        self, mock_qdrant_class, mock_qdrant_client, temp_project_dir
    ):
        mock_qdrant_class.return_value = mock_qdrant_client
        mock_qdrant_client.get_collections.side_effect = RuntimeError("RPC failed")
        indexer = VectorIndexer(
            persist_dir=str(temp_project_dir / "data" / "vector_store")
        )
        with pytest.raises(IndexingError, match="Failed to create collection"):
            indexer.create_collection(vector_size=1024)

    @patch("src.indexer.QdrantClient")
    def test_index_chunks_upsert_failure_raises_indexing_error(
        self, mock_qdrant_class, mock_qdrant_client, temp_project_dir
    ):
        mock_qdrant_class.return_value = mock_qdrant_client
        mock_qdrant_client.upsert.side_effect = RuntimeError("Upsert failed")
        indexer = VectorIndexer(
            persist_dir=str(temp_project_dir / "data" / "vector_store")
        )
        chunks = [{"chunk_id": "c1", "text": "hello", "metadata": {}}]
        embeddings = np.array([[0.1, 0.2, 0.3]], dtype=np.float32)
        with pytest.raises(IndexingError, match="Failed to index chunks"):
            indexer.index_chunks(chunks, embeddings)

    @patch("src.indexer.QdrantClient")
    def test_delete_collection_failure_raises_indexing_error(
        self, mock_qdrant_class, mock_qdrant_client, temp_project_dir
    ):
        mock_qdrant_class.return_value = mock_qdrant_client
        mock_qdrant_client.delete_collection.side_effect = RuntimeError("Delete failed")
        indexer = VectorIndexer(
            persist_dir=str(temp_project_dir / "data" / "vector_store")
        )
        with pytest.raises(IndexingError, match="Failed to delete collection"):
            indexer.delete_collection()

    @patch("src.indexer.QdrantClient")
    def test_build_index_embedder_failure(
        self, mock_qdrant_class, mock_qdrant_client, temp_project_dir
    ):
        mock_qdrant_class.return_value = mock_qdrant_client
        chunks_dir = temp_project_dir / "data" / "chunks"
        chunk_file = chunks_dir / "test.jsonl"
        with open(chunk_file, "w", encoding="utf-8") as f:
            f.write(
                json.dumps({"chunk_id": "c1", "text": "hello", "metadata": {}}) + "\n"
            )
        mock_embedder_inst = MagicMock()
        mock_embedder_inst.embed_texts.side_effect = RuntimeError(
            "Embedding API failed"
        )
        indexer = VectorIndexer(
            persist_dir=str(temp_project_dir / "data" / "vector_store")
        )
        with pytest.raises(RuntimeError, match="Embedding API failed"):
            indexer.build_index(chunks_dir=str(chunks_dir), embedder=mock_embedder_inst)

    @patch("src.indexer.QdrantClient")
    def test_build_index_no_jsonl_files(
        self, mock_qdrant_class, mock_qdrant_client, temp_project_dir
    ):
        mock_qdrant_class.return_value = mock_qdrant_client
        chunks_dir = temp_project_dir / "data" / "chunks"
        indexer = VectorIndexer(
            persist_dir=str(temp_project_dir / "data" / "vector_store")
        )
        indexer.build_index(chunks_dir=str(chunks_dir), embedder=MagicMock())
        mock_qdrant_client.create_collection.assert_not_called()


@pytest.mark.unit
class TestVectorIndexerReopen:
    @patch("src.indexer.QdrantClient")
    def test_is_closed_false_initially(
        self, mock_qdrant_class, mock_qdrant_client, temp_project_dir
    ):
        mock_qdrant_class.return_value = mock_qdrant_client
        indexer = VectorIndexer(
            persist_dir=str(temp_project_dir / "data" / "vector_store")
        )
        assert indexer.is_closed() is False

    @patch("src.indexer.QdrantClient")
    def test_is_closed_true_after_close(
        self, mock_qdrant_class, mock_qdrant_client, temp_project_dir
    ):
        mock_qdrant_class.return_value = mock_qdrant_client
        indexer = VectorIndexer(
            persist_dir=str(temp_project_dir / "data" / "vector_store")
        )
        indexer.close()
        assert indexer.is_closed() is True

    @patch("src.indexer.QdrantClient")
    def test_reopen_creates_new_client(
        self, mock_qdrant_class, mock_qdrant_client, temp_project_dir
    ):
        mock_qdrant_class.return_value = mock_qdrant_client
        indexer = VectorIndexer(
            persist_dir=str(temp_project_dir / "data" / "vector_store")
        )
        indexer.close()
        assert indexer.is_closed() is True

        mock_new_client = MagicMock()
        mock_qdrant_class.return_value = mock_new_client
        indexer.reopen()

        assert indexer.is_closed() is False
        assert indexer.client is mock_new_client
        mock_qdrant_class.assert_called_with(
            path=str(temp_project_dir / "data" / "vector_store")
        )

    @patch("src.indexer.QdrantClient")
    def test_reopen_noop_when_not_closed(
        self, mock_qdrant_class, mock_qdrant_client, temp_project_dir
    ):
        mock_qdrant_class.return_value = mock_qdrant_client
        indexer = VectorIndexer(
            persist_dir=str(temp_project_dir / "data" / "vector_store")
        )
        original_client = indexer.client

        indexer.reopen()

        assert indexer.is_closed() is False
        assert indexer.client is original_client
        assert mock_qdrant_class.call_count == 1


@pytest.mark.unit
class TestVectorIndexerRemaining:
    @patch("src.indexer.QdrantClient")
    def test_build_index_source_filter_no_match(
        self, mock_qdrant_class, mock_qdrant_client, temp_project_dir
    ):
        mock_qdrant_class.return_value = mock_qdrant_client
        chunks_dir = temp_project_dir / "data" / "chunks"
        chunk_file = chunks_dir / "report_a.jsonl"
        with open(chunk_file, "w", encoding="utf-8") as f:
            f.write(
                json.dumps({"chunk_id": "c1", "text": "hello", "metadata": {}}) + "\n"
            )
        indexer = VectorIndexer(
            persist_dir=str(temp_project_dir / "data" / "vector_store")
        )
        indexer.build_index(
            chunks_dir=str(chunks_dir),
            embedder=MagicMock(),
            source_filter={"nonexistent.jsonl"},
        )
        mock_qdrant_client.create_collection.assert_not_called()

    @patch("src.indexer.QdrantClient")
    def test_close_without_client_attribute(
        self, mock_qdrant_class, mock_qdrant_client, temp_project_dir
    ):
        mock_qdrant_class.return_value = mock_qdrant_client
        indexer = VectorIndexer(
            persist_dir=str(temp_project_dir / "data" / "vector_store")
        )
        del indexer.client
        indexer.close()

    @patch("src.indexer.QdrantClient")
    def test_close_client_error_logs_warning(
        self, mock_qdrant_class, mock_qdrant_client, temp_project_dir
    ):
        mock_qdrant_class.return_value = mock_qdrant_client
        mock_qdrant_client.close.side_effect = RuntimeError("Close failed")
        indexer = VectorIndexer(
            persist_dir=str(temp_project_dir / "data" / "vector_store")
        )
        indexer.close()

    @patch("src.indexer.QdrantClient")
    def test_index_chunks_missing_text_key_raises_key_error(
        self, mock_qdrant_class, mock_qdrant_client, temp_project_dir
    ):
        mock_qdrant_class.return_value = mock_qdrant_client
        indexer = VectorIndexer(
            persist_dir=str(temp_project_dir / "data" / "vector_store")
        )
        chunks = [{"chunk_id": "c1"}]
        embeddings = np.array([[0.1, 0.2, 0.3]], dtype=np.float32)
        with pytest.raises(IndexingError, match="Failed to index chunks"):
            indexer.index_chunks(chunks, embeddings)

    @patch("src.indexer.QdrantClient")
    def test_build_index_all_corrupted_jsonl(
        self, mock_qdrant_class, mock_qdrant_client, temp_project_dir
    ):
        mock_qdrant_class.return_value = mock_qdrant_client
        chunks_dir = temp_project_dir / "data" / "chunks"
        bad_file = chunks_dir / "bad.jsonl"
        with open(bad_file, "w", encoding="utf-8") as f:
            f.write("not valid json\n")
        indexer = VectorIndexer(
            persist_dir=str(temp_project_dir / "data" / "vector_store")
        )
        indexer.build_index(chunks_dir=str(chunks_dir), embedder=MagicMock())
        mock_qdrant_client.create_collection.assert_not_called()
