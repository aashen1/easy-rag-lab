import json
import tempfile
import warnings
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from src.experiment import (
    ExperimentConfig,
    ExperimentManager,
    ExperimentResult,
    VALID_GENERATION_METRICS,
    VALID_ON_MISSING_VALUES,
    VALID_RETRIEVAL_METRICS,
    deep_merge,
    get_test_set_config,
    get_test_set_name,
    get_variant_config,
    is_new_format,
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

    @pytest.mark.unit
    def test_creation(self):
        data = self._make_config_dict()
        config = ExperimentConfig.from_dict(data)
        assert config.name == "test_experiment"
        assert config.description == "Test experiment description"
        assert config.data["meal"] == "meal_baseline"
        assert len(config.test_sets) == 1
        assert len(config.variants) == 1

    @pytest.mark.unit
    def test_to_dict(self):
        data = self._make_config_dict()
        config = ExperimentConfig.from_dict(data)
        d = config.to_dict()
        assert d["name"] == "test_experiment"
        assert d["description"] == "Test experiment description"
        assert d["data"]["meal"] == "meal_baseline"
        assert len(d["test_sets"]) == 1
        assert len(d["variants"]) == 1

    @pytest.mark.unit
    def test_invalid_config_catches_all_errors(self):
        data_missing_name = self._make_config_dict()
        del data_missing_name["name"]
        with pytest.raises(ValueError, match="Missing required fields"):
            ExperimentConfig.from_dict(data_missing_name)

        with pytest.raises(ValueError, match="Missing required fields"):
            ExperimentConfig.from_dict({"name": "test"})

        data = self._make_config_dict(
            name="",
            description="",
            test_sets=[],
            variants=[],
        )
        del data["data"]["meal"]
        del data["evaluation"]["metrics"]

        config = ExperimentConfig.from_dict(data)
        errors = config.validate()

        assert "Experiment name cannot be empty" in errors
        assert "Experiment description cannot be empty" in errors
        assert "Data configuration must include 'meal' field" in errors
        assert "At least one test set must be defined" in errors
        assert "At least one variant must be defined" in errors
        assert "Evaluation configuration must include 'metrics' field" in errors
        assert len(errors) == 6

    @pytest.mark.unit
    def test_invalid_config_partial_errors(self):
        data = self._make_config_dict()
        data["test_sets"] = [{"num_questions": 10}]
        data["variants"] = [{"description": "no name"}]

        config = ExperimentConfig.from_dict(data)
        errors = config.validate()

        assert "Test set 0 missing 'strategy' field" in errors
        assert "Test set 0 missing 'num_questions' field" not in errors
        assert "Variant 0 missing 'name' field" in errors
        assert "Experiment name cannot be empty" not in errors
        assert "Experiment description cannot be empty" not in errors
        assert "Data configuration must include 'meal' field" not in errors
        assert "At least one test set must be defined" not in errors
        assert "At least one variant must be defined" not in errors
        assert "Evaluation configuration must include 'metrics' field" not in errors

        data2 = self._make_config_dict()
        data2["test_sets"] = [{"strategy": "factual"}]
        config2 = ExperimentConfig.from_dict(data2)
        errors2 = config2.validate()
        assert "Test set 0 missing 'num_questions' field" in errors2

    @pytest.mark.unit
    def test_valid_metrics_with_retrieval_only(self):
        data = self._make_config_dict()
        data["evaluation"]["metrics"] = {
            "retrieval": ["hit_rate", "mrr", "ndcg"]
        }
        config = ExperimentConfig.from_dict(data)
        errors = config.validate()
        assert not any("metrics" in e.lower() for e in errors)

    @pytest.mark.unit
    def test_valid_metrics_with_retrieval_and_generation(self):
        data = self._make_config_dict()
        data["evaluation"]["metrics"] = {
            "retrieval": ["hit_rate", "mrr"],
            "generation": ["faithfulness", "answer_relevancy"]
        }
        config = ExperimentConfig.from_dict(data)
        errors = config.validate()
        assert not any("metrics" in e.lower() for e in errors)

    @pytest.mark.unit
    def test_invalid_retrieval_metrics(self):
        data = self._make_config_dict()
        data["evaluation"]["metrics"] = {
            "retrieval": ["hit_rate", "invalid_metric", "another_invalid"]
        }
        config = ExperimentConfig.from_dict(data)
        errors = config.validate()
        assert any("Invalid retrieval metrics" in e for e in errors)
        assert any("invalid_metric" in e for e in errors)

    @pytest.mark.unit
    def test_invalid_generation_metrics(self):
        data = self._make_config_dict()
        data["evaluation"]["metrics"] = {
            "retrieval": ["hit_rate"],
            "generation": ["faithfulness", "invalid_gen_metric"]
        }
        config = ExperimentConfig.from_dict(data)
        errors = config.validate()
        assert any("Invalid generation metrics" in e for e in errors)
        assert any("invalid_gen_metric" in e for e in errors)

    @pytest.mark.unit
    def test_metrics_not_dict(self):
        data = self._make_config_dict()
        data["evaluation"]["metrics"] = ["hit_rate", "mrr"]
        config = ExperimentConfig.from_dict(data)
        errors = config.validate()
        assert any("must be a dictionary" in e for e in errors)

    @pytest.mark.unit
    def test_retrieval_not_list(self):
        data = self._make_config_dict()
        data["evaluation"]["metrics"] = {
            "retrieval": "hit_rate"
        }
        config = ExperimentConfig.from_dict(data)
        errors = config.validate()
        assert any("Retrieval metrics must be a list" in e for e in errors)

    @pytest.mark.unit
    def test_generation_not_list(self):
        data = self._make_config_dict()
        data["evaluation"]["metrics"] = {
            "retrieval": ["hit_rate"],
            "generation": "faithfulness"
        }
        config = ExperimentConfig.from_dict(data)
        errors = config.validate()
        assert any("Generation metrics must be a list" in e for e in errors)

    @pytest.mark.unit
    def test_missing_retrieval_field(self):
        data = self._make_config_dict()
        data["evaluation"]["metrics"] = {
            "generation": ["faithfulness"]
        }
        config = ExperimentConfig.from_dict(data)
        errors = config.validate()
        assert any("must include 'retrieval' field" in e for e in errors)

    @pytest.mark.unit
    def test_valid_metrics_constants(self):
        assert VALID_RETRIEVAL_METRICS == {
            "hit_rate", "mrr", "ndcg",
            "chunk_hit_rate", "chunk_mrr", "chunk_ndcg",
            "dedup_hit_rate", "dedup_mrr", "dedup_ndcg",
            "false_positive_rate",
        }
        assert VALID_GENERATION_METRICS == {"faithfulness", "answer_relevancy"}


class TestDeepMerge:
    @pytest.mark.unit
    def test_simple_override(self):
        base = {"a": 1, "b": 2}
        override = {"b": 3, "c": 4}
        result = deep_merge(base, override)
        assert result == {"a": 1, "b": 3, "c": 4}

    @pytest.mark.unit
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

    @pytest.mark.unit
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

    @pytest.mark.unit
    def test_non_dict_values_not_merged(self):
        base = {"list": [1, 2, 3], "string": "original"}
        override = {"list": [4, 5], "string": "overridden"}
        result = deep_merge(base, override)
        assert result["list"] == [4, 5]
        assert result["string"] == "overridden"

    @pytest.mark.unit
    def test_empty_override(self):
        base = {"a": 1, "b": 2}
        override = {}
        result = deep_merge(base, override)
        assert result == {"a": 1, "b": 2}

    @pytest.mark.unit
    def test_empty_base(self):
        base = {}
        override = {"a": 1, "b": 2}
        result = deep_merge(base, override)
        assert result == {"a": 1, "b": 2}

    @pytest.mark.unit
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

    @pytest.mark.unit
    def test_merge_without_variant(self):
        system_config = self._make_system_config()
        exp_config = self._make_experiment_config()
        result = merge_config(system_config, exp_config)
        assert result["chunker"]["chunk_size"] == 256
        assert result["chunker"]["chunk_overlap"] == 50

    @pytest.mark.unit
    def test_merge_with_variant(self):
        system_config = self._make_system_config()
        exp_config = self._make_experiment_config()
        variant = exp_config.variants[0]
        result = merge_config(system_config, exp_config, variant)
        assert result["chunker"]["chunk_size"] == 512
        assert result["chunker"]["chunk_overlap"] == 50
        assert result["embedding"]["model_name"] == "model_a"

    @pytest.mark.unit
    def test_original_config_not_modified(self):
        system_config = self._make_system_config()
        exp_config = self._make_experiment_config()
        variant = exp_config.variants[0]
        original_chunk_size = system_config["chunker"]["chunk_size"]
        merge_config(system_config, exp_config, variant)
        assert system_config["chunker"]["chunk_size"] == original_chunk_size


class TestLoadExperimentConfig:
    @pytest.mark.unit
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

    @pytest.mark.unit
    def test_load_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            load_experiment_config("nonexistent_file.yaml")

    @pytest.mark.unit
    def test_load_invalid_yaml(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False, encoding="utf-8") as f:
            f.write("invalid: yaml: content: [")
            temp_path = f.name

        try:
            with pytest.raises(yaml.YAMLError):
                load_experiment_config(temp_path)
        finally:
            Path(temp_path).unlink()

    @pytest.mark.unit
    def test_load_empty_file(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False, encoding="utf-8") as f:
            f.write("")
            temp_path = f.name

        try:
            with pytest.raises(ValueError, match="Empty configuration file"):
                load_experiment_config(temp_path)
        finally:
            Path(temp_path).unlink()

    @pytest.mark.unit
    def test_load_non_dict_config(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False, encoding="utf-8") as f:
            yaml.dump(["item1", "item2"], f)
            temp_path = f.name

        try:
            with pytest.raises(ValueError, match="must be a dictionary"):
                load_experiment_config(temp_path)
        finally:
            Path(temp_path).unlink()

    @pytest.mark.unit
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

    @pytest.mark.unit
    def test_get_variant_config_found(self):
        system_config, experiment_config = self._make_configs()
        result = get_variant_config(system_config, experiment_config, "variant_a")
        assert result["chunker"]["chunk_size"] == 512
        assert result["chunker"]["chunk_overlap"] == 50

    @pytest.mark.unit
    def test_get_variant_config_different_variant(self):
        system_config, experiment_config = self._make_configs()
        result = get_variant_config(system_config, experiment_config, "variant_b")
        assert result["chunker"]["chunk_size"] == 1024
        assert result["chunker"]["chunk_overlap"] == 100

    @pytest.mark.unit
    def test_get_variant_config_not_found(self):
        system_config, experiment_config = self._make_configs()
        with pytest.raises(ValueError, match="not found"):
            get_variant_config(system_config, experiment_config, "nonexistent")


class TestListVariants:
    @pytest.mark.unit
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

    @pytest.mark.unit
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

    @pytest.mark.unit
    def test_get_first_test_set(self):
        config = self._make_config()
        test_set = get_test_set_config(config, 0)
        assert test_set["strategy"] == "factual"
        assert test_set["num_questions"] == 10

    @pytest.mark.unit
    def test_get_second_test_set(self):
        config = self._make_config()
        test_set = get_test_set_config(config, 1)
        assert test_set["strategy"] == "boundary"
        assert test_set["num_questions"] == 15

    @pytest.mark.unit
    def test_get_test_set_default_index(self):
        config = self._make_config()
        test_set = get_test_set_config(config)
        assert test_set["strategy"] == "factual"

    @pytest.mark.unit
    def test_get_test_set_out_of_range(self):
        config = self._make_config()
        with pytest.raises(IndexError, match="out of range"):
            get_test_set_config(config, 10)

    @pytest.mark.unit
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

    @pytest.mark.unit
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

    @pytest.mark.unit
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

    @pytest.mark.unit
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

    @pytest.mark.unit
    def test_from_dict_missing_required_field(self):
        data = {
            "experiment_id": "exp_test",
            "name": "test",
        }
        with pytest.raises(ValueError, match="Missing required fields"):
            ExperimentResult.from_dict(data)

    @pytest.mark.unit
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

    @pytest.mark.unit
    def test_init(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            system_config = self._make_system_config(temp_path)
            manager = ExperimentManager(system_config)
            assert manager.exp_dir == temp_path / "exp_reports"
            assert manager.configs_dir == temp_path / "exp_configs"

    @pytest.mark.unit
    def test_init_default_paths(self):
        manager = ExperimentManager({})
        assert manager.exp_dir == Path("data/exp_reports")
        assert manager.configs_dir == Path("exp_configs")

    @pytest.mark.unit
    def test_generate_experiment_id(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            system_config = self._make_system_config(temp_path)
            manager = ExperimentManager(system_config)
            config = self._make_config()

            exp_id = manager.generate_experiment_id(config)

            assert exp_id.startswith("exp_")
            assert "test_experiment" in exp_id

    @pytest.mark.unit
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

    @pytest.mark.unit
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

    @pytest.mark.unit
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

    @pytest.mark.unit
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

    @pytest.mark.unit
    def test_load_experiment_result_missing_manifest(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            system_config = self._make_system_config(temp_path)
            manager = ExperimentManager(system_config)

            exp_dir = temp_path / "exp_reports" / "exp_test"
            exp_dir.mkdir(parents=True)

            with pytest.raises(FileNotFoundError, match="Manifest file not found"):
                manager.load_experiment_result(exp_dir)

    @pytest.mark.unit
    def test_list_experiments_empty(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            system_config = self._make_system_config(temp_path)
            manager = ExperimentManager(system_config)

            experiments = manager.list_experiments()

            assert experiments == []

    @pytest.mark.unit
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

    @pytest.mark.unit
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

    @pytest.mark.unit
    def test_get_experiment_info_not_found(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            system_config = self._make_system_config(temp_path)
            manager = ExperimentManager(system_config)

            with pytest.raises(FileNotFoundError, match="Experiment not found"):
                manager.get_experiment_info("nonexistent_experiment")

    @pytest.mark.unit
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

    @pytest.mark.unit
    def test_update_manifest_status_missing_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            system_config = self._make_system_config(temp_path)
            manager = ExperimentManager(system_config)

            exp_dir = temp_path / "exp_reports" / "exp_test"
            exp_dir.mkdir(parents=True)

            manager.update_manifest_status(exp_dir, "completed")

            assert not (exp_dir / "manifest.json").exists()

    @pytest.mark.unit
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

    @pytest.mark.unit
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


class TestIsNewFormat:
    @pytest.mark.unit
    def test_new_format_with_name(self):
        config = {"name": "my_test_set", "generation": {"strategy": "document", "num_questions": 10}}
        assert is_new_format(config) is True

    @pytest.mark.unit
    def test_old_format_without_name(self):
        config = {"strategy": "factual", "num_questions": 20}
        assert is_new_format(config) is False

    @pytest.mark.unit
    def test_empty_dict(self):
        assert is_new_format({}) is False

    @pytest.mark.unit
    def test_new_format_name_only(self):
        config = {"name": "minimal_new"}
        assert is_new_format(config) is True


class TestGetTestSetName:
    @pytest.mark.unit
    def test_new_format_returns_name(self):
        config = {"name": "custom_name", "generation": {"strategy": "document", "num_questions": 10}}
        assert get_test_set_name(config) == "custom_name"

    @pytest.mark.unit
    def test_old_format_factual_strategy(self):
        config = {"strategy": "factual", "num_questions": 20}
        assert get_test_set_name(config) == "auto_factual_n20"

    @pytest.mark.unit
    def test_old_format_document_strategy(self):
        config = {"strategy": "document", "num_questions": 10}
        assert get_test_set_name(config) == "document_level_n10"

    @pytest.mark.unit
    def test_old_format_defaults(self):
        config = {}
        assert get_test_set_name(config) == "auto_factual_n20"

    @pytest.mark.unit
    def test_old_format_missing_num_questions(self):
        config = {"strategy": "reasoning"}
        assert get_test_set_name(config) == "auto_reasoning_n20"

    @pytest.mark.unit
    def test_old_format_missing_strategy(self):
        config = {"num_questions": 15}
        assert get_test_set_name(config) == "auto_factual_n15"


class TestNewFormatValidation:
    def _make_config_dict(self, **overrides) -> dict:
        defaults = {
            "name": "test_experiment",
            "description": "Test experiment description",
            "data": {"meal": "meal_baseline"},
            "test_sets": [
                {
                    "name": "doc_level_test",
                    "on_missing": "auto",
                    "generation": {"strategy": "document", "num_questions": 10},
                }
            ],
            "variants": [{"name": "v1"}],
            "evaluation": {"metrics": {"retrieval": ["hit_rate"]}},
        }
        defaults.update(overrides)
        return defaults

    @pytest.mark.unit
    def test_valid_new_format(self):
        data = self._make_config_dict()
        config = ExperimentConfig.from_dict(data)
        errors = config.validate()
        test_set_errors = [e for e in errors if "Test set" in e]
        assert test_set_errors == []

    @pytest.mark.unit
    def test_new_format_without_generation(self):
        data = self._make_config_dict()
        data["test_sets"] = [{"name": "prebuilt_test", "on_missing": "strict"}]
        config = ExperimentConfig.from_dict(data)
        errors = config.validate()
        test_set_errors = [e for e in errors if "Test set" in e]
        assert test_set_errors == []

    @pytest.mark.unit
    def test_new_format_empty_name(self):
        data = self._make_config_dict()
        data["test_sets"] = [{"name": "", "generation": {"strategy": "document", "num_questions": 10}}]
        config = ExperimentConfig.from_dict(data)
        errors = config.validate()
        assert any("'name' must be a non-empty string" in e for e in errors)

    @pytest.mark.unit
    def test_new_format_whitespace_name(self):
        data = self._make_config_dict()
        data["test_sets"] = [{"name": "   ", "generation": {"strategy": "document", "num_questions": 10}}]
        config = ExperimentConfig.from_dict(data)
        errors = config.validate()
        assert any("'name' must be a non-empty string" in e for e in errors)

    @pytest.mark.unit
    def test_new_format_invalid_on_missing(self):
        data = self._make_config_dict()
        data["test_sets"] = [{"name": "test", "on_missing": "invalid_value", "generation": {"strategy": "document", "num_questions": 10}}]
        config = ExperimentConfig.from_dict(data)
        errors = config.validate()
        assert any("invalid 'on_missing' value" in e for e in errors)

    @pytest.mark.unit
    def test_new_format_generation_missing_strategy(self):
        data = self._make_config_dict()
        data["test_sets"] = [{"name": "test", "generation": {"num_questions": 10}}]
        config = ExperimentConfig.from_dict(data)
        errors = config.validate()
        assert any("'generation' missing 'strategy' field" in e for e in errors)

    @pytest.mark.unit
    def test_new_format_generation_missing_num_questions(self):
        data = self._make_config_dict()
        data["test_sets"] = [{"name": "test", "generation": {"strategy": "document"}}]
        config = ExperimentConfig.from_dict(data)
        errors = config.validate()
        assert any("'generation' missing 'num_questions' field" in e for e in errors)

    @pytest.mark.unit
    def test_new_format_generation_not_dict(self):
        data = self._make_config_dict()
        data["test_sets"] = [{"name": "test", "generation": "not_a_dict"}]
        config = ExperimentConfig.from_dict(data)
        errors = config.validate()
        assert any("'generation' must be a dictionary" in e for e in errors)

    @pytest.mark.unit
    def test_valid_on_missing_values(self):
        assert VALID_ON_MISSING_VALUES == {"auto", "clean_only", "strict"}

    @pytest.mark.unit
    def test_new_format_all_valid_on_missing_values(self):
        for on_missing_val in ["auto", "clean_only", "strict"]:
            data = self._make_config_dict()
            data["test_sets"] = [{"name": "test", "on_missing": on_missing_val, "generation": {"strategy": "document", "num_questions": 10}}]
            config = ExperimentConfig.from_dict(data)
            errors = config.validate()
            test_set_errors = [e for e in errors if "on_missing" in e]
            assert test_set_errors == [], f"Unexpected error for on_missing='{on_missing_val}'"


class TestOldFormatDeprecation:
    def _make_config_dict(self, **overrides) -> dict:
        defaults = {
            "name": "test_experiment",
            "description": "Test experiment description",
            "data": {"meal": "meal_baseline"},
            "test_sets": [{"strategy": "factual", "num_questions": 20}],
            "variants": [{"name": "v1"}],
            "evaluation": {"metrics": {"retrieval": ["hit_rate"]}},
        }
        defaults.update(overrides)
        return defaults

    @pytest.mark.unit
    def test_old_format_emits_deprecation_warning(self):
        data = self._make_config_dict()
        config = ExperimentConfig.from_dict(data)
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            config.validate()
            deprecation_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
            assert len(deprecation_warnings) == 1
            assert "deprecated configuration format" in str(deprecation_warnings[0].message)

    @pytest.mark.unit
    def test_old_format_still_validates(self):
        data = self._make_config_dict()
        config = ExperimentConfig.from_dict(data)
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            errors = config.validate()
        test_set_errors = [e for e in errors if "Test set" in e]
        assert test_set_errors == []

    @pytest.mark.unit
    def test_old_format_missing_strategy_still_errors(self):
        data = self._make_config_dict()
        data["test_sets"] = [{"num_questions": 10}]
        config = ExperimentConfig.from_dict(data)
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            errors = config.validate()
        assert any("missing 'strategy' field" in e for e in errors)

    @pytest.mark.unit
    def test_new_format_no_deprecation_warning(self):
        data = self._make_config_dict()
        data["test_sets"] = [{"name": "test", "generation": {"strategy": "document", "num_questions": 10}}]
        config = ExperimentConfig.from_dict(data)
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            config.validate()
            deprecation_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
            assert len(deprecation_warnings) == 0

    @pytest.mark.unit
    def test_mixed_formats_emits_warning(self):
        data = self._make_config_dict()
        data["test_sets"] = [
            {"name": "new_format", "generation": {"strategy": "document", "num_questions": 10}},
            {"strategy": "factual", "num_questions": 20},
        ]
        config = ExperimentConfig.from_dict(data)
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            config.validate()
            deprecation_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
            assert len(deprecation_warnings) == 1
