import os

# 设置 HuggingFace Hub 为离线模式，避免模型加载时尝试从网络下载
# 这对于已经预先下载好模型的离线环境非常有用
os.environ["HF_HUB_OFFLINE"] = "1"

from typing import Any

import numpy as np
import torch
from loguru import logger
from tqdm import tqdm
from transformers import AutoModel, AutoTokenizer

from src.exceptions import ConfigurationError, IndexingError


class Embedder:
    _tokenizer_cache: dict[str, Any] = {}

    def __init__(
        self,
        model_name: str = "BAAI/bge-large-zh-v1.5",
        device: str = "cuda",
        use_fp16: bool = True,
        query_instruction: str | None = None,
    ):
        """Initialize the Embedder by loading a transformer model and tokenizer.

        Falls back to CPU automatically when CUDA is not available.

        Args:
            model_name: Hugging Face model identifier for the embedding model.
            device: Device to run inference on (``"cuda"`` or ``"cpu"``).
            use_fp16: Whether to use half-precision on CUDA. Ignored on CPU.
            query_instruction: Instruction prefix prepended to queries in
                ``embed_query()``. When ``None`` (default), auto-detects BGE
                models and uses the recommended Chinese instruction; for
                non-BGE models defaults to ``None`` (no prefix). An explicit
                value (including empty string ``""``) overrides auto-detection.

        Raises:
            Exception: If the model or tokenizer fails to load.
        """
        self.model_name = model_name
        self.device = device
        self.use_fp16 = use_fp16

        if query_instruction is not None:
            self.query_instruction = query_instruction
        elif "bge" in model_name.lower():
            self.query_instruction = "为这个句子生成表示以用于检索相关文章："
        else:
            self.query_instruction = None

        try:
            logger.info(f"Loading embedding model: {model_name}")

            if device == "cuda" and not torch.cuda.is_available():
                logger.warning("CUDA not available, falling back to CPU")
                self.device = "cpu"

            self._tokenizer = AutoTokenizer.from_pretrained(model_name)
            Embedder._tokenizer_cache[model_name] = self._tokenizer
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
            raise IndexingError(error_msg) from e

    @classmethod
    def get_tokenizer(cls, model_name: str = "BAAI/bge-large-zh-v1.5") -> AutoTokenizer:
        """Get or create a tokenizer for the specified model.

        Returns a cached tokenizer if one exists (e.g., from an
        already-initialized Embedder instance), otherwise creates a
        standalone tokenizer without loading the full model.

        Args:
            model_name: Hugging Face model identifier. Defaults to
                ``"BAAI/bge-large-zh-v1.5"``.

        Returns:
            An ``AutoTokenizer`` instance for the specified model.

        Raises:
            Exception: If the tokenizer fails to load.
        """
        if model_name not in cls._tokenizer_cache:
            try:
                logger.info(f"Loading standalone tokenizer for: {model_name}")
                cls._tokenizer_cache[model_name] = AutoTokenizer.from_pretrained(
                    model_name
                )
                logger.success(f"Standalone tokenizer loaded for: {model_name}")
            except Exception as e:
                error_msg = f"Failed to load tokenizer for {model_name}: {str(e)}"
                logger.error(error_msg)
                raise Exception(error_msg) from e
        return cls._tokenizer_cache[model_name]

    def _encode_batch(
        self,
        texts: list[str],
        batch_size: int,
        max_length: int = 512,
        show_progress: bool = False,
    ) -> np.ndarray:
        """Encode a list of texts into normalized CLS embeddings in batches.

        Uses the model's CLS token representation and L2-normalizes the
        output vectors.

        Args:
            texts: List of text strings to encode.
            batch_size: Number of texts per forward pass.
            max_length: Maximum token length for truncation. Defaults to 512.
            show_progress: If True, display a tqdm progress bar over batches.

        Returns:
            A numpy array of shape ``(len(texts), embedding_dim)`` with
            L2-normalized row vectors.
        """
        all_embeddings = []

        batch_range = range(0, len(texts), batch_size)
        if show_progress:
            batch_range = tqdm(batch_range, desc="Embedding", unit="batch")
        for i in batch_range:
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
        self, texts: list[str], batch_size: int = 32, show_progress: bool = False
    ) -> np.ndarray:
        """Generate embeddings for a list of document texts.

        Args:
            texts: List of text strings to embed. All items must be strings.
            batch_size: Number of texts per encoding batch. Defaults to 32.
            show_progress: If True, display a tqdm progress bar during embedding.

        Returns:
            A numpy array of shape ``(len(texts), embedding_dim)``. Returns an
            empty array if ``texts`` is empty.

        Raises:
            ValueError: If any item in ``texts`` is not a string.
            Exception: If the encoding process fails.
        """
        if not texts:
            logger.warning("Empty text list provided for embedding")
            return np.array([])

        if not all(isinstance(text, str) for text in texts):
            error_msg = "All items in texts must be strings"
            logger.error(error_msg)
            raise ConfigurationError(error_msg)

        try:
            logger.info(f"Embedding {len(texts)} texts with batch size {batch_size}")

            embeddings = self._encode_batch(
                texts, batch_size, show_progress=show_progress
            )

            logger.success(f"Successfully embedded {len(texts)} texts")

            return embeddings

        except Exception as e:
            error_msg = f"Failed to embed texts: {str(e)}"
            logger.error(error_msg)
            raise IndexingError(error_msg) from e

    def embed_query(self, query: str) -> np.ndarray:
        """Generate an embedding for a single query string.

        If ``self.query_instruction`` is set, it is prepended to the query
        before encoding. This is recommended for BGE models to improve
        retrieval quality.

        Args:
            query: The query text to embed. Must be a non-empty string.

        Returns:
            A 1-D numpy array of shape ``(embedding_dim,)`` representing the
            L2-normalized query embedding.

        Raises:
            ValueError: If ``query`` is empty or not a string.
            Exception: If the encoding process fails.
        """
        if not query or not isinstance(query, str):
            error_msg = "Query must be a non-empty string"
            logger.error(error_msg)
            raise ConfigurationError(error_msg)

        try:
            prefixed_query = query
            if self.query_instruction:
                prefixed_query = self.query_instruction + query
                logger.debug(f"Prepended query instruction to query: {query[:30]}...")

            logger.debug(f"Embedding query: {query[:50]}...")

            embeddings = self._encode_batch([prefixed_query], batch_size=1)

            logger.debug("Query embedded successfully")

            return embeddings[0]

        except Exception as e:
            error_msg = f"Failed to embed query: {str(e)}"
            logger.error(error_msg)
            raise IndexingError(error_msg) from e

    def get_embedding_dimension(self) -> int:
        """Return the embedding dimension of the loaded model.

        Returns:
            The hidden size (embedding dimension) as an integer.
        """
        return self.embedding_dim


if __name__ == "__main__":
    from src.utils import load_config, setup_logger

    config = load_config()
    setup_logger(config)

    embedding_config = config["embedding"]

    embedder = Embedder(
        model_name=embedding_config["model_name"],
        device=embedding_config["device"],
        query_instruction=embedding_config.get("query_instruction"),
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
