import json
from pathlib import Path
from typing import Any

import numpy as np
import tiktoken
from loguru import logger

from src.utils import detect_document_category, ensure_dir


def _extract_headings(text: str) -> list[str]:
    """Extract Markdown headings from text.

    Args:
        text: Input text with optional Markdown headings.

    Returns:
        List of heading strings (e.g., ['# Title', '## Subtitle']).
    """
    headings = []
    for line in text.split('\n'):
        stripped = line.strip()
        if stripped.startswith('#'):
            headings.append(stripped)
    return headings


def _split_into_sentences(text: str) -> list[str]:
    """Split text into sentences using Chinese and English punctuation.

    Handles Chinese punctuation (。！？；) and English punctuation (.!?;).
    Merges very short segments with the next one to avoid noise.

    Args:
        text: Input text to split.

    Returns:
        List of sentence strings.
    """
    import re

    parts = re.split(r'(?<=[。！？；.!?;])', text)

    sentences = []
    buffer = ""
    for part in parts:
        if not part.strip():
            continue
        if buffer:
            part = buffer + part
            buffer = ""
        if len(part.strip()) < 10:
            buffer = part
            continue
        sentences.append(part.strip())

    if buffer:
        if sentences:
            sentences[-1] = sentences[-1] + buffer
        else:
            sentences.append(buffer)

    return sentences


def _split_into_paragraphs(text: str) -> list[str]:
    """Split text into paragraphs based on double newlines or headers.

    Preserves Markdown header structure for document-aware chunking.

    Args:
        text: Input text to split.

    Returns:
        List of paragraph strings.
    """
    import re

    parts = re.split(r'\n\s*\n|\n(?=#)', text)

    paragraphs = []
    for part in parts:
        stripped = part.strip()
        if stripped:
            paragraphs.append(stripped)

    return paragraphs


def _compute_sentence_similarities(
    sentences: list[str],
    embedder: Any,
) -> np.ndarray:
    """Compute cosine similarity between consecutive sentence embeddings.

    Args:
        sentences: List of sentence strings.
        embedder: Embedder instance with ``embed_texts()`` method.

    Returns:
        Array of cosine similarities between consecutive sentences.
        Length is ``len(sentences) - 1``.
    """
    if len(sentences) <= 1:
        return np.array([])

    embeddings = embedder.embed_texts(sentences)

    embeddings_array = np.array(embeddings)
    norms = np.linalg.norm(embeddings_array, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1, norms)
    normalized = embeddings_array / norms

    similarities = np.sum(normalized[:-1] * normalized[1:], axis=1)

    return similarities


