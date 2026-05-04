from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pytest


class TestEmbedChunks:
    def test_embed_chunks_returns_list_of_lists(self):
        from src.core.ops.embed import embed_chunks

        mock_embedder = MagicMock()
        mock_embedder.embed_texts.return_value = np.array(
            [[0.1, 0.2], [0.3, 0.4]], dtype=np.float32
        )

        chunks = [{"text": "hello"}, {"text": "world"}]
        result = embed_chunks(chunks, mock_embedder)

        assert isinstance(result, list)
        assert len(result) == 2
        assert isinstance(result[0], list)
        assert len(result[0]) == 2

    def test_embed_chunks_empty_list(self):
        from src.core.ops.embed import embed_chunks

        result = embed_chunks([], MagicMock())
        assert result == []

    def test_embed_chunks_missing_text_key(self):
        from src.core.ops.embed import embed_chunks

        mock_embedder = MagicMock()
        chunks = [{"no_text_key": "oops"}]

        with pytest.raises(KeyError):
            embed_chunks(chunks, mock_embedder)

    def test_embed_chunks_uses_batch_size(self):
        from src.core.ops.embed import embed_chunks

        mock_embedder = MagicMock()
        mock_embedder.embed_texts.return_value = np.array([[0.1]], dtype=np.float32)

        chunks = [{"text": "hello"}]
        embed_chunks(chunks, mock_embedder, batch_size=64)

        mock_embedder.embed_texts.assert_called_once_with(["hello"], batch_size=64)
