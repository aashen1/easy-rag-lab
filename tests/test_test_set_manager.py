import json
from pathlib import Path

import pytest

from src.exceptions import TestSetError
from src.meal import MealConfig, MealFile
from src.test_set_manager import TestSetManager, TestSetMetadata


def _make_meal_config(data_id: str = "abc123", pdf_paths: list = None) -> MealConfig:
    if pdf_paths is None:
        pdf_paths = ["reports/report_0.pdf", "reports/report_1.pdf"]
    pdf_files = [
        MealFile(path=p, sha256=f"hash_{i}", size_bytes=100)
        for i, p in enumerate(pdf_paths)
    ]
    return MealConfig(
        data_id=data_id,
        name="test_meal",
        created_at="2026-04-20T10:00:00",
        sampling_config={"mode": "count", "value": 2},
        collection_name="m_test123456",
        pdf_files=pdf_files,
    )


class TestTestSetMetadata:
    def test_creation_defaults(self):
        meta = TestSetMetadata(
            name="test_set_1",
            meal_id="abc123",
            created_at="2026-04-20T10:00:00",
            updated_at="2026-04-20T10:00:00",
        )
        assert meta.name == "test_set_1"
        assert meta.meal_id == "abc123"
        assert meta.generation is None
        assert meta.user_defined is False
        assert meta.invalid_policy is None
        assert meta.audit_log == []
        assert meta.suppress_warnings is False
        assert meta.composition == {}

    def test_creation_with_all_fields(self):
        meta = TestSetMetadata(
            name="custom_set",
            meal_id="def456",
            created_at="2026-04-20T10:00:00",
            updated_at="2026-04-20T11:00:00",
            generation={"strategy": "random", "num_questions": 10, "seed": 42},
            user_defined=True,
            invalid_policy="trim",
            audit_log=[{"action": "created", "timestamp": "2026-04-20T10:00:00"}],
            suppress_warnings=True,
        )
        assert meta.user_defined is True
        assert meta.invalid_policy == "trim"
        assert meta.generation["strategy"] == "random"
        assert len(meta.audit_log) == 1
        assert meta.suppress_warnings is True
        assert meta.composition == {}

    def test_to_dict(self):
        meta = TestSetMetadata(
            name="test_set_1",
            meal_id="abc123",
            created_at="2026-04-20T10:00:00",
            updated_at="2026-04-20T10:00:00",
            generation={"strategy": "random", "num_questions": 5},
        )
        d = meta.to_dict()
        assert d["name"] == "test_set_1"
        assert d["meal_id"] == "abc123"
        assert d["generation"] == {"strategy": "random", "num_questions": 5}
        assert d["user_defined"] is False
        assert d["audit_log"] == []
        assert d["composition"] == {}

    def test_from_dict(self):
        data = {
            "name": "test_set_1",
            "meal_id": "abc123",
            "created_at": "2026-04-20T10:00:00",
            "updated_at": "2026-04-20T10:00:00",
            "generation": {"strategy": "random", "num_questions": 5},
            "user_defined": True,
            "invalid_policy": "immutable",
            "audit_log": [{"action": "created"}],
            "suppress_warnings": True,
        }
        meta = TestSetMetadata.from_dict(data)
        assert meta.name == "test_set_1"
        assert meta.meal_id == "abc123"
        assert meta.user_defined is True
        assert meta.invalid_policy == "immutable"
        assert meta.generation["strategy"] == "random"
        assert len(meta.audit_log) == 1
        assert meta.suppress_warnings is True
        assert meta.composition == {}

    def test_from_dict_defaults(self):
        data = {
            "name": "minimal",
            "meal_id": "xyz",
            "created_at": "2026-04-20T10:00:00",
            "updated_at": "2026-04-20T10:00:00",
        }
        meta = TestSetMetadata.from_dict(data)
        assert meta.generation is None
        assert meta.user_defined is False
        assert meta.invalid_policy is None
        assert meta.audit_log == []
        assert meta.suppress_warnings is False
        assert meta.composition == {}

    def test_roundtrip(self):
        meta = TestSetMetadata(
            name="roundtrip",
            meal_id="rt123",
            created_at="2026-04-20T10:00:00",
            updated_at="2026-04-20T11:00:00",
            generation={"strategy": "document_level", "num_questions": 20, "seed": 7},
            user_defined=False,
            audit_log=[{"action": "created", "ts": "2026-04-20T10:00:00"}],
        )
        d = meta.to_dict()
        meta2 = TestSetMetadata.from_dict(d)
        assert meta.name == meta2.name
        assert meta.meal_id == meta2.meal_id
        assert meta.generation == meta2.generation
        assert meta.user_defined == meta2.user_defined
        assert meta.audit_log == meta2.audit_log

    def test_composition_field_default(self):
        meta = TestSetMetadata(
            name="test_composition",
            meal_id="abc123",
            created_at="2026-04-20T10:00:00",
            updated_at="2026-04-20T10:00:00",
        )
        assert meta.composition == {}

    def test_composition_field_with_data(self):
        composition_data = {
            "type": "merged",
            "sources": [
                {"meal": "A", "test_set": "TA"},
                {"meal": "B", "test_set": "TB"},
            ],
            "dedup_count": 5,
            "original_count": 25,
            "final_count": 20,
        }
        meta = TestSetMetadata(
            name="merged_set",
            meal_id="abc123",
            created_at="2026-04-20T10:00:00",
            updated_at="2026-04-20T10:00:00",
            composition=composition_data,
        )
        assert meta.composition["type"] == "merged"
        assert len(meta.composition["sources"]) == 2
        assert meta.composition["dedup_count"] == 5
        assert meta.composition["original_count"] == 25
        assert meta.composition["final_count"] == 20

    def test_composition_serialization(self):
        composition_data = {
            "type": "generated",
            "sources": [],
            "dedup_count": 0,
            "original_count": 20,
            "final_count": 20,
        }
        meta = TestSetMetadata(
            name="gen_set",
            meal_id="abc123",
            created_at="2026-04-20T10:00:00",
            updated_at="2026-04-20T10:00:00",
            composition=composition_data,
        )
        d = meta.to_dict()
        assert "composition" in d
        assert d["composition"]["type"] == "generated"
        assert d["composition"]["original_count"] == 20

    def test_composition_deserialization(self):
        data = {
            "name": "test_set_1",
            "meal_id": "abc123",
            "created_at": "2026-04-20T10:00:00",
            "updated_at": "2026-04-20T10:00:00",
            "composition": {
                "type": "user_defined",
                "sources": [{"meal": "manual", "test_set": "custom"}],
                "dedup_count": 0,
                "original_count": 10,
                "final_count": 10,
            },
        }
        meta = TestSetMetadata.from_dict(data)
        assert meta.composition["type"] == "user_defined"
        assert len(meta.composition["sources"]) == 1

    def test_composition_backward_compatibility(self):
        data = {
            "name": "old_set",
            "meal_id": "xyz",
            "created_at": "2026-04-20T10:00:00",
            "updated_at": "2026-04-20T10:00:00",
        }
        meta = TestSetMetadata.from_dict(data)
        assert meta.composition == {}

    def test_composition_roundtrip(self):
        composition_data = {
            "type": "merged",
            "sources": [{"meal": "A", "test_set": "TA"}],
            "dedup_count": 3,
            "original_count": 15,
            "final_count": 12,
        }
        meta = TestSetMetadata(
            name="roundtrip_comp",
            meal_id="rt123",
            created_at="2026-04-20T10:00:00",
            updated_at="2026-04-20T11:00:00",
            composition=composition_data,
        )
        d = meta.to_dict()
        meta2 = TestSetMetadata.from_dict(d)
        assert meta2.composition == composition_data
        assert meta2.composition["type"] == "merged"
        assert meta2.composition["dedup_count"] == 3


def _make_config(tmp_path: Path) -> dict:
    meals_dir = tmp_path / "meals"
    meals_dir.mkdir(exist_ok=True)
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir(exist_ok=True)
    parsed_dir = tmp_path / "parsed"
    parsed_dir.mkdir(exist_ok=True)
    chunks_dir = tmp_path / "chunks"
    chunks_dir.mkdir(exist_ok=True)
    vector_dir = tmp_path / "vector_store"
    vector_dir.mkdir(exist_ok=True)
    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir(exist_ok=True)

    return {
        "parser": {"input_dir": str(raw_dir), "output_dir": str(parsed_dir)},
        "chunker": {
            "input_dir": str(parsed_dir),
            "output_dir": str(chunks_dir),
            "chunk_size": 512,
            "chunk_overlap": 0,
        },
        "embedding": {"model_name": "BAAI/bge-large-zh-v1.5", "device": "cpu"},
        "vector_store": {
            "persist_dir": str(vector_dir),
            "collection_name": "test",
            "distance": "Cosine",
        },
        "meals": {"dir": str(meals_dir), "collection_prefix": "m_"},
        "artifacts": {"dir": str(artifacts_dir)},
    }


def _create_meal_dir(config: dict, meal_name: str) -> Path:
    meals_dir = Path(config["meals"]["dir"])
    meal_dir = meals_dir / meal_name
    meal_dir.mkdir(parents=True, exist_ok=True)
    test_sets_dir = meal_dir / "test_sets"
    test_sets_dir.mkdir(exist_ok=True)
    return meal_dir


def _make_test_set_data(name: str, meal_id: str = "abc123") -> dict:
    return {
        "metadata": {
            "name": name,
            "meal_id": meal_id,
            "created_at": "2026-04-20T10:00:00",
            "updated_at": "2026-04-20T10:00:00",
            "generation": {"strategy": "random", "num_questions": 5},
            "user_defined": False,
            "audit_log": [],
        },
        "questions": [
            {"id": 1, "question": "What is revenue?", "answer": "1B"},
        ],
    }


