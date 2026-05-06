from __future__ import annotations

from typing import Any

from loguru import logger

from src.chunker import chunk_text, chunk_text_page_aware
from src.parsers.base import ParsedPage, ParseResult
from src.semantic_chunker import chunk_text_semantic


def _parse_result_from_pages_json(
    pages_data: list[dict[str, Any]], source: str
) -> ParseResult:
    """Convert .pages.json file data into a ParseResult.

    Args:
        pages_data: List of page dictionaries from a .pages.json file.
            Each dict should contain ``"text"`` and ``"metadata"`` keys.
        source: Source identifier (typically the file stem) to embed in
            the ParseResult metadata.

    Returns:
        A ParseResult with one ParsedPage per entry in *pages_data*.
    """
    pages = []
    for entry in pages_data:
        page_number = entry.get("metadata", {}).get("page_number", 0)
        pages.append(
            ParsedPage(
                page_number=page_number,
                text=entry.get("text", ""),
                metadata=entry.get("metadata", {}),
            )
        )
    return ParseResult(pages=pages, metadata={"source": source})


def _parse_result_from_md(text: str, source: str) -> ParseResult:
    """Convert a Markdown text blob into a single-page ParseResult.

    Args:
        text: The full Markdown text content.
        source: Source identifier (typically the file stem) to embed in
            the ParseResult metadata.

    Returns:
        A ParseResult with a single ParsedPage containing *text*.
    """
    return ParseResult(
        pages=[ParsedPage(page_number=1, text=text, metadata={})],
        metadata={"source": source},
    )


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
    min_chunk_size: int = 100,
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
        min_chunk_size: Minimum tokens per chunk for semantic strategy.
            Merges small chunks with neighbors. Defaults to 100.
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
            min_chunk_size=min_chunk_size,
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
