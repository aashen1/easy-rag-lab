from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
import torch

from src.embedder import Embedder


@pytest.fixture
def embedder_setup():
    with patch("src.embedder.AutoTokenizer") as mock_auto_tokenizer, \
         patch("src.embedder.AutoModel") as mock_auto_model, \
         patch("src.embedder.torch.cuda.is_available") as mock_cuda_available:

        mock_cuda_available.return_value = True

        mock_model = MagicMock()
        mock_model.config.hidden_size = 1024
        mock_model.to.return_value = mock_model
        mock_model.half.return_value = mock_model
        mock_model.eval.return_value = mock_model

        mock_auto_model.from_pretrained.return_value = mock_model
        mock_auto_tokenizer.from_pretrained.return_value = MagicMock()

        embedder = Embedder(model_name="test-model", device="cuda")

        yield SimpleNamespace(
            mock_model=mock_model,
            mock_auto_model=mock_auto_model,
            mock_auto_tokenizer=mock_auto_tokenizer,
            mock_cuda_available=mock_cuda_available,
            embedder=embedder,
        )


class TestEmbedder:
    @pytest.mark.unit
    def test_embedder_init_success(self, embedder_setup):
        assert embedder_setup.embedder.model_name == "test-model"
        assert embedder_setup.embedder.device == "cuda"
        assert embedder_setup.embedder.embedding_dim == 1024

    @pytest.mark.unit
    def test_embedder_init_cuda_fallback_to_cpu(self, embedder_setup):
        embedder_setup.mock_cuda_available.return_value = False
        embedder = Embedder(model_name="test-model", device="cuda")
        assert embedder.device == "cpu"

    @pytest.mark.unit
    def test_embedder_init_failure(self, embedder_setup):
        embedder_setup.mock_auto_model.from_pretrained.side_effect = Exception("Model load error")
        with pytest.raises(Exception) as exc_info:
            Embedder(model_name="test-model")
        assert "Failed to load embedding model" in str(exc_info.value)

    @pytest.mark.unit
    def test_embed_texts_success(self, embedder_setup):
        mock_outputs = MagicMock()
        mock_outputs.last_hidden_state = torch.randn(3, 10, 1024)
        embedder_setup.mock_model.return_value = mock_outputs

        mock_tokenizer = MagicMock()
        mock_tokenizer.return_value = {
            "input_ids": torch.randint(0, 1000, (3, 10)),
            "attention_mask": torch.ones(3, 10),
        }
        embedder_setup.embedder._tokenizer = mock_tokenizer

        texts = ["text1", "text2", "text3"]
        embeddings = embedder_setup.embedder.embed_texts(texts, batch_size=32)
        assert embeddings.shape == (3, 1024)

    @pytest.mark.unit
    def test_embed_texts_empty_list(self, embedder_setup):
        embeddings = embedder_setup.embedder.embed_texts([])
        assert embeddings.shape == (0,)

    @pytest.mark.unit
    def test_embed_texts_invalid_input(self, embedder_setup):
        with pytest.raises(ValueError) as exc_info:
            embedder_setup.embedder.embed_texts([123, 456])
        assert "All items in texts must be strings" in str(exc_info.value)

    @pytest.mark.unit
    def test_embed_texts_encoding_failure(self, embedder_setup):
        embedder_setup.mock_model.side_effect = Exception("Encoding error")

        mock_tokenizer = MagicMock()
        mock_tokenizer.return_value = {
            "input_ids": torch.randint(0, 1000, (2, 10)),
            "attention_mask": torch.ones(2, 10),
        }
        embedder_setup.embedder._tokenizer = mock_tokenizer

        with pytest.raises(Exception) as exc_info:
            embedder_setup.embedder.embed_texts(["text1", "text2"])
        assert "Failed to embed texts" in str(exc_info.value)

    @pytest.mark.unit
    def test_embed_query_success(self, embedder_setup):
        mock_outputs = MagicMock()
        mock_outputs.last_hidden_state = torch.randn(1, 10, 1024)
        embedder_setup.mock_model.return_value = mock_outputs

        mock_tokenizer = MagicMock()
        mock_tokenizer.return_value = {
            "input_ids": torch.randint(0, 1000, (1, 10)),
            "attention_mask": torch.ones(1, 10),
        }
        embedder_setup.embedder._tokenizer = mock_tokenizer

        query = "test query"
        embedding = embedder_setup.embedder.embed_query(query)
        assert embedding.shape == (1024,)

    @pytest.mark.unit
    def test_embed_query_empty_string(self, embedder_setup):
        with pytest.raises(ValueError) as exc_info:
            embedder_setup.embedder.embed_query("")
        assert "Query must be a non-empty string" in str(exc_info.value)

    @pytest.mark.unit
    def test_embed_query_invalid_type(self, embedder_setup):
        with pytest.raises(ValueError) as exc_info:
            embedder_setup.embedder.embed_query(123)
        assert "Query must be a non-empty string" in str(exc_info.value)

    @pytest.mark.unit
    def test_embed_query_encoding_failure(self, embedder_setup):
        embedder_setup.mock_model.side_effect = Exception("Encoding error")

        mock_tokenizer = MagicMock()
        mock_tokenizer.return_value = {
            "input_ids": torch.randint(0, 1000, (1, 10)),
            "attention_mask": torch.ones(1, 10),
        }
        embedder_setup.embedder._tokenizer = mock_tokenizer

        with pytest.raises(Exception) as exc_info:
            embedder_setup.embedder.embed_query("test query")
        assert "Failed to embed query" in str(exc_info.value)

    @pytest.mark.unit
    def test_get_embedding_dimension(self, embedder_setup):
        dim = embedder_setup.embedder.get_embedding_dimension()
        assert dim == 1024
