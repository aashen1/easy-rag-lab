from typing import Any, Dict, List

from loguru import logger
from qdrant_client.http.models import PointStruct

from src.embedder import Embedder
from src.indexer import VectorIndexer


class Retriever:
    def __init__(
        self,
        indexer: VectorIndexer,
        embedder: Embedder,
        top_k: int = 5,
    ):
        self.indexer = indexer
        self.embedder = embedder
        self.top_k = top_k

    def retrieve(self, query: str) -> List[Dict[str, Any]]:
        if not query or not isinstance(query, str):
            error_msg = "Query must be a non-empty string"
            logger.error(error_msg)
            raise ValueError(error_msg)

        try:
            logger.info(f"Retrieving top-{self.top_k} results for query: {query[:50]}...")

            query_embedding = self.embedder.embed_query(query)

            search_results = self.indexer.client.query_points(
                collection_name=self.indexer.collection_name,
                query=query_embedding.tolist(),
                limit=self.top_k,
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

            logger.success(f"Retrieved {len(results)} results")
            return results

        except Exception as e:
            error_msg = f"Failed to retrieve results: {str(e)}"
            logger.error(error_msg)
            raise Exception(error_msg)


if __name__ == "__main__":
    from src.utils import load_config, setup_logger

    config = load_config()
    setup_logger(config)

    embedding_config = config["embedding"]
    vector_store_config = config["vector_store"]
    retrieval_config = config["retrieval"]

    embedder = Embedder(
        model_name=embedding_config["model_name"],
        device=embedding_config["device"],
    )

    indexer = VectorIndexer(
        persist_dir=vector_store_config["persist_dir"],
        collection_name=vector_store_config["collection_name"],
        distance=vector_store_config["distance"],
    )

    retriever = Retriever(
        indexer=indexer,
        embedder=embedder,
        top_k=retrieval_config["top_k"],
    )

    query = "贵州茅台2023年的营业收入是多少？"
    results = retriever.retrieve(query)

    for i, result in enumerate(results, 1):
        logger.info(f"\nResult {i}:")
        logger.info(f"Score: {result['score']:.4f}")
        logger.info(f"Text: {result['text'][:100]}...")
        logger.info(f"Source: {result['metadata'].get('source', 'Unknown')}")
