from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.exceptions import RetrievalError
from src.pipeline import RAGPipeline


def _make_config():
    return {
        "embedding": {"model_name": "test-model", "device": "cpu"},
        "vector_store": {
            "persist_dir": "/tmp/vs",
            "collection_name": "default_col",
            "distance": "Cosine",
        },
        "retrieval": {"top_k": 5},
        "generation": {"system_prompt": None},
        "logging": {
            "level": "INFO",
            "log_dir": "/tmp/logs",
            "format": "",
            "rotation": "10 MB",
            "retention": "7 days",
        },
    }


def _make_llm_config():
    return {
        "model_name": "test-llm",
        "api_key": "key",
        "base_url": "url",
        "temperature": 0.0,
        "max_tokens": 1024,
    }


@pytest.mark.unit
class TestRAGPipeline:
    @patch("src.pipeline.Generator")
    @patch("src.pipeline.Retriever")
    @patch("src.pipeline.VectorIndexer")
    @patch("src.pipeline.Embedder")
    @patch("src.pipeline.get_llm_config")
    @patch("src.pipeline.load_config")
    def test_init_without_meal(
        self,
        mock_load_config,
        mock_get_llm_config,
        mock_embedder,
        mock_indexer,
        mock_retriever,
        mock_generator,
    ):
        mock_load_config.return_value = _make_config()
        mock_get_llm_config.return_value = _make_llm_config()

        pipeline = RAGPipeline(config="dummy.yaml")

        mock_embedder.assert_called_once_with(
            model_name="test-model", device="cpu", query_instruction=None
        )
        mock_indexer.assert_not_called()
        mock_retriever.assert_called_once_with(
            indexer=None,
            embedder=mock_embedder.return_value,
            top_k=5,
            score_threshold=0,
        )
        mock_generator.assert_called_once_with(
            model_name="test-llm",
            api_key="key",
            base_url="url",
            temperature=0.0,
            max_tokens=1024,
            token_tracker=pipeline.token_tracker,
            system_prompt=None,
            max_context_tokens=None,
        )
        assert pipeline.meal_name is None
        assert pipeline.meal_config is None
        assert pipeline.indexer is None

    @patch("src.pipeline.Generator")
    @patch("src.pipeline.Retriever")
    @patch("src.pipeline.VectorIndexer")
    @patch("src.pipeline.Embedder")
    @patch("src.pipeline.get_llm_config")
    @patch("src.pipeline.load_config")
    def test_init_with_meal(
        self,
        mock_load_config,
        mock_get_llm_config,
        mock_embedder,
        mock_indexer,
        mock_retriever,
        mock_generator,
    ):
        mock_load_config.return_value = _make_config()
        mock_get_llm_config.return_value = _make_llm_config()

        mock_meal_config = MagicMock()
        mock_meal_config.collection_name = "meal_col_123"
        mock_meal_config.data_id = "abc123def456"

        with patch("src.meal.MealManager") as mock_meal_mgr_cls:
            mock_meal_mgr = mock_meal_mgr_cls.return_value
            mock_meal_mgr.load_meal.return_value = mock_meal_config

            pipeline = RAGPipeline(config="dummy.yaml", meal_name="test_meal")

            mock_meal_mgr.load_meal.assert_called_once_with("test_meal")

        mock_indexer.assert_not_called()
        assert pipeline.meal_name == "test_meal"
        assert pipeline.meal_config is mock_meal_config
        assert pipeline.indexer is None

    @patch("src.pipeline.Generator")
    @patch("src.pipeline.Retriever")
    @patch("src.pipeline.VectorIndexer")
    @patch("src.pipeline.Embedder")
    @patch("src.pipeline.get_llm_config")
    @patch("src.pipeline.load_config")
    def test_query_full_flow(
        self,
        mock_load_config,
        mock_get_llm_config,
        mock_embedder,
        mock_indexer,
        mock_retriever,
        mock_generator,
    ):
        mock_load_config.return_value = _make_config()
        mock_get_llm_config.return_value = _make_llm_config()

        mock_retriever_instance = mock_retriever.return_value
        mock_retriever_instance.retrieve.return_value = [
            {
                "text": "Revenue was 100 billion.",
                "score": 0.95,
                "metadata": {"source": "report_2023.pdf"},
            },
            {
                "text": "Profit increased by 10%.",
                "score": 0.85,
                "metadata": {"source": "report_2024.pdf"},
            },
        ]

        mock_generator_instance = mock_generator.return_value
        mock_generator_instance.generate.return_value = "Revenue was 100 billion."
        mock_generator_instance.last_token_usage = None

        pipeline = RAGPipeline(config="dummy.yaml")
        result = pipeline.query("What is the revenue?")

        mock_retriever_instance.retrieve.assert_called_once_with(
            "What is the revenue?", top_k=5
        )
        mock_generator_instance.generate.assert_called_once_with(
            "What is the revenue?",
            ["Revenue was 100 billion.", "Profit increased by 10%."],
            sources=["report_2023.pdf", "report_2024.pdf"],
        )
        assert result["question"] == "What is the revenue?"
        assert result["answer"] == "Revenue was 100 billion."
        assert result["contexts"] == [
            "Revenue was 100 billion.",
            "Profit increased by 10%.",
        ]
        assert result["scores"] == [0.95, 0.85]
        assert result["sources"] == ["report_2023.pdf", "report_2024.pdf"]

    @patch("src.pipeline.Generator")
    @patch("src.pipeline.Retriever")
    @patch("src.pipeline.VectorIndexer")
    @patch("src.pipeline.Embedder")
    @patch("src.pipeline.get_llm_config")
    @patch("src.pipeline.load_config")
    def test_query_invalid_input(
        self,
        mock_load_config,
        mock_get_llm_config,
        mock_embedder,
        mock_indexer,
        mock_retriever,
        mock_generator,
    ):
        mock_load_config.return_value = _make_config()
        mock_get_llm_config.return_value = _make_llm_config()

        pipeline = RAGPipeline(config="dummy.yaml")

        with pytest.raises(RetrievalError, match="Question must be a non-empty string"):
            pipeline.query("")

        with pytest.raises(RetrievalError, match="Question must be a non-empty string"):
            pipeline.query(123)

    @patch("src.pipeline.Generator")
    @patch("src.pipeline.Retriever")
    @patch("src.pipeline.VectorIndexer")
    @patch("src.pipeline.Embedder")
    @patch("src.pipeline.get_llm_config")
    @patch("src.pipeline.load_config")
    def test_use_meal_switch(
        self,
        mock_load_config,
        mock_get_llm_config,
        mock_embedder,
        mock_indexer,
        mock_retriever,
        mock_generator,
    ):
        mock_load_config.return_value = _make_config()
        mock_get_llm_config.return_value = _make_llm_config()

        pipeline = RAGPipeline(config="dummy.yaml")

        assert pipeline.meal_name is None

        mock_new_meal_config = MagicMock()
        mock_new_meal_config.collection_name = "new_meal_col_456"
        mock_new_meal_config.data_id = "xyz789abc012"

        with patch("src.meal.MealManager") as mock_meal_mgr_cls:
            mock_meal_mgr = mock_meal_mgr_cls.return_value
            mock_meal_mgr.load_meal.return_value = mock_new_meal_config

            result = pipeline.use_meal("new_meal")

            mock_meal_mgr.load_meal.assert_called_once_with("new_meal")

        assert pipeline.meal_name == "new_meal"
        assert pipeline.meal_config is mock_new_meal_config
        assert result is mock_new_meal_config

        mock_indexer.assert_called_with(
            persist_dir="/tmp/vs",
            collection_name="new_meal_col_456",
            distance="Cosine",
        )
        mock_retriever.assert_called_with(
            indexer=mock_indexer.return_value,
            embedder=mock_embedder.return_value,
            top_k=5,
            score_threshold=0,
        )

    @patch("src.pipeline.Generator")
    @patch("src.pipeline.Retriever")
    @patch("src.pipeline.VectorIndexer")
    @patch("src.pipeline.Embedder")
    @patch("src.pipeline.get_llm_config")
    @patch("src.pipeline.load_config")
    def test_close_calls_indexer_close(
        self,
        mock_load_config,
        mock_get_llm_config,
        mock_embedder,
        mock_indexer,
        mock_retriever,
        mock_generator,
    ):
        mock_load_config.return_value = _make_config()
        mock_get_llm_config.return_value = _make_llm_config()

        pipeline = RAGPipeline(config="dummy.yaml")
        pipeline.close()

        mock_indexer.return_value.close.assert_not_called()

    @patch("src.pipeline.Generator")
    @patch("src.pipeline.Retriever")
    @patch("src.pipeline.VectorIndexer")
    @patch("src.pipeline.Embedder")
    @patch("src.pipeline.get_llm_config")
    @patch("src.pipeline.load_config")
    def test_close_calls_indexer_close_when_indexer_exists(
        self,
        mock_load_config,
        mock_get_llm_config,
        mock_embedder,
        mock_indexer,
        mock_retriever,
        mock_generator,
    ):
        mock_load_config.return_value = _make_config()
        mock_get_llm_config.return_value = _make_llm_config()

        pipeline = RAGPipeline(config="dummy.yaml")
        pipeline.indexer = mock_indexer.return_value
        pipeline.close()

        mock_indexer.return_value.close.assert_called_once()

    @patch("src.pipeline.Generator")
    @patch("src.pipeline.Retriever")
    @patch("src.pipeline.VectorIndexer")
    @patch("src.pipeline.Embedder")
    @patch("src.pipeline.get_llm_config")
    @patch("src.pipeline.load_config")
    def test_context_manager_calls_close(
        self,
        mock_load_config,
        mock_get_llm_config,
        mock_embedder,
        mock_indexer,
        mock_retriever,
        mock_generator,
    ):
        mock_load_config.return_value = _make_config()
        mock_get_llm_config.return_value = _make_llm_config()

        with RAGPipeline(config="dummy.yaml") as pipeline:
            pipeline.indexer = mock_indexer.return_value

        mock_indexer.return_value.close.assert_called_once()

    @patch("src.pipeline.Generator")
    @patch("src.pipeline.Retriever")
    @patch("src.pipeline.VectorIndexer")
    @patch("src.pipeline.Embedder")
    @patch("src.pipeline.get_llm_config")
    @patch("src.pipeline.load_config")
    def test_use_meal_closes_old_indexer(
        self,
        mock_load_config,
        mock_get_llm_config,
        mock_embedder,
        mock_indexer,
        mock_retriever,
        mock_generator,
    ):
        mock_load_config.return_value = _make_config()
        mock_get_llm_config.return_value = _make_llm_config()

        pipeline = RAGPipeline(config="dummy.yaml")
        old_indexer = MagicMock()
        pipeline.indexer = old_indexer

        mock_new_meal_config = MagicMock()
        mock_new_meal_config.collection_name = "new_meal_col_789"
        mock_new_meal_config.data_id = "new_data_id"

        with patch("src.meal.MealManager") as mock_meal_mgr_cls:
            mock_meal_mgr = mock_meal_mgr_cls.return_value
            mock_meal_mgr.load_meal.return_value = mock_new_meal_config

            pipeline.use_meal("new_meal")

        old_indexer.close.assert_called_once()

    @patch("src.pipeline.Generator")
    @patch("src.pipeline.Retriever")
    @patch("src.pipeline.VectorIndexer")
    @patch("src.pipeline.Embedder")
    @patch("src.pipeline.get_llm_config")
    @patch("src.pipeline.load_config")
    def test_build_index_passes_parser_options(
        self,
        mock_load_config,
        mock_get_llm_config,
        mock_embedder,
        mock_indexer,
        mock_retriever,
        mock_generator,
    ):
        config = _make_config()
        config["parser"] = {
            "input_dir": "/tmp/parser_in",
            "output_dir": "/tmp/parser_out",
            "pymupdf4llm": {"page_chunks": True, "table_strategy": "text"},
        }
        config["chunker"] = {
            "strategy": "fixed",
            "input_dir": "/tmp/chunker_in",
            "output_dir": "/tmp/chunker_out",
            "chunk_size": 500,
            "chunk_overlap": 50,
        }
        config["embedding"]["batch_size"] = 32
        mock_load_config.return_value = config
        mock_get_llm_config.return_value = _make_llm_config()

        pipeline = RAGPipeline(config="dummy.yaml")

        with (
            patch("src.pipeline.parse_all_pdfs_unified") as mock_parse,
            patch("src.chunker.process_parsed_files_page_aware") as mock_page_aware,
            patch("src.meal.create_artifact_cache") as mock_cache_cls,
            patch("src.meal.compute_data_id", return_value="fake_data_id"),
            patch(
                "src.meal.compute_parser_config_hash",
                return_value="fake_ph",
            ),
            patch(
                "src.meal.compute_chunker_config_hash",
                return_value="fake_ch",
            ),
            patch("src.meal.compute_file_sha256", return_value="sha"),
        ):
            mock_cache = MagicMock()
            mock_cache_cls.return_value = mock_cache
            mock_cache.artifacts_dir = Path("data/artifacts")
            mock_cache.raw_dir = Path("data/raw")
            mock_cache.get_parsed_dir.return_value = Path("/tmp/parsed")
            mock_cache.get_chunks_dir.return_value = Path("/tmp/chunks")
            mock_parse.return_value = []
            mock_page_aware.return_value = []
            pipeline.build_index()

        mock_parse.assert_called_once_with(
            input_dir="/tmp/parser_in",
            artifacts_dir=str(Path("data/artifacts")),
            force=False,
            parser_options={"page_chunks": True, "table_strategy": "text"},
        )
        mock_page_aware.assert_called_once_with(
            input_dir=str(Path("/tmp/parsed")),
            output_dir=str(Path("/tmp/chunks")),
            chunk_size=500,
            overlap=50,
            encoding_name="cl100k_base",
            source_filter=None,
            model_name="test-model",
            cross_page_overlap=0,
        )

    @patch("src.pipeline.Generator")
    @patch("src.pipeline.Retriever")
    @patch("src.pipeline.VectorIndexer")
    @patch("src.pipeline.Embedder")
    @patch("src.pipeline.get_llm_config")
    @patch("src.pipeline.load_config")
    def test_build_index_parser_options_none_when_missing(
        self,
        mock_load_config,
        mock_get_llm_config,
        mock_embedder,
        mock_indexer,
        mock_retriever,
        mock_generator,
    ):
        config = _make_config()
        config["parser"] = {
            "input_dir": "/tmp/parser_in",
            "output_dir": "/tmp/parser_out",
        }
        config["chunker"] = {
            "strategy": "fixed",
            "input_dir": "/tmp/chunker_in",
            "output_dir": "/tmp/chunker_out",
            "chunk_size": 500,
            "chunk_overlap": 50,
        }
        config["embedding"]["batch_size"] = 32
        mock_load_config.return_value = config
        mock_get_llm_config.return_value = _make_llm_config()

        pipeline = RAGPipeline(config="dummy.yaml")

        with (
            patch("src.pipeline.parse_all_pdfs_unified") as mock_parse,
            patch("src.pipeline.process_parsed_files") as mock_chunk,
            patch("src.meal.create_artifact_cache") as mock_cache_cls,
            patch("src.meal.compute_data_id", return_value="fake_data_id"),
            patch(
                "src.meal.compute_parser_config_hash",
                return_value="fake_ph",
            ),
            patch(
                "src.meal.compute_chunker_config_hash",
                return_value="fake_ch",
            ),
            patch("src.meal.compute_file_sha256", return_value="sha"),
        ):
            mock_cache = MagicMock()
            mock_cache_cls.return_value = mock_cache
            mock_cache.artifacts_dir = Path("data/artifacts")
            mock_cache.raw_dir = Path("data/raw")
            mock_cache.get_parsed_dir.return_value = Path("/tmp/parsed")
            mock_cache.get_chunks_dir.return_value = Path("/tmp/chunks")
            mock_parse.return_value = []
            mock_chunk.return_value = []
            pipeline.build_index()

        mock_parse.assert_called_once_with(
            input_dir="/tmp/parser_in",
            artifacts_dir=str(Path("data/artifacts")),
            force=False,
            parser_options=None,
        )

    @patch("src.pipeline.Generator")
    @patch("src.pipeline.Retriever")
    @patch("src.pipeline.VectorIndexer")
    @patch("src.pipeline.Embedder")
    @patch("src.pipeline.get_llm_config")
    @patch("src.pipeline.load_config")
    def test_build_index_page_aware_chunking(
        self,
        mock_load_config,
        mock_get_llm_config,
        mock_embedder,
        mock_indexer,
        mock_retriever,
        mock_generator,
    ):
        config = _make_config()
        config["parser"] = {
            "input_dir": "/tmp/parser_in",
            "output_dir": "/tmp/parser_out",
            "pymupdf4llm": {"page_chunks": True},
        }
        config["chunker"] = {
            "strategy": "fixed",
            "input_dir": "/tmp/chunker_in",
            "output_dir": "/tmp/chunker_out",
            "chunk_size": 500,
            "chunk_overlap": 50,
        }
        config["embedding"]["batch_size"] = 32
        mock_load_config.return_value = config
        mock_get_llm_config.return_value = _make_llm_config()

        pipeline = RAGPipeline(config="dummy.yaml")

        parse_results = [
            {"output": "/tmp/parser_out/report_2023.pages.json", "status": "ok"},
            {"output": "/tmp/parser_out/report_2024.pages.json", "status": "ok"},
        ]

        with (
            patch("src.pipeline.parse_all_pdfs_unified") as mock_parse,
            patch("src.chunker.process_parsed_files_page_aware") as mock_page_aware,
            patch("src.pipeline.process_parsed_files") as mock_chunk,
            patch("src.meal.create_artifact_cache") as mock_cache_cls,
            patch("src.meal.compute_data_id", return_value="fake_data_id"),
            patch(
                "src.meal.compute_parser_config_hash",
                return_value="fake_ph",
            ),
            patch(
                "src.meal.compute_chunker_config_hash",
                return_value="fake_ch",
            ),
            patch("src.meal.compute_file_sha256", return_value="sha"),
        ):
            mock_cache = MagicMock()
            mock_cache_cls.return_value = mock_cache
            mock_cache.artifacts_dir = Path("data/artifacts")
            mock_cache.raw_dir = Path("data/raw")
            mock_cache.get_parsed_dir.return_value = Path("/tmp/parsed")
            mock_cache.get_chunks_dir.return_value = Path("/tmp/chunks")
            mock_parse.return_value = parse_results
            mock_page_aware.return_value = [
                {"output": "/tmp/chunks/report_2023.jsonl", "status": "ok"},
            ]
            mock_chunk.return_value = []
            pipeline.build_index()

        mock_page_aware.assert_called_once_with(
            input_dir=str(Path("/tmp/parsed")),
            output_dir=str(Path("/tmp/chunks")),
            chunk_size=500,
            overlap=50,
            encoding_name="cl100k_base",
            source_filter=None,
            model_name="test-model",
            cross_page_overlap=0,
        )
        mock_chunk.assert_not_called()

    @patch("src.pipeline.Generator")
    @patch("src.pipeline.Retriever")
    @patch("src.pipeline.VectorIndexer")
    @patch("src.pipeline.Embedder")
    @patch("src.pipeline.get_llm_config")
    @patch("src.pipeline.load_config")
    def test_build_index_regular_chunking_when_no_page_chunks(
        self,
        mock_load_config,
        mock_get_llm_config,
        mock_embedder,
        mock_indexer,
        mock_retriever,
        mock_generator,
    ):
        config = _make_config()
        config["parser"] = {
            "input_dir": "/tmp/parser_in",
            "output_dir": "/tmp/parser_out",
            "pymupdf4llm": {"page_chunks": False},
        }
        config["chunker"] = {
            "strategy": "fixed",
            "input_dir": "/tmp/chunker_in",
            "output_dir": "/tmp/chunker_out",
            "chunk_size": 500,
            "chunk_overlap": 50,
        }
        config["embedding"]["batch_size"] = 32
        mock_load_config.return_value = config
        mock_get_llm_config.return_value = _make_llm_config()

        pipeline = RAGPipeline(config="dummy.yaml")

        with (
            patch("src.pipeline.parse_all_pdfs_unified") as mock_parse,
            patch("src.pipeline.process_parsed_files") as mock_chunk,
            patch("src.meal.create_artifact_cache") as mock_cache_cls,
            patch("src.meal.compute_data_id", return_value="fake_data_id"),
            patch(
                "src.meal.compute_parser_config_hash",
                return_value="fake_ph",
            ),
            patch(
                "src.meal.compute_chunker_config_hash",
                return_value="fake_ch",
            ),
            patch("src.meal.compute_file_sha256", return_value="sha"),
        ):
            mock_cache = MagicMock()
            mock_cache_cls.return_value = mock_cache
            mock_cache.artifacts_dir = Path("data/artifacts")
            mock_cache.raw_dir = Path("data/raw")
            mock_cache.get_parsed_dir.return_value = Path("/tmp/parsed")
            mock_cache.get_chunks_dir.return_value = Path("/tmp/chunks")
            mock_parse.return_value = []
            mock_chunk.return_value = []
            pipeline.build_index()

        mock_chunk.assert_called_once_with(
            input_dir=str(Path("/tmp/parsed")),
            output_dir=str(Path("/tmp/chunks")),
            chunk_size=500,
            overlap=50,
            encoding_name="cl100k_base",
            source_filter=None,
            model_name="test-model",
        )

    @patch("src.pipeline.Generator")
    @patch("src.pipeline.Retriever")
    @patch("src.pipeline.VectorIndexer")
    @patch("src.pipeline.Embedder")
    @patch("src.pipeline.get_llm_config")
    @patch("src.pipeline.load_config")
    def test_query_with_config_overrides_top_k(
        self,
        mock_load_config,
        mock_get_llm_config,
        mock_embedder,
        mock_indexer,
        mock_retriever,
        mock_generator,
    ):
        mock_load_config.return_value = _make_config()
        mock_get_llm_config.return_value = _make_llm_config()

        mock_retriever_instance = mock_retriever.return_value
        mock_retriever_instance.retrieve.return_value = [
            {
                "text": "Revenue was 100 billion.",
                "score": 0.95,
                "metadata": {"source": "report_2023.pdf"},
            },
        ]

        mock_generator_instance = mock_generator.return_value
        mock_generator_instance.generate.return_value = "Revenue was 100 billion."
        mock_generator_instance.last_token_usage = None

        pipeline = RAGPipeline(config="dummy.yaml")
        result = pipeline.query(
            "What is the revenue?",
            config_overrides={"retrieval": {"top_k": 3}},
        )

        assert result["question"] == "What is the revenue?"
        mock_retriever_instance.retrieve.assert_called_once_with(
            "What is the revenue?", top_k=3
        )

    @patch("src.pipeline.Generator")
    @patch("src.pipeline.Retriever")
    @patch("src.pipeline.VectorIndexer")
    @patch("src.pipeline.Embedder")
    @patch("src.pipeline.get_llm_config")
    @patch("src.pipeline.load_config")
    def test_query_with_config_overrides_none_is_noop(
        self,
        mock_load_config,
        mock_get_llm_config,
        mock_embedder,
        mock_indexer,
        mock_retriever,
        mock_generator,
    ):
        mock_load_config.return_value = _make_config()
        mock_get_llm_config.return_value = _make_llm_config()

        mock_retriever_instance = mock_retriever.return_value
        mock_retriever_instance.retrieve.return_value = [
            {
                "text": "Revenue was 100 billion.",
                "score": 0.95,
                "metadata": {"source": "report_2023.pdf"},
            },
        ]

        mock_generator_instance = mock_generator.return_value
        mock_generator_instance.generate.return_value = "Revenue was 100 billion."
        mock_generator_instance.last_token_usage = None

        pipeline = RAGPipeline(config="dummy.yaml")
        result = pipeline.query("What is the revenue?", config_overrides=None)

        assert result["question"] == "What is the revenue?"
        mock_retriever_instance.retrieve.assert_called_once_with(
            "What is the revenue?", top_k=5
        )

    @patch("src.pipeline.Generator")
    @patch("src.pipeline.Retriever")
    @patch("src.pipeline.VectorIndexer")
    @patch("src.pipeline.Embedder")
    @patch("src.pipeline.get_llm_config")
    @patch("src.pipeline.load_config")
    def test_query_with_config_overrides_reranker_enabled(
        self,
        mock_load_config,
        mock_get_llm_config,
        mock_embedder,
        mock_indexer,
        mock_retriever,
        mock_generator,
    ):
        mock_load_config.return_value = _make_config()
        mock_get_llm_config.return_value = _make_llm_config()

        mock_retriever_instance = mock_retriever.return_value
        mock_retriever_instance.retrieve.return_value = [
            {
                "text": "Revenue was 100 billion.",
                "score": 0.95,
                "metadata": {"source": "report_2023.pdf"},
                "chunk_id": "c1",
            },
        ]

        mock_generator_instance = mock_generator.return_value
        mock_generator_instance.generate.return_value = "Revenue was 100 billion."
        mock_generator_instance.last_token_usage = None

        pipeline = RAGPipeline(config="dummy.yaml")
        assert pipeline.reranker is None

        with patch("src.pipeline.Reranker") as mock_reranker_cls:
            mock_reranker_instance = mock_reranker_cls.return_value
            mock_reranker_instance.rerank.return_value = [
                {
                    "text": "Revenue was 100 billion.",
                    "score": 0.99,
                    "metadata": {"source": "report_2023.pdf"},
                    "chunk_id": "c1",
                },
            ]

            pipeline.query(
                "What is the revenue?",
                config_overrides={
                    "retrieval": {"reranker": {"enabled": True}},
                },
            )

            mock_reranker_cls.assert_called_once()
            mock_reranker_instance.rerank.assert_called_once()

    @patch("src.pipeline.Generator")
    @patch("src.pipeline.Retriever")
    @patch("src.pipeline.VectorIndexer")
    @patch("src.pipeline.Embedder")
    @patch("src.pipeline.get_llm_config")
    @patch("src.pipeline.load_config")
    def test_query_with_config_overrides_disables_rewrite(
        self,
        mock_load_config,
        mock_get_llm_config,
        mock_embedder,
        mock_indexer,
        mock_retriever,
        mock_generator,
    ):
        config = _make_config()
        config["retrieval"]["query_rewrite"] = {
            "enabled": True,
            "strategy": "hyde",
        }
        mock_load_config.return_value = config
        mock_get_llm_config.return_value = _make_llm_config()

        mock_retriever_instance = mock_retriever.return_value
        mock_retriever_instance.retrieve.return_value = [
            {
                "text": "Revenue was 100 billion.",
                "score": 0.95,
                "metadata": {"source": "report_2023.pdf"},
            },
        ]

        mock_generator_instance = mock_generator.return_value
        mock_generator_instance.generate.return_value = "Revenue was 100 billion."
        mock_generator_instance.last_token_usage = None

        pipeline = RAGPipeline(config="dummy.yaml")

        with patch.object(pipeline, "_get_rewrite_strategy") as mock_get_rw:
            pipeline.query(
                "What is the revenue?",
                config_overrides={
                    "retrieval": {"query_rewrite": {"enabled": False}},
                },
            )
            mock_get_rw.assert_not_called()

    @patch("src.pipeline.Generator")
    @patch("src.pipeline.Retriever")
    @patch("src.pipeline.VectorIndexer")
    @patch("src.pipeline.Embedder")
    @patch("src.pipeline.get_llm_config")
    @patch("src.pipeline.load_config")
    def test_query_with_config_overrides_bm25_method(
        self,
        mock_load_config,
        mock_get_llm_config,
        mock_embedder,
        mock_indexer,
        mock_retriever,
        mock_generator,
    ):
        mock_load_config.return_value = _make_config()
        mock_get_llm_config.return_value = _make_llm_config()

        mock_generator_instance = mock_generator.return_value
        mock_generator_instance.generate.return_value = "Revenue was 100 billion."
        mock_generator_instance.last_token_usage = None

        pipeline = RAGPipeline(config="dummy.yaml")

        with (
            patch.object(pipeline, "_ensure_bm25_index") as mock_ensure_bm25,
            patch("src.pipeline.BM25RetrievalStrategy") as mock_bm25_strategy_cls,
        ):
            mock_bm25_strategy = MagicMock()
            mock_bm25_strategy.retrieve.return_value = MagicMock(
                chunks=[
                    {
                        "text": "Revenue was 100 billion.",
                        "score": 0.9,
                        "metadata": {"source": "report_2023.pdf"},
                        "chunk_id": "c1",
                    },
                ]
            )
            mock_bm25_strategy_cls.return_value = mock_bm25_strategy

            pipeline.query(
                "What is the revenue?",
                config_overrides={"retrieval": {"method": "bm25"}},
            )

            mock_ensure_bm25.assert_called_once()
            mock_bm25_strategy_cls.assert_called_once_with(pipeline.bm25_retriever)

    @patch("src.pipeline.Generator")
    @patch("src.pipeline.Retriever")
    @patch("src.pipeline.VectorIndexer")
    @patch("src.pipeline.Embedder")
    @patch("src.pipeline.get_llm_config")
    @patch("src.pipeline.load_config")
    def test_query_with_config_overrides_does_not_mutate_base_config(
        self,
        mock_load_config,
        mock_get_llm_config,
        mock_embedder,
        mock_indexer,
        mock_retriever,
        mock_generator,
    ):
        mock_load_config.return_value = _make_config()
        mock_get_llm_config.return_value = _make_llm_config()

        mock_retriever_instance = mock_retriever.return_value
        mock_retriever_instance.retrieve.return_value = [
            {
                "text": "Revenue was 100 billion.",
                "score": 0.95,
                "metadata": {"source": "report_2023.pdf"},
            },
        ]

        mock_generator_instance = mock_generator.return_value
        mock_generator_instance.generate.return_value = "Revenue was 100 billion."
        mock_generator_instance.last_token_usage = None

        pipeline = RAGPipeline(config="dummy.yaml")
        original_top_k = pipeline.config["retrieval"]["top_k"]

        pipeline.query(
            "What is the revenue?",
            config_overrides={"retrieval": {"top_k": 99}},
        )

        assert pipeline.config["retrieval"]["top_k"] == original_top_k

    @patch("src.pipeline.Generator")
    @patch("src.pipeline.Retriever")
    @patch("src.pipeline.VectorIndexer")
    @patch("src.pipeline.Embedder")
    @patch("src.pipeline.get_llm_config")
    @patch("src.pipeline.load_config")
    def test_query_with_config_overrides_hybrid_method(
        self,
        mock_load_config,
        mock_get_llm_config,
        mock_embedder,
        mock_indexer,
        mock_retriever,
        mock_generator,
    ):
        mock_load_config.return_value = _make_config()
        mock_get_llm_config.return_value = _make_llm_config()

        mock_generator_instance = mock_generator.return_value
        mock_generator_instance.generate.return_value = "Revenue was 100 billion."
        mock_generator_instance.last_token_usage = None

        pipeline = RAGPipeline(config="dummy.yaml")

        with (
            patch.object(pipeline, "_ensure_bm25_index") as mock_ensure_bm25,
            patch("src.pipeline.HybridRetrievalStrategy") as mock_hybrid_strategy_cls,
        ):
            mock_hybrid_strategy = MagicMock()
            mock_hybrid_result = MagicMock()
            mock_hybrid_result.chunks = [
                {
                    "text": "Revenue was 100 billion.",
                    "score": 0.9,
                    "metadata": {"source": "report_2023.pdf"},
                    "chunk_id": "c1",
                },
            ]
            mock_hybrid_strategy.retrieve.return_value = mock_hybrid_result
            mock_hybrid_strategy_cls.return_value = mock_hybrid_strategy

            pipeline.query(
                "What is the revenue?",
                config_overrides={
                    "retrieval": {
                        "method": "hybrid",
                        "hybrid": {
                            "fusion": "rrf",
                            "rrf_k": 60,
                            "vector_weight": 0.7,
                            "bm25_weight": 0.3,
                        },
                    },
                },
            )

            mock_ensure_bm25.assert_called_once()
            mock_hybrid_strategy_cls.assert_called_once()

    @patch("src.pipeline.Generator")
    @patch("src.pipeline.Retriever")
    @patch("src.pipeline.VectorIndexer")
    @patch("src.pipeline.Embedder")
    @patch("src.pipeline.get_llm_config")
    @patch("src.pipeline.load_config")
    def test_query_with_config_overrides_query_rewrite_enabled(
        self,
        mock_load_config,
        mock_get_llm_config,
        mock_embedder,
        mock_indexer,
        mock_retriever,
        mock_generator,
    ):
        mock_load_config.return_value = _make_config()
        mock_get_llm_config.return_value = _make_llm_config()

        mock_retriever_instance = mock_retriever.return_value
        mock_retriever_instance.retrieve.return_value = [
            {
                "text": "Revenue was 100 billion.",
                "score": 0.95,
                "metadata": {"source": "report_2023.pdf"},
            },
        ]

        mock_generator_instance = mock_generator.return_value
        mock_generator_instance.generate.return_value = "Revenue was 100 billion."
        mock_generator_instance.last_token_usage = None

        pipeline = RAGPipeline(config="dummy.yaml")
        assert pipeline.query_rewriter is None

        with patch.object(pipeline, "_ensure_query_rewriter") as mock_ensure_rw:
            pipeline.query(
                "What is the revenue?",
                config_overrides={
                    "retrieval": {
                        "query_rewrite": {"enabled": True, "strategy": "hyde"},
                    },
                },
            )

            mock_ensure_rw.assert_called_once_with("hyde")

    @patch("src.pipeline.Generator")
    @patch("src.pipeline.Retriever")
    @patch("src.pipeline.VectorIndexer")
    @patch("src.pipeline.Embedder")
    @patch("src.pipeline.get_llm_config")
    @patch("src.pipeline.load_config")
    def test_ensure_bm25_index_lazy_loads(
        self,
        mock_load_config,
        mock_get_llm_config,
        mock_embedder,
        mock_indexer,
        mock_retriever,
        mock_generator,
    ):
        mock_load_config.return_value = _make_config()
        mock_get_llm_config.return_value = _make_llm_config()

        pipeline = RAGPipeline(config="dummy.yaml")

        mock_chunks_dir = MagicMock()
        mock_chunks_dir.exists.return_value = True
        pipeline._chunks_dir = mock_chunks_dir

        with (
            patch.object(pipeline.bm25_retriever, "is_indexed", return_value=False),
            patch.object(
                pipeline.bm25_retriever, "build_index_from_chunks"
            ) as mock_build,
        ):
            pipeline._ensure_bm25_index()

            mock_build.assert_called_once_with(str(mock_chunks_dir))

    @patch("src.pipeline.Generator")
    @patch("src.pipeline.Retriever")
    @patch("src.pipeline.VectorIndexer")
    @patch("src.pipeline.Embedder")
    @patch("src.pipeline.get_llm_config")
    @patch("src.pipeline.load_config")
    def test_ensure_bm25_index_raises_when_no_chunks_dir(
        self,
        mock_load_config,
        mock_get_llm_config,
        mock_embedder,
        mock_indexer,
        mock_retriever,
        mock_generator,
    ):
        mock_load_config.return_value = _make_config()
        mock_get_llm_config.return_value = _make_llm_config()

        pipeline = RAGPipeline(config="dummy.yaml")
        pipeline._chunks_dir = None

        with (
            patch.object(pipeline.bm25_retriever, "is_indexed", return_value=False),
            pytest.raises(RetrievalError, match="BM25 索引不可用"),
        ):
            pipeline._ensure_bm25_index()

    @patch("src.pipeline.Generator")
    @patch("src.pipeline.Retriever")
    @patch("src.pipeline.VectorIndexer")
    @patch("src.pipeline.Embedder")
    @patch("src.pipeline.get_llm_config")
    @patch("src.pipeline.load_config")
    def test_ensure_reranker_lazy_loads(
        self,
        mock_load_config,
        mock_get_llm_config,
        mock_embedder,
        mock_indexer,
        mock_retriever,
        mock_generator,
    ):
        mock_load_config.return_value = _make_config()
        mock_get_llm_config.return_value = _make_llm_config()

        pipeline = RAGPipeline(config="dummy.yaml")
        assert pipeline.reranker is None

        with patch("src.pipeline.Reranker") as mock_reranker_cls:
            mock_reranker_instance = mock_reranker_cls.return_value
            pipeline._ensure_reranker()

            mock_reranker_cls.assert_called_once()
            assert pipeline.reranker is mock_reranker_instance

    @patch("src.pipeline.Generator")
    @patch("src.pipeline.Retriever")
    @patch("src.pipeline.VectorIndexer")
    @patch("src.pipeline.Embedder")
    @patch("src.pipeline.get_llm_config")
    @patch("src.pipeline.load_config")
    def test_ensure_reranker_noop_when_already_loaded(
        self,
        mock_load_config,
        mock_get_llm_config,
        mock_embedder,
        mock_indexer,
        mock_retriever,
        mock_generator,
    ):
        mock_load_config.return_value = _make_config()
        mock_get_llm_config.return_value = _make_llm_config()

        pipeline = RAGPipeline(config="dummy.yaml")
        existing_reranker = MagicMock()
        pipeline.reranker = existing_reranker

        with patch("src.pipeline.Reranker") as mock_reranker_cls:
            pipeline._ensure_reranker()

            mock_reranker_cls.assert_not_called()
            assert pipeline.reranker is existing_reranker

    @patch("src.pipeline.Generator")
    @patch("src.pipeline.Retriever")
    @patch("src.pipeline.VectorIndexer")
    @patch("src.pipeline.Embedder")
    @patch("src.pipeline.get_llm_config")
    @patch("src.pipeline.load_config")
    def test_ensure_query_rewriter_lazy_loads(
        self,
        mock_load_config,
        mock_get_llm_config,
        mock_embedder,
        mock_indexer,
        mock_retriever,
        mock_generator,
    ):
        mock_load_config.return_value = _make_config()
        mock_get_llm_config.return_value = _make_llm_config()

        pipeline = RAGPipeline(config="dummy.yaml")
        assert pipeline.query_rewriter is None

        with patch("src.pipeline.QueryRewriter") as mock_qr_cls:
            mock_qr_instance = mock_qr_cls.return_value
            mock_qr_instance.strategy = "hyde"

            pipeline._ensure_query_rewriter("hyde")

            mock_qr_cls.assert_called_once()
            assert pipeline.query_rewriter is mock_qr_instance

    @patch("src.pipeline.Generator")
    @patch("src.pipeline.Retriever")
    @patch("src.pipeline.VectorIndexer")
    @patch("src.pipeline.Embedder")
    @patch("src.pipeline.get_llm_config")
    @patch("src.pipeline.load_config")
    def test_ensure_query_rewriter_reinitializes_on_strategy_change(
        self,
        mock_load_config,
        mock_get_llm_config,
        mock_embedder,
        mock_indexer,
        mock_retriever,
        mock_generator,
    ):
        mock_load_config.return_value = _make_config()
        mock_get_llm_config.return_value = _make_llm_config()

        pipeline = RAGPipeline(config="dummy.yaml")

        mock_existing_rw = MagicMock()
        mock_existing_rw.strategy = "hyde"
        pipeline.query_rewriter = mock_existing_rw

        with patch("src.pipeline.QueryRewriter") as mock_qr_cls:
            mock_new_rw = mock_qr_cls.return_value
            mock_new_rw.strategy = "multi_query"

            pipeline._ensure_query_rewriter("multi_query")

            mock_qr_cls.assert_called_once()
            assert pipeline.query_rewriter is mock_new_rw
            assert pipeline.query_rewriter is not mock_existing_rw

    @patch("src.pipeline.Generator")
    @patch("src.pipeline.Retriever")
    @patch("src.pipeline.VectorIndexer")
    @patch("src.pipeline.Embedder")
    @patch("src.pipeline.get_llm_config")
    @patch("src.pipeline.load_config")
    def test_ensure_query_rewriter_noop_when_same_strategy(
        self,
        mock_load_config,
        mock_get_llm_config,
        mock_embedder,
        mock_indexer,
        mock_retriever,
        mock_generator,
    ):
        mock_load_config.return_value = _make_config()
        mock_get_llm_config.return_value = _make_llm_config()

        pipeline = RAGPipeline(config="dummy.yaml")

        mock_existing_rw = MagicMock()
        mock_existing_rw.strategy = "hyde"
        pipeline.query_rewriter = mock_existing_rw

        with patch("src.pipeline.QueryRewriter") as mock_qr_cls:
            pipeline._ensure_query_rewriter("hyde")

            mock_qr_cls.assert_not_called()
            assert pipeline.query_rewriter is mock_existing_rw


