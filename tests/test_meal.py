import hashlib
import json
from pathlib import Path

import pytest

from src.meal import (
    ArtifactCache,
    MealConfig,
    MealFile,
    MealManager,
    MealStatus,
    build_chunks_if_needed,
    compute_chunker_config_hash,
    compute_data_id,
    compute_embedding_config_hash,
    compute_file_sha256,
    compute_index_key,
    compute_parser_config_hash,
    generate_collection_name,
    generate_timestamp_name,
    validate_meal_name,
)


class TestMealFile:
    def test_creation(self):
        mf = MealFile(path="test.pdf", sha256="abc123", size_bytes=1024)
        assert mf.path == "test.pdf"
        assert mf.sha256 == "abc123"
        assert mf.size_bytes == 1024


class TestMealConfig:
    def _make_config(self, **overrides):
        defaults = {
            "data_id": "a1b2c3d4e5f6789012345678abcdef1234567890abcdef1234567890abcdef12",
            "name": "test_meal",
            "created_at": "2026-04-16T14:30:00",
            "sampling_config": {"mode": "count", "value": 10, "seed": 42},
            "collection_name": "m_a1b2c3d4e5f6",
            "pdf_files": [
                MealFile(path="test.pdf", sha256="abc123", size_bytes=1024)
            ],
            "config_snapshot": {
                "parser": {"algorithm": "pymupdf4llm"},
                "chunker": {"chunk_size": 512, "overlap": 0},
                "embedding": {"model_name": "BAAI/bge-large-zh-v1.5"},
            },
            "config_hashes": {
                "parser": "p1a2b3c4",
                "chunker": "c5d6e7f8",
                "embedding": "e9f0a1b2",
            },
            "stats": {"total_pdfs": 1, "total_pages": 50, "total_chunks": 200},
        }
        defaults.update(overrides)
        return MealConfig(**defaults)

    def test_to_dict(self):
        config = self._make_config()
        d = config.to_dict()
        assert d["data_id"] == "a1b2c3d4e5f6789012345678abcdef1234567890abcdef1234567890abcdef12"
        assert d["name"] == "test_meal"
        assert len(d["pdf_files"]) == 1
        assert d["pdf_files"][0]["path"] == "test.pdf"
        assert d["config_snapshot"] is not None
        assert d["config_hashes"] is not None

    def test_from_dict(self):
        data = {
            "data_id": "a1b2c3d4e5f6789012345678abcdef1234567890abcdef1234567890abcdef12",
            "name": "test_meal",
            "created_at": "2026-04-16T14:30:00",
            "sampling_config": {"mode": "count", "value": 10, "seed": 42},
            "collection_name": "m_a1b2c3d4e5f6",
            "pdf_files": [
                {"path": "test.pdf", "sha256": "abc123", "size_bytes": 1024}
            ],
            "config_snapshot": {"chunker": {"chunk_size": 512}},
            "config_hashes": {"chunker": "c5d6e7f8"},
            "stats": {"total_pdfs": 1, "total_pages": 50, "total_chunks": 200},
        }
        config = MealConfig.from_dict(data)
        assert config.data_id == "a1b2c3d4e5f6789012345678abcdef1234567890abcdef1234567890abcdef12"
        assert config.name == "test_meal"
        assert len(config.pdf_files) == 1
        assert isinstance(config.pdf_files[0], MealFile)
        assert config.pdf_files[0].path == "test.pdf"
        assert config.config_hashes == {"chunker": "c5d6e7f8"}

    def test_from_dict_legacy_uuid(self):
        data = {
            "uuid": "legacy-uuid-1234",
            "name": "legacy_meal",
            "created_at": "2026-04-16T14:30:00",
            "sampling_config": None,
            "collection_name": "m_legacy-u",
            "pdf_files": [
                {"path": "a.pdf", "sha256": "hash_a", "size_bytes": 100},
                {"path": "b.pdf", "sha256": "hash_b", "size_bytes": 200},
            ],
            "stats": {},
        }
        config = MealConfig.from_dict(data)
        assert config.data_id != ""
        expected = hashlib.sha256(b"hash_a|hash_b").hexdigest()
        assert config.data_id == expected

    def test_roundtrip(self):
        config = self._make_config()
        d = config.to_dict()
        config2 = MealConfig.from_dict(d)
        assert config.data_id == config2.data_id
        assert config.name == config2.name
        assert len(config.pdf_files) == len(config2.pdf_files)
        assert config.config_hashes == config2.config_hashes


