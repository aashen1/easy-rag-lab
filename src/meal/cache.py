from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from loguru import logger

from src.meal.hashes import compute_data_id, compute_file_sha256
from src.meal.models import MealFile
from src.utils import ensure_dir


class ArtifactCache:
    def __init__(self, artifacts_dir: Path, raw_dir: Path | None = None):
        """Initialize the ArtifactCache with a base artifacts directory.

        Args:
            artifacts_dir: Root directory for storing cached artifacts.
            raw_dir: Root directory containing source PDF files. Required for
                full-mode operations (computing full data_id).
        """
        self.artifacts_dir = artifacts_dir
        self.raw_dir = raw_dir

    @property
    def pointers_dir(self) -> Path:
        """Directory for pointer files that provide quick access to artifacts.

        Returns:
            Path to the ``_pointers`` subdirectory under artifacts_dir.
        """
        return self.artifacts_dir / "_pointers"

    def save_pointer(self, name: str, target: str) -> None:
        """Save a pointer file pointing to an artifact directory.

        Pointer files are plain text files stored under ``_pointers/``
        that record the relative path to an artifact directory. This
        allows users to quickly locate full-parse artifacts without
        knowing the hash-based directory name.

        Args:
            name: Pointer name (e.g., ``'full_parsed'``, ``'full_chunks'``).
                Used as the filename with a ``.pointer`` suffix.
            target: Relative path under ``artifacts_dir``
                (e.g., ``'d3a711e6/parsed_a1b2c3d4'``).
        """
        self.pointers_dir.mkdir(parents=True, exist_ok=True)
        pointer_file = self.pointers_dir / f"{name}.pointer"
        try:
            pointer_file.write_text(target, encoding="utf-8")
            logger.debug(f"Saved pointer '{name}' -> {target}")
        except Exception as e:
            logger.warning(f"Failed to save pointer '{name}': {str(e)}")

    def resolve_pointer(self, name: str) -> Path | None:
        """Resolve a pointer to an actual artifact directory.

        Args:
            name: Pointer name to resolve (without ``.pointer`` suffix).

        Returns:
            Full Path to the artifact directory, or None if the pointer
            file does not exist or the target directory does not exist.
        """
        pointer_file = self.pointers_dir / f"{name}.pointer"
        if not pointer_file.exists():
            return None

        try:
            relative_path = pointer_file.read_text(encoding="utf-8").strip()
            target = self.artifacts_dir / relative_path
            if target.exists():
                return target
            logger.warning(f"Pointer '{name}' points to non-existent path: {target}")
            return None
        except Exception as e:
            logger.warning(f"Failed to resolve pointer '{name}': {str(e)}")
            return None

    def _compute_full_data_id(self) -> str:
        """Compute data_id for all PDFs in the raw directory.

        Returns:
            Deterministic data_id based on SHA-256 hashes of all PDFs.

        Raises:
            ValueError: If raw_dir is not set or contains no PDFs.
        """
        if self.raw_dir is None:
            raise ValueError("raw_dir must be set to compute full data_id")

        all_pdfs = sorted(self.raw_dir.rglob("*.pdf"))
        if not all_pdfs:
            raise ValueError("No PDF files found in raw directory")

        pdf_files = []
        for pdf_path in all_pdfs:
            try:
                rel_path = pdf_path.relative_to(self.raw_dir).as_posix()
                sha256 = compute_file_sha256(pdf_path)
                size_bytes = pdf_path.stat().st_size
                pdf_files.append(
                    MealFile(
                        path=rel_path,
                        sha256=sha256,
                        size_bytes=size_bytes,
                    )
                )
            except Exception as e:
                logger.warning(f"Skipping {pdf_path}: {str(e)}")

        if not pdf_files:
            raise ValueError("No PDF files could be processed")

        return compute_data_id(pdf_files)

    def get_artifact_group_dir(self, data_id: str) -> Path:
        """Get the artifact group directory for a given data ID.

        Args:
            data_id: Data identifier string.

        Returns:
            Path to the artifact group directory using the first 16 chars of data_id.
        """
        short_id = data_id[:16]
        return self.artifacts_dir / short_id

    def get_parsed_dir(self, data_id: str, parser_hash: str | None = None) -> Path:
        """Get the directory for parsed artifacts of a given data ID.

        Args:
            data_id: Data identifier string.
            parser_hash: Short hash of the parser configuration. If provided,
                the directory name includes the hash suffix.

        Returns:
            Path to the 'parsed' or 'parsed_{parser_hash}' subdirectory.
        """
        group_dir = self.get_artifact_group_dir(data_id)
        if parser_hash:
            return group_dir / f"parsed_{parser_hash}"
        return group_dir / "parsed"

    def get_chunks_dir(self, data_id: str, chunker_hash: str) -> Path:
        """Get the directory for chunked artifacts of a given data ID and chunker hash.

        Args:
            data_id: Data identifier string.
            chunker_hash: Short hash of the chunker configuration.

        Returns:
            Path to the 'chunks_{chunker_hash}' subdirectory within the artifact group.
        """
        group_dir = self.get_artifact_group_dir(data_id)
        return group_dir / f"chunks_{chunker_hash}"

    def parsed_exists(
        self,
        data_id: str,
        expected_files: list[str],
        parser_hash: str | None = None,
        manifest: dict[str, Any] | None = None,
    ) -> bool:
        """Check whether parsed artifacts exist and contain all expected files.

        Args:
            data_id: Data identifier string.
            expected_files: List of expected markdown file names.
            parser_hash: Short hash of the parser configuration.
            manifest: Optional manifest dict for SHA-256 validation. If provided,
                source files are validated against pdf_inventory.

        Returns:
            True if the parsed directory exists and contains all expected .md files.
            When manifest is provided, also validates source file SHA-256 hashes.
        """
        parsed_dir = self.get_parsed_dir(data_id, parser_hash)
        if not parsed_dir.exists():
            return False
        existing = set(p.name for p in parsed_dir.rglob("*.md"))
        if not set(expected_files).issubset(existing):
            return False
        if (
            manifest is not None
            and "pdf_inventory" in manifest
            and self.raw_dir is not None
        ):
            for rel_path, expected_sha in manifest["pdf_inventory"].items():
                pdf_path = self.raw_dir / rel_path
                if not pdf_path.exists():
                    return False
                if compute_file_sha256(pdf_path) != expected_sha:
                    return False
        return True

    def chunks_exist(
        self,
        data_id: str,
        chunker_hash: str,
        expected_files: list[str],
        manifest: dict[str, Any] | None = None,
    ) -> bool:
        """Check whether chunked artifacts exist and contain all expected files.

        Args:
            data_id: Data identifier string.
            chunker_hash: Short hash of the chunker configuration.
            expected_files: List of expected JSONL file names.
            manifest: Optional manifest dict for SHA-256 validation. If provided,
                source files are validated against pdf_inventory.

        Returns:
            True if the chunks directory exists and contains all expected .jsonl files.
            When manifest is provided, also validates source file SHA-256 hashes.
        """
        chunks_dir = self.get_chunks_dir(data_id, chunker_hash)
        if not chunks_dir.exists():
            return False
        existing = set(p.name for p in chunks_dir.rglob("*.jsonl"))
        if not set(expected_files).issubset(existing):
            return False
        if (
            manifest is not None
            and "pdf_inventory" in manifest
            and self.raw_dir is not None
        ):
            for rel_path, expected_sha in manifest["pdf_inventory"].items():
                pdf_path = self.raw_dir / rel_path
                if not pdf_path.exists():
                    return False
                if compute_file_sha256(pdf_path) != expected_sha:
                    return False
        return True

    def ensure_dirs(
        self, data_id: str, chunker_hash: str, parser_hash: str | None = None
    ) -> tuple[Path, Path]:
        """Ensure that artifact directories exist, creating them if necessary.

        Args:
            data_id: Data identifier string.
            chunker_hash: Short hash of the chunker configuration.
            parser_hash: Short hash of the parser configuration.

        Returns:
            Tuple of (parsed_dir, chunks_dir) paths that are guaranteed to exist.
        """
        group_dir = self.get_artifact_group_dir(data_id)
        ensure_dir(str(group_dir))
        parsed_dir = self.get_parsed_dir(data_id, parser_hash)
        ensure_dir(str(parsed_dir))
        chunks_dir = self.get_chunks_dir(data_id, chunker_hash)
        ensure_dir(str(chunks_dir))
        return parsed_dir, chunks_dir

    def save_manifest(self, data_id: str, manifest: dict[str, Any]) -> None:
        """Save an artifact manifest JSON file for a given data ID.

        Args:
            data_id: Data identifier string.
            manifest: Dictionary to serialize as the manifest.

        Returns:
            True if saved successfully, False otherwise.
        """
        group_dir = self.get_artifact_group_dir(data_id)
        ensure_dir(str(group_dir))
        manifest_path = group_dir / "manifest.json"
        lock_path = group_dir / "manifest.json.lock"
        try:
            from filelock import FileLock

            lock = FileLock(str(lock_path), timeout=30)
            with lock, open(manifest_path, "w", encoding="utf-8") as f:
                json.dump(manifest, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            logger.error(f"Failed to save manifest for data_id {data_id}: {str(e)}")
            return False

    def load_manifest(self, data_id: str) -> dict[str, Any] | None:
        """Load an artifact manifest JSON file for a given data ID.

        Args:
            data_id: Data identifier string.

        Returns:
            Parsed manifest dictionary, or None if the manifest file does not exist.
        """
        group_dir = self.get_artifact_group_dir(data_id)
        manifest_path = group_dir / "manifest.json"
        if not manifest_path.exists():
            return None
        lock_path = group_dir / "manifest.json.lock"
        try:
            from filelock import FileLock

            lock = FileLock(str(lock_path), timeout=30)
            with lock, open(manifest_path, encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load manifest for data_id {data_id}: {str(e)}")
            return None

    def get_full_parsed_dir(self, parser_hash: str) -> Path:
        """Get the parsed directory for full-mode (all PDFs in raw_dir).

        Args:
            parser_hash: Short hash of the parser configuration.

        Returns:
            Path to the parsed directory for full data_id.
        """
        full_data_id = self._compute_full_data_id()
        return self.get_parsed_dir(full_data_id, parser_hash)

    def save_full_manifest(self, manifest: dict[str, Any]) -> None:
        """Save manifest for full-mode parsing results.

        Args:
            manifest: Dictionary to serialize as the manifest.
        """
        full_data_id = self._compute_full_data_id()
        return self.save_manifest(full_data_id, manifest)

    def load_full_manifest(self) -> dict[str, Any] | None:
        """Load manifest for full-mode parsing results.

        Returns:
            Parsed manifest dictionary, or None if not found.
        """
        full_data_id = self._compute_full_data_id()
        return self.load_manifest(full_data_id)

    def is_full_parsed_valid(self, parser_hash: str) -> bool:
        """Check if full-mode parsed artifacts are valid and cache can be reused.

        Validates that:
        1. The parsed directory exists with parser_hash
        2. Manifest exists and contains pdf_inventory
        3. No previously failed files exist (retry them)
        4. All source PDFs have matching SHA-256 hashes
        5. All expected parsed files exist

        Args:
            parser_hash: Short hash of the parser configuration.

        Returns:
            True if all validations pass, False otherwise.
        """
        try:
            manifest = self.load_full_manifest()
            if not manifest or "pdf_inventory" not in manifest:
                return False

            parsed_dir = self.get_full_parsed_dir(parser_hash)
            if not parsed_dir.exists():
                return False

            failed_inventory = manifest.get("failed_inventory", {})
            if failed_inventory:
                logger.info(
                    f"Found {len(failed_inventory)} previously failed files, "
                    "invalidating cache for retry"
                )
                return False

            pdf_inventory = manifest["pdf_inventory"]
            for rel_path, expected_sha in pdf_inventory.items():
                pdf_path = self.raw_dir / rel_path
                if not pdf_path.exists():
                    return False
                if compute_file_sha256(pdf_path) != expected_sha:
                    return False

                if rel_path.endswith(".pages.json"):
                    parsed_file = parsed_dir / Path(rel_path).with_suffix(".pages.json")
                else:
                    parsed_file = parsed_dir / Path(rel_path).with_suffix(".md")
                if not parsed_file.exists():
                    return False

            return True
        except Exception as e:
            logger.warning(f"Full parsed validation failed: {str(e)}")
            return False
