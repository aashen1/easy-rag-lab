import json
from pathlib import Path
from typing import Any

from loguru import logger

from src.document_loader import LazyDocumentLoader
from src.meal import ArtifactCache, MealConfig


def resolve_parsed_dir(config: dict, meal_config: MealConfig) -> Path | None:
    """Resolve the parsed artifacts directory for a meal.

    Args:
        config: Application configuration dictionary.
        meal_config: MealConfig object with data_id and config_hashes.

    Returns:
        Path to the parsed directory, or None if not found.
    """
    if meal_config.data_id and meal_config.config_hashes:
        parser_hash = meal_config.config_hashes.get("parser", "")
        if parser_hash:
            artifacts_config = config.get("artifacts", {})
            artifacts_dir = Path(artifacts_config.get("dir", "data/artifacts"))
            raw_dir = Path(config.get("parser", {}).get("input_dir", "data/raw"))
            cache = ArtifactCache(artifacts_dir, raw_dir)
            parsed_dir = cache.get_parsed_dir(meal_config.data_id, parser_hash)
            if parsed_dir.exists():
                logger.debug(f"Resolved parsed dir via ArtifactCache: {parsed_dir}")
                return parsed_dir

    logger.warning(
        f"Could not resolve parsed dir via ArtifactCache for "
        f"meal_config data_id={meal_config.data_id}"
    )
    return None


def resolve_chunks_dir(config: dict, meal_config: MealConfig) -> Path | None:
    """Resolve the chunks artifacts directory for a meal.

    Args:
        config: Application configuration dictionary.
        meal_config: MealConfig object with data_id and config_hashes.

    Returns:
        Path to the chunks directory, or None if not found.
    """
    if meal_config.data_id and meal_config.config_hashes:
        chunker_hash = meal_config.config_hashes.get("chunker", "")
        if chunker_hash:
            artifacts_config = config.get("artifacts", {})
            artifacts_dir = Path(artifacts_config.get("dir", "data/artifacts"))
            raw_dir = Path(config.get("parser", {}).get("input_dir", "data/raw"))
            cache = ArtifactCache(artifacts_dir, raw_dir)
            chunks_dir = cache.get_chunks_dir(meal_config.data_id, chunker_hash)
            if chunks_dir.exists():
                logger.debug(f"Resolved chunks dir via ArtifactCache: {chunks_dir}")
                return chunks_dir
            logger.warning(
                f"Could not resolve chunks dir via ArtifactCache for "
                f"meal_config data_id={meal_config.data_id}: "
                f"computed path does not exist (chunks_dir={chunks_dir})"
            )
            return None

    reason = "unknown"
    if not meal_config.data_id:
        reason = "data_id is empty"
    elif not meal_config.config_hashes:
        reason = "config_hashes is empty"
    elif not meal_config.config_hashes.get("chunker"):
        reason = "config_hashes missing 'chunker' key"
    logger.warning(
        f"Could not resolve chunks dir via ArtifactCache for "
        f"meal_config data_id={meal_config.data_id}: {reason}"
    )
    return None


