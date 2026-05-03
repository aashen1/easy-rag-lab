from __future__ import annotations

import uuid
from typing import Any

from loguru import logger
from qdrant_client.http.models import FieldCondition, Filter, MatchValue

from src.indexer import VectorIndexer


def index_chunks(
    chunks: list[dict[str, Any]],
    embedder: Any,
    collection_name: str = "financial_reports",
    batch_size: int = 32,
    source_filter: set | None = None,
) -> int:
    """Embed chunks and insert them into a Qdrant vector collection.

    Creates the collection if it does not already exist, generates
    embeddings via *embedder*, and upserts the chunk–embedding pairs.

    Args:
        chunks: List of chunk dictionaries, each containing at least a
            ``"text"`` key and optionally ``"chunk_id"`` and ``"metadata"``
            keys.
        embedder: An object with ``embed_texts(texts, batch_size)`` and
            ``get_embedding_dimension()`` methods.
        collection_name: Name of the Qdrant collection. Defaults to
            ``"financial_reports"``.
        batch_size: Batch size for the embedding call. Defaults to 32.
        source_filter: Optional set of source paths to filter chunks
            before indexing. Currently unused but reserved for future
            filtering logic.

    Returns:
        The number of chunks indexed.

    Raises:
        Exception: If embedding or indexing fails.
    """
    if not chunks:
        logger.warning("No chunks provided for indexing")
        return 0

    indexer: VectorIndexer | None = None
    try:
        indexer = VectorIndexer(collection_name=collection_name)

        texts = [chunk["text"] for chunk in chunks]
        embeddings = embedder.embed_texts(texts, batch_size=batch_size)

        vector_size = embedder.get_embedding_dimension()
        indexer.create_collection(vector_size=vector_size, recreate=False)

        indexer.index_chunks(chunks, embeddings, batch_size=100)

        logger.success(f"Indexed {len(chunks)} chunks into '{collection_name}'")
        return len(chunks)
    except Exception as e:
        logger.error(f"Failed to index chunks: {e}")
        raise
    finally:
        if indexer is not None:
            indexer.close()


def delete_source_and_reindex(
    source: str,
    new_chunks: list[dict[str, Any]],
    embedder: Any,
    collection_name: str = "financial_reports",
) -> int:
    """Delete vectors belonging to a source and re-insert updated chunks.

    Removes all points whose ``metadata.source`` matches *source*, then
    embeds *new_chunks* and upserts them with UUID-based point IDs.

    Args:
        source: The source identifier to match against
            ``metadata.source`` in the Qdrant payload.
        new_chunks: List of replacement chunk dictionaries (same schema
            as ``index_chunks``).
        embedder: An object with ``embed_texts(texts, batch_size)`` and
            ``get_embedding_dimension()`` methods.
        collection_name: Name of the Qdrant collection. Defaults to
            ``"financial_reports"``.

    Returns:
        The number of new chunks indexed.

    Raises:
        Exception: If deletion, embedding, or indexing fails.
    """
    indexer: VectorIndexer | None = None
    try:
        indexer = VectorIndexer(collection_name=collection_name)

        logger.info(f"Deleting vectors for source '{source}' from '{collection_name}'")
        indexer.client.delete(
            collection_name=collection_name,
            points_selector=Filter(
                must=[
                    FieldCondition(
                        key="metadata.source",
                        match=MatchValue(value=source),
                    )
                ]
            ),
        )
        logger.success(f"Deleted vectors for source '{source}'")

        if not new_chunks:
            logger.warning("No new chunks provided after deletion")
            indexer.close()
            return 0

        texts = [chunk["text"] for chunk in new_chunks]
        embeddings = embedder.embed_texts(texts, batch_size=32)

        vector_size = embedder.get_embedding_dimension()
        collection_info = indexer.get_collection_info()
        if collection_info is None:
            indexer.create_collection(vector_size=vector_size, recreate=False)

        offset = 0
        if collection_info is not None:
            offset = collection_info.get("points_count", 0)

        from qdrant_client.http.models import PointStruct

        points = []
        for i, (chunk, embedding) in enumerate(
            zip(new_chunks, embeddings, strict=False)
        ):
            point_id = str(uuid.uuid4())
            point = PointStruct(
                id=point_id,
                vector=embedding.tolist(),
                payload={
                    "chunk_id": chunk.get("chunk_id", f"chunk_{offset + i}"),
                    "text": chunk["text"],
                    "metadata": chunk.get("metadata", {}),
                },
            )
            points.append(point)

        for i in range(0, len(points), 100):
            batch = points[i : i + 100]
            indexer.client.upsert(
                collection_name=collection_name,
                points=batch,
            )

        logger.success(f"Re-indexed {len(new_chunks)} chunks for source '{source}'")
        indexer.close()
        return len(new_chunks)
    except Exception as e:
        logger.error(f"Failed to delete source and reindex: {e}")
        if indexer is not None:
            indexer.close()
        raise