class TestComputeDataId:
    def test_same_files_same_id(self):
        files = [
            MealFile(path="a.pdf", sha256="hash_a", size_bytes=100),
            MealFile(path="b.pdf", sha256="hash_b", size_bytes=200),
        ]
        id1 = compute_data_id(files)
        id2 = compute_data_id(files)
        assert id1 == id2

    def test_order_independent(self):
        files_ab = [
            MealFile(path="a.pdf", sha256="hash_a", size_bytes=100),
            MealFile(path="b.pdf", sha256="hash_b", size_bytes=200),
        ]
        files_ba = [
            MealFile(path="b.pdf", sha256="hash_b", size_bytes=200),
            MealFile(path="a.pdf", sha256="hash_a", size_bytes=100),
        ]
        assert compute_data_id(files_ab) == compute_data_id(files_ba)

    def test_different_files_different_id(self):
        files_a = [MealFile(path="a.pdf", sha256="hash_a", size_bytes=100)]
        files_b = [MealFile(path="b.pdf", sha256="hash_b", size_bytes=200)]
        assert compute_data_id(files_a) != compute_data_id(files_b)

    def test_is_sha256(self):
        files = [MealFile(path="a.pdf", sha256="hash_a", size_bytes=100)]
        result = compute_data_id(files)
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)


