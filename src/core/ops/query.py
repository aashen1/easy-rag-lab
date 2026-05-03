from __future__ import annotations

from typing import Any

from loguru import logger


def query_rag(question: str, pipeline: Any) -> dict[str, Any]:
    """Execute a RAG query through the provided pipeline.

    Thin wrapper around ``RAGPipeline.query()`` for Phase A. Delegates
    all retrieval and generation logic to the pipeline instance.

    Args:
        question: The user question to answer. Must be a non-empty string.
        pipeline: A ``RAGPipeline`` instance (or any object with a
            ``query(question)`` method).

    Returns:
        A dictionary containing at minimum ``question`` and ``answer`` keys.
        When the pipeline returns contexts, also includes ``contexts``,
        ``scores``, ``sources``, ``chunk_ids``, and optionally ``token_usage``.

    Raises:
        AttributeError: If *pipeline* does not have a ``query`` method.
        RetrievalError: If the pipeline fails to process the question.
    """
    logger.debug(f"query_rag called with question: {question[:50]}...")
    result = pipeline.query(question)
    logger.debug("query_rag completed successfully")
    return result
