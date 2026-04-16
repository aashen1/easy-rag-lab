import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from src.experiment import (
    ExperimentConfig,
    ExperimentManager,
    ExperimentResult,
    deep_merge,
    get_test_set_config,
    get_variant_config,
    list_variants,
    load_experiment_config,
    merge_config,
)


class TestExperimentConfig:
    def _make_config_dict(self, **overrides) -> dict:
        defaults = {
            "name": "test_experiment",
            "description": "Test experiment description",
            "data": {
                "meal": "meal_baseline",
                "create_if_missing": {
                    "sample_ratio": 0.1,
                    "seed": 42,
                },
            },
            "test_sets": [
                {
                    "strategy": "factual",
                    "num_questions": 20,
                    "seed": 100,
                }
            ],
            "variants": [
                {
                    "name": "chunk_512_overlap_0",
                    "description": "chunk_size=512, overlap=0",
                    "config_overrides": {
                        "chunker": {
                            "chunk_size": 512,
                            "chunk_overlap": 0,
                        }
                    },
                }
            ],
            "evaluation": {
                "llm_preset": "default",
                "metrics": {
                    "retrieval": ["hit_rate", "mrr", "ndcg"],
                },
            },
            "llm": {
                "question_generation": "sonnet",
                "answering": "default",
            },
        }
        defaults.update(overrides)
        return defaults

    def test_creation(self):
        data = self._make_config_dict()
        config = ExperimentConfig.from_dict(data)
        assert config.name == "test_experiment"
        assert config.description == "Test experiment description"
        assert config.data["meal"] == "meal_baseline"
        assert len(config.test_sets) == 1
        assert len(config.variants) == 1

    def test_to_dict(self):
        data = self._make_config_dict()
        config = ExperimentConfig.from_dict(data)
        d = config.to_dict()
        assert d["name"] == "test_experiment"
        assert d["description"] == "Test experiment description"
        assert d["data"]["meal"] == "meal_baseline"
        assert len(d["test_sets"]) == 1
        assert len(d["variants"]) == 1

    def test_from_dict_missing_required_field(self):
        data = self._make_config_dict()
        del data["name"]
        with pytest.raises(ValueError, match="Missing required fields"):
            ExperimentConfig.from_dict(data)

    def test_from_dict_missing_multiple_fields(self):
        data = {"name": "test"}
        with pytest.raises(ValueError, match="Missing required fields"):
            ExperimentConfig.from_dict(data)

    def test_validate_valid_config(self):
        data = self._make_config_dict()
        config = ExperimentConfig.from_dict(data)
        errors = config.validate()
        assert errors == []

    def test_validate_empty_name(self):
        data = self._make_config_dict(name="")
        config = ExperimentConfig.from_dict(data)
        errors = config.validate()
        assert "Experiment name cannot be empty" in errors

    def test_validate_empty_description(self):
        data = self._make_config_dict(description="")
        config = ExperimentConfig.from_dict(data)
        errors = config.validate()
        assert "Experiment description cannot be empty" in errors

    def test_validate_missing_meal(self):
        data = self._make_config_dict()
        del data["data"]["meal"]
        config = ExperimentConfig.from_dict(data)
        errors = config.validate()
        assert "Data configuration must include 'meal' field" in errors

    def test_validate_empty_test_sets(self):
        data = self._make_config_dict(test_sets=[])
        config = ExperimentConfig.from_dict(data)
        errors = config.validate()
        assert "At least one test set must be defined" in errors

    def test_validate_test_set_missing_strategy(self):
        data = self._make_config_dict()
        data["test_sets"] = [{"num_questions": 10}]
        config = ExperimentConfig.from_dict(data)
        errors = config.validate()
        assert "Test set 0 missing 'strategy' field" in errors

    def test_validate_test_set_missing_num_questions(self):
        data = self._make_config_dict()
        data["test_sets"] = [{"strategy": "factual"}]
        config = ExperimentConfig.from_dict(data)
        errors = config.validate()
        assert "Test set 0 missing 'num_questions' field" in errors

    def test_validate_empty_variants(self):
        data = self._make_config_dict(variants=[])
        config = ExperimentConfig.from_dict(data)
        errors = config.validate()
        assert "At least one variant must be defined" in errors

    def test_validate_variant_missing_name(self):
        data = self._make_config_dict()
        data["variants"] = [{"description": "test"}]
        config = ExperimentConfig.from_dict(data)
        errors = config.validate()
        assert "Variant 0 missing 'name' field" in errors

    def test_validate_missing_metrics(self):
        data = self._make_config_dict()
        del data["evaluation"]["metrics"]
        config = ExperimentConfig.from_dict(data)
        errors = config.validate()
        assert "Evaluation configuration must include 'metrics' field" in errors

    def test_default_llm_field(self):
        data = self._make_config_dict()
        del data["llm"]
        config = ExperimentConfig.from_dict(data)
        assert config.llm == {}