def chunk_text_semantic(
    text: str,
    embedder: Any,
    chunk_size: int = 512,
    similarity_threshold: float = 0.5,
    breakpoint_percentile: float | None = None,
    min_chunk_size: int = 100,
    encoding_name: str = "cl100k_base",
) -> list[dict[str, Any]]:
    """Split text into chunks based on semantic similarity boundaries.

    Detects semantic breakpoints where the similarity between consecutive
    sentences drops below a threshold, indicating a topic shift. Falls
    back to fixed-size chunking for segments that exceed ``chunk_size``.

    Two modes for detecting breakpoints:

    - **Threshold mode** (default): Split where similarity <
      ``similarity_threshold``.
    - **Percentile mode**: Split where similarity < ``breakpoint_percentile``
      percentile of all similarities.

    Args:
        text: The input text to chunk.
        embedder: Embedder instance with ``embed_texts()`` method.
        chunk_size: Maximum tokens per chunk. Segments exceeding this
            are re-chunked with fixed-size splitting. Defaults to 512.
        similarity_threshold: Cosine similarity threshold below which
            a breakpoint is inserted. Defaults to 0.5.
        breakpoint_percentile: If set, uses this percentile of all
            similarity scores as the threshold instead of
            ``similarity_threshold``. Value in (0, 100). Defaults to None.
        min_chunk_size: Minimum tokens per chunk. Merges small chunks
            with neighbors. Defaults to 100.
        encoding_name: Tiktoken encoding for token counting.
            Defaults to "cl100k_base".

    Returns:
        List of dictionaries, each with "text" and "metadata" keys,
        following the same format as ``chunk_text()``.

    Raises:
        ValueError: If text is empty or embedder is None.
    """
    if not text or not text.strip():
        logger.warning("Empty text provided for semantic chunking")
        return []

    if embedder is None:
        raise ValueError("Embedder is required for semantic chunking")

    try:
        encoding = tiktoken.get_encoding(encoding_name)
    except Exception as e:
        error_msg = f"Failed to load tiktoken encoding {encoding_name}: {str(e)}"
        logger.error(error_msg)
        raise Exception(error_msg)

    sentences = _split_into_sentences(text)

    if len(sentences) <= 1:
        paragraphs = _split_into_paragraphs(text)
        if paragraphs:
            sentences = paragraphs
        else:
            sentences = [text]

    if len(sentences) <= 1:
        tokens = encoding.encode(text)
        return [{
            "text": text,
            "metadata": {
                "chunk_index": 0,
                "char_count": len(text),
                "token_count": len(tokens),
                "start_token": 0,
                "end_token": len(tokens),
                "strategy": "semantic",
            },
        }]

    logger.debug(f"Computing similarities for {len(sentences)} sentences...")
    similarities = _compute_sentence_similarities(sentences, embedder)

    if len(similarities) == 0:
        tokens = encoding.encode(text)
        return [{
            "text": text,
            "metadata": {
                "chunk_index": 0,
                "char_count": len(text),
                "token_count": len(tokens),
                "start_token": 0,
                "end_token": len(tokens),
                "strategy": "semantic",
            },
        }]

    if breakpoint_percentile is not None:
        threshold = np.percentile(similarities, breakpoint_percentile)
        logger.debug(f"Percentile threshold: {threshold:.4f} (p={breakpoint_percentile})")
    else:
        threshold = similarity_threshold

    breakpoints = []
    for i, sim in enumerate(similarities):
        if sim < threshold:
            breakpoints.append(i + 1)

    breakpoints = [0] + breakpoints + [len(sentences)]

    chunks = []
    chunk_index = 0
    token_offset = 0

    for i in range(len(breakpoints) - 1):
        start = breakpoints[i]
        end = breakpoints[i + 1]
        segment_text = "".join(sentences[start:end])

        segment_tokens = encoding.encode(segment_text)
        token_count = len(segment_tokens)

        if token_count > chunk_size:
            sub_chunks = _fixed_split_tokens(segment_tokens, encoding, chunk_size)
            for sub_text, sub_tokens in sub_chunks:
                chunks.append({
                    "text": sub_text,
                    "metadata": {
                        "chunk_index": chunk_index,
                        "char_count": len(sub_text),
                        "token_count": sub_tokens,
                        "start_token": token_offset,
                        "end_token": token_offset + sub_tokens,
                        "strategy": "semantic",
                    },
                })
                chunk_index += 1
                token_offset += sub_tokens
        elif token_count < min_chunk_size and chunks:
            last = chunks[-1]
            merged_text = last["text"] + segment_text
            merged_tokens = encoding.encode(merged_text)
            if len(merged_tokens) <= chunk_size:
                chunks[-1] = {
                    "text": merged_text,
                    "metadata": {
                        "chunk_index": last["metadata"]["chunk_index"],
                        "char_count": len(merged_text),
                        "token_count": len(merged_tokens),
                        "start_token": last["metadata"]["start_token"],
                        "end_token": last["metadata"]["start_token"] + len(merged_tokens),
                        "strategy": "semantic",
                    },
                }
                token_offset = last["metadata"]["start_token"] + len(merged_tokens)
            else:
                chunks.append({
                    "text": segment_text,
                    "metadata": {
                        "chunk_index": chunk_index,
                        "char_count": len(segment_text),
                        "token_count": token_count,
                        "start_token": token_offset,
                        "end_token": token_offset + token_count,
                        "strategy": "semantic",
                    },
                })
                chunk_index += 1
                token_offset += token_count
        else:
            chunks.append({
                "text": segment_text,
                "metadata": {
                    "chunk_index": chunk_index,
                    "char_count": len(segment_text),
                    "token_count": token_count,
                    "start_token": token_offset,
                    "end_token": token_offset + token_count,
                    "strategy": "semantic",
                },
            })
            chunk_index += 1
            token_offset += token_count

    logger.info(f"Semantic chunking: {len(sentences)} sentences -> {len(chunks)} chunks")
    return chunks


def _fixed_split_tokens(
    tokens: list,
    encoding: Any,
    chunk_size: int,
) -> list[tuple[str, int]]:
    """Split a token list into fixed-size sub-chunks.

    Args:
        tokens: List of token integers.
        encoding: Tiktoken encoding instance for decoding.
        chunk_size: Maximum tokens per sub-chunk.

    Returns:
        List of (decoded_text, token_count) tuples.
    """
    result = []
    start = 0
    while start < len(tokens):
        end = min(start + chunk_size, len(tokens))
        chunk_tokens = tokens[start:end]
        decoded = encoding.decode(chunk_tokens)
        result.append((decoded, len(chunk_tokens)))
        start = end
    return result


