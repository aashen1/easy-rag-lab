from __future__ import annotations

import contextlib
import hashlib
import json
import random
import re
import shutil
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger

from src.sampler import SamplingConfig, count_pdf_pages, determine_sample
from src.utils import ensure_dir

if TYPE_CHECKING:
    from src.indexer import VectorIndexer


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
            sorted_hashes = sorted(f["sha256"]
                                   for f in data.get("pdf_files", []))
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
        )


def compute_file_sha256(file_path: Path, chunk_size: int = 8192) -> str:
    """Compute SHA-256 hash of a file by reading it in chunks.

    Args:
        file_path: Path to the file to hash.
        chunk_size: Number of bytes to read per iteration.

    Returns:
        Hexadecimal SHA-256 digest string.
    """
    sha256 = hashlib.sha256()
    try:
        with open(file_path, "rb") as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                sha256.update(chunk)
        return sha256.hexdigest()
    except Exception as e:
        logger.error(f"Failed to compute SHA256 for {file_path}: {str(e)}")
        return ""


def compute_data_id(pdf_files: list[MealFile]) -> str:
    """Compute a deterministic data ID from a list of meal files.

    Args:
        pdf_files: List of MealFile objects whose SHA-256 hashes are combined.

    Returns:
        Hexadecimal SHA-256 digest string serving as the data ID.
    """
    sorted_hashes = sorted(f.sha256 for f in pdf_files)
    combined = "|".join(sorted_hashes)
    return hashlib.sha256(combined.encode()).hexdigest()


def compute_parser_config_hash(parser_config: dict) -> str:
    """Compute a short hash of the parser configuration.

    Args:
        parser_config: Parser configuration dictionary. May contain
            ``algorithm``, ``options``, or a nested key like ``pymupdf4llm``
            that holds algorithm-specific options.

    Returns:
        First 8 characters of the SHA-256 hex digest.
    """
    algorithm = parser_config.get("algorithm", "pymupdf4llm")
    options = parser_config.get(algorithm, {})
    relevant = {"algorithm": algorithm, "options": options}
    return hashlib.sha256(json.dumps(relevant, sort_keys=True).encode()).hexdigest()[:8]


def compute_chunker_config_hash(chunker_config: dict) -> str:
    """Compute a short hash of the chunker configuration.

    The hash includes all parameters that affect chunking results:
    - strategy: chunking strategy (fixed, semantic, etc.)
    - chunk_size: target chunk size
    - overlap: chunk overlap
    - encoding: tokenizer encoding
    - semantic config: similarity_threshold, breakpoint_percentile, min_chunk_size

    Args:
        chunker_config: Chunker configuration dictionary.

    Returns:
        First 8 characters of the SHA-256 hex digest.
    """
    overlap = chunker_config.get(
        "chunk_overlap", chunker_config.get("overlap", 0))
    relevant = {
        "strategy": chunker_config.get("strategy", "fixed"),
        "chunk_size": chunker_config["chunk_size"],
        "overlap": overlap,
        "encoding": chunker_config.get("encoding", "cl100k_base"),
    }

    if chunker_config.get("strategy") == "semantic":
        semantic_config = chunker_config.get("semantic", {})
        relevant["semantic"] = {
            "similarity_threshold": semantic_config.get("similarity_threshold", 0.5),
            "breakpoint_percentile": semantic_config.get("breakpoint_percentile"),
            "min_chunk_size": semantic_config.get("min_chunk_size", 100),
        }

    return hashlib.sha256(json.dumps(relevant, sort_keys=True).encode()).hexdigest()[:8]


def compute_embedding_config_hash(embedding_config: dict) -> str:
    """Compute a short hash of the embedding configuration.

    Args:
        embedding_config: Embedding configuration dictionary containing model_name.

    Returns:
        First 8 characters of the SHA-256 hex digest.
    """
    relevant = {"model_name": embedding_config["model_name"]}
    return hashlib.sha256(json.dumps(relevant, sort_keys=True).encode()).hexdigest()[:8]


def compute_index_key(data_id: str, config_hashes: dict[str, str]) -> str:
    parts = [
        ("d", data_id),
        ("p", config_hashes.get("parser", "")),
        ("c", config_hashes.get("chunker", "")),
        ("e", config_hashes.get("embedding", "")),
    ]
    combined = "|".join(f"{k}:{v}" for k, v in parts)
    return hashlib.sha256(combined.encode()).hexdigest()


def generate_collection_name(index_key: str, prefix: str = "m_") -> str:
    """Generate a Qdrant collection name from an index key.

    Args:
        index_key: Full index key string.
        prefix: Prefix to prepend to the truncated index key.

    Returns:
        Collection name string in the format '{prefix}{first_12_chars_of_index_key}'.
    """
    return f"{prefix}{index_key[:12]}"


