from unittest.mock import MagicMock, patch

import pytest

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
    @patch("src.pipeline.setup_logger")
    @patch("src.pipeline.load_config")
    def test_init_without_meal(
        self,
        mock_load_config,
        mock_setup_logger,
        mock_get_llm_config,
        mock_embedder,
        mock_indexer,
        mock_retriever,
        mock_generator,
    ):
        mock_load_config.return_value = _make_config()
        mock_get_llm_config.return_value = _make_llm_config()

        pipeline = RAGPipeline(config_path="dummy.yaml")

        mock_embedder.assert_called_once_with(
            model_name="test-model", device="cpu", query_instruction=None
        )
        mock_indexer.assert_called_once_with(
            persist_dir="/tmp/vs",
            collection_name="default_col",
            distance="Cosine",
        )
        mock_retriever.assert_called_once_with(
            indexer=mock_indexer.return_value,
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

    @patch("src.pipeline.Generator")
    @patch("src.pipeline.Retriever")
    @patch("src.pipeline.VectorIndexer")
    @patch("src.pipeline.Embedder")
    @patch("src.pipeline.get_llm_config")
    @patch("src.pipeline.setup_logger")
    @patch("src.pipeline.load_config")
    def test_init_with_meal(
        self,
        mock_load_config,
        mock_setup_logger,
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

            pipeline = RAGPipeline(
                config_path="dummy.yaml", meal_name="test_meal"
            )

            mock_meal_mgr.load_meal.assert_called_once_with("test_meal")

        mock_indexer.assert_called_once_with(
            persist_dir="/tmp/vs",
            collection_name="meal_col_123",
            distance="Cosine",
        )
        assert pipeline.meal_name == "test_meal"
        assert pipeline.meal_config is mock_meal_config

    @patch("src.pipeline.Generator")
    @patch("src.pipeline.Retriever")
    @patch("src.pipeline.VectorIndexer")
    @patch("src.pipeline.Embedder")
    @patch("src.pipeline.get_llm_config")
    @patch("src.pipeline.setup_logger")
    @patch("src.pipeline.load_config")
    def test_query_full_flow(
        self,
        mock_load_config,
        mock_setup_logger,
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

        pipeline = RAGPipeline(config_path="dummy.yaml")
        result = pipeline.query("What is the revenue?")

        mock_retriever_instance.retrieve.assert_called_once_with(
            "What is the revenue?"
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
    @patch("src.pipeline.setup_logger")
    @patch("src.pipeline.load_config")
    def test_query_invalid_input(
        self,
        mock_load_config,
        mock_setup_logger,
        mock_get_llm_config,
        mock_embedder,
        mock_indexer,
        mock_retriever,
        mock_generator,
    ):
        mock_load_config.return_value = _make_config()
        mock_get_llm_config.return_value = _make_llm_config()

        pipeline = RAGPipeline(config_path="dummy.yaml")

        with pytest.raises(ValueError, match="Question must be a non-empty string"):
            pipeline.query("")

        with pytest.raises(ValueError, match="Question must be a non-empty string"):
            pipeline.query(123)

    @patch("src.pipeline.Generator")
    @patch("src.pipeline.Retriever")
    @patch("src.pipeline.VectorIndexer")
    @patch("src.pipeline.Embedder")
    @patch("src.pipeline.get_llm_config")
    @patch("src.pipeline.setup_logger")
    @patch("src.pipeline.load_config")
    def test_use_meal_switch(
        self,
        mock_load_config,
        mock_setup_logger,
        mock_get_llm_config,
        mock_embedder,
        mock_indexer,
        mock_retriever,
        mock_generator,
    ):
        mock_load_config.return_value = _make_config()
        mock_get_llm_config.return_value = _make_llm_config()

        pipeline = RAGPipeline(config_path="dummy.yaml")

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
    @patch("src.pipeline.setup_logger")
    @patch("src.pipeline.load_config")
    def test_close_calls_indexer_close(
        self,
        mock_load_config,
        mock_setup_logger,
        mock_get_llm_config,
        mock_embedder,
        mock_indexer,
        mock_retriever,
        mock_generator,
    ):
        mock_load_config.return_value = _make_config()
        mock_get_llm_config.return_value = _make_llm_config()

        pipeline = RAGPipeline(config_path="dummy.yaml")
        pipeline.close()

        mock_indexer.return_value.close.assert_called_once()

    @patch("src.pipeline.Generator")
    @patch("src.pipeline.Retriever")
    @patch("src.pipeline.VectorIndexer")
    @patch("src.pipeline.Embedder")
    @patch("src.pipeline.get_llm_config")
    @patch("src.pipeline.setup_logger")
    @patch("src.pipeline.load_config")
    def test_context_manager_calls_close(
        self,
        mock_load_config,
        mock_setup_logger,
        mock_get_llm_config,
        mock_embedder,
        mock_indexer,
        mock_retriever,
        mock_generator,
    ):
        mock_load_config.return_value = _make_config()
        mock_get_llm_config.return_value = _make_llm_config()

        with RAGPipeline(config_path="dummy.yaml") as pipeline:
            pass

        mock_indexer.return_value.close.assert_called_once()

    @patch("src.pipeline.Generator")
    @patch("src.pipeline.Retriever")
    @patch("src.pipeline.VectorIndexer")
    @patch("src.pipeline.Embedder")
    @patch("src.pipeline.get_llm_config")
    @patch("src.pipeline.setup_logger")
    @patch("src.pipeline.load_config")
    def test_use_meal_closes_old_indexer(
        self,
        mock_load_config,
        mock_setup_logger,
        mock_get_llm_config,
        mock_embedder,
        mock_indexer,
        mock_retriever,
        mock_generator,
    ):
        mock_load_config.return_value = _make_config()
        mock_get_llm_config.return_value = _make_llm_config()

        pipeline = RAGPipeline(config_path="dummy.yaml")
        old_indexer = pipeline.indexer

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
    @patch("src.pipeline.setup_logger")
    @patch("src.pipeline.load_config")
    def test_build_index_passes_parser_options(
        self,
        mock_load_config,
        mock_setup_logger,
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

        pipeline = RAGPipeline(config_path="dummy.yaml")

        with patch("src.pipeline.parse_all_pdfs") as mock_parse, patch(
            "src.chunker.process_parsed_files_page_aware"
        ) as mock_page_aware:
            mock_parse.return_value = []
            mock_page_aware.return_value = []
            pipeline.build_index()

        mock_parse.assert_called_once_with(
            input_dir="/tmp/parser_in",
            output_dir="/tmp/parser_out",
            force=False,
            pdf_files=None,
            parser_options={"page_chunks": True, "table_strategy": "text"},
        )
        mock_page_aware.assert_called_once_with(
            input_dir="/tmp/chunker_in",
            output_dir="/tmp/chunker_out",
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
    @patch("src.pipeline.setup_logger")
    @patch("src.pipeline.load_config")
    def test_build_index_parser_options_none_when_missing(
        self,
        mock_load_config,
        mock_setup_logger,
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

        pipeline = RAGPipeline(config_path="dummy.yaml")

        with patch("src.pipeline.parse_all_pdfs") as mock_parse, patch(
            "src.pipeline.process_parsed_files"
        ) as mock_chunk:
            mock_parse.return_value = []
            mock_chunk.return_value = []
            pipeline.build_index()

        mock_parse.assert_called_once_with(
            input_dir="/tmp/parser_in",
            output_dir="/tmp/parser_out",
            force=False,
            pdf_files=None,
            parser_options=None,
        )

    @patch("src.pipeline.Generator")
    @patch("src.pipeline.Retriever")
    @patch("src.pipeline.VectorIndexer")
    @patch("src.pipeline.Embedder")
    @patch("src.pipeline.get_llm_config")
    @patch("src.pipeline.setup_logger")
    @patch("src.pipeline.load_config")
    def test_build_index_page_aware_chunking(
        self,
        mock_load_config,
        mock_setup_logger,
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

        pipeline = RAGPipeline(config_path="dummy.yaml")

        parse_results = [
            {"output": "/tmp/parser_out/report_2023.pages.json", "status": "ok"},
            {"output": "/tmp/parser_out/report_2024.pages.json", "status": "ok"},
        ]

        with patch("src.pipeline.parse_all_pdfs") as mock_parse, patch(
            "src.chunker.process_parsed_files_page_aware"
        ) as mock_page_aware, patch(
            "src.pipeline.process_parsed_files"
        ) as mock_chunk:
            mock_parse.return_value = parse_results
            mock_page_aware.return_value = [
                {"output": "/tmp/chunker_out/report_2023.jsonl", "status": "ok"},
            ]
            mock_chunk.return_value = []
            pipeline.build_index()

        mock_page_aware.assert_called_once_with(
            input_dir="/tmp/chunker_in",
            output_dir="/tmp/chunker_out",
            chunk_size=500,
            overlap=50,
            encoding_name="cl100k_base",
            source_filter=None,
            model_name="test-model",
        )
        mock_chunk.assert_not_called()

    @patch("src.pipeline.Generator")
    @patch("src.pipeline.Retriever")
    @patch("src.pipeline.VectorIndexer")
    @patch("src.pipeline.Embedder")
    @patch("src.pipeline.get_llm_config")
    @patch("src.pipeline.setup_logger")
    @patch("src.pipeline.load_config")
    def test_build_index_regular_chunking_when_no_page_chunks(
        self,
        mock_load_config,
        mock_setup_logger,
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

        pipeline = RAGPipeline(config_path="dummy.yaml")

        with patch("src.pipeline.parse_all_pdfs") as mock_parse, patch(
            "src.pipeline.process_parsed_files"
        ) as mock_chunk:
            mock_parse.return_value = []
            mock_chunk.return_value = []
            pipeline.build_index()

        mock_chunk.assert_called_once_with(
            input_dir="/tmp/chunker_in",
            output_dir="/tmp/chunker_out",
            chunk_size=500,
            overlap=50,
            encoding_name="cl100k_base",
            source_filter=None,
            model_name="test-model",
        )