def process_parsed_files_semantic(
    input_dir: str,
    output_dir: str,
    embedder: Any,
    chunk_size: int = 512,
    similarity_threshold: float = 0.5,
    breakpoint_percentile: float | None = None,
    min_chunk_size: int = 100,
    encoding_name: str = "cl100k_base",
    source_filter: set | None = None,
) -> list[dict[str, Any]]:
    """Read parsed Markdown files and chunk them using semantic boundaries.

    This is the semantic equivalent of ``process_parsed_files()``. It
    produces JSONL output in the same format, allowing drop-in replacement
    in the RAG pipeline.

    Args:
        input_dir: Directory containing parsed Markdown files.
        output_dir: Directory where chunked JSONL files will be saved.
        embedder: Embedder instance for computing sentence similarities.
        chunk_size: Maximum tokens per chunk. Defaults to 512.
        similarity_threshold: Cosine similarity threshold for breakpoints.
            Defaults to 0.5.
        breakpoint_percentile: Percentile-based threshold. Overrides
            ``similarity_threshold`` if set. Defaults to None.
        min_chunk_size: Minimum tokens per chunk. Defaults to 100.
        encoding_name: Tiktoken encoding name. Defaults to "cl100k_base".
        source_filter: Optional set of relative paths to process.

    Returns:
        List of result dictionaries with source, output, category,
        chunk_count, and status keys.

    Raises:
        FileNotFoundError: If input_dir does not exist.
    """
    input_path = Path(input_dir)

    if not input_path.exists():
        error_msg = f"Input directory not found: {input_dir}"
        logger.error(error_msg)
        raise FileNotFoundError(error_msg)

    output_path = ensure_dir(output_dir)

    md_files = list(input_path.rglob("*.md"))

    if not md_files:
        logger.warning(f"No Markdown files found in {input_dir}")
        return []

    if source_filter is not None:
        original_count = len(md_files)
        md_files = [
            f for f in md_files if str(f.relative_to(input_path)) in source_filter
        ]
        logger.info(
            f"Source filter applied: {len(md_files)}/{original_count} files matched"
        )

    logger.info(f"Found {len(md_files)} Markdown files for semantic chunking")

    all_results = []

    for md_file in md_files:
        try:
            with open(md_file, encoding="utf-8") as f:
                text = f.read()

            chunks = chunk_text_semantic(
                text,
                embedder,
                chunk_size=chunk_size,
                similarity_threshold=similarity_threshold,
                breakpoint_percentile=breakpoint_percentile,
                min_chunk_size=min_chunk_size,
                encoding_name=encoding_name,
            )

            relative_path = md_file.relative_to(input_path)
            source_name = relative_path.stem

            category = detect_document_category(str(md_file))

            output_file = output_path / relative_path.with_suffix(".jsonl")

            output_file.parent.mkdir(parents=True, exist_ok=True)

            with open(output_file, "w", encoding="utf-8") as f:
                for chunk in chunks:
                    chunk_id = f"{source_name}::chunk::{chunk['metadata']['chunk_index']:03d}"

                    chunk_headings = _extract_headings(chunk["text"])

                    chunk_data = {
                        "chunk_id": chunk_id,
                        "text": chunk["text"],
                        "metadata": {
                            "source": str(relative_path),
                            "category": category,
                            "chunk_index": chunk["metadata"]["chunk_index"],
                            "char_count": chunk["metadata"]["char_count"],
                            "token_count": chunk["metadata"]["token_count"],
                            "start_token": chunk["metadata"]["start_token"],
                            "end_token": chunk["metadata"]["end_token"],
                            "strategy": chunk["metadata"].get("strategy", "semantic"),
                            "headings": chunk_headings,
                        },
                    }

                    f.write(json.dumps(chunk_data, ensure_ascii=False) + "\n")

            all_results.append(
                {
                    "source": str(md_file),
                    "output": str(output_file),
                    "category": category,
                    "chunk_count": len(chunks),
                    "status": "success",
                }
            )

            logger.success(
                f"Semantic chunked {md_file.name}: {len(chunks)} chunks -> {output_file.name}"
            )

        except Exception as e:
            logger.error(f"Failed to process {md_file}: {str(e)}")
            all_results.append(
                {
                    "source": str(md_file),
                    "output": None,
                    "category": None,
                    "chunk_count": 0,
                    "status": "failed",
                    "error": str(e),
                }
            )

    success_count = sum(1 for r in all_results if r["status"] == "success")
    failed_count = sum(1 for r in all_results if r["status"] == "failed")
    total_chunks = sum(r.get("chunk_count", 0) for r in all_results)

    logger.info(
        f"Semantic chunking completed: {success_count} succeeded, "
        f"{failed_count} failed, {total_chunks} total chunks"
    )

    return all_results