def _infer_equivalence_groups(pdf_files: list[str]) -> dict[str, list[str]]:
    """Infer equivalence groups from PDF file paths by stripping common suffixes.

    For each file path, extracts the filename stem (without extension) and
    removes common suffixes such as "摘要", "_摘要", "_英文版_", "_修订版_".
    Files sharing the same resulting group key are placed in one group.

    Args:
        pdf_files: List of relative PDF file paths.

    Returns:
        Dictionary mapping group keys to lists of original file paths.
    """
    suffix_pattern = re.compile(
        r"(摘要|_摘要|_英文版_|_修订版_)$"
    )
    groups: dict[str, list[str]] = {}
    for file_path in pdf_files:
        stem = Path(file_path).stem
        group_key = suffix_pattern.sub("", stem)
        groups.setdefault(group_key, []).append(file_path)
    return groups


def validate_meal_name(name: str) -> bool:
    """Validate that a meal name contains only allowed characters.

    Args:
        name: Proposed meal name string.

    Returns:
        True if the name matches the pattern of alphanumeric characters,
        underscores, and hyphens; False otherwise.
    """
    if not name:
        return False
    pattern = r'^[a-zA-Z0-9_-]+$'
    return bool(re.match(pattern, name))


def generate_timestamp_name() -> str:
    """Generate a meal name based on the current timestamp.

    Returns:
        Meal name string in the format 'meal_YYYYMMDD_HHMMSS'.
    """
    return f"meal_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


def build_chunks_if_needed(
    parsed_dir: Path,
    chunks_dir: Path,
    chunker_config: dict[str, Any],
) -> None:
    """
    Build chunks from parsed files if no chunk files exist.

    Automatically detects whether parsed results are in .pages.json format
    (page-level output) or .md format, and selects the appropriate chunking
    path accordingly.

    Args:
        parsed_dir: Directory containing parsed files (.md or .pages.json).
        chunks_dir: Target directory for chunked files (.jsonl).
        chunker_config: Chunker configuration dictionary.
    """
    if chunks_dir.exists() and any(chunks_dir.rglob("*.jsonl")):
        return

    logger.info("Chunking documents...")

    has_pages_json = parsed_dir.exists() and any(parsed_dir.rglob("*.pages.json"))

    if has_pages_json:
        from src.chunker import process_parsed_files_page_aware

        source_filter = set()
        for pages_file in parsed_dir.rglob("*.pages.json"):
            rel = str(pages_file.relative_to(parsed_dir))
            source_filter.add(rel)

        process_parsed_files_page_aware(
            input_dir=str(parsed_dir),
            output_dir=str(chunks_dir),
            chunk_size=chunker_config.get("chunk_size", 512),
            overlap=chunker_config.get("chunk_overlap", 0),
            source_filter=source_filter,
        )
    else:
        from src.chunker import process_parsed_files

        source_filter_md = set()
        if parsed_dir.exists():
            for md_file in parsed_dir.rglob("*.md"):
                rel = str(md_file.relative_to(parsed_dir))
                source_filter_md.add(rel)

        process_parsed_files(
            input_dir=str(parsed_dir),
            output_dir=str(chunks_dir),
            chunk_size=chunker_config.get("chunk_size", 512),
            overlap=chunker_config.get("chunk_overlap", 0),
            source_filter=source_filter_md,
        )


def build_index_from_chunks(
    chunks_dir: Path,
    embedding_config: dict[str, Any],
    vector_store_config: dict[str, Any],
    collection_name: str,
) -> VectorIndexer:
    """
    Build vector index from chunks directory.

    Args:
        chunks_dir: Directory containing chunked files (.jsonl).
        embedding_config: Embedding configuration dictionary.
        vector_store_config: Vector store configuration dictionary.
        collection_name: Name of the collection to create/use.

    Returns:
        Configured VectorIndexer instance with index built.
    """
    from src.embedder import Embedder
    from src.indexer import VectorIndexer

    source_filter_jsonl = set()
    if chunks_dir.exists():
        for jsonl_file in chunks_dir.rglob("*.jsonl"):
            rel = str(jsonl_file.relative_to(chunks_dir))
            source_filter_jsonl.add(rel)

    embedder = Embedder(
        model_name=embedding_config.get("model_name"),
        device=embedding_config.get("device", "cpu"),
    )

    indexer = VectorIndexer(
        persist_dir=vector_store_config.get(
            "persist_dir", "data/vector_store"),
        collection_name=collection_name,
        distance=vector_store_config.get("distance", "Cosine"),
    )

    indexer.build_index(
        chunks_dir=str(chunks_dir),
        embedder=embedder,
        batch_size=embedding_config.get("batch_size", 32),
        rebuild=True,
        source_filter=source_filter_jsonl,
    )

    return indexer


