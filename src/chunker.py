import json
from pathlib import Path
from typing import Any

import tiktoken
from loguru import logger

from src.exceptions import ParsingError
from src.utils import detect_document_category, ensure_dir


class BGETokenizerEncoder:
    """Wrapper around a HuggingFace tokenizer that mimics tiktoken's Encoding interface.

    Provides ``encode`` and ``decode`` methods compatible with how
    ``chunk_text()`` uses tiktoken, allowing the chunker to split text
    using the same tokenizer as the embedding model.

    Args:
        model_name: Hugging Face model identifier used to load the
            tokenizer via ``AutoTokenizer``.

    Raises:
        Exception: If the tokenizer cannot be loaded and tiktoken
            fallback also fails.
    """

    def __init__(self, model_name: str) -> None:
        self._model_name = model_name
        self._tokenizer: Any = None

    def _ensure_tokenizer(self) -> Any:
        """Lazily load the tokenizer on first use.

        Returns:
            The loaded ``AutoTokenizer`` instance.

        Raises:
            Exception: If the tokenizer fails to load.
        """
        if self._tokenizer is not None:
            return self._tokenizer

        try:
            from src.embedder import Embedder

            self._tokenizer = Embedder.get_tokenizer(self._model_name)
            logger.info(f"BGETokenizerEncoder loaded tokenizer for: {self._model_name}")
        except Exception as e:
            error_msg = f"Failed to load BGE tokenizer for {self._model_name}: {str(e)}"
            logger.error(error_msg)
            raise Exception(error_msg) from e

        return self._tokenizer

    def encode(self, text: str) -> list[int]:
        """Tokenize text into a list of token IDs.

        Args:
            text: The input text to tokenize.

        Returns:
            List of integer token IDs.
        """
        tokenizer = self._ensure_tokenizer()
        return tokenizer.encode(text, add_special_tokens=False)

    def decode(self, tokens: list[int]) -> str:
        """Decode a list of token IDs back into text.

        Args:
            tokens: List of integer token IDs to decode.

        Returns:
            The decoded text string.
        """
        tokenizer = self._ensure_tokenizer()
        return tokenizer.decode(tokens, skip_special_tokens=True)


_bge_encoder_cache: dict[str, BGETokenizerEncoder] = {}


def _get_bge_encoder(model_name: str) -> BGETokenizerEncoder:
    """Get or create a cached BGETokenizerEncoder for the given model.

    Args:
        model_name: Hugging Face model identifier.

    Returns:
        A cached ``BGETokenizerEncoder`` instance.
    """
    if model_name not in _bge_encoder_cache:
        _bge_encoder_cache[model_name] = BGETokenizerEncoder(model_name)
    return _bge_encoder_cache[model_name]


def _get_encoding(encoding_name: str, model_name: str | None = None) -> Any:
    """Resolve an encoding object from the encoding name.

    When *encoding_name* is ``"bge"``, returns a
    ``BGETokenizerEncoder`` wrapping the HuggingFace tokenizer for
    *model_name*.  Otherwise delegates to ``tiktoken.get_encoding()``.

    Args:
        encoding_name: Encoding identifier — ``"bge"`` for the BGE
            tokenizer, or any tiktoken encoding name (e.g.
            ``"cl100k_base"``).
        model_name: Hugging Face model identifier.  Required when
            *encoding_name* is ``"bge"``.  Ignored for tiktoken
            encodings.

    Returns:
        An encoding object with ``encode`` and ``decode`` methods.

    Raises:
        ValueError: If *encoding_name* is ``"bge"`` and *model_name*
            is not provided.
        Exception: If the encoding cannot be loaded.
    """
    if encoding_name == "bge":
        if not model_name:
            error_msg = (
                "model_name is required when encoding is 'bge'. "
                "Set chunker.model_name or embedding.model_name in config."
            )
            logger.error(error_msg)
            raise ValueError(error_msg)
        return _get_bge_encoder(model_name)

    try:
        return tiktoken.get_encoding(encoding_name)
    except Exception as e:
        error_msg = f"Failed to load tiktoken encoding {encoding_name}: {str(e)}"
        logger.error(error_msg)
        raise Exception(error_msg) from e


def _extract_headings(text: str) -> list[str]:
    """Extract Markdown headings from text.

    Args:
        text: Input text with optional Markdown headings.

    Returns:
        List of heading strings (e.g., ['# Title', '## Subtitle']).
    """
    headings = []
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("#"):
            headings.append(stripped)
    return headings


