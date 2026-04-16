import hashlib
import json
import random
import re
import shutil
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

from src.sampler import SamplingConfig, count_pdf_pages, determine_sample
from src.utils import ensure_dir


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
    sampling_config: Optional[Dict[str, Any]]
    collection_name: str
    pdf_files: List[MealFile]
    config_snapshot: Optional[Dict[str, Any]] = None
    config_hashes: Optional[Dict[str, str]] = None
    stats: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MealConfig":
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
        )


def compute_file_sha256(file_path: Path, chunk_size: int = 8192) -> str:
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            sha256.update(chunk)
    return sha256.hexdigest()


def compute_data_id(pdf_files: List[MealFile]) -> str:
    sorted_hashes = sorted(f.sha256 for f in pdf_files)
    combined = "|".join(sorted_hashes)
    return hashlib.sha256(combined.encode()).hexdigest()


def compute_parser_config_hash(parser_config: Dict) -> str:
    relevant = {"algorithm": parser_config.get("algorithm", "pymupdf4llm")}
    return hashlib.sha256(json.dumps(relevant, sort_keys=True).encode()).hexdigest()[:8]


def compute_chunker_config_hash(chunker_config: Dict) -> str:
    overlap = chunker_config.get("chunk_overlap", chunker_config.get("overlap", 0))
    relevant = {
        "chunk_size": chunker_config["chunk_size"],
        "overlap": overlap,
        "encoding": chunker_config.get("encoding", "cl100k_base"),
    }
    return hashlib.sha256(json.dumps(relevant, sort_keys=True).encode()).hexdigest()[:8]


def compute_embedding_config_hash(embedding_config: Dict) -> str:
    relevant = {"model_name": embedding_config["model_name"]}
    return hashlib.sha256(json.dumps(relevant, sort_keys=True).encode()).hexdigest()[:8]


def compute_index_key(data_id: str, config_hashes: Dict[str, str]) -> str:
    parts = [
        ("d", data_id),
        ("p", config_hashes.get("parser", "")),
        ("c", config_hashes.get("chunker", "")),
        ("e", config_hashes.get("embedding", "")),
    ]
    combined = "|".join(f"{k}:{v}" for k, v in parts)
    return hashlib.sha256(combined.encode()).hexdigest()


def generate_collection_name(index_key: str, prefix: str = "m_") -> str:
    return f"{prefix}{index_key[:12]}"


def validate_meal_name(name: str) -> bool:
    if not name:
        return False
    pattern = r'^[a-zA-Z0-9_-]+$'
    return bool(re.match(pattern, name))


def generate_timestamp_name() -> str:
    return f"meal_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


class ArtifactCache:
    def __init__(self, artifacts_dir: Path):
        self.artifacts_dir = artifacts_dir

    def get_artifact_group_dir(self, data_id: str) -> Path:
        short_id = data_id[:12]
        return self.artifacts_dir / short_id

    def get_parsed_dir(self, data_id: str) -> Path:
        group_dir = self.get_artifact_group_dir(data_id)
        return group_dir / "parsed"

    def get_chunks_dir(self, data_id: str, chunker_hash: str) -> Path:
        group_dir = self.get_artifact_group_dir(data_id)
        return group_dir / f"chunks_{chunker_hash}"

    def parsed_exists(self, data_id: str, expected_files: List[str]) -> bool:
        parsed_dir = self.get_parsed_dir(data_id)
        if not parsed_dir.exists():
            return False
        existing = set(p.name for p in parsed_dir.rglob("*.md"))
        return set(expected_files).issubset(existing)

    def chunks_exist(self, data_id: str, chunker_hash: str, expected_files: List[str]) -> bool:
        chunks_dir = self.get_chunks_dir(data_id, chunker_hash)
        if not chunks_dir.exists():
            return False
        existing = set(p.name for p in chunks_dir.rglob("*.jsonl"))
        return set(expected_files).issubset(existing)

    def ensure_dirs(self, data_id: str, chunker_hash: str) -> Tuple[Path, Path]:
        group_dir = self.get_artifact_group_dir(data_id)
        ensure_dir(str(group_dir))
        parsed_dir = self.get_parsed_dir(data_id)
        ensure_dir(str(parsed_dir))
        chunks_dir = self.get_chunks_dir(data_id, chunker_hash)
        ensure_dir(str(chunks_dir))
        return parsed_dir, chunks_dir

    def save_manifest(self, data_id: str, manifest: Dict[str, Any]) -> None:
        group_dir = self.get_artifact_group_dir(data_id)
        ensure_dir(str(group_dir))
        manifest_path = group_dir / "manifest.json"
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)

    def load_manifest(self, data_id: str) -> Optional[Dict[str, Any]]:
        group_dir = self.get_artifact_group_dir(data_id)
        manifest_path = group_dir / "manifest.json"
        if not manifest_path.exists():
            return None
        with open(manifest_path, "r", encoding="utf-8") as f:
            return json.load(f)