class TestDeepMerge:
    def test_simple_override(self):
        base = {"a": 1, "b": 2}
        override = {"b": 3, "c": 4}
        result = deep_merge(base, override)
        assert result == {"a": 1, "b": 3, "c": 4}

    def test_nested_merge(self):
        base = {
            "chunker": {
                "chunk_size": 512,
                "chunk_overlap": 0,
            },
            "embedding": {
                "model_name": "model_a",
            },
        }
        override = {
            "chunker": {
                "chunk_overlap": 100,
            },
        }
        result = deep_merge(base, override)
        assert result["chunker"]["chunk_size"] == 512
        assert result["chunker"]["chunk_overlap"] == 100
        assert result["embedding"]["model_name"] == "model_a"

    def test_deep_nested_merge(self):
        base = {
            "level1": {
                "level2": {
                    "level3": {
                        "value": "original",
                        "other": "keep",
                    }
                }
            }
        }
        override = {
            "level1": {
                "level2": {
                    "level3": {
                        "value": "overridden",
                    }
                }
            }
        }
        result = deep_merge(base, override)
        assert result["level1"]["level2"]["level3"]["value"] == "overridden"
        assert result["level1"]["level2"]["level3"]["other"] == "keep"

    def test_non_dict_values_not_merged(self):
        base = {"list": [1, 2, 3], "string": "original"}
        override = {"list": [4, 5], "string": "overridden"}
        result = deep_merge(base, override)
        assert result["list"] == [4, 5]
        assert result["string"] == "overridden"

    def test_empty_override(self):
        base = {"a": 1, "b": 2}
        override = {}
        result = deep_merge(base, override)
        assert result == {"a": 1, "b": 2}

    def test_empty_base(self):
        base = {}
        override = {"a": 1, "b": 2}
        result = deep_merge(base, override)
        assert result == {"a": 1, "b": 2}

    def test_original_not_modified(self):
        base = {"a": {"b": 1}}
        override = {"a": {"c": 2}}
        result = deep_merge(base, override)
        assert "c" not in base["a"]
        assert "c" in result["a"]