class TestTestSetManager:
    @pytest.fixture
    def env(self, tmp_path):
        config = _make_config(tmp_path)
        manager = TestSetManager(config)
        return manager, config

    def test_get_test_sets_dir(self, env):
        manager, config = env
        _create_meal_dir(config, "my_meal")
        result = manager.get_test_sets_dir("my_meal")
        expected = Path(config["meals"]["dir"]) / "my_meal" / "test_sets"
        assert result == expected

    def test_save_test_set(self, env):
        manager, config = env
        _create_meal_dir(config, "my_meal")
        data = _make_test_set_data("set_a")
        path = manager.save_test_set("my_meal", data)
        assert path.exists()
        assert path.name == "set_a.json"
        with open(path, encoding="utf-8") as f:
            loaded = json.load(f)
        assert loaded["metadata"]["name"] == "set_a"

    def test_save_test_set_creates_dir(self, env):
        manager, config = env
        meals_dir = Path(config["meals"]["dir"])
        meal_dir = meals_dir / "new_meal"
        meal_dir.mkdir(parents=True)
        data = _make_test_set_data("set_b")
        path = manager.save_test_set("new_meal", data)
        assert path.exists()
        assert (meal_dir / "test_sets").exists()

    def test_load_test_set(self, env):
        manager, config = env
        _create_meal_dir(config, "my_meal")
        data = _make_test_set_data("set_a")
        manager.save_test_set("my_meal", data)
        loaded = manager.load_test_set("my_meal", "set_a")
        assert loaded["metadata"]["name"] == "set_a"
        assert len(loaded["questions"]) == 1

    def test_load_test_set_not_found(self, env):
        manager, config = env
        _create_meal_dir(config, "my_meal")
        with pytest.raises(TestSetError):
            manager.load_test_set("my_meal", "nonexistent")

    def test_find_by_name(self, env):
        manager, config = env
        _create_meal_dir(config, "my_meal")
        data = _make_test_set_data("set_a")
        manager.save_test_set("my_meal", data)
        result = manager.find_by_name("my_meal", "set_a")
        assert result is not None
        assert result["metadata"]["name"] == "set_a"

    def test_find_by_name_not_found(self, env):
        manager, config = env
        _create_meal_dir(config, "my_meal")
        result = manager.find_by_name("my_meal", "nonexistent")
        assert result is None

    def test_find_by_name_excludes_archive(self, env):
        manager, config = env
        _create_meal_dir(config, "my_meal")
        test_sets_dir = Path(config["meals"]["dir"]) / "my_meal" / "test_sets"
        archive_file = test_sets_dir / "old_set.archive.20260420.json"
        with open(archive_file, "w", encoding="utf-8") as f:
            json.dump(_make_test_set_data("old_set"), f)
        result = manager.find_by_name("my_meal", "old_set.archive.20260420")
        assert result is None

    def test_list_test_sets(self, env):
        manager, config = env
        _create_meal_dir(config, "my_meal")
        for name in ["set_a", "set_b", "set_c"]:
            manager.save_test_set("my_meal", _make_test_set_data(name))
        result = manager.list_test_sets("my_meal")
        assert len(result) == 3
        names = {r["name"] for r in result}
        assert names == {"set_a", "set_b", "set_c"}

    def test_list_test_sets_empty(self, env):
        manager, config = env
        _create_meal_dir(config, "my_meal")
        result = manager.list_test_sets("my_meal")
        assert result == []

    def test_list_test_sets_no_dir(self, env):
        manager, config = env
        result = manager.list_test_sets("no_such_meal")
        assert result == []

    def test_list_test_sets_excludes_archive(self, env):
        manager, config = env
        _create_meal_dir(config, "my_meal")
        manager.save_test_set("my_meal", _make_test_set_data("active_set"))
        test_sets_dir = Path(config["meals"]["dir"]) / "my_meal" / "test_sets"
        archive_file = test_sets_dir / "archived.archive.20260420.json"
        with open(archive_file, "w", encoding="utf-8") as f:
            json.dump(_make_test_set_data("archived"), f)
        result = manager.list_test_sets("my_meal")
        assert len(result) == 1
        assert result[0]["name"] == "active_set"

    def test_delete_test_set(self, env):
        manager, config = env
        _create_meal_dir(config, "my_meal")
        manager.save_test_set("my_meal", _make_test_set_data("to_delete"))
        assert manager.test_set_exists("my_meal", "to_delete")
        manager.delete_test_set("my_meal", "to_delete")
        assert not manager.test_set_exists("my_meal", "to_delete")

    def test_delete_test_set_not_found(self, env):
        manager, config = env
        _create_meal_dir(config, "my_meal")
        with pytest.raises(TestSetError):
            manager.delete_test_set("my_meal", "nonexistent")

    def test_test_set_exists_true(self, env):
        manager, config = env
        _create_meal_dir(config, "my_meal")
        manager.save_test_set("my_meal", _make_test_set_data("exists"))
        assert manager.test_set_exists("my_meal", "exists") is True

    def test_test_set_exists_false(self, env):
        manager, config = env
        _create_meal_dir(config, "my_meal")
        assert manager.test_set_exists("my_meal", "nope") is False


class TestValidateTestSet:
    @pytest.fixture
    def env(self, tmp_path):
        config = _make_config(tmp_path)
        manager = TestSetManager(config)
        return manager, config

    def test_fast_path_meal_id_matches(self, env):
        manager, config = env
        meal_config = _make_meal_config(data_id="matching_id")
        test_set_data = {
            "metadata": {
                "name": "test_set",
                "meal_id": "matching_id",
                "created_at": "2026-04-20T10:00:00",
                "updated_at": "2026-04-20T10:00:00",
            },
            "questions": [
                {"id": 1, "question": "What?", "source_files": ["nonexistent.pdf"]},
            ],
        }
        is_valid, invalid = manager.validate_test_set(test_set_data, meal_config)
        assert is_valid is True
        assert invalid == []

    def test_slow_path_all_questions_valid(self, env):
        manager, config = env
        meal_config = _make_meal_config(
            data_id="current_meal",
            pdf_paths=["reports/report_0.pdf", "reports/report_1.pdf"],
        )
        test_set_data = {
            "metadata": {
                "name": "test_set",
                "meal_id": "different_meal",
                "created_at": "2026-04-20T10:00:00",
                "updated_at": "2026-04-20T10:00:00",
            },
            "questions": [
                {"id": 1, "question": "Q1", "source_files": ["reports/report_0.pdf"]},
                {"id": 2, "question": "Q2", "source_files": ["reports/report_1.pdf"]},
            ],
        }
        is_valid, invalid = manager.validate_test_set(test_set_data, meal_config)
        assert is_valid is True
        assert invalid == []

    def test_slow_path_some_questions_invalid(self, env):
        manager, config = env
        meal_config = _make_meal_config(
            data_id="current_meal",
            pdf_paths=["reports/report_0.pdf"],
        )
        test_set_data = {
            "metadata": {
                "name": "test_set",
                "meal_id": "different_meal",
                "created_at": "2026-04-20T10:00:00",
                "updated_at": "2026-04-20T10:00:00",
            },
            "questions": [
                {"id": 1, "question": "Q1", "source_files": ["reports/report_0.pdf"]},
                {"id": 2, "question": "Q2", "source_files": ["reports/report_1.pdf"]},
                {
                    "id": 3,
                    "question": "Q3",
                    "source_files": ["reports/report_0.pdf", "reports/report_2.pdf"],
                },
            ],
        }
        is_valid, invalid = manager.validate_test_set(test_set_data, meal_config)
        assert is_valid is False
        assert len(invalid) == 2
        invalid_ids = {q["id"] for q in invalid}
        assert invalid_ids == {2, 3}

    def test_empty_questions_list_valid(self, env):
        manager, config = env
        meal_config = _make_meal_config(data_id="current_meal")
        test_set_data = {
            "metadata": {
                "name": "test_set",
                "meal_id": "different_meal",
                "created_at": "2026-04-20T10:00:00",
                "updated_at": "2026-04-20T10:00:00",
            },
            "questions": [],
        }
        is_valid, invalid = manager.validate_test_set(test_set_data, meal_config)
        assert is_valid is True
        assert invalid == []

    def test_questions_without_source_files_valid(self, env):
        manager, config = env
        meal_config = _make_meal_config(data_id="current_meal")
        test_set_data = {
            "metadata": {
                "name": "test_set",
                "meal_id": "different_meal",
                "created_at": "2026-04-20T10:00:00",
                "updated_at": "2026-04-20T10:00:00",
            },
            "questions": [
                {"id": 1, "question": "Q1"},
                {"id": 2, "question": "Q2", "source_files": []},
                {
                    "id": 3,
                    "question": "Q3",
                    "question_type": "irrelevant",
                    "source_files": ["nonexistent.pdf"],
                },
            ],
        }
        is_valid, invalid = manager.validate_test_set(test_set_data, meal_config)
        assert is_valid is True
        assert invalid == []

    def test_update_meal_id(self, env):
        manager, config = env
        test_set_data = {
            "metadata": {
                "name": "test_set",
                "meal_id": "old_id",
                "created_at": "2026-04-20T10:00:00",
                "updated_at": "2026-04-20T10:00:00",
            },
            "questions": [],
        }
        updated = manager._update_meal_id(test_set_data, "new_id")
        assert updated["metadata"]["meal_id"] == "new_id"
        assert updated["metadata"]["updated_at"] != "2026-04-20T10:00:00"


class TestMigrateTestSet:
    @pytest.fixture
    def env(self, tmp_path):
        config = _make_config(tmp_path)
        manager = TestSetManager(config)
        return manager, config

    def test_new_format_unchanged(self, env):
        manager, config = env
        new_format = {
            "metadata": {
                "name": "test_set",
                "meal_id": "abc123",
                "created_at": "2026-04-20T10:00:00",
                "updated_at": "2026-04-20T10:00:00",
                "generation": {"strategy": "document"},
                "user_defined": True,
                "invalid_policy": "trim",
                "audit_log": [{"event": "created"}],
                "suppress_warnings": True,
            },
            "quality_metrics": {"authenticity_pass_rate": 0.9},
            "questions": [{"id": "q001", "question": "What?"}],
        }
        result = manager._migrate_test_set(new_format)
        assert result is new_format

    def test_old_format_migrated(self, env):
        manager, config = env
        old_format = {
            "name": "old_test_set",
            "meal_data_id": "xyz789",
            "meal_name": "test_meal",
            "strategy": "document",
            "created_at": "2026-04-20T10:00:00",
            "generation_config": {
                "num_questions": 20,
                "llm_preset": "default",
            },
            "quality_metrics": {"authenticity_pass_rate": 0.8},
            "questions": [{"id": "q001", "question": "What?"}],
        }
        result = manager._migrate_test_set(old_format)
        assert "metadata" in result
        assert result["metadata"]["name"] == "old_test_set"
        assert result["metadata"]["meal_id"] == "xyz789"
        assert result["metadata"]["created_at"] == "2026-04-20T10:00:00"
        assert result["metadata"]["updated_at"] == "2026-04-20T10:00:00"
        assert result["metadata"]["generation"]["num_questions"] == 20
        assert result["metadata"]["user_defined"] is False
        assert result["metadata"]["invalid_policy"] is None
        assert result["metadata"]["audit_log"] == []
        assert result["metadata"]["suppress_warnings"] is False
        assert result["metadata"]["composition"] == {}
        assert result["quality_metrics"]["authenticity_pass_rate"] == 0.8
        assert len(result["questions"]) == 1

    def test_old_format_minimal_fields(self, env):
        manager, config = env
        old_format = {
            "questions": [{"id": "q001"}],
        }
        result = manager._migrate_test_set(old_format)
        assert result["metadata"]["name"] == "unknown"
        assert result["metadata"]["meal_id"] == ""
        assert result["metadata"]["created_at"] == ""
        assert result["metadata"]["updated_at"] == ""
        assert result["metadata"]["generation"] == {}
        assert result["metadata"]["composition"] == {}
        assert result["quality_metrics"] == {}
        assert len(result["questions"]) == 1

    def test_load_test_set_auto_migrates(self, env):
        manager, config = env
        _create_meal_dir(config, "my_meal")
        test_sets_dir = Path(config["meals"]["dir"]) / "my_meal" / "test_sets"
        old_format = {
            "name": "old_set",
            "meal_data_id": "legacy123",
            "created_at": "2026-04-20T10:00:00",
            "generation_config": {"num_questions": 10},
            "questions": [{"id": "q001", "question": "What?"}],
        }
        old_file = test_sets_dir / "old_set.json"
        with open(old_file, "w", encoding="utf-8") as f:
            json.dump(old_format, f)
        loaded = manager.load_test_set("my_meal", "old_set")
        assert "metadata" in loaded
        assert loaded["metadata"]["name"] == "old_set"
        assert loaded["metadata"]["meal_id"] == "legacy123"

    def test_find_by_name_auto_migrates(self, env):
        manager, config = env
        _create_meal_dir(config, "my_meal")
        test_sets_dir = Path(config["meals"]["dir"]) / "my_meal" / "test_sets"
        old_format = {
            "name": "legacy_set",
            "meal_data_id": "legacy456",
            "created_at": "2026-04-20T10:00:00",
            "questions": [],
        }
        old_file = test_sets_dir / "legacy_set.json"
        with open(old_file, "w", encoding="utf-8") as f:
            json.dump(old_format, f)
        result = manager.find_by_name("my_meal", "legacy_set")
        assert result is not None
        assert "metadata" in result
        assert result["metadata"]["name"] == "legacy_set"
        assert result["metadata"]["meal_id"] == "legacy456"


