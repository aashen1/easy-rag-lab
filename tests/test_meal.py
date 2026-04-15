import json
import os
import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.meal import (
    MealConfig,
    MealFile,
    MealManager,
    MealStatus,
    compute_file_sha256,
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
            "uuid": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
            "name": "test_meal",
            "created_at": "2026-04-16T14:30:00",
            "sampling_config": {"mode": "count", "value": 10, "seed": 42},
            "collection_name": "m_a1b2c3d4",
            "pdf_files": [
                MealFile(path="test.pdf", sha256="abc123", size_bytes=1024)
            ],
            "stats": {"total_pdfs": 1, "total_pages": 50, "total_chunks": 200},
        }
        defaults.update(overrides)
        return MealConfig(**defaults)

    def test_to_dict(self):
        config = self._make_config()
        d = config.to_dict()
        assert d["uuid"] == "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        assert d["name"] == "test_meal"
        assert len(d["pdf_files"]) == 1
        assert d["pdf_files"][0]["path"] == "test.pdf"

    def test_from_dict(self):
        data = {
            "uuid": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
            "name": "test_meal",
            "created_at": "2026-04-16T14:30:00",
            "sampling_config": {"mode": "count", "value": 10, "seed": 42},
            "collection_name": "m_a1b2c3d4",
            "pdf_files": [
                {"path": "test.pdf", "sha256": "abc123", "size_bytes": 1024}
            ],
            "stats": {"total_pdfs": 1, "total_pages": 50, "total_chunks": 200},
        }
        config = MealConfig.from_dict(data)
        assert config.uuid == "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        assert config.name == "test_meal"
        assert len(config.pdf_files) == 1
        assert isinstance(config.pdf_files[0], MealFile)
        assert config.pdf_files[0].path == "test.pdf"

    def test_roundtrip(self):
        config = self._make_config()
        d = config.to_dict()
        config2 = MealConfig.from_dict(d)
        assert config.uuid == config2.uuid
        assert config.name == config2.name
        assert len(config.pdf_files) == len(config2.pdf_files)


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
        result = generate_collection_name("a1b2c3d4-e5f6-7890-abcd-ef1234567890")
        assert result == "m_a1b2c3d4"

    def test_custom_prefix(self):
        result = generate_collection_name(
            "a1b2c3d4-e5f6-7890-abcd-ef1234567890", prefix="meal_"
        )
        assert result == "meal_a1b2c3d4"


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
        }
        return config

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
        meal_dir = manager.get_meal_dir("test_meal")
        meal_dir.mkdir()
        (meal_dir / "test_sets").mkdir()

        meal = MealConfig(
            uuid="test-uuid-1234",
            name="test_meal",
            created_at="2026-04-16T14:30:00",
            sampling_config={"mode": "count", "value": 3, "seed": 42},
            collection_name="m_test-uu",
            pdf_files=[
                MealFile(path="reports/report_0.pdf", sha256="abc", size_bytes=100)
            ],
            stats={"total_pdfs": 1, "total_pages": 50, "total_chunks": 200},
        )

        manifest_path = meal_dir / "manifest.json"
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(meal.to_dict(), f, ensure_ascii=False, indent=2)

        loaded = manager.load_meal("test_meal")
        assert loaded.uuid == "test-uuid-1234"
        assert loaded.name == "test_meal"
        assert len(loaded.pdf_files) == 1
        assert loaded.pdf_files[0].path == "reports/report_0.pdf"

    def test_check_meal_status_available(self, temp_dirs):
        manager = MealManager(temp_dirs)
        meal_dir = manager.get_meal_dir("avail_meal")
        meal_dir.mkdir()
        (meal_dir / "test_sets").mkdir()

        pdf_path = Path(temp_dirs["parser"]["input_dir"]) / "reports" / "report_0.pdf"
        sha256 = compute_file_sha256(pdf_path)

        meal = MealConfig(
            uuid="avail-uuid-1234",
            name="avail_meal",
            created_at="2026-04-16T14:30:00",
            sampling_config={"mode": "count", "value": 1, "seed": 42},
            collection_name="m_avail-uu",
            pdf_files=[
                MealFile(
                    path="reports/report_0.pdf",
                    sha256=sha256,
                    size_bytes=pdf_path.stat().st_size,
                )
            ],
            stats={"total_pdfs": 1, "total_pages": 50, "total_chunks": 200},
        )

        with open(meal_dir / "manifest.json", "w", encoding="utf-8") as f:
            json.dump(meal.to_dict(), f, ensure_ascii=False, indent=2)

        status, issues = manager.check_meal_status("avail_meal")
        assert status == MealStatus.AVAILABLE
        assert issues == []

    def test_check_meal_status_missing(self, temp_dirs):
        manager = MealManager(temp_dirs)
        meal_dir = manager.get_meal_dir("missing_meal")
        meal_dir.mkdir()
        (meal_dir / "test_sets").mkdir()

        meal = MealConfig(
            uuid="missing-uuid-1234",
            name="missing_meal",
            created_at="2026-04-16T14:30:00",
            sampling_config={"mode": "count", "value": 1, "seed": 42},
            collection_name="m_missing-",
            pdf_files=[
                MealFile(
                    path="reports/nonexistent.pdf",
                    sha256="abc123",
                    size_bytes=100,
                )
            ],
            stats={"total_pdfs": 1, "total_pages": 50, "total_chunks": 200},
        )

        with open(meal_dir / "manifest.json", "w", encoding="utf-8") as f:
            json.dump(meal.to_dict(), f, ensure_ascii=False, indent=2)

        status, issues = manager.check_meal_status("missing_meal")
        assert status == MealStatus.FILES_MISSING
        assert len(issues) == 1

    def test_check_meal_status_changed(self, temp_dirs):
        manager = MealManager(temp_dirs)
        meal_dir = manager.get_meal_dir("changed_meal")
        meal_dir.mkdir()
        (meal_dir / "test_sets").mkdir()

        meal = MealConfig(
            uuid="changed-uuid-1234",
            name="changed_meal",
            created_at="2026-04-16T14:30:00",
            sampling_config={"mode": "count", "value": 1, "seed": 42},
            collection_name="m_changed-",
            pdf_files=[
                MealFile(
                    path="reports/report_0.pdf",
                    sha256="wrong_hash_value",
                    size_bytes=999,
                )
            ],
            stats={"total_pdfs": 1, "total_pages": 50, "total_chunks": 200},
        )

        with open(meal_dir / "manifest.json", "w", encoding="utf-8") as f:
            json.dump(meal.to_dict(), f, ensure_ascii=False, indent=2)

        status, issues = manager.check_meal_status("changed_meal")
        assert status == MealStatus.FILES_CHANGED
        assert len(issues) == 1

    def test_rename_meal(self, temp_dirs):
        manager = MealManager(temp_dirs)
        meal_dir = manager.get_meal_dir("old_name")
        meal_dir.mkdir()
        (meal_dir / "test_sets").mkdir()

        meal = MealConfig(
            uuid="rename-uuid-1234",
            name="old_name",
            created_at="2026-04-16T14:30:00",
            sampling_config=None,
            collection_name="m_rename-u",
            pdf_files=[],
            stats={"total_pdfs": 0, "total_pages": 0, "total_chunks": 0},
        )

        with open(meal_dir / "manifest.json", "w", encoding="utf-8") as f:
            json.dump(meal.to_dict(), f, ensure_ascii=False, indent=2)

        result = manager.rename_meal("old_name", "new_name")
        assert result.name == "new_name"
        assert result.uuid == "rename-uuid-1234"
        assert not manager.meal_exists("old_name")
        assert manager.meal_exists("new_name")

    def test_rename_meal_invalid_name(self, temp_dirs):
        manager = MealManager(temp_dirs)
        meal_dir = manager.get_meal_dir("valid_name")
        meal_dir.mkdir()
        (meal_dir / "test_sets").mkdir()

        meal = MealConfig(
            uuid="rename-uuid-1234",
            name="valid_name",
            created_at="2026-04-16T14:30:00",
            sampling_config=None,
            collection_name="m_rename-u",
            pdf_files=[],
            stats={"total_pdfs": 0, "total_pages": 0, "total_chunks": 0},
        )

        with open(meal_dir / "manifest.json", "w", encoding="utf-8") as f:
            json.dump(meal.to_dict(), f, ensure_ascii=False, indent=2)

        with pytest.raises(ValueError, match="Invalid meal name"):
            manager.rename_meal("valid_name", "invalid name")

    def test_rename_meal_duplicate_name(self, temp_dirs):
        manager = MealManager(temp_dirs)
        for name in ["meal_a", "meal_b"]:
            meal_dir = manager.get_meal_dir(name)
            meal_dir.mkdir()
            (meal_dir / "test_sets").mkdir()
            meal = MealConfig(
                uuid=f"{name}-uuid",
                name=name,
                created_at="2026-04-16T14:30:00",
                sampling_config=None,
                collection_name=f"m_{name[:8]}",
                pdf_files=[],
                stats={"total_pdfs": 0, "total_pages": 0, "total_chunks": 0},
            )
            with open(meal_dir / "manifest.json", "w", encoding="utf-8") as f:
                json.dump(meal.to_dict(), f, ensure_ascii=False, indent=2)

        with pytest.raises(ValueError, match="already exists"):
            manager.rename_meal("meal_a", "meal_b")

    def test_list_meals(self, temp_dirs):
        manager = MealManager(temp_dirs)
        for i in range(3):
            name = f"meal_{i}"
            meal_dir = manager.get_meal_dir(name)
            meal_dir.mkdir()
            (meal_dir / "test_sets").mkdir()
            meal = MealConfig(
                uuid=f"uuid-{i}",
                name=name,
                created_at="2026-04-16T14:30:00",
                sampling_config=None,
                collection_name=f"m_uuid-{i}",
                pdf_files=[],
                stats={"total_pdfs": 0, "total_pages": 0, "total_chunks": 0},
            )
            with open(meal_dir / "manifest.json", "w", encoding="utf-8") as f:
                json.dump(meal.to_dict(), f, ensure_ascii=False, indent=2)

        meals = manager.list_meals()
        assert len(meals) == 3
        names = {m.name for m in meals}
        assert names == {"meal_0", "meal_1", "meal_2"}

    def test_load_meal_by_uuid(self, temp_dirs):
        manager = MealManager(temp_dirs)
        meal_dir = manager.get_meal_dir("uuid_test")
        meal_dir.mkdir()
        (meal_dir / "test_sets").mkdir()
        meal = MealConfig(
            uuid="unique-uuid-5678",
            name="uuid_test",
            created_at="2026-04-16T14:30:00",
            sampling_config=None,
            collection_name="m_unique-u",
            pdf_files=[],
            stats={"total_pdfs": 0, "total_pages": 0, "total_chunks": 0},
        )
        with open(meal_dir / "manifest.json", "w", encoding="utf-8") as f:
            json.dump(meal.to_dict(), f, ensure_ascii=False, indent=2)

        found = manager.load_meal_by_uuid("unique-uuid-5678")
        assert found is not None
        assert found.name == "uuid_test"

        not_found = manager.load_meal_by_uuid("nonexistent-uuid")
        assert not_found is None

    def test_copy_meal(self, temp_dirs):
        manager = MealManager(temp_dirs)
        meal_dir = manager.get_meal_dir("source_meal")
        meal_dir.mkdir()
        (meal_dir / "test_sets").mkdir()
        meal = MealConfig(
            uuid="source-uuid-1234",
            name="source_meal",
            created_at="2026-04-16T14:30:00",
            sampling_config={"mode": "count", "value": 5, "seed": 42},
            collection_name="m_source-u",
            pdf_files=[
                MealFile(path="test.pdf", sha256="abc", size_bytes=100)
            ],
            stats={"total_pdfs": 1, "total_pages": 50, "total_chunks": 200},
        )
        with open(meal_dir / "manifest.json", "w", encoding="utf-8") as f:
            json.dump(meal.to_dict(), f, ensure_ascii=False, indent=2)

        result = manager.copy_meal("source_meal", "target_meal")
        assert result.name == "target_meal"
        assert result.uuid != "source-uuid-1234"
        assert result.collection_name == "m_source-u"
        assert manager.meal_exists("source_meal")
        assert manager.meal_exists("target_meal")

    def test_copy_meal_duplicate_name(self, temp_dirs):
        manager = MealManager(temp_dirs)
        meal_dir = manager.get_meal_dir("existing")
        meal_dir.mkdir()
        (meal_dir / "test_sets").mkdir()
        meal = MealConfig(
            uuid="existing-uuid",
            name="existing",
            created_at="2026-04-16T14:30:00",
            sampling_config=None,
            collection_name="m_existing",
            pdf_files=[],
            stats={"total_pdfs": 0, "total_pages": 0, "total_chunks": 0},
        )
        with open(meal_dir / "manifest.json", "w", encoding="utf-8") as f:
            json.dump(meal.to_dict(), f, ensure_ascii=False, indent=2)

        with pytest.raises(ValueError, match="already exists"):
            manager.copy_meal("existing", "existing")
