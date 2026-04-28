from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from loguru import logger

from src.query_rewriter import QueryRewriter


@dataclass
class RewrittenQuery:
    queries: list[str]
    is_multi: bool = False


class QueryRewriteStrategy(ABC):
    @abstractmethod
    def rewrite(self, query: str, **kwargs) -> RewrittenQuery: ...


class NoRewriteStrategy(QueryRewriteStrategy):
    def rewrite(self, query: str, **kwargs) -> RewrittenQuery:
        return RewrittenQuery(queries=[query])


class HyDERewriteStrategy(QueryRewriteStrategy):
    def __init__(self, rewriter: QueryRewriter) -> None:
        self._rewriter = rewriter

    def rewrite(self, query: str, **kwargs) -> RewrittenQuery:
        logger.debug("Rewriting query...")
        result = self._rewriter.rewrite(query)
        logger.info("HyDE: using hypothetical answer for retrieval")
        return RewrittenQuery(queries=[result["rewritten"]])


class MultiQueryRewriteStrategy(QueryRewriteStrategy):
    def __init__(self, rewriter: QueryRewriter) -> None:
        self._rewriter = rewriter

    def rewrite(self, query: str, **kwargs) -> RewrittenQuery:
        logger.debug("Rewriting query...")
        result = self._rewriter.rewrite(query)
        return RewrittenQuery(queries=result["rewritten"], is_multi=True)