class TestMergeConfig:
    def _make_system_config(self) -> dict:
        return {
            "chunker": {
                "chunk_size": 256,
                "chunk_overlap": 50,
            },
            "embedding": {
                "model_name": "model_a",
                "device": "cpu",
            },
            "retrieval": {
                "top_k": 5,
            },
        }

    def _make_experiment_config(self) -> ExperimentConfig:
        return ExperimentConfig(
            name="test",
            description="test",
            data={"meal": "test_meal"},
            test_sets=[{"strategy": "factual", "num_questions": 10}],
            variants=[
                {
                    "name": "variant_a",
                    "config_overrides": {
                        "chunker": {
                            "chunk_size": 512,
                        }
                    },
                }
            ],
            evaluation={"metrics": {"retrieval": ["hit_rate"]}},
        )

    def test_merge_without_variant(self):
        system_config = self._make_system_config()
        exp_config = self._make_experiment_config()
        result = merge_config(system_config, exp_config)
        assert result["chunker"]["chunk_size"] == 256
        assert result["chunker"]["chunk_overlap"] == 50

    def test_merge_with_variant(self):
        system_config = self._make_system_config()
        exp_config = self._make_experiment_config()
        variant = exp_config.variants[0]
        result = merge_config(system_config, exp_config, variant)
        assert result["chunker"]["chunk_size"] == 512
        assert result["chunker"]["chunk_overlap"] == 50
        assert result["embedding"]["model_name"] == "model_a"

    def test_original_config_not_modified(self):
        system_config = self._make_system_config()
        exp_config = self._make_experiment_config()
        variant = exp_config.variants[0]
        original_chunk_size = system_config["chunker"]["chunk_size"]
        merge_config(system_config, exp_config, variant)
        assert system_config["chunker"]["chunk_size"] == original_chunk_size


class TestLoadExperimentConfig:
    def test_load_valid_config(self):
        config_data = {
            "name": "test_exp",
            "description": "Test experiment",
            "data": {"meal": "test_meal"},
            "test_sets": [{"strategy": "factual", "num_questions": 10}],
            "variants": [{"name": "v1"}],
            "evaluation": {"metrics": {"retrieval": ["hit_rate"]}},
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False, encoding="utf-8") as f:
            yaml.dump(config_data, f)
            temp_path = f.name

        try:
            config = load_experiment_config(temp_path)
            assert config.name == "test_exp"
            assert config.description == "Test experiment"
        finally:
            Path(temp_path).unlink()

    def test_load_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            load_experiment_config("nonexistent_file.yaml")

    def test_load_invalid_yaml(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False, encoding="utf-8") as f:
            f.write("invalid: yaml: content: [")
            temp_path = f.name

        try:
            with pytest.raises(yaml.YAMLError):
                load_experiment_config(temp_path)
        finally:
            Path(temp_path).unlink()

    def test_load_empty_file(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False, encoding="utf-8") as f:
            f.write("")
            temp_path = f.name

        try:
            with pytest.raises(ValueError, match="Empty configuration file"):
                load_experiment_config(temp_path)
        finally:
            Path(temp_path).unlink()

    def test_load_non_dict_config(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False, encoding="utf-8") as f:
            yaml.dump(["item1", "item2"], f)
            temp_path = f.name

        try:
            with pytest.raises(ValueError, match="must be a dictionary"):
                load_experiment_config(temp_path)
        finally:
            Path(temp_path).unlink()

    def test_load_invalid_config_validation(self):
        config_data = {
            "name": "",
            "description": "Test",
            "data": {"meal": "test"},
            "test_sets": [{"strategy": "factual", "num_questions": 10}],
            "variants": [{"name": "v1"}],
            "evaluation": {"metrics": {"retrieval": ["hit_rate"]}},
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False, encoding="utf-8") as f:
            yaml.dump(config_data, f)
            temp_path = f.name

        try:
            with pytest.raises(ValueError, match="validation failed"):
                load_experiment_config(temp_path)
        finally:
            Path(temp_path).unlink()