class MealManager:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        meals_config = config.get("meals", {})
        self.meals_dir = Path(meals_config.get("dir", "data/meals"))
        self.collection_prefix = meals_config.get("collection_prefix", "m_")
        self.raw_dir = Path(config.get("parser", {}).get("input_dir", "data/raw"))
        self.chunks_dir = Path(config.get("chunker", {}).get("output_dir", "data/chunks"))

        artifacts_config = config.get("artifacts", {})
        artifacts_base = artifacts_config.get("dir", "data/artifacts")
        self.artifacts_dir = Path(artifacts_base)
        self.cache = ArtifactCache(self.artifacts_dir)

    def _build_config_snapshot_and_hashes(self) -> Tuple[Dict[str, Any], Dict[str, str]]:
        parser_config = self.config.get("parser", {})
        chunker_config = self.config.get("chunker", {})
        embedding_config = self.config.get("embedding", {})
        retrieval_config = self.config.get("retrieval", {})

        config_snapshot = {
            "parser": {
                "algorithm": parser_config.get("algorithm", "pymupdf4llm"),
                "input_dir": parser_config.get("input_dir", "data/raw"),
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
        name: Optional[str],
        sampling_config: SamplingConfig,
        seed: Optional[int] = None,
        force_parse: bool = False,
    ) -> MealConfig:

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
        collection_name = generate_collection_name(index_key, self.collection_prefix)

        chunker_hash = config_hashes["chunker"]
        expected_md_names = [
            Path(f.path).with_suffix(".md").name for f in meal_files
        ]

        parsed_dir, chunks_dir = self.cache.ensure_dirs(data_id, chunker_hash)

        from src.parser import parse_all_pdfs
        from src.chunker import process_parsed_files
        from src.embedder import Embedder
        from src.indexer import VectorIndexer

        parser_config = self.config.get("parser", {})
        chunker_config = self.config.get("chunker", {})
        embedding_config = self.config.get("embedding", {})

        cache_hit_parse = False
        cache_hit_chunk = False

        if not force_parse and self.cache.parsed_exists(data_id, expected_md_names):
            logger.info(f"Cache HIT: Parsed artifacts exist for data_id={data_id[:12]}")
            cache_hit_parse = True
        else:
            logger.info(f"Step 1: Parsing {len(sampled_pdfs)} PDFs for meal '{name}'...")
            parse_results = parse_all_pdfs(
                input_dir=parser_config["input_dir"],
                output_dir=str(parsed_dir),
                force=True,
                pdf_files=sampled_pdfs,
            )

        source_filter_md = set()
        md_files_in_cache = list(parsed_dir.rglob("*.md"))
        for md_file in md_files_in_cache:
            rel = str(md_file.relative_to(parsed_dir))
            source_filter_md.add(rel)

        expected_jsonl_names = [
            Path(md_name).with_suffix(".jsonl").name for md_name in expected_md_names
        ]

        if self.cache.chunks_exist(data_id, chunker_hash, expected_jsonl_names):
            logger.info(f"Cache HIT: Chunked artifacts exist for chunker_hash={chunker_hash}")
            cache_hit_chunk = True
        else:
            logger.info(f"Step 2: Chunking {len(source_filter_md)} files for meal '{name}'...")
            chunk_results = process_parsed_files(
                input_dir=str(parsed_dir),
                output_dir=str(chunks_dir),
                chunk_size=chunker_config["chunk_size"],
                overlap=chunker_config["chunk_overlap"],
                source_filter=source_filter_md,
            )

        source_filter_jsonl = set()
        jsonl_files_in_cache = list(chunks_dir.rglob("*.jsonl"))
        for jsonl_file in jsonl_files_in_cache:
            rel = str(jsonl_file.relative_to(chunks_dir))
            source_filter_jsonl.add(rel)

        logger.info(f"Step 3: Building vector index for meal '{name}' (collection: {collection_name})...")

        embedder = Embedder(
            model_name=embedding_config["model_name"],
            device=embedding_config["device"],
        )
        indexer = VectorIndexer(
            persist_dir=self.config.get("vector_store", {}).get("persist_dir", "data/vector_store"),
            collection_name=collection_name,
            distance=self.config.get("vector_store", {}).get("distance", "Cosine"),
        )
        indexer.build_index(
            chunks_dir=str(chunks_dir),
            embedder=embedder,
            batch_size=embedding_config["batch_size"],
            rebuild=True,
            source_filter=source_filter_jsonl,
        )

        total_chunks = len(source_filter_jsonl)
        for jsonl_rel in source_filter_jsonl:
            jsonl_path = chunks_dir / jsonl_rel
            try:
                with open(jsonl_path, "r", encoding="utf-8") as f:
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
        )

        meal_dir = self.get_meal_dir(name)
        ensure_dir(str(meal_dir))
        ensure_dir(str(meal_dir / "test_sets"))

        manifest_path = meal_dir / "manifest.json"
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(meal_config.to_dict(), f, ensure_ascii=False, indent=2)

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
        meal_dir = self.get_meal_dir(name)
        manifest_path = meal_dir / "manifest.json"

        if not manifest_path.exists():
            raise FileNotFoundError(f"Meal '{name}' not found (manifest missing)")

        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return MealConfig.from_dict(data)
        except Exception as e:
            raise ValueError(f"Failed to load meal '{name}': {str(e)}")

    def find_equivalent_meals(self, data_id: str) -> List[MealConfig]:
        equivalents = []
        for meal in self.list_meals():
            if meal.data_id == data_id:
                equivalents.append(meal)
        return equivalents

    def list_meals(self) -> List[MealConfig]:
        if not self.meals_dir.exists():
            return []

        meals = []
        for item in sorted(self.meals_dir.iterdir()):
            if item.is_dir():
                manifest_path = item / "manifest.json"
                if manifest_path.exists():
                    try:
                        with open(manifest_path, "r", encoding="utf-8") as f:
                            data = json.load(f)
                        meals.append(MealConfig.from_dict(data))
                    except Exception as e:
                        logger.warning(f"Failed to load meal from {item}: {str(e)}")
        return meals

    def delete_meal(self, name: str) -> None:
        meal_config = self.load_meal(name)
        meal_dir = self.get_meal_dir(name)

        from src.indexer import VectorIndexer

        try:
            indexer = VectorIndexer(
                persist_dir=self.config.get("vector_store", {}).get("persist_dir", "data/vector_store"),
                collection_name=meal_config.collection_name,
                distance=self.config.get("vector_store", {}).get("distance", "Cosine"),
            )
            shared = self._is_collection_shared(meal_config.collection_name, exclude_name=name)
            if not shared:
                indexer.delete_collection()
                logger.info(f"Deleted Qdrant collection '{meal_config.collection_name}'")
            else:
                logger.info(
                    f"Collection '{meal_config.collection_name}' is shared with other meals, skipping deletion"
                )
        except Exception as e:
            logger.warning(f"Failed to delete Qdrant collection: {str(e)}")

        shutil.rmtree(meal_dir)
        logger.success(f"Meal '{name}' deleted successfully")

    def rename_meal(self, old_name: str, new_name: str) -> MealConfig:
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
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(meal_config.to_dict(), f, ensure_ascii=False, indent=2)

        logger.success(f"Meal renamed from '{old_name}' to '{new_name}' (data_id unchanged: {meal_config.data_id[:12]})")
        return meal_config

    def copy_meal(self, source_name: str, target_name: str) -> MealConfig:
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
        )

        manifest_path = target_dir / "manifest.json"
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(new_config.to_dict(), f, ensure_ascii=False, indent=2)

        logger.success(
            f"Meal copied from '{source_name}' to '{target_name}' "
            f"(same data_id: {source_config.data_id[:12]}, shared collection: {source_config.collection_name})"
        )
        return new_config

    def check_meal_status(self, name: str) -> Tuple[MealStatus, List[str]]:
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
        replacements: Optional[Dict[str, str]] = None,
        create_new: bool = False,
        new_name: Optional[str] = None,
    ) -> MealConfig:
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
                    logger.info(f"Replaced: {meal_file.path} -> {new_rel_path}")
                else:
                    logger.warning(f"Replacement file not found: {new_rel_path}, keeping original")
                    new_pdf_files.append(meal_file)
            else:
                file_path = self.raw_dir / meal_file.path
                if file_path.exists():
                    current_sha256 = compute_file_sha256(file_path)
                    if current_sha256 == meal_file.sha256:
                        new_pdf_files.append(meal_file)
                    else:
                        logger.warning(f"File changed but no replacement specified: {meal_file.path}, skipping")
                else:
                    logger.warning(f"File missing and no replacement specified: {meal_file.path}, skipping")

        if not new_pdf_files:
            raise ValueError("No valid PDF files remain after repair")

        new_data_id = compute_data_id(new_pdf_files)
        config_snapshot, config_hashes = self._build_config_snapshot_and_hashes()
        index_key = compute_index_key(new_data_id, config_hashes)
        new_collection_name = generate_collection_name(index_key, self.collection_prefix)

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

        from src.parser import parse_all_pdfs
        from src.chunker import process_parsed_files
        from src.embedder import Embedder
        from src.indexer import VectorIndexer

        parser_config = self.config.get("parser", {})
        chunker_config = self.config.get("chunker", {})
        embedding_config = self.config.get("embedding", {})

        chunker_hash = config_hashes["chunker"]
        parsed_dir, chunks_dir = self.cache.ensure_dirs(new_data_id, chunker_hash)

        sampled_pdfs = [self.raw_dir / f.path for f in new_pdf_files]

        logger.info(f"Rebuilding index for repaired meal '{target_name}'...")
        parse_results = parse_all_pdfs(
            input_dir=parser_config["input_dir"],
            output_dir=str(parsed_dir),
            force=True,
            pdf_files=sampled_pdfs,
        )

        source_filter_md = set()
        md_files_in_cache = list(parsed_dir.rglob("*.md"))
        for md_file in md_files_in_cache:
            rel = str(md_file.relative_to(parsed_dir))
            source_filter_md.add(rel)

        chunk_results = process_parsed_files(
            input_dir=str(parsed_dir),
            output_dir=str(chunks_dir),
            chunk_size=chunker_config["chunk_size"],
            overlap=chunker_config["chunk_overlap"],
            source_filter=source_filter_md,
        )

        source_filter_jsonl = set()
        jsonl_files_in_cache = list(chunks_dir.rglob("*.jsonl"))
        for jsonl_file in jsonl_files_in_cache:
            rel = str(jsonl_file.relative_to(chunks_dir))
            source_filter_jsonl.add(rel)

        embedder = Embedder(
            model_name=embedding_config["model_name"],
            device=embedding_config["device"],
        )
        indexer = VectorIndexer(
            persist_dir=self.config.get("vector_store", {}).get("persist_dir", "data/vector_store"),
            collection_name=new_collection_name,
            distance=self.config.get("vector_store", {}).get("distance", "Cosine"),
        )
        indexer.build_index(
            chunks_dir=str(chunks_dir),
            embedder=embedder,
            batch_size=embedding_config["batch_size"],
            rebuild=True,
            source_filter=source_filter_jsonl,
        )

        total_pages = 0
        total_chunks = 0
        for mf in new_pdf_files:
            try:
                total_pages += count_pdf_pages(self.raw_dir / mf.path)
            except Exception:
                pass
        for jsonl_rel in source_filter_jsonl:
            jsonl_path = chunks_dir / jsonl_rel
            try:
                with open(jsonl_path, "r", encoding="utf-8") as f:
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
        )

        if create_new:
            meal_dir = self.get_meal_dir(target_name)
            ensure_dir(str(meal_dir))
            ensure_dir(str(meal_dir / "test_sets"))
        else:
            try:
                old_indexer = VectorIndexer(
                    persist_dir=self.config.get("vector_store", {}).get("persist_dir", "data/vector_store"),
                    collection_name=meal_config.collection_name,
                    distance=self.config.get("vector_store", {}).get("distance", "Cosine"),
                )
                shared = self._is_collection_shared(meal_config.collection_name, exclude_name=name)
                if not shared:
                    old_indexer.delete_collection()
            except Exception as e:
                logger.warning(f"Failed to delete old collection: {str(e)}")
            meal_dir = self.get_meal_dir(target_name)

        manifest_path = meal_dir / "manifest.json"
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(new_config.to_dict(), f, ensure_ascii=False, indent=2)

        logger.success(
            f"Meal '{target_name}' repaired successfully "
            f"[{new_data_id[:12]}] ({len(new_pdf_files)} PDFs, {total_pages} pages, {total_chunks} chunks)"
        )
        return new_config

    def meal_exists(self, name: str) -> bool:
        meal_dir = self.get_meal_dir(name)
        return meal_dir.exists() and (meal_dir / "manifest.json").exists()

    def get_meal_dir(self, name: str) -> Path:
        return self.meals_dir / name

    def _is_collection_shared(self, collection_name: str, exclude_name: Optional[str] = None) -> bool:
        for meal in self.list_meals():
            if meal.name == exclude_name:
                continue
            if meal.collection_name == collection_name:
                return True
        return False
