"""Quantify token count difference between tiktoken cl100k_base and BGE WordPiece tokenizer.

Reads JSONL chunk files, computes token counts with both tokenizers,
and outputs a statistical report to help decide whether chunk_size needs
adjustment for the BGE embedding model.

Usage:
    pixi run python scripts/analyze_tokenizer_diff.py --input_dir data/artifacts/{data_id}/chunks_{hash}
"""

import argparse
import json
import statistics
from pathlib import Path

import tiktoken
from loguru import logger
from transformers import AutoTokenizer


def load_chunks(input_dir: str) -> list[str]:
    """Read all JSONL files from the given directory and extract text fields.

    Scans the directory recursively for .jsonl files, parses each line as
    JSON, and collects the value of the "text" field from every record.

    Args:
        input_dir: Path to the directory containing JSONL chunk files.

    Returns:
        A list of text strings extracted from the "text" field of each
        JSONL record. Returns an empty list if no JSONL files are found
        or if no valid records contain a "text" field.

    Raises:
        FileNotFoundError: If input_dir does not exist.
    """
    input_path = Path(input_dir)

    if not input_path.exists():
        error_msg = f"Input directory not found: {input_dir}"
        logger.error(error_msg)
        raise FileNotFoundError(error_msg)

    jsonl_files = list(input_path.rglob("*.jsonl"))

    if not jsonl_files:
        logger.warning(f"No JSONL files found in {input_dir}")
        return []

    logger.info(f"Found {len(jsonl_files)} JSONL file(s) in {input_dir}")

    texts: list[str] = []

    for jsonl_file in jsonl_files:
        try:
            with open(jsonl_file, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                        text = record.get("text", "")
                        if text:
                            texts.append(text)
                    except json.JSONDecodeError as e:
                        logger.warning(f"Skipping malformed line in {jsonl_file}: {e}")
        except Exception as e:
            logger.error(f"Failed to read {jsonl_file}: {e}")

    logger.info(f"Loaded {len(texts)} chunks from JSONL files")
    return texts


def count_tiktoken_tokens(
    texts: list[str], encoding_name: str = "cl100k_base"
) -> list[int]:
    """Compute tiktoken token counts for each text in the list.

    Args:
        texts: List of text strings to tokenize.
        encoding_name: Name of the tiktoken encoding to use. Defaults to
            "cl100k_base".

    Returns:
        A list of integers representing the token count for each text.

    Raises:
        Exception: If the tiktoken encoding cannot be loaded.
    """
    try:
        encoding = tiktoken.get_encoding(encoding_name)
    except Exception as e:
        error_msg = f"Failed to load tiktoken encoding {encoding_name}: {e}"
        logger.error(error_msg)
        raise Exception(error_msg) from None

    counts = [len(encoding.encode(text)) for text in texts]
    logger.info(
        f"Computed tiktoken ({encoding_name}) token counts for {len(texts)} chunks"
    )
    return counts


def count_bge_tokens(
    texts: list[str], model_name: str = "BAAI/bge-large-zh-v1.5"
) -> list[int]:
    """Compute BGE WordPiece tokenizer token counts for each text.

    Args:
        texts: List of text strings to tokenize.
        model_name: Hugging Face model identifier for the tokenizer.
            Defaults to "BAAI/bge-large-zh-v1.5".

    Returns:
        A list of integers representing the token count for each text.

    Raises:
        Exception: If the tokenizer cannot be loaded.
    """
    try:
        tokenizer = AutoTokenizer.from_pretrained(model_name)
    except Exception as e:
        error_msg = f"Failed to load BGE tokenizer {model_name}: {e}"
        logger.error(error_msg)
        raise Exception(error_msg) from None

    counts = [len(tokenizer.encode(text)) for text in texts]
    logger.info(f"Computed BGE ({model_name}) token counts for {len(texts)} chunks")
    return counts


def compute_stats(counts: list[int]) -> dict[str, float]:
    """Compute descriptive statistics for a list of token counts.

    Args:
        counts: List of integer token counts.

    Returns:
        A dictionary with keys "min", "max", "mean", and "median".
        Returns all zeros if the input list is empty.
    """
    if not counts:
        return {"min": 0, "max": 0, "mean": 0, "median": 0}

    return {
        "min": min(counts),
        "max": max(counts),
        "mean": statistics.mean(counts),
        "median": statistics.median(counts),
    }


def generate_report(
    tiktoken_counts: list[int],
    bge_counts: list[int],
) -> str:
    """Generate a statistical comparison report for the two tokenizers.

    The report includes total chunk count, per-tokenizer statistics (min,
    max, mean, median), the number and percentage of chunks exceeding 512
    BGE tokens, and a conclusion on whether chunk_size needs adjustment.

    Args:
        tiktoken_counts: Token counts from tiktoken cl100k_base.
        bge_counts: Token counts from BGE WordPiece tokenizer.

    Returns:
        A formatted string containing the full statistical report.
    """
    total = len(tiktoken_counts)
    tiktoken_stats = compute_stats(tiktoken_counts)
    bge_stats = compute_stats(bge_counts)

    bge_over_512 = sum(1 for c in bge_counts if c > 512)
    bge_over_512_pct = (bge_over_512 / total * 100) if total > 0 else 0.0

    if bge_over_512 == 0:
        conclusion = (
            "No chunks exceed 512 BGE tokens. "
            "Current chunk_size is well-aligned with the BGE model limit. "
            "No adjustment needed."
        )
    elif bge_over_512_pct < 5:
        conclusion = (
            f"Only {bge_over_512_pct:.1f}% of chunks exceed 512 BGE tokens. "
            "The current chunk_size is mostly compatible. "
            "Consider a slight reduction if truncation loss is unacceptable."
        )
    elif bge_over_512_pct < 20:
        conclusion = (
            f"{bge_over_512_pct:.1f}% of chunks exceed 512 BGE tokens. "
            "chunk_size should be reduced to avoid truncation during embedding. "
            "A chunk_size of ~400-450 tiktoken tokens may be more appropriate."
        )
    else:
        conclusion = (
            f"{bge_over_512_pct:.1f}% of chunks exceed 512 BGE tokens. "
            "chunk_size MUST be reduced. Significant information is being "
            "truncated during embedding. Recommend reducing chunk_size to "
            "~350-400 tiktoken tokens and re-chunking."
        )

    lines = [
        "=" * 60,
        "  Tokenizer Difference Analysis Report",
        "=" * 60,
        "",
        f"Total chunks analyzed: {total}",
        "",
        "--- tiktoken (cl100k_base) ---",
        f"  Min:    {tiktoken_stats['min']:.0f}",
        f"  Max:    {tiktoken_stats['max']:.0f}",
        f"  Mean:   {tiktoken_stats['mean']:.1f}",
        f"  Median: {tiktoken_stats['median']:.1f}",
        "",
        "--- BGE WordPiece (BAAI/bge-large-zh-v1.5) ---",
        f"  Min:    {bge_stats['min']:.0f}",
        f"  Max:    {bge_stats['max']:.0f}",
        f"  Mean:   {bge_stats['mean']:.1f}",
        f"  Median: {bge_stats['median']:.1f}",
        "",
        f"Chunks exceeding 512 BGE tokens: {bge_over_512} / {total} ({bge_over_512_pct:.1f}%)",
        "",
        "--- Conclusion ---",
        conclusion,
        "=" * 60,
    ]

    return "\n".join(lines)


def main() -> None:
    """CLI entry point for tokenizer difference analysis.

    Parses command-line arguments, loads chunk data, computes token counts
    with both tokenizers, and prints a statistical comparison report.
    Exits gracefully with a log message if no JSONL files are found.
    """
    parser = argparse.ArgumentParser(
        description="Analyze token count differences between tiktoken and BGE tokenizer on chunks."
    )
    parser.add_argument(
        "--input_dir",
        type=str,
        required=True,
        help="Directory containing JSONL chunk files (each line has a 'text' field).",
    )
    args = parser.parse_args()

    logger.info(f"Starting tokenizer diff analysis on: {args.input_dir}")

    texts = load_chunks(args.input_dir)

    if not texts:
        logger.info("No chunks found. Nothing to analyze. Exiting.")
        return

    tiktoken_counts = count_tiktoken_tokens(texts)
    bge_counts = count_bge_tokens(texts)

    report = generate_report(tiktoken_counts, bge_counts)
    logger.info(f"\n{report}")


if __name__ == "__main__":
    main()
