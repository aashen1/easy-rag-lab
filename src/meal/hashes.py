from __future__ import annotations

import hashlib
import json
from pathlib import Path

from loguru import logger

from src.meal.models import MealFile


def compute_file_sha256(file_path: Path, chunk_size: int = 8192) -> str:
    """Compute SHA-256 hash of a file by reading it in chunks.

    Args:
        file_path: Path to the file to hash.
        chunk_size: Number of bytes to read per iteration.

    Returns:
        Hexadecimal SHA-256 digest string.
    """
    sha256 = hashlib.sha256()
    try:
        with open(file_path, "rb") as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                sha256.update(chunk)
        return sha256.hexdigest()
    except Exception as e:
        logger.error(f"Failed to compute SHA256 for {file_path}: {str(e)}")
        return ""


def compute_data_id(pdf_files: list[MealFile]) -> str:
    """Compute a deterministic data ID from a list of meal files.

    Args:
        pdf_files: List of MealFile objects whose SHA-256 hashes are combined.

    Returns:
        Hexadecimal SHA-256 digest string serving as the data ID.
    """
    sorted_hashes = sorted(f.sha256 for f in pdf_files)
    combined = "|".join(sorted_hashes)
    return hashlib.sha256(combined.encode()).hexdigest()


def _version_hint_for(name: str) -> str:
    try:
        if name == "pymupdf4llm":
            import pymupdf4llm

            return pymupdf4llm.__version__
        elif name == "pymupdf":
            import pymupdf

            return pymupdf.__version__
        elif name in ("fitz_pdfplumber", "pdfplumber"):
            import pdfplumber

            return pdfplumber.__version__
        elif name == "fitz":
            import pymupdf

            return pymupdf.__version__
    except (ImportError, AttributeError):
        pass
    return "unknown"


def compute_parser_config_hash(parser_config: dict) -> str:
    """Compute a short hash of the parser configuration.

    Args:
        parser_config: Parser configuration dictionary. Supports both the
            legacy format (``algorithm`` + ``options`` keys) and the new
            composite format (``primary`` + ``enhancer`` +
            ``primary_config`` + ``enhancer_config`` keys).

    Returns:
        First 8 characters of the SHA-256 hex digest.
    """
    if "primary" in parser_config:
        relevant = {
            "primary": parser_config.get("primary", "pymupdf4llm"),
            "enhancer": parser_config.get("enhancer"),
            "primary_config": parser_config.get("primary_config", {}),
            "enhancer_config": parser_config.get("enhancer_config", {}),
        }
        relevant["_primary_version"] = _version_hint_for(relevant["primary"])
        if relevant["enhancer"]:
            relevant["_enhancer_version"] = _version_hint_for(relevant["enhancer"])
    else:
        algorithm = parser_config.get("algorithm", "pymupdf4llm")
        options = parser_config.get("options", {})
        relevant = {"algorithm": algorithm, "options": options}
        relevant["_version_hint"] = _version_hint_for(algorithm)

    return hashlib.sha256(json.dumps(relevant, sort_keys=True).encode()).hexdigest()[:8]


def compute_chunker_config_hash(chunker_config: dict) -> str:
    """Compute a short hash of the chunker configuration.

    The hash includes all parameters that affect chunking results:
    - strategy: chunking strategy (fixed, semantic, etc.)
    - chunk_size: target chunk size
    - overlap: chunk overlap
    - encoding: tokenizer encoding
    - semantic config: similarity_threshold, breakpoint_percentile, min_chunk_size

    Args:
        chunker_config: Chunker configuration dictionary.

    Returns:
        First 8 characters of the SHA-256 hex digest.
    """
    overlap = chunker_config.get("chunk_overlap", chunker_config.get("overlap", 0))
    relevant = {
        "strategy": chunker_config.get("strategy", "fixed"),
        "chunk_size": chunker_config["chunk_size"],
        "overlap": overlap,
        "encoding": chunker_config.get("encoding", "cl100k_base"),
        "cross_page_overlap": chunker_config.get("cross_page_overlap", 0),
    }

    if chunker_config.get("strategy") == "semantic":
        semantic_config = chunker_config.get("semantic", {})
        relevant["semantic"] = {
            "similarity_threshold": semantic_config.get("similarity_threshold", 0.5),
            "breakpoint_percentile": semantic_config.get("breakpoint_percentile"),
            "min_chunk_size": semantic_config.get("min_chunk_size", 100),
        }

    return hashlib.sha256(json.dumps(relevant, sort_keys=True).encode()).hexdigest()[:8]


def compute_embedding_config_hash(embedding_config: dict) -> str:
    """Compute a short hash of the embedding configuration.

    Args:
        embedding_config: Embedding configuration dictionary containing model_name.

    Returns:
        First 8 characters of the SHA-256 hex digest.
    """
    relevant = {"model_name": embedding_config["model_name"]}
    if "dimension" in embedding_config:
        relevant["dimension"] = embedding_config["dimension"]
    return hashlib.sha256(json.dumps(relevant, sort_keys=True).encode()).hexdigest()[:8]


def compute_index_key(data_id: str, config_hashes: dict[str, str]) -> str:
    parts = [
        ("d", data_id),
        ("p", config_hashes.get("parser", "")),
        ("c", config_hashes.get("chunker", "")),
        ("e", config_hashes.get("embedding", "")),
    ]
    combined = "|".join(f"{k}:{v}" for k, v in parts)
    return hashlib.sha256(combined.encode()).hexdigest()


def compute_variant_config_hash(
    variant: dict,
    merged_config: dict,
    exp_data: dict | None = None,
    exp_test_sets: list | None = None,
    exp_evaluation: dict | None = None,
) -> str:
    """Compute a deterministic hash of all config that affects a variant's results.

    This hash captures everything that determines variant behavior: the variant's
    config_overrides, the merged pipeline config, and the experiment-level data/
    test_sets/evaluation settings.  If any of these change, the variant must be
    re-run.

    Args:
        variant: Variant dict (must contain ``name``; may contain
            ``config_overrides`` and ``description``).
        merged_config: The fully-merged pipeline config (system + experiment +
            variant overrides), after sanitization.
        exp_data: Experiment-level ``data`` block (meal name, sample ratio, etc.).
        exp_test_sets: Experiment-level ``test_sets`` list.
        exp_evaluation: Experiment-level ``evaluation`` block.

    Returns:
        First 12 characters of the SHA-256 hex digest.
    """
    payload = {
        "variant_overrides": variant.get("config_overrides", {}),
        "merged": merged_config,
    }
    if exp_data is not None:
        payload["data"] = exp_data
    if exp_test_sets is not None:
        payload["test_sets"] = exp_test_sets
    if exp_evaluation is not None:
        payload["evaluation"] = exp_evaluation
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:12]


def generate_collection_name(index_key: str, prefix: str = "m_") -> str:
    """Generate a Qdrant collection name from an index key.

    Args:
        index_key: Full index key string.
        prefix: Prefix to prepend to the truncated index key.

    Returns:
        Collection name string in the format '{prefix}{first_12_chars_of_index_key}'.
    """
    return f"{prefix}{index_key[:12]}"