def _build_token_char_offsets(
    encoding: Any, tokens: list[int], text: str
) -> list[tuple[int, int]]:
    """Build a mapping from token indices to character offsets in *text*.

    For each token, decodes it individually to determine its character
    length, then accumulates offsets so that ``token_char_offsets[i]``
    gives the ``(start_char, end_char)`` range in the original text.

    This avoids the encoding corruption that can occur when
    ``encoding.decode(tokens[start:end])`` splits a multi-byte UTF-8
    character across chunk boundaries (BUG-024).

    Args:
        encoding: A tiktoken or BGETokenizerEncoder object with
            ``decode`` method.
        tokens: List of token IDs produced by ``encoding.encode(text)``.
        text: The original text that was tokenized.

    Returns:
        List of ``(start_char, end_char)`` tuples, one per token.
    """
    offsets: list[tuple[int, int]] = []
    char_pos = 0
    for i in range(len(tokens)):
        token_text = encoding.decode(tokens[i : i + 1])
        start_char = char_pos
        end_char = char_pos + len(token_text)
        offsets.append((start_char, end_char))
        char_pos = end_char
    return offsets


def chunk_text(
    text: str,
    chunk_size: int = 512,
    overlap: int = 0,
    encoding_name: str = "cl100k_base",
    model_name: str | None = None,
) -> list[dict[str, Any]]:
    """Split text into fixed-size chunks based on token count.

    Uses the specified encoding to tokenize the input text, then slices
    the token sequence into overlapping or non-overlapping chunks.
    Chunk text is extracted directly from the original text using
    character offsets derived from token boundaries, which avoids
    encoding corruption when chunk boundaries split multi-byte UTF-8
    characters (BUG-024).

    When *encoding_name* is ``"bge"``, the HuggingFace tokenizer from
    the embedding model is used so that token counts align with the
    embedder's ``max_length``.

    Args:
        text: The input text to chunk.
        chunk_size: Maximum number of tokens per chunk. Defaults to 512.
        overlap: Number of tokens to overlap between consecutive chunks.
            Must be less than chunk_size. Defaults to 0.
        encoding_name: Encoding identifier — ``"bge"`` for the BGE
            tokenizer, or any tiktoken encoding name (e.g.
            ``"cl100k_base"``).  Defaults to ``"cl100k_base"``.
        model_name: Hugging Face model identifier.  Required when
            *encoding_name* is ``"bge"``.  Ignored for tiktoken
            encodings.  Defaults to None.

    Returns:
        List of dictionaries, each with a "text" key containing the chunk
        text (a substring of the original text) and a "metadata" key with
        chunk_index, char_count, token_count, start_token, and end_token.

    Raises:
        ValueError: If overlap is greater than or equal to chunk_size, or
            if *encoding_name* is ``"bge"`` and *model_name* is not provided.
        Exception: If the encoding cannot be loaded.
    """
    if not text or not text.strip():
        logger.warning("Empty text provided for chunking")
        return []

    if overlap >= chunk_size:
        error_msg = f"Overlap ({overlap}) must be less than chunk_size ({chunk_size})"
        logger.error(error_msg)
        raise ParsingError(error_msg)

    encoding = _get_encoding(encoding_name, model_name)

    tokens = encoding.encode(text)
    total_tokens = len(tokens)

    if total_tokens == 0:
        logger.warning("Text encoded to zero tokens")
        return []

    token_char_offsets = _build_token_char_offsets(encoding, tokens, text)

    chunks = []
    chunk_index = 0
    start = 0

    while start < total_tokens:
        end = min(start + chunk_size, total_tokens)

        char_start = token_char_offsets[start][0]
        char_end = token_char_offsets[end - 1][1]
        chunk_text_decoded = text[char_start:char_end]

        char_count = len(chunk_text_decoded)
        token_count = end - start

        chunks.append(
            {
                "text": chunk_text_decoded,
                "metadata": {
                    "chunk_index": chunk_index,
                    "char_count": char_count,
                    "token_count": token_count,
                    "start_token": start,
                    "end_token": end,
                },
            }
        )

        chunk_index += 1

        if end >= total_tokens:
            break

        start = end - overlap if overlap > 0 else end

    return chunks