class TestArchiveBackup:
    @pytest.fixture
    def env(self, tmp_path):
        config = _make_config(tmp_path)
        manager = TestSetManager(config)
        return manager, config

    def test_create_archive_backup(self, env):
        manager, config = env
        _create_meal_dir(config, "my_meal")
        test_set_data = {
            "metadata": {
                "name": "golden_test",
                "meal_id": "abc123",
                "created_at": "2026-04-20T10:00:00",
                "updated_at": "2026-04-20T10:00:00",
            },
            "questions": [{"id": 1, "question": "What?"}],
        }
        archive_path = manager._create_archive_backup(test_set_data, "my_meal")
        assert archive_path.exists()
        assert "golden_test.archive." in archive_path.name
        assert archive_path.name.endswith(".json")
        with open(archive_path, encoding="utf-8") as f:
            loaded = json.load(f)
        assert loaded["metadata"]["name"] == "golden_test"

    def test_archive_filename_format(self, env):
        manager, config = env
        _create_meal_dir(config, "my_meal")
        test_set_data = {
            "metadata": {
                "name": "test_set",
                "meal_id": "abc123",
                "created_at": "2026-04-20T10:00:00",
                "updated_at": "2026-04-20T10:00:00",
            },
            "questions": [],
        }
        archive_path = manager._create_archive_backup(test_set_data, "my_meal")
        filename = archive_path.name
        assert filename.startswith("test_set.archive.")
        assert filename.endswith(".json")
        timestamp_part = filename.replace("test_set.archive.", "").replace(".json", "")
        assert len(timestamp_part) == 16
        assert "T" in timestamp_part
        assert timestamp_part.endswith("Z")


class TestCleanImmutablePolicy:
    @pytest.fixture
    def env(self, tmp_path):
        config = _make_config(tmp_path)
        manager = TestSetManager(config)
        return manager, config

    def test_no_invalid_questions_updates_meal_id(self, env):
        manager, config = env
        meal_config = _make_meal_config(data_id="new_meal_id")
        test_set_data = {
            "metadata": {
                "name": "immutable_set",
                "meal_id": "old_meal_id",
                "created_at": "2026-04-20T10:00:00",
                "updated_at": "2026-04-20T10:00:00",
                "invalid_policy": "immutable",
            },
            "questions": [
                {"id": 1, "question": "Q1", "source_files": ["reports/report_0.pdf"]},
            ],
        }
        result = manager._clean_immutable_policy(test_set_data, meal_config, [])
        assert result["metadata"]["meal_id"] == "new_meal_id"
        assert result["metadata"]["updated_at"] != "2026-04-20T10:00:00"

    def test_invalid_questions_raises_error(self, env):
        manager, config = env
        meal_config = _make_meal_config(data_id="current_meal")
        test_set_data = {
            "metadata": {
                "name": "immutable_set",
                "meal_id": "old_meal_id",
                "created_at": "2026-04-20T10:00:00",
                "updated_at": "2026-04-20T10:00:00",
                "invalid_policy": "immutable",
            },
            "questions": [
                {"id": 1, "question": "Q1", "source_files": ["missing.pdf"]},
            ],
        }
        invalid_questions = [
            {"id": 1, "question": "Q1", "source_files": ["missing.pdf"]}
        ]
        with pytest.raises(TestSetError) as exc_info:
            manager._clean_immutable_policy(
                test_set_data, meal_config, invalid_questions
            )
        assert "immutable policy" in str(exc_info.value).lower()
        assert "1 invalid questions" in str(exc_info.value)

    def test_multiple_invalid_questions_raises_error(self, env):
        manager, config = env
        meal_config = _make_meal_config(data_id="current_meal")
        test_set_data = {
            "metadata": {
                "name": "immutable_set",
                "meal_id": "old_meal_id",
                "created_at": "2026-04-20T10:00:00",
                "updated_at": "2026-04-20T10:00:00",
                "invalid_policy": "immutable",
            },
            "questions": [
                {"id": 1, "question": "Q1"},
                {"id": 2, "question": "Q2"},
            ],
        }
        invalid_questions = [
            {"id": 1, "question": "Q1"},
            {"id": 2, "question": "Q2"},
        ]
        with pytest.raises(TestSetError) as exc_info:
            manager._clean_immutable_policy(
                test_set_data, meal_config, invalid_questions
            )
        assert "2 invalid questions" in str(exc_info.value)


class TestCleanTrimPolicy:
    @pytest.fixture
    def env(self, tmp_path):
        config = _make_config(tmp_path)
        manager = TestSetManager(config)
        return manager, config

    def test_trim_removes_invalid_questions(self, env):
        manager, config = env
        meal_config = _make_meal_config(
            data_id="current_meal",
            pdf_paths=["reports/report_0.pdf"],
        )
        _create_meal_dir(config, meal_config.name)
        test_set_data = {
            "metadata": {
                "name": "trim_set",
                "meal_id": "old_meal_id",
                "created_at": "2026-04-20T10:00:00",
                "updated_at": "2026-04-20T10:00:00",
                "invalid_policy": "trim",
                "audit_log": [],
            },
            "questions": [
                {"id": 1, "question": "Q1", "source_files": ["reports/report_0.pdf"]},
                {"id": 2, "question": "Q2", "source_files": ["missing.pdf"]},
                {"id": 3, "question": "Q3", "source_files": ["reports/report_0.pdf"]},
            ],
        }
        invalid_questions = [
            {"id": 2, "question": "Q2", "source_files": ["missing.pdf"]}
        ]
        result = manager._clean_trim_policy(
            test_set_data, meal_config, invalid_questions
        )
        assert len(result["questions"]) == 2
        question_ids = {q["id"] for q in result["questions"]}
        assert question_ids == {1, 3}
        assert result["metadata"]["meal_id"] == "current_meal"
        assert len(result["metadata"]["audit_log"]) == 1
        assert result["metadata"]["audit_log"][0]["action"] == "trimmed"
        assert result["metadata"]["audit_log"][0]["removed_count"] == 1

    def test_all_invalid_raises_error(self, env):
        manager, config = env
        meal_config = _make_meal_config(data_id="current_meal")
        _create_meal_dir(config, meal_config.name)
        test_set_data = {
            "metadata": {
                "name": "trim_set",
                "meal_id": "old_meal_id",
                "created_at": "2026-04-20T10:00:00",
                "updated_at": "2026-04-20T10:00:00",
                "invalid_policy": "trim",
                "audit_log": [],
            },
            "questions": [
                {"id": 1, "question": "Q1", "source_files": ["missing.pdf"]},
                {"id": 2, "question": "Q2", "source_files": ["missing.pdf"]},
            ],
        }
        invalid_questions = [
            {"id": 1, "question": "Q1", "source_files": ["missing.pdf"]},
            {"id": 2, "question": "Q2", "source_files": ["missing.pdf"]},
        ]
        with pytest.raises(TestSetError) as exc_info:
            manager._clean_trim_policy(test_set_data, meal_config, invalid_questions)
        assert "all" in str(exc_info.value).lower()
        assert "invalid" in str(exc_info.value).lower()

    def test_trim_creates_archive_backup(self, env):
        manager, config = env
        meal_config = _make_meal_config(
            data_id="current_meal",
            pdf_paths=["reports/report_0.pdf"],
        )
        _create_meal_dir(config, meal_config.name)
        test_set_data = {
            "metadata": {
                "name": "trim_set",
                "meal_id": "old_meal_id",
                "created_at": "2026-04-20T10:00:00",
                "updated_at": "2026-04-20T10:00:00",
                "invalid_policy": "trim",
                "audit_log": [],
            },
            "questions": [
                {"id": 1, "question": "Q1", "source_files": ["reports/report_0.pdf"]},
                {"id": 2, "question": "Q2", "source_files": ["missing.pdf"]},
            ],
        }
        invalid_questions = [
            {"id": 2, "question": "Q2", "source_files": ["missing.pdf"]}
        ]
        manager._clean_trim_policy(test_set_data, meal_config, invalid_questions)
        test_sets_dir = Path(config["meals"]["dir"]) / meal_config.name / "test_sets"
        archive_files = list(test_sets_dir.glob("trim_set.archive.*.json"))
        assert len(archive_files) == 1

    def test_trim_saves_updated_test_set(self, env):
        manager, config = env
        meal_config = _make_meal_config(
            data_id="current_meal",
            pdf_paths=["reports/report_0.pdf"],
        )
        _create_meal_dir(config, meal_config.name)
        test_set_data = {
            "metadata": {
                "name": "trim_set",
                "meal_id": "old_meal_id",
                "created_at": "2026-04-20T10:00:00",
                "updated_at": "2026-04-20T10:00:00",
                "invalid_policy": "trim",
                "audit_log": [],
            },
            "questions": [
                {"id": 1, "question": "Q1", "source_files": ["reports/report_0.pdf"]},
                {"id": 2, "question": "Q2", "source_files": ["missing.pdf"]},
            ],
        }
        invalid_questions = [
            {"id": 2, "question": "Q2", "source_files": ["missing.pdf"]}
        ]
        manager._clean_trim_policy(test_set_data, meal_config, invalid_questions)
        loaded = manager.load_test_set(meal_config.name, "trim_set")
        assert len(loaded["questions"]) == 1
        assert loaded["questions"][0]["id"] == 1


