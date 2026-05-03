from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

HISTORY_FILENAME = "history.json"
ANSWER_PREVIEW_LEN = 80
QUESTION_PREVIEW_LEN = 50
DEFAULT_MAX_ENTRIES = 10
DEFAULT_DIR = "data/query_history"


def _get_project_root() -> Path:
    return Path(__file__).resolve().parent.parent


class QueryHistory:
    """Ring-buffer style query history manager for CLI single-query mode.

    Persists query results to disk so that recent Q&A sessions can be
    reviewed and later promoted to badcase/goodcase entries via the
    ``case_collector`` module.

    Args:
        max_entries: Maximum number of history records to retain.
            Oldest entries are evicted when the limit is exceeded.
        history_dir: Directory for persisting history data.
            Defaults to ``data/query_history`` under the project root.
    """

    def __init__(
        self,
        max_entries: int = DEFAULT_MAX_ENTRIES,
        history_dir: str | Path | None = None,
    ) -> None:
        self.max_entries = max(1, max_entries)
        if history_dir is None:
            self._dir = _get_project_root() / DEFAULT_DIR
        else:
            self._dir = Path(history_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._history_path = self._dir / HISTORY_FILENAME

    def _load_history(self) -> list[dict[str, Any]]:
        if not self._history_path.exists():
            return []
        try:
            data = json.loads(self._history_path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return data
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to load query history: {e}")
        return []

    def _save_history(self, records: list[dict[str, Any]]) -> None:
        try:
            self._history_path.write_text(
                json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OSError as e:
            logger.error(f"Failed to save query history: {e}")

    def _next_id(self, records: list[dict[str, Any]]) -> str:
        max_seq = 0
        for rec in records:
            rid = rec.get("id", "")
            if isinstance(rid, str) and rid.startswith("qh_"):
                try:
                    seq = int(rid[3:])
                    if seq > max_seq:
                        max_seq = seq
                except ValueError:
                    pass
        return f"qh_{max_seq + 1:04d}"

    def _result_path(self, record_id: str) -> Path:
        return self._dir / f"{record_id}_result.json"

    def _evict_oldest(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        while len(records) > self.max_entries:
            oldest = records.pop(0)
            result_file = self._result_path(oldest.get("id", ""))
            if result_file.exists():
                try:
                    trashbin = self._dir.parent / ".trashbin"
                    trashbin.mkdir(parents=True, exist_ok=True)
                    dest = (
                        trashbin
                        / f"{result_file.name}_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
                    )
                    result_file.rename(dest)
                except OSError as e:
                    logger.warning(f"Failed to trash result file {result_file}: {e}")
        return records

    def add(
        self,
        question: str,
        result: dict[str, Any],
        meal_name: str | None = None,
        llm_preset: str | None = None,
        config_overrides: dict[str, Any] | None = None,
    ) -> str:
        """Add a query result to the history ring buffer.

        Args:
            question: The user's original question.
            result: The full query result dictionary from ``pipeline.query()``.
            meal_name: Name of the active meal, or None.
            llm_preset: LLM preset name used for this query.
            config_overrides: Config overrides applied for this query.

        Returns:
            The record ID string (e.g. ``qh_0001``).
        """
        records = self._load_history()
        record_id = self._next_id(records)

        answer = result.get("answer", "")
        answer_preview = (
            answer[:ANSWER_PREVIEW_LEN] + "..."
            if len(answer) > ANSWER_PREVIEW_LEN
            else answer
        )

        result_path = self._result_path(record_id)
        try:
            result_path.write_text(
                json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OSError as e:
            logger.error(f"Failed to save query result for {record_id}: {e}")

        record: dict[str, Any] = {
            "id": record_id,
            "timestamp": datetime.now().isoformat(),
            "question": question,
            "answer_preview": answer_preview,
            "meal_name": meal_name,
            "llm_preset": llm_preset,
            "saved_case_type": None,
            "saved_case_id": None,
            "config_overrides": config_overrides or {},
        }

        records.append(record)
        records = self._evict_oldest(records)
        self._save_history(records)

        logger.info(f"Query history recorded: {record_id}")
        return record_id

    def list_recent(self, limit: int | None = None) -> list[dict[str, Any]]:
        """List recent history records (newest first).

        Args:
            limit: Maximum number of records to return. None means all.

        Returns:
            List of record summary dictionaries (no full query_result).
        """
        records = self._load_history()
        records.reverse()
        if limit is not None:
            records = records[:limit]
        return records

    def get(self, record_id: str) -> dict[str, Any] | None:
        """Get a full history record including the query result.

        Args:
            record_id: The record ID (e.g. ``qh_0001``).

        Returns:
            Dictionary with record metadata and ``query_result`` key,
            or None if the record is not found.
        """
        records = self._load_history()
        for rec in records:
            if rec.get("id") == record_id:
                result_path = self._result_path(record_id)
                query_result: dict[str, Any] | None = None
                if result_path.exists():
                    try:
                        query_result = json.loads(
                            result_path.read_text(encoding="utf-8")
                        )
                    except (json.JSONDecodeError, OSError) as e:
                        logger.warning(f"Failed to load result for {record_id}: {e}")
                full = dict(rec)
                full["query_result"] = query_result
                return full
        return None

    def mark_saved(self, record_id: str, case_type: str, case_id: str) -> None:
        """Mark a history record as saved to a particular case type.

        Args:
            record_id: The history record ID.
            case_type: ``"bad"`` or ``"good"``.
            case_id: The case directory name that was created.
        """
        records = self._load_history()
        for rec in records:
            if rec.get("id") == record_id:
                rec["saved_case_type"] = case_type
                rec["saved_case_id"] = case_id
                break
        self._save_history(records)

    def check_saved(self, record_id: str) -> tuple[str | None, str | None]:
        """Check if a history record has already been saved as a case.

        Args:
            record_id: The history record ID.

        Returns:
            Tuple of (saved_case_type, saved_case_id). Both are None
            if the record has not been saved.
        """
        records = self._load_history()
        for rec in records:
            if rec.get("id") == record_id:
                return rec.get("saved_case_type"), rec.get("saved_case_id")
        return None, None

    def clear_saved(self, record_id: str) -> None:
        """Clear the saved-case marker on a history record.

        Used after a case is deleted (e.g. during type conversion).

        Args:
            record_id: The history record ID.
        """
        records = self._load_history()
        for rec in records:
            if rec.get("id") == record_id:
                rec["saved_case_type"] = None
                rec["saved_case_id"] = None
                break
        self._save_history(records)
