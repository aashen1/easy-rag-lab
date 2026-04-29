from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from src.bm25_retriever import BM25Retriever
from src.hybrid_retriever import HybridRetriever
from src.retriever import Retriever


@dataclass
class RetrievalResult:
    chunks: list[dict[str, Any]]
    scores: list[float] = field(default_factory=list)


class RetrievalStrategy(ABC):
    @abstractmethod
    def retrieve(self, query: str, top_k: int, **kwargs) -> RetrievalResult: ...


class VectorRetrievalStrategy(RetrievalStrategy):
    def __init__(self, retriever: Retriever) -> None:
        self._retriever = retriever

    def retrieve(self, query: str, top_k: int, **kwargs) -> RetrievalResult:
        chunks = self._retriever.retrieve(query, top_k=top_k)
        return RetrievalResult(chunks=chunks)


class BM25RetrievalStrategy(RetrievalStrategy):
    def __init__(self, retriever: BM25Retriever) -> None:
        self._retriever = retriever

    def retrieve(self, query: str, top_k: int, **kwargs) -> RetrievalResult:
        chunks = self._retriever.retrieve(query, top_k=top_k)
        return RetrievalResult(chunks=chunks)


class HybridRetrievalStrategy(RetrievalStrategy):
    def __init__(self, retriever: HybridRetriever) -> None:
        self._retriever = retriever

    def retrieve(self, query: str, top_k: int, **kwargs) -> RetrievalResult:
        chunks = self._retriever.retrieve(query, top_k=top_k)
        return RetrievalResult(chunks=chunks)
