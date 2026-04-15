from unittest.mock import MagicMock, Mock, patch

import numpy as np
import pytest

from src.embedder import Embedder


class TestEmbedder:
    @patch("src.embedder.FlagModel")
    @patch("src.embedder.torch.cuda.is_available")
    def test_embedder_init_success(self, mock_cuda_available, mock_flag_model):
        mock_cuda_available.return_value = True
        mock_model = MagicMock()
        mock_model.model.config.hidden_size = 1024
        mock_flag_model.return_value = mock_model

        embedder = Embedder(model_name="test-model", device="cuda")

        assert embedder.model_name == "test-model"
        assert embedder.device == "cuda"
        assert embedder.embedding_dim == 1024

    @patch("src.embedder.FlagModel")
    @patch("src.embedder.torch.cuda.is_available")
    def test_embedder_init_cuda_fallback_to_cpu(
        self, mock_cuda_available, mock_flag_model
    ):
        mock_cuda_available.return_value = False
        mock_model = MagicMock()
        mock_model.model.config.hidden_size = 1024
        mock_flag_model.return_value = mock_model

        embedder = Embedder(model_name="test-model", device="cuda")

        assert embedder.device == "cpu"

    @patch("src.embedder.FlagModel")
    def test_embedder_init_failure(self, mock_flag_model):
        mock_flag_model.side_effect = Exception("Model load error")

        with pytest.raises(Exception) as exc_info:
            Embedder(model_name="test-model")
        assert "Failed to load embedding model" in str(exc_info.value)

    @patch("src.embedder.FlagModel")
    @patch("src.embedder.torch.cuda.is_available")
    def test_embed_texts_success(self, mock_cuda_available, mock_flag_model):
        mock_cuda_available.return_value = True
        mock_model = MagicMock()
        mock_model.model.config.hidden_size = 1024
        mock_model.encode.return_value = np.random.rand(3, 1024)
        mock_flag_model.return_value = mock_model

        embedder = Embedder(model_name="test-model")

        texts = ["text1", "text2", "text3"]
        embeddings = embedder.embed_texts(texts, batch_size=32)

        assert embeddings.shape == (3, 1024)
        mock_model.encode.assert_called_once()

    @patch("src.embedder.FlagModel")
    @patch("src.embedder.torch.cuda.is_available")
    def test_embed_texts_empty_list(self, mock_cuda_available, mock_flag_model):
        mock_cuda_available.return_value = True
        mock_model = MagicMock()
        mock_model.model.config.hidden_size = 1024
        mock_flag_model.return_value = mock_model

        embedder = Embedder(model_name="test-model")

        embeddings = embedder.embed_texts([])

        assert embeddings.shape == (0,)

    @patch("src.embedder.FlagModel")
    @patch("src.embedder.torch.cuda.is_available")
    def test_embed_texts_invalid_input(self, mock_cuda_available, mock_flag_model):
        mock_cuda_available.return_value = True
        mock_model = MagicMock()
        mock_model.model.config.hidden_size = 1024
        mock_flag_model.return_value = mock_model

        embedder = Embedder(model_name="test-model")

        with pytest.raises(ValueError) as exc_info:
            embedder.embed_texts([123, 456])
        assert "All items in texts must be strings" in str(exc_info.value)

    @patch("src.embedder.FlagModel")
    @patch("src.embedder.torch.cuda.is_available")
    def test_embed_texts_encoding_failure(self, mock_cuda_available, mock_flag_model):
        mock_cuda_available.return_value = True
        mock_model = MagicMock()
        mock_model.model.config.hidden_size = 1024
        mock_model.encode.side_effect = Exception("Encoding error")
        mock_flag_model.return_value = mock_model

        embedder = Embedder(model_name="test-model")

        with pytest.raises(Exception) as exc_info:
            embedder.embed_texts(["text1", "text2"])
        assert "Failed to embed texts" in str(exc_info.value)

    @patch("src.embedder.FlagModel")
    @patch("src.embedder.torch.cuda.is_available")
    def test_embed_query_success(self, mock_cuda_available, mock_flag_model):
        mock_cuda_available.return_value = True
        mock_model = MagicMock()
        mock_model.model.config.hidden_size = 1024
        mock_model.encode.return_value = np.random.rand(1, 1024)
        mock_flag_model.return_value = mock_model

        embedder = Embedder(model_name="test-model")

        query = "test query"
        embedding = embedder.embed_query(query)

        assert embedding.shape == (1024,)
        mock_model.encode.assert_called_once()

    @patch("src.embedder.FlagModel")
    @patch("src.embedder.torch.cuda.is_available")
    def test_embed_query_empty_string(self, mock_cuda_available, mock_flag_model):
        mock_cuda_available.return_value = True
        mock_model = MagicMock()
        mock_model.model.config.hidden_size = 1024
        mock_flag_model.return_value = mock_model

        embedder = Embedder(model_name="test-model")

        with pytest.raises(ValueError) as exc_info:
            embedder.embed_query("")
        assert "Query must be a non-empty string" in str(exc_info.value)

    @patch("src.embedder.FlagModel")
    @patch("src.embedder.torch.cuda.is_available")
    def test_embed_query_invalid_type(self, mock_cuda_available, mock_flag_model):
        mock_cuda_available.return_value = True
        mock_model = MagicMock()
        mock_model.model.config.hidden_size = 1024
        mock_flag_model.return_value = mock_model

        embedder = Embedder(model_name="test-model")

        with pytest.raises(ValueError) as exc_info:
            embedder.embed_query(123)
        assert "Query must be a non-empty string" in str(exc_info.value)

    @patch("src.embedder.FlagModel")
    @patch("src.embedder.torch.cuda.is_available")
    def test_embed_query_encoding_failure(self, mock_cuda_available, mock_flag_model):
        mock_cuda_available.return_value = True
        mock_model = MagicMock()
        mock_model.model.config.hidden_size = 1024
        mock_model.encode.side_effect = Exception("Encoding error")
        mock_flag_model.return_value = mock_model

        embedder = Embedder(model_name="test-model")

        with pytest.raises(Exception) as exc_info:
            embedder.embed_query("test query")
        assert "Failed to embed query" in str(exc_info.value)

    @patch("src.embedder.FlagModel")
    @patch("src.embedder.torch.cuda.is_available")
    def test_get_embedding_dimension(self, mock_cuda_available, mock_flag_model):
        mock_cuda_available.return_value = True
        mock_model = MagicMock()
        mock_model.model.config.hidden_size = 1024
        mock_flag_model.return_value = mock_model

        embedder = Embedder(model_name="test-model")

        dim = embedder.get_embedding_dimension()

        assert dim == 1024