class TestGetVariantConfig:
    def _make_configs(self):
        system_config = {
            "chunker": {"chunk_size": 256, "chunk_overlap": 50},
            "embedding": {"model_name": "model_a"},
        }
        experiment_config = ExperimentConfig(
            name="test",
            description="test",
            data={"meal": "test"},
            test_sets=[{"strategy": "factual", "num_questions": 10}],
            variants=[
                {
                    "name": "variant_a",
                    "config_overrides": {"chunker": {"chunk_size": 512}},
                },
                {
                    "name": "variant_b",
                    "config_overrides": {"chunker": {"chunk_size": 1024, "chunk_overlap": 100}},
                },
            ],
            evaluation={"metrics": {"retrieval": ["hit_rate"]}},
        )
        return system_config, experiment_config

    def test_get_variant_config_found(self):
        system_config, experiment_config = self._make_configs()
        result = get_variant_config(system_config, experiment_config, "variant_a")
        assert result["chunker"]["chunk_size"] == 512
        assert result["chunker"]["chunk_overlap"] == 50

    def test_get_variant_config_different_variant(self):
        system_config, experiment_config = self._make_configs()
        result = get_variant_config(system_config, experiment_config, "variant_b")
        assert result["chunker"]["chunk_size"] == 1024
        assert result["chunker"]["chunk_overlap"] == 100

    def test_get_variant_config_not_found(self):
        system_config, experiment_config = self._make_configs()
        with pytest.raises(ValueError, match="not found"):
            get_variant_config(system_config, experiment_config, "nonexistent")


class TestListVariants:
    def test_list_variants(self):
        config = ExperimentConfig(
            name="test",
            description="test",
            data={"meal": "test"},
            test_sets=[{"strategy": "factual", "num_questions": 10}],
            variants=[
                {"name": "variant_a"},
                {"name": "variant_b"},
                {"name": "variant_c"},
            ],
            evaluation={"metrics": {"retrieval": ["hit_rate"]}},
        )
        names = list_variants(config)
        assert names == ["variant_a", "variant_b", "variant_c"]

    def test_list_variants_unnamed(self):
        config = ExperimentConfig(
            name="test",
            description="test",
            data={"meal": "test"},
            test_sets=[{"strategy": "factual", "num_questions": 10}],
            variants=[
                {"description": "no name"},
                {"name": "named"},
            ],
            evaluation={"metrics": {"retrieval": ["hit_rate"]}},
        )
        names = list_variants(config)
        assert names == ["unnamed", "named"]


class TestGetTestSetConfig:
    def _make_config(self) -> ExperimentConfig:
        return ExperimentConfig(
            name="test",
            description="test",
            data={"meal": "test"},
            test_sets=[
                {"strategy": "factual", "num_questions": 10, "seed": 1},
                {"strategy": "boundary", "num_questions": 15, "seed": 2},
            ],
            variants=[{"name": "v1"}],
            evaluation={"metrics": {"retrieval": ["hit_rate"]}},
        )

    def test_get_first_test_set(self):
        config = self._make_config()
        test_set = get_test_set_config(config, 0)
        assert test_set["strategy"] == "factual"
        assert test_set["num_questions"] == 10

    def test_get_second_test_set(self):
        config = self._make_config()
        test_set = get_test_set_config(config, 1)
        assert test_set["strategy"] == "boundary"
        assert test_set["num_questions"] == 15

    def test_get_test_set_default_index(self):
        config = self._make_config()
        test_set = get_test_set_config(config)
        assert test_set["strategy"] == "factual"

    def test_get_test_set_out_of_range(self):
        config = self._make_config()
        with pytest.raises(IndexError, match="out of range"):
            get_test_set_config(config, 10)

    def test_get_test_set_negative_index(self):
        config = self._make_config()
        with pytest.raises(IndexError, match="out of range"):
            get_test_set_config(config, -1)