class TestCleanRegeneratePolicy:
    @pytest.fixture
    def env(self, tmp_path):
        config = _make_config(tmp_path)
        manager = TestSetManager(config)
        return manager, config

    def test_missing_generation_config_raises_error(self, env):
        manager, config = env
        meal_config = _make_meal_config(data_id="current_meal")
        test_set_data = {
            "metadata": {
                "name": "regen_set",
                "meal_id": "old_meal_id",
                "created_at": "2026-04-20T10:00:00",
                "updated_at": "2026-04-20T10:00:00",
                "invalid_policy": "regenerate",
                "generation": None,
                "audit_log": [],
            },
            "questions": [{"id": 1, "question": "Q1"}],
        }
        invalid_questions = [{"id": 1, "question": "Q1"}]
        with pytest.raises(TestSetError) as exc_info:
            manager._clean_regenerate_policy(
                test_set_data, meal_config, invalid_questions, None, "default", None
            )
        assert "generation config" in str(exc_info.value).lower()

    def test_no_generation_key_raises_error(self, env):
        manager, config = env
        meal_config = _make_meal_config(data_id="current_meal")
        test_set_data = {
            "metadata": {
                "name": "regen_set",
                "meal_id": "old_meal_id",
                "created_at": "2026-04-20T10:00:00",
                "updated_at": "2026-04-20T10:00:00",
                "invalid_policy": "regenerate",
                "audit_log": [],
            },
            "questions": [{"id": 1, "question": "Q1"}],
        }
        invalid_questions = [{"id": 1, "question": "Q1"}]
        with pytest.raises(TestSetError) as exc_info:
            manager._clean_regenerate_policy(
                test_set_data, meal_config, invalid_questions, None, "default", None
            )
        assert "generation config" in str(exc_info.value).lower()

    def test_removes_invalid_questions_without_generator(self, env):
        manager, config = env
        meal_config = _make_meal_config(
            data_id="current_meal",
            pdf_paths=["reports/report_0.pdf"],
        )
        _create_meal_dir(config, meal_config.name)
        test_set_data = {
            "metadata": {
                "name": "regen_set",
                "meal_id": "old_meal_id",
                "created_at": "2026-04-20T10:00:00",
                "updated_at": "2026-04-20T10:00:00",
                "invalid_policy": "regenerate",
                "generation": {"strategy": "random", "num_questions": 5},
                "audit_log": [],
            },
            "questions": [
                {"id": 1, "question": "Q1", "source_files": ["reports/report_0.pdf"]},
                {"id": 2, "question": "Q2", "source_files": ["missing.pdf"]},
            ],
        }
        invalid_questions = [
            {"id": 2, "question": "Q2", "source_files": ["missing.pdf"]}
        ]
        result = manager._clean_regenerate_policy(
            test_set_data, meal_config, invalid_questions, None, "default", None
        )
        assert len(result["questions"]) == 1
        assert result["questions"][0]["id"] == 1

    def test_creates_archive_backup(self, env):
        manager, config = env
        meal_config = _make_meal_config(
            data_id="current_meal",
            pdf_paths=["reports/report_0.pdf"],
        )
        _create_meal_dir(config, meal_config.name)
        test_set_data = {
            "metadata": {
                "name": "regen_set",
                "meal_id": "old_meal_id",
                "created_at": "2026-04-20T10:00:00",
                "updated_at": "2026-04-20T10:00:00",
                "invalid_policy": "regenerate",
                "generation": {"strategy": "random", "num_questions": 5},
                "audit_log": [],
            },
            "questions": [
                {"id": 1, "question": "Q1", "source_files": ["reports/report_0.pdf"]},
                {"id": 2, "question": "Q2", "source_files": ["missing.pdf"]},
            ],
        }
        invalid_questions = [
            {"id": 2, "question": "Q2", "source_files": ["missing.pdf"]}
        ]
        manager._clean_regenerate_policy(
            test_set_data, meal_config, invalid_questions, None, "default", None
        )
        test_sets_dir = Path(config["meals"]["dir"]) / meal_config.name / "test_sets"
        archive_files = list(test_sets_dir.glob("regen_set.archive.*.json"))
        assert len(archive_files) == 1

    def test_audit_log_entry(self, env):
        manager, config = env
        meal_config = _make_meal_config(
            data_id="current_meal",
            pdf_paths=["reports/report_0.pdf"],
        )
        _create_meal_dir(config, meal_config.name)
        test_set_data = {
            "metadata": {
                "name": "regen_set",
                "meal_id": "old_meal_id",
                "created_at": "2026-04-20T10:00:00",
                "updated_at": "2026-04-20T10:00:00",
                "invalid_policy": "regenerate",
                "generation": {"strategy": "random", "num_questions": 5},
                "audit_log": [],
            },
            "questions": [
                {"id": 1, "question": "Q1", "source_files": ["reports/report_0.pdf"]},
                {"id": 2, "question": "Q2", "source_files": ["missing.pdf"]},
            ],
        }
        invalid_questions = [
            {"id": 2, "question": "Q2", "source_files": ["missing.pdf"]}
        ]
        result = manager._clean_regenerate_policy(
            test_set_data, meal_config, invalid_questions, None, "default", None
        )
        assert len(result["metadata"]["audit_log"]) == 1
        entry = result["metadata"]["audit_log"][0]
        assert entry["action"] == "regenerated"
        assert entry["removed_count"] == 1
        assert 2 in entry["removed_ids"]
        assert "full_regeneration" not in entry

    def test_full_regeneration_flag(self, env):
        manager, config = env
        meal_config = _make_meal_config(data_id="current_meal")
        _create_meal_dir(config, meal_config.name)
        test_set_data = {
            "metadata": {
                "name": "regen_set",
                "meal_id": "old_meal_id",
                "created_at": "2026-04-20T10:00:00",
                "updated_at": "2026-04-20T10:00:00",
                "invalid_policy": "regenerate",
                "generation": {"strategy": "random", "num_questions": 5},
                "audit_log": [],
            },
            "questions": [
                {"id": 1, "question": "Q1", "source_files": ["missing.pdf"]},
                {"id": 2, "question": "Q2", "source_files": ["missing.pdf"]},
            ],
        }
        invalid_questions = [
            {"id": 1, "question": "Q1", "source_files": ["missing.pdf"]},
            {"id": 2, "question": "Q2", "source_files": ["missing.pdf"]},
        ]
        result = manager._clean_regenerate_policy(
            test_set_data, meal_config, invalid_questions, None, "default", None
        )
        entry = result["metadata"]["audit_log"][0]
        assert entry["full_regeneration"] is True

    def test_with_generator_calls_generate(self, env):
        manager, config = env
        meal_config = _make_meal_config(
            data_id="current_meal",
            pdf_paths=["reports/report_0.pdf"],
        )
        _create_meal_dir(config, meal_config.name)

        class MockGenerator:
            def generate_questions(
                self, meal_config, num_questions, llm_preset, token_tracker
            ):
                return [
                    {"id": 100, "question": f"New Q{i}"} for i in range(num_questions)
                ]

        test_set_data = {
            "metadata": {
                "name": "regen_set",
                "meal_id": "old_meal_id",
                "created_at": "2026-04-20T10:00:00",
                "updated_at": "2026-04-20T10:00:00",
                "invalid_policy": "regenerate",
                "generation": {"strategy": "random", "num_questions": 5},
                "audit_log": [],
            },
            "questions": [
                {"id": 1, "question": "Q1", "source_files": ["reports/report_0.pdf"]},
                {"id": 2, "question": "Q2", "source_files": ["missing.pdf"]},
            ],
        }
        invalid_questions = [
            {"id": 2, "question": "Q2", "source_files": ["missing.pdf"]}
        ]
        result = manager._clean_regenerate_policy(
            test_set_data,
            meal_config,
            invalid_questions,
            MockGenerator(),
            "default",
            None,
        )
        assert len(result["questions"]) == 2
        question_ids = {q["id"] for q in result["questions"]}
        assert 1 in question_ids
        assert 100 in question_ids


class TestCleanUserTestSet:
    @pytest.fixture
    def env(self, tmp_path):
        config = _make_config(tmp_path)
        manager = TestSetManager(config)
        return manager, config

    def test_routes_to_immutable_policy(self, env):
        manager, config = env
        meal_config = _make_meal_config(data_id="new_meal_id")
        test_set_data = {
            "metadata": {
                "name": "test_set",
                "meal_id": "old_meal_id",
                "created_at": "2026-04-20T10:00:00",
                "updated_at": "2026-04-20T10:00:00",
                "invalid_policy": "immutable",
            },
            "questions": [{"id": 1, "question": "Q1"}],
        }
        result = manager._clean_user_test_set(test_set_data, meal_config, [])
        assert result["metadata"]["meal_id"] == "new_meal_id"

    def test_routes_to_trim_policy(self, env):
        manager, config = env
        meal_config = _make_meal_config(
            data_id="current_meal",
            pdf_paths=["reports/report_0.pdf"],
        )
        _create_meal_dir(config, meal_config.name)
        test_set_data = {
            "metadata": {
                "name": "test_set",
                "meal_id": "old_meal_id",
                "created_at": "2026-04-20T10:00:00",
                "updated_at": "2026-04-20T10:00:00",
                "invalid_policy": "trim",
                "audit_log": [],
            },
            "questions": [
                {"id": 1, "question": "Q1", "source_files": ["reports/report_0.pdf"]},
                {"id": 2, "question": "Q2", "source_files": ["missing.pdf"]},
            ],
        }
        invalid_questions = [
            {"id": 2, "question": "Q2", "source_files": ["missing.pdf"]}
        ]
        result = manager._clean_user_test_set(
            test_set_data, meal_config, invalid_questions
        )
        assert len(result["questions"]) == 1

    def test_routes_to_regenerate_policy(self, env):
        manager, config = env
        meal_config = _make_meal_config(
            data_id="current_meal",
            pdf_paths=["reports/report_0.pdf"],
        )
        _create_meal_dir(config, meal_config.name)
        test_set_data = {
            "metadata": {
                "name": "test_set",
                "meal_id": "old_meal_id",
                "created_at": "2026-04-20T10:00:00",
                "updated_at": "2026-04-20T10:00:00",
                "invalid_policy": "regenerate",
                "generation": {"strategy": "random", "num_questions": 5},
                "audit_log": [],
            },
            "questions": [
                {"id": 1, "question": "Q1", "source_files": ["reports/report_0.pdf"]},
                {"id": 2, "question": "Q2", "source_files": ["missing.pdf"]},
            ],
        }
        invalid_questions = [
            {"id": 2, "question": "Q2", "source_files": ["missing.pdf"]}
        ]
        result = manager._clean_user_test_set(
            test_set_data, meal_config, invalid_questions
        )
        assert len(result["questions"]) == 1
        assert result["metadata"]["audit_log"][0]["action"] == "regenerated"

    def test_unknown_policy_raises_error(self, env):
        manager, config = env
        meal_config = _make_meal_config(data_id="current_meal")
        test_set_data = {
            "metadata": {
                "name": "test_set",
                "meal_id": "old_meal_id",
                "created_at": "2026-04-20T10:00:00",
                "updated_at": "2026-04-20T10:00:00",
                "invalid_policy": "unknown_policy",
            },
            "questions": [],
        }
        with pytest.raises(TestSetError) as exc_info:
            manager._clean_user_test_set(test_set_data, meal_config, [])
        assert "unknown invalid_policy" in str(exc_info.value).lower()


