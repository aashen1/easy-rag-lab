from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from loguru import logger


class ExperienceStore:
    def __init__(self, store: Any) -> None:
        self._store = store

    def save_experience(
        self, namespace: tuple[str, ...], experience: dict[str, Any]
    ) -> str:
        key = f"exp_{uuid.uuid4().hex[:8]}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        experience["timestamp"] = datetime.now().isoformat()
        try:
            self._store.put(namespace, key, experience)
            logger.info(f"Saved experience to {namespace}/{key}")
            return key
        except Exception as e:
            logger.error(f"Failed to save experience: {e}")
            raise

    def search_experiences(
        self, namespace: tuple[str, ...], query: str | None = None
    ) -> list[dict[str, Any]]:
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