class TestExperimentResult:
    def _make_config(self) -> ExperimentConfig:
        return ExperimentConfig(
            name="test_experiment",
            description="Test experiment description",
            data={"meal": "test_meal"},
            test_sets=[{"strategy": "factual", "num_questions": 10}],
            variants=[{"name": "variant_a"}],
            evaluation={"metrics": {"retrieval": ["hit_rate"]}},
        )

    def test_creation(self):
        config = self._make_config()
        result = ExperimentResult(
            experiment_id="exp_20250416_120000_test",
            name="test_experiment",
            description="Test experiment description",
            created_at="2025-04-16T12:00:00",
            status="completed",
            config=config,
        )
        assert result.experiment_id == "exp_20250416_120000_test"
        assert result.name == "test_experiment"
        assert result.status == "completed"

    def test_to_dict(self):
        config = self._make_config()
        result = ExperimentResult(
            experiment_id="exp_20250416_120000_test",
            name="test_experiment",
            description="Test experiment description",
            created_at="2025-04-16T12:00:00",
            status="completed",
            config=config,
            meal_snapshot={"meal_id": "test"},
            test_set_snapshots=[{"strategy": "factual"}],
            variant_results=[{"variant": "a", "score": 0.9}],
        )
        d = result.to_dict()
        assert d["experiment_id"] == "exp_20250416_120000_test"
        assert d["name"] == "test_experiment"
        assert d["meal_snapshot"]["meal_id"] == "test"
        assert len(d["test_set_snapshots"]) == 1
        assert len(d["variant_results"]) == 1

    def test_from_dict(self):
        data = {
            "experiment_id": "exp_20250416_120000_test",
            "name": "test_experiment",
            "description": "Test description",
            "created_at": "2025-04-16T12:00:00",
            "status": "completed",
            "config": {
                "name": "test_experiment",
                "description": "Test description",
                "data": {"meal": "test_meal"},
                "test_sets": [{"strategy": "factual", "num_questions": 10}],
                "variants": [{"name": "variant_a"}],
                "evaluation": {"metrics": {"retrieval": ["hit_rate"]}},
            },
            "meal_snapshot": {"meal_id": "test"},
            "test_set_snapshots": [],
            "variant_results": [],
        }
        result = ExperimentResult.from_dict(data)
        assert result.experiment_id == "exp_20250416_120000_test"
        assert result.name == "test_experiment"
        assert result.config.name == "test_experiment"

    def test_from_dict_missing_required_field(self):
        data = {
            "experiment_id": "exp_test",
            "name": "test",
        }
        with pytest.raises(ValueError, match="Missing required fields"):
            ExperimentResult.from_dict(data)

    def test_default_values(self):
        config = self._make_config()
        result = ExperimentResult(
            experiment_id="exp_test",
            name="test",
            description="test",
            created_at="2025-04-16T12:00:00",
            status="running",
            config=config,
        )
        assert result.meal_snapshot == {}
        assert result.test_set_snapshots == []
        assert result.variant_results == []