class TestConfigHashes:
    def test_parser_config_hash_deterministic(self):
        config = {"algorithm": "pymupdf4llm"}
        h1 = compute_parser_config_hash(config)
        h2 = compute_parser_config_hash(config)
        assert h1 == h2
        assert len(h1) == 8

    def test_parser_config_hash_different_options(self):
        config_a = {"algorithm": "pymupdf4llm", "pymupdf4llm": {"page_chunks": True}}
        config_b = {"algorithm": "pymupdf4llm", "pymupdf4llm": {"page_chunks": False}}
        h_a = compute_parser_config_hash(config_a)
        h_b = compute_parser_config_hash(config_b)
        assert h_a != h_b

    def test_parser_config_hash_same_options(self):
        config_a = {"algorithm": "pymupdf4llm", "pymupdf4llm": {"page_chunks": True}}
        config_b = {"algorithm": "pymupdf4llm", "pymupdf4llm": {"page_chunks": True}}
        h_a = compute_parser_config_hash(config_a)
        h_b = compute_parser_config_hash(config_b)
        assert h_a == h_b

    def test_parser_config_hash_empty_options_backward_compat(self):
        config = {"algorithm": "pymupdf4llm"}
        h = compute_parser_config_hash(config)
        assert len(h) == 8

    def test_parser_config_hash_options_from_pymupdf4llm_key(self):
        config = {"algorithm": "pymupdf4llm", "pymupdf4llm": {"page_chunks": True}}
        h1 = compute_parser_config_hash(config)
        config_minimal = {"algorithm": "pymupdf4llm"}
        h2 = compute_parser_config_hash(config_minimal)
        assert h1 != h2

    def test_chunker_config_hash_changes_with_params(self):
        config_a = {"chunk_size": 512, "chunk_overlap": 0, "encoding": "cl100k_base"}
        config_b = {"chunk_size": 512, "chunk_overlap": 50, "encoding": "cl100k_base"}
        h_a = compute_chunker_config_hash(config_a)
        h_b = compute_chunker_config_hash(config_b)
        assert h_a != h_b

    def test_chunker_config_hash_same_params(self):
        config = {"chunk_size": 512, "chunk_overlap": 0, "encoding": "cl100k_base"}
        h1 = compute_chunker_config_hash(config)
        h2 = compute_chunker_config_hash(config)
        assert h1 == h2

    def test_chunker_config_hash_different_strategies(self):
        config_fixed = {
            "strategy": "fixed",
            "chunk_size": 512,
            "chunk_overlap": 0,
            "encoding": "cl100k_base",
        }
        config_semantic = {
            "strategy": "semantic",
            "chunk_size": 512,
            "chunk_overlap": 0,
            "encoding": "cl100k_base",
            "semantic": {"similarity_threshold": 0.5, "min_chunk_size": 100},
        }
        h_fixed = compute_chunker_config_hash(config_fixed)
        h_semantic = compute_chunker_config_hash(config_semantic)
        assert h_fixed != h_semantic, "Different strategies should produce different hashes"

    def test_chunker_config_hash_semantic_different_thresholds(self):
        config_a = {
            "strategy": "semantic",
            "chunk_size": 512,
            "chunk_overlap": 0,
            "encoding": "cl100k_base",
            "semantic": {"similarity_threshold": 0.5, "min_chunk_size": 100},
        }
        config_b = {
            "strategy": "semantic",
            "chunk_size": 512,
            "chunk_overlap": 0,
            "encoding": "cl100k_base",
            "semantic": {"similarity_threshold": 0.3, "min_chunk_size": 100},
        }
        h_a = compute_chunker_config_hash(config_a)
        h_b = compute_chunker_config_hash(config_b)
        assert h_a != h_b, "Different semantic thresholds should produce different hashes"

    def test_chunker_config_hash_semantic_different_percentiles(self):
        config_a = {
            "strategy": "semantic",
            "chunk_size": 512,
            "chunk_overlap": 0,
            "encoding": "cl100k_base",
            "semantic": {"breakpoint_percentile": 25, "min_chunk_size": 100},
        }
        config_b = {
            "strategy": "semantic",
            "chunk_size": 512,
            "chunk_overlap": 0,
            "encoding": "cl100k_base",
            "semantic": {"breakpoint_percentile": 50, "min_chunk_size": 100},
        }
        h_a = compute_chunker_config_hash(config_a)
        h_b = compute_chunker_config_hash(config_b)
        assert h_a != h_b, "Different breakpoint percentiles should produce different hashes"

    def test_chunker_config_hash_default_strategy_is_fixed(self):
        config_no_strategy = {
            "chunk_size": 512,
            "chunk_overlap": 0,
            "encoding": "cl100k_base",
        }
        config_fixed = {
            "strategy": "fixed",
            "chunk_size": 512,
            "chunk_overlap": 0,
            "encoding": "cl100k_base",
        }
        h_no_strategy = compute_chunker_config_hash(config_no_strategy)
        h_fixed = compute_chunker_config_hash(config_fixed)
        assert h_no_strategy == h_fixed, "Default strategy should be 'fixed'"

    def test_embedding_config_hash(self):
        config = {"model_name": "BAAI/bge-large-zh-v1.5"}
        h = compute_embedding_config_hash(config)
        assert len(h) == 8

    def test_embedding_config_hash_different_models(self):
        config_a = {"model_name": "BAAI/bge-large-zh-v1.5"}
        config_b = {"model_name": "text-embedding-3-small"}
        assert compute_embedding_config_hash(config_a) != compute_embedding_config_hash(config_b)

    def test_index_key_combines_all(self):
        data_id = "abc123"
        hashes_a = {"parser": "p1", "chunker": "c1", "embedding": "e1"}
        hashes_b = {"parser": "p1", "chunker": "c2", "embedding": "e1"}
        key_a = compute_index_key(data_id, hashes_a)
        key_b = compute_index_key(data_id, hashes_b)
        assert key_a != key_b
        assert len(key_a) == 64

    def test_index_key_deterministic(self):
        data_id = "abc123"
        hashes = {"parser": "p1", "chunker": "c1", "embedding": "e1"}
        key1 = compute_index_key(data_id, hashes)
        key2 = compute_index_key(data_id, hashes)
        assert key1 == key2


class TestValidateMealName:
    def test_valid_names(self):
        assert validate_meal_name("small_sample") is True
        assert validate_meal_name("5k-pages") is True
        assert validate_meal_name("test123") is True
        assert validate_meal_name("A_B_C") is True

    def test_invalid_names(self):
        assert validate_meal_name("") is False
        assert validate_meal_name("my meal") is False
        assert validate_meal_name("meal.name") is False
        assert validate_meal_name("meal/name") is False
        assert validate_meal_name("中文") is False


