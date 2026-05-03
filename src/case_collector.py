from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from loguru import logger

from src.utils import deep_merge

CASE_TYPE_BAD = "bad"
CASE_TYPE_GOOD = "good"
CASE_DIR_PREFIX: dict[str, str] = {CASE_TYPE_BAD: "bc", CASE_TYPE_GOOD: "gc"}
VALID_CASE_TYPES = {CASE_TYPE_BAD, CASE_TYPE_GOOD}

CASES_DIR_NAME = "cases"
DATA_DIR_NAME = "data"


def get_cases_dir() -> Path:
    """Return the path to the cases storage directory.

    Returns:
        Path to data/cases/ directory. Created if it does not exist.
    """
    project_root = Path(__file__).resolve().parent.parent
    cases_dir = project_root / DATA_DIR_NAME / CASES_DIR_NAME
    cases_dir.mkdir(parents=True, exist_ok=True)
    return cases_dir


def _generate_case_id(case_type: str, question: str) -> str:
    """Generate a unique case ID from type, timestamp, and question hash.

    Args:
        case_type: Case type string (``CASE_TYPE_BAD`` or ``CASE_TYPE_GOOD``).
        question: The user question text.

    Returns:
        Case ID string like ``bc_20260502_143000_a1b2c3``.
    """
    prefix = CASE_DIR_PREFIX.get(case_type, "uk")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    question_hash = hashlib.sha256(question.encode("utf-8")).hexdigest()[:6]
    return f"{prefix}_{timestamp}_{question_hash}"


def _build_meal_snapshot(
    meal_config: Any | None, meal_name: str | None
) -> dict[str, Any]:
    """Build a meal snapshot dictionary for reproducibility.

    Args:
        meal_config: MealConfig instance, or None.
        meal_name: Name of the meal, or None.

    Returns:
        Dictionary with meal metadata and PDF file hashes.
    """
    if meal_config is None:
        return {"meal_name": meal_name, "pdf_files": []}

    snapshot = {
        "meal_name": meal_name or meal_config.name,
        "data_id": meal_config.data_id,
        "collection_name": meal_config.collection_name,
        "created_at": meal_config.created_at,
        "pdf_files": [],
    }

    for pdf_file in meal_config.pdf_files:
        snapshot["pdf_files"].append(
            {
                "path": pdf_file.path,
                "sha256": pdf_file.sha256,
                "size_bytes": pdf_file.size_bytes,
            }
        )

    return snapshot


def _sanitize_config(config: dict[str, Any]) -> dict[str, Any]:
    """Create a sanitized copy of configuration with API keys masked.

    Args:
        config: Configuration dictionary to sanitize.

    Returns:
        Deep-copied configuration with api_key values replaced by '***'.
    """
    import copy

    result = copy.deepcopy(config)
    llm_presets = result.get("llm_presets", {})
    for _preset_name, preset_config in llm_presets.items():
        if isinstance(preset_config, dict) and "api_key" in preset_config:
            preset_config["api_key"] = "***"
    return result


def _collect_environment_info() -> dict[str, Any]:
    """Collect environment version information for reproducibility.

    Returns:
        Dictionary containing timestamp, OS, Python version, and key package versions.
    """
    env_info: dict[str, Any] = {
        "timestamp": datetime.now().isoformat(),
    }

    try:
        import platform

        env_info["os"] = platform.platform()
        env_info["python_version"] = platform.python_version()
    except Exception:
        pass

    try:
        import pkg_resources

        key_packages = [
            "torch",
            "transformers",
            "qdrant-client",
            "langchain",
            "langchain-community",
            "pymupdf",
            "sentence-transformers",
            "rank-bm25",
            "loguru",
        ]
        installed: dict[str, str] = {}
        for pkg in pkg_resources.working_set:
            if pkg.key.lower() in key_packages:
                installed[pkg.key] = pkg.version
        if installed:
            env_info["key_packages"] = installed
    except Exception:
        pass

    return env_info