@pytest.mark.unit
class TestCloneForConcurrency:
    @patch("src.pipeline.Generator")
    @patch("src.pipeline.Retriever")
    @patch("src.pipeline.VectorIndexer")
    @patch("src.pipeline.Embedder")
    @patch("src.pipeline.get_llm_config")
    @patch("src.pipeline.load_config")
    def test_clone_shares_indexer_embedder_tracker(
        self,
        mock_load_config,
        mock_get_llm_config,
        mock_embedder,
        mock_indexer,
        mock_retriever,
        mock_generator,
    ):
        mock_load_config.return_value = _make_config()
        mock_get_llm_config.return_value = _make_llm_config()

        pipeline = RAGPipeline(config="dummy.yaml")

        clone = pipeline.clone_for_concurrency()

        assert clone.indexer is pipeline.indexer
        assert clone.embedder is pipeline.embedder
        assert clone.token_tracker is pipeline.token_tracker
        assert clone.profiler is pipeline.profiler

    @patch("src.pipeline.Generator")
    @patch("src.pipeline.Retriever")
    @patch("src.pipeline.VectorIndexer")
    @patch("src.pipeline.Embedder")
    @patch("src.pipeline.get_llm_config")
    @patch("src.pipeline.load_config")
    def test_clone_creates_new_generator(
        self,
        mock_load_config,
        mock_get_llm_config,
        mock_embedder,
        mock_indexer,
        mock_retriever,
        mock_generator,
    ):
        mock_load_config.return_value = _make_config()
        mock_get_llm_config.return_value = _make_llm_config()

        pipeline = RAGPipeline(config="dummy.yaml")

        pipeline.clone_for_concurrency()

        assert mock_generator.call_count == 2

    @patch("src.pipeline.Generator")
    @patch("src.pipeline.Retriever")
    @patch("src.pipeline.VectorIndexer")
    @patch("src.pipeline.Embedder")
    @patch("src.pipeline.get_llm_config")
    @patch("src.pipeline.load_config")
    def test_clone_reranker_and_query_rewriter_are_none(
        self,
        mock_load_config,
        mock_get_llm_config,
        mock_embedder,
        mock_indexer,
        mock_retriever,
        mock_generator,
    ):
        mock_load_config.return_value = _make_config()
        mock_get_llm_config.return_value = _make_llm_config()

        pipeline = RAGPipeline(config="dummy.yaml")
        pipeline.reranker = MagicMock()
        pipeline.query_rewriter = MagicMock()

        clone = pipeline.clone_for_concurrency()

        assert clone.reranker is None
        assert clone.query_rewriter is None

    @patch("src.pipeline.Generator")
    @patch("src.pipeline.Retriever")
    @patch("src.pipeline.VectorIndexer")
    @patch("src.pipeline.Embedder")
    @patch("src.pipeline.get_llm_config")
    @patch("src.pipeline.load_config")
    def test_clone_preserves_config_and_meal(
        self,
        mock_load_config,
        mock_get_llm_config,
        mock_embedder,
        mock_indexer,
        mock_retriever,
        mock_generator,
    ):
        mock_load_config.return_value = _make_config()
        mock_get_llm_config.return_value = _make_llm_config()

        pipeline = RAGPipeline(config="dummy.yaml")
        pipeline.meal_name = "test_meal"

        clone = pipeline.clone_for_concurrency()

        assert clone.config is pipeline.config
        assert clone.meal_name == "test_meal"
        assert clone.meal_config is pipeline.meal_config
