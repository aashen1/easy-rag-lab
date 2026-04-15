import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
from loguru import logger
from qdrant_client import QdrantClient
from qdrant_client.http import models
from qdrant_client.http.models import Distance, PointStruct, VectorParams

from src.embedder import Embedder
from src.utils import ensure_dir


class VectorIndexer:
    def __init__(
        self,
        persist_dir: str = "data/vector_store",
        collection_name: str = "financial_reports",
        distance: str = "Cosine",
    ):
        self.persist_dir = Path(persist_dir)
        self.collection_name = collection_name
        self.distance = distance

        try:
            ensure_dir(str(self.persist_dir))

            logger.info(f"Initializing Qdrant client at {self.persist_dir}")
            self.client = QdrantClient(path=str(self.persist_dir))

            logger.success("Qdrant client initialized successfully")

        except Exception as e:
            error_msg = f"Failed to initialize Qdrant client: {str(e)}"
            logger.error(error_msg)
            raise Exception(error_msg)

    def create_collection(
        self, vector_size: int, recreate: bool = False
    ) -> None:
        try:
            collections = self.client.get_collections().collections
            collection_names = [c.name for c in collections]

            if self.collection_name in collection_names:
                if recreate:
                    logger.info(
                        f"Deleting existing collection: {self.collection_name}")
                    self.client.delete_collection(self.collection_name)
                else:
                    logger.info(
                        f"Collection {self.collection_name} already exists")
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

            logger.success(
                f"Collection {self.collection_name} created successfully")

        except Exception as e:
            error_msg = f"Failed to create collection: {str(e)}"
            logger.error(error_msg)
            raise Exception(error_msg)

    def index_chunks(
        self, chunks: List[Dict[str, Any]], embeddings: np.ndarray, batch_size: int = 100
    ) -> None:
        if not chunks or len(embeddings) == 0:
            logger.warning("No chunks or embeddings to index")
            return

        if len(chunks) != len(embeddings):
            error_msg = f"Number of chunks ({len(chunks)}) does not match number of embeddings ({len(embeddings)})"
            logger.error(error_msg)
            raise ValueError(error_msg)

        try:
            logger.info(f"Indexing {len(chunks)} chunks")

            points = []
            for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
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
                batch = points[i: i + batch_size]
                self.client.upsert(
                    collection_name=self.collection_name,
                    points=batch,
                )
                logger.debug(
                    f"Indexed batch {i // batch_size + 1}/{(len(points) - 1) // batch_size + 1}")

            logger.success(f"Successfully indexed {len(chunks)} chunks")

        except Exception as e:
            error_msg = f"Failed to index chunks: {str(e)}"
            logger.error(error_msg)
            raise Exception(error_msg)

    def build_index(
        self,
        chunks_dir: str,
        embedder: Embedder,
        batch_size: int = 32,
        rebuild: bool = False,
    ) -> None:
        chunks_path = Path(chunks_dir)

        if not chunks_path.exists():
            error_msg = f"Chunks directory not found: {chunks_dir}"
            logger.error(error_msg)
            raise FileNotFoundError(error_msg)

        jsonl_files = list(chunks_path.rglob("*.jsonl"))

        if not jsonl_files:
            logger.warning(f"No JSONL files found in {chunks_dir}")
            return

        logger.info(f"Found {len(jsonl_files)} JSONL files")

        all_chunks = []
        for jsonl_file in jsonl_files:
            try:
                with open(jsonl_file, "r", encoding="utf-8") as f:
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
        embeddings = embedder.embed_texts(texts, batch_size=batch_size)

        self.create_collection(
            vector_size=embedder.get_embedding_dimension(), recreate=rebuild
        )

        self.index_chunks(all_chunks, embeddings, batch_size=100)

    def get_collection_info(self) -> Optional[Dict[str, Any]]:
        try:
            info = self.client.get_collection(self.collection_name)
            return {
                "points_count": info.points_count,
                "status": info.status.value,
            }
        except Exception as e:
            logger.error(f"Failed to get collection info: {str(e)}")
            return None

    def delete_collection(self) -> None:
        try:
            logger.info(f"Deleting collection: {self.collection_name}")
            self.client.delete_collection(self.collection_name)
            logger.success(
                f"Collection {self.collection_name} deleted successfully")
        except Exception as e:
            error_msg = f"Failed to delete collection: {str(e)}"
            logger.error(error_msg)
            raise Exception(error_msg)


if __name__ == "__main__":
    from src.utils import load_config, setup_logger

    config = load_config()
    setup_logger(config)

    vector_store_config = config["vector_store"]
    embedding_config = config["embedding"]

    indexer = VectorIndexer(
        persist_dir=vector_store_config["persist_dir"],
        collection_name=vector_store_config["collection_name"],
        distance=vector_store_config["distance"],
    )

    embedder = Embedder(
        model_name=embedding_config["model_name"],
        device=embedding_config["device"],
    )

    indexer.build_index(
        chunks_dir=config["chunker"]["output_dir"],
        embedder=embedder,
        batch_size=embedding_config["batch_size"],
        rebuild=True,
    )

    info = indexer.get_collection_info()
    logger.info(f"Collection info: {info}")