def load_meal_chunks(config: dict, meal_config: MealConfig) -> list[dict[str, Any]]:
    """Load chunk data from JSONL files associated with a meal's PDF files.

    Args:
        config: Application configuration dictionary.
        meal_config: MealConfig object.

    Returns:
        List of chunk dictionaries loaded from matching JSONL files.
    """
    chunks_dir = resolve_chunks_dir(config, meal_config)
    if not chunks_dir or not chunks_dir.exists():
        return []

    source_filter = set()
    for mf in meal_config.pdf_files:
        md_path = Path(mf.path).with_suffix(".md")
        source_filter.add(md_path.as_posix())

    all_chunks = []
    jsonl_files = list(chunks_dir.rglob("*.jsonl"))

    for jsonl_file in jsonl_files:
        try:
            rel_path = jsonl_file.relative_to(chunks_dir).as_posix()
            jsonl_md_path = rel_path.rsplit(".", 1)[0] + ".md"

            if source_filter and jsonl_md_path not in source_filter:
                continue

            with open(jsonl_file, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        chunk = json.loads(line)
                        all_chunks.append(chunk)
        except Exception as e:
            logger.warning(f"Failed to load {jsonl_file}: {str(e)}")
            continue

    return all_chunks


def load_document_chunks(
    config: dict,
    meal_config: MealConfig,
    document_contents: dict[str, dict[str, str]],
    chunks_dir: Path | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Load chunks for each document in document_contents.

    Args:
        config: Application configuration dictionary.
        meal_config: MealConfig object for resolving chunks directory.
        document_contents: Dictionary mapping document names to content dicts.
        chunks_dir: Optional path to chunks directory.

    Returns:
        Dictionary mapping document names to lists of chunk dictionaries.
    """
    if chunks_dir is not None:
        chunks_path = chunks_dir
    else:
        chunks_path = resolve_chunks_dir(config, meal_config)

    if not chunks_path:
        logger.warning(
            f"Chunks directory could not be resolved for "
            f"meal_config data_id={meal_config.data_id}"
        )
        return {doc_name: [] for doc_name in document_contents}
    if not chunks_path.exists():
        logger.warning(f"Chunks directory does not exist: {chunks_path}")
        return {doc_name: [] for doc_name in document_contents}

    source_to_doc_name: dict[str, str] = {}
    for doc_name, doc_data in document_contents.items():
        source_path = doc_data.get("source_path", "")
        source_to_doc_name[source_path] = doc_name

    doc_chunks_map: dict[str, list[dict[str, Any]]] = {
        doc_name: [] for doc_name in document_contents
    }

    jsonl_files = list(chunks_path.rglob("*.jsonl"))

    for jsonl_file in jsonl_files:
        try:
            with open(jsonl_file, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    chunk = json.loads(line)
                    chunk_source = (
                        chunk.get("metadata", {}).get("source", "").replace("\\", "/")
                    )

                    doc_name = source_to_doc_name.get(chunk_source)
                    if doc_name:
                        doc_chunks_map[doc_name].append(chunk)
        except Exception as e:
            logger.warning(f"Failed to load {jsonl_file}: {str(e)}")
            continue

    for doc_name, chunks in doc_chunks_map.items():
        if chunks:
            chunks.sort(key=lambda c: c.get("metadata", {}).get("chunk_index", 0))
            logger.debug(f"Loaded {len(chunks)} chunks for document: {doc_name}")

    return doc_chunks_map


def load_document_pages(
    config: dict,
    meal_config: MealConfig,
) -> dict[str, list[dict[str, Any]]]:
    """Load per-page data from ``.pages.json`` files.

    Args:
        config: Application configuration dictionary.
        meal_config: MealConfig whose ``pdf_files`` determine which
            documents to load.

    Returns:
        Dictionary mapping document names to lists of page dicts.
    """
    parsed_dir = resolve_parsed_dir(config, meal_config)
    if not parsed_dir or not parsed_dir.exists():
        logger.warning(f"Parsed directory not found: {parsed_dir}")
        return {}

    source_filter: set[str] = set()
    for mf in meal_config.pdf_files:
        pages_rel = Path(mf.path).with_suffix(".pages.json").as_posix()
        source_filter.add(pages_rel)

    result: dict[str, list[dict[str, Any]]] = {}
    pages_files = list(parsed_dir.rglob("*.pages.json"))

    for pages_file in pages_files:
        try:
            rel_path = pages_file.relative_to(parsed_dir).as_posix()
            if source_filter and rel_path not in source_filter:
                continue

            with open(pages_file, encoding="utf-8") as f:
                pages_data = json.load(f)

            if not isinstance(pages_data, list):
                continue

            doc_name = pages_file.stem.replace(".pages", "")
            page_list: list[dict[str, Any]] = []
            for page in pages_data:
                if not isinstance(page, dict):
                    continue
                text = page.get("text", "")
                page_number = page.get("page_number", 0)
                if text and text.strip():
                    page_list.append({"page_number": page_number, "text": text})

            if page_list:
                result[doc_name] = page_list
                logger.debug(f"Loaded {len(page_list)} pages for document: {doc_name}")
        except Exception as e:
            logger.error(f"Failed to load {pages_file}: {str(e)}")
            continue

    return result


def load_full_documents(
    config: dict,
    meal_config: MealConfig,
) -> dict[str, dict[str, str]]:
    """Load full documents associated with a meal's PDF files.

    Args:
        config: Application configuration dictionary.
        meal_config: MealConfig object whose pdf_files determine the
            documents to load.

    Returns:
        Dictionary mapping document names to dicts with 'content' and
        'source_path' keys.
    """
    parsed_dir = resolve_parsed_dir(config, meal_config)
    if not parsed_dir or not parsed_dir.exists():
        logger.warning(f"Parsed directory not found: {parsed_dir}")
        return {}

    try:
        loader = LazyDocumentLoader(parsed_dir)
    except FileNotFoundError as e:
        logger.error(f"Failed to initialize LazyDocumentLoader: {str(e)}")
        return {}

    source_filter = set()
    for mf in meal_config.pdf_files:
        md_path = Path(mf.path).with_suffix(".md").as_posix()
        pages_path = Path(mf.path).with_suffix(".pages.json").as_posix()
        source_filter.add(md_path)
        source_filter.add(pages_path)

    documents: dict[str, dict[str, str]] = {}

    for doc_name in loader.document_names:
        try:
            doc = loader.get(doc_name)
            rel_path = Path(doc.source_path).relative_to(parsed_dir).as_posix()

            if source_filter and rel_path not in source_filter:
                continue

            documents[doc_name] = {
                "content": doc.content,
                "source_path": rel_path,
            }
            logger.debug(f"Loaded document: {doc_name} ({len(doc.content)} chars)")
        except Exception as e:
            logger.error(f"Failed to load document '{doc_name}': {str(e)}")
            continue

    return documents


def load_pages_json_documents(
    parsed_dir: Path, meal_config: MealConfig
) -> dict[str, dict[str, str]]:
    """Load documents from .pages.json format.

    Args:
        parsed_dir: Directory containing .pages.json files.
        meal_config: MealConfig object for source filtering.

    Returns:
        Dictionary mapping document names to content dicts.
    """
    source_filter = set()
    for mf in meal_config.pdf_files:
        pages_rel = Path(mf.path).with_suffix(".pages.json").as_posix()
        source_filter.add(pages_rel)

    documents = {}
    pages_files = list(parsed_dir.rglob("*.pages.json"))

    for pages_file in pages_files:
        try:
            rel_path = pages_file.relative_to(parsed_dir).as_posix()
            if source_filter and rel_path not in source_filter:
                continue

            with open(pages_file, encoding="utf-8") as f:
                pages_data = json.load(f)

            full_text = "\n\n".join(
                page.get("text", "")
                for page in sorted(pages_data, key=lambda p: p.get("page_number", 0))
            )

            doc_name = pages_file.stem.replace(".pages", "")
            documents[doc_name] = {
                "content": full_text,
                "source_path": rel_path,
            }
            logger.debug(f"Loaded document: {doc_name} ({len(full_text)} chars)")
        except Exception as e:
            logger.error(f"Failed to load {pages_file}: {str(e)}")

    return documents


def load_md_documents(
    parsed_dir: Path, meal_config: MealConfig
) -> dict[str, dict[str, str]]:
    """Load documents from .md format.

    Args:
        parsed_dir: Directory containing .md files.
        meal_config: MealConfig object for source filtering.

    Returns:
        Dictionary mapping document names to content dicts.
    """
    source_filter = set()
    for mf in meal_config.pdf_files:
        md_rel = Path(mf.path).with_suffix(".md").as_posix()
        source_filter.add(md_rel)

    documents = {}
    md_files = list(parsed_dir.rglob("*.md"))

    for md_file in md_files:
        try:
            rel_path = md_file.relative_to(parsed_dir).as_posix()
            if source_filter and rel_path not in source_filter:
                continue

            with open(md_file, encoding="utf-8") as f:
                content = f.read()

            doc_name = md_file.stem
            documents[doc_name] = {
                "content": content,
                "source_path": rel_path,
            }
            logger.debug(f"Loaded document: {doc_name} ({len(content)} chars)")
        except Exception as e:
            logger.error(f"Failed to load {md_file}: {str(e)}")

    return documents