def save_case(
    case_type: str,
    question: str,
    result: dict[str, Any],
    config_overrides: dict[str, Any],
    base_config: dict[str, Any],
    meal_config: Any | None = None,
    meal_name: str | None = None,
) -> Path:
    """Save a case (bad or good) with full reproducibility context.

    Persists five files into a timestamped directory under ``data/cases/``:
    ``manifest.json``, ``config_snapshot.yaml``, ``meal_snapshot.json``,
    ``query_result.json``, and ``environment.json``.

    Args:
        case_type: ``CASE_TYPE_BAD`` or ``CASE_TYPE_GOOD``.
        question: The original user question.
        result: The full query result dictionary from ``pipeline.query()``.
        config_overrides: The config overrides used for this query.
        base_config: The base configuration (from config.yaml).
        meal_config: MealConfig instance for the active meal, or None.
        meal_name: Name of the active meal, or None.

    Returns:
        Path to the created case directory.

    Raises:
        ValueError: If ``case_type`` is not a valid type.
    """
    if case_type not in VALID_CASE_TYPES:
        raise ValueError(
            f"Invalid case_type '{case_type}'. Must be one of {VALID_CASE_TYPES}"
        )

    case_id = _generate_case_id(case_type, question)
    case_dir = get_cases_dir() / case_id
    case_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "case_id": case_id,
        "case_type": case_type,
        "status": "open",
        "created_at": datetime.now().isoformat(),
        "question_preview": question[:50],
        "meal_name": meal_name,
    }
    (case_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    effective_config = (
        deep_merge(base_config, config_overrides) if config_overrides else base_config
    )
    sanitized_config = _sanitize_config(effective_config)
    (case_dir / "config_snapshot.yaml").write_text(
        yaml.dump(sanitized_config, allow_unicode=True, default_flow_style=False),
        encoding="utf-8",
    )

    meal_snapshot = _build_meal_snapshot(meal_config, meal_name)
    (case_dir / "meal_snapshot.json").write_text(
        json.dumps(meal_snapshot, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    (case_dir / "query_result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    env_info = _collect_environment_info()
    (case_dir / "environment.json").write_text(
        json.dumps(env_info, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    logger.info(f"Case saved: {case_id} (type={case_type})")
    return case_dir


def list_cases(case_type: str | None = None) -> list[dict[str, Any]]:
    """List all saved cases, optionally filtered by type.

    Args:
        case_type: If provided, only return cases of this type
            (``CASE_TYPE_BAD`` or ``CASE_TYPE_GOOD``).

    Returns:
        List of manifest dictionaries, sorted by creation time (newest first).
    """
    cases_dir = get_cases_dir()
    cases: list[dict[str, Any]] = []

    for child in sorted(cases_dir.iterdir(), reverse=True):
        if not child.is_dir():
            continue
        manifest_path = child / "manifest.json"
        if not manifest_path.exists():
            continue
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if case_type is not None and manifest.get("case_type") != case_type:
                continue
            cases.append(manifest)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to read manifest in {child}: {e}")

    return cases


def load_case(case_id: str) -> dict[str, Any]:
    """Load all files for a given case.

    Args:
        case_id: The case directory name (e.g. ``bc_20260502_143000_a1b2c3``).

    Returns:
        Dictionary with keys ``manifest``, ``config_snapshot``,
        ``meal_snapshot``, ``query_result``, and ``environment``.

    Raises:
        FileNotFoundError: If the case directory does not exist.
    """
    case_dir = get_cases_dir() / case_id
    if not case_dir.exists():
        raise FileNotFoundError(f"Case not found: {case_id}")

    data: dict[str, Any] = {}

    manifest_path = case_dir / "manifest.json"
    if manifest_path.exists():
        data["manifest"] = json.loads(manifest_path.read_text(encoding="utf-8"))

    config_path = case_dir / "config_snapshot.yaml"
    if config_path.exists():
        data["config_snapshot"] = yaml.safe_load(
            config_path.read_text(encoding="utf-8")
        )

    meal_path = case_dir / "meal_snapshot.json"
    if meal_path.exists():
        data["meal_snapshot"] = json.loads(meal_path.read_text(encoding="utf-8"))

    result_path = case_dir / "query_result.json"
    if result_path.exists():
        data["query_result"] = json.loads(result_path.read_text(encoding="utf-8"))

    env_path = case_dir / "environment.json"
    if env_path.exists():
        data["environment"] = json.loads(env_path.read_text(encoding="utf-8"))

    return data


def delete_case(case_id: str) -> None:
    """Delete a case by moving its directory to .trashbin/.

    Args:
        case_id: The case directory name (e.g. ``bc_20260502_143000_a1b2c3``).

    Raises:
        FileNotFoundError: If the case directory does not exist.
    """
    cases_dir = get_cases_dir()
    case_dir = cases_dir / case_id
    if not case_dir.exists():
        raise FileNotFoundError(f"Case not found: {case_id}")

    trashbin = cases_dir.parent.parent / ".trashbin"
    trashbin.mkdir(parents=True, exist_ok=True)
    dest = trashbin / f"{case_id}_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
    try:
        case_dir.rename(dest)
        logger.info(f"Case moved to trashbin: {case_id} → {dest}")
    except OSError as e:
        logger.error(f"Failed to move case {case_id} to trashbin: {e}")
        raise


def convert_case(source_case_id: str, target_type: str) -> Path:
    """Convert a case from one type to another (e.g. bad→good).

    Loads the source case data, creates a new case of the target type,
    then deletes the original case directory.

    Args:
        source_case_id: The source case directory name.
        target_type: ``CASE_TYPE_BAD`` or ``CASE_TYPE_GOOD``.

    Returns:
        Path to the newly created case directory.

    Raises:
        FileNotFoundError: If the source case does not exist.
        ValueError: If ``target_type`` is not valid.
    """
    if target_type not in VALID_CASE_TYPES:
        raise ValueError(
            f"Invalid target_type '{target_type}'. Must be one of {VALID_CASE_TYPES}"
        )

    data = load_case(source_case_id)

    query_result = data.get("query_result", {})
    question = query_result.get("question", "")
    config_snapshot = data.get("config_snapshot", {})
    meal_snapshot = data.get("meal_snapshot", {})
    meal_name = meal_snapshot.get("meal_name")

    config_overrides: dict[str, Any] = {}
    base_config = config_snapshot

    new_case_dir = save_case(
        case_type=target_type,
        question=question,
        result=query_result,
        config_overrides=config_overrides,
        base_config=base_config,
        meal_config=None,
        meal_name=meal_name,
    )

    delete_case(source_case_id)

    logger.info(
        f"Case converted: {source_case_id} → {new_case_dir.name} (type={target_type})"
    )
    return new_case_dir


def find_case_by_question(
    question: str, case_type: str | None = None
) -> dict[str, Any] | None:
    """Find an existing case by question text.

    Searches through all saved cases and returns the first manifest
    whose ``question_preview`` matches the beginning of the given
    question text.

    Args:
        question: The question text to search for.
        case_type: If provided, only search cases of this type.

    Returns:
        The matching manifest dictionary, or None if no match found.
    """
    cases = list_cases(case_type=case_type)
    for manifest in cases:
        preview = manifest.get("question_preview", "")
        if preview and question.startswith(preview):
            return manifest
    return None