class ArtifactCache:
    def __init__(self, artifacts_dir: Path):
        """Initialize the ArtifactCache with a base artifacts directory.

        Args:
            artifacts_dir: Root directory for storing cached artifacts.
        """
        self.artifacts_dir = artifacts_dir

    def get_artifact_group_dir(self, data_id: str) -> Path:
        """Get the artifact group directory for a given data ID.

        Args:
            data_id: Data identifier string.

        Returns:
            Path to the artifact group directory using the first 12 chars of data_id.
        """
        short_id = data_id[:12]
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

    def parsed_exists(self, data_id: str, expected_files: list[str], parser_hash: str | None = None) -> bool:
        """Check whether parsed artifacts exist and contain all expected files.

        Args:
            data_id: Data identifier string.
            expected_files: List of expected markdown file names.
            parser_hash: Short hash of the parser configuration.

        Returns:
            True if the parsed directory exists and contains all expected .md files.
        """
        parsed_dir = self.get_parsed_dir(data_id, parser_hash)
        if not parsed_dir.exists():
            return False
        existing = set(p.name for p in parsed_dir.rglob("*.md"))
        return set(expected_files).issubset(existing)

    def chunks_exist(self, data_id: str, chunker_hash: str, expected_files: list[str]) -> bool:
        """Check whether chunked artifacts exist and contain all expected files.

        Args:
            data_id: Data identifier string.
            chunker_hash: Short hash of the chunker configuration.
            expected_files: List of expected JSONL file names.

        Returns:
            True if the chunks directory exists and contains all expected .jsonl files.
        """
        chunks_dir = self.get_chunks_dir(data_id, chunker_hash)
        if not chunks_dir.exists():
            return False
        existing = set(p.name for p in chunks_dir.rglob("*.jsonl"))
        return set(expected_files).issubset(existing)

    def ensure_dirs(self, data_id: str, chunker_hash: str, parser_hash: str | None = None) -> tuple[Path, Path]:
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
        """
        group_dir = self.get_artifact_group_dir(data_id)
        ensure_dir(str(group_dir))
        manifest_path = group_dir / "manifest.json"
        try:
            with open(manifest_path, "w", encoding="utf-8") as f:
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
        try:
            with open(manifest_path, encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load manifest for data_id {data_id}: {str(e)}")
            return None


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
        self.raw_dir = Path(config.get(
            "parser", {}).get("input_dir", "data/raw"))
        self.chunks_dir = Path(config.get(
            "chunker", {}).get("output_dir", "data/chunks"))

        artifacts_config = config.get("artifacts", {})
        artifacts_base = artifacts_config.get("dir", "data/artifacts")
        self.artifacts_dir = Path(artifacts_base)
        self.cache = ArtifactCache(self.artifacts_dir)

    def _build_config_snapshot_and_hashes(self) -> tuple[dict[str, Any], dict[str, str]]:
        parser_config = self.config.get("parser", {})
        chunker_config = self.config.get("chunker", {})
        embedding_config = self.config.get("embedding", {})
        retrieval_config = self.config.get("retrieval", {})

        config_snapshot = {
            "parser": {
                "algorithm": parser_config.get("algorithm", "pymupdf4llm"),
                "input_dir": parser_config.get("input_dir", "data/raw"),
                "options": parser_config.get(parser_config.get("algorithm", "pymupdf4llm"), {}),
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
            "chunker": compute_chunker_config_hash({
                "chunk_size": config_snapshot["chunker"]["chunk_size"],
                "chunk_overlap": config_snapshot["chunker"]["chunk_overlap"],
                "encoding": config_snapshot["chunker"]["encoding"],
            }),
            "embedding": compute_embedding_config_hash(config_snapshot["embedding"]),
        }

        return config_snapshot, config_hashes

    def create_meal(
        self,
        name: str | None,
        sampling_config: SamplingConfig,
        seed: int | None = None,
        force_parse: bool = False,
    ) -> MealConfig:
        """Create a new meal by sampling PDFs, parsing, chunking, and indexing.

        Args:
            name: Desired meal name. If None, a timestamp-based name is generated.
            sampling_config: Configuration controlling how PDFs are sampled.
            seed: Random seed for reproducible sampling. If None, a random seed is used.
            force_parse: If True, re-parse PDFs even if cached parsed artifacts exist.

        Returns:
            MealConfig object for the newly created meal.

        Raises:
            ValueError: If the meal name is invalid, already exists, or no PDFs
                could be processed.
        """

        if name is None:
            name = generate_timestamp_name()

        if not validate_meal_name(name):
            raise ValueError(
                f"Invalid meal name '{name}'. "
                "Only alphanumeric characters, underscores, and hyphens are allowed."
            )

        if self.meal_exists(name):
            raise ValueError(f"Meal '{name}' already exists")

        if seed is None:
            seed = random.randint(0, 2**32 - 1)

        random.seed(seed)

        input_path = self.raw_dir
        all_pdfs = list(input_path.rglob("*.pdf"))
        if not all_pdfs:
            raise ValueError("No PDF files found in input directory")

        sampled_pdfs = determine_sample(all_pdfs, sampling_config)

        meal_files = []
        total_pages = 0
        for pdf_path in sampled_pdfs:
            try:
                rel_path = str(pdf_path.relative_to(input_path))
                sha256 = compute_file_sha256(pdf_path)
                size_bytes = pdf_path.stat().st_size
                pages = count_pdf_pages(pdf_path)
                total_pages += pages
                meal_files.append(MealFile(
                    path=rel_path,
                    sha256=sha256,
                    size_bytes=size_bytes,
                ))
            except Exception as e:
                logger.warning(f"Skipping {pdf_path}: {str(e)}")

        if not meal_files:
            raise ValueError("No PDF files could be processed for the meal")

        data_id = compute_data_id(meal_files)
        config_snapshot, config_hashes = self._build_config_snapshot_and_hashes()
        index_key = compute_index_key(data_id, config_hashes)
        collection_name = generate_collection_name(
            index_key, self.collection_prefix)

        chunker_hash = config_hashes["chunker"]
        parser_hash = config_hashes["parser"]

        parser_config = self.config.get("parser", {})
        chunker_config = self.config.get("chunker", {})
        embedding_config = self.config.get("embedding", {})

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

        parsed_dir, chunks_dir = self.cache.ensure_dirs(data_id, chunker_hash, parser_hash)


        cache_hit_parse = False
        cache_hit_chunk = False

        if not force_parse and self.cache.parsed_exists(data_id, expected_md_names, parser_hash):
            logger.info(
                f"Cache HIT: Parsed artifacts exist for data_id={data_id[:12]}")
            cache_hit_parse = True
        else:
            logger.info(
                f"Step 1: Parsing {len(sampled_pdfs)} PDFs for meal '{name}'...")
            self._parse_pdfs_with_registry(
                parser_config, sampled_pdfs, parsed_dir,
            )

        expected_jsonl_names = []
        for md_name in expected_md_names:
            if md_name.endswith(".pages.json"):
                base = md_name[: -len(".pages.json")]
                expected_jsonl_names.append(base + ".jsonl")
            else:
                expected_jsonl_names.append(Path(md_name).with_suffix(".jsonl").name)

        if self.cache.chunks_exist(data_id, chunker_hash, expected_jsonl_names):
            logger.info(
                f"Cache HIT: Chunked artifacts exist for chunker_hash={chunker_hash}")
            cache_hit_chunk = True
        else:
            logger.info(f"Step 2: Chunking files for meal '{name}'...")
            build_chunks_if_needed(parsed_dir, chunks_dir, chunker_config)

        logger.info(
            f"Step 3: Building vector index for meal '{name}' (collection: {collection_name})...")

        build_index_from_chunks(
            chunks_dir=chunks_dir,
            embedding_config=embedding_config,
            vector_store_config=self.config.get("vector_store", {}),
            collection_name=collection_name,
        )

        source_filter_jsonl = set()
        if chunks_dir.exists():
            for jsonl_file in chunks_dir.rglob("*.jsonl"):
                rel = str(jsonl_file.relative_to(chunks_dir))
                source_filter_jsonl.add(rel)

        total_chunks = 0
        for jsonl_rel in source_filter_jsonl:
            jsonl_path = chunks_dir / jsonl_rel
            try:
                with open(jsonl_path, encoding="utf-8") as f:
                    total_chunks += sum(1 for _ in f)
            except Exception:
                pass

        artifact_manifest = {
            "data_id": data_id,
            "pdf_count": len(meal_files),
            "page_count": total_pages,
            "chunk_count": total_chunks,
            "created_at": datetime.now().isoformat(),
            "config_hashes": config_hashes,
        }
        self.cache.save_manifest(data_id, artifact_manifest)

        equivalence_groups = _infer_equivalence_groups(
            [f.path for f in meal_files]
        )

        meal_config = MealConfig(
            data_id=data_id,
            name=name,
            created_at=datetime.now().isoformat(),
            sampling_config={
                "mode": sampling_config.mode,
                "value": sampling_config.value,
                "seed": seed,
            },
            collection_name=collection_name,
            pdf_files=meal_files,
            config_snapshot=config_snapshot,
            config_hashes=config_hashes,
            stats={
                "total_pdfs": len(meal_files),
                "total_pages": total_pages,
                "total_chunks": total_chunks,
                "cache_hit_parse": cache_hit_parse,
                "cache_hit_chunk": cache_hit_chunk,
            },
            equivalence_groups=equivalence_groups,
        )

        meal_dir = self.get_meal_dir(name)
        ensure_dir(str(meal_dir))
        ensure_dir(str(meal_dir / "test_sets"))

        manifest_path = meal_dir / "manifest.json"
        try:
            with open(manifest_path, "w", encoding="utf-8") as f:
                json.dump(meal_config.to_dict(), f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to write manifest for meal '{name}': {str(e)}")
            raise

        cache_status = []
        if cache_hit_parse:
            cache_status.append("parse")
        if cache_hit_chunk:
            cache_status.append("chunk")
        cache_str = ", ".join(cache_status) if cache_status else "none"

        logger.success(
            f"Meal '{name}' created successfully "
            f"[{data_id[:12]}] ({len(meal_files)} PDFs, {total_pages} pages, {total_chunks} chunks, cache: {cache_str})"
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
            raise FileNotFoundError(
                f"Meal '{name}' not found (manifest missing)")

        try:
            with open(manifest_path, encoding="utf-8") as f:
                data = json.load(f)
            return MealConfig.from_dict(data)
        except Exception as e:
            raise ValueError(f"Failed to load meal '{name}': {str(e)}") from e

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
                        logger.warning(
                            f"Failed to load meal from {item}: {str(e)}")
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
                    "persist_dir", "data/vector_store"),
                collection_name=meal_config.collection_name,
                distance=self.config.get("vector_store", {}).get(
                    "distance", "Cosine"),
            )
            shared = self._is_collection_shared(
                meal_config.collection_name, exclude_name=name)
            if not shared:
                indexer.delete_collection()
                logger.info(
                    f"Deleted Qdrant collection '{meal_config.collection_name}'")
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
            raise ValueError(
                f"Invalid meal name '{new_name}'. "
                "Only alphanumeric characters, underscores, and hyphens are allowed."
            )

        if self.meal_exists(new_name):
            raise ValueError(f"Meal '{new_name}' already exists")

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
            logger.error(f"Failed to write manifest after renaming meal from '{old_name}' to '{new_name}': {str(e)}")
            raise

        logger.success(
            f"Meal renamed from '{old_name}' to '{new_name}' (data_id unchanged: {meal_config.data_id[:12]})")
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
            raise ValueError(
                f"Invalid meal name '{target_name}'. "
                "Only alphanumeric characters, underscores, and hyphens are allowed."
            )

        if self.meal_exists(target_name):
            raise ValueError(f"Meal '{target_name}' already exists")

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
            logger.error(f"Failed to write manifest for copied meal '{target_name}': {str(e)}")
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
            raise ValueError("meal_names cannot be empty")

        if name is None:
            name = generate_timestamp_name()

        if not validate_meal_name(name):
            raise ValueError(
                f"Invalid meal name '{name}'. "
                "Only alphanumeric characters, underscores, and hyphens are allowed."
            )

        if self.meal_exists(name):
            raise ValueError(f"Meal '{name}' already exists")

        source_configs: list[MealConfig] = []
        for meal_name in meal_names:
            if not self.meal_exists(meal_name):
                raise ValueError(f"Meal '{meal_name}' does not exist")
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
            source_info.append({
                "meal": source_config.name,
                "pdf_count": pdf_added,
            })

        if not merged_pdf_files:
            raise ValueError("No PDF files found in source meals")

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

        parser_config = self.config.get("parser", {})
        chunker_config = self.config.get("chunker", {})
        embedding_config = self.config.get("embedding", {})

        algorithm = parser_config.get("algorithm", "pymupdf4llm")
        parser_options = parser_config.get(algorithm, {})
        use_page_chunks = bool(parser_options.get("page_chunks", False))

        parsed_dir, chunks_dir = self.cache.ensure_dirs(new_data_id, chunker_hash, parser_hash)

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
            self._parse_pdfs_with_registry(parser_config, pdfs_to_parse, parsed_dir)
        else:
            logger.info("All PDFs already parsed, reusing cached artifacts")

        all_chunks_exist = True
        for meal_file in merged_pdf_files:
            if use_page_chunks:
                jsonl_name = Path(meal_file.path).with_suffix(".jsonl").name
            else:
                jsonl_name = Path(meal_file.path).with_suffix(".jsonl").name

            if not (chunks_dir / jsonl_name).exists():
                all_chunks_exist = False
                break

        if not all_chunks_exist:
            logger.info("Building chunks for merged meal...")
            build_chunks_if_needed(parsed_dir, chunks_dir, chunker_config)
        else:
            logger.info("All chunks already exist, reusing cached artifacts")

        logger.info(f"Building vector index for merged meal '{name}'...")
        build_index_from_chunks(
            chunks_dir=chunks_dir,
            embedding_config=embedding_config,
            vector_store_config=self.config.get("vector_store", {}),
            collection_name=collection_name,
        )

        source_filter_jsonl = set()
        if chunks_dir.exists():
            for jsonl_file in chunks_dir.rglob("*.jsonl"):
                rel = str(jsonl_file.relative_to(chunks_dir))
                source_filter_jsonl.add(rel)

        total_chunks = 0
        for jsonl_rel in source_filter_jsonl:
            jsonl_path = chunks_dir / jsonl_rel
            try:
                with open(jsonl_path, encoding="utf-8") as f:
                    total_chunks += sum(1 for _ in f)
            except Exception:
                pass

        from src.sampler import count_pdf_pages

        total_pages = 0
        for meal_file in merged_pdf_files:
            pdf_path = self.raw_dir / meal_file.path
            try:
                if pdf_path.exists():
                    total_pages += count_pdf_pages(pdf_path)
            except Exception:
                pass

        artifact_manifest = {
            "data_id": new_data_id,
            "pdf_count": len(merged_pdf_files),
            "page_count": total_pages,
            "chunk_count": total_chunks,
            "created_at": datetime.now().isoformat(),
            "config_hashes": config_hashes,
        }
        self.cache.save_manifest(new_data_id, artifact_manifest)

        equivalence_groups = _infer_equivalence_groups(
            [f.path for f in merged_pdf_files]
        )

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

        meal_config = MealConfig(
            data_id=new_data_id,
            name=name,
            created_at=datetime.now().isoformat(),
            sampling_config=None,
            collection_name=collection_name,
            pdf_files=merged_pdf_files,
            config_snapshot=config_snapshot,
            config_hashes=config_hashes,
            stats={
                "total_pdfs": len(merged_pdf_files),
                "total_pages": total_pages,
                "total_chunks": total_chunks,
            },
            equivalence_groups=equivalence_groups,
            composition=composition,
        )

        meal_dir = self.get_meal_dir(name)
        ensure_dir(str(meal_dir))
        ensure_dir(str(meal_dir / "test_sets"))

        manifest_path = meal_dir / "manifest.json"
        try:
            with open(manifest_path, "w", encoding="utf-8") as f:
                json.dump(meal_config.to_dict(), f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to write manifest for merged meal '{name}': {str(e)}")
            raise

        logger.success(
            f"Meal '{name}' created successfully by merging {len(meal_names)} meals "
            f"[{new_data_id[:12]}] ({len(merged_pdf_files)} unique PDFs, {total_pages} pages, {total_chunks} chunks)"
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
                    new_pdf_files.append(MealFile(
                        path=new_rel_path,
                        sha256=new_sha256,
                        size_bytes=new_size,
                    ))
                    logger.info(
                        f"Replaced: {meal_file.path} -> {new_rel_path}")
                else:
                    logger.warning(
                        f"Replacement file not found: {new_rel_path}, keeping original")
                    new_pdf_files.append(meal_file)
            else:
                file_path = self.raw_dir / meal_file.path
                if file_path.exists():
                    current_sha256 = compute_file_sha256(file_path)
                    if current_sha256 == meal_file.sha256:
                        new_pdf_files.append(meal_file)
                    else:
                        logger.warning(
                            f"File changed but no replacement specified: {meal_file.path}, skipping")
                else:
                    logger.warning(
                        f"File missing and no replacement specified: {meal_file.path}, skipping")

        if not new_pdf_files:
            raise ValueError("No valid PDF files remain after repair")

        new_data_id = compute_data_id(new_pdf_files)
        config_snapshot, config_hashes = self._build_config_snapshot_and_hashes()
        index_key = compute_index_key(new_data_id, config_hashes)
        new_collection_name = generate_collection_name(
            index_key, self.collection_prefix)

        if create_new:
            target_name = new_name or f"{name}_repaired"
            if self.meal_exists(target_name):
                raise ValueError(f"Meal '{target_name}' already exists")
        else:
            target_name = name
            logger.warning(
                f"In-place repair will change the data_id of meal '{name}' "
                f"from {meal_config.data_id[:12]} to {new_data_id[:12]}"
            )

        parser_config = self.config.get("parser", {})
        chunker_config = self.config.get("chunker", {})
        embedding_config = self.config.get("embedding", {})

        chunker_hash = config_hashes["chunker"]
        parser_hash = config_hashes["parser"]
        parsed_dir, chunks_dir = self.cache.ensure_dirs(
            new_data_id, chunker_hash, parser_hash)

        sampled_pdfs = [self.raw_dir / f.path for f in new_pdf_files]

        logger.info(f"Rebuilding index for repaired meal '{target_name}'...")
        self._parse_pdfs_with_registry(
            parser_config, sampled_pdfs, parsed_dir,
        )

        build_chunks_if_needed(parsed_dir, chunks_dir, chunker_config)

        build_index_from_chunks(
            chunks_dir=chunks_dir,
            embedding_config=embedding_config,
            vector_store_config=self.config.get("vector_store", {}),
            collection_name=new_collection_name,
        )

        source_filter_jsonl = set()
        if chunks_dir.exists():
            for jsonl_file in chunks_dir.rglob("*.jsonl"):
                rel = str(jsonl_file.relative_to(chunks_dir))
                source_filter_jsonl.add(rel)

        total_pages = 0
        total_chunks = 0
        for mf in new_pdf_files:
            with contextlib.suppress(Exception):
                total_pages += count_pdf_pages(self.raw_dir / mf.path)
        for jsonl_rel in source_filter_jsonl:
            jsonl_path = chunks_dir / jsonl_rel
            try:
                with open(jsonl_path, encoding="utf-8") as f:
                    total_chunks += sum(1 for _ in f)
            except Exception:
                pass

        artifact_manifest = {
            "data_id": new_data_id,
            "pdf_count": len(new_pdf_files),
            "page_count": total_pages,
            "chunk_count": total_chunks,
            "created_at": datetime.now().isoformat(),
            "config_hashes": config_hashes,
        }
        self.cache.save_manifest(new_data_id, artifact_manifest)

        new_equivalence_groups = _infer_equivalence_groups(
            [f.path for f in new_pdf_files]
        )

        new_config = MealConfig(
            data_id=new_data_id,
            name=target_name,
            created_at=datetime.now().isoformat(),
            sampling_config=meal_config.sampling_config,
            collection_name=new_collection_name,
            pdf_files=new_pdf_files,
            config_snapshot=config_snapshot,
            config_hashes=config_hashes,
            stats={
                "total_pdfs": len(new_pdf_files),
                "total_pages": total_pages,
                "total_chunks": total_chunks,
            },
            equivalence_groups=new_equivalence_groups,
        )

        if create_new:
            meal_dir = self.get_meal_dir(target_name)
            ensure_dir(str(meal_dir))
            ensure_dir(str(meal_dir / "test_sets"))
        else:
            try:
                from src.indexer import VectorIndexer
                old_indexer = VectorIndexer(
                    persist_dir=self.config.get("vector_store", {}).get(
                        "persist_dir", "data/vector_store"),
                    collection_name=meal_config.collection_name,
                    distance=self.config.get("vector_store", {}).get(
                        "distance", "Cosine"),
                )
                shared = self._is_collection_shared(
                    meal_config.collection_name, exclude_name=name)
                if not shared:
                    old_indexer.delete_collection()
            except Exception as e:
                logger.warning(f"Failed to delete old collection: {str(e)}")
            meal_dir = self.get_meal_dir(target_name)

        manifest_path = meal_dir / "manifest.json"
        try:
            with open(manifest_path, "w", encoding="utf-8") as f:
                json.dump(new_config.to_dict(), f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to write manifest for repaired meal '{target_name}': {str(e)}")
            raise

        logger.success(
            f"Meal '{target_name}' repaired successfully "
            f"[{new_data_id[:12]}] ({len(new_pdf_files)} PDFs, {total_pages} pages, {total_chunks} chunks)"
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

    def _is_collection_shared(self, collection_name: str, exclude_name: str | None = None) -> bool:
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
            raise ValueError(f"Source meal '{source_meal}' does not exist")

        if name is None:
            name = generate_timestamp_name()

        if not validate_meal_name(name):
            raise ValueError(
                f"Invalid meal name '{name}'. "
                "Only alphanumeric characters, underscores, and hyphens are allowed."
            )

        if self.meal_exists(name):
            raise ValueError(f"Meal '{name}' already exists")

        source_config = self.load_meal(source_meal)

        existing_paths = {f.path for f in source_config.pdf_files}

        valid_new_pdfs: list[tuple[Path, str, int]] = []
        skipped_files: list[str] = []

        for pdf_input in new_pdfs:
            if isinstance(pdf_input, Path):
                pdf_path = pdf_input
            else:
                pdf_path = Path(pdf_input)

            if not pdf_path.is_absolute():
                pdf_path = self.raw_dir / pdf_path

            if not pdf_path.exists():
                raise ValueError(f"PDF file does not exist: {pdf_input}")

            try:
                rel_path_obj = pdf_path.relative_to(self.raw_dir)
                rel_path = rel_path_obj.as_posix()
            except ValueError as e:
                raise ValueError(
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
            raise ValueError(
                "No new PDF files to add (all files either don't exist or are already in the source meal)"
            )

        added_files = [rel_path for _, rel_path, _ in valid_new_pdfs]

        all_meal_files = list(source_config.pdf_files)
        for pdf_path, rel_path, size_bytes in valid_new_pdfs:
            sha256 = compute_file_sha256(pdf_path)
            all_meal_files.append(MealFile(
                path=rel_path,
                sha256=sha256,
                size_bytes=size_bytes,
            ))

        new_data_id = compute_data_id(all_meal_files)
        config_snapshot, config_hashes = self._build_config_snapshot_and_hashes()
        index_key = compute_index_key(new_data_id, config_hashes)
        collection_name = generate_collection_name(index_key, self.collection_prefix)

        chunker_hash = config_hashes["chunker"]
        parser_hash = config_hashes["parser"]

        parser_config = self.config.get("parser", {})
        chunker_config = self.config.get("chunker", {})
        embedding_config = self.config.get("embedding", {})

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

        if source_parsed_dir.exists():
            for parsed_file in source_parsed_dir.rglob("*"):
                if parsed_file.is_file():
                    rel_parsed = parsed_file.relative_to(source_parsed_dir)
                    target_file = new_parsed_dir / rel_parsed
                    target_file.parent.mkdir(parents=True, exist_ok=True)
                    try:
                        shutil.copy2(parsed_file, target_file)
                    except Exception as e:
                        logger.warning(
                            f"Failed to copy parsed file {parsed_file}: {str(e)}"
                        )

        if source_chunks_dir.exists():
            for chunk_file in source_chunks_dir.rglob("*"):
                if chunk_file.is_file():
                    rel_chunk = chunk_file.relative_to(source_chunks_dir)
                    target_file = new_chunks_dir / rel_chunk
                    target_file.parent.mkdir(parents=True, exist_ok=True)
                    try:
                        shutil.copy2(chunk_file, target_file)
                    except Exception as e:
                        logger.warning(
                            f"Failed to copy chunk file {chunk_file}: {str(e)}"
                        )

        logger.info(
            f"Step 1: Parsing {len(valid_new_pdfs)} new PDFs for extended meal '{name}'..."
        )
        new_pdf_paths = [pdf_path for pdf_path, _, _ in valid_new_pdfs]
        self._parse_pdfs_with_registry(parser_config, new_pdf_paths, new_parsed_dir)

        logger.info(f"Step 2: Chunking new files for extended meal '{name}'...")
        build_chunks_if_needed(new_parsed_dir, new_chunks_dir, chunker_config)

        logger.info(
            f"Step 3: Building vector index for extended meal '{name}' "
            f"(collection: {collection_name})..."
        )
        build_index_from_chunks(
            chunks_dir=new_chunks_dir,
            embedding_config=embedding_config,
            vector_store_config=self.config.get("vector_store", {}),
            collection_name=collection_name,
        )

        total_pages = 0
        total_chunks = 0

        for meal_file in all_meal_files:
            try:
                pdf_path = self.raw_dir / meal_file.path
                total_pages += count_pdf_pages(pdf_path)
            except Exception:
                pass

        for jsonl_file in new_chunks_dir.rglob("*.jsonl"):
            try:
                with open(jsonl_file, encoding="utf-8") as f:
                    total_chunks += sum(1 for _ in f)
            except Exception:
                pass

        artifact_manifest = {
            "data_id": new_data_id,
            "pdf_count": len(all_meal_files),
            "page_count": total_pages,
            "chunk_count": total_chunks,
            "created_at": datetime.now().isoformat(),
            "config_hashes": config_hashes,
        }
        self.cache.save_manifest(new_data_id, artifact_manifest)

        equivalence_groups = _infer_equivalence_groups(
            [f.path for f in all_meal_files]
        )

        composition = {
            "type": "extended",
            "base_meal": source_meal,
            "added_files": added_files,
            "created_at": datetime.now().isoformat(),
        }
        if skipped_files:
            composition["skipped_files"] = skipped_files

        meal_config = MealConfig(
            data_id=new_data_id,
            name=name,
            created_at=datetime.now().isoformat(),
            sampling_config=source_config.sampling_config,
            collection_name=collection_name,
            pdf_files=all_meal_files,
            config_snapshot=config_snapshot,
            config_hashes=config_hashes,
            stats={
                "total_pdfs": len(all_meal_files),
                "total_pages": total_pages,
                "total_chunks": total_chunks,
            },
            equivalence_groups=equivalence_groups,
            composition=composition,
        )

        meal_dir = self.get_meal_dir(name)
        ensure_dir(str(meal_dir))
        ensure_dir(str(meal_dir / "test_sets"))

        manifest_path = meal_dir / "manifest.json"
        try:
            with open(manifest_path, "w", encoding="utf-8") as f:
                json.dump(meal_config.to_dict(), f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(
                f"Failed to write manifest for extended meal '{name}': {str(e)}"
            )
            raise

        logger.success(
            f"Meal '{name}' created successfully by extending '{source_meal}' "
            f"[{new_data_id[:12]}] ({len(all_meal_files)} PDFs, {total_pages} pages, {total_chunks} chunks, "
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
                    import json
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