class TestExperimentManager:
    def _make_config(self) -> ExperimentConfig:
        return ExperimentConfig(
            name="test_experiment",
            description="Test experiment description",
            data={"meal": "test_meal"},
            test_sets=[
                {"strategy": "factual", "num_questions": 20, "seed": 100},
                {"strategy": "boundary", "num_questions": 15, "seed": 101},
            ],
            variants=[
                {"name": "variant_a", "description": "Variant A"},
                {"name": "variant_b", "description": "Variant B"},
            ],
            evaluation={"metrics": {"retrieval": ["hit_rate", "mrr"]}},
        )

    def _make_system_config(self, temp_dir: Path) -> dict:
        return {
            "experiments": {
                "dir": str(temp_dir / "exp_reports"),
                "configs_dir": str(temp_dir / "exp_configs"),
            }
        }

    def test_init(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            system_config = self._make_system_config(temp_path)
            manager = ExperimentManager(system_config)
            assert manager.exp_dir == temp_path / "exp_reports"
            assert manager.configs_dir == temp_path / "exp_configs"

    def test_init_default_paths(self):
        manager = ExperimentManager({})
        assert manager.exp_dir == Path("data/exp_reports")
        assert manager.configs_dir == Path("exp_configs")

    def test_generate_experiment_id(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            system_config = self._make_system_config(temp_path)
            manager = ExperimentManager(system_config)
            config = self._make_config()

            exp_id = manager.generate_experiment_id(config)

            assert exp_id.startswith("exp_")
            assert "test_experiment" in exp_id

    def test_generate_experiment_id_special_chars(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            system_config = self._make_system_config(temp_path)
            manager = ExperimentManager(system_config)
            config = ExperimentConfig(
                name="Test-Experiment 2024!",
                description="Test",
                data={"meal": "test"},
                test_sets=[{"strategy": "factual", "num_questions": 10}],
                variants=[{"name": "v1"}],
                evaluation={"metrics": {}},
            )

            exp_id = manager.generate_experiment_id(config)

            assert "!" not in exp_id
            assert "test_experiment_2024" in exp_id

    def test_create_experiment_dir(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            system_config = self._make_system_config(temp_path)
            manager = ExperimentManager(system_config)
            config = self._make_config()

            exp_dir = manager.create_experiment_dir(config)

            assert exp_dir.exists()
            assert exp_dir.name.startswith("exp_")
            assert (exp_dir / "test_sets").exists()
            assert (exp_dir / "results").exists()

    def test_save_snapshots(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            system_config = self._make_system_config(temp_path)
            manager = ExperimentManager(system_config)
            config = self._make_config()

            exp_dir = manager.create_experiment_dir(config)

            meal_snapshot = {
                "meal_id": "test_meal",
                "pdf_count": 10,
                "total_chunks": 100,
            }
            test_set_snapshots = [
                {"strategy": "factual", "num_questions": 20, "questions": []},
                {"strategy": "boundary", "num_questions": 15, "questions": []},
            ]
            config_snapshot = {
                "chunker": {"chunk_size": 512, "chunk_overlap": 0},
                "embedding": {"model_name": "test_model"},
            }

            manager.save_snapshots(
                exp_dir, config, meal_snapshot, test_set_snapshots, config_snapshot
            )

            assert (exp_dir / "config_snapshot.yaml").exists()
            assert (exp_dir / "meal_snapshot.json").exists()
            assert (exp_dir / "manifest.json").exists()
            assert (exp_dir / "test_sets" / "factual.json").exists()
            assert (exp_dir / "test_sets" / "boundary.json").exists()

            with open(exp_dir / "meal_snapshot.json", "r", encoding="utf-8") as f:
                loaded_meal = json.load(f)
            assert loaded_meal["meal_id"] == "test_meal"

            with open(exp_dir / "manifest.json", "r", encoding="utf-8") as f:
                manifest = json.load(f)
            assert manifest["name"] == "test_experiment"
            assert manifest["status"] == "running"
            assert "variant_a" in manifest["variants"]
            assert "factual" in manifest["test_sets"]

    def test_load_experiment_result(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            system_config = self._make_system_config(temp_path)
            manager = ExperimentManager(system_config)
            config = self._make_config()

            exp_dir = manager.create_experiment_dir(config)

            meal_snapshot = {"meal_id": "test_meal"}
            test_set_snapshots = [{"strategy": "factual", "num_questions": 20}]
            config_snapshot = {
                "data": {"meal": "test_meal"},
                "evaluation": {"metrics": {"retrieval": ["hit_rate"]}},
            }

            manager.save_snapshots(
                exp_dir, config, meal_snapshot, test_set_snapshots, config_snapshot
            )

            variant_result = {
                "variant_name": "variant_a",
                "metrics": {"hit_rate": 0.85, "mrr": 0.72},
            }
            manager.save_variant_result(exp_dir, "variant_a", variant_result)

            result = manager.load_experiment_result(exp_dir)

            assert result.experiment_id == exp_dir.name
            assert result.name == "test_experiment"
            assert result.meal_snapshot["meal_id"] == "test_meal"
            assert len(result.test_set_snapshots) == 1
            assert len(result.variant_results) == 1

    def test_load_experiment_result_missing_manifest(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            system_config = self._make_system_config(temp_path)
            manager = ExperimentManager(system_config)

            exp_dir = temp_path / "exp_reports" / "exp_test"
            exp_dir.mkdir(parents=True)

            with pytest.raises(FileNotFoundError, match="Manifest file not found"):
                manager.load_experiment_result(exp_dir)

    def test_list_experiments_empty(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            system_config = self._make_system_config(temp_path)
            manager = ExperimentManager(system_config)

            experiments = manager.list_experiments()

            assert experiments == []

    def test_list_experiments(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            system_config = self._make_system_config(temp_path)
            manager = ExperimentManager(system_config)
            config = self._make_config()

            exp_dir1 = manager.create_experiment_dir(config)
            manager.save_snapshots(
                exp_dir1, config, {}, [], {}
            )

            config2 = ExperimentConfig(
                name="second_experiment",
                description="Second test",
                data={"meal": "test"},
                test_sets=[{"strategy": "factual", "num_questions": 10}],
                variants=[{"name": "v1"}],
                evaluation={"metrics": {}},
            )
            exp_dir2 = manager.create_experiment_dir(config2)
            manager.save_snapshots(
                exp_dir2, config2, {}, [], {}
            )

            experiments = manager.list_experiments()

            assert len(experiments) == 2

    def test_get_experiment_info(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            system_config = self._make_system_config(temp_path)
            manager = ExperimentManager(system_config)
            config = self._make_config()

            exp_dir = manager.create_experiment_dir(config)
            manager.save_snapshots(
                exp_dir, config, {"meal_id": "test"}, [], {}
            )

            info = manager.get_experiment_info(exp_dir.name)

            assert info["name"] == "test_experiment"
            assert info["meal_snapshot"]["meal_id"] == "test"

    def test_get_experiment_info_not_found(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            system_config = self._make_system_config(temp_path)
            manager = ExperimentManager(system_config)

            with pytest.raises(FileNotFoundError, match="Experiment not found"):
                manager.get_experiment_info("nonexistent_experiment")

    def test_update_manifest_status(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            system_config = self._make_system_config(temp_path)
            manager = ExperimentManager(system_config)
            config = self._make_config()

            exp_dir = manager.create_experiment_dir(config)
            manager.save_snapshots(exp_dir, config, {}, [], {})

            manager.update_manifest_status(exp_dir, "completed")

            with open(exp_dir / "manifest.json", "r", encoding="utf-8") as f:
                manifest = json.load(f)
            assert manifest["status"] == "completed"

    def test_update_manifest_status_missing_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            system_config = self._make_system_config(temp_path)
            manager = ExperimentManager(system_config)

            exp_dir = temp_path / "exp_reports" / "exp_test"
            exp_dir.mkdir(parents=True)

            with pytest.raises(FileNotFoundError, match="Manifest file not found"):
                manager.update_manifest_status(exp_dir, "completed")

    def test_save_variant_result(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            system_config = self._make_system_config(temp_path)
            manager = ExperimentManager(system_config)
            config = self._make_config()

            exp_dir = manager.create_experiment_dir(config)

            result = {
                "variant_name": "variant_a",
                "metrics": {"hit_rate": 0.85, "mrr": 0.72},
                "details": [],
            }

            result_path = manager.save_variant_result(exp_dir, "variant_a", result)

            assert result_path.exists()
            assert result_path.name == "variant_a.json"

            with open(result_path, "r", encoding="utf-8") as f:
                loaded_result = json.load(f)
            assert loaded_result["variant_name"] == "variant_a"
            assert loaded_result["metrics"]["hit_rate"] == 0.85

    def test_save_variant_result_special_chars(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            system_config = self._make_system_config(temp_path)
            manager = ExperimentManager(system_config)
            config = self._make_config()

            exp_dir = manager.create_experiment_dir(config)

            result = {"metrics": {}}

            result_path = manager.save_variant_result(exp_dir, "Variant-A Test!", result)

            assert result_path.exists()
            assert "!" not in result_path.name
