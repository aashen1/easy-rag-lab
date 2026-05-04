from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

from langchain_core.tools import tool
from loguru import logger


def _backup_to_trashbin(source_path: Path, label: str) -> str | None:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    trashbin = Path(".trashbin")
    dest = trashbin / f"{label}_{timestamp}"
    try:
        trashbin.mkdir(parents=True, exist_ok=True)
        if source_path.is_dir():
            shutil.copytree(str(source_path), str(dest))
        elif source_path.is_file():
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(source_path), str(dest))
        else:
            return None
        logger.info(f"Backed up {source_path} to {dest}")
        return str(dest)
    except Exception as e:
        logger.warning(f"Backup failed for {source_path}: {e}")
        return None


@tool
def list_meals(meal_dir: str | None = None) -> str:
    """List all available meals in the system.

    Args:
        meal_dir: Optional directory path containing meal data. Defaults to config value.

    Returns:
        JSON string with list of meal names and their basic info.
    """
    try:
        from src.config import get_config
        from src.meal.manager import MealManager

        config = get_config()
        mgr = MealManager(config)
        meals = mgr.list_meals()
        result = []
        for m in meals:
            result.append(
                {
                    "name": m.name,
                    "data_id": m.data_id,
                    "pdf_count": len(m.pdf_files),
                    "creation_mode": m.creation_mode,
                }
            )
        return json.dumps(result, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"list_meals failed: {e}")
        return f"Error listing meals: {e}"


@tool
def get_meal_detail(meal_name: str) -> str:
    """Get detailed information about a specific meal, including its PDF files and config.

    Args:
        meal_name: Name of the meal to inspect.

    Returns:
        JSON string with meal details including pdf_files, config_snapshot, and stats.
    """
    try:
        from src.config import get_config
        from src.meal.manager import MealManager

        config = get_config()
        mgr = MealManager(config)
        meal = mgr.load_meal(meal_name)
        if meal is None:
            return f"Meal '{meal_name}' not found."
        result = {
            "name": meal.name,
            "data_id": meal.data_id,
            "creation_mode": meal.creation_mode,
            "pdf_files": [
                {"path": f.path, "sha256": f.sha256, "size_bytes": f.size_bytes}
                for f in meal.pdf_files
            ],
            "stats": meal.stats,
            "config_snapshot": meal.config_snapshot,
        }
        return json.dumps(result, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"get_meal_detail failed: {e}")
        return f"Error getting meal detail: {e}"


@tool
def query_rag_tool(question: str, meal_name: str) -> str:
    """Query the RAG pipeline with a question to test retrieval and generation quality.

    Args:
        question: The question to ask the RAG system.
        meal_name: Name of the meal whose pipeline to query.

    Returns:
        JSON string with answer, sources, and scores.
    """
    try:
        from src.config import get_config
        from src.core.ops.query import query_rag
        from src.meal.manager import MealManager

        config = get_config()
        mgr = MealManager(config)
        meal = mgr.load_meal(meal_name)
        if meal is None:
            return f"Meal '{meal_name}' not found."
        pipeline = mgr.get_pipeline(meal_name)
        if pipeline is None:
            return f"No pipeline found for meal '{meal_name}'."
        result = query_rag(question, pipeline)
        return json.dumps(result, ensure_ascii=False, indent=2, default=str)
    except Exception as e:
        logger.error(f"query_rag_tool failed: {e}")
        return f"Error querying RAG: {e}"


@tool
def parse_pdf_tool(
    pdf_path: str, parser_name: str = "pymupdf4llm", enhancer_name: str | None = None
) -> str:
    """Parse a PDF file and return the extracted text per page.

    Args:
        pdf_path: Path to the PDF file.
        parser_name: Parser to use (default: pymupdf4llm).
        enhancer_name: Optional table enhancer (e.g., pdfplumber).

    Returns:
        JSON string with page_number to text mapping and metadata.
    """
    try:
        from src.core.ops.parse import parse_pdf

        result = parse_pdf(
            pdf_path, parser_name=parser_name, enhancer_name=enhancer_name
        )
        pages = {
            p.page_number: p.text[:500] + ("..." if len(p.text) > 500 else "")
            for p in result.pages
        }
        output = {
            "metadata": result.metadata,
            "pages": pages,
            "total_pages": len(result.pages),
        }
        return json.dumps(output, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"parse_pdf_tool failed: {e}")
        return f"Error parsing PDF: {e}"


