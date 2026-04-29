from typing import Any

from loguru import logger

from src.embedder import Embedder
from src.exceptions import RetrievalError
from src.indexer import VectorIndexer


class Retriever:
    def __init__(
        self,
        indexer: VectorIndexer,
        embedder: Embedder,
        top_k: int = 5,
        score_threshold: float = 0,
    ) -> None:
        """Initialize the Retriever with an indexer, embedder, and top-k setting.

        Args:
            indexer: VectorIndexer instance used to search the vector store.
            embedder: Embedder instance used to convert queries into vectors.
            top_k: Number of top results to return. Defaults to 5.
            score_threshold: Minimum similarity score for a result to be
                included. 0 means no filtering. Defaults to 0.
        """
        self.indexer = indexer
        self.embedder = embedder
        self.top_k = top_k
        self.score_threshold = score_threshold

    def retrieve(self, query: str, top_k: int | None = None) -> list[dict[str, Any]]:
        """Retrieve the top-k most relevant chunks for the given query.

        Embeds the query and searches the vector store for the closest
        matching document chunks. When ``score_threshold`` > 0, results
        with a score below the threshold are filtered out.

        Args:
            query: The search query string. Must be non-empty.
            top_k: Override the number of top results to return for this
                call. When ``None``, uses the instance-level ``self.top_k``.

        Returns:
            A list of dictionaries, each containing ``chunk_id``, ``text``,
            ``metadata``, and ``score`` keys, sorted by descending relevance.
            May contain fewer than ``top_k`` items when score threshold
            filtering is active.

        Raises:
            ValueError: If ``query`` is empty or not a string.
            Exception: If the embedding or search operation fails.
        """
        if not query or not isinstance(query, str):
            error_msg = "Query must be a non-empty string"
            logger.error(error_msg)
            raise RetrievalError(error_msg)

        effective_top_k = top_k if top_k is not None else self.top_k

        try:
            logger.info(
                f"Retrieving top-{effective_top_k} results for query: {query[:50]}..."
            )

            query_embedding = self.embedder.embed_query(query)

            search_results = self.indexer.client.query_points(
                collection_name=self.indexer.collection_name,
                query=query_embedding.tolist(),
                limit=effective_top_k,
                with_payload=True,
            ).points

            results = []
            for result in search_results:
                results.append(
                    {
                        "chunk_id": result.payload.get("chunk_id", ""),
                        "text": result.payload.get("text", ""),
                        "metadata": result.payload.get("metadata", {}),
                        "score": result.score,
                    }
                )

            if self.score_threshold > 0:
                before_count = len(results)
                results = [r for r in results if r["score"] >= self.score_threshold]
                filtered_count = before_count - len(results)
                if filtered_count > 0:
                    logger.debug(
                        f"Score threshold {self.score_threshold} filtered out "
                        f"{filtered_count} of {before_count} results"
                    )

            logger.success(f"Retrieved {len(results)} results")
            return results

        except Exception as e:
            error_msg = f"Failed to retrieve results: {str(e)}"
            logger.error(error_msg)
            raise RetrievalError(error_msg) from e
