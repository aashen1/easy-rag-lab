from __future__ import annotations

from typing import Any

from loguru import logger

from src.chunker import chunk_text, chunk_text_page_aware
from src.parsers.base import ParseResult
from src.semantic_chunker import chunk_text_semantic


def chunk_parsed(
    parse_result: ParseResult,
    strategy: str = "page_aware",
    chunk_size: int = 512,
    overlap: int = 0,
    encoding_name: str = "cl100k_base",
    model_name: str | None = None,
    cross_page_overlap: int = 0,
    similarity_threshold: float = 0.5,
    breakpoint_percentile: float | None = None,
    embedder: Any | None = None,
    parent_chunk_config: dict | None = None,
) -> list[dict[str, Any]]:
    """Chunk a ParseResult using the specified strategy.

    Converts the ParseResult into the format expected by the underlying
    chunking functions and dispatches to the appropriate implementation
    based on *strategy*.

    Args:
        parse_result: Parsed document output containing pages and metadata.
        strategy: Chunking strategy — one of ``"fixed"``, ``"page_aware"``,
            or ``"semantic"``. Defaults to ``"page_aware"``.
        chunk_size: Maximum number of tokens per chunk. Defaults to 512.
        overlap: Number of overlapping tokens between consecutive chunks
            within the same page. Defaults to 0.
        encoding_name: Encoding identifier for tokenization. Defaults to
            ``"cl100k_base"``.
        model_name: Hugging Face model identifier. Required when
            *encoding_name* is ``"bge"``. Defaults to None.
        cross_page_overlap: Number of tokens from the end of the previous
            page to prepend to the current page (page_aware only).
            Defaults to 0.
        similarity_threshold: Cosine similarity threshold for semantic
            breakpoints. Defaults to 0.5.
        breakpoint_percentile: Percentile-based threshold for semantic
            chunking. Overrides *similarity_threshold* if set.
            Defaults to None.
        embedder: Embedder instance with ``embed_texts()`` method.
            Required for ``"semantic"`` strategy. Defaults to None.
        parent_chunk_config: Configuration for parent-child chunk
            relationships. Not yet implemented. Defaults to None.

    Returns:
        List of chunk dictionaries, each with ``"text"`` and
        ``"metadata"`` keys. Source metadata from *parse_result* is
        merged into each chunk's metadata.

    Raises:
        ValueError: If *strategy* is not one of ``"fixed"``,
            ``"page_aware"``, or ``"semantic"``.
        ValueError: If ``"semantic"`` strategy is selected and
            *embedder* is None.
    """
    if parent_chunk_config is not None and parent_chunk_config.get("enabled"):
        logger.warning(
            "parent_chunk_config is enabled but parent chunk logic is not yet implemented; "
            "chunks will be produced without parent_id"
        )

    if strategy == "fixed":
        full_text = "\n\n".join(page.text for page in parse_result.pages)
        chunks = chunk_text(
            full_text,
            chunk_size=chunk_size,
            overlap=overlap,
            encoding_name=encoding_name,
            model_name=model_name,
        )
    elif strategy == "page_aware":
        page_chunks = [
            {"text": page.text, "metadata": page.metadata}
            for page in parse_result.pages
        ]
        source_name = parse_result.metadata.get("source", "unknown")
        chunks = chunk_text_page_aware(
            page_chunks,
            source_name=source_name,
            chunk_size=chunk_size,
            overlap=overlap,
            encoding_name=encoding_name,
            model_name=model_name,
            cross_page_overlap=cross_page_overlap,
        )
    elif strategy == "semantic":
        if embedder is None:
            raise ValueError("embedder is required for semantic chunking strategy")
        full_text = "\n\n".join(page.text for page in parse_result.pages)
        if not full_text or not full_text.strip():
            logger.warning(
                f"Empty text after joining pages for document "
                f"{parse_result.metadata.get('source', 'unknown')}"
            )
            return []
        chunks = chunk_text_semantic(
            full_text,
            embedder=embedder,
            chunk_size=chunk_size,
            similarity_threshold=similarity_threshold,
            breakpoint_percentile=breakpoint_percentile,
            encoding_name=encoding_name,
        )
    else:
        raise ValueError(
            f"Unknown chunking strategy: {strategy!r}. "
            f"Must be one of 'fixed', 'page_aware', 'semantic'."
        )

    for chunk in chunks:
        chunk["metadata"].update(parse_result.metadata)

    return chunks