@tool
def enhance_page_tool(
    pdf_path: str,
    page_number: int,
    existing_text: str,
    enhancer_name: str = "pdfplumber",
) -> str:
    """Enhance a single page's text with table extraction from pdfplumber.

    Args:
        pdf_path: Path to the PDF file.
        page_number: 1-indexed page number to enhance.
        existing_text: The current text of the page.
        enhancer_name: Enhancer to use (default: pdfplumber).

    Returns:
        The enhanced text for the page.
    """
    try:
        from src.core.ops.parse import enhance_page

        result = enhance_page(
            pdf_path, page_number, existing_text, enhancer_name=enhancer_name
        )
        return result
    except Exception as e:
        logger.error(f"enhance_page_tool failed: {e}")
        return f"Error enhancing page: {e}"


@tool
def chunk_parsed_tool(
    pdf_path: str,
    strategy: str = "page_aware",
    chunk_size: int = 512,
    overlap: int = 0,
    parser_name: str = "pymupdf4llm",
    enhancer_name: str | None = None,
) -> str:
    """Parse a PDF and chunk it using the specified strategy.

    Args:
        pdf_path: Path to the PDF file.
        strategy: Chunking strategy (fixed, page_aware, semantic).
        chunk_size: Maximum chunk size in tokens.
        overlap: Overlap between chunks in tokens.
        parser_name: Parser to use.
        enhancer_name: Optional table enhancer.

    Returns:
        JSON string with chunk count and first few chunks preview.
    """
    try:
        from src.core.ops.chunk import chunk_parsed
        from src.core.ops.parse import parse_pdf

        parse_result = parse_pdf(
            pdf_path, parser_name=parser_name, enhancer_name=enhancer_name
        )
        chunks = chunk_parsed(
            parse_result, strategy=strategy, chunk_size=chunk_size, overlap=overlap
        )
        preview = [
            {"text": c["text"][:200] + "...", "metadata": c.get("metadata", {})}
            for c in chunks[:5]
        ]
        output = {"total_chunks": len(chunks), "preview": preview}
        return json.dumps(output, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"chunk_parsed_tool failed: {e}")
        return f"Error chunking: {e}"


@tool
def evaluate_answer_tool(
    question: str,
    answer: str,
    contexts: list[str],
    expected_answer: str | None = None,
) -> str:
    """Evaluate a RAG answer quality using available metrics.

    Args:
        question: The original question.
        answer: The generated answer.
        contexts: The retrieved context passages.
        expected_answer: Optional expected answer for comparison.

    Returns:
        JSON string with metric scores.
    """
    try:
        from src.core.ops.evaluate import evaluate_single

        result = evaluate_single(
            question=question,
            answer=answer,
            contexts=contexts,
            expected_answer=expected_answer,
        )
        return json.dumps(result, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"evaluate_answer_tool failed: {e}")
        return f"Error evaluating: {e}"


@tool
def get_index_info(meal_name: str) -> str:
    """Get information about the vector index for a meal's collection.

    Args:
        meal_name: Name of the meal.

    Returns:
        JSON string with index info (point count, vector size, etc).
    """
    try:
        from src.config import get_config
        from src.indexer import VectorIndexer

        config = get_config()
        collection_name = f"meal_{meal_name}"
        persist_dir = str(
            Path(config.get("index", {}).get("persist_dir", "data/index"))
        )
        indexer = VectorIndexer(
            persist_dir=persist_dir, collection_name=collection_name
        )
        info = indexer.get_collection_info()
        indexer.close()
        if info is None:
            return f"No index found for meal '{meal_name}'."
        return json.dumps(info, ensure_ascii=False, indent=2, default=str)
    except Exception as e:
        logger.error(f"get_index_info failed: {e}")
        return f"Error getting index info: {e}"