class TestCleaningWarnings:
    @pytest.fixture
    def env(self, tmp_path):
        config = _make_config(tmp_path)
        manager = TestSetManager(config)
        return manager, config

    def test_no_warning_when_no_audit_log(self, env):
        manager, config = env
        test_set_data = {
            "metadata": {
                "name": "test_set",
                "meal_id": "abc123",
                "audit_log": [],
            },
            "questions": [],
        }
        should_warn, message = manager._should_warn_about_cleaning(test_set_data)
        assert should_warn is False
        assert message == ""

    def test_no_warning_when_suppress_warnings_true(self, env):
        manager, config = env
        test_set_data = {
            "metadata": {
                "name": "test_set",
                "meal_id": "abc123",
                "suppress_warnings": True,
                "audit_log": [
                    {
                        "action": "trimmed",
                        "timestamp": "2026-04-20T10:00:00",
                        "removed_count": 2,
                    }
                ],
            },
            "questions": [],
        }
        should_warn, message = manager._should_warn_about_cleaning(test_set_data)
        assert should_warn is False
        assert message == ""

    def test_warning_for_trimmed_action(self, env):
        manager, config = env
        test_set_data = {
            "metadata": {
                "name": "test_set",
                "meal_id": "abc123",
                "suppress_warnings": False,
                "audit_log": [
                    {
                        "action": "trimmed",
                        "timestamp": "2026-04-20T10:00:00",
                        "removed_count": 3,
                    }
                ],
            },
            "questions": [],
        }
        should_warn, message = manager._should_warn_about_cleaning(test_set_data)
        assert should_warn is True
        assert "trimmed" in message.lower()
        assert "3 questions" in message

    def test_warning_for_regenerated_action(self, env):
        manager, config = env
        test_set_data = {
            "metadata": {
                "name": "test_set",
                "meal_id": "abc123",
                "suppress_warnings": False,
                "audit_log": [
                    {
                        "action": "regenerated",
                        "timestamp": "2026-04-20T11:00:00",
                        "removed_count": 5,
                    }
                ],
            },
            "questions": [],
        }
        should_warn, message = manager._should_warn_about_cleaning(test_set_data)
        assert should_warn is True
        assert "regenerated" in message.lower()
        assert "5 questions" in message

    def test_warning_for_full_regeneration(self, env):
        manager, config = env
        test_set_data = {
            "metadata": {
                "name": "test_set",
                "meal_id": "abc123",
                "suppress_warnings": False,
                "audit_log": [
                    {
                        "action": "regenerated",
                        "timestamp": "2026-04-20T12:00:00",
                        "full_regeneration": True,
                    }
                ],
            },
            "questions": [],
        }
        should_warn, message = manager._should_warn_about_cleaning(test_set_data)
        assert should_warn is True
        assert "full regeneration" in message.lower()
        assert "all questions were replaced" in message.lower()

    def test_returns_first_warning_found(self, env):
        manager, config = env
        test_set_data = {
            "metadata": {
                "name": "test_set",
                "meal_id": "abc123",
                "suppress_warnings": False,
                "audit_log": [
                    {
                        "action": "trimmed",
                        "timestamp": "2026-04-20T10:00:00",
                        "removed_count": 1,
                    },
                    {
                        "action": "regenerated",
                        "timestamp": "2026-04-20T11:00:00",
                        "removed_count": 2,
                    },
                ],
            },
            "questions": [],
        }
        should_warn, message = manager._should_warn_about_cleaning(test_set_data)
        assert should_warn is True
        assert "trimmed" in message.lower()

    def test_no_warning_for_other_actions(self, env):
        manager, config = env
        test_set_data = {
            "metadata": {
                "name": "test_set",
                "meal_id": "abc123",
                "suppress_warnings": False,
                "audit_log": [
                    {"action": "created", "timestamp": "2026-04-20T09:00:00"},
                ],
            },
            "questions": [],
        }
        should_warn, message = manager._should_warn_about_cleaning(test_set_data)
        assert should_warn is False
        assert message == ""


class TestCleanMachineTestSet:
    @pytest.fixture
    def env(self, tmp_path):
        config = _make_config(tmp_path)
        manager = TestSetManager(config)
        return manager, config

    def test_basic_cleaning_removes_invalid_questions(self, env):
        manager, config = env
        meal_config = _make_meal_config(
            data_id="current_meal",
            pdf_paths=["reports/report_0.pdf"],
        )
        _create_meal_dir(config, meal_config.name)
        test_set_data = {
            "metadata": {
                "name": "machine_set",
                "meal_id": "old_meal_id",
                "created_at": "2026-04-20T10:00:00",
                "updated_at": "2026-04-20T10:00:00",
                "generation": {"strategy": "document", "num_questions": 5},
                "audit_log": [],
            },
            "questions": [
                {"id": 1, "question": "Q1", "source_files": ["reports/report_0.pdf"]},
                {"id": 2, "question": "Q2", "source_files": ["missing.pdf"]},
                {"id": 3, "question": "Q3", "source_files": ["reports/report_0.pdf"]},
            ],
        }
        invalid_questions = [
            {"id": 2, "question": "Q2", "source_files": ["missing.pdf"]}
        ]
        result = manager._clean_machine_test_set(
            test_set_data, meal_config, invalid_questions
        )
        assert len(result["questions"]) == 2
        question_ids = {q["id"] for q in result["questions"]}
        assert question_ids == {1, 3}

    def test_cleaning_supplements_questions_to_restore_count(self, env):
        manager, config = env
        meal_config = _make_meal_config(
            data_id="current_meal",
            pdf_paths=["reports/report_0.pdf"],
        )
        _create_meal_dir(config, meal_config.name)

        class MockGenerator:
            def supplement_document_based_questions(
                self,
                meal_name,
                existing_test_set,
                target_count,
                llm_preset,
                token_tracker,
            ):
                current_count = len(existing_test_set.get("questions", []))
                deficit = target_count - current_count
                for i in range(deficit):
                    existing_test_set["questions"].append(
                        {"id": 100 + i, "question": f"New Q{i}"}
                    )
                return existing_test_set

        test_set_data = {
            "metadata": {
                "name": "machine_set",
                "meal_id": "old_meal_id",
                "created_at": "2026-04-20T10:00:00",
                "updated_at": "2026-04-20T10:00:00",
                "generation": {"strategy": "document", "num_questions": 5},
                "audit_log": [],
            },
            "questions": [
                {"id": 1, "question": "Q1", "source_files": ["reports/report_0.pdf"]},
                {"id": 2, "question": "Q2", "source_files": ["missing.pdf"]},
                {"id": 3, "question": "Q3", "source_files": ["reports/report_0.pdf"]},
            ],
        }
        invalid_questions = [
            {"id": 2, "question": "Q2", "source_files": ["missing.pdf"]}
        ]
        result = manager._clean_machine_test_set(
            test_set_data, meal_config, invalid_questions, generator=MockGenerator()
        )
        assert len(result["questions"]) == 3
        question_ids = {q["id"] for q in result["questions"]}
        assert 1 in question_ids
        assert 3 in question_ids
        assert 100 in question_ids

    def test_cleaning_updates_meal_id(self, env):
        manager, config = env
        meal_config = _make_meal_config(
            data_id="new_meal_id",
            pdf_paths=["reports/report_0.pdf"],
        )
        _create_meal_dir(config, meal_config.name)
        test_set_data = {
            "metadata": {
                "name": "machine_set",
                "meal_id": "old_meal_id",
                "created_at": "2026-04-20T10:00:00",
                "updated_at": "2026-04-20T10:00:00",
                "generation": {"strategy": "document", "num_questions": 5},
                "audit_log": [],
            },
            "questions": [
                {"id": 1, "question": "Q1", "source_files": ["reports/report_0.pdf"]},
            ],
        }
        result = manager._clean_machine_test_set(test_set_data, meal_config, [])
        assert result["metadata"]["meal_id"] == "new_meal_id"
        assert result["metadata"]["updated_at"] != "2026-04-20T10:00:00"

    def test_cleaning_adds_audit_log_entry(self, env):
        manager, config = env
        meal_config = _make_meal_config(
            data_id="new_meal_id",
            pdf_paths=["reports/report_0.pdf"],
        )
        _create_meal_dir(config, meal_config.name)
        test_set_data = {
            "metadata": {
                "name": "machine_set",
                "meal_id": "old_meal_id",
                "created_at": "2026-04-20T10:00:00",
                "updated_at": "2026-04-20T10:00:00",
                "generation": {"strategy": "document", "num_questions": 5},
                "audit_log": [],
            },
            "questions": [
                {"id": 1, "question": "Q1", "source_files": ["reports/report_0.pdf"]},
                {"id": 2, "question": "Q2", "source_files": ["missing.pdf"]},
            ],
        }
        invalid_questions = [
            {"id": 2, "question": "Q2", "source_files": ["missing.pdf"]}
        ]
        result = manager._clean_machine_test_set(
            test_set_data, meal_config, invalid_questions
        )
        assert len(result["metadata"]["audit_log"]) == 1
        entry = result["metadata"]["audit_log"][0]
        assert entry["event"] == "cleaned"
        assert entry["from_meal"] == "old_meal_id"
        assert entry["to_meal"] == "new_meal_id"
        assert entry["removed_count"] == 1
        assert entry["added_count"] == 0
        assert "timestamp" in entry

    def test_generation_config_conflict_is_logged(self, env):
        manager, config = env
        meal_config = _make_meal_config(
            data_id="current_meal",
            pdf_paths=["reports/report_0.pdf"],
        )
        _create_meal_dir(config, meal_config.name)
        test_set_data = {
            "metadata": {
                "name": "machine_set",
                "meal_id": "old_meal_id",
                "created_at": "2026-04-20T10:00:00",
                "updated_at": "2026-04-20T10:00:00",
                "generation": {"strategy": "document", "num_questions": 5},
                "audit_log": [],
            },
            "questions": [
                {"id": 1, "question": "Q1", "source_files": ["reports/report_0.pdf"]},
            ],
        }
        new_generation_config = {"strategy": "random", "num_questions": 10, "seed": 42}
        result = manager._clean_machine_test_set(
            test_set_data, meal_config, [], generation_config=new_generation_config
        )
        assert len(result["metadata"]["audit_log"]) == 2
        config_change_entry = result["metadata"]["audit_log"][0]
        assert config_change_entry["event"] == "generation_config_changed"
        assert config_change_entry["old_config"] == {
            "strategy": "document",
            "num_questions": 5,
        }
        assert config_change_entry["new_config"] == new_generation_config
        cleaned_entry = result["metadata"]["audit_log"][1]
        assert cleaned_entry["event"] == "cleaned"

    def test_cleaning_without_generator_just_removes_questions(self, env):
        manager, config = env
        meal_config = _make_meal_config(
            data_id="current_meal",
            pdf_paths=["reports/report_0.pdf"],
        )
        _create_meal_dir(config, meal_config.name)
        test_set_data = {
            "metadata": {
                "name": "machine_set",
                "meal_id": "old_meal_id",
                "created_at": "2026-04-20T10:00:00",
                "updated_at": "2026-04-20T10:00:00",
                "generation": {"strategy": "document", "num_questions": 5},
                "audit_log": [],
            },
            "questions": [
                {"id": 1, "question": "Q1", "source_files": ["reports/report_0.pdf"]},
                {"id": 2, "question": "Q2", "source_files": ["missing.pdf"]},
                {"id": 3, "question": "Q3", "source_files": ["missing2.pdf"]},
            ],
        }
        invalid_questions = [
            {"id": 2, "question": "Q2", "source_files": ["missing.pdf"]},
            {"id": 3, "question": "Q3", "source_files": ["missing2.pdf"]},
        ]
        result = manager._clean_machine_test_set(
            test_set_data, meal_config, invalid_questions
        )
        assert len(result["questions"]) == 1
        assert result["questions"][0]["id"] == 1
        assert result["metadata"]["audit_log"][0]["removed_count"] == 2
        assert result["metadata"]["audit_log"][0]["added_count"] == 0

    def test_cleaning_saves_test_set(self, env):
        manager, config = env
        meal_config = _make_meal_config(
            data_id="current_meal",
            pdf_paths=["reports/report_0.pdf"],
        )
        _create_meal_dir(config, meal_config.name)
        test_set_data = {
            "metadata": {
                "name": "machine_set",
                "meal_id": "old_meal_id",
                "created_at": "2026-04-20T10:00:00",
                "updated_at": "2026-04-20T10:00:00",
                "generation": {"strategy": "document", "num_questions": 5},
                "audit_log": [],
            },
            "questions": [
                {"id": 1, "question": "Q1", "source_files": ["reports/report_0.pdf"]},
                {"id": 2, "question": "Q2", "source_files": ["missing.pdf"]},
            ],
        }
        invalid_questions = [
            {"id": 2, "question": "Q2", "source_files": ["missing.pdf"]}
        ]
        manager._clean_machine_test_set(test_set_data, meal_config, invalid_questions)
        loaded = manager.load_test_set(meal_config.name, "machine_set")
        assert len(loaded["questions"]) == 1
        assert loaded["questions"][0]["id"] == 1
        assert loaded["metadata"]["meal_id"] == "current_meal"

    def test_cleaning_with_no_invalid_questions(self, env):
        manager, config = env
        meal_config = _make_meal_config(
            data_id="new_meal_id",
            pdf_paths=["reports/report_0.pdf"],
        )
        _create_meal_dir(config, meal_config.name)
        test_set_data = {
            "metadata": {
                "name": "machine_set",
                "meal_id": "old_meal_id",
                "created_at": "2026-04-20T10:00:00",
                "updated_at": "2026-04-20T10:00:00",
                "generation": {"strategy": "document", "num_questions": 5},
                "audit_log": [],
            },
            "questions": [
                {"id": 1, "question": "Q1", "source_files": ["reports/report_0.pdf"]},
            ],
        }
        result = manager._clean_machine_test_set(test_set_data, meal_config, [])
        assert len(result["questions"]) == 1
        assert result["metadata"]["meal_id"] == "new_meal_id"
        assert result["metadata"]["audit_log"][0]["removed_count"] == 0
        assert result["metadata"]["audit_log"][0]["added_count"] == 0


