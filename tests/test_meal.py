import hashlib
import json
import threading
from pathlib import Path

import pytest

from src.exceptions import MealError
from src.meal import (
    ArtifactCache,
    MealConfig,
    MealFile,
    MealManager,
    MealStatus,
    _infer_equivalence_groups,
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
            "pdf_files": [MealFile(path="test.pdf", sha256="abc123", size_bytes=1024)],
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
        assert (
            d["data_id"]
            == "a1b2c3d4e5f6789012345678abcdef1234567890abcdef1234567890abcdef12"
        )
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
            "pdf_files": [{"path": "test.pdf", "sha256": "abc123", "size_bytes": 1024}],
            "config_snapshot": {"chunker": {"chunk_size": 512}},
            "config_hashes": {"chunker": "c5d6e7f8"},
            "stats": {"total_pdfs": 1, "total_pages": 50, "total_chunks": 200},
        }
        config = MealConfig.from_dict(data)
        assert (
            config.data_id
            == "a1b2c3d4e5f6789012345678abcdef1234567890abcdef1234567890abcdef12"
        )
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

    def test_composition_default_empty_dict(self):
        config = self._make_config()
        assert config.composition == {}
        d = config.to_dict()
        assert d["composition"] == {}

    def test_composition_serialization(self):
        composition_data = {
            "type": "merged",
            "sources": [
                {"meal": "meal_a", "pdf_count": 10},
                {"meal": "meal_b", "pdf_count": 15},
            ],
            "created_at": "2026-04-23T10:00:00",
        }
        config = self._make_config(composition=composition_data)
        d = config.to_dict()
        assert d["composition"] == composition_data
        assert d["composition"]["type"] == "merged"
        assert len(d["composition"]["sources"]) == 2

    def test_composition_deserialization(self):
        data = {
            "data_id": "a1b2c3d4e5f6789012345678abcdef1234567890abcdef1234567890abcdef12",
            "name": "test_meal",
            "created_at": "2026-04-16T14:30:00",
            "sampling_config": {"mode": "count", "value": 10, "seed": 42},
            "collection_name": "m_a1b2c3d4e5f6",
            "pdf_files": [{"path": "test.pdf", "sha256": "abc123", "size_bytes": 1024}],
            "composition": {
                "type": "extended",
                "base_meal": "meal_a",
                "added_files": ["new1.pdf", "new2.pdf"],
                "created_at": "2026-04-23T10:00:00",
            },
        }
        config = MealConfig.from_dict(data)
        assert config.composition["type"] == "extended"
        assert config.composition["base_meal"] == "meal_a"
        assert len(config.composition["added_files"]) == 2

    def test_composition_backward_compat(self):
        data = {
            "data_id": "a1b2c3d4e5f6789012345678abcdef1234567890abcdef1234567890abcdef12",
            "name": "legacy_meal",
            "created_at": "2026-04-16T14:30:00",
            "sampling_config": None,
            "collection_name": "m_a1b2c3d4e5f6",
            "pdf_files": [{"path": "test.pdf", "sha256": "abc123", "size_bytes": 1024}],
        }
        config = MealConfig.from_dict(data)
        assert config.composition == {}

    def test_composition_roundtrip(self):
        composition_data = {
            "type": "original",
            "created_at": "2026-04-23T10:00:00",
        }
        config = self._make_config(composition=composition_data)
        d = config.to_dict()
        config2 = MealConfig.from_dict(d)
        assert config2.composition == composition_data


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
        config_a = {"algorithm": "pymupdf4llm", "options": {"page_chunks": True}}
        config_b = {"algorithm": "pymupdf4llm", "options": {"page_chunks": False}}
        h_a = compute_parser_config_hash(config_a)
        h_b = compute_parser_config_hash(config_b)
        assert h_a != h_b

    def test_parser_config_hash_same_options(self):
        config_a = {"algorithm": "pymupdf4llm", "options": {"page_chunks": True}}
        config_b = {"algorithm": "pymupdf4llm", "options": {"page_chunks": True}}
        h_a = compute_parser_config_hash(config_a)
        h_b = compute_parser_config_hash(config_b)
        assert h_a == h_b

    def test_parser_config_hash_empty_options_backward_compat(self):
        config = {"algorithm": "pymupdf4llm"}
        h = compute_parser_config_hash(config)
        assert len(h) == 8

    def test_parser_config_hash_options_included(self):
        config = {"algorithm": "pymupdf4llm", "options": {"page_chunks": True}}
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
        assert h_fixed != h_semantic, (
            "Different strategies should produce different hashes"
        )

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
        assert h_a != h_b, (
            "Different semantic thresholds should produce different hashes"
        )

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
        assert h_a != h_b, (
            "Different breakpoint percentiles should produce different hashes"
        )

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
        assert compute_embedding_config_hash(config_a) != compute_embedding_config_hash(
            config_b
        )

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
        assert (
            result == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        )

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
        raw_dir = tmp_path / "raw"
        raw_dir.mkdir()
        return ArtifactCache(artifacts_dir, raw_dir)

    def test_get_parsed_dir(self, cache):
        data_id = "abc123" + "0" * 58
        parsed_dir = cache.get_parsed_dir(data_id)
        assert parsed_dir.name == "parsed"
        assert parsed_dir.parent.name == data_id[:16]

    def test_get_chunks_dir(self, cache):
        data_id = "abc123" + "0" * 58
        chunks_dir = cache.get_chunks_dir(data_id, "c5d6e7f8")
        assert chunks_dir.name == "chunks_c5d6e7f8"
        assert chunks_dir.parent.name == data_id[:16]

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

    def test_concurrent_manifest_write(self, tmp_path):
        cache = ArtifactCache(artifacts_dir=tmp_path, raw_dir=None)
        data_id = "a" * 64
        errors = []
        results = []

        def write_manifest(index):
            try:
                manifest = {"index": index, "data": f"test_{index}"}
                result = cache.save_manifest(data_id, manifest)
                results.append(result)
            except Exception as e:
                errors.append(str(e))

        threads = [
            threading.Thread(target=write_manifest, args=(i,)) for i in range(10)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Errors during concurrent writes: {errors}"
        loaded = cache.load_manifest(data_id)
        assert loaded is not None
        assert "index" in loaded

    def test_parsed_exists_sha_validation(self, tmp_path):
        raw_dir = tmp_path / "raw"
        raw_dir.mkdir()
        artifacts_dir = tmp_path / "artifacts"
        artifacts_dir.mkdir()

        pdf_file = raw_dir / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 fake content")

        cache = ArtifactCache(artifacts_dir=artifacts_dir, raw_dir=raw_dir)
        data_id = compute_data_id(
            [
                MealFile(
                    path="test.pdf",
                    sha256=compute_file_sha256(pdf_file),
                    size_bytes=100,
                )
            ]
        )

        parsed_dir = cache.get_parsed_dir(data_id, "abc12345")
        parsed_dir.mkdir(parents=True)
        (parsed_dir / "test.md").write_text("parsed content", encoding="utf-8")

        manifest = {"pdf_inventory": {"test.pdf": compute_file_sha256(pdf_file)}}
        assert (
            cache.parsed_exists(
                data_id, ["test.md"], parser_hash="abc12345", manifest=manifest
            )
            is True
        )

        pdf_file.write_bytes(b"%PDF-1.4 modified content")
        assert (
            cache.parsed_exists(
                data_id, ["test.md"], parser_hash="abc12345", manifest=manifest
            )
            is False
        )

    def test_chunks_exist_sha_validation(self, tmp_path):
        raw_dir = tmp_path / "raw"
        raw_dir.mkdir()
        artifacts_dir = tmp_path / "artifacts"
        artifacts_dir.mkdir()

        pdf_file = raw_dir / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 fake content")

        cache = ArtifactCache(artifacts_dir=artifacts_dir, raw_dir=raw_dir)
        data_id = compute_data_id(
            [
                MealFile(
                    path="test.pdf",
                    sha256=compute_file_sha256(pdf_file),
                    size_bytes=100,
                )
            ]
        )

        chunks_dir = cache.get_chunks_dir(data_id, "abc12345")
        chunks_dir.mkdir(parents=True)
        (chunks_dir / "test.jsonl").write_text("{}", encoding="utf-8")

        manifest = {"pdf_inventory": {"test.pdf": compute_file_sha256(pdf_file)}}
        assert (
            cache.chunks_exist(data_id, "abc12345", ["test.jsonl"], manifest=manifest)
            is True
        )

        pdf_file.write_bytes(b"%PDF-1.4 modified content")
        assert (
            cache.chunks_exist(data_id, "abc12345", ["test.jsonl"], manifest=manifest)
            is False
        )

    def test_parsed_exists_manifest_missing_pdf(self, tmp_path):
        raw_dir = tmp_path / "raw"
        raw_dir.mkdir()
        artifacts_dir = tmp_path / "artifacts"
        artifacts_dir.mkdir()

        cache = ArtifactCache(artifacts_dir=artifacts_dir, raw_dir=raw_dir)
        data_id = "a" * 64

        parsed_dir = cache.get_parsed_dir(data_id, "abc12345")
        parsed_dir.mkdir(parents=True)
        (parsed_dir / "test.md").write_text("parsed content", encoding="utf-8")

        manifest = {"pdf_inventory": {"nonexistent.pdf": "somehash"}}
        assert (
            cache.parsed_exists(
                data_id, ["test.md"], parser_hash="abc12345", manifest=manifest
            )
            is False
        )

    def test_parsed_exists_no_manifest_backward_compat(self, cache):
        data_id = "abc123" + "0" * 58
        parsed_dir = cache.get_parsed_dir(data_id)
        parsed_dir.mkdir(parents=True)
        (parsed_dir / "test.md").write_text("# Test")
        assert cache.parsed_exists(data_id, ["test.md"]) is True

    def test_chunks_exist_no_manifest_backward_compat(self, cache):
        data_id = "abc123" + "0" * 58
        chunks_dir = cache.get_chunks_dir(data_id, "c5d6e7f8")
        chunks_dir.mkdir(parents=True)
        (chunks_dir / "test.jsonl").write_text("{}")
        assert cache.chunks_exist(data_id, "c5d6e7f8", ["test.jsonl"]) is True


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
        with pytest.raises(MealError):
            manager.load_meal("nonexistent")

    def test_save_and_load_meal(self, temp_dirs):
        manager = MealManager(temp_dirs)
        meal = self._make_meal_config()
        self._save_meal(manager, meal)

        loaded = manager.load_meal("test_meal")
        assert (
            loaded.data_id
            == "a1b2c3d4e5f6789012345678abcdef1234567890abcdef1234567890abcdef12"
        )
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
        assert (
            result.data_id
            == "a1b2c3d4e5f6789012345678abcdef1234567890abcdef1234567890abcdef12"
        )
        assert not manager.meal_exists("old_name")
        assert manager.meal_exists("new_name")

    def test_rename_meal_invalid_name(self, temp_dirs):
        manager = MealManager(temp_dirs)
        meal = self._make_meal_config(name="valid_name")
        self._save_meal(manager, meal)

        with pytest.raises(MealError, match="Invalid meal name"):
            manager.rename_meal("valid_name", "invalid name")

    def test_rename_meal_duplicate_name(self, temp_dirs):
        manager = MealManager(temp_dirs)
        for name in ["meal_a", "meal_b"]:
            meal = self._make_meal_config(name=name)
            self._save_meal(manager, meal)

        with pytest.raises(MealError, match="already exists"):
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

        with pytest.raises(MealError, match="already exists"):
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

    def test_find_full_dataset_meal_found(self, temp_dirs):
        manager = MealManager(temp_dirs)
        full_data_id = manager.cache._compute_full_data_id()
        meal_config = self._make_meal_config(name="full_meal", data_id=full_data_id)
        self._save_meal(manager, meal_config)

        result = manager.find_full_dataset_meal()
        assert result is not None
        assert result.name == "full_meal"
        assert result.data_id == full_data_id

    def test_find_full_dataset_meal_not_found(self, temp_dirs):
        manager = MealManager(temp_dirs)
        other_meal = self._make_meal_config(name="partial_meal", data_id="deadbeef" * 8)
        self._save_meal(manager, other_meal)

        result = manager.find_full_dataset_meal()
        assert result is None

    def test_find_full_dataset_meal_no_pdfs(self, tmp_path):
        raw_dir = tmp_path / "raw"
        raw_dir.mkdir()
        meals_dir = tmp_path / "meals"
        meals_dir.mkdir()
        artifacts_dir = tmp_path / "artifacts"
        artifacts_dir.mkdir()
        config = {
            "parser": {"input_dir": str(raw_dir)},
            "meals": {"dir": str(meals_dir)},
            "artifacts": {"dir": str(artifacts_dir)},
        }
        manager = MealManager(config)
        result = manager.find_full_dataset_meal()
        assert result is None


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
                encoding_name="cl100k_base",
                source_filter={"report.pages.json"},
                model_name=None,
                cross_page_overlap=0,
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
                encoding_name="cl100k_base",
                source_filter={"report.md"},
                model_name=None,
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


class TestMergeMeals:
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
        for i in range(10):
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
            "pdf_files": [],
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

    def test_merge_meals_empty_list(self, temp_dirs):
        manager = MealManager(temp_dirs)
        with pytest.raises(MealError, match="meal_names cannot be empty"):
            manager.merge_meals([])

    def test_merge_meals_nonexistent_meal(self, temp_dirs):
        manager = MealManager(temp_dirs)
        with pytest.raises(MealError, match="does not exist"):
            manager.merge_meals(["nonexistent_meal"])

    def test_merge_meals_invalid_name(self, temp_dirs):
        manager = MealManager(temp_dirs)
        meal_a = self._make_meal_config(name="meal_a")
        self._save_meal(manager, meal_a)

        with pytest.raises(MealError, match="Invalid meal name"):
            manager.merge_meals(["meal_a"], name="invalid name")

    def test_merge_meals_duplicate_name(self, temp_dirs):
        manager = MealManager(temp_dirs)
        meal_a = self._make_meal_config(name="meal_a")
        self._save_meal(manager, meal_a)

        with pytest.raises(MealError, match="already exists"):
            manager.merge_meals(["meal_a"], name="meal_a")

    def test_merge_two_meals_no_overlap(self, temp_dirs):
        from unittest.mock import MagicMock, patch

        manager = MealManager(temp_dirs)

        meal_a = self._make_meal_config(
            name="meal_a",
            data_id="a" * 64,
            collection_name="m_aaaaaaaaaaaa",
            pdf_files=[
                MealFile(path="reports/report_0.pdf", sha256="hash_0", size_bytes=100),
                MealFile(path="reports/report_1.pdf", sha256="hash_1", size_bytes=200),
            ],
        )
        meal_b = self._make_meal_config(
            name="meal_b",
            data_id="b" * 64,
            collection_name="m_bbbbbbbbbbbb",
            pdf_files=[
                MealFile(path="reports/report_2.pdf", sha256="hash_2", size_bytes=300),
                MealFile(path="reports/report_3.pdf", sha256="hash_3", size_bytes=400),
            ],
        )
        self._save_meal(manager, meal_a)
        self._save_meal(manager, meal_b)

        with (
            patch("src.meal.build_index_from_chunks") as mock_build_index,
            patch("src.meal.build_chunks_if_needed"),
            patch("src.sampler.count_pdf_pages", return_value=10),
        ):
            mock_build_index.return_value = MagicMock()

            result = manager.merge_meals(["meal_a", "meal_b"], name="merged_meal")

        assert result.name == "merged_meal"
        assert len(result.pdf_files) == 4
        assert result.composition["type"] == "merged"
        assert len(result.composition["sources"]) == 2
        assert result.composition["dedup_info"]["total_input_pdfs"] == 4
        assert result.composition["dedup_info"]["unique_pdfs"] == 4
        assert result.composition["dedup_info"]["duplicates"] == 0
        assert manager.meal_exists("merged_meal")

    def test_merge_meals_with_overlap(self, temp_dirs):
        from unittest.mock import MagicMock, patch

        manager = MealManager(temp_dirs)

        meal_a = self._make_meal_config(
            name="meal_a",
            data_id="a" * 64,
            collection_name="m_aaaaaaaaaaaa",
            pdf_files=[
                MealFile(path="reports/report_0.pdf", sha256="hash_0", size_bytes=100),
                MealFile(path="reports/report_1.pdf", sha256="hash_1", size_bytes=200),
            ],
        )
        meal_b = self._make_meal_config(
            name="meal_b",
            data_id="b" * 64,
            collection_name="m_bbbbbbbbbbbb",
            pdf_files=[
                MealFile(path="reports/report_1.pdf", sha256="hash_1", size_bytes=200),
                MealFile(path="reports/report_2.pdf", sha256="hash_2", size_bytes=300),
            ],
        )
        self._save_meal(manager, meal_a)
        self._save_meal(manager, meal_b)

        with (
            patch("src.meal.build_index_from_chunks") as mock_build_index,
            patch("src.meal.build_chunks_if_needed"),
            patch("src.sampler.count_pdf_pages", return_value=10),
        ):
            mock_build_index.return_value = MagicMock()

            result = manager.merge_meals(["meal_a", "meal_b"], name="merged_meal")

        assert len(result.pdf_files) == 3
        paths = [f.path for f in result.pdf_files]
        assert "reports/report_0.pdf" in paths
        assert "reports/report_1.pdf" in paths
        assert "reports/report_2.pdf" in paths
        assert result.composition["dedup_info"]["total_input_pdfs"] == 4
        assert result.composition["dedup_info"]["unique_pdfs"] == 3
        assert result.composition["dedup_info"]["duplicates"] == 1

    def test_merge_meals_composition_metadata(self, temp_dirs):
        from unittest.mock import MagicMock, patch

        manager = MealManager(temp_dirs)

        meal_a = self._make_meal_config(
            name="meal_a",
            data_id="a" * 64,
            collection_name="m_aaaaaaaaaaaa",
            pdf_files=[
                MealFile(path="reports/report_0.pdf", sha256="hash_0", size_bytes=100),
            ],
        )
        meal_b = self._make_meal_config(
            name="meal_b",
            data_id="b" * 64,
            collection_name="m_bbbbbbbbbbbb",
            pdf_files=[
                MealFile(path="reports/report_1.pdf", sha256="hash_1", size_bytes=200),
                MealFile(path="reports/report_2.pdf", sha256="hash_2", size_bytes=300),
            ],
        )
        self._save_meal(manager, meal_a)
        self._save_meal(manager, meal_b)

        with (
            patch("src.meal.build_index_from_chunks") as mock_build_index,
            patch("src.meal.build_chunks_if_needed"),
            patch("src.sampler.count_pdf_pages", return_value=10),
        ):
            mock_build_index.return_value = MagicMock()

            result = manager.merge_meals(["meal_a", "meal_b"], name="merged_meal")

        assert result.composition["type"] == "merged"
        assert len(result.composition["sources"]) == 2
        assert result.composition["sources"][0]["meal"] == "meal_a"
        assert result.composition["sources"][0]["pdf_count"] == 1
        assert result.composition["sources"][1]["meal"] == "meal_b"
        assert result.composition["sources"][1]["pdf_count"] == 2
        assert "created_at" in result.composition

    def test_merge_meals_auto_timestamp_name(self, temp_dirs):
        from unittest.mock import MagicMock, patch

        manager = MealManager(temp_dirs)

        meal_a = self._make_meal_config(
            name="meal_a",
            data_id="a" * 64,
            collection_name="m_aaaaaaaaaaaa",
            pdf_files=[
                MealFile(path="reports/report_0.pdf", sha256="hash_0", size_bytes=100),
            ],
        )
        self._save_meal(manager, meal_a)

        with (
            patch("src.meal.build_index_from_chunks") as mock_build_index,
            patch("src.meal.build_chunks_if_needed"),
            patch("src.sampler.count_pdf_pages", return_value=10),
        ):
            mock_build_index.return_value = MagicMock()

            result = manager.merge_meals(["meal_a"])

        assert result.name.startswith("meal_")
        assert manager.meal_exists(result.name)

    def test_merge_meals_cache_reuse(self, temp_dirs):
        from unittest.mock import MagicMock, patch

        manager = MealManager(temp_dirs)

        meal_a = self._make_meal_config(
            name="meal_a",
            data_id="a" * 64,
            collection_name="m_aaaaaaaaaaaa",
            pdf_files=[
                MealFile(path="reports/report_0.pdf", sha256="hash_0", size_bytes=100),
            ],
        )
        self._save_meal(manager, meal_a)

        with (
            patch("src.meal.build_index_from_chunks") as mock_build_index,
            patch("src.meal.build_chunks_if_needed"),
            patch("src.sampler.count_pdf_pages", return_value=10),
        ):
            mock_build_index.return_value = MagicMock()

            result = manager.merge_meals(["meal_a"], name="merged_meal")

        assert result is not None
        assert result.name == "merged_meal"


class TestExtendMeal:
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

    def test_extend_meal_source_not_found(self, temp_dirs):
        manager = MealManager(temp_dirs)
        with pytest.raises(MealError, match="Source meal .* does not exist"):
            manager.extend_meal("nonexistent", ["new.pdf"])

    def test_extend_meal_invalid_name(self, temp_dirs):
        manager = MealManager(temp_dirs)
        meal = self._make_meal_config(name="source_meal")
        self._save_meal(manager, meal)

        with pytest.raises(MealError, match="Invalid meal name"):
            manager.extend_meal("source_meal", ["new.pdf"], name="invalid name")

    def test_extend_meal_duplicate_name(self, temp_dirs):
        manager = MealManager(temp_dirs)
        meal = self._make_meal_config(name="existing_meal")
        self._save_meal(manager, meal)

        with pytest.raises(MealError, match="already exists"):
            manager.extend_meal("existing_meal", ["new.pdf"], name="existing_meal")

    def test_extend_meal_pdf_not_found(self, temp_dirs):
        manager = MealManager(temp_dirs)
        meal = self._make_meal_config(name="source_meal")
        self._save_meal(manager, meal)

        with pytest.raises(MealError, match="PDF file does not exist"):
            manager.extend_meal("source_meal", ["nonexistent.pdf"])

    def test_extend_meal_all_pdfs_already_exist(self, temp_dirs):
        manager = MealManager(temp_dirs)
        pdf_path = Path(temp_dirs["parser"]["input_dir"]) / "reports" / "report_0.pdf"
        sha256 = compute_file_sha256(pdf_path)

        meal = self._make_meal_config(
            name="source_meal",
            pdf_files=[
                MealFile(
                    path="reports/report_0.pdf",
                    sha256=sha256,
                    size_bytes=pdf_path.stat().st_size,
                )
            ],
        )
        self._save_meal(manager, meal)

        with pytest.raises(MealError, match="No new PDF files to add"):
            manager.extend_meal("source_meal", ["reports/report_0.pdf"])

    def test_extend_meal_success(self, temp_dirs):
        from unittest.mock import patch

        manager = MealManager(temp_dirs)

        pdf_path_0 = Path(temp_dirs["parser"]["input_dir"]) / "reports" / "report_0.pdf"
        sha256_0 = compute_file_sha256(pdf_path_0)

        source_meal = self._make_meal_config(
            name="source_meal",
            pdf_files=[
                MealFile(
                    path="reports/report_0.pdf",
                    sha256=sha256_0,
                    size_bytes=pdf_path_0.stat().st_size,
                )
            ],
        )
        self._save_meal(manager, source_meal)

        with (
            patch.object(manager, "_parse_pdfs_with_registry") as mock_parse,
            patch("src.meal.build_chunks_if_needed") as mock_chunk,
            patch("src.meal.build_index_from_chunks") as mock_index,
        ):
            result = manager.extend_meal(
                "source_meal", ["reports/report_1.pdf"], name="extended_meal"
            )

            assert result.name == "extended_meal"
            assert len(result.pdf_files) == 2
            assert result.composition["type"] == "extended"
            assert result.composition["base_meal"] == "source_meal"
            assert "reports/report_1.pdf" in result.composition["added_files"]
            assert "skipped_files" not in result.composition

            mock_parse.assert_called_once()
            mock_chunk.assert_called_once()
            mock_index.assert_called_once()

    def test_extend_meal_skips_existing_pdf(self, temp_dirs):
        from unittest.mock import patch

        manager = MealManager(temp_dirs)

        pdf_path_0 = Path(temp_dirs["parser"]["input_dir"]) / "reports" / "report_0.pdf"
        sha256_0 = compute_file_sha256(pdf_path_0)

        source_meal = self._make_meal_config(
            name="source_meal",
            pdf_files=[
                MealFile(
                    path="reports/report_0.pdf",
                    sha256=sha256_0,
                    size_bytes=pdf_path_0.stat().st_size,
                )
            ],
        )
        self._save_meal(manager, source_meal)

        with (
            patch.object(manager, "_parse_pdfs_with_registry") as mock_parse,
            patch("src.meal.build_chunks_if_needed"),
            patch("src.meal.build_index_from_chunks"),
        ):
            result = manager.extend_meal(
                "source_meal",
                ["reports/report_0.pdf", "reports/report_1.pdf"],
                name="extended_meal",
            )

            assert len(result.pdf_files) == 2
            assert "reports/report_0.pdf" in result.composition["skipped_files"]
            assert "reports/report_1.pdf" in result.composition["added_files"]

            mock_parse.assert_called_once()

    def test_extend_meal_composition_metadata(self, temp_dirs):
        from unittest.mock import patch

        manager = MealManager(temp_dirs)

        pdf_path_0 = Path(temp_dirs["parser"]["input_dir"]) / "reports" / "report_0.pdf"
        sha256_0 = compute_file_sha256(pdf_path_0)

        source_meal = self._make_meal_config(
            name="source_meal",
            pdf_files=[
                MealFile(
                    path="reports/report_0.pdf",
                    sha256=sha256_0,
                    size_bytes=pdf_path_0.stat().st_size,
                )
            ],
        )
        self._save_meal(manager, source_meal)

        with (
            patch.object(manager, "_parse_pdfs_with_registry"),
            patch("src.meal.build_chunks_if_needed"),
            patch("src.meal.build_index_from_chunks"),
        ):
            result = manager.extend_meal(
                "source_meal", ["reports/report_1.pdf"], name="extended_meal"
            )

            assert result.composition["type"] == "extended"
            assert result.composition["base_meal"] == "source_meal"
            assert result.composition["added_files"] == ["reports/report_1.pdf"]
            assert "created_at" in result.composition

    def test_extend_meal_copies_source_artifacts(self, temp_dirs):
        from unittest.mock import patch

        manager = MealManager(temp_dirs)

        pdf_path_0 = Path(temp_dirs["parser"]["input_dir"]) / "reports" / "report_0.pdf"
        sha256_0 = compute_file_sha256(pdf_path_0)

        source_meal = self._make_meal_config(
            name="source_meal",
            pdf_files=[
                MealFile(
                    path="reports/report_0.pdf",
                    sha256=sha256_0,
                    size_bytes=pdf_path_0.stat().st_size,
                )
            ],
        )
        self._save_meal(manager, source_meal)

        _, config_hashes = manager._build_config_snapshot_and_hashes()
        parser_hash = config_hashes["parser"]
        chunker_hash = config_hashes["chunker"]

        source_parsed_dir = manager.cache.get_parsed_dir(
            source_meal.data_id, parser_hash
        )
        source_parsed_dir.mkdir(parents=True, exist_ok=True)
        (source_parsed_dir / "report_0.md").write_text("# Source content")

        source_chunks_dir = manager.cache.get_chunks_dir(
            source_meal.data_id, chunker_hash
        )
        source_chunks_dir.mkdir(parents=True, exist_ok=True)
        (source_chunks_dir / "report_0.jsonl").write_text('{"chunk": "data"}')

        with (
            patch.object(manager, "_parse_pdfs_with_registry"),
            patch("src.meal.build_chunks_if_needed"),
            patch("src.meal.build_index_from_chunks"),
        ):
            result = manager.extend_meal(
                "source_meal", ["reports/report_1.pdf"], name="extended_meal"
            )

            new_parsed_dir = manager.cache.get_parsed_dir(result.data_id, parser_hash)
            new_chunks_dir = manager.cache.get_chunks_dir(result.data_id, chunker_hash)

            assert (new_parsed_dir / "report_0.md").exists()
            assert (new_chunks_dir / "report_0.jsonl").exists()

    def test_extend_meal_absolute_path(self, temp_dirs):
        from unittest.mock import patch

        manager = MealManager(temp_dirs)

        pdf_path_0 = Path(temp_dirs["parser"]["input_dir"]) / "reports" / "report_0.pdf"
        sha256_0 = compute_file_sha256(pdf_path_0)

        source_meal = self._make_meal_config(
            name="source_meal",
            pdf_files=[
                MealFile(
                    path="reports/report_0.pdf",
                    sha256=sha256_0,
                    size_bytes=pdf_path_0.stat().st_size,
                )
            ],
        )
        self._save_meal(manager, source_meal)

        pdf_path_1 = Path(temp_dirs["parser"]["input_dir"]) / "reports" / "report_1.pdf"

        with (
            patch.object(manager, "_parse_pdfs_with_registry"),
            patch("src.meal.build_chunks_if_needed"),
            patch("src.meal.build_index_from_chunks"),
        ):
            result = manager.extend_meal(
                "source_meal", [pdf_path_1], name="extended_meal"
            )

            assert len(result.pdf_files) == 2
            assert result.pdf_files[1].path == "reports/report_1.pdf"

    def test_extend_meal_path_object(self, temp_dirs):
        from pathlib import Path as P
        from unittest.mock import patch

        manager = MealManager(temp_dirs)

        pdf_path_0 = Path(temp_dirs["parser"]["input_dir"]) / "reports" / "report_0.pdf"
        sha256_0 = compute_file_sha256(pdf_path_0)

        source_meal = self._make_meal_config(
            name="source_meal",
            pdf_files=[
                MealFile(
                    path="reports/report_0.pdf",
                    sha256=sha256_0,
                    size_bytes=pdf_path_0.stat().st_size,
                )
            ],
        )
        self._save_meal(manager, source_meal)

        with (
            patch.object(manager, "_parse_pdfs_with_registry"),
            patch("src.meal.build_chunks_if_needed"),
            patch("src.meal.build_index_from_chunks"),
        ):
            result = manager.extend_meal(
                "source_meal", [P("reports/report_1.pdf")], name="extended_meal"
            )

            assert len(result.pdf_files) == 2

    def test_extend_meal_generates_timestamp_name(self, temp_dirs):
        from unittest.mock import patch

        manager = MealManager(temp_dirs)

        pdf_path_0 = Path(temp_dirs["parser"]["input_dir"]) / "reports" / "report_0.pdf"
        sha256_0 = compute_file_sha256(pdf_path_0)

        source_meal = self._make_meal_config(
            name="source_meal",
            pdf_files=[
                MealFile(
                    path="reports/report_0.pdf",
                    sha256=sha256_0,
                    size_bytes=pdf_path_0.stat().st_size,
                )
            ],
        )
        self._save_meal(manager, source_meal)

        with (
            patch.object(manager, "_parse_pdfs_with_registry"),
            patch("src.meal.build_chunks_if_needed"),
            patch("src.meal.build_index_from_chunks"),
        ):
            result = manager.extend_meal("source_meal", ["reports/report_1.pdf"])

            assert result.name.startswith("meal_")


class TestInferEquivalenceGroups:
    def test_different_dirs_same_stem_different_groups(self):
        pdf_files = [
            "annual_reports/2023/云南白药/2023年年度报告.pdf",
            "annual_reports/2023/隆基绿能/2023年年度报告.pdf",
        ]
        groups = _infer_equivalence_groups(pdf_files)
        assert "云南白药/2023年年度报告" in groups
        assert "隆基绿能/2023年年度报告" in groups
        assert len(groups) == 2
        assert groups["云南白药/2023年年度报告"] == [
            "annual_reports/2023/云南白药/2023年年度报告.pdf"
        ]
        assert groups["隆基绿能/2023年年度报告"] == [
            "annual_reports/2023/隆基绿能/2023年年度报告.pdf"
        ]

    def test_same_dir_suffix_strip_same_group(self):
        pdf_files = [
            "annual_reports/2023/云南白药/2023年年度报告.pdf",
            "annual_reports/2023/云南白药/2023年年度报告_英文版_.pdf",
            "annual_reports/2023/云南白药/2023年年度报告摘要.pdf",
        ]
        groups = _infer_equivalence_groups(pdf_files)
        assert "云南白药/2023年年度报告" in groups
        assert len(groups) == 1
        assert len(groups["云南白药/2023年年度报告"]) == 3

    def test_suffix_stripping_with_parent_dir(self):
        pdf_files = [
            "annual_reports/2023/云南白药/2023年年度报告_修订版_.pdf",
        ]
        groups = _infer_equivalence_groups(pdf_files)
        assert "云南白药/2023年年度报告" in groups

    def test_research_reports_each_own_group(self):
        pdf_files = [
            "research_reports/2026现代女性精力管理现状报告.pdf",
            "research_reports/2025新能源行业白皮书.pdf",
        ]
        groups = _infer_equivalence_groups(pdf_files)
        assert "research_reports/2026现代女性精力管理现状报告" in groups
        assert "research_reports/2025新能源行业白皮书" in groups
        assert len(groups) == 2

    def test_research_reports_suffix_strip(self):
        pdf_files = [
            "research_reports/2026现代女性精力管理现状报告.pdf",
            "research_reports/2026现代女性精力管理现状报告摘要.pdf",
        ]
        groups = _infer_equivalence_groups(pdf_files)
        assert "research_reports/2026现代女性精力管理现状报告" in groups
        assert len(groups) == 1
        assert len(groups["research_reports/2026现代女性精力管理现状报告"]) == 2

    def test_posix_paths_in_output(self):
        pdf_files = [
            "annual_reports/2023/云南白药/2023年年度报告.pdf",
        ]
        groups = _infer_equivalence_groups(pdf_files)
        paths = groups["云南白药/2023年年度报告"]
        assert all("\\" not in p for p in paths)

    def test_no_parent_dir_uses_stem_only(self):
        pdf_files = [
            "2023年年度报告.pdf",
        ]
        groups = _infer_equivalence_groups(pdf_files)
        assert "2023年年度报告" in groups

    def test_empty_input(self):
        groups = _infer_equivalence_groups([])
        assert groups == {}

    def test_mixed_annual_and_research_reports(self):
        pdf_files = [
            "annual_reports/2023/云南白药/2023年年度报告.pdf",
            "annual_reports/2023/云南白药/2023年年度报告_英文版_.pdf",
            "annual_reports/2023/隆基绿能/2023年年度报告.pdf",
            "research_reports/2026现代女性精力管理现状报告.pdf",
        ]
        groups = _infer_equivalence_groups(pdf_files)
        assert len(groups) == 3
        assert "云南白药/2023年年度报告" in groups
        assert "隆基绿能/2023年年度报告" in groups
        assert "research_reports/2026现代女性精力管理现状报告" in groups
        assert len(groups["云南白药/2023年年度报告"]) == 2


def test_chunker_config_hash_includes_cross_page_overlap():
    config_base = {
        "strategy": "fixed",
        "chunk_size": 512,
        "chunk_overlap": 0,
        "encoding": "cl100k_base",
    }
    config_with_overlap = {**config_base, "cross_page_overlap": 50}
    config_without_overlap = {**config_base, "cross_page_overlap": 0}
    hash_with = compute_chunker_config_hash(config_with_overlap)
    hash_without = compute_chunker_config_hash(config_without_overlap)
    assert hash_with != hash_without


def test_embedding_config_hash_includes_dimension():
    config_base = {"model_name": "BAAI/bge-large-zh-v1.5"}
    config_with_dim = {**config_base, "dimension": 1024}
    config_without_dim = {**config_base}
    hash_with = compute_embedding_config_hash(config_with_dim)
    hash_without = compute_embedding_config_hash(config_without_dim)
    assert hash_with != hash_without


def test_parser_config_hash_includes_version():
    config_a = {"algorithm": "pymupdf4llm", "options": {}}
    config_b = {"algorithm": "pymupdf4llm", "options": {}}
    hash_a = compute_parser_config_hash(config_a)
    hash_b = compute_parser_config_hash(config_b)
    assert hash_a == hash_b
    config_c = {"algorithm": "nonexistent_parser", "options": {}}
    hash_c = compute_parser_config_hash(config_c)
    assert hash_a != hash_c


def test_short_id_length():
    cache = ArtifactCache(artifacts_dir=Path("/tmp/test_artifacts"), raw_dir=None)
    data_id = "a" * 64
    group_dir = cache.get_artifact_group_dir(data_id)
    assert group_dir.name == data_id[:16]


def test_partial_parse_manifest_consistency(tmp_path):
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    artifacts_dir = tmp_path / "artifacts"

    cache = ArtifactCache(artifacts_dir=artifacts_dir, raw_dir=raw_dir)

    data_id = "a" * 64
    manifest = {
        "data_id": data_id,
        "pdf_count": 3,
        "pdf_inventory": {"success1.pdf": "sha256_1", "success2.pdf": "sha256_2"},
        "failed_inventory": {"failed1.pdf": "sha256_3"},
    }
    cache.save_manifest(data_id, manifest)

    loaded = cache.load_manifest(data_id)
    assert "pdf_inventory" in loaded
    assert "failed_inventory" in loaded
    assert len(loaded["pdf_inventory"]) == 2
    assert len(loaded["failed_inventory"]) == 1
    assert "failed1.pdf" not in loaded["pdf_inventory"]
    assert "failed1.pdf" in loaded["failed_inventory"]


def test_is_full_parsed_valid_with_failed_inventory(tmp_path):
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    artifacts_dir = tmp_path / "artifacts"

    cache = ArtifactCache(artifacts_dir=artifacts_dir, raw_dir=raw_dir)

    pdf_file = raw_dir / "test.pdf"
    pdf_file.write_bytes(b"%PDF-1.4 fake content")
    sha = compute_file_sha256(pdf_file)

    data_id = compute_data_id([MealFile(path="test.pdf", sha256=sha, size_bytes=100)])

    parsed_dir = cache.get_parsed_dir(data_id, "abc12345")
    parsed_dir.mkdir(parents=True)
    (parsed_dir / "test.md").write_text("content", encoding="utf-8")

    manifest_with_failed = {
        "pdf_inventory": {"test.pdf": sha},
        "failed_inventory": {"other.pdf": "sha_other"},
    }
    cache.save_manifest(data_id, manifest_with_failed)
    assert cache.is_full_parsed_valid("abc12345") is False

    manifest_no_failed = {
        "pdf_inventory": {"test.pdf": sha},
    }
    cache.save_manifest(data_id, manifest_no_failed)
    assert cache.is_full_parsed_valid("abc12345") is True
