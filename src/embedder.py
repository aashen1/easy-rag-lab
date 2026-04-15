from typing import List, Optional

import numpy as np
import torch
from FlagEmbedding import FlagModel
from loguru import logger


class Embedder:
    def __init__(
        self,
        model_name: str = "BAAI/bge-large-zh-v1.5",
        device: str = "cuda",
        use_fp16: bool = True,
    ):
        self.model_name = model_name
        self.device = device
        self.use_fp16 = use_fp16

        try:
            logger.info(f"Loading embedding model: {model_name}")

            if device == "cuda" and not torch.cuda.is_available():
                logger.warning("CUDA not available, falling back to CPU")
                self.device = "cpu"

            self.model = FlagModel(
                model_name,
                normalize_embeddings=True,
                use_fp16=use_fp16 if self.device == "cuda" else False,
            )

            self.embedding_dim = self.model.model.config.hidden_size

            logger.success(
                f"Model loaded successfully. Embedding dimension: {self.embedding_dim}"
            )

        except Exception as e:
            error_msg = f"Failed to load embedding model {model_name}: {str(e)}"
            logger.error(error_msg)
            raise Exception(error_msg)

    def embed_texts(
        self, texts: List[str], batch_size: int = 32, show_progress: bool = False
    ) -> np.ndarray:
        if not texts:
            logger.warning("Empty text list provided for embedding")
            return np.array([])

        if not all(isinstance(text, str) for text in texts):
            error_msg = "All items in texts must be strings"
            logger.error(error_msg)
            raise ValueError(error_msg)

        try:
            logger.info(f"Embedding {len(texts)} texts with batch size {batch_size}")

            embeddings = self.model.encode(
                texts,
                batch_size=batch_size,
                max_length=512,
                return_numpy=True,
                convert_to_numpy=True,
            )

            logger.success(f"Successfully embedded {len(texts)} texts")

            return embeddings

        except Exception as e:
            error_msg = f"Failed to embed texts: {str(e)}"
            logger.error(error_msg)
            raise Exception(error_msg)

    def embed_query(self, query: str) -> np.ndarray:
        if not query or not isinstance(query, str):
            error_msg = "Query must be a non-empty string"
            logger.error(error_msg)
            raise ValueError(error_msg)

        try:
            logger.debug(f"Embedding query: {query[:50]}...")

            embedding = self.model.encode(
                [query],
                batch_size=1,
                max_length=512,
                return_numpy=True,
                convert_to_numpy=True,
            )

            logger.debug("Query embedded successfully")

            return embedding[0]

        except Exception as e:
            error_msg = f"Failed to embed query: {str(e)}"
            logger.error(error_msg)
            raise Exception(error_msg)

    def get_embedding_dimension(self) -> int:
        return self.embedding_dim


if __name__ == "__main__":
    from src.utils import load_config, setup_logger

    config = load_config()
    setup_logger(config)

    embedding_config = config["embedding"]

    embedder = Embedder(
        model_name=embedding_config["model_name"],
        device=embedding_config["device"],
    )

    test_texts = [
        "这是一个测试句子。",
        "这是另一个测试句子。",
        "贵州茅台2023年营业收入为1500亿元。",
    ]

    embeddings = embedder.embed_texts(
        test_texts, batch_size=embedding_config["batch_size"]
    )

    logger.info(f"Embeddings shape: {embeddings.shape}")
    logger.info(f"Embedding dimension: {embedder.get_embedding_dimension()}")

    query = "茅台的营业收入是多少？"
    query_embedding = embedder.embed_query(query)
    logger.info(f"Query embedding shape: {query_embedding.shape}")