class TestResolveTestSet:
    @pytest.fixture
    def env(self, tmp_path):
        config = _make_config(tmp_path)
        manager = TestSetManager(config)
        return manager, config

    def test_auto_mode_valid_test_set_found_returned_directly(self, env):
        manager, config = env
        meal_config = _make_meal_config(
            data_id="matching_id",
            pdf_paths=["reports/report_0.pdf"],
        )
        _create_meal_dir(config, meal_config.name)
        test_set_data = {
            "metadata": {
                "name": "valid_set",
                "meal_id": "matching_id",
                "created_at": "2026-04-20T10:00:00",
                "updated_at": "2026-04-20T10:00:00",
                "user_defined": False,
            },
            "questions": [
                {"id": 1, "question": "Q1", "source_files": ["reports/report_0.pdf"]},
            ],
        }
        manager.save_test_set(meal_config.name, test_set_data)
        test_set_config = {"name": "valid_set", "on_missing": "auto"}
        result = manager.resolve_test_set(
            meal_name=meal_config.name,
            test_set_config=test_set_config,
            meal_config=meal_config,
        )
        assert result["metadata"]["name"] == "valid_set"
        assert len(result["questions"]) == 1

    def test_auto_mode_invalid_machine_test_set_cleaned_and_returned(self, env):
        manager, config = env
        meal_config = _make_meal_config(
            data_id="current_meal",
            pdf_paths=["reports/report_0.pdf"],
        )
        _create_meal_dir(config, meal_config.name)
        test_set_data = {
            "metadata": {
                "name": "machine_set",
                "meal_id": "old_meal_id",
                "created_at": "2026-04-20T10:00:00",
                "updated_at": "2026-04-20T10:00:00",
                "user_defined": False,
                "generation": {"strategy": "document", "num_questions": 5},
                "audit_log": [],
            },
            "questions": [
                {"id": 1, "question": "Q1", "source_files": ["reports/report_0.pdf"]},
                {"id": 2, "question": "Q2", "source_files": ["missing.pdf"]},
            ],
        }
        manager.save_test_set(meal_config.name, test_set_data)
        test_set_config = {"name": "machine_set", "on_missing": "auto"}
        result = manager.resolve_test_set(
            meal_name=meal_config.name,
            test_set_config=test_set_config,
            meal_config=meal_config,
        )
        assert result["metadata"]["name"] == "machine_set"
        assert result["metadata"]["meal_id"] == "current_meal"
        assert len(result["questions"]) == 1

    def test_auto_mode_invalid_user_test_set_cleaned_and_returned(self, env):
        manager, config = env
        meal_config = _make_meal_config(
            data_id="current_meal",
            pdf_paths=["reports/report_0.pdf"],
        )
        _create_meal_dir(config, meal_config.name)
        test_set_data = {
            "metadata": {
                "name": "user_set",
                "meal_id": "old_meal_id",
                "created_at": "2026-04-20T10:00:00",
                "updated_at": "2026-04-20T10:00:00",
                "user_defined": True,
                "invalid_policy": "trim",
                "audit_log": [],
            },
            "questions": [
                {"id": 1, "question": "Q1", "source_files": ["reports/report_0.pdf"]},
                {"id": 2, "question": "Q2", "source_files": ["missing.pdf"]},
            ],
        }
        manager.save_test_set(meal_config.name, test_set_data)
        test_set_config = {"name": "user_set", "on_missing": "auto"}
        result = manager.resolve_test_set(
            meal_name=meal_config.name,
            test_set_config=test_set_config,
            meal_config=meal_config,
        )
        assert result["metadata"]["name"] == "user_set"
        assert len(result["questions"]) == 1

    def test_auto_mode_not_found_with_generation_config_generated(self, env):
        manager, config = env
        meal_config = _make_meal_config(
            data_id="current_meal",
            pdf_paths=["reports/report_0.pdf"],
        )
        _create_meal_dir(config, meal_config.name)

        class MockGenerator:
            def generate_document_based_questions(
                self, meal_name, num_questions, name, llm_preset, token_tracker
            ):
                return {
                    "metadata": {
                        "name": name,
                        "meal_id": "current_meal",
                        "created_at": "2026-04-20T10:00:00",
                        "updated_at": "2026-04-20T10:00:00",
                        "generation": {
                            "strategy": "document",
                            "num_questions": num_questions,
                        },
                    },
                    "questions": [
                        {"id": i, "question": f"Q{i}"} for i in range(num_questions)
                    ],
                }

        test_set_config = {
            "name": "new_set",
            "on_missing": "auto",
            "generation": {"strategy": "document", "num_questions": 5},
        }
        result = manager.resolve_test_set(
            meal_name=meal_config.name,
            test_set_config=test_set_config,
            meal_config=meal_config,
            generator=MockGenerator(),
        )
        assert result["metadata"]["name"] == "new_set"
        assert len(result["questions"]) == 5

    def test_auto_mode_not_found_without_generation_config_generated_with_defaults(
        self, env
    ):
        manager, config = env
        meal_config = _make_meal_config(
            data_id="current_meal",
            pdf_paths=["reports/report_0.pdf"],
        )
        _create_meal_dir(config, meal_config.name)

        class MockGenerator:
            def generate_document_based_questions(
                self, meal_name, num_questions, name, llm_preset, token_tracker
            ):
                return {
                    "metadata": {
                        "name": name,
                        "meal_id": "current_meal",
                        "created_at": "2026-04-20T10:00:00",
                        "updated_at": "2026-04-20T10:00:00",
                        "generation": {
                            "strategy": "document",
                            "num_questions": num_questions,
                        },
                    },
                    "questions": [
                        {"id": i, "question": f"Q{i}"} for i in range(num_questions)
                    ],
                }

        test_set_config = {
            "name": "default_set",
            "on_missing": "auto",
        }
        result = manager.resolve_test_set(
            meal_name=meal_config.name,
            test_set_config=test_set_config,
            meal_config=meal_config,
            generator=MockGenerator(),
        )
        assert result["metadata"]["name"] == "default_set"
        assert len(result["questions"]) == 10

    def test_clean_only_mode_valid_test_set_found_returned_directly(self, env):
        manager, config = env
        meal_config = _make_meal_config(
            data_id="matching_id",
            pdf_paths=["reports/report_0.pdf"],
        )
        _create_meal_dir(config, meal_config.name)
        test_set_data = {
            "metadata": {
                "name": "valid_set",
                "meal_id": "matching_id",
                "created_at": "2026-04-20T10:00:00",
                "updated_at": "2026-04-20T10:00:00",
            },
            "questions": [
                {"id": 1, "question": "Q1", "source_files": ["reports/report_0.pdf"]},
            ],
        }
        manager.save_test_set(meal_config.name, test_set_data)
        test_set_config = {"name": "valid_set", "on_missing": "clean_only"}
        result = manager.resolve_test_set(
            meal_name=meal_config.name,
            test_set_config=test_set_config,
            meal_config=meal_config,
        )
        assert result["metadata"]["name"] == "valid_set"

    def test_clean_only_mode_invalid_test_set_cleaned_and_returned(self, env):
        manager, config = env
        meal_config = _make_meal_config(
            data_id="current_meal",
            pdf_paths=["reports/report_0.pdf"],
        )
        _create_meal_dir(config, meal_config.name)
        test_set_data = {
            "metadata": {
                "name": "machine_set",
                "meal_id": "old_meal_id",
                "created_at": "2026-04-20T10:00:00",
                "updated_at": "2026-04-20T10:00:00",
                "user_defined": False,
                "generation": {"strategy": "document", "num_questions": 5},
                "audit_log": [],
            },
            "questions": [
                {"id": 1, "question": "Q1", "source_files": ["reports/report_0.pdf"]},
                {"id": 2, "question": "Q2", "source_files": ["missing.pdf"]},
            ],
        }
        manager.save_test_set(meal_config.name, test_set_data)
        test_set_config = {"name": "machine_set", "on_missing": "clean_only"}
        result = manager.resolve_test_set(
            meal_name=meal_config.name,
            test_set_config=test_set_config,
            meal_config=meal_config,
        )
        assert result["metadata"]["name"] == "machine_set"
        assert len(result["questions"]) == 1

    def test_clean_only_mode_not_found_raises_value_error(self, env):
        manager, config = env
        meal_config = _make_meal_config(
            data_id="current_meal",
            pdf_paths=["reports/report_0.pdf"],
        )
        _create_meal_dir(config, meal_config.name)
        test_set_config = {"name": "nonexistent", "on_missing": "clean_only"}
        with pytest.raises(TestSetError) as exc_info:
            manager.resolve_test_set(
                meal_name=meal_config.name,
                test_set_config=test_set_config,
                meal_config=meal_config,
            )
        assert "not found" in str(exc_info.value)
        assert "clean_only" in str(exc_info.value)

    def test_strict_mode_valid_test_set_found_returned_directly(self, env):
        manager, config = env
        meal_config = _make_meal_config(
            data_id="matching_id",
            pdf_paths=["reports/report_0.pdf"],
        )
        _create_meal_dir(config, meal_config.name)
        test_set_data = {
            "metadata": {
                "name": "valid_set",
                "meal_id": "matching_id",
                "created_at": "2026-04-20T10:00:00",
                "updated_at": "2026-04-20T10:00:00",
            },
            "questions": [
                {"id": 1, "question": "Q1", "source_files": ["reports/report_0.pdf"]},
            ],
        }
        manager.save_test_set(meal_config.name, test_set_data)
        test_set_config = {"name": "valid_set", "on_missing": "strict"}
        result = manager.resolve_test_set(
            meal_name=meal_config.name,
            test_set_config=test_set_config,
            meal_config=meal_config,
        )
        assert result["metadata"]["name"] == "valid_set"

    def test_strict_mode_invalid_test_set_raises_value_error(self, env):
        manager, config = env
        meal_config = _make_meal_config(
            data_id="current_meal",
            pdf_paths=["reports/report_0.pdf"],
        )
        _create_meal_dir(config, meal_config.name)
        test_set_data = {
            "metadata": {
                "name": "invalid_set",
                "meal_id": "old_meal_id",
                "created_at": "2026-04-20T10:00:00",
                "updated_at": "2026-04-20T10:00:00",
            },
            "questions": [
                {"id": 1, "question": "Q1", "source_files": ["missing.pdf"]},
            ],
        }
        manager.save_test_set(meal_config.name, test_set_data)
        test_set_config = {"name": "invalid_set", "on_missing": "strict"}
        with pytest.raises(TestSetError) as exc_info:
            manager.resolve_test_set(
                meal_name=meal_config.name,
                test_set_config=test_set_config,
                meal_config=meal_config,
            )
        assert "invalid" in str(exc_info.value).lower()
        assert "strict" in str(exc_info.value)

    def test_strict_mode_not_found_raises_value_error(self, env):
        manager, config = env
        meal_config = _make_meal_config(
            data_id="current_meal",
            pdf_paths=["reports/report_0.pdf"],
        )
        _create_meal_dir(config, meal_config.name)
        test_set_config = {"name": "nonexistent", "on_missing": "strict"}
        with pytest.raises(TestSetError) as exc_info:
            manager.resolve_test_set(
                meal_name=meal_config.name,
                test_set_config=test_set_config,
                meal_config=meal_config,
            )
        assert "not found" in str(exc_info.value)
        assert "strict" in str(exc_info.value)


