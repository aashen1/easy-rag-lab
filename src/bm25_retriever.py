import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

import jieba
from loguru import logger


class BM25Retriever:
    def __init__(
        self,
        k1: float = 1.5,
        b: float = 0.75,
        epsilon: float = 0.25,
    ) -> None:
        """Initialize the BM25 retriever with Okapi BM25 parameters.

        Args:
            k1: Term frequency saturation parameter. Controls how quickly
                term frequency reaches saturation. Defaults to 1.5.
            b: Length normalization parameter. 0 means no normalization,
                1 means full normalization. Defaults to 0.75.
            epsilon: Floor value for IDF to prevent negative scores for
                very common terms. Defaults to 0.25.

        Raises:
            ValueError: If k1 is negative or b is not in [0, 1].
        """
        if k1 < 0:
            raise ValueError(f"k1 must be non-negative, got {k1}")
        if not 0 <= b <= 1:
            raise ValueError(f"b must be in [0, 1], got {b}")

        self.k1 = k1
        self.b = b
        self.epsilon = epsilon

        self._corpus_tokens: list[list[str]] = []
        self._corpus_size: int = 0
        self._avgdl: float = 0.0
        self._doc_freqs: dict[str, int] = defaultdict(int)
        self._doc_lens: list[int] = []
        self._idf: dict[str, float] = {}
        self._doc_data: list[dict[str, Any]] = []
        self._is_indexed: bool = False

    @staticmethod
    def tokenize(text: str) -> list[str]:
        """Tokenize Chinese text using jieba segmentation.

        Filters out whitespace and single-character tokens to reduce
        noise in BM25 scoring.

        Args:
            text: Input text string to tokenize.

        Returns:
            List of token strings after jieba segmentation and filtering.
        """
        tokens = jieba.lcut(text)
        return [t.strip() for t in tokens if t.strip() and len(t.strip()) > 1]

    def build_index_from_chunks(
        self,
        chunks_dir: str,
        source_filter: set | None = None,
    ) -> None:
        """Build BM25 index from JSONL chunk files.

        Reads all ``*.jsonl`` files from ``chunks_dir``, tokenizes each
        chunk's text, and computes document frequencies and IDF values.

        Args:
            chunks_dir: Directory containing JSONL chunk files.
            source_filter: Optional set of relative file paths; only JSONL
                files whose path relative to ``chunks_dir`` is in this set
                will be processed.

        Raises:
            FileNotFoundError: If ``chunks_dir`` does not exist.
            Exception: If index building fails.
        """
        chunks_path = Path(chunks_dir)

        if not chunks_path.exists():
            error_msg = f"Chunks directory not found: {chunks_dir}"
            logger.error(error_msg)
            raise FileNotFoundError(error_msg)

        jsonl_files = list(chunks_path.rglob("*.jsonl"))

        if not jsonl_files:
            logger.warning(f"No JSONL files found in {chunks_dir}")
            return

        if source_filter is not None:
            original_count = len(jsonl_files)
            jsonl_files = [
                f for f in jsonl_files if str(f.relative_to(chunks_path)) in source_filter
            ]
            logger.info(
                f"Source filter applied: {len(jsonl_files)}/{original_count} files matched"
            )

        all_chunks: list[dict[str, Any]] = []
        for jsonl_file in jsonl_files:
            try:
                with open(jsonl_file, encoding="utf-8") as f:
                    for line in f:
                        chunk = json.loads(line.strip())
                        all_chunks.append(chunk)
            except Exception as e:
                logger.error(f"Failed to load {jsonl_file}: {str(e)}")
                continue

        if not all_chunks:
            logger.warning("No chunks found in JSONL files")
            return

        logger.info(f"Building BM25 index from {len(all_chunks)} chunks...")
        self.build_index(all_chunks)
        logger.success(f"BM25 index built: {self._corpus_size} documents, avgdl={self._avgdl:.1f}")

    def build_index(self, chunks: list[dict[str, Any]]) -> None:
        """Build BM25 index from a list of chunk dictionaries.

        Each chunk must contain a ``text`` key and optionally ``chunk_id``
        and ``metadata`` keys.

        Args:
            chunks: List of chunk dictionaries to index.

        Raises:
            ValueError: If chunks is empty.
        """
        if not chunks:
            raise ValueError("Cannot build BM25 index from empty chunks list")

        self._corpus_tokens = []
        self._doc_data = []
        self._doc_freqs = defaultdict(int)
        self._doc_lens = []

        for chunk in chunks:
            text = chunk.get("text", "")
            tokens = self.tokenize(text)

            self._corpus_tokens.append(tokens)
            self._doc_lens.append(len(tokens))
            self._doc_data.append({
                "chunk_id": chunk.get("chunk_id", ""),
                "text": text,
                "metadata": chunk.get("metadata", {}),
            })

            token_set = set(tokens)
            for token in token_set:
                self._doc_freqs[token] += 1

        self._corpus_size = len(chunks)
        self._avgdl = sum(self._doc_lens) / self._corpus_size if self._corpus_size > 0 else 0.0

        self._compute_idf()
        self._is_indexed = True

    def _compute_idf(self) -> None:
        """Compute inverse document frequency for all terms in the corpus.

        Uses the standard BM25 IDF formula:
            IDF(t) = ln((N - df(t) + 0.5) / (df(t) + 0.5) + 1)

        Terms with negative IDF are clamped to ``epsilon * avg_idf``
        to prevent very common terms from dominating scores.
        """
        idf_sum = 0.0
        negative_idfs: list[str] = []

        for term, df in self._doc_freqs.items():
            idf = math.log((self._corpus_size - df + 0.5) / (df + 0.5) + 1)
            self._idf[term] = idf
            idf_sum += idf

            if idf < 0:
                negative_idfs.append(term)

        avg_idf = idf_sum / len(self._idf) if self._idf else 0.0
        eps = self.epsilon * avg_idf

        for term in negative_idfs:
            self._idf[term] = eps

    def retrieve(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        """Retrieve the top-k most relevant chunks for the given query.

        Scores each document against the query using the Okapi BM25
        formula and returns the top-k results sorted by descending score.

        Args:
            query: The search query string. Must be non-empty.
            top_k: Number of top results to return. Defaults to 5.

        Returns:
            A list of dictionaries, each containing ``chunk_id``, ``text``,
            ``metadata``, and ``score`` keys, sorted by descending relevance.

        Raises:
            ValueError: If ``query`` is empty or not a string.
            RuntimeError: If the index has not been built yet.
        """
        if not query or not isinstance(query, str):
            error_msg = "Query must be a non-empty string"
            logger.error(error_msg)
            raise ValueError(error_msg)

        if not self._is_indexed:
            error_msg = "BM25 index not built. Call build_index() or build_index_from_chunks() first."
            logger.error(error_msg)
            raise RuntimeError(error_msg)

        try:
            query_tokens = self.tokenize(query)

            if not query_tokens:
                logger.warning(f"Query produced no tokens after tokenization: {query[:50]}")
                return []

            scores = self._score(query_tokens)

            scored_docs = list(enumerate(scores))
            scored_docs.sort(key=lambda x: x[1], reverse=True)

            top_docs = scored_docs[:top_k]

            results = []
            for doc_idx, score in top_docs:
                if score <= 0:
                    continue
                doc = self._doc_data[doc_idx]
                results.append({
                    "chunk_id": doc["chunk_id"],
                    "text": doc["text"],
                    "metadata": doc["metadata"],
                    "score": float(score),
                })

            logger.success(f"BM25 retrieved {len(results)} results for query: {query[:50]}...")
            return results

        except Exception as e:
            error_msg = f"Failed to retrieve results: {str(e)}"
            logger.error(error_msg)
            raise Exception(error_msg) from e

    def _score(self, query_tokens: list[str]) -> list[float]:
        """Compute BM25 scores for all documents against the query tokens.

        Args:
            query_tokens: List of tokenized query terms.

        Returns:
            List of BM25 scores, one per document in the corpus.
        """
        scores = [0.0] * self._corpus_size

        for token in query_tokens:
            if token not in self._idf:
                continue

            idf = self._idf[token]

            for doc_idx in range(self._corpus_size):
                doc_tokens = self._corpus_tokens[doc_idx]
                tf = doc_tokens.count(token)
                dl = self._doc_lens[doc_idx]

                numerator = tf * (self.k1 + 1)
                denominator = tf + self.k1 * (1 - self.b + self.b * dl / self._avgdl)

                scores[doc_idx] += idf * numerator / denominator

        return scores

    def get_corpus_size(self) -> int:
        """Return the number of documents in the BM25 index.

        Returns:
            Number of indexed documents.
        """
        return self._corpus_size

    def is_indexed(self) -> bool:
        """Check whether the BM25 index has been built.

        Returns:
            True if the index is ready for queries, False otherwise.
        """
        return self._is_indexed


if __name__ == "__main__":
    from src.utils import load_config, setup_logger

    config = load_config()
    setup_logger(config)

    retriever = BM25Retriever()
    retriever.build_index_from_chunks(config["chunker"]["output_dir"])

    query = "贵州茅台2023年的营业收入是多少？"
    results = retriever.retrieve(query, top_k=5)

    for i, result in enumerate(results, 1):
        logger.info(f"\nResult {i}:")
        logger.info(f"Score: {result['score']:.4f}")
        logger.info(f"Text: {result['text'][:100]}...")
        logger.info(f"Source: {result['metadata'].get('source', 'Unknown')}")
