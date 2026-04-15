import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import tiktoken
from loguru import logger

from src.utils import ensure_dir


def chunk_text(
    text: str,
    chunk_size: int = 512,
    overlap: int = 0,
    encoding_name: str = "cl100k_base",
) -> List[Dict[str, Any]]:
    if not text or not text.strip():
        logger.warning("Empty text provided for chunking")
        return []

    if overlap >= chunk_size:
        error_msg = f"Overlap ({overlap}) must be less than chunk_size ({chunk_size})"
        logger.error(error_msg)
        raise ValueError(error_msg)

    try:
        encoding = tiktoken.get_encoding(encoding_name)
    except Exception as e:
        error_msg = f"Failed to load tiktoken encoding {encoding_name}: {str(e)}"
        logger.error(error_msg)
        raise Exception(error_msg)

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
) -> List[Dict[str, Any]]:
    input_path = Path(input_dir)
    output_path = ensure_dir(output_dir)

    if not input_path.exists():
        error_msg = f"Input directory not found: {input_dir}"
        logger.error(error_msg)
        raise FileNotFoundError(error_msg)

    md_files = list(input_path.rglob("*.md"))

    if not md_files:
        logger.warning(f"No Markdown files found in {input_dir}")
        return []

    logger.info(f"Found {len(md_files)} Markdown files to process")

    all_results = []

    for md_file in md_files:
        try:
            with open(md_file, "r", encoding="utf-8") as f:
                text = f.read()

            chunks = chunk_text(text, chunk_size, overlap, encoding_name)

            relative_path = md_file.relative_to(input_path)
            source_name = relative_path.stem

            category = "unknown"
            if "annual_report" in str(md_file) or "年报" in str(md_file):
                category = "annual_report"
            elif "research_report" in str(md_file) or "研报" in str(md_file):
                category = "research_report"

            output_file = output_path / relative_path.with_suffix(".jsonl")

            output_file.parent.mkdir(parents=True, exist_ok=True)

            with open(output_file, "w", encoding="utf-8") as f:
                for chunk in chunks:
                    chunk_id = f"{source_name}_{chunk['metadata']['chunk_index']:03d}"

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


if __name__ == "__main__":
    from src.utils import load_config, setup_logger

    config = load_config()
    setup_logger(config)

    chunker_config = config["chunker"]
    results = process_parsed_files(
        input_dir=chunker_config["input_dir"],
        output_dir=chunker_config["output_dir"],
        chunk_size=chunker_config["chunk_size"],
        overlap=chunker_config["chunk_overlap"],
    )

    for result in results:
        logger.info(f"Result: {result}")