class TestMergeTestSets:
    @pytest.fixture
    def env(self, tmp_path):
        config = _make_config(tmp_path)
        manager = TestSetManager(config)
        return manager, config

    def test_merge_two_test_sets_without_duplicates(self, env):
        manager, config = env
        _create_meal_dir(config, "meal_a")
        _create_meal_dir(config, "meal_b")
        _create_meal_dir(config, "target_meal")

        test_set_a = {
            "metadata": {
                "name": "set_a",
                "meal_id": "id_a",
                "created_at": "2026-04-20T10:00:00",
                "updated_at": "2026-04-20T10:00:00",
            },
            "questions": [
                {
                    "id": "q001",
                    "question": "What is revenue?",
                    "source_files": ["reports/report_0.pdf"],
                },
                {
                    "id": "q002",
                    "question": "What is profit?",
                    "source_files": ["reports/report_0.pdf"],
                },
            ],
        }
        test_set_b = {
            "metadata": {
                "name": "set_b",
                "meal_id": "id_b",
                "created_at": "2026-04-20T10:00:00",
                "updated_at": "2026-04-20T10:00:00",
            },
            "questions": [
                {
                    "id": "q001",
                    "question": "What is cash flow?",
                    "source_files": ["reports/report_1.pdf"],
                },
                {
                    "id": "q002",
                    "question": "What is debt?",
                    "source_files": ["reports/report_1.pdf"],
                },
            ],
        }

        manager.save_test_set("meal_a", test_set_a)
        manager.save_test_set("meal_b", test_set_b)

        target_meal_config = _make_meal_config(
            data_id="target_id",
            pdf_paths=["reports/report_0.pdf", "reports/report_1.pdf"],
        )

        source_specs = [
            {"meal": "meal_a", "test_set": "set_a"},
            {"meal": "meal_b", "test_set": "set_b"},
        ]

        result = manager.merge_test_sets(
            source_specs=source_specs,
            target_meal_name="target_meal",
            target_meal_config=target_meal_config,
            name="merged_set",
        )

        assert result["metadata"]["name"] == "merged_set"
        assert len(result["questions"]) == 4
        question_ids = [q["id"] for q in result["questions"]]
        assert question_ids == ["q001", "q002", "q003", "q004"]

        question_texts = {q["question"] for q in result["questions"]}
        assert "What is revenue?" in question_texts
        assert "What is profit?" in question_texts
        assert "What is cash flow?" in question_texts
        assert "What is debt?" in question_texts

    def test_merge_test_sets_with_duplicates(self, env):
        manager, config = env
        _create_meal_dir(config, "meal_a")
        _create_meal_dir(config, "meal_b")
        _create_meal_dir(config, "target_meal")

        test_set_a = {
            "metadata": {
                "name": "set_a",
                "meal_id": "id_a",
                "created_at": "2026-04-20T10:00:00",
                "updated_at": "2026-04-20T10:00:00",
            },
            "questions": [
                {
                    "id": "q001",
                    "question": "What is revenue?",
                    "source_files": ["reports/report_0.pdf"],
                },
                {
                    "id": "q002",
                    "question": "What is profit?",
                    "source_files": ["reports/report_0.pdf"],
                },
            ],
        }
        test_set_b = {
            "metadata": {
                "name": "set_b",
                "meal_id": "id_b",
                "created_at": "2026-04-20T10:00:00",
                "updated_at": "2026-04-20T10:00:00",
            },
            "questions": [
                {
                    "id": "q001",
                    "question": "What is revenue?",
                    "source_files": ["reports/report_0.pdf"],
                },
                {
                    "id": "q002",
                    "question": "What is cash flow?",
                    "source_files": ["reports/report_0.pdf"],
                },
            ],
        }

        manager.save_test_set("meal_a", test_set_a)
        manager.save_test_set("meal_b", test_set_b)

        target_meal_config = _make_meal_config(
            data_id="target_id",
            pdf_paths=["reports/report_0.pdf"],
        )

        source_specs = [
            {"meal": "meal_a", "test_set": "set_a"},
            {"meal": "meal_b", "test_set": "set_b"},
        ]

        result = manager.merge_test_sets(
            source_specs=source_specs,
            target_meal_name="target_meal",
            target_meal_config=target_meal_config,
            name="merged_dedup",
        )

        assert len(result["questions"]) == 3
        question_texts = [q["question"] for q in result["questions"]]
        assert question_texts.count("What is revenue?") == 1
        assert "What is profit?" in question_texts
        assert "What is cash flow?" in question_texts

        assert result["metadata"]["composition"]["dedup_count"] == 1
        assert result["metadata"]["composition"]["original_count"] == 4
        assert result["metadata"]["composition"]["final_count"] == 3

    def test_merge_test_sets_with_invalid_questions(self, env):
        manager, config = env
        _create_meal_dir(config, "meal_a")
        _create_meal_dir(config, "target_meal")

        test_set_a = {
            "metadata": {
                "name": "set_a",
                "meal_id": "id_a",
                "created_at": "2026-04-20T10:00:00",
                "updated_at": "2026-04-20T10:00:00",
            },
            "questions": [
                {
                    "id": "q001",
                    "question": "Valid question?",
                    "source_files": ["reports/report_0.pdf"],
                },
                {
                    "id": "q002",
                    "question": "Invalid question?",
                    "source_files": ["reports/missing.pdf"],
                },
                {
                    "id": "q003",
                    "question": "Another valid?",
                    "source_files": ["reports/report_0.pdf"],
                },
            ],
        }

        manager.save_test_set("meal_a", test_set_a)

        target_meal_config = _make_meal_config(
            data_id="target_id",
            pdf_paths=["reports/report_0.pdf"],
        )

        source_specs = [{"meal": "meal_a", "test_set": "set_a"}]

        result = manager.merge_test_sets(
            source_specs=source_specs,
            target_meal_name="target_meal",
            target_meal_config=target_meal_config,
            name="merged_valid",
        )

        assert len(result["questions"]) == 2
        question_texts = {q["question"] for q in result["questions"]}
        assert "Valid question?" in question_texts
        assert "Another valid?" in question_texts
        assert "Invalid question?" not in question_texts

        assert result["metadata"]["audit_log"][0]["invalid_count"] == 1

    def test_merge_test_sets_composition_metadata(self, env):
        manager, config = env
        _create_meal_dir(config, "meal_a")
        _create_meal_dir(config, "meal_b")
        _create_meal_dir(config, "target_meal")

        test_set_a = {
            "metadata": {
                "name": "set_a",
                "meal_id": "id_a",
                "created_at": "2026-04-20T10:00:00",
                "updated_at": "2026-04-20T10:00:00",
            },
            "questions": [
                {
                    "id": "q001",
                    "question": "Q1",
                    "source_files": ["reports/report_0.pdf"],
                },
            ],
        }
        test_set_b = {
            "metadata": {
                "name": "set_b",
                "meal_id": "id_b",
                "created_at": "2026-04-20T10:00:00",
                "updated_at": "2026-04-20T10:00:00",
            },
            "questions": [
                {
                    "id": "q001",
                    "question": "Q2",
                    "source_files": ["reports/report_0.pdf"],
                },
            ],
        }

        manager.save_test_set("meal_a", test_set_a)
        manager.save_test_set("meal_b", test_set_b)

        target_meal_config = _make_meal_config(
            data_id="target_id",
            pdf_paths=["reports/report_0.pdf"],
        )

        source_specs = [
            {"meal": "meal_a", "test_set": "set_a"},
            {"meal": "meal_b", "test_set": "set_b"},
        ]

        result = manager.merge_test_sets(
            source_specs=source_specs,
            target_meal_name="target_meal",
            target_meal_config=target_meal_config,
            name="merged_comp",
        )

        composition = result["metadata"]["composition"]
        assert composition["type"] == "merged"
        assert len(composition["sources"]) == 2
        assert {"meal": "meal_a", "test_set": "set_a"} in composition["sources"]
        assert {"meal": "meal_b", "test_set": "set_b"} in composition["sources"]
        assert composition["original_count"] == 2
        assert composition["final_count"] == 2
        assert composition["dedup_count"] == 0

    def test_merge_test_sets_audit_log(self, env):
        manager, config = env
        _create_meal_dir(config, "meal_a")
        _create_meal_dir(config, "target_meal")

        test_set_a = {
            "metadata": {
                "name": "set_a",
                "meal_id": "id_a",
                "created_at": "2026-04-20T10:00:00",
                "updated_at": "2026-04-20T10:00:00",
            },
            "questions": [
                {
                    "id": "q001",
                    "question": "Q1",
                    "source_files": ["reports/report_0.pdf"],
                },
                {
                    "id": "q002",
                    "question": "Q2",
                    "source_files": ["reports/missing.pdf"],
                },
            ],
        }

        manager.save_test_set("meal_a", test_set_a)

        target_meal_config = _make_meal_config(
            data_id="target_id",
            pdf_paths=["reports/report_0.pdf"],
        )

        source_specs = [{"meal": "meal_a", "test_set": "set_a"}]

        result = manager.merge_test_sets(
            source_specs=source_specs,
            target_meal_name="target_meal",
            target_meal_config=target_meal_config,
            name="merged_audit",
        )

        audit_log = result["metadata"]["audit_log"]
        assert len(audit_log) == 1

        entry = audit_log[0]
        assert entry["event"] == "merged"
        assert entry["sources"] == [{"meal": "meal_a", "test_set": "set_a"}]
        assert entry["dedup_count"] == 0
        assert entry["invalid_count"] == 1
        assert "timestamp" in entry

    def test_merge_test_sets_auto_name(self, env):
        manager, config = env
        _create_meal_dir(config, "meal_a")
        _create_meal_dir(config, "target_meal")

        test_set_a = {
            "metadata": {
                "name": "original_set",
                "meal_id": "id_a",
                "created_at": "2026-04-20T10:00:00",
                "updated_at": "2026-04-20T10:00:00",
            },
            "questions": [
                {
                    "id": "q001",
                    "question": "Q1",
                    "source_files": ["reports/report_0.pdf"],
                },
            ],
        }

        manager.save_test_set("meal_a", test_set_a)

        target_meal_config = _make_meal_config(
            data_id="target_id",
            pdf_paths=["reports/report_0.pdf"],
        )

        source_specs = [{"meal": "meal_a", "test_set": "original_set"}]

        result = manager.merge_test_sets(
            source_specs=source_specs,
            target_meal_name="target_meal",
            target_meal_config=target_meal_config,
        )

        assert result["metadata"]["name"] == "original_set_merged"

    def test_merge_test_sets_source_not_found(self, env):
        manager, config = env
        _create_meal_dir(config, "target_meal")

        target_meal_config = _make_meal_config(
            data_id="target_id",
            pdf_paths=["reports/report_0.pdf"],
        )

        source_specs = [{"meal": "nonexistent_meal", "test_set": "nonexistent_set"}]

        with pytest.raises(TestSetError) as exc_info:
            manager.merge_test_sets(
                source_specs=source_specs,
                target_meal_name="target_meal",
                target_meal_config=target_meal_config,
            )
        assert "not found" in str(exc_info.value)

    def test_merge_test_sets_empty_source_specs(self, env):
        manager, config = env
        _create_meal_dir(config, "target_meal")

        target_meal_config = _make_meal_config(
            data_id="target_id",
            pdf_paths=["reports/report_0.pdf"],
        )

        with pytest.raises(TestSetError) as exc_info:
            manager.merge_test_sets(
                source_specs=[],
                target_meal_name="target_meal",
                target_meal_config=target_meal_config,
            )
        assert "source_specs cannot be empty" in str(exc_info.value)

    def test_merge_test_sets_invalid_source_spec(self, env):
        manager, config = env
        _create_meal_dir(config, "target_meal")

        target_meal_config = _make_meal_config(
            data_id="target_id",
            pdf_paths=["reports/report_0.pdf"],
        )

        with pytest.raises(TestSetError) as exc_info:
            manager.merge_test_sets(
                source_specs=[{"meal": "only_meal"}],
                target_meal_name="target_meal",
                target_meal_config=target_meal_config,
            )
        assert "Invalid source spec" in str(exc_info.value)

    def test_merge_test_sets_irrelevant_questions_preserved(self, env):
        manager, config = env
        _create_meal_dir(config, "meal_a")
        _create_meal_dir(config, "target_meal")

        test_set_a = {
            "metadata": {
                "name": "set_a",
                "meal_id": "id_a",
                "created_at": "2026-04-20T10:00:00",
                "updated_at": "2026-04-20T10:00:00",
            },
            "questions": [
                {
                    "id": "q001",
                    "question": "Normal question?",
                    "source_files": ["reports/report_0.pdf"],
                },
                {
                    "id": "q002",
                    "question": "Irrelevant question?",
                    "question_type": "irrelevant",
                    "source_files": ["reports/nonexistent.pdf"],
                },
            ],
        }

        manager.save_test_set("meal_a", test_set_a)

        target_meal_config = _make_meal_config(
            data_id="target_id",
            pdf_paths=["reports/report_0.pdf"],
        )

        source_specs = [{"meal": "meal_a", "test_set": "set_a"}]

        result = manager.merge_test_sets(
            source_specs=source_specs,
            target_meal_name="target_meal",
            target_meal_config=target_meal_config,
            name="merged_irrelevant",
        )

        assert len(result["questions"]) == 2
        question_types = {q.get("question_type", "simple") for q in result["questions"]}
        assert "irrelevant" in question_types

    def test_merge_test_sets_saves_to_target_meal(self, env):
        manager, config = env
        _create_meal_dir(config, "meal_a")
        _create_meal_dir(config, "target_meal")

        test_set_a = {
            "metadata": {
                "name": "set_a",
                "meal_id": "id_a",
                "created_at": "2026-04-20T10:00:00",
                "updated_at": "2026-04-20T10:00:00",
            },
            "questions": [
                {
                    "id": "q001",
                    "question": "Q1",
                    "source_files": ["reports/report_0.pdf"],
                },
            ],
        }

        manager.save_test_set("meal_a", test_set_a)

        target_meal_config = _make_meal_config(
            data_id="target_id",
            pdf_paths=["reports/report_0.pdf"],
        )

        source_specs = [{"meal": "meal_a", "test_set": "set_a"}]

        manager.merge_test_sets(
            source_specs=source_specs,
            target_meal_name="target_meal",
            target_meal_config=target_meal_config,
            name="saved_merged",
        )

        loaded = manager.load_test_set("target_meal", "saved_merged")
        assert loaded is not None
        assert loaded["metadata"]["name"] == "saved_merged"
        assert len(loaded["questions"]) == 1

    def test_merge_test_sets_question_id_reassigned(self, env):
        manager, config = env
        _create_meal_dir(config, "meal_a")
        _create_meal_dir(config, "target_meal")

        test_set_a = {
            "metadata": {
                "name": "set_a",
                "meal_id": "id_a",
                "created_at": "2026-04-20T10:00:00",
                "updated_at": "2026-04-20T10:00:00",
            },
            "questions": [
                {
                    "id": "old_id_1",
                    "question": "Q1",
                    "source_files": ["reports/report_0.pdf"],
                },
                {
                    "id": "old_id_2",
                    "question": "Q2",
                    "source_files": ["reports/report_0.pdf"],
                },
                {
                    "id": "old_id_3",
                    "question": "Q3",
                    "source_files": ["reports/report_0.pdf"],
                },
            ],
        }

        manager.save_test_set("meal_a", test_set_a)

        target_meal_config = _make_meal_config(
            data_id="target_id",
            pdf_paths=["reports/report_0.pdf"],
        )

        source_specs = [{"meal": "meal_a", "test_set": "set_a"}]

        result = manager.merge_test_sets(
            source_specs=source_specs,
            target_meal_name="target_meal",
            target_meal_config=target_meal_config,
            name="reassigned_ids",
        )

        question_ids = [q["id"] for q in result["questions"]]
        assert question_ids == ["q001", "q002", "q003"]