class TestGenerateCollectionName:
    def test_default_prefix(self):
        index_key = "a1b2c3d4e5f67890abcdef1234567890abcdef1234567890abcdef12345678"
        result = generate_collection_name(index_key)
        assert result == "m_a1b2c3d4e5f6"

    def test_custom_prefix(self):
        index_key = "a1b2c3d4e5f67890abcdef1234567890abcdef1234567890abcdef12345678"
        result = generate_collection_name(index_key, prefix="meal_")
        assert result == "meal_a1b2c3d4e5f6"

    def test_different_keys_different_names(self):
        key_a = "aaa" + "a" * 61
        key_b = "bbb" + "b" * 61
        assert generate_collection_name(key_a) != generate_collection_name(key_b)


class TestGenerateTimestampName:
    def test_format(self):
        name = generate_timestamp_name()
        assert name.startswith("meal_")
        assert len(name) > 5


class TestComputeFileSha256:
    def test_known_content(self, tmp_path):
        test_file = tmp_path / "test.txt"
        test_file.write_text("hello world")
        result = compute_file_sha256(test_file)
        assert isinstance(result, str)
        assert len(result) == 64

    def test_empty_file(self, tmp_path):
        test_file = tmp_path / "empty.txt"
        test_file.write_bytes(b"")
        result = compute_file_sha256(test_file)
        assert result == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

    def test_consistent(self, tmp_path):
        test_file = tmp_path / "test.txt"
        test_file.write_text("consistent content")
        r1 = compute_file_sha256(test_file)
        r2 = compute_file_sha256(test_file)
        assert r1 == r2


class TestArtifactCache:
    @pytest.fixture
    def cache(self, tmp_path):
        artifacts_dir = tmp_path / "artifacts"
        artifacts_dir.mkdir()
        return ArtifactCache(artifacts_dir)

    def test_get_parsed_dir(self, cache):
        data_id = "abc123" + "0" * 58
        parsed_dir = cache.get_parsed_dir(data_id)
        assert parsed_dir.name == "parsed"
        assert parsed_dir.parent.name == data_id[:12]

    def test_get_chunks_dir(self, cache):
        data_id = "abc123" + "0" * 58
        chunks_dir = cache.get_chunks_dir(data_id, "c5d6e7f8")
        assert chunks_dir.name == "chunks_c5d6e7f8"
        assert chunks_dir.parent.name == data_id[:12]

    def test_parsed_exists_false(self, cache):
        data_id = "abc123" + "0" * 58
        assert cache.parsed_exists(data_id, ["test.md"]) is False

    def test_parsed_exists_true(self, cache):
        data_id = "abc123" + "0" * 58
        parsed_dir = cache.get_parsed_dir(data_id)
        parsed_dir.mkdir(parents=True)
        (parsed_dir / "test.md").write_text("# Test")
        assert cache.parsed_exists(data_id, ["test.md"]) is True

    def test_parsed_exists_partial(self, cache):
        data_id = "abc123" + "0" * 58
        parsed_dir = cache.get_parsed_dir(data_id)
        parsed_dir.mkdir(parents=True)
        (parsed_dir / "a.md").write_text("# A")
        assert cache.parsed_exists(data_id, ["a.md", "b.md"]) is False

    def test_chunks_exist_false(self, cache):
        data_id = "abc123" + "0" * 58
        assert cache.chunks_exist(data_id, "c5d6e7f8", ["test.jsonl"]) is False

    def test_chunks_exist_true(self, cache):
        data_id = "abc123" + "0" * 58
        chunks_dir = cache.get_chunks_dir(data_id, "c5d6e7f8")
        chunks_dir.mkdir(parents=True)
        (chunks_dir / "test.jsonl").write_text("{}")
        assert cache.chunks_exist(data_id, "c5d6e7f8", ["test.jsonl"]) is True

    def test_ensure_dirs(self, cache):
        data_id = "abc123" + "0" * 58
        parsed_dir, chunks_dir = cache.ensure_dirs(data_id, "c5d6e7f8")
        assert parsed_dir.exists()
        assert chunks_dir.exists()

    def test_save_and_load_manifest(self, cache):
        data_id = "abc123" + "0" * 58
        manifest = {"data_id": data_id, "pdf_count": 5}
        cache.save_manifest(data_id, manifest)
        loaded = cache.load_manifest(data_id)
        assert loaded is not None
        assert loaded["pdf_count"] == 5

    def test_load_manifest_not_found(self, cache):
        data_id = "xyz789" + "0" * 58
        assert cache.load_manifest(data_id) is None