def process_parsed_files(
    input_dir: str,
    output_dir: str,
    chunk_size: int = 512,
    overlap: int = 0,
    encoding_name: str = "cl100k_base",
    source_filter: set | None = None,
    model_name: str | None = None,
) -> list[dict[str, Any]]:
    """Read parsed Markdown files, chunk them, and save results as JSONL.

    Scans the input directory for .md files, applies optional source
    filtering, chunks each file's text, and writes the chunked output
    to JSONL files in the output directory.

    Args:
        input_dir: Directory containing parsed Markdown files.
        output_dir: Directory where chunked JSONL files will be saved.
        chunk_size: Maximum number of tokens per chunk. Defaults to 512.
        overlap: Number of overlapping tokens between consecutive chunks.
            Defaults to 0.
        encoding_name: Encoding identifier — ``"bge"`` for the BGE
            tokenizer, or any tiktoken encoding name.  Defaults to
            ``"cl100k_base"``.
        source_filter: Optional set of relative path strings; only files
            whose relative path is in this set will be processed.
        model_name: Hugging Face model identifier.  Required when
            *encoding_name* is ``"bge"``.  Defaults to None.

    Returns:
        List of result dictionaries, each containing source, output,
        category, chunk_count, and status keys (plus error on failure).

    Raises:
        FileNotFoundError: If input_dir does not exist.
    """
    input_path = Path(input_dir)

    if not input_path.exists():
        error_msg = f"Input directory not found: {input_dir}"
        logger.error(error_msg)
        raise ParsingError(error_msg)

    output_path = ensure_dir(output_dir)

    md_files = list(input_path.rglob("*.md"))

    if not md_files:
        logger.warning(f"No Markdown files found in {input_dir}")
        return []

    if source_filter is not None:
        original_count = len(md_files)
        md_files = [
            f for f in md_files if f.relative_to(input_path).as_posix() in source_filter
        ]
        logger.info(
            f"Source filter applied: {len(md_files)}/{original_count} files matched"
        )

    logger.info(f"Found {len(md_files)} Markdown files to process")

    all_results = []

    for md_file in md_files:
        try:
            with open(md_file, encoding="utf-8") as f:
                text = f.read()

            chunks = chunk_text(text, chunk_size, overlap, encoding_name, model_name)

            relative_path = md_file.relative_to(input_path)
            source_name = relative_path.stem

            category = detect_document_category(str(md_file))

            output_file = output_path / relative_path.with_suffix(".jsonl")

            output_file.parent.mkdir(parents=True, exist_ok=True)

            with open(output_file, "w", encoding="utf-8") as f:
                for chunk in chunks:
                    chunk_id = (
                        f"{source_name}::chunk::{chunk['metadata']['chunk_index']:03d}"
                    )

                    chunk_headings = _extract_headings(chunk["text"])

                    chunk_data = {
                        "chunk_id": chunk_id,
                        "text": chunk["text"],
                        "metadata": {
                            "source": relative_path.as_posix(),
                            "category": category,
                            "chunk_index": chunk["metadata"]["chunk_index"],
                            "char_count": chunk["metadata"]["char_count"],
                            "token_count": chunk["metadata"]["token_count"],
                            "start_token": chunk["metadata"]["start_token"],
                            "end_token": chunk["metadata"]["end_token"],
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

            logger.debug(
                f"Processed {md_file.name}: {len(chunks)} chunks -> {output_file.name}"
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
        f"Chunking completed: {success_count} succeeded, {failed_count} failed, {total_chunks} total chunks"
    )

    return all_results


def chunk_text_page_aware(
    page_chunks: list[dict],
    source_name: str,
    chunk_size: int = 512,
    overlap: int = 0,
    encoding_name: str = "cl100k_base",
    model_name: str | None = None,
    cross_page_overlap: int = 0,
) -> list[dict[str, Any]]:
    """Split page-level parsed results into chunks with page metadata.

    Each page is chunked independently by default. When *cross_page_overlap*
    is greater than zero, the last *cross_page_overlap* tokens of the
    previous page are prepended to the current page before chunking so that
    information spanning page boundaries is preserved.

    Args:
        page_chunks: List of page dictionaries from parse_pdf(page_chunks=True).
            Each dict must contain "text" and "metadata" keys.
        source_name: Base name for chunk_id generation (e.g. filename stem).
        chunk_size: Maximum number of tokens per chunk. Defaults to 512.
        overlap: Number of tokens to overlap between consecutive chunks within
            the same page. Must be less than chunk_size. Defaults to 0.
        encoding_name: Encoding identifier — ``"bge"`` for the BGE
            tokenizer, or any tiktoken encoding name.  Defaults to
            ``"cl100k_base"``.
        model_name: Hugging Face model identifier.  Required when
            *encoding_name* is ``"bge"``.  Defaults to None.
        cross_page_overlap: Number of tokens from the end of the previous
            page to prepend to the current page before chunking.  Must be
            non-negative and less than *chunk_size*.  Defaults to 0 (no
            cross-page overlap, backward compatible).

    Returns:
        List of dictionaries, each with "text" and "metadata" keys. Metadata
        includes "page_number", "chunk_index", "char_count", "token_count",
        "start_token", and "end_token".  When *cross_page_overlap* > 0,
        chunks that contain overlap from the previous page additionally
        include "cross_page" (True) and "overlap_from_page" (the source
        page number).

    Raises:
        ValueError: If overlap is greater than or equal to chunk_size, or
            if cross_page_overlap is negative or greater than or equal to
            chunk_size.
    """
    if overlap >= chunk_size:
        error_msg = f"Overlap ({overlap}) must be less than chunk_size ({chunk_size})"
        logger.error(error_msg)
        raise ParsingError(error_msg)

    if cross_page_overlap < 0:
        error_msg = f"cross_page_overlap ({cross_page_overlap}) must be non-negative"
        logger.error(error_msg)
        raise ValueError(error_msg)

    if cross_page_overlap >= chunk_size:
        error_msg = (
            f"cross_page_overlap ({cross_page_overlap}) must be less than "
            f"chunk_size ({chunk_size})"
        )
        logger.error(error_msg)
        raise ValueError(error_msg)

    all_chunks: list[dict[str, Any]] = []
    encoding = (
        _get_encoding(encoding_name, model_name) if cross_page_overlap > 0 else None
    )
    prev_page_overlap_text: str | None = None
    prev_page_number: int | None = None

    for page in page_chunks:
        text = page.get("text", "")
        page_number = page.get("metadata", {}).get("page_number", 0)

        if not text or not text.strip():
            logger.debug(f"Skipping empty page {page_number}")
            continue

        if cross_page_overlap > 0 and prev_page_overlap_text is not None:
            separator = "\n"
            combined_text = prev_page_overlap_text + separator + text

            overlap_prefix_tokens = encoding.encode(  # type: ignore[union-attr]
                prev_page_overlap_text + separator
            )
            overlap_prefix_token_count = len(overlap_prefix_tokens)

            page_chunks_result = chunk_text(
                combined_text, chunk_size, overlap, encoding_name, model_name
            )

            for chunk in page_chunks_result:
                chunk["metadata"]["page_number"] = page_number
                chunk_index = chunk["metadata"]["chunk_index"]
                chunk["metadata"]["chunk_index"] = f"p{page_number}_{chunk_index:03d}"

                if chunk["metadata"]["start_token"] < overlap_prefix_token_count:
                    chunk["metadata"]["cross_page"] = True
                    chunk["metadata"]["overlap_from_page"] = prev_page_number
        else:
            page_chunks_result = chunk_text(
                text, chunk_size, overlap, encoding_name, model_name
            )

            for chunk in page_chunks_result:
                chunk["metadata"]["page_number"] = page_number
                chunk_index = chunk["metadata"]["chunk_index"]
                chunk["metadata"]["chunk_index"] = f"p{page_number}_{chunk_index:03d}"

        if cross_page_overlap > 0:
            tokens = encoding.encode(text)  # type: ignore[union-attr]
            if len(tokens) > cross_page_overlap:
                offsets = _build_token_char_offsets(encoding, tokens, text)  # type: ignore[arg-type]
                char_start = offsets[len(tokens) - cross_page_overlap][0]
                char_end = offsets[-1][1]
                prev_page_overlap_text = text[char_start:char_end]
            else:
                prev_page_overlap_text = text
            prev_page_number = page_number

        all_chunks.extend(page_chunks_result)

    logger.info(
        f"Created {len(all_chunks)} page-aware chunks from {len(page_chunks)} pages"
    )
    return all_chunks


def process_parsed_files_page_aware(
    input_dir: str,
    output_dir: str,
    chunk_size: int = 512,
    overlap: int = 0,
    encoding_name: str = "cl100k_base",
    source_filter: set | None = None,
    model_name: str | None = None,
    cross_page_overlap: int = 0,
) -> list[dict[str, Any]]:
    """Read .pages.json files, apply page-aware chunking, save as JSONL.

    Scans the input directory for .pages.json files (produced by
    parse_all_pdfs with page_chunks=True), applies page-aware chunking
    to each file, and writes the chunked output to JSONL files.

    Args:
        input_dir: Directory containing .pages.json files.
        output_dir: Directory where chunked JSONL files will be saved.
        chunk_size: Maximum number of tokens per chunk. Defaults to 512.
        overlap: Number of overlapping tokens between consecutive chunks.
            Defaults to 0.
        encoding_name: Encoding identifier — ``"bge"`` for the BGE
            tokenizer, or any tiktoken encoding name.  Defaults to
            ``"cl100k_base"``.
        source_filter: Optional set of relative path strings; only files
            whose relative path is in this set will be processed.
        model_name: Hugging Face model identifier.  Required when
            *encoding_name* is ``"bge"``.  Defaults to None.
        cross_page_overlap: Number of tokens from the end of the previous
            page to prepend to the current page before chunking.  Defaults
            to 0 (no cross-page overlap).

    Returns:
        List of result dictionaries, each containing source, output,
        category, chunk_count, and status keys (plus error on failure).

    Raises:
        FileNotFoundError: If input_dir does not exist.
    """
    input_path = Path(input_dir)

    if not input_path.exists():
        error_msg = f"Input directory not found: {input_dir}"
        logger.error(error_msg)
        raise ParsingError(error_msg)

    output_path = ensure_dir(output_dir)

    pages_files = list(input_path.rglob("*.pages.json"))

    if not pages_files:
        logger.warning(f"No .pages.json files found in {input_dir}")
        return []

    if source_filter is not None:
        original_count = len(pages_files)
        pages_files = [
            f
            for f in pages_files
            if f.relative_to(input_path).as_posix() in source_filter
        ]
        logger.info(
            f"Source filter applied: {len(pages_files)}/{original_count} files matched"
        )

    logger.info(f"Found {len(pages_files)} .pages.json files to process")

    all_results = []

    for pages_file in pages_files:
        try:
            with open(pages_file, encoding="utf-8") as f:
                page_chunks_data = json.load(f)

            relative_path = pages_file.relative_to(input_path)
            source_name = relative_path.with_suffix("").stem

            category = detect_document_category(str(pages_file))

            chunks = chunk_text_page_aware(
                page_chunks_data,
                source_name=source_name,
                chunk_size=chunk_size,
                overlap=overlap,
                encoding_name=encoding_name,
                model_name=model_name,
                cross_page_overlap=cross_page_overlap,
            )

            output_file = output_path / relative_path.with_suffix(".jsonl")

            output_file.parent.mkdir(parents=True, exist_ok=True)

            with open(output_file, "w", encoding="utf-8") as f:
                for chunk in chunks:
                    page_number = chunk["metadata"].get("page_number", 0)
                    chunk_index_str = chunk["metadata"].get("chunk_index", "000")
                    chunk_id = f"{source_name}_{chunk_index_str}"

                    chunk_data = {
                        "chunk_id": chunk_id,
                        "text": chunk["text"],
                        "metadata": {
                            "source": relative_path.as_posix(),
                            "page_number": page_number,
                            "category": category,
                            "strategy": "page_aware_fixed",
                            "chunk_index": chunk["metadata"]["chunk_index"],
                            "char_count": chunk["metadata"]["char_count"],
                            "token_count": chunk["metadata"]["token_count"],
                            "start_token": chunk["metadata"]["start_token"],
                            "end_token": chunk["metadata"]["end_token"],
                        },
                    }

                    if chunk["metadata"].get("cross_page"):
                        chunk_data["metadata"]["cross_page"] = True
                        chunk_data["metadata"]["overlap_from_page"] = chunk["metadata"][
                            "overlap_from_page"
                        ]

                    f.write(json.dumps(chunk_data, ensure_ascii=False) + "\n")

            all_results.append(
                {
                    "source": str(pages_file),
                    "output": str(output_file),
                    "category": category,
                    "chunk_count": len(chunks),
                    "status": "success",
                }
            )

            logger.debug(
                f"Processed {pages_file.name}: {len(chunks)} chunks -> {output_file.name}"
            )

        except Exception as e:
            logger.error(f"Failed to process {pages_file}: {str(e)}")
            all_results.append(
                {
                    "source": str(pages_file),
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
        f"Page-aware chunking completed: {success_count} succeeded, {failed_count} failed, {total_chunks} total chunks"
    )

    return all_results
