import json
from pathlib import Path
from typing import Any

import tiktoken
from loguru import logger

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
            error_msg = (
                f"Failed to load BGE tokenizer for {self._model_name}: {str(e)}"
            )
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
    for line in text.split('\n'):
        stripped = line.strip()
        if stripped.startswith('#'):
            headings.append(stripped)
    return headings


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
        List of dictionaries, each with a "text" key containing the decoded
        chunk and a "metadata" key with chunk_index, char_count, token_count,
        start_token, and end_token.

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
        raise ValueError(error_msg)

    encoding = _get_encoding(encoding_name, model_name)

    tokens = encoding.encode(text)
    total_tokens = len(tokens)

    if total_tokens == 0:
        logger.warning("Text encoded to zero tokens")
        return []

    logger.debug(f"Text has {total_tokens} tokens")

    chunks = []
    chunk_index = 0
    start = 0

    while start < total_tokens:
        end = min(start + chunk_size, total_tokens)
        chunk_tokens = tokens[start:end]
        chunk_text_decoded = encoding.decode(chunk_tokens)

        char_count = len(chunk_text_decoded)
        token_count = len(chunk_tokens)

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

    logger.info(f"Created {len(chunks)} chunks from text with {total_tokens} tokens")
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
        raise FileNotFoundError(error_msg)

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
                    chunk_id = f"{source_name}::chunk::{chunk['metadata']['chunk_index']:03d}"

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

            logger.success(
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
) -> list[dict[str, Any]]:
    """Split page-level parsed results into chunks with page metadata.

    Each page is chunked independently (no cross-page chunks). Every chunk
    carries a page_number in its metadata.

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

    Returns:
        List of dictionaries, each with "text" and "metadata" keys. Metadata
        includes "page_number", "chunk_index", "char_count", "token_count",
        "start_token", and "end_token".

    Raises:
        ValueError: If overlap is greater than or equal to chunk_size.
    """
    if overlap >= chunk_size:
        error_msg = f"Overlap ({overlap}) must be less than chunk_size ({chunk_size})"
        logger.error(error_msg)
        raise ValueError(error_msg)

    all_chunks = []

    for page in page_chunks:
        text = page.get("text", "")
        page_number = page.get("metadata", {}).get("page_number", 0)

        if not text or not text.strip():
            logger.debug(f"Skipping empty page {page_number}")
            continue

        page_chunks_result = chunk_text(text, chunk_size, overlap, encoding_name, model_name)

        for chunk in page_chunks_result:
            chunk["metadata"]["page_number"] = page_number
            chunk_index = chunk["metadata"]["chunk_index"]
            chunk["metadata"]["chunk_index"] = f"p{page_number}_{chunk_index:03d}"
            all_chunks.append(chunk)

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
        raise FileNotFoundError(error_msg)

    output_path = ensure_dir(output_dir)

    pages_files = list(input_path.rglob("*.pages.json"))

    if not pages_files:
        logger.warning(f"No .pages.json files found in {input_dir}")
        return []

    if source_filter is not None:
        original_count = len(pages_files)
        pages_files = [
            f for f in pages_files if f.relative_to(input_path).as_posix() in source_filter
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
                            "source": relative_path.with_suffix(".pages.json").as_posix(),
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

            logger.success(
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


if __name__ == "__main__":
    from src.utils import load_config, setup_logger

    config = load_config()
    setup_logger(config)

    chunker_config = config["chunker"]
    embedding_config = config.get("embedding", {})
    results = process_parsed_files(
        input_dir=chunker_config["input_dir"],
        output_dir=chunker_config["output_dir"],
        chunk_size=chunker_config["chunk_size"],
        overlap=chunker_config["chunk_overlap"],
        encoding_name=chunker_config.get("encoding", "cl100k_base"),
        model_name=embedding_config.get("model_name"),
    )

    for result in results:
        logger.info(f"Result: {result}")
