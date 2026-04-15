from typing import List

import numpy as np
import torch
from loguru import logger
from transformers import AutoModel, AutoTokenizer


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

            self._tokenizer = AutoTokenizer.from_pretrained(model_name)
            self._model = AutoModel.from_pretrained(model_name)

            self._model.to(self.device)

            if self.use_fp16 and self.device == "cuda":
                self._model = self._model.half()

            self._model.eval()

            self.embedding_dim = self._model.config.hidden_size

            logger.success(
                f"Model loaded successfully. Embedding dimension: {self.embedding_dim}"
            )

        except Exception as e:
            error_msg = f"Failed to load embedding model {model_name}: {str(e)}"
            logger.error(error_msg)
            raise Exception(error_msg)

    def _encode_batch(
        self, texts: List[str], batch_size: int, max_length: int = 512
    ) -> np.ndarray:
        all_embeddings = []

        for i in range(0, len(texts), batch_size):
            batch_texts = texts[i : i + batch_size]

            encoded = self._tokenizer(
                batch_texts,
                padding=True,
                truncation=True,
                max_length=max_length,
                return_tensors="pt",
            )

            input_ids = encoded["input_ids"].to(self.device)
            attention_mask = encoded["attention_mask"].to(self.device)

            with torch.no_grad():
                outputs = self._model(
                    input_ids=input_ids, attention_mask=attention_mask
                )

                last_hidden_state = outputs.last_hidden_state
                cls_embeddings = last_hidden_state[:, 0, :]

                embeddings = torch.nn.functional.normalize(cls_embeddings, p=2, dim=1)

                all_embeddings.append(embeddings.cpu().numpy())

        return np.vstack(all_embeddings)

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

            embeddings = self._encode_batch(texts, batch_size)

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

            embeddings = self._encode_batch([query], batch_size=1)

            logger.debug("Query embedded successfully")

            return embeddings[0]

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