class TestBoundaryConditions:
    @pytest.fixture
    def env(self, tmp_path):
        config = _make_config(tmp_path)
        manager = TestSetManager(config)
        return manager, config

    def test_save_test_set_missing_metadata_key_raises_key_error(self, env):
        manager, config = env
        _create_meal_dir(config, "my_meal")
        data = {"questions": []}
        with pytest.raises(KeyError):
            manager.save_test_set("my_meal", data)

    def test_save_test_set_missing_name_in_metadata_raises_key_error(self, env):
        manager, config = env
        _create_meal_dir(config, "my_meal")
        data = {"metadata": {"meal_id": "abc"}, "questions": []}
        with pytest.raises(KeyError):
            manager.save_test_set("my_meal", data)

    def test_find_by_name_corrupted_json_returns_none(self, env):
        manager, config = env
        _create_meal_dir(config, "my_meal")
        test_sets_dir = Path(config["meals"]["dir"]) / "my_meal" / "test_sets"
        bad_file = test_sets_dir / "corrupted.json"
        with open(bad_file, "w", encoding="utf-8") as f:
            f.write("not valid json")
        result = manager.find_by_name("my_meal", "corrupted")
        assert result is None

    def test_list_test_sets_corrupted_json_skipped(self, env):
        manager, config = env
        _create_meal_dir(config, "my_meal")
        test_sets_dir = Path(config["meals"]["dir"]) / "my_meal" / "test_sets"
        bad_file = test_sets_dir / "corrupted.json"
        with open(bad_file, "w", encoding="utf-8") as f:
            f.write("not valid json")
        manager.save_test_set("my_meal", _make_test_set_data("good_set"))
        result = manager.list_test_sets("my_meal")
        assert len(result) == 1
        assert result[0]["name"] == "good_set"

    def test_load_test_set_corrupted_json_raises_exception(self, env):
        manager, config = env
        _create_meal_dir(config, "my_meal")
        test_sets_dir = Path(config["meals"]["dir"]) / "my_meal" / "test_sets"
        bad_file = test_sets_dir / "corrupted.json"
        with open(bad_file, "w", encoding="utf-8") as f:
            f.write("not valid json")
        with pytest.raises(json.JSONDecodeError):
            manager.load_test_set("my_meal", "corrupted")

    def test_validate_test_set_missing_metadata_key_raises_key_error(self, env):
        manager, config = env
        meal_config = _make_meal_config(data_id="abc")
        test_set_data = {"questions": []}
        with pytest.raises(KeyError):
            manager.validate_test_set(test_set_data, meal_config)

    def test_derive_test_set_name_none_config(self, env):
        manager, config = env
        name = manager._derive_test_set_name(None)
        assert name.startswith("document_n")

    def test_derive_test_set_name_with_strategy(self, env):
        manager, config = env
        generation_config = {"strategy": "chunk", "num_questions": 25}
        name = manager._derive_test_set_name(generation_config)
        assert name == "chunk_n25"

    def test_derive_test_set_name_missing_strategy_defaults_to_document(self, env):
        manager, config = env
        generation_config = {"num_questions": 15}
        name = manager._derive_test_set_name(generation_config)
        assert name == "document_n15"

    def test_derive_test_set_name_missing_num_questions_defaults_to_10(self, env):
        manager, config = env
        generation_config = {"strategy": "random"}
        name = manager._derive_test_set_name(generation_config)
        assert name == "random_n10"

    def test_resolve_test_set_auto_derived_name(self, env):
        manager, config = env
        meal_config = _make_meal_config(
            data_id="current_meal",
            pdf_paths=["reports/report_0.pdf"],
        )
        _create_meal_dir(config, meal_config.name)

        class MockGenerator:
            def generate_document_based_questions(
                self, meal_name, num_questions, name, llm_preset, token_tracker
            ):
                return {
                    "metadata": {
                        "name": name,
                        "meal_id": "current_meal",
                        "created_at": "2026-04-20T10:00:00",
                        "updated_at": "2026-04-20T10:00:00",
                    },
                    "questions": [
                        {"id": i, "question": f"Q{i}"} for i in range(num_questions)
                    ],
                }

        test_set_config = {
            "on_missing": "auto",
            "generation": {"strategy": "document", "num_questions": 5},
        }
        result = manager.resolve_test_set(
            meal_name=meal_config.name,
            test_set_config=test_set_config,
            meal_config=meal_config,
            generator=MockGenerator(),
        )
        assert result["metadata"]["name"] == "document_n5"

    def test_resolve_test_set_auto_not_found_without_generator_raises_error(self, env):
        manager, config = env
        meal_config = _make_meal_config(
            data_id="current_meal",
            pdf_paths=["reports/report_0.pdf"],
        )
        _create_meal_dir(config, meal_config.name)
        test_set_config = {"name": "nonexistent", "on_missing": "auto"}
        with pytest.raises(TestSetError, match="no generator provided"):
            manager.resolve_test_set(
                meal_name=meal_config.name,
                test_set_config=test_set_config,
                meal_config=meal_config,
            )

    def test_update_meal_id_persists_to_disk(self, env):
        manager, config = env
        _create_meal_dir(config, "my_meal")
        data = _make_test_set_data("set_a", meal_id="old_id")
        manager.save_test_set("my_meal", data)
        manager.update_meal_id("my_meal", "set_a", "new_id_123")
        loaded = manager.load_test_set("my_meal", "set_a")
        assert loaded["metadata"]["meal_id"] == "new_id_123"

    def test_check_questions_validity_empty_questions(self, env):
        manager, config = env
        meal_config = _make_meal_config(data_id="abc")
        result = manager._check_questions_validity([], meal_config)
        assert result == []

    def test_check_questions_validity_irrelevant_type_skipped(self, env):
        manager, config = env
        meal_config = _make_meal_config(data_id="abc")
        questions = [
            {
                "id": 1,
                "question_type": "irrelevant",
                "source_files": ["nonexistent.pdf"],
            },
        ]
        result = manager._check_questions_validity(questions, meal_config)
        assert result == []

    def test_check_questions_validity_empty_source_files_skipped(self, env):
        manager, config = env
        meal_config = _make_meal_config(data_id="abc")
        questions = [
            {"id": 1, "source_files": []},
            {"id": 2},
        ]
        result = manager._check_questions_validity(questions, meal_config)
        assert result == []
