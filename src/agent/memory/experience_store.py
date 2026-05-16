from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger


class ExperienceStore:
    NAMESPACE_PREFIX: tuple[str, ...] = ("maintenance", "experience")

    def __init__(self, store: Any) -> None:
        self._store = store

    def save_experience(
        self,
        summary: str | None = None,
        category: str | None = None,
        details: str | None = None,
        session_id: str | None = None,
        pdf_type: str | None = None,
        source_path: str | None = None,
    ) -> str:
        key = f"exp_{uuid.uuid4().hex[:12]}"
        ns = self.NAMESPACE_PREFIX + ((pdf_type,) if pdf_type else ("generic",))
        value: dict[str, Any] = {
            "summary": summary or "",
            "category": category or "",
            "details": details or "",
            "session_id": session_id,
            "pdf_type": pdf_type,
            "source_path": source_path,
            "timestamp": datetime.now().isoformat(),
        }
        try:
            self._store.put(ns, key, value)
            logger.info(f"Saved experience to {ns}/{key}")
            return key
        except Exception as e:
            logger.error(f"Failed to save experience: {e}")
            raise

    def get_relevant_experiences(self, pdf_type: str | None = None) -> list[dict]:
        namespace_prefix = self.NAMESPACE_PREFIX + ((pdf_type,) if pdf_type else ())
        try:
            items = self._store.search(namespace_prefix, limit=20)
            return [item.value for item in items]
        except Exception as e:
            logger.error(f"Failed to get relevant experiences: {e}")
            return []

    def search_experiences(self, query: str, limit: int = 10) -> list[dict]:
        try:
            items = self._store.search(self.NAMESPACE_PREFIX, query=query, limit=limit)
            return [item.value for item in items]
        except Exception as e:
            logger.error(f"Failed to search experiences: {e}")
            return []

    def list_experiences(
        self,
        category: str | None = None,
        pdf_type: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        namespace_prefix = self.NAMESPACE_PREFIX + ((pdf_type,) if pdf_type else ())
        try:
            kwargs: dict[str, Any] = {"limit": limit}
            if category:
                kwargs["filter"] = {"category": category}
            items = self._store.search(namespace_prefix, **kwargs)
            return [
                {"namespace": item.namespace, "key": item.key, "value": item.value}
                for item in items
            ]
        except Exception as e:
            logger.error(f"Failed to list experiences: {e}")
            return []

    def delete_experience(self, namespace: tuple[str, ...], key: str) -> None:
        try:
            self._store.delete(namespace, key)
            logger.info(f"Deleted experience {namespace}/{key}")
        except Exception as e:
            logger.error(f"Failed to delete experience {namespace}/{key}: {e}")
            raise

    def get_all_experiences(self, namespace: tuple[str, ...]) -> list[dict[str, Any]]:
        try:
            items = self._store.search(namespace)
            return [item.value for item in items]
        except Exception as e:
            logger.error(f"Failed to get all experiences: {e}")
            return []

    @classmethod
    def _migrate_from_json(cls, store: Any, json_path: str | Path) -> None:
        json_path = Path(json_path)
        if not json_path.exists():
            logger.debug(f"No JSON file at {json_path}, skipping migration")
            return
        try:
            with open(json_path, encoding="utf-8") as f:
                data = json.load(f)
            namespaces = data.get("namespaces", {})
            migrated_count = 0
            for ns_key, experiences in namespaces.items():
                ns = tuple(ns_key.split("/"))
                for exp in experiences:
                    key = (
                        exp.get("_store_key") or f"exp_{uuid.uuid4().hex[:12]}_migrated"
                    )
                    exp_clean = {k: v for k, v in exp.items() if k != "_store_key"}
                    try:
                        store.put(ns, key, exp_clean)
                        migrated_count += 1
                    except Exception as e:
                        logger.warning(
                            f"Failed to migrate experience {ns_key}/{key}: {e}"
                        )
            migrated_path = json_path.with_suffix(".json.migrated")
            json_path.rename(migrated_path)
            logger.info(
                f"Migrated {migrated_count} experiences from {json_path} "
                f"-> {migrated_path}"
            )
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to migrate from JSON: {e}")
