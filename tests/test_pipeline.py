import pytest
from unittest.mock import MagicMock, patch

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
            model_name="test-model", device="cpu"
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
        )
        mock_generator.assert_called_once_with(
            model_name="test-llm",
            api_key="key",
            base_url="url",
            temperature=0.0,
            max_tokens=1024,
            token_tracker=pipeline.token_tracker,
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
