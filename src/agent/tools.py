from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from langchain_core.tools import tool
from loguru import logger


def _resolve_pdf_path(pdf_path: str) -> str:
    """Resolve a PDF path, trying the raw data directory if the file is not found.

    If the given path does not exist, attempts to prefix it with the raw
    data directory from config (e.g., ``data/raw/``). This handles cases
    where the LLM provides a relative path without the data prefix.

    Args:
        pdf_path: The PDF file path to resolve.

    Returns:
        The resolved path string that exists on disk, or the original path
        if no alternative is found (letting the downstream code handle the
        FileNotFoundError).
    """
    p = Path(pdf_path)
    if p.exists():
        return pdf_path

    try:
        from src.utils import load_config

        config = load_config()
        raw_dir = config.get("parser", {}).get("input_dir", "data/raw")
        candidate = Path(raw_dir) / pdf_path
        if candidate.exists():
            logger.info(f"Resolved PDF path: {pdf_path} -> {candidate}")
            return str(candidate)
    except Exception:
        pass

    return pdf_path


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
        from src.meal.manager import MealManager
        from src.utils import load_config

        config = load_config()
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
        from src.meal.manager import MealManager
        from src.utils import load_config

        config = load_config()
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
        from src.pipeline import RAGPipeline

        pipeline = RAGPipeline(meal_name=meal_name)
        result = pipeline.query(question)
        return json.dumps(result, ensure_ascii=False, indent=2, default=str)
    except Exception as e:
        logger.error(f"query_rag_tool failed: {e}")
        return f"Error querying RAG: {e}"


@tool
def parse_pdf_tool(
    pdf_path: str, parser_name: str | None = None, enhancer_name: str | None = None
) -> str:
    """Parse a PDF file and return the extracted text per page.

    Args:
        pdf_path: Path to the PDF file. If the file is not found, will try
            prefixing with the raw data directory from config (e.g., data/raw/).
        parser_name: Parser to use (default: from config or pymupdf4llm).
        enhancer_name: Optional table enhancer (e.g., pdfplumber).

    Returns:
        JSON string with page_number to text mapping and metadata.
    """
    try:
        if parser_name is None:
            from src.agent.config import get_agent_default

            parser_name = get_agent_default("parser_name", "pymupdf4llm")
        from src.core.ops.parse import parse_pdf

        resolved_path = _resolve_pdf_path(pdf_path)
        result = parse_pdf(
            resolved_path, parser_name=parser_name, enhancer_name=enhancer_name
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
    enhancer_name: str | None = None,
) -> str:
    """Enhance a single page's text with table extraction from pdfplumber.

    Args:
        pdf_path: Path to the PDF file.
        page_number: 1-indexed page number to enhance.
        existing_text: The current text of the page.
        enhancer_name: Enhancer to use (default: from config or pdfplumber).

    Returns:
        The enhanced text for the page.
    """
    try:
        if enhancer_name is None:
            from src.agent.config import get_agent_default

            enhancer_name = get_agent_default("enhancer_name", "pdfplumber")
        from src.core.ops.parse import enhance_page

        resolved_path = _resolve_pdf_path(pdf_path)
        result = enhance_page(
            resolved_path, page_number, existing_text, enhancer_name=enhancer_name
        )
        return result
    except Exception as e:
        logger.error(f"enhance_page_tool failed: {e}")
        return f"Error enhancing page: {e}"


