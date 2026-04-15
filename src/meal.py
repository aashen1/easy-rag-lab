import hashlib
import json
import random
import re
import shutil
import uuid
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
    uuid: str
    name: str
    created_at: str
    sampling_config: Optional[Dict[str, Any]]
    collection_name: str
    pdf_files: List[MealFile]
    stats: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MealConfig":
        pdf_files = [MealFile(**f) for f in data.get("pdf_files", [])]
        return cls(
            uuid=data["uuid"],
            name=data["name"],
            created_at=data["created_at"],
            sampling_config=data.get("sampling_config"),
            collection_name=data["collection_name"],
            pdf_files=pdf_files,
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


def validate_meal_name(name: str) -> bool:
    if not name:
        return False
    pattern = r'^[a-zA-Z0-9_-]+$'
    return bool(re.match(pattern, name))


def generate_timestamp_name() -> str:
    return f"meal_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


def generate_collection_name(meal_uuid: str, prefix: str = "m_") -> str:
    return f"{prefix}{meal_uuid[:8]}"


class MealManager:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        meals_config = config.get("meals", {})
        self.meals_dir = Path(meals_config.get("dir", "data/meals"))
        self.collection_prefix = meals_config.get("collection_prefix", "m_")
        self.raw_dir = Path(config.get("parser", {}).get("input_dir", "data/raw"))
        self.chunks_dir = Path(config.get("chunker", {}).get("output_dir", "data/chunks"))

    def create_meal(
        self,
        name: Optional[str],
        sampling_config: SamplingConfig,
        seed: Optional[int] = None,
        force_parse: bool = False,
    ) -> MealConfig:
        meal_uuid = str(uuid.uuid4())

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

        collection_name = generate_collection_name(meal_uuid, self.collection_prefix)

        from src.parser import parse_all_pdfs
        from src.chunker import process_parsed_files
        from src.embedder import Embedder
        from src.indexer import VectorIndexer

        parser_config = self.config.get("parser", {})
        chunker_config = self.config.get("chunker", {})
        embedding_config = self.config.get("embedding", {})

        logger.info(f"Step 1: Parsing {len(sampled_pdfs)} PDFs for meal '{name}'...")
        parse_results = parse_all_pdfs(
            input_dir=parser_config["input_dir"],
            output_dir=parser_config["output_dir"],
            force=force_parse,
            pdf_files=sampled_pdfs,
        )

        source_filter_md = set()
        for r in parse_results:
            if r.get("output"):
                output_path = Path(r["output"])
                parsed_dir = Path(parser_config["output_dir"])
                source_filter_md.add(str(output_path.relative_to(parsed_dir)))

        logger.info(f"Step 2: Chunking {len(source_filter_md)} files for meal '{name}'...")
        chunk_results = process_parsed_files(
            input_dir=chunker_config["input_dir"],
            output_dir=chunker_config["output_dir"],
            chunk_size=chunker_config["chunk_size"],
            overlap=chunker_config["chunk_overlap"],
            source_filter=source_filter_md,
        )

        source_filter_jsonl = set()
        for r in chunk_results:
            if r.get("output"):
                output_path = Path(r["output"])
                chunks_dir = Path(chunker_config["output_dir"])
                source_filter_jsonl.add(str(output_path.relative_to(chunks_dir)))

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
            chunks_dir=chunker_config["output_dir"],
            embedder=embedder,
            batch_size=embedding_config["batch_size"],
            rebuild=True,
            source_filter=source_filter_jsonl,
        )

        total_chunks = 0
        for jsonl_rel in source_filter_jsonl:
            jsonl_path = self.chunks_dir / jsonl_rel
            try:
                with open(jsonl_path, "r", encoding="utf-8") as f:
                    total_chunks += sum(1 for _ in f)
            except Exception:
                pass

        meal_config = MealConfig(
            uuid=meal_uuid,
            name=name,
            created_at=datetime.now().isoformat(),
            sampling_config={
                "mode": sampling_config.mode,
                "value": sampling_config.value,
                "seed": seed,
            },
            collection_name=collection_name,
            pdf_files=meal_files,
            stats={
                "total_pdfs": len(meal_files),
                "total_pages": total_pages,
                "total_chunks": total_chunks,
            },
        )

        meal_dir = self.get_meal_dir(name)
        ensure_dir(str(meal_dir))
        ensure_dir(str(meal_dir / "test_sets"))

        manifest_path = meal_dir / "manifest.json"
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(meal_config.to_dict(), f, ensure_ascii=False, indent=2)

        logger.success(
            f"Meal '{name}' created successfully "
            f"[{meal_uuid[:8]}] ({len(meal_files)} PDFs, {total_pages} pages, {total_chunks} chunks)"
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

    def load_meal_by_uuid(self, meal_uuid: str) -> Optional[MealConfig]:
        for meal in self.list_meals():
            if meal.uuid == meal_uuid:
                return meal
        return None

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

        logger.success(f"Meal renamed from '{old_name}' to '{new_name}' (UUID unchanged: {meal_config.uuid[:8]})")
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

        new_uuid = str(uuid.uuid4())
        new_collection_name = generate_collection_name(new_uuid, self.collection_prefix)

        shutil.copytree(source_dir, target_dir)

        new_config = MealConfig(
            uuid=new_uuid,
            name=target_name,
            created_at=source_config.created_at,
            sampling_config=source_config.sampling_config,
            collection_name=source_config.collection_name,
            pdf_files=source_config.pdf_files,
            stats=source_config.stats,
        )

        manifest_path = target_dir / "manifest.json"
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(new_config.to_dict(), f, ensure_ascii=False, indent=2)

        logger.success(
            f"Meal copied from '{source_name}' to '{target_name}' "
            f"(shallow copy, shared collection: {source_config.collection_name})"
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

        new_uuid = str(uuid.uuid4())
        new_collection_name = generate_collection_name(new_uuid, self.collection_prefix)

        if create_new:
            target_name = new_name or f"{name}_repaired"
            if self.meal_exists(target_name):
                raise ValueError(f"Meal '{target_name}' already exists")
        else:
            target_name = name
            logger.warning(
                f"In-place repair will change the UUID of meal '{name}' "
                f"from {meal_config.uuid[:8]} to {new_uuid[:8]}"
            )

        from src.parser import parse_all_pdfs
        from src.chunker import process_parsed_files
        from src.embedder import Embedder
        from src.indexer import VectorIndexer

        parser_config = self.config.get("parser", {})
        chunker_config = self.config.get("chunker", {})
        embedding_config = self.config.get("embedding", {})

        sampled_pdfs = [self.raw_dir / f.path for f in new_pdf_files]

        logger.info(f"Rebuilding index for repaired meal '{target_name}'...")
        parse_results = parse_all_pdfs(
            input_dir=parser_config["input_dir"],
            output_dir=parser_config["output_dir"],
            force=False,
            pdf_files=sampled_pdfs,
        )

        source_filter_md = set()
        for r in parse_results:
            if r.get("output"):
                output_path = Path(r["output"])
                parsed_dir = Path(parser_config["output_dir"])
                source_filter_md.add(str(output_path.relative_to(parsed_dir)))

        chunk_results = process_parsed_files(
            input_dir=chunker_config["input_dir"],
            output_dir=chunker_config["output_dir"],
            chunk_size=chunker_config["chunk_size"],
            overlap=chunker_config["chunk_overlap"],
            source_filter=source_filter_md,
        )

        source_filter_jsonl = set()
        for r in chunk_results:
            if r.get("output"):
                output_path = Path(r["output"])
                chunks_dir = Path(chunker_config["output_dir"])
                source_filter_jsonl.add(str(output_path.relative_to(chunks_dir)))

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
            chunks_dir=chunker_config["output_dir"],
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
            jsonl_path = self.chunks_dir / jsonl_rel
            try:
                with open(jsonl_path, "r", encoding="utf-8") as f:
                    total_chunks += sum(1 for _ in f)
            except Exception:
                pass

        new_config = MealConfig(
            uuid=new_uuid,
            name=target_name,
            created_at=datetime.now().isoformat(),
            sampling_config=meal_config.sampling_config,
            collection_name=new_collection_name,
            pdf_files=new_pdf_files,
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
            f"[{new_uuid[:8]}] ({len(new_pdf_files)} PDFs, {total_pages} pages, {total_chunks} chunks)"
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
