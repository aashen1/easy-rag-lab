from __future__ import annotations

import contextlib
import json
import os
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, ClassVar

from loguru import logger


class ExperienceStore:
    _default_persist_path: ClassVar[Path | None] = None

    def __init__(self, store: Any, persist_path: str | Path | None = None) -> None:
        self._store = store
        if persist_path is not None:
            self._persist_path = Path(persist_path)
            ExperienceStore._default_persist_path = self._persist_path
            self._load_from_file()
        else:
            self._persist_path = ExperienceStore._default_persist_path

    @staticmethod
    def _namespace_to_key(namespace: tuple[str, ...]) -> str:
        return "/".join(namespace)

    @staticmethod
    def _key_to_namespace(key: str) -> tuple[str, ...]:
        return tuple(key.split("/"))

    def _save_to_file(self) -> None:
        if self._persist_path is None:
            return
        try:
            namespaces_data: dict[str, list[dict[str, Any]]] = {}
            namespaces = self._store.list_namespaces(limit=10000)
            for ns in namespaces:
                ns_key = self._namespace_to_key(ns)
                items = self._store.search(ns, limit=10000)
                namespaces_data[ns_key] = [item.value for item in items]

            self._persist_path.parent.mkdir(parents=True, exist_ok=True)
            data = {"namespaces": namespaces_data}

            tmp_fd, tmp_path = tempfile.mkstemp(
                dir=str(self._persist_path.parent), suffix=".json"
            )
            try:
                with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                os.replace(tmp_path, str(self._persist_path))
            except Exception:
                with contextlib.suppress(OSError):
                    os.unlink(tmp_path)
                raise

            logger.info(f"Persisted experiences to {self._persist_path}")
        except Exception as e:
            logger.error(f"Failed to persist experiences: {e}")

    def _load_from_file(self) -> dict[str, list[dict[str, Any]]]:
        if self._persist_path is None:
            return {}
        try:
            if not self._persist_path.exists():
                logger.debug(f"No persist file at {self._persist_path}, starting fresh")
                return {}
            with open(self._persist_path, encoding="utf-8") as f:
                data = json.load(f)
            namespaces = data.get("namespaces", {})
            for ns_key, experiences in namespaces.items():
                ns = self._key_to_namespace(ns_key)
                for exp in experiences:
                    key = exp.get("_store_key") or f"exp_{uuid.uuid4().hex[:8]}_loaded"
                    exp_clean = {k: v for k, v in exp.items() if k != "_store_key"}
                    try:
                        self._store.put(ns, key, exp_clean)
                    except Exception as e:
                        logger.warning(f"Failed to load experience {ns_key}/{key}: {e}")
            logger.info(
                f"Loaded experiences from {self._persist_path} "
                f"({len(namespaces)} namespaces)"
            )
            return namespaces
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to load experiences from file: {e}")
            return {}

    def save_experience(
        self, namespace: tuple[str, ...], experience: dict[str, Any]
    ) -> str:
        key = f"exp_{uuid.uuid4().hex[:8]}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        experience["timestamp"] = datetime.now().isoformat()
        try:
            self._store.put(namespace, key, experience)
            logger.info(f"Saved experience to {namespace}/{key}")
            self._save_to_file()
            return key
        except Exception as e:
            logger.error(f"Failed to save experience: {e}")
            raise

    def search_experiences(
        self, namespace: tuple[str, ...], query: str | None = None
    ) -> list[dict[str, Any]]:
        """Search experiences by query string.

        NOTE: This method is currently unused in the agent graph.
        ``agent_node`` uses ``get_all_experiences`` instead because
        InMemoryStore does not support semantic search.  This method
        is retained for future use when a persistent store with
        search capability is adopted.
        """
        try:
            kwargs: dict[str, Any] = {}
            if query:
                kwargs["query"] = query
            items = self._store.search(namespace, **kwargs)
            return [item.value for item in items]
        except Exception as e:
            logger.error(f"Failed to search experiences: {e}")
            return []

    def get_all_experiences(self, namespace: tuple[str, ...]) -> list[dict[str, Any]]:
        try:
            items = self._store.search(namespace)
            return [item.value for item in items]
        except Exception as e:
            logger.error(f"Failed to get all experiences: {e}")
            return []
