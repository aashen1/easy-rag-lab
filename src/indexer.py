import json
from pathlib import Path
from typing import Any

import numpy as np
from loguru import logger
from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, PointStruct, VectorParams

from src.embedder import Embedder
from src.exceptions import IndexingError
from src.utils import ensure_dir


class VectorIndexer:
    def __init__(
        self,
        persist_dir: str | None = None,
        collection_name: str = "financial_reports",
        distance: str = "Cosine",
    ):
        """Initialize the VectorIndexer with a local Qdrant client.

        Args:
            persist_dir: Directory path for Qdrant data persistence.
                If None, reads from config ``vector_store.persist_dir``.
            collection_name: Name of the Qdrant collection to use.
            distance: Distance metric for vector similarity. One of
                ``"Cosine"``, ``"Euclidean"``, or ``"Dot"``.

        Raises:
            Exception: If the Qdrant client fails to initialize.
        """
        if persist_dir is None:
            from src.utils import load_config

            config = load_config()
            persist_dir = config.get("vector_store", {}).get(
                "persist_dir", "data/vector_store"
            )
        self.persist_dir = Path(persist_dir)
        self.collection_name = collection_name
        self.distance = distance

        try:
            ensure_dir(str(self.persist_dir))

            logger.info(f"Initializing Qdrant client at {self.persist_dir}")
            self.client = QdrantClient(path=str(self.persist_dir))
            self._is_closed = False

            logger.success("Qdrant client initialized successfully")

        except Exception as e:
            error_msg = f"Failed to initialize Qdrant client: {str(e)}"
            logger.error(error_msg)
            raise IndexingError(error_msg) from e

    def create_collection(self, vector_size: int, recreate: bool = False) -> None:
        """Create a Qdrant collection with the specified vector size.

        If the collection already exists and ``recreate`` is False, this
        method is a no-op. If ``recreate`` is True, the existing collection
        is deleted first.

        Args:
            vector_size: Dimensionality of the vectors to store.
            recreate: Whether to delete and re-create the collection if it
                already exists. Defaults to False.

        Raises:
            Exception: If collection creation or deletion fails.
        """
        try:
            collections = self.client.get_collections().collections
            collection_names = [c.name for c in collections]

            if self.collection_name in collection_names:
                if recreate:
                    logger.info(f"Deleting existing collection: {self.collection_name}")
                    self.client.delete_collection(self.collection_name)
                else:
                    logger.info(f"Collection {self.collection_name} already exists")
                    return

            distance_map = {
                "Cosine": Distance.COSINE,
                "Euclidean": Distance.EUCLID,
                "Dot": Distance.DOT,
            }

            distance_metric = distance_map.get(self.distance, Distance.COSINE)

            logger.info(
                f"Creating collection: {self.collection_name} with vector size {vector_size}"
            )

            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(
                    size=vector_size,
                    distance=distance_metric,
                ),
            )

            logger.success(f"Collection {self.collection_name} created successfully")

        except Exception as e:
            error_msg = f"Failed to create collection: {str(e)}"
            logger.error(error_msg)
            raise IndexingError(error_msg) from e

    def index_chunks(
        self,
        chunks: list[dict[str, Any]],
        embeddings: np.ndarray,
        batch_size: int = 100,
    ) -> None:
        """Insert document chunks and their embeddings into the Qdrant collection.

        Args:
            chunks: List of chunk dictionaries, each containing at least a
                ``text`` key and optionally ``chunk_id`` and ``metadata`` keys.
            embeddings: Numpy array of shape ``(N, D)`` where N matches the
                number of chunks and D is the embedding dimension.
            batch_size: Number of points to upsert in each batch. Defaults to 100.

        Raises:
            ValueError: If the number of chunks does not match the number of
                embeddings.
            Exception: If the upsert operation fails.
        """
        if not chunks or len(embeddings) == 0:
            logger.warning("No chunks or embeddings to index")
            return

        if len(chunks) != len(embeddings):
            error_msg = f"Number of chunks ({len(chunks)}) does not match number of embeddings ({len(embeddings)})"
            logger.error(error_msg)
            raise IndexingError(error_msg)

        try:
            logger.info(f"Indexing {len(chunks)} chunks")

            points = []
            for i, (chunk, embedding) in enumerate(
                zip(chunks, embeddings, strict=False)
            ):
                point = PointStruct(
                    id=i,
                    vector=embedding.tolist(),
                    payload={
                        "chunk_id": chunk.get("chunk_id", f"chunk_{i}"),
                        "text": chunk["text"],
                        "metadata": chunk.get("metadata", {}),
                    },
                )
                points.append(point)

            for i in range(0, len(points), batch_size):
                batch = points[i : i + batch_size]
                self.client.upsert(
                    collection_name=self.collection_name,
                    points=batch,
                )
                logger.debug(
                    f"Indexed batch {i // batch_size + 1}/{(len(points) - 1) // batch_size + 1}"
                )

            logger.success(f"Successfully indexed {len(chunks)} chunks")

        except Exception as e:
            error_msg = f"Failed to index chunks: {str(e)}"
            logger.error(error_msg)
            raise IndexingError(error_msg) from e

    def build_index(
        self,
        chunks_dir: str,
        embedder: Embedder,
        batch_size: int = 32,
        rebuild: bool = False,
        source_filter: set | None = None,
        profiler: Any | None = None,
    ) -> None:
        """Load JSONL chunk files, embed their texts, and index them into Qdrant.

        Reads all ``*.jsonl`` files from ``chunks_dir``, generates embeddings
        via the provided embedder, creates (or re-creates) the collection, and
        inserts the chunks.

        Args:
            chunks_dir: Directory containing JSONL chunk files.
            embedder: Embedder instance used to generate vector embeddings.
            batch_size: Batch size for the embedding call. Defaults to 32.
            rebuild: Whether to re-create the collection from scratch.
            source_filter: Optional set of relative file paths; only JSONL
                files whose path relative to ``chunks_dir`` is in this set
                will be processed.
            profiler: Optional PipelineProfiler for stage tracking.

        Raises:
            FileNotFoundError: If ``chunks_dir`` does not exist.
            Exception: If embedding or indexing fails.
        """
        chunks_path = Path(chunks_dir)

        if not chunks_path.exists():
            error_msg = f"Chunks directory not found: {chunks_dir}"
            logger.error(error_msg)
            raise IndexingError(error_msg)

        jsonl_files = list(chunks_path.rglob("*.jsonl"))

        if not jsonl_files:
            logger.warning(f"No JSONL files found in {chunks_dir}")
            return

        if source_filter is not None:
            original_count = len(jsonl_files)
            jsonl_files = [
                f
                for f in jsonl_files
                if f.relative_to(chunks_path).as_posix() in source_filter
            ]
            logger.info(
                f"Source filter applied: {len(jsonl_files)}/{original_count} files matched"
            )

        logger.info(f"Found {len(jsonl_files)} JSONL files")

        all_chunks = []
        for jsonl_file in jsonl_files:
            try:
                with open(jsonl_file, encoding="utf-8") as f:
                    for line in f:
                        chunk = json.loads(line.strip())
                        all_chunks.append(chunk)

                logger.debug(f"Loaded {jsonl_file.name}")

            except Exception as e:
                logger.error(f"Failed to load {jsonl_file}: {str(e)}")
                continue

        if not all_chunks:
            logger.warning("No chunks found in JSONL files")
            return

        logger.info(f"Total chunks to index: {len(all_chunks)}")

        texts = [chunk["text"] for chunk in all_chunks]

        if profiler:
            profiler.begin_stage("S3")
        embeddings = embedder.embed_texts(texts, batch_size=batch_size)
        if profiler:
            profiler.end_stage()

        if profiler:
            profiler.begin_stage("S4")
        self.create_collection(
            vector_size=embedder.get_embedding_dimension(), recreate=rebuild
        )

        self.index_chunks(all_chunks, embeddings, batch_size=100)
        if profiler:
            profiler.end_stage()

    def get_collection_info(self) -> dict[str, Any] | None:
        """Retrieve metadata about the current Qdrant collection.

        Returns:
            A dictionary with ``points_count`` and ``status`` keys, or None
            if the collection does not exist or the query fails.
        """
        try:
            info = self.client.get_collection(self.collection_name)
            return {
                "points_count": info.points_count,
                "status": info.status.value,
            }
        except Exception as e:
            logger.warning(
                f"Collection not found or unavailable: {self.collection_name} ({str(e)})"
            )
            return None

    def delete_collection(self) -> None:
        """Delete the current Qdrant collection.

        Raises:
            Exception: If the collection deletion fails.
        """
        try:
            logger.info(f"Deleting collection: {self.collection_name}")
            self.client.delete_collection(self.collection_name)
            logger.success(f"Collection {self.collection_name} deleted successfully")
        except Exception as e:
            error_msg = f"Failed to delete collection: {str(e)}"
            logger.error(error_msg)
            raise IndexingError(error_msg) from e

    def close(self) -> None:
        """Close the Qdrant client and release associated resources."""
        try:
            if hasattr(self, "client") and self.client is not None:
                self.client.close()
                self._is_closed = True
                logger.info(
                    f"Qdrant client closed for collection: {self.collection_name}"
                )
        except Exception as e:
            logger.warning(f"Error closing Qdrant client: {str(e)}")

    def is_closed(self) -> bool:
        """Check if the Qdrant client is closed.

        Returns:
            True if the client is closed, False otherwise.
        """
        return self._is_closed

    def reopen(self) -> None:
        """Reopen the Qdrant client if it was closed.

        This is useful when reusing a cached indexer across multiple variants.
        """
        if self._is_closed:
            logger.info(
                f"Reopening Qdrant client for collection: {self.collection_name}"
            )
            self.client = QdrantClient(path=str(self.persist_dir))
            self._is_closed = False
            logger.success("Qdrant client reopened successfully")
