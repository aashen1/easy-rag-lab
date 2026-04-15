from unittest.mock import MagicMock, Mock, patch

import numpy as np
import pytest
import torch

from src.embedder import Embedder


class TestEmbedder:
    @patch("src.embedder.AutoTokenizer")
    @patch("src.embedder.AutoModel")
    @patch("src.embedder.torch.cuda.is_available")
    def test_embedder_init_success(
        self, mock_cuda_available, mock_auto_model, mock_auto_tokenizer
    ):
        mock_cuda_available.return_value = True
        mock_model = MagicMock()
        mock_model.config.hidden_size = 1024
        mock_model.to.return_value = mock_model
        mock_model.half.return_value = mock_model
        mock_auto_model.from_pretrained.return_value = mock_model
        mock_auto_tokenizer.from_pretrained.return_value = MagicMock()

        embedder = Embedder(model_name="test-model", device="cuda")

        assert embedder.model_name == "test-model"
        assert embedder.device == "cuda"
        assert embedder.embedding_dim == 1024

    @patch("src.embedder.AutoTokenizer")
    @patch("src.embedder.AutoModel")
    @patch("src.embedder.torch.cuda.is_available")
    def test_embedder_init_cuda_fallback_to_cpu(
        self, mock_cuda_available, mock_auto_model, mock_auto_tokenizer
    ):
        mock_cuda_available.return_value = False
        mock_model = MagicMock()
        mock_model.config.hidden_size = 1024
        mock_model.to.return_value = mock_model
        mock_auto_model.from_pretrained.return_value = mock_model
        mock_auto_tokenizer.from_pretrained.return_value = MagicMock()

        embedder = Embedder(model_name="test-model", device="cuda")

        assert embedder.device == "cpu"

    @patch("src.embedder.AutoTokenizer")
    @patch("src.embedder.AutoModel")
    def test_embedder_init_failure(self, mock_auto_model, mock_auto_tokenizer):
        mock_auto_model.from_pretrained.side_effect = Exception("Model load error")

        with pytest.raises(Exception) as exc_info:
            Embedder(model_name="test-model")
        assert "Failed to load embedding model" in str(exc_info.value)

    @patch("src.embedder.AutoTokenizer")
    @patch("src.embedder.AutoModel")
    @patch("src.embedder.torch.cuda.is_available")
    def test_embed_texts_success(
        self, mock_cuda_available, mock_auto_model, mock_auto_tokenizer
    ):
        mock_cuda_available.return_value = True
        mock_model = MagicMock()
        mock_model.config.hidden_size = 1024
        mock_model.to.return_value = mock_model
        mock_model.half.return_value = mock_model
        mock_model.eval.return_value = mock_model

        mock_outputs = MagicMock()
        mock_outputs.last_hidden_state = torch.randn(3, 10, 1024)
        mock_model.return_value = mock_outputs

        mock_auto_model.from_pretrained.return_value = mock_model

        mock_tokenizer = MagicMock()
        mock_tokenizer.return_value = {
            "input_ids": torch.randint(0, 1000, (3, 10)),
            "attention_mask": torch.ones(3, 10),
        }
        mock_auto_tokenizer.from_pretrained.return_value = mock_tokenizer

        embedder = Embedder(model_name="test-model")

        texts = ["text1", "text2", "text3"]
        embeddings = embedder.embed_texts(texts, batch_size=32)

        assert embeddings.shape == (3, 1024)

    @patch("src.embedder.AutoTokenizer")
    @patch("src.embedder.AutoModel")
    @patch("src.embedder.torch.cuda.is_available")
    def test_embed_texts_empty_list(
        self, mock_cuda_available, mock_auto_model, mock_auto_tokenizer
    ):
        mock_cuda_available.return_value = True
        mock_model = MagicMock()
        mock_model.config.hidden_size = 1024
        mock_model.to.return_value = mock_model
        mock_model.half.return_value = mock_model
        mock_auto_model.from_pretrained.return_value = mock_model
        mock_auto_tokenizer.from_pretrained.return_value = MagicMock()

        embedder = Embedder(model_name="test-model")

        embeddings = embedder.embed_texts([])

        assert embeddings.shape == (0,)

    @patch("src.embedder.AutoTokenizer")
    @patch("src.embedder.AutoModel")
    @patch("src.embedder.torch.cuda.is_available")
    def test_embed_texts_invalid_input(
        self, mock_cuda_available, mock_auto_model, mock_auto_tokenizer
    ):
        mock_cuda_available.return_value = True
        mock_model = MagicMock()
        mock_model.config.hidden_size = 1024
        mock_model.to.return_value = mock_model
        mock_model.half.return_value = mock_model
        mock_auto_model.from_pretrained.return_value = mock_model
        mock_auto_tokenizer.from_pretrained.return_value = MagicMock()

        embedder = Embedder(model_name="test-model")

        with pytest.raises(ValueError) as exc_info:
            embedder.embed_texts([123, 456])
        assert "All items in texts must be strings" in str(exc_info.value)

    @patch("src.embedder.AutoTokenizer")
    @patch("src.embedder.AutoModel")
    @patch("src.embedder.torch.cuda.is_available")
    def test_embed_texts_encoding_failure(
        self, mock_cuda_available, mock_auto_model, mock_auto_tokenizer
    ):
        mock_cuda_available.return_value = True
        mock_model = MagicMock()
        mock_model.config.hidden_size = 1024
        mock_model.to.return_value = mock_model
        mock_model.half.return_value = mock_model
        mock_model.eval.return_value = mock_model
        mock_model.side_effect = Exception("Encoding error")
        mock_auto_model.from_pretrained.return_value = mock_model

        mock_tokenizer = MagicMock()
        mock_tokenizer.return_value = {
            "input_ids": torch.randint(0, 1000, (2, 10)),
            "attention_mask": torch.ones(2, 10),
        }
        mock_auto_tokenizer.from_pretrained.return_value = mock_tokenizer

        embedder = Embedder(model_name="test-model")

        with pytest.raises(Exception) as exc_info:
            embedder.embed_texts(["text1", "text2"])
        assert "Failed to embed texts" in str(exc_info.value)

    @patch("src.embedder.AutoTokenizer")
    @patch("src.embedder.AutoModel")
    @patch("src.embedder.torch.cuda.is_available")
    def test_embed_query_success(
        self, mock_cuda_available, mock_auto_model, mock_auto_tokenizer
    ):
        mock_cuda_available.return_value = True
        mock_model = MagicMock()
        mock_model.config.hidden_size = 1024
        mock_model.to.return_value = mock_model
        mock_model.half.return_value = mock_model
        mock_model.eval.return_value = mock_model

        mock_outputs = MagicMock()
        mock_outputs.last_hidden_state = torch.randn(1, 10, 1024)
        mock_model.return_value = mock_outputs

        mock_auto_model.from_pretrained.return_value = mock_model

        mock_tokenizer = MagicMock()
        mock_tokenizer.return_value = {
            "input_ids": torch.randint(0, 1000, (1, 10)),
            "attention_mask": torch.ones(1, 10),
        }
        mock_auto_tokenizer.from_pretrained.return_value = mock_tokenizer

        embedder = Embedder(model_name="test-model")

        query = "test query"
        embedding = embedder.embed_query(query)

        assert embedding.shape == (1024,)

    @patch("src.embedder.AutoTokenizer")
    @patch("src.embedder.AutoModel")
    @patch("src.embedder.torch.cuda.is_available")
    def test_embed_query_empty_string(
        self, mock_cuda_available, mock_auto_model, mock_auto_tokenizer
    ):
        mock_cuda_available.return_value = True
        mock_model = MagicMock()
        mock_model.config.hidden_size = 1024
        mock_model.to.return_value = mock_model
        mock_model.half.return_value = mock_model
        mock_auto_model.from_pretrained.return_value = mock_model
        mock_auto_tokenizer.from_pretrained.return_value = MagicMock()

        embedder = Embedder(model_name="test-model")

        with pytest.raises(ValueError) as exc_info:
            embedder.embed_query("")
        assert "Query must be a non-empty string" in str(exc_info.value)

    @patch("src.embedder.AutoTokenizer")
    @patch("src.embedder.AutoModel")
    @patch("src.embedder.torch.cuda.is_available")
    def test_embed_query_invalid_type(
        self, mock_cuda_available, mock_auto_model, mock_auto_tokenizer
    ):
        mock_cuda_available.return_value = True
        mock_model = MagicMock()
        mock_model.config.hidden_size = 1024
        mock_model.to.return_value = mock_model
        mock_model.half.return_value = mock_model
        mock_auto_model.from_pretrained.return_value = mock_model
        mock_auto_tokenizer.from_pretrained.return_value = MagicMock()

        embedder = Embedder(model_name="test-model")

        with pytest.raises(ValueError) as exc_info:
            embedder.embed_query(123)
        assert "Query must be a non-empty string" in str(exc_info.value)

    @patch("src.embedder.AutoTokenizer")
    @patch("src.embedder.AutoModel")
    @patch("src.embedder.torch.cuda.is_available")
    def test_embed_query_encoding_failure(
        self, mock_cuda_available, mock_auto_model, mock_auto_tokenizer
    ):
        mock_cuda_available.return_value = True
        mock_model = MagicMock()
        mock_model.config.hidden_size = 1024
        mock_model.to.return_value = mock_model
        mock_model.half.return_value = mock_model
        mock_model.eval.return_value = mock_model
        mock_model.side_effect = Exception("Encoding error")
        mock_auto_model.from_pretrained.return_value = mock_model

        mock_tokenizer = MagicMock()
        mock_tokenizer.return_value = {
            "input_ids": torch.randint(0, 1000, (1, 10)),
            "attention_mask": torch.ones(1, 10),
        }
        mock_auto_tokenizer.from_pretrained.return_value = mock_tokenizer

        embedder = Embedder(model_name="test-model")

        with pytest.raises(Exception) as exc_info:
            embedder.embed_query("test query")
        assert "Failed to embed query" in str(exc_info.value)

    @patch("src.embedder.AutoTokenizer")
    @patch("src.embedder.AutoModel")
    @patch("src.embedder.torch.cuda.is_available")
    def test_get_embedding_dimension(
        self, mock_cuda_available, mock_auto_model, mock_auto_tokenizer
    ):
        mock_cuda_available.return_value = True
        mock_model = MagicMock()
        mock_model.config.hidden_size = 1024
        mock_model.to.return_value = mock_model
        mock_model.half.return_value = mock_model
        mock_auto_model.from_pretrained.return_value = mock_model
        mock_auto_tokenizer.from_pretrained.return_value = MagicMock()

        embedder = Embedder(model_name="test-model")

        dim = embedder.get_embedding_dimension()

        assert dim == 1024