class TestMealManager:
    @pytest.fixture
    def temp_dirs(self, tmp_path):
        raw_dir = tmp_path / "raw"
        raw_dir.mkdir()
        parsed_dir = tmp_path / "parsed"
        parsed_dir.mkdir()
        chunks_dir = tmp_path / "chunks"
        chunks_dir.mkdir()
        vector_dir = tmp_path / "vector_store"
        vector_dir.mkdir()
        meals_dir = tmp_path / "meals"
        meals_dir.mkdir()
        artifacts_dir = tmp_path / "artifacts"
        artifacts_dir.mkdir()

        pdf_dir = raw_dir / "reports"
        pdf_dir.mkdir()
        for i in range(5):
            pdf_file = pdf_dir / f"report_{i}.pdf"
            pdf_file.write_bytes(f"fake pdf content {i}".encode())

        config = {
            "parser": {
                "input_dir": str(raw_dir),
                "output_dir": str(parsed_dir),
            },
            "chunker": {
                "input_dir": str(parsed_dir),
                "output_dir": str(chunks_dir),
                "chunk_size": 512,
                "chunk_overlap": 0,
            },
            "embedding": {
                "model_name": "BAAI/bge-large-zh-v1.5",
                "device": "cpu",
                "batch_size": 32,
            },
            "vector_store": {
                "persist_dir": str(vector_dir),
                "collection_name": "financial_reports",
                "distance": "Cosine",
            },
            "meals": {
                "dir": str(meals_dir),
                "collection_prefix": "m_",
            },
            "artifacts": {
                "dir": str(artifacts_dir),
            },
        }
        return config

    def _make_meal_config(self, **overrides):
        defaults = {
            "data_id": "a1b2c3d4e5f6789012345678abcdef1234567890abcdef1234567890abcdef12",
            "name": "test_meal",
            "created_at": "2026-04-16T14:30:00",
            "sampling_config": {"mode": "count", "value": 3, "seed": 42},
            "collection_name": "m_a1b2c3d4e5f6",
            "pdf_files": [
                MealFile(path="reports/report_0.pdf", sha256="abc", size_bytes=100)
            ],
            "config_snapshot": {"chunker": {"chunk_size": 512, "overlap": 0}},
            "config_hashes": {"chunker": "c5d6e7f8"},
            "stats": {"total_pdfs": 1, "total_pages": 50, "total_chunks": 200},
        }
        defaults.update(overrides)
        return MealConfig(**defaults)

    def _save_meal(self, manager, meal_config):
        meal_dir = manager.get_meal_dir(meal_config.name)
        meal_dir.mkdir(parents=True, exist_ok=True)
        (meal_dir / "test_sets").mkdir(exist_ok=True)
        with open(meal_dir / "manifest.json", "w", encoding="utf-8") as f:
            json.dump(meal_config.to_dict(), f, ensure_ascii=False, indent=2)

    def test_meal_exists_false(self, temp_dirs):
        manager = MealManager(temp_dirs)
        assert manager.meal_exists("nonexistent") is False

    def test_list_meals_empty(self, temp_dirs):
        manager = MealManager(temp_dirs)
        meals = manager.list_meals()
        assert meals == []

    def test_load_meal_not_found(self, temp_dirs):
        manager = MealManager(temp_dirs)
        with pytest.raises(FileNotFoundError):
            manager.load_meal("nonexistent")

    def test_save_and_load_meal(self, temp_dirs):
        manager = MealManager(temp_dirs)
        meal = self._make_meal_config()
        self._save_meal(manager, meal)

        loaded = manager.load_meal("test_meal")
        assert loaded.data_id == "a1b2c3d4e5f6789012345678abcdef1234567890abcdef1234567890abcdef12"
        assert loaded.name == "test_meal"
        assert len(loaded.pdf_files) == 1
        assert loaded.pdf_files[0].path == "reports/report_0.pdf"
        assert loaded.config_hashes is not None

    def test_check_meal_status_available(self, temp_dirs):
        manager = MealManager(temp_dirs)
        pdf_path = Path(temp_dirs["parser"]["input_dir"]) / "reports" / "report_0.pdf"
        sha256 = compute_file_sha256(pdf_path)

        meal = self._make_meal_config(
            pdf_files=[
                MealFile(
                    path="reports/report_0.pdf",
                    sha256=sha256,
                    size_bytes=pdf_path.stat().st_size,
                )
            ],
        )
        self._save_meal(manager, meal)

        status, issues = manager.check_meal_status("test_meal")
        assert status == MealStatus.AVAILABLE
        assert issues == []

    def test_check_meal_status_missing(self, temp_dirs):
        manager = MealManager(temp_dirs)
        meal = self._make_meal_config(
            pdf_files=[
                MealFile(
                    path="reports/nonexistent.pdf",
                    sha256="abc123",
                    size_bytes=100,
                )
            ],
        )
        self._save_meal(manager, meal)

        status, issues = manager.check_meal_status("test_meal")
        assert status == MealStatus.FILES_MISSING
        assert len(issues) == 1

    def test_check_meal_status_changed(self, temp_dirs):
        manager = MealManager(temp_dirs)
        meal = self._make_meal_config(
            pdf_files=[
                MealFile(
                    path="reports/report_0.pdf",
                    sha256="wrong_hash_value",
                    size_bytes=999,
                )
            ],
        )
        self._save_meal(manager, meal)

        status, issues = manager.check_meal_status("test_meal")
        assert status == MealStatus.FILES_CHANGED
        assert len(issues) == 1

    def test_rename_meal(self, temp_dirs):
        manager = MealManager(temp_dirs)
        meal = self._make_meal_config(name="old_name")
        self._save_meal(manager, meal)

        result = manager.rename_meal("old_name", "new_name")
        assert result.name == "new_name"
        assert result.data_id == "a1b2c3d4e5f6789012345678abcdef1234567890abcdef1234567890abcdef12"
        assert not manager.meal_exists("old_name")
        assert manager.meal_exists("new_name")

    def test_rename_meal_invalid_name(self, temp_dirs):
        manager = MealManager(temp_dirs)
        meal = self._make_meal_config(name="valid_name")
        self._save_meal(manager, meal)

        with pytest.raises(ValueError, match="Invalid meal name"):
            manager.rename_meal("valid_name", "invalid name")

    def test_rename_meal_duplicate_name(self, temp_dirs):
        manager = MealManager(temp_dirs)
        for name in ["meal_a", "meal_b"]:
            meal = self._make_meal_config(name=name)
            self._save_meal(manager, meal)

        with pytest.raises(ValueError, match="already exists"):
            manager.rename_meal("meal_a", "meal_b")

    def test_list_meals(self, temp_dirs):
        manager = MealManager(temp_dirs)
        for i in range(3):
            meal = self._make_meal_config(
                name=f"meal_{i}",
                data_id=f"{i:064d}",
            )
            self._save_meal(manager, meal)

        meals = manager.list_meals()
        assert len(meals) == 3
        names = {m.name for m in meals}
        assert names == {"meal_0", "meal_1", "meal_2"}

    def test_find_equivalent_meals(self, temp_dirs):
        manager = MealManager(temp_dirs)
        shared_data_id = "abc123" + "0" * 58

        meal_a = self._make_meal_config(
            name="meal_a",
            data_id=shared_data_id,
            collection_name="m_aaa111111111",
        )
        meal_b = self._make_meal_config(
            name="meal_b",
            data_id=shared_data_id,
            collection_name="m_bbb222222222",
        )
        meal_c = self._make_meal_config(
            name="meal_c",
            data_id="def456" + "0" * 58,
            collection_name="m_ccc333333333",
        )
        self._save_meal(manager, meal_a)
        self._save_meal(manager, meal_b)
        self._save_meal(manager, meal_c)

        equivalents = manager.find_equivalent_meals(shared_data_id)
        assert len(equivalents) == 2
        names = {m.name for m in equivalents}
        assert names == {"meal_a", "meal_b"}

    def test_copy_meal(self, temp_dirs):
        manager = MealManager(temp_dirs)
        meal = self._make_meal_config(
            name="source_meal",
            collection_name="m_source123456",
        )
        self._save_meal(manager, meal)

        result = manager.copy_meal("source_meal", "target_meal")
        assert result.name == "target_meal"
        assert result.data_id == meal.data_id
        assert result.collection_name == "m_source123456"
        assert manager.meal_exists("source_meal")
        assert manager.meal_exists("target_meal")

    def test_copy_meal_duplicate_name(self, temp_dirs):
        manager = MealManager(temp_dirs)
        meal = self._make_meal_config(name="existing")
        self._save_meal(manager, meal)

        with pytest.raises(ValueError, match="already exists"):
            manager.copy_meal("existing", "existing")

    def test_delete_meal(self, temp_dirs):
        manager = MealManager(temp_dirs)
        meal = self._make_meal_config(name="to_delete")
        self._save_meal(manager, meal)

        assert manager.meal_exists("to_delete")
        manager.delete_meal("to_delete")
        assert not manager.meal_exists("to_delete")

    def test_build_config_snapshot_and_hashes(self, temp_dirs):
        manager = MealManager(temp_dirs)
        snapshot, hashes = manager._build_config_snapshot_and_hashes()

        assert "parser" in snapshot
        assert "chunker" in snapshot
        assert "embedding" in snapshot
        assert "retrieval" in snapshot

        assert "parser" in hashes
        assert "chunker" in hashes
        assert "embedding" in hashes

        assert len(hashes["parser"]) == 8
        assert len(hashes["chunker"]) == 8
        assert len(hashes["embedding"]) == 8

    def test_config_snapshot_includes_parser_options(self, temp_dirs):
        temp_dirs["parser"]["pymupdf4llm"] = {"page_chunks": True}
        manager = MealManager(temp_dirs)
        snapshot, hashes = manager._build_config_snapshot_and_hashes()

        assert "options" in snapshot["parser"]
        assert snapshot["parser"]["options"] == {"page_chunks": True}
        assert len(hashes["parser"]) == 8

    def test_config_snapshot_parser_options_default_empty(self, temp_dirs):
        manager = MealManager(temp_dirs)
        snapshot, _ = manager._build_config_snapshot_and_hashes()

        assert "options" in snapshot["parser"]
        assert snapshot["parser"]["options"] == {}