@tool
def rebuild_index(meal_name: str, rebuild: bool = True) -> str:
    """Rebuild the vector index for a meal from its chunk files.

    HIGH-RISK: This operation deletes the existing index and rebuilds from scratch.
    Requires user approval before execution.

    Args:
        meal_name: Name of the meal whose index to rebuild.
        rebuild: Whether to force rebuild (default: True).

    Returns:
        JSON string with rebuild result including point count.
    """
    try:
        from src.config import get_config
        from src.meal.manager import MealManager

        config = get_config()
        mgr = MealManager(config)
        meal = mgr.load_meal(meal_name)
        if meal is None:
            return f"Meal '{meal_name}' not found."

        pipeline = mgr.get_pipeline(meal_name)
        if pipeline is None:
            return f"No pipeline found for meal '{meal_name}'."

        indexer = pipeline.indexer
        embedder = pipeline.embedder

        chunks_dir = str(
            Path(config.get("paths", {}).get("chunks_dir", "data/chunks"))
            / meal.data_id
        )
        chunks_path = Path(chunks_dir)
        if not chunks_path.exists():
            return f"No chunks directory found at {chunks_dir}."

        backup_path = _backup_to_trashbin(chunks_path, f"chunks_{meal.data_id}")
        backup_info = (
            {"backup_path": backup_path} if backup_path else {"backup_path": None}
        )

        indexer.create_collection(
            vector_size=embedder.get_embedding_dimension(), recreate=rebuild
        )
        indexer.build_index(
            chunks_dir=chunks_dir,
            embedder=embedder,
            rebuild=rebuild,
        )
        info = indexer.get_collection_info()
        return json.dumps(
            {
                "status": "rebuilt",
                "meal_name": meal_name,
                "collection_info": info,
                **backup_info,
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    except Exception as e:
        logger.error(f"rebuild_index failed: {e}")
        return f"Error rebuilding index: {e}"


@tool
def delete_source(meal_name: str, source: str) -> str:
    """Delete a specific source file from the meal's vector index.

    HIGH-RISK: This operation permanently removes indexed data for a source.
    Requires user approval before execution.

    Args:
        meal_name: Name of the meal.
        source: Source file path to delete from the index.

    Returns:
        JSON string with deletion result.
    """
    try:
        from src.config import get_config
        from src.meal.manager import MealManager

        config = get_config()
        mgr = MealManager(config)
        meal = mgr.load_meal(meal_name)
        if meal is None:
            return f"Meal '{meal_name}' not found."

        pipeline = mgr.get_pipeline(meal_name)
        if pipeline is None:
            return f"No pipeline found for meal '{meal_name}'."

        indexer = pipeline.indexer

        persist_dir = (
            Path(indexer.persist_dir) if hasattr(indexer, "persist_dir") else None
        )
        backup_info = {}
        if persist_dir and persist_dir.exists():
            backup_path = _backup_to_trashbin(persist_dir, f"index_{meal_name}")
            backup_info = {"backup_path": backup_path}

        deleted_count = indexer.delete_by_source(source)
        return json.dumps(
            {
                "status": "deleted",
                "meal_name": meal_name,
                "source": source,
                "deleted_points": deleted_count,
                **backup_info,
            },
            ensure_ascii=False,
            indent=2,
        )
    except Exception as e:
        logger.error(f"delete_source failed: {e}")
        return f"Error deleting source: {e}"


@tool
def update_meal(meal_name: str, updates: dict) -> str:
    """Update a meal's configuration or metadata.

    HIGH-RISK: This operation modifies meal configuration.
    Requires user approval before execution.

    Args:
        meal_name: Name of the meal to update.
        updates: Dictionary of fields to update (e.g., {"description": "new desc", "tags": ["tag1"]}).

    Returns:
        JSON string with update result.
    """
    try:
        from src.config import get_config
        from src.meal.manager import MealManager

        config = get_config()
        mgr = MealManager(config)
        meal = mgr.load_meal(meal_name)
        if meal is None:
            return f"Meal '{meal_name}' not found."

        allowed_fields = {"description", "tags"}
        applied = {}
        for key, value in updates.items():
            if key in allowed_fields:
                applied[key] = value
            else:
                logger.warning(f"Skipping disallowed field: {key}")

        if not applied:
            return "No valid fields to update. Allowed fields: " + ", ".join(
                sorted(allowed_fields)
            )

        cache = mgr.cache

        manifest_path = cache.get_artifact_group_dir(meal.data_id) / "manifest.json"
        backup_info = {}
        if manifest_path.exists():
            backup_path = _backup_to_trashbin(manifest_path, f"manifest_{meal.data_id}")
            backup_info = {"backup_path": backup_path}

        for key, value in applied.items():
            success = cache.update_manifest_entry(meal.data_id, key, value)
            if not success:
                return f"Failed to update field '{key}'."

        return json.dumps(
            {
                "status": "updated",
                "meal_name": meal_name,
                "applied_updates": applied,
                **backup_info,
            },
            ensure_ascii=False,
            indent=2,
        )
    except Exception as e:
        logger.error(f"update_meal failed: {e}")
        return f"Error updating meal: {e}"


HIGH_RISK_TOOLS = {"rebuild_index", "delete_source", "update_meal"}
