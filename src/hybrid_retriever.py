from typing import Any

from loguru import logger

from src.bm25_retriever import BM25Retriever
from src.exceptions import RetrievalError
from src.retriever import Retriever


class HybridRetriever:
    def __init__(
        self,
        vector_retriever: Retriever,
        bm25_retriever: BM25Retriever,
        fusion_method: str = "rrf",
        rrf_k: int = 60,
        vector_weight: float = 0.7,
        bm25_weight: float = 0.3,
        top_k: int = 5,
    ) -> None:
        """Initialize the Hybrid Retriever combining vector and BM25 search.

        Supports two fusion strategies:

        - **RRF (Reciprocal Rank Fusion)**: Combines results based on rank
          positions. Robust to score scale differences between retrievers.
          Formula: ``score = 1 / (k + rank)`` for each retriever, then summed.

        - **Weighted**: Normalizes each retriever's scores to [0, 1] and
          combines with configurable weights. Sensitive to score distributions.

        Args:
            vector_retriever: Vector-based Retriever instance.
            bm25_retriever: BM25Retriever instance.
            fusion_method: Fusion strategy, either ``"rrf"`` or ``"weighted"``.
                Defaults to ``"rrf"``.
            rrf_k: Constant k for RRF formula. Higher values dampen the
                impact of high rankings. Defaults to 60.
            vector_weight: Weight for vector retriever scores in weighted
                fusion. Defaults to 0.7.
            bm25_weight: Weight for BM25 retriever scores in weighted
                fusion. Defaults to 0.3.
            top_k: Number of top results to return. Defaults to 5.

        Raises:
            ValueError: If fusion_method is not ``"rrf"`` or ``"weighted"``.
            ValueError: If vector_weight + bm25_weight is close to zero.
        """
        if fusion_method not in ("rrf", "weighted"):
            raise RetrievalError(
                f"fusion_method must be 'rrf' or 'weighted', got '{fusion_method}'"
            )

        if abs(vector_weight + bm25_weight) < 1e-9:
            raise RetrievalError("vector_weight + bm25_weight must not be zero")

        self.vector_retriever = vector_retriever
        self.bm25_retriever = bm25_retriever
        self.fusion_method = fusion_method
        self.rrf_k = rrf_k
        self.vector_weight = vector_weight
        self.bm25_weight = bm25_weight
        self.top_k = top_k

    def retrieve(self, query: str, top_k: int | None = None) -> list[dict[str, Any]]:
        """Retrieve the top-k results using hybrid fusion of vector and BM25.

        Executes both retrieval strategies, fuses their results using the
        configured fusion method, and returns the top-k combined results.

        Args:
            query: The search query string. Must be non-empty.
            top_k: Override the number of top results to return for this
                call. When ``None``, uses the instance-level ``self.top_k``.

        Returns:
            A list of dictionaries, each containing ``chunk_id``, ``text``,
            ``metadata``, and ``score`` keys, sorted by descending relevance.

        Raises:
            ValueError: If ``query`` is empty or not a string.
            Exception: If retrieval or fusion fails.
        """
        if not query or not isinstance(query, str):
            error_msg = "Query must be a non-empty string"
            logger.error(error_msg)
            raise RetrievalError(error_msg)

        effective_top_k = top_k if top_k is not None else self.top_k

        try:
            logger.info(
                f"Hybrid retrieving (method={self.fusion_method}, "
                f"top_k={effective_top_k}) for query: {query[:50]}..."
            )

            fetch_k = effective_top_k * 3

            vector_results = self.vector_retriever.retrieve(query)
            bm25_results = self.bm25_retriever.retrieve(query, top_k=fetch_k)

            if self.fusion_method == "rrf":
                results = self._rrf_fusion(
                    vector_results, bm25_results, effective_top_k
                )
            else:
                results = self._weighted_fusion(
                    vector_results, bm25_results, effective_top_k
                )

            logger.success(f"Hybrid retrieved {len(results)} results")
            return results

        except Exception as e:
            error_msg = f"Failed to retrieve hybrid results: {str(e)}"
            logger.error(error_msg)
            raise RetrievalError(error_msg) from e

    def _rrf_fusion(
        self,
        vector_results: list[dict[str, Any]],
        bm25_results: list[dict[str, Any]],
        top_k: int,
    ) -> list[dict[str, Any]]:
        """Fuse results using Reciprocal Rank Fusion (RRF).

        Each document's RRF score is the sum of ``1 / (k + rank)`` across
        all retrievers that returned it. Documents appearing in both
        retrievers get higher combined scores.

        Args:
            vector_results: Results from the vector retriever.
            bm25_results: Results from the BM25 retriever.
            top_k: Number of top results to return after fusion.

        Returns:
            Top-k fused results sorted by descending RRF score.
        """
        rrf_scores: dict[str, float] = {}
        doc_data: dict[str, dict[str, Any]] = {}

        for rank, result in enumerate(vector_results, 1):
            chunk_id = result["chunk_id"]
            rrf_scores[chunk_id] = rrf_scores.get(chunk_id, 0.0) + 1.0 / (
                self.rrf_k + rank
            )
            if chunk_id not in doc_data:
                doc_data[chunk_id] = {
                    "chunk_id": chunk_id,
                    "text": result["text"],
                    "metadata": result["metadata"],
                }

        for rank, result in enumerate(bm25_results, 1):
            chunk_id = result["chunk_id"]
            rrf_scores[chunk_id] = rrf_scores.get(chunk_id, 0.0) + 1.0 / (
                self.rrf_k + rank
            )
            if chunk_id not in doc_data:
                doc_data[chunk_id] = {
                    "chunk_id": chunk_id,
                    "text": result["text"],
                    "metadata": result["metadata"],
                }

        sorted_ids = sorted(
            rrf_scores.keys(), key=lambda x: rrf_scores[x], reverse=True
        )

        results = []
        for chunk_id in sorted_ids[:top_k]:
            entry = doc_data[chunk_id].copy()
            entry["score"] = rrf_scores[chunk_id]
            results.append(entry)

        return results

    def _weighted_fusion(
        self,
        vector_results: list[dict[str, Any]],
        bm25_results: list[dict[str, Any]],
        top_k: int,
    ) -> list[dict[str, Any]]:
        """Fuse results using weighted score combination.

        Normalizes each retriever's scores to [0, 1] using min-max
        normalization, then combines with the configured weights.

        Args:
            vector_results: Results from the vector retriever.
            bm25_results: Results from the BM25 retriever.
            top_k: Number of top results to return after fusion.

        Returns:
            Top-k fused results sorted by descending weighted score.
        """
        combined_scores: dict[str, float] = {}
        doc_data: dict[str, dict[str, Any]] = {}

        vector_scores = {r["chunk_id"]: r["score"] for r in vector_results}
        bm25_scores = {r["chunk_id"]: r["score"] for r in bm25_results}

        norm_vector = self._normalize_scores(vector_scores)
        norm_bm25 = self._normalize_scores(bm25_scores)

        all_chunk_ids = set(vector_scores.keys()) | set(bm25_scores.keys())

        for chunk_id in all_chunk_ids:
            v_score = norm_vector.get(chunk_id, 0.0)
            b_score = norm_bm25.get(chunk_id, 0.0)

            combined_scores[chunk_id] = (
                self.vector_weight * v_score + self.bm25_weight * b_score
            )

        for result in vector_results:
            if result["chunk_id"] not in doc_data:
                doc_data[result["chunk_id"]] = {
                    "chunk_id": result["chunk_id"],
                    "text": result["text"],
                    "metadata": result["metadata"],
                }

        for result in bm25_results:
            if result["chunk_id"] not in doc_data:
                doc_data[result["chunk_id"]] = {
                    "chunk_id": result["chunk_id"],
                    "text": result["text"],
                    "metadata": result["metadata"],
                }

        sorted_ids = sorted(
            combined_scores.keys(), key=lambda x: combined_scores[x], reverse=True
        )

        results = []
        for chunk_id in sorted_ids[:top_k]:
            entry = doc_data[chunk_id].copy()
            entry["score"] = combined_scores[chunk_id]
            results.append(entry)

        return results

    @staticmethod
    def _normalize_scores(scores: dict[str, float]) -> dict[str, float]:
        """Normalize scores to [0, 1] using min-max scaling.

        If all scores are equal, returns 1.0 for each to avoid
        division by zero.

        Args:
            scores: Dictionary mapping chunk IDs to raw scores.

        Returns:
            Dictionary mapping chunk IDs to normalized scores in [0, 1].
        """
        if not scores:
            return {}

        values = list(scores.values())
        min_score = min(values)
        max_score = max(values)
        score_range = max_score - min_score

        if score_range < 1e-9:
            return {k: 1.0 for k in scores}

        return {k: (v - min_score) / score_range for k, v in scores.items()}
