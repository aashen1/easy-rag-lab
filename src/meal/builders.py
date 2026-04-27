from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger

if TYPE_CHECKING:
    from src.indexer import VectorIndexer


def build_chunks_if_needed(
    parsed_dir: Path,
    chunks_dir: Path,
    chunker_config: dict[str, Any],
    model_name: str | None = None,
    force: bool = False,
) -> None:
    """
    Build chunks from parsed files if no chunk files exist.

    Automatically detects whether parsed results are in .pages.json format
    (page-level output) or .md format, and selects the appropriate chunking
    path accordingly.

    Args:
        parsed_dir: Directory containing parsed files (.md or .pages.json).
        chunks_dir: Target directory for chunked files (.jsonl).
        chunker_config: Chunker configuration dictionary.
        model_name: Hugging Face model identifier for BGE tokenizer.
            Required when chunker encoding is "bge". Defaults to None.
        force: If True, delete existing chunks and rebuild from scratch.
    """
    if not force and chunks_dir.exists() and any(chunks_dir.rglob("*.jsonl")):
        return

    if force and chunks_dir.exists():
        import shutil

        logger.info(f"Force overwrite: clearing existing chunks in {chunks_dir}")
        shutil.rmtree(chunks_dir, ignore_errors=True)

    logger.info("Chunking documents...")

    encoding_name = chunker_config.get("encoding", "cl100k_base")
    has_pages_json = parsed_dir.exists() and any(parsed_dir.rglob("*.pages.json"))

    if has_pages_json:
        from src.chunker import process_parsed_files_page_aware

        source_filter = set()
        for pages_file in parsed_dir.rglob("*.pages.json"):
            rel = pages_file.relative_to(parsed_dir).as_posix()
            source_filter.add(rel)

        process_parsed_files_page_aware(
            input_dir=str(parsed_dir),
            output_dir=str(chunks_dir),
            chunk_size=chunker_config.get("chunk_size", 512),
            overlap=chunker_config.get("chunk_overlap", 0),
            encoding_name=encoding_name,
            source_filter=source_filter,
            model_name=model_name,
            cross_page_overlap=chunker_config.get("cross_page_overlap", 0),
        )
    else:
        from src.chunker import process_parsed_files

        source_filter_md = set()
        if parsed_dir.exists():
            for md_file in parsed_dir.rglob("*.md"):
                rel = md_file.relative_to(parsed_dir).as_posix()
                source_filter_md.add(rel)

        process_parsed_files(
            input_dir=str(parsed_dir),
            output_dir=str(chunks_dir),
            chunk_size=chunker_config.get("chunk_size", 512),
            overlap=chunker_config.get("chunk_overlap", 0),
            encoding_name=encoding_name,
            source_filter=source_filter_md,
            model_name=model_name,
        )


def build_index_from_chunks(
    chunks_dir: Path,
    embedding_config: dict[str, Any],
    vector_store_config: dict[str, Any],
    collection_name: str,
) -> VectorIndexer:
    """
    Build vector index from chunks directory.

    Args:
        chunks_dir: Directory containing chunked files (.jsonl).
        embedding_config: Embedding configuration dictionary.
        vector_store_config: Vector store configuration dictionary.
        collection_name: Name of the collection to create/use.

    Returns:
        Configured VectorIndexer instance with index built.
    """
    from src.embedder import Embedder
    from src.indexer import VectorIndexer

    source_filter_jsonl = set()
    if chunks_dir.exists():
        for jsonl_file in chunks_dir.rglob("*.jsonl"):
            rel = jsonl_file.relative_to(chunks_dir).as_posix()
            source_filter_jsonl.add(rel)

    embedder = Embedder(
        model_name=embedding_config.get("model_name"),
        device=embedding_config.get("device", "cpu"),
    )

    indexer = VectorIndexer(
        persist_dir=vector_store_config.get("persist_dir", "data/vector_store"),
        collection_name=collection_name,
        distance=vector_store_config.get("distance", "Cosine"),
    )

    indexer.build_index(
        chunks_dir=str(chunks_dir),
        embedder=embedder,
        batch_size=embedding_config.get("batch_size", 32),
        rebuild=True,
        source_filter=source_filter_jsonl,
    )

    return indexer
