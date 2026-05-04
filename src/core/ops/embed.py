from __future__ import annotations

from typing import Any

from loguru import logger


def embed_chunks(
    chunks: list[dict[str, Any]],
    embedder: Any,
    batch_size: int = 32,
) -> list[list[float]]:
    """Generate embeddings for a list of chunk dictionaries.

    Extracts the ``text`` field from each chunk, calls
    ``embedder.embed_texts()`` to produce vector embeddings, and converts
    the resulting numpy array to a plain list-of-lists.

    Args:
        chunks: List of chunk dictionaries, each containing at least a
            ``"text"`` key.
        embedder: An object with an ``embed_texts(texts, batch_size)``
            method that returns a numpy array of shape ``(N, D)``.
        batch_size: Number of texts per embedding batch. Defaults to 32.

    Returns:
        A list of ``N`` float lists, each of length ``D`` (the embedding
        dimension).  Returns an empty list when *chunks* is empty.

    Raises:
        KeyError: If any chunk does not contain a ``"text"`` key.
        Exception: If the embedding call fails.
    """
    if not chunks:
        logger.warning("No chunks provided for embedding")
        return []

    try:
        texts = [chunk["text"] for chunk in chunks]
        embeddings = embedder.embed_texts(texts, batch_size=batch_size)
        return embeddings.tolist()
    except KeyError as e:
        logger.error(f"Chunk missing 'text' key: {e}")
        raise
    except Exception as e:
        logger.error(f"Failed to embed chunks: {e}")
        raise