class TestBuildChunksIfNeeded:
    def test_build_chunks_if_needed_pages_json(self, tmp_path):
        from unittest.mock import patch

        parsed_dir = tmp_path / "parsed"
        parsed_dir.mkdir()
        (parsed_dir / "report.pages.json").write_text('{"pages": []}')

        chunks_dir = tmp_path / "chunks"
        chunker_config = {"chunk_size": 512, "chunk_overlap": 0}

        with patch("src.chunker.process_parsed_files_page_aware") as mock_page_aware:
            build_chunks_if_needed(parsed_dir, chunks_dir, chunker_config)
            mock_page_aware.assert_called_once_with(
                input_dir=str(parsed_dir),
                output_dir=str(chunks_dir),
                chunk_size=512,
                overlap=0,
                source_filter={"report.pages.json"},
            )

    def test_build_chunks_if_needed_md(self, tmp_path):
        from unittest.mock import patch

        parsed_dir = tmp_path / "parsed"
        parsed_dir.mkdir()
        (parsed_dir / "report.md").write_text("# Report")

        chunks_dir = tmp_path / "chunks"
        chunker_config = {"chunk_size": 512, "chunk_overlap": 0}

        with patch("src.chunker.process_parsed_files") as mock_process:
            build_chunks_if_needed(parsed_dir, chunks_dir, chunker_config)
            mock_process.assert_called_once_with(
                input_dir=str(parsed_dir),
                output_dir=str(chunks_dir),
                chunk_size=512,
                overlap=0,
                source_filter={"report.md"},
            )

    def test_build_chunks_if_needed_skips_existing(self, tmp_path):
        from unittest.mock import patch

        parsed_dir = tmp_path / "parsed"
        parsed_dir.mkdir()
        (parsed_dir / "report.md").write_text("# Report")

        chunks_dir = tmp_path / "chunks"
        chunks_dir.mkdir()
        (chunks_dir / "report.jsonl").write_text("{}")

        chunker_config = {"chunk_size": 512, "chunk_overlap": 0}

        with patch("src.chunker.process_parsed_files") as mock_process:
            build_chunks_if_needed(parsed_dir, chunks_dir, chunker_config)
            mock_process.assert_not_called()
