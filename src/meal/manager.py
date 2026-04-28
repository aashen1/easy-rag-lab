from __future__ import annotations

import json
import random
import shutil
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger

from src.exceptions import MealError
from src.meal.builders import build_chunks_if_needed, build_index_from_chunks
from src.meal.cache import ArtifactCache
from src.meal.hashes import (
    compute_chunker_config_hash,
    compute_data_id,
    compute_embedding_config_hash,
    compute_file_sha256,
    compute_index_key,
    compute_parser_config_hash,
    generate_collection_name,
)
from src.meal.models import MealConfig, MealFile, MealStatus
from src.meal.utils import (
    _infer_equivalence_groups,
    generate_timestamp_name,
    validate_meal_name,
)
from src.sampler import SamplingConfig, count_pdf_pages, determine_sample
from src.utils import ensure_dir

if TYPE_CHECKING:
    pass


class MealManager:
    def __init__(self, config: dict[str, Any]):
        """Initialize the MealManager with application configuration.

        Args:
            config: Application configuration dictionary containing 'meals',
                'parser', 'chunker', 'artifacts', and 'vector_store' sections.
        """
        self.config = config
        meals_config = config.get("meals", {})
        self.meals_dir = Path(meals_config.get("dir", "data/meals"))
        self.collection_prefix = meals_config.get("collection_prefix", "m_")
        self.raw_dir = Path(config.get("parser", {}).get("input_dir", "data/raw"))

        artifacts_config = config.get("artifacts", {})
        artifacts_base = artifacts_config.get("dir", "data/artifacts")
        self.artifacts_dir = Path(artifacts_base)
        self.cache = ArtifactCache(self.artifacts_dir, self.raw_dir)

    def _build_config_snapshot_and_hashes(
        self,
    ) -> tuple[dict[str, Any], dict[str, str]]:
        parser_config = self.config.get("parser", {})
        chunker_config = self.config.get("chunker", {})
        embedding_config = self.config.get("embedding", {})
        retrieval_config = self.config.get("retrieval", {})

        config_snapshot = {
            "parser": {
                "algorithm": parser_config.get("algorithm", "pymupdf4llm"),
                "input_dir": parser_config.get("input_dir", "data/raw"),
                "options": parser_config.get(
                    parser_config.get("algorithm", "pymupdf4llm"), {}
                ),
            },
            "chunker": {
                "chunk_size": chunker_config.get("chunk_size", 512),
                "chunk_overlap": chunker_config.get("chunk_overlap", 0),
                "encoding": chunker_config.get("encoding", "cl100k_base"),
            },
            "embedding": {
                "model_name": embedding_config.get("model_name", ""),
                "device": embedding_config.get("device", "cpu"),
            },
            "retrieval": {
                "top_k": retrieval_config.get("top_k", 5),
            },
        }

        config_hashes = {
            "parser": compute_parser_config_hash(config_snapshot["parser"]),
            "chunker": compute_chunker_config_hash(
                {
                    "chunk_size": config_snapshot["chunker"]["chunk_size"],
                    "chunk_overlap": config_snapshot["chunker"]["chunk_overlap"],
                    "encoding": config_snapshot["chunker"]["encoding"],
                }
            ),
            "embedding": compute_embedding_config_hash(config_snapshot["embedding"]),
        }

        return config_snapshot, config_hashes

    def _build_pipeline(
        self,
        *,
        meal_files: list[MealFile],
        config_snapshot: dict,
        config_hashes: dict,
        data_id: str,
        collection_name: str,
        pdfs_to_parse: list[Path],
        parsed_dir: Path,
        chunks_dir: Path,
        reuse_parsed: bool = False,
        source_parsed_dir: Path | None = None,
        source_chunks_dir: Path | None = None,
        composition: dict | None = None,
        sampling_config: dict | None = None,
        stats_extras: dict | None = None,
        meal_name: str,
        meal_dir: Path | None = None,
        force_chunk: bool = False,
    ) -> MealConfig:
        """Execute the shared parse-chunk-index-stats-manifest-config-save pipeline.

        Encapsulates the common flow shared by create_meal, merge_meals,
        extend_meal, and repair_meal: extract configs, copy source artifacts
        (for extend), parse PDFs, build chunks, build vector index, count
        stats, save artifact manifest, infer equivalence groups, build
        MealConfig, create meal directory, and save manifest.json.

        Args:
            meal_files: List of MealFile objects for this meal.
            config_snapshot: Configuration snapshot dictionary.
            config_hashes: Configuration hashes dictionary.
            data_id: Data identifier for this meal's file set.
            collection_name: Qdrant collection name for the vector index.
            pdfs_to_parse: List of PDF file paths that need parsing.
            parsed_dir: Directory for parsed artifacts.
            chunks_dir: Directory for chunked artifacts.
            reuse_parsed: If True, skip parsing (parsed results already available).
            source_parsed_dir: If provided, copy parsed files from this directory
                first (used by extend_meal).
            source_chunks_dir: If provided, copy chunk files from this directory
                first (used by extend_meal).
            composition: Composition metadata for the MealConfig.
            sampling_config: Sampling configuration for the MealConfig.
            stats_extras: Additional stats to merge into MealConfig.stats.
            meal_name: Name of the meal (for directory creation and logging).
            meal_dir: If provided, use this directory instead of creating a new
                one (used by repair_meal in-place mode).
            force_chunk: If True, force re-chunking even if chunks exist.

        Returns:
            MealConfig object for the created/rebuilt meal.

        Raises:
            OSError: If the manifest file cannot be written.
        """
        parser_config = self.config.get("parser", {})
        chunker_config = self.config.get("chunker", {})
        embedding_config = self.config.get("embedding", {})

        if source_parsed_dir is not None and source_parsed_dir.exists():
            for parsed_file in source_parsed_dir.rglob("*"):
                if parsed_file.is_file():
                    rel_parsed = parsed_file.relative_to(source_parsed_dir)
                    target_file = parsed_dir / rel_parsed
                    target_file.parent.mkdir(parents=True, exist_ok=True)
                    try:
                        shutil.copy2(parsed_file, target_file)
                    except Exception as e:
                        logger.warning(
                            f"Failed to copy parsed file {parsed_file}: {str(e)}"
                        )

        if source_chunks_dir is not None and source_chunks_dir.exists():
            for chunk_file in source_chunks_dir.rglob("*"):
                if chunk_file.is_file():
                    rel_chunk = chunk_file.relative_to(source_chunks_dir)
                    target_file = chunks_dir / rel_chunk
                    target_file.parent.mkdir(parents=True, exist_ok=True)
                    try:
                        shutil.copy2(chunk_file, target_file)
                    except Exception as e:
                        logger.warning(
                            f"Failed to copy chunk file {chunk_file}: {str(e)}"
                        )

        if not reuse_parsed and pdfs_to_parse:
            self._parse_pdfs_with_registry(parser_config, pdfs_to_parse, parsed_dir)

        build_chunks_if_needed(
            parsed_dir,
            chunks_dir,
            chunker_config,
            model_name=embedding_config.get("model_name"),
            force=force_chunk,
        )

        build_index_from_chunks(
            chunks_dir=chunks_dir,
            embedding_config=embedding_config,
            vector_store_config=self.config.get("vector_store", {}),
            collection_name=collection_name,
        )

        total_chunks = 0
        if chunks_dir.exists():
            for jsonl_file in chunks_dir.rglob("*.jsonl"):
                try:
                    with open(jsonl_file, encoding="utf-8") as f:
                        total_chunks += sum(1 for _ in f)
                except Exception:
                    pass

        total_pages = 0
        for meal_file in meal_files:
            pdf_path = self.raw_dir / meal_file.path
            try:
                if pdf_path.exists():
                    total_pages += count_pdf_pages(pdf_path)
            except Exception:
                pass

        artifact_manifest = {
            "data_id": data_id,
            "pdf_count": len(meal_files),
            "page_count": total_pages,
            "chunk_count": total_chunks,
            "created_at": datetime.now().isoformat(),
            "config_hashes": config_hashes,
            "pdf_inventory": {f.path: f.sha256 for f in meal_files},
        }
        self.cache.save_manifest(data_id, artifact_manifest)

        equivalence_groups = _infer_equivalence_groups([f.path for f in meal_files])

        stats: dict[str, Any] = {
            "total_pdfs": len(meal_files),
            "total_pages": total_pages,
            "total_chunks": total_chunks,
        }
        if stats_extras:
            stats.update(stats_extras)

        meal_config = MealConfig(
            data_id=data_id,
            name=meal_name,
            created_at=datetime.now().isoformat(),
            sampling_config=sampling_config,
            collection_name=collection_name,
            pdf_files=meal_files,
            config_snapshot=config_snapshot,
            config_hashes=config_hashes,
            stats=stats,
            equivalence_groups=equivalence_groups,
            composition=composition if composition is not None else {},
        )

        if meal_dir is None:
            meal_dir = self.get_meal_dir(meal_name)
            ensure_dir(str(meal_dir))
            ensure_dir(str(meal_dir / "test_sets"))

        manifest_path = meal_dir / "manifest.json"
        try:
            with open(manifest_path, "w", encoding="utf-8") as f:
                json.dump(meal_config.to_dict(), f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to write manifest for meal '{meal_name}': {str(e)}")
            raise

        return meal_config

    def create_meal(
        self,
        name: str | None,
        sampling_config: SamplingConfig,
        seed: int | None = None,
        force_parse: bool = False,
        force_chunk: bool = False,
    ) -> MealConfig:
        """Create a new meal by sampling PDFs, parsing, chunking, and indexing.

        Args:
            name: Desired meal name. If None, a timestamp-based name is generated.
            sampling_config: Configuration controlling how PDFs are sampled.
            seed: Random seed for reproducible sampling. If None, a random seed is used.
            force_parse: If True, re-parse PDFs even if cached parsed artifacts exist.
            force_chunk: If True, re-chunk documents even if cached chunk artifacts exist.

        Returns:
            MealConfig object for the newly created meal.

        Raises:
            ValueError: If the meal name is invalid, already exists, or no PDFs
                could be processed.
        """

        if name is None:
            name = generate_timestamp_name()

        if not validate_meal_name(name):
            raise MealError(
                f"Invalid meal name '{name}'. "
                "Only alphanumeric characters, underscores, and hyphens are allowed."
            )

        if self.meal_exists(name):
            raise MealError(f"Meal '{name}' already exists")

        if seed is None:
            seed = random.randint(0, 2**32 - 1)

        random.seed(seed)

        input_path = self.raw_dir
        all_pdfs = list(input_path.rglob("*.pdf"))
        if not all_pdfs:
            raise MealError("No PDF files found in input directory")

        sampled_pdfs = determine_sample(all_pdfs, sampling_config)

        meal_files: list[MealFile] = []
        for pdf_path in sampled_pdfs:
            try:
                rel_path = pdf_path.relative_to(input_path).as_posix()
                sha256 = compute_file_sha256(pdf_path)
                size_bytes = pdf_path.stat().st_size
                meal_files.append(
                    MealFile(
                        path=rel_path,
                        sha256=sha256,
                        size_bytes=size_bytes,
                    )
                )
            except Exception as e:
                logger.warning(f"Skipping {pdf_path}: {str(e)}")

        if not meal_files:
            raise MealError("No PDF files could be processed for the meal")

        data_id = compute_data_id(meal_files)
        config_snapshot, config_hashes = self._build_config_snapshot_and_hashes()
        index_key = compute_index_key(data_id, config_hashes)
        collection_name = generate_collection_name(index_key, self.collection_prefix)

        chunker_hash = config_hashes["chunker"]
        parser_hash = config_hashes["parser"]

        parsed_dir, chunks_dir = self.cache.ensure_dirs(
            data_id, chunker_hash, parser_hash
        )

        parser_config = self.config.get("parser", {})
        algorithm = parser_config.get("algorithm", "pymupdf4llm")
        parser_options = parser_config.get(algorithm, {})
        use_page_chunks = bool(parser_options.get("page_chunks", False))

        if use_page_chunks:
            expected_md_names = [
                Path(f.path).with_suffix(".pages.json").name for f in meal_files
            ]
        else:
            expected_md_names = [
                Path(f.path).with_suffix(".md").name for f in meal_files
            ]

        cache_hit_parse = False
        cache_hit_chunk = False
        reuse_parsed = False
        pdfs_to_parse: list[Path] = list(sampled_pdfs)

        full_parsed_dir = None
        if not force_parse:
            try:
                if self.cache.is_full_parsed_valid(parser_hash):
                    full_parsed_dir = self.cache.get_full_parsed_dir(parser_hash)
                    logger.info(
                        f"Found full parsed artifacts, reusing for meal '{name}'"
                    )
            except Exception as e:
                logger.debug(f"Full parsed check failed: {str(e)}")

        if full_parsed_dir is not None:
            self._reuse_full_parsed(
                meal_files, full_parsed_dir, parsed_dir, use_page_chunks
            )
            cache_hit_parse = True
            reuse_parsed = True
            pdfs_to_parse = []
        elif not force_parse and self.cache.parsed_exists(
            data_id, expected_md_names, parser_hash
        ):
            logger.info(f"Cache HIT: Parsed artifacts exist for data_id={data_id[:12]}")
            cache_hit_parse = True
            reuse_parsed = True
            pdfs_to_parse = []
        else:
            logger.info(
                f"Step 1: Parsing {len(sampled_pdfs)} PDFs for meal '{name}'..."
            )

        expected_jsonl_names = []
        for md_name in expected_md_names:
            if md_name.endswith(".pages.json"):
                base = md_name[: -len(".pages.json")]
                expected_jsonl_names.append(base + ".jsonl")
            else:
                expected_jsonl_names.append(Path(md_name).with_suffix(".jsonl").name)

        if not force_chunk and self.cache.chunks_exist(
            data_id, chunker_hash, expected_jsonl_names
        ):
            logger.info(
                f"Cache HIT: Chunked artifacts exist for chunker_hash={chunker_hash}"
            )
            cache_hit_chunk = True

        stats_extras = {
            "cache_hit_parse": cache_hit_parse,
            "cache_hit_chunk": cache_hit_chunk,
        }

        meal_config = self._build_pipeline(
            meal_files=meal_files,
            config_snapshot=config_snapshot,
            config_hashes=config_hashes,
            data_id=data_id,
            collection_name=collection_name,
            pdfs_to_parse=pdfs_to_parse,
            parsed_dir=parsed_dir,
            chunks_dir=chunks_dir,
            reuse_parsed=reuse_parsed,
            sampling_config={
                "mode": sampling_config.mode,
                "value": sampling_config.value,
                "seed": seed,
            },
            stats_extras=stats_extras,
            meal_name=name,
            force_chunk=force_chunk,
        )

        cache_status = []
        if cache_hit_parse:
            cache_status.append("parse")
        if cache_hit_chunk:
            cache_status.append("chunk")
        cache_str = ", ".join(cache_status) if cache_status else "none"

        logger.success(
            f"Meal '{name}' created successfully "
            f"[{data_id[:12]}] ({len(meal_files)} PDFs, {meal_config.stats['total_pages']} pages, {meal_config.stats['total_chunks']} chunks, cache: {cache_str})"
        )
        return meal_config

    def load_meal(self, name: str) -> MealConfig:
        """Load a meal configuration from its manifest file.

        Args:
            name: Name of the meal to load.

        Returns:
            MealConfig object loaded from the meal's manifest.

        Raises:
            FileNotFoundError: If the meal manifest file does not exist.
            ValueError: If the manifest file cannot be parsed.
        """
        meal_dir = self.get_meal_dir(name)
        manifest_path = meal_dir / "manifest.json"

        if not manifest_path.exists():
            raise MealError(f"Meal '{name}' not found (manifest missing)")

        try:
            with open(manifest_path, encoding="utf-8") as f:
                data = json.load(f)
            return MealConfig.from_dict(data)
        except Exception as e:
            raise MealError(f"Failed to load meal '{name}': {str(e)}") from e

    def find_equivalent_meals(self, data_id: str) -> list[MealConfig]:
        """Find all meals that share the same data ID.

        Args:
            data_id: Data identifier to search for.

        Returns:
            List of MealConfig objects with the matching data ID.
        """
        equivalents = []
        for meal in self.list_meals():
            if meal.data_id == data_id:
                equivalents.append(meal)
        return equivalents

    def find_full_dataset_meal(self) -> MealConfig | None:
        """Find the meal that contains all PDFs in raw_dir.

        Computes the full data_id from raw_dir via ArtifactCache, then
        searches all meals for one with a matching data_id.

        Returns:
            MealConfig if a matching meal is found, None otherwise.
        """
        try:
            full_data_id = self.cache._compute_full_data_id()
        except ValueError:
            logger.debug("Cannot compute full data_id: no PDFs in raw_dir")
            return None

        equivalents = self.find_equivalent_meals(full_data_id)
        if equivalents:
            logger.info(
                f"Found full-dataset meal '{equivalents[0].name}' "
                f"(data_id={full_data_id[:16]}...)"
            )
            return equivalents[0]

        logger.debug(
            f"No meal matches full data_id {full_data_id[:16]}... "
            f"— create a meal with sampling=1.0 first"
        )
        return None

    def list_meals(self) -> list[MealConfig]:
        """List all available meals by scanning the meals directory.

        Returns:
            List of MealConfig objects for all meals with valid manifests.
        """
        if not self.meals_dir.exists():
            return []

        meals = []
        for item in sorted(self.meals_dir.iterdir()):
            if item.is_dir():
                manifest_path = item / "manifest.json"
                if manifest_path.exists():
                    try:
                        with open(manifest_path, encoding="utf-8") as f:
                            data = json.load(f)
                        meals.append(MealConfig.from_dict(data))
                    except Exception as e:
                        logger.warning(f"Failed to load meal from {item}: {str(e)}")
        return meals

    def delete_meal(self, name: str) -> None:
        """Delete a meal and its associated Qdrant collection if not shared.

        Args:
            name: Name of the meal to delete.

        Raises:
            FileNotFoundError: If the meal does not exist.
            ValueError: If the meal manifest cannot be loaded.
        """
        meal_config = self.load_meal(name)
        meal_dir = self.get_meal_dir(name)

        from src.indexer import VectorIndexer

        try:
            indexer = VectorIndexer(
                persist_dir=self.config.get("vector_store", {}).get(
                    "persist_dir", "data/vector_store"
                ),
                collection_name=meal_config.collection_name,
                distance=self.config.get("vector_store", {}).get("distance", "Cosine"),
            )
            shared = self._is_collection_shared(
                meal_config.collection_name, exclude_name=name
            )
            if not shared:
                indexer.delete_collection()
                logger.info(
                    f"Deleted Qdrant collection '{meal_config.collection_name}'"
                )
            else:
                logger.info(
                    f"Collection '{meal_config.collection_name}' is shared with other meals, skipping deletion"
                )
        except Exception as e:
            logger.warning(f"Failed to delete Qdrant collection: {str(e)}")

        shutil.rmtree(meal_dir)
        logger.success(f"Meal '{name}' deleted successfully")

    def rename_meal(self, old_name: str, new_name: str) -> MealConfig:
        """Rename a meal by moving its directory and updating the manifest.

        Args:
            old_name: Current name of the meal.
            new_name: Desired new name for the meal.

        Returns:
            Updated MealConfig object with the new name.

        Raises:
            ValueError: If the new name is invalid or already exists.
        """
        if not validate_meal_name(new_name):
            raise MealError(
                f"Invalid meal name '{new_name}'. "
                "Only alphanumeric characters, underscores, and hyphens are allowed."
            )

        if self.meal_exists(new_name):
            raise MealError(f"Meal '{new_name}' already exists")

        meal_config = self.load_meal(old_name)
        old_dir = self.get_meal_dir(old_name)
        new_dir = self.get_meal_dir(new_name)

        old_dir.rename(new_dir)

        meal_config.name = new_name
        manifest_path = new_dir / "manifest.json"
        try:
            with open(manifest_path, "w", encoding="utf-8") as f:
                json.dump(meal_config.to_dict(), f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(
                f"Failed to write manifest after renaming meal from '{old_name}' to '{new_name}': {str(e)}"
            )
            raise

        logger.success(
            f"Meal renamed from '{old_name}' to '{new_name}' (data_id unchanged: {meal_config.data_id[:12]})"
        )
        return meal_config

    def copy_meal(self, source_name: str, target_name: str) -> MealConfig:
        """Copy a meal's directory and create a new manifest with the target name.

        The copied meal shares the same Qdrant collection as the source.

        Args:
            source_name: Name of the meal to copy from.
            target_name: Name for the new copied meal.

        Returns:
            MealConfig object for the newly created copy.

        Raises:
            ValueError: If the target name is invalid or already exists.
        """
        if not validate_meal_name(target_name):
            raise MealError(
                f"Invalid meal name '{target_name}'. "
                "Only alphanumeric characters, underscores, and hyphens are allowed."
            )

        if self.meal_exists(target_name):
            raise MealError(f"Meal '{target_name}' already exists")

        source_config = self.load_meal(source_name)
        source_dir = self.get_meal_dir(source_name)
        target_dir = self.get_meal_dir(target_name)

        shutil.copytree(source_dir, target_dir)

        new_config = MealConfig(
            data_id=source_config.data_id,
            name=target_name,
            created_at=source_config.created_at,
            sampling_config=source_config.sampling_config,
            collection_name=source_config.collection_name,
            pdf_files=source_config.pdf_files,
            config_snapshot=source_config.config_snapshot,
            config_hashes=source_config.config_hashes,
            stats=source_config.stats,
            equivalence_groups=source_config.equivalence_groups,
        )

        manifest_path = target_dir / "manifest.json"
        try:
            with open(manifest_path, "w", encoding="utf-8") as f:
                json.dump(new_config.to_dict(), f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(
                f"Failed to write manifest for copied meal '{target_name}': {str(e)}"
            )
            raise

        logger.success(
            f"Meal copied from '{source_name}' to '{target_name}' "
            f"(same data_id: {source_config.data_id[:12]}, shared collection: {source_config.collection_name})"
        )
        return new_config

    def merge_meals(
        self,
        meal_names: list[str],
        name: str | None = None,
    ) -> MealConfig:
        """Merge multiple meals into a new meal.

        Args:
            meal_names: List of meal names to merge.
            name: Name for the new merged meal. If None, generates a timestamp-based name.

        Returns:
            MealConfig object for the newly created merged meal.

        Raises:
            ValueError: If meal_names is empty or contains non-existent meals.
        """
        if not meal_names:
            raise MealError("meal_names cannot be empty")

        if name is None:
            name = generate_timestamp_name()

        if not validate_meal_name(name):
            raise MealError(
                f"Invalid meal name '{name}'. "
                "Only alphanumeric characters, underscores, and hyphens are allowed."
            )

        if self.meal_exists(name):
            raise MealError(f"Meal '{name}' already exists")

        source_configs: list[MealConfig] = []
        for meal_name in meal_names:
            if not self.meal_exists(meal_name):
                raise MealError(f"Meal '{meal_name}' does not exist")
            source_configs.append(self.load_meal(meal_name))

        seen_paths: set[str] = set()
        merged_pdf_files: list[MealFile] = []
        source_info: list[dict[str, Any]] = []
        total_input_pdfs = 0

        for source_config in source_configs:
            pdf_count_before = len(merged_pdf_files)
            for meal_file in source_config.pdf_files:
                total_input_pdfs += 1
                if meal_file.path not in seen_paths:
                    seen_paths.add(meal_file.path)
                    merged_pdf_files.append(meal_file)
            pdf_added = len(merged_pdf_files) - pdf_count_before
            source_info.append(
                {
                    "meal": source_config.name,
                    "pdf_count": pdf_added,
                }
            )

        if not merged_pdf_files:
            raise MealError("No PDF files found in source meals")

        duplicates = total_input_pdfs - len(merged_pdf_files)

        logger.info(
            f"Merging {len(meal_names)} meals: {', '.join(meal_names)} "
            f"({total_input_pdfs} total PDFs, {len(merged_pdf_files)} unique, {duplicates} duplicates)"
        )

        new_data_id = compute_data_id(merged_pdf_files)
        config_snapshot, config_hashes = self._build_config_snapshot_and_hashes()
        index_key = compute_index_key(new_data_id, config_hashes)
        collection_name = generate_collection_name(index_key, self.collection_prefix)

        chunker_hash = config_hashes["chunker"]
        parser_hash = config_hashes["parser"]

        parsed_dir, chunks_dir = self.cache.ensure_dirs(
            new_data_id, chunker_hash, parser_hash
        )

        parser_config = self.config.get("parser", {})
        algorithm = parser_config.get("algorithm", "pymupdf4llm")
        parser_options = parser_config.get(algorithm, {})
        use_page_chunks = bool(parser_options.get("page_chunks", False))

        pdfs_to_parse: list[Path] = []
        for meal_file in merged_pdf_files:
            pdf_path = self.raw_dir / meal_file.path
            if not pdf_path.exists():
                logger.warning(f"PDF file not found: {meal_file.path}, skipping")
                continue

            if use_page_chunks:
                expected_name = Path(meal_file.path).with_suffix(".pages.json").name
            else:
                expected_name = Path(meal_file.path).with_suffix(".md").name

            if not (parsed_dir / expected_name).exists():
                pdfs_to_parse.append(pdf_path)

        if pdfs_to_parse:
            logger.info(f"Parsing {len(pdfs_to_parse)} new PDFs for merged meal...")
        else:
            logger.info("All PDFs already parsed, reusing cached artifacts")

        composition = {
            "type": "merged",
            "sources": source_info,
            "dedup_info": {
                "total_input_pdfs": total_input_pdfs,
                "unique_pdfs": len(merged_pdf_files),
                "duplicates": duplicates,
            },
            "created_at": datetime.now().isoformat(),
        }

        meal_config = self._build_pipeline(
            meal_files=merged_pdf_files,
            config_snapshot=config_snapshot,
            config_hashes=config_hashes,
            data_id=new_data_id,
            collection_name=collection_name,
            pdfs_to_parse=pdfs_to_parse,
            parsed_dir=parsed_dir,
            chunks_dir=chunks_dir,
            composition=composition,
            meal_name=name,
        )

        logger.success(
            f"Meal '{name}' created successfully by merging {len(meal_names)} meals "
            f"[{new_data_id[:12]}] ({len(merged_pdf_files)} unique PDFs, {meal_config.stats['total_pages']} pages, {meal_config.stats['total_chunks']} chunks)"
        )
        return meal_config

    def check_meal_status(self, name: str) -> tuple[MealStatus, list[str]]:
        """Check the integrity of a meal's source PDF files.

        Args:
            name: Name of the meal to check.

        Returns:
            Tuple of (MealStatus, list of issue descriptions). The status
            indicates whether files are available, missing, changed, or mixed.
        """
        meal_config = self.load_meal(name)
        issues = []
        has_missing = False
        has_changed = False

        for meal_file in meal_config.pdf_files:
            file_path = self.raw_dir / meal_file.path
            if not file_path.exists():
                issues.append(f"MISSING: {meal_file.path}")
                has_missing = True
                continue

            try:
                current_sha256 = compute_file_sha256(file_path)
                if current_sha256 != meal_file.sha256:
                    issues.append(f"CHANGED: {meal_file.path}")
                    has_changed = True
            except Exception as e:
                issues.append(f"ERROR: {meal_file.path} ({str(e)})")
                has_changed = True

        if has_missing and has_changed:
            return MealStatus.MIXED, issues
        elif has_missing:
            return MealStatus.FILES_MISSING, issues
        elif has_changed:
            return MealStatus.FILES_CHANGED, issues
        else:
            return MealStatus.AVAILABLE, []

    def repair_meal(
        self,
        name: str,
        replacements: dict[str, str] | None = None,
        create_new: bool = False,
        new_name: str | None = None,
    ) -> MealConfig:
        """Repair a meal by replacing or removing corrupted/missing PDF files.

        Rebuilds the parsing, chunking, and indexing pipeline for the repaired
        set of PDF files.

        Args:
            name: Name of the meal to repair.
            replacements: Mapping from old relative file paths to new relative
                file paths within the raw directory.
            create_new: If True, create a new meal instead of modifying in-place.
            new_name: Name for the new meal when create_new is True. Defaults
                to '{name}_repaired'.

        Returns:
            MealConfig object for the repaired (or newly created) meal.

        Raises:
            ValueError: If no valid PDF files remain after repair, or if the
                target meal name already exists.
        """
        meal_config = self.load_meal(name)
        replacements = replacements or {}

        new_pdf_files = []
        for meal_file in meal_config.pdf_files:
            if meal_file.path in replacements:
                new_rel_path = replacements[meal_file.path]
                new_abs_path = self.raw_dir / new_rel_path
                if new_abs_path.exists():
                    new_sha256 = compute_file_sha256(new_abs_path)
                    new_size = new_abs_path.stat().st_size
                    new_pdf_files.append(
                        MealFile(
                            path=new_rel_path,
                            sha256=new_sha256,
                            size_bytes=new_size,
                        )
                    )
                    logger.info(f"Replaced: {meal_file.path} -> {new_rel_path}")
                else:
                    logger.warning(
                        f"Replacement file not found: {new_rel_path}, keeping original"
                    )
                    new_pdf_files.append(meal_file)
            else:
                file_path = self.raw_dir / meal_file.path
                if file_path.exists():
                    current_sha256 = compute_file_sha256(file_path)
                    if current_sha256 == meal_file.sha256:
                        new_pdf_files.append(meal_file)
                    else:
                        logger.warning(
                            f"File changed but no replacement specified: {meal_file.path}, skipping"
                        )
                else:
                    logger.warning(
                        f"File missing and no replacement specified: {meal_file.path}, skipping"
                    )

        if not new_pdf_files:
            raise MealError("No valid PDF files remain after repair")

        new_data_id = compute_data_id(new_pdf_files)
        config_snapshot, config_hashes = self._build_config_snapshot_and_hashes()
        index_key = compute_index_key(new_data_id, config_hashes)
        new_collection_name = generate_collection_name(
            index_key, self.collection_prefix
        )

        if create_new:
            target_name = new_name or f"{name}_repaired"
            if self.meal_exists(target_name):
                raise MealError(f"Meal '{target_name}' already exists")
            target_meal_dir: Path | None = None
        else:
            target_name = name
            logger.warning(
                f"In-place repair will change the data_id of meal '{name}' "
                f"from {meal_config.data_id[:12]} to {new_data_id[:12]}"
            )
            try:
                from src.indexer import VectorIndexer

                old_indexer = VectorIndexer(
                    persist_dir=self.config.get("vector_store", {}).get(
                        "persist_dir", "data/vector_store"
                    ),
                    collection_name=meal_config.collection_name,
                    distance=self.config.get("vector_store", {}).get(
                        "distance", "Cosine"
                    ),
                )
                shared = self._is_collection_shared(
                    meal_config.collection_name, exclude_name=name
                )
                if not shared:
                    old_indexer.delete_collection()
            except Exception as e:
                logger.warning(f"Failed to delete old collection: {str(e)}")
            target_meal_dir = self.get_meal_dir(target_name)

        chunker_hash = config_hashes["chunker"]
        parser_hash = config_hashes["parser"]
        parsed_dir, chunks_dir = self.cache.ensure_dirs(
            new_data_id, chunker_hash, parser_hash
        )

        sampled_pdfs = [self.raw_dir / f.path for f in new_pdf_files]

        logger.info(f"Rebuilding index for repaired meal '{target_name}'...")

        new_config = self._build_pipeline(
            meal_files=new_pdf_files,
            config_snapshot=config_snapshot,
            config_hashes=config_hashes,
            data_id=new_data_id,
            collection_name=new_collection_name,
            pdfs_to_parse=sampled_pdfs,
            parsed_dir=parsed_dir,
            chunks_dir=chunks_dir,
            sampling_config=meal_config.sampling_config,
            meal_name=target_name,
            meal_dir=target_meal_dir,
        )

        logger.success(
            f"Meal '{target_name}' repaired successfully "
            f"[{new_data_id[:12]}] ({len(new_pdf_files)} PDFs, {new_config.stats['total_pages']} pages, {new_config.stats['total_chunks']} chunks)"
        )
        return new_config

    def meal_exists(self, name: str) -> bool:
        """Check whether a meal with the given name exists.

        Args:
            name: Name of the meal to check.

        Returns:
            True if the meal directory and its manifest file both exist.
        """
        meal_dir = self.get_meal_dir(name)
        return meal_dir.exists() and (meal_dir / "manifest.json").exists()

    def get_meal_dir(self, name: str) -> Path:
        """Get the filesystem path for a meal's directory.

        Args:
            name: Name of the meal.

        Returns:
            Path to the meal directory under the meals root.
        """
        return self.meals_dir / name

    def _is_collection_shared(
        self, collection_name: str, exclude_name: str | None = None
    ) -> bool:
        for meal in self.list_meals():
            if meal.name == exclude_name:
                continue
            if meal.collection_name == collection_name:
                return True
        return False

    def extend_meal(
        self,
        source_meal: str,
        new_pdfs: list[str | Path],
        name: str | None = None,
    ) -> MealConfig:
        """Extend an existing meal by adding new PDF files.

        Args:
            source_meal: Name of the source meal to extend.
            new_pdfs: List of new PDF file paths to add (relative to raw_dir or absolute).
            name: Name for the new meal. If None, a timestamp-based name is generated.

        Returns:
            MealConfig object for the newly created extended meal.

        Raises:
            ValueError: If the source meal does not exist, or if none of the new PDFs
                exist, or if all new PDFs already exist in the source meal.
        """
        if not self.meal_exists(source_meal):
            raise MealError(f"Source meal '{source_meal}' does not exist")

        if name is None:
            name = generate_timestamp_name()

        if not validate_meal_name(name):
            raise MealError(
                f"Invalid meal name '{name}'. "
                "Only alphanumeric characters, underscores, and hyphens are allowed."
            )

        if self.meal_exists(name):
            raise MealError(f"Meal '{name}' already exists")

        source_config = self.load_meal(source_meal)

        existing_paths = {f.path for f in source_config.pdf_files}

        valid_new_pdfs: list[tuple[Path, str, int]] = []
        skipped_files: list[str] = []

        for pdf_input in new_pdfs:
            pdf_path = pdf_input if isinstance(pdf_input, Path) else Path(pdf_input)

            if not pdf_path.is_absolute():
                pdf_path = self.raw_dir / pdf_path

            if not pdf_path.exists():
                raise MealError(f"PDF file does not exist: {pdf_input}")

            try:
                rel_path_obj = pdf_path.relative_to(self.raw_dir)
                rel_path = rel_path_obj.as_posix()
            except ValueError as e:
                raise MealError(
                    f"PDF file '{pdf_input}' is not within the raw directory"
                ) from e

            if rel_path in existing_paths:
                logger.warning(
                    f"PDF '{rel_path}' already exists in source meal '{source_meal}', skipping"
                )
                skipped_files.append(rel_path)
                continue

            sha256 = compute_file_sha256(pdf_path)
            size_bytes = pdf_path.stat().st_size
            valid_new_pdfs.append((pdf_path, rel_path, size_bytes))

        if not valid_new_pdfs:
            raise MealError(
                "No new PDF files to add (all files either don't exist or are already in the source meal)"
            )

        added_files = [rel_path for _, rel_path, _ in valid_new_pdfs]

        all_meal_files = list(source_config.pdf_files)
        for pdf_path, rel_path, size_bytes in valid_new_pdfs:
            sha256 = compute_file_sha256(pdf_path)
            all_meal_files.append(
                MealFile(
                    path=rel_path,
                    sha256=sha256,
                    size_bytes=size_bytes,
                )
            )

        new_data_id = compute_data_id(all_meal_files)
        config_snapshot, config_hashes = self._build_config_snapshot_and_hashes()
        index_key = compute_index_key(new_data_id, config_hashes)
        collection_name = generate_collection_name(index_key, self.collection_prefix)

        chunker_hash = config_hashes["chunker"]
        parser_hash = config_hashes["parser"]

        source_parsed_dir = self.cache.get_parsed_dir(
            source_config.data_id, parser_hash
        )
        source_chunks_dir = self.cache.get_chunks_dir(
            source_config.data_id, chunker_hash
        )

        new_parsed_dir, new_chunks_dir = self.cache.ensure_dirs(
            new_data_id, chunker_hash, parser_hash
        )

        logger.info(
            f"Extending meal '{source_meal}' with {len(valid_new_pdfs)} new PDFs..."
        )

        new_pdf_paths = [pdf_path for pdf_path, _, _ in valid_new_pdfs]

        composition: dict[str, Any] = {
            "type": "extended",
            "base_meal": source_meal,
            "added_files": added_files,
            "created_at": datetime.now().isoformat(),
        }
        if skipped_files:
            composition["skipped_files"] = skipped_files

        meal_config = self._build_pipeline(
            meal_files=all_meal_files,
            config_snapshot=config_snapshot,
            config_hashes=config_hashes,
            data_id=new_data_id,
            collection_name=collection_name,
            pdfs_to_parse=new_pdf_paths,
            parsed_dir=new_parsed_dir,
            chunks_dir=new_chunks_dir,
            source_parsed_dir=source_parsed_dir,
            source_chunks_dir=source_chunks_dir,
            composition=composition,
            sampling_config=source_config.sampling_config,
            meal_name=name,
        )

        logger.success(
            f"Meal '{name}' created successfully by extending '{source_meal}' "
            f"[{new_data_id[:12]}] ({len(all_meal_files)} PDFs, {meal_config.stats['total_pages']} pages, {meal_config.stats['total_chunks']} chunks, "
            f"added: {len(added_files)}, skipped: {len(skipped_files)})"
        )
        return meal_config

    def _parse_pdfs_with_registry(
        self,
        parser_config: dict[str, Any],
        pdf_files: list[Path],
        output_dir: Path,
    ) -> None:
        """Parse PDFs using the ParserRegistry.

        Args:
            parser_config: Parser configuration dictionary.
            pdf_files: List of PDF file paths to parse.
            output_dir: Directory for parsed output files.
        """
        from src.parsers.registry import ParserRegistry

        algorithm = parser_config.get("algorithm", "pymupdf4llm")
        parser_options = parser_config.get(algorithm, {})
        parser = ParserRegistry.get(algorithm, parser_options)
        use_page_chunks = bool(parser_options.get("page_chunks", False))

        for pdf_file in pdf_files:
            try:
                relative_path = pdf_file.relative_to(self.raw_dir)
                if use_page_chunks:
                    output_file = output_dir / relative_path.with_suffix(".pages.json")
                else:
                    output_file = output_dir / relative_path.with_suffix(".md")

                if output_file.exists():
                    logger.info(f"Skipping (already parsed): {pdf_file.name}")
                    continue

                result = parser.parse(str(pdf_file))

                output_file.parent.mkdir(parents=True, exist_ok=True)

                if use_page_chunks:
                    pages_data = [
                        {
                            "page_number": page.page_number,
                            "text": page.text,
                            "metadata": page.metadata,
                        }
                        for page in result.pages
                    ]
                    with open(output_file, "w", encoding="utf-8") as f:
                        json.dump(pages_data, f, ensure_ascii=False, indent=2)
                else:
                    with open(output_file, "w", encoding="utf-8") as f:
                        for page in result.pages:
                            f.write(page.text)
                            f.write("\n\n")

                logger.success(f"Parsed: {pdf_file.name} -> {output_file.name}")
            except Exception as e:
                logger.error(f"Failed to parse {pdf_file}: {str(e)}")

    def _reuse_full_parsed(
        self,
        meal_files: list[MealFile],
        full_parsed_dir: Path,
        meal_parsed_dir: Path,
        use_page_chunks: bool,
    ) -> None:
        """Copy relevant parsed files from full-mode artifacts to meal artifacts.

        Only copies files that belong to this meal (subset of full raw_dir).

        Args:
            meal_files: List of MealFile objects for this meal.
            full_parsed_dir: Source directory with full-mode parsed results.
            meal_parsed_dir: Destination directory for this meal's artifacts.
            use_page_chunks: Whether to look for .pages.json or .md files.
        """
        copied = 0
        for meal_file in meal_files:
            if use_page_chunks:
                src_name = Path(meal_file.path).with_suffix(".pages.json")
            else:
                src_name = Path(meal_file.path).with_suffix(".md")

            src = full_parsed_dir / src_name
            dst = meal_parsed_dir / src_name

            if not src.exists():
                logger.warning(
                    f"Full parsed file not found: {src}, will parse separately"
                )
                continue

            dst.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copy2(src, dst)
                copied += 1
            except Exception as e:
                logger.error(f"Failed to copy {src} to {dst}: {str(e)}")

        logger.info(
            f"Reused {copied}/{len(meal_files)} parsed files from full-mode cache"
        )