@tool
def chunk_parsed_tool(
    pdf_path: str,
    strategy: str = "page_aware",
    chunk_size: int | None = None,
    overlap: int | None = None,
    parser_name: str | None = None,
    enhancer_name: str | None = None,
) -> str:
    """Parse a PDF and chunk it using the specified strategy.

    Args:
        pdf_path: Path to the PDF file.
        strategy: Chunking strategy (fixed, page_aware, semantic).
        chunk_size: Maximum chunk size in tokens (default: from config or 512).
        overlap: Overlap between chunks in tokens (default: from config or 0).
        parser_name: Parser to use (default: from config or pymupdf4llm).
        enhancer_name: Optional table enhancer.

    Returns:
        JSON string with chunk count and first few chunks preview.
    """
    try:
        if parser_name is None:
            from src.agent.config import get_agent_default

            parser_name = get_agent_default("parser_name", "pymupdf4llm")
        if chunk_size is None:
            from src.agent.config import get_agent_default

            chunk_size = get_agent_default("chunk_size", 512)
        if overlap is None:
            from src.agent.config import get_agent_default

            overlap = get_agent_default("chunk_overlap", 0)
        from src.core.ops.chunk import chunk_parsed
        from src.core.ops.parse import parse_pdf

        resolved_path = _resolve_pdf_path(pdf_path)
        parse_result = parse_pdf(
            resolved_path, parser_name=parser_name, enhancer_name=enhancer_name
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
        from src.indexer import VectorIndexer
        from src.utils import load_config

        config = load_config()
        collection_name = f"meal_{meal_name}"
        persist_dir = str(
            Path(config.get("vector_store", {}).get("persist_dir", "data/vector_store"))
        )
        indexer = VectorIndexer(
            persist_dir=persist_dir, collection_name=collection_name
        )
        try:
            info = indexer.get_collection_info()
        finally:
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
        from src.pipeline import RAGPipeline

        pipeline = RAGPipeline(meal_name=meal_name)

        chunks_dir = str(pipeline._chunks_dir) if pipeline._chunks_dir else None
        if not chunks_dir:
            return f"No chunks directory found for meal '{meal_name}'."
        chunks_path = Path(chunks_dir)
        if not chunks_path.exists():
            return f"No chunks directory found at {chunks_dir}."

        backup_path = _backup_to_trashbin(
            chunks_path, f"chunks_{pipeline.meal.data_id}"
        )
        backup_info = (
            {"backup_path": backup_path} if backup_path else {"backup_path": None}
        )

        pipeline.build_index(rebuild=rebuild)
        info = pipeline.indexer.get_collection_info()
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
        from src.pipeline import RAGPipeline

        pipeline = RAGPipeline(meal_name=meal_name)
        indexer = pipeline.indexer

        logger.info(f"Deleting source '{source}' from meal '{meal_name}'")

        backup_path = None
        try:
            points_metadata = indexer.scroll_by_source(source, with_vectors=False)
            if points_metadata:
                source_hash = hashlib.md5(source.encode()).hexdigest()[:8]
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                trashbin = Path(".trashbin")
                trashbin.mkdir(parents=True, exist_ok=True)
                backup_file = trashbin / f"source_backup_{source_hash}_{timestamp}.json"
                backup_file.write_text(
                    json.dumps(
                        points_metadata, ensure_ascii=False, indent=2, default=str
                    ),
                    encoding="utf-8",
                )
                backup_path = str(backup_file)
                logger.info(
                    f"Backed up {len(points_metadata)} points metadata to {backup_path}"
                )
        except Exception as e:
            logger.warning(f"Backup failed for source '{source}': {e}")

        deleted_count = indexer.delete_by_source(source)
        return json.dumps(
            {
                "status": "deleted",
                "meal_name": meal_name,
                "source": source,
                "deleted_points": deleted_count,
                "backup_path": backup_path,
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
        from src.meal.manager import MealManager
        from src.utils import load_config

        config = load_config()
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


@tool
def create_issue(
    title: str,
    issue_type: str = "bug",
    priority: str = "medium",
    labels: str | None = None,
) -> str:
    """Create a new issue in the issue tracking system.

    Args:
        title: Issue title.
        issue_type: Type of issue (bug/feat/rf/opt/inv/test). Defaults to 'bug'.
        priority: Priority level (high/medium/low). Defaults to 'medium'.
        labels: Comma-separated labels.

    Returns:
        JSON string with creation result.
    """
    try:
        cmd = [
            "pixi",
            "run",
            "issue",
            "create",
            "-t",
            issue_type,
            "-T",
            title,
            "-p",
            priority,
        ]
        if labels:
            cmd.extend(["-l", labels])
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            logger.warning(f"create_issue command failed: {result.stderr}")
            return json.dumps(
                {"status": "error", "stderr": result.stderr.strip()},
                ensure_ascii=False,
                indent=2,
            )
        return json.dumps(
            {"status": "created", "output": result.stdout.strip()},
            ensure_ascii=False,
            indent=2,
        )
    except subprocess.TimeoutExpired:
        logger.error("create_issue timed out")
        return "Error: create_issue timed out after 30 seconds"
    except Exception as e:
        logger.error(f"create_issue failed: {e}")
        return f"Error creating issue: {e}"


@tool
def list_issues(
    status: str | None = None,
    issue_type: str | None = None,
) -> str:
    """List issues from the issue tracking system.

    Args:
        status: Filter by status (todo/in_progress/review/done/deferred/cancelled).
        issue_type: Filter by type (bug/feat/rf/opt/inv/test).

    Returns:
        JSON string with issue list.
    """
    try:
        cmd = ["pixi", "run", "issue", "list", "--all"]
        if status:
            cmd.extend(["--status", status])
        if issue_type:
            cmd.extend(["--type", issue_type])
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            logger.warning(f"list_issues command failed: {result.stderr}")
            return json.dumps(
                {"status": "error", "stderr": result.stderr.strip()},
                ensure_ascii=False,
                indent=2,
            )
        return json.dumps(
            {"status": "ok", "output": result.stdout.strip()},
            ensure_ascii=False,
            indent=2,
        )
    except subprocess.TimeoutExpired:
        logger.error("list_issues timed out")
        return "Error: list_issues timed out after 30 seconds"
    except Exception as e:
        logger.error(f"list_issues failed: {e}")
        return f"Error listing issues: {e}"


@tool
def close_issue(issue_id: str) -> str:
    """Close an issue by marking it as done.

    Args:
        issue_id: The issue ID to close (e.g., BUG-20260504-001-wt1).

    Returns:
        JSON string with closure result.
    """
    try:
        cmd = ["pixi", "run", "issue", "done", issue_id]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            logger.warning(f"close_issue command failed: {result.stderr}")
            return json.dumps(
                {"status": "error", "stderr": result.stderr.strip()},
                ensure_ascii=False,
                indent=2,
            )
        return json.dumps(
            {"status": "closed", "issue_id": issue_id, "output": result.stdout.strip()},
            ensure_ascii=False,
            indent=2,
        )
    except subprocess.TimeoutExpired:
        logger.error("close_issue timed out")
        return "Error: close_issue timed out after 30 seconds"
    except Exception as e:
        logger.error(f"close_issue failed: {e}")
        return f"Error closing issue: {e}"


HIGH_RISK_TOOLS = {
    "rebuild_index",
    "delete_source",
    "update_meal",
    "delete_and_reindex_tool",
}

FORBIDDEN_OPERATIONS = {
    "delete_collection",
    "drop_collection",
    "delete_all",
    "drop_all",
    "delete_meal",
    "remove_meal",
}


@tool
def embed_chunks_tool(chunks: list[dict], collection_name: str | None = None) -> str:
    """Embed a list of text chunks using the configured embedder.

    Args:
        chunks: List of chunk dictionaries, each containing a 'text' key.
        collection_name: Target collection name. Defaults to config value.

    Returns:
        JSON string with embedding dimension and chunk count.
    """
    try:
        from src.agent.config import get_agent_default
        from src.core.ops.embed import embed_chunks
        from src.embedder import Embedder
        from src.utils import load_config

        if collection_name is None:
            collection_name = get_agent_default("collection_name", "financial_reports")

        config = load_config()
        embedder = Embedder(config)
        result = embed_chunks(chunks, embedder)
        return json.dumps(
            {
                "embedding_dim": len(result[0]) if result else 0,
                "chunk_count": len(result),
            },
            ensure_ascii=False,
            indent=2,
        )
    except Exception as e:
        logger.error(f"embed_chunks_tool failed: {e}")
        return f"Error embedding chunks: {e}"


@tool
def index_chunks_tool(chunks: list[dict], collection_name: str | None = None) -> str:
    """Index a list of chunks into the vector store.

    Args:
        chunks: List of chunk dictionaries to index.
        collection_name: Target collection name. Defaults to config value.

    Returns:
        JSON string with indexed count.
    """
    try:
        from src.agent.config import get_agent_default
        from src.core.ops.index import index_chunks
        from src.embedder import Embedder
        from src.utils import load_config

        if collection_name is None:
            collection_name = get_agent_default("collection_name", "financial_reports")

        config = load_config()
        embedder = Embedder(config)
        indexed = index_chunks(chunks, embedder, collection_name=collection_name)
        return json.dumps(
            {"indexed_count": indexed, "collection_name": collection_name},
            ensure_ascii=False,
            indent=2,
        )
    except Exception as e:
        logger.error(f"index_chunks_tool failed: {e}")
        return f"Error indexing chunks: {e}"


@tool
def delete_and_reindex_tool(
    source: str, new_chunks: list[dict], collection_name: str | None = None
) -> str:
    """Delete vectors for a source and re-index with new chunks.

    HIGH-RISK: This operation removes existing vectors and replaces them.
    Requires user approval before execution.

    Args:
        source: Source identifier to delete and re-index.
        new_chunks: New chunk dictionaries to index.
        collection_name: Target collection name. Defaults to config value.

    Returns:
        JSON string with re-indexed count.
    """
    try:
        from src.agent.config import get_agent_default
        from src.core.ops.index import delete_source_and_reindex
        from src.embedder import Embedder
        from src.utils import load_config

        if collection_name is None:
            collection_name = get_agent_default("collection_name", "financial_reports")

        config = load_config()
        embedder = Embedder(config)
        reindexed = delete_source_and_reindex(
            source, new_chunks, embedder, collection_name=collection_name
        )
        return json.dumps(
            {
                "reindexed_count": reindexed,
                "source": source,
                "collection_name": collection_name,
            },
            ensure_ascii=False,
            indent=2,
        )
    except Exception as e:
        logger.error(f"delete_and_reindex_tool failed: {e}")
        return f"Error deleting and reindexing: {e}"


@tool
def create_curated_meal(
    name: str | None = None,
    pdf_files: list[str] | None = None,
    source_dir: str | None = None,
    file_pattern: str | None = None,
    tags: list[str] | None = None,
    description: str | None = None,
) -> str:
    """Create a new meal by manually specifying PDF files.

    Args:
        name: Optional name for the meal.
        pdf_files: List of PDF file paths to include.
        source_dir: Directory to search for PDFs.
        file_pattern: Filename pattern for filtering (e.g., '*年报*').
        tags: Tags for the meal.
        description: Description for the meal.

    Returns:
        JSON string with created meal details.
    """
    try:
        from src.meal.manager import MealManager
        from src.utils import load_config

        config = load_config()
        mgr = MealManager(config)
        meal = mgr.create_meal_manual(
            name=name,
            pdf_files=pdf_files,
            source_dir=source_dir,
            file_pattern=file_pattern,
            tags=tags,
            description=description,
        )
        result = {
            "name": meal.name,
            "data_id": meal.data_id,
            "creation_mode": meal.creation_mode,
            "pdf_count": len(meal.pdf_files),
        }
        return json.dumps(result, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"create_curated_meal failed: {e}")
        return f"Error creating curated meal: {e}"


@tool
def list_pdfs(pattern: str = "*.pdf") -> str:
    """List available PDF files in the raw data directory.

    Args:
        pattern: Glob pattern for filtering files. Defaults to '*.pdf'.

    Returns:
        JSON string with list of PDF files.
    """
    try:
        from src.utils import load_config

        config = load_config()
        raw_dir = Path(config.get("parser", {}).get("input_dir", "data/raw"))
        if not raw_dir.exists():
            return f"Raw data directory not found: {raw_dir}"

        pdf_files = []
        for f in sorted(raw_dir.rglob(pattern)):
            stat = f.stat()
            pdf_files.append(
                {
                    "name": f.name,
                    "path": str(f),
                    "size_bytes": stat.st_size,
                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                }
            )
        return json.dumps(pdf_files, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"list_pdfs failed: {e}")
        return f"Error listing PDFs: {e}"


@tool
def generate_maintenance_report_tool(
    session_id: str = "default",
    current_source: str | None = None,
    current_meal: str | None = None,
    execution_log: list[str] | None = None,
    stage_history: list[str] | None = None,
    diagnosis: list[dict] | None = None,
    messages_summary: list[str] | None = None,
    config_recommendations: list[dict] | None = None,
    experiences: list[dict] | None = None,
) -> str:
    """Generate a maintenance session report summarizing all operations.

    Args:
        session_id: Session identifier for the report.
        current_source: Current PDF source path.
        current_meal: Current meal name.
        execution_log: List of execution log entries.
        stage_history: List of tool names executed in order.
        diagnosis: List of diagnostic findings.
        messages_summary: Key findings from AI messages.
        config_recommendations: List of recommended config items with item, value, reason.
        experiences: List of experience records with pdf_type, best_parser, etc.

    Returns:
        JSON string with report file path.
    """
    try:
        from src.agent.reporters.maintenance_report import MaintenanceReporter

        reporter = MaintenanceReporter()
        state = {
            "current_source": current_source,
            "current_meal": current_meal,
            "execution_log": execution_log or [],
            "stage_history": stage_history or [],
            "diagnosis": diagnosis or [],
            "messages": [],
            "config_recommendations": config_recommendations or [],
            "experiences": experiences or [],
        }
        report = reporter.generate(state, session_id)
        filepath = reporter.save(report, session_id)
        return json.dumps(
            {"status": "generated", "report_path": str(filepath)},
            ensure_ascii=False,
            indent=2,
        )
    except Exception as e:
        logger.error(f"generate_maintenance_report_tool failed: {e}")
        return f"Error generating maintenance report: {e}"


@tool
def generate_comparison_report_tool(
    results: list[dict],
    session_id: str = "default",
) -> str:
    """Generate a comparison report for multiple experiment results.

    Args:
        results: List of dicts, each with 'label' and 'metrics' keys.
            Example: [{"label": "方案A", "metrics": {"chunk_count": 100}},
                      {"label": "方案B", "metrics": {"chunk_count": 85}}]
        session_id: Session identifier for the report.

    Returns:
        JSON string with report file path.
    """
    try:
        from src.agent.reporters.comparison_report import ComparisonReporter

        reporter = ComparisonReporter()
        for r in results:
            reporter.add_result(r["label"], r["metrics"])
        report = reporter.generate()
        filepath = reporter.save(report, session_id)
        return json.dumps(
            {"status": "generated", "report_path": str(filepath)},
            ensure_ascii=False,
            indent=2,
        )
    except Exception as e:
        logger.error(f"generate_comparison_report_tool failed: {e}")
        return f"Error generating comparison report: {e}"
