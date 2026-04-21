from typing import Any

import torch
from loguru import logger
from transformers import AutoModelForSequenceClassification, AutoTokenizer


class Reranker:
    def __init__(
        self,
        model_name: str = "BAAI/bge-reranker-large",
        device: str = "cuda",
        use_fp16: bool = True,
        max_length: int = 512,
    ) -> None:
        """Initialize the Reranker with a cross-encoder model.

        Loads a sequence classification model (cross-encoder) for
        re-ranking query-document pairs. Falls back to CPU when CUDA
        is not available.

        Args:
            model_name: Hugging Face model identifier for the cross-encoder.
                Defaults to ``"BAAI/bge-reranker-large"``.
            device: Device for inference (``"cuda"`` or ``"cpu"``).
            use_fp16: Whether to use half-precision on CUDA. Ignored on CPU.
            max_length: Maximum token length for input pairs. Defaults to 512.

        Raises:
            Exception: If the model or tokenizer fails to load.
        """
        self.model_name = model_name
        self.device = device
        self.use_fp16 = use_fp16
        self.max_length = max_length

        try:
            logger.info(f"Loading reranker model: {model_name}")

            if device == "cuda" and not torch.cuda.is_available():
                logger.warning("CUDA not available, falling back to CPU")
                self.device = "cpu"

            self._tokenizer = AutoTokenizer.from_pretrained(model_name)
            self._model = AutoModelForSequenceClassification.from_pretrained(model_name)

            self._model.to(self.device)

            if self.use_fp16 and self.device == "cuda":
                self._model = self._model.half()

            self._model.eval()

            logger.success(f"Reranker model loaded successfully on {self.device}")

        except Exception as e:
            error_msg = f"Failed to load reranker model {model_name}: {str(e)}"
            logger.error(error_msg)
            raise Exception(error_msg)

    def rerank(
        self,
        query: str,
        results: list[dict[str, Any]],
        top_n: int | None = None,
    ) -> list[dict[str, Any]]:
        """Re-rank retrieval results using the cross-encoder model.

        Scores each query-document pair with the cross-encoder, sorts by
        descending relevance score, and returns the top-n results.

        Args:
            query: The search query string. Must be non-empty.
            results: List of retrieval result dictionaries, each containing
                at least a ``text`` key and optionally ``chunk_id`` and
                ``metadata`` keys.
            top_n: Number of top results to return after re-ranking. If None,
                returns all results in re-ranked order. Defaults to None.

        Returns:
            A list of dictionaries with the same structure as input, plus
            a ``rerank_score`` key containing the cross-encoder score.
            Sorted by descending ``rerank_score``.

        Raises:
            ValueError: If ``query`` is empty or ``results`` is empty.
            Exception: If the scoring process fails.
        """
        if not query or not isinstance(query, str):
            error_msg = "Query must be a non-empty string"
            logger.error(error_msg)
            raise ValueError(error_msg)

        if not results:
            logger.warning("No results to rerank")
            return []

        try:
            logger.info(f"Reranking {len(results)} results for query: {query[:50]}...")

            pairs = [(query, result["text"]) for result in results]

            scores = self._score_pairs(pairs)

            for i, score in enumerate(scores):
                results[i]["rerank_score"] = float(score)

            reranked = sorted(results, key=lambda x: x["rerank_score"], reverse=True)

            if top_n is not None:
                reranked = reranked[:top_n]

            logger.success(f"Reranked results: top-{len(reranked)} selected")
            return reranked

        except Exception as e:
            error_msg = f"Failed to rerank results: {str(e)}"
            logger.error(error_msg)
            raise Exception(error_msg)

    def _score_pairs(self, pairs: list[tuple]) -> list[float]:
        """Score query-document pairs using the cross-encoder model.

        Processes pairs in batches for efficiency.

        Args:
            pairs: List of (query, document) tuples.

        Returns:
            List of relevance scores, one per pair.
        """
        all_scores = []
        batch_size = 16

        for i in range(0, len(pairs), batch_size):
            batch_pairs = pairs[i : i + batch_size]

            queries = [p[0] for p in batch_pairs]
            documents = [p[1] for p in batch_pairs]

            encoded = self._tokenizer(
                queries,
                documents,
                padding=True,
                truncation=True,
                max_length=self.max_length,
                return_tensors="pt",
            )

            input_ids = encoded["input_ids"].to(self.device)
            attention_mask = encoded["attention_mask"].to(self.device)

            with torch.no_grad():
                outputs = self._model(
                    input_ids=input_ids,
                    attention_mask=attention_mask,
                )
                logits = outputs.logits.squeeze(-1)
                batch_scores = logits.cpu().float().tolist()

            if isinstance(batch_scores, float):
                batch_scores = [batch_scores]

            all_scores.extend(batch_scores)

        return all_scores


if __name__ == "__main__":
    from src.utils import load_config, setup_logger

    config = load_config()
    setup_logger(config)

    reranker = Reranker()

    query = "贵州茅台2023年的营业收入是多少？"
    mock_results = [
        {"chunk_id": "c1", "text": "贵州茅台2023年营业收入达到1500亿元", "metadata": {"source": "moutai.md"}, "score": 0.95},
        {"chunk_id": "c2", "text": "五粮液2023年实现营业收入832亿元", "metadata": {"source": "wuliangye.md"}, "score": 0.80},
        {"chunk_id": "c3", "text": "白酒行业整体增速放缓", "metadata": {"source": "industry.md"}, "score": 0.60},
    ]

    reranked = reranker.rerank(query, mock_results, top_n=2)

    for i, result in enumerate(reranked, 1):
        logger.info(f"\nResult {i}:")
        logger.info(f"Rerank Score: {result['rerank_score']:.4f}")
        logger.info(f"Original Score: {result['score']:.4f}")
        logger.info(f"Text: {result['text'][:100]}...")
