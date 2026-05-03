from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any

from loguru import logger


class MealStatus(Enum):
    AVAILABLE = "available"
    FILES_MISSING = "files_missing"
    FILES_CHANGED = "files_changed"
    MIXED = "mixed"


@dataclass
class MealFile:
    path: str
    sha256: str
    size_bytes: int


@dataclass
class MealConfig:
    data_id: str
    name: str
    created_at: str
    sampling_config: dict[str, Any] | None
    collection_name: str
    pdf_files: list[MealFile]
    config_snapshot: dict[str, Any] | None = None
    config_hashes: dict[str, str] | None = None
    stats: dict[str, Any] = field(default_factory=dict)
    equivalence_groups: dict[str, list[str]] = field(default_factory=dict)
    composition: dict[str, Any] = field(default_factory=dict)
    creation_mode: str = "random"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MealConfig:
        """Reconstruct a MealConfig from a dictionary representation.

        Args:
            data: Dictionary containing meal configuration data, typically
                loaded from a manifest.json file.

        Returns:
            MealConfig instance with all fields populated from the dictionary.

        Raises:
            KeyError: If required fields (name, created_at, collection_name)
                are missing from the input dictionary.
        """
        pdf_files = [MealFile(**f) for f in data.get("pdf_files", [])]

        if "uuid" in data and "data_id" not in data:
            logger.warning(
                f"Loading legacy manifest with UUID '{data['uuid']}', "
                "migrating to data_id-based identity"
            )
            sorted_hashes = sorted(f["sha256"] for f in data.get("pdf_files", []))
            combined = "|".join(sorted_hashes)
            data_id = hashlib.sha256(combined.encode()).hexdigest()
        else:
            data_id = data.get("data_id", "")

        return cls(
            data_id=data_id,
            name=data["name"],
            created_at=data["created_at"],
            sampling_config=data.get("sampling_config"),
            collection_name=data["collection_name"],
            pdf_files=pdf_files,
            config_snapshot=data.get("config_snapshot"),
            config_hashes=data.get("config_hashes"),
            stats=data.get("stats", {}),
            equivalence_groups=data.get("equivalence_groups", {}),
            composition=data.get("composition", {}),
            creation_mode=data.get("creation_mode", "random"),
        )
