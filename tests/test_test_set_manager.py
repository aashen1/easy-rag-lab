import json
from pathlib import Path

import pytest

from src.test_set_manager import TestSetManager, TestSetMetadata


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
        with open(path, "r", encoding="utf-8") as f:
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
        with pytest.raises(FileNotFoundError):
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
        with pytest.raises(FileNotFoundError):
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
