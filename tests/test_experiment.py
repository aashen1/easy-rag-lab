import json
import tempfile
import warnings
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from src.exceptions import ConfigurationError
from src.experiment import (
    VALID_GENERATION_METRICS,
    VALID_ON_MISSING_VALUES,
    VALID_RETRIEVAL_METRICS,
    ExperimentConfig,
    ExperimentManager,
    ExperimentResult,
    deep_merge,
    get_test_set_config,
    get_test_set_name,
    get_variant_config,
    is_new_format,
    list_variants,
    load_experiment_config,
    merge_config,
)
from src.meal.hashes import compute_variant_config_hash


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
        with pytest.raises(ConfigurationError, match="Missing required fields"):
            ExperimentConfig.from_dict(data_missing_name)

        with pytest.raises(ConfigurationError, match="Missing required fields"):
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
        assert (
            "Evaluation configuration must include 'metrics' or 'metrics_preset' field"
            in errors
        )
        assert len(errors) == 6

    @pytest.mark.unit
    def test_invalid_config_partial_errors(self):
        data = self._make_config_dict()
        data["test_sets"] = [{"num_questions": 10}]
        data["variants"] = [{"description": "no name"}]

        config = ExperimentConfig.from_dict(data)
        with pytest.warns(DeprecationWarning, match="deprecated configuration format"):
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
        with pytest.warns(DeprecationWarning, match="deprecated configuration format"):
            errors2 = config2.validate()
        assert "Test set 0 missing 'num_questions' field" in errors2

    @pytest.mark.unit
    def test_valid_metrics_with_retrieval_only(self):
        data = self._make_config_dict()
        data["evaluation"]["metrics"] = {"retrieval": ["hit_rate", "mrr", "ndcg"]}
        config = ExperimentConfig.from_dict(data)
        with pytest.warns(DeprecationWarning, match="deprecated configuration format"):
            errors = config.validate()
        assert not any("metrics" in e.lower() for e in errors)

    @pytest.mark.unit
    def test_valid_metrics_with_retrieval_and_generation(self):
        data = self._make_config_dict()
        data["evaluation"]["metrics"] = {
            "retrieval": ["hit_rate", "mrr"],
            "generation": ["faithfulness", "answer_relevancy"],
        }
        config = ExperimentConfig.from_dict(data)
        with pytest.warns(DeprecationWarning, match="deprecated configuration format"):
            errors = config.validate()
        assert not any("metrics" in e.lower() for e in errors)

    @pytest.mark.unit
    def test_invalid_retrieval_metrics(self):
        data = self._make_config_dict()
        data["evaluation"]["metrics"] = {
            "retrieval": ["hit_rate", "invalid_metric", "another_invalid"]
        }
        config = ExperimentConfig.from_dict(data)
        with pytest.warns(DeprecationWarning, match="deprecated configuration format"):
            errors = config.validate()
        assert any("Invalid retrieval metrics" in e for e in errors)
        assert any("invalid_metric" in e for e in errors)

    @pytest.mark.unit
    def test_invalid_generation_metrics(self):
        data = self._make_config_dict()
        data["evaluation"]["metrics"] = {
            "retrieval": ["hit_rate"],
            "generation": ["faithfulness", "invalid_gen_metric"],
        }
        config = ExperimentConfig.from_dict(data)
        with pytest.warns(DeprecationWarning, match="deprecated configuration format"):
            errors = config.validate()
        assert any("Invalid generation metrics" in e for e in errors)
        assert any("invalid_gen_metric" in e for e in errors)

    @pytest.mark.unit
    def test_metrics_not_dict(self):
        data = self._make_config_dict()
        data["evaluation"]["metrics"] = ["hit_rate", "mrr"]
        config = ExperimentConfig.from_dict(data)
        with pytest.warns(DeprecationWarning, match="deprecated configuration format"):
            errors = config.validate()
        assert any("must be a dictionary" in e for e in errors)

    @pytest.mark.unit
    def test_retrieval_not_list(self):
        data = self._make_config_dict()
        data["evaluation"]["metrics"] = {"retrieval": "hit_rate"}
        config = ExperimentConfig.from_dict(data)
        with pytest.warns(DeprecationWarning, match="deprecated configuration format"):
            errors = config.validate()
        assert any("Retrieval metrics must be a list" in e for e in errors)

    @pytest.mark.unit
    def test_generation_not_list(self):
        data = self._make_config_dict()
        data["evaluation"]["metrics"] = {
            "retrieval": ["hit_rate"],
            "generation": "faithfulness",
        }
        config = ExperimentConfig.from_dict(data)
        with pytest.warns(DeprecationWarning, match="deprecated configuration format"):
            errors = config.validate()
        assert any("Generation metrics must be a list" in e for e in errors)

    @pytest.mark.unit
    def test_missing_retrieval_field(self):
        data = self._make_config_dict()
        data["evaluation"]["metrics"] = {"generation": ["faithfulness"]}
        config = ExperimentConfig.from_dict(data)
        with pytest.warns(DeprecationWarning, match="deprecated configuration format"):
            errors = config.validate()
        assert any("must include 'retrieval' field" in e for e in errors)

    @pytest.mark.unit
    def test_valid_metrics_constants(self):
        assert {
            "hit_rate",
            "mrr",
            "ndcg",
            "chunk_hit_rate",
            "chunk_mrr",
            "chunk_ndcg",
            "dedup_hit_rate",
            "dedup_mrr",
            "dedup_ndcg",
            "false_positive_rate",
            "context_precision",
            "context_recall",
            "recall_3",
            "recall_5",
            "recall_10",
            "retrieval_diversity",
        } == VALID_RETRIEVAL_METRICS
        assert {"faithfulness", "answer_relevancy"} == VALID_GENERATION_METRICS

    @pytest.mark.unit
    def test_context_precision_in_retrieval_with_ragas_backend(self):
        data = self._make_config_dict()
        data["evaluation"]["backends"] = ["ragas"]
        data["evaluation"]["metrics"] = {
            "retrieval": ["context_precision", "context_recall"],
            "generation": ["faithfulness", "answer_relevancy", "answer_correctness"],
        }
        config = ExperimentConfig.from_dict(data)
        with pytest.warns(DeprecationWarning, match="deprecated configuration format"):
            errors = config.validate()
        assert not any("Invalid retrieval metrics" in e for e in errors)

    @pytest.mark.unit
    def test_context_precision_in_retrieval_with_builtin_backend(self):
        data = self._make_config_dict()
        data["evaluation"]["backends"] = ["builtin"]
        data["evaluation"]["metrics"] = {
            "retrieval": ["context_precision", "context_recall"],
        }
        config = ExperimentConfig.from_dict(data)
        with pytest.warns(DeprecationWarning, match="deprecated configuration format"):
            errors = config.validate()
        assert not any("Invalid retrieval metrics" in e for e in errors)

    @pytest.mark.unit
    def test_context_precision_in_retrieval_without_supported_backend(self):
        data = self._make_config_dict()
        data["evaluation"]["backends"] = ["nonexistent"]
        data["evaluation"]["metrics"] = {
            "retrieval": ["context_precision"],
        }
        config = ExperimentConfig.from_dict(data)
        with pytest.warns(DeprecationWarning, match="deprecated configuration format"):
            errors = config.validate()
        assert any("LLM-based retrieval metrics" in e for e in errors)

    @pytest.mark.unit
    def test_non_builtin_generation_metrics_require_ragas(self):
        data = self._make_config_dict()
        data["evaluation"]["backends"] = ["builtin"]
        data["evaluation"]["metrics"] = {
            "retrieval": ["hit_rate"],
            "generation": ["faithfulness", "answer_correctness"],
        }
        config = ExperimentConfig.from_dict(data)
        with pytest.warns(DeprecationWarning, match="deprecated configuration format"):
            errors = config.validate()
        assert any("require 'ragas' in evaluation.backends" in e for e in errors)

    @pytest.mark.unit
    def test_context_precision_in_generation_with_ragas_backend(self):
        data = self._make_config_dict()
        data["evaluation"]["backends"] = ["ragas"]
        data["evaluation"]["metrics"] = {
            "retrieval": [],
            "generation": ["context_precision", "context_recall", "answer_correctness"],
        }
        config = ExperimentConfig.from_dict(data)
        with pytest.warns(DeprecationWarning, match="deprecated configuration format"):
            errors = config.validate()
        assert not any("metrics" in e.lower() for e in errors)


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

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, encoding="utf-8"
        ) as f:
            yaml.dump(config_data, f)
            temp_path = f.name

        try:
            with pytest.warns(
                DeprecationWarning, match="deprecated configuration format"
            ):
                config = load_experiment_config(temp_path)
            assert config.name == "test_exp"
            assert config.description == "Test experiment"
        finally:
            Path(temp_path).unlink()

    @pytest.mark.unit
    def test_load_file_not_found(self):
        with pytest.raises(ConfigurationError):
            load_experiment_config("nonexistent_file.yaml")

    @pytest.mark.unit
    def test_load_invalid_yaml(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, encoding="utf-8"
        ) as f:
            f.write("invalid: yaml: content: [")
            temp_path = f.name

        try:
            with pytest.raises(yaml.YAMLError):
                load_experiment_config(temp_path)
        finally:
            Path(temp_path).unlink()

    @pytest.mark.unit
    def test_load_empty_file(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, encoding="utf-8"
        ) as f:
            f.write("")
            temp_path = f.name

        try:
            with pytest.raises(ConfigurationError, match="Empty configuration file"):
                load_experiment_config(temp_path)
        finally:
            Path(temp_path).unlink()

    @pytest.mark.unit
    def test_load_non_dict_config(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, encoding="utf-8"
        ) as f:
            yaml.dump(["item1", "item2"], f)
            temp_path = f.name

        try:
            with pytest.raises(ConfigurationError, match="must be a dictionary"):
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

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, encoding="utf-8"
        ) as f:
            yaml.dump(config_data, f)
            temp_path = f.name

        try:
            with (
                pytest.warns(
                    DeprecationWarning, match="deprecated configuration format"
                ),
                pytest.raises(ConfigurationError, match="validation failed"),
            ):
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
                    "config_overrides": {
                        "chunker": {"chunk_size": 1024, "chunk_overlap": 100}
                    },
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
        with pytest.raises(ConfigurationError, match="not found"):
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
        with pytest.raises(ConfigurationError, match="Missing required fields"):
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

            with open(exp_dir / "meal_snapshot.json", encoding="utf-8") as f:
                loaded_meal = json.load(f)
            assert loaded_meal["meal_id"] == "test_meal"

            with open(exp_dir / "manifest.json", encoding="utf-8") as f:
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

            with pytest.raises(ConfigurationError, match="Manifest file not found"):
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
            manager.save_snapshots(exp_dir1, config, {}, [], {})

            config2 = ExperimentConfig(
                name="second_experiment",
                description="Second test",
                data={"meal": "test"},
                test_sets=[{"strategy": "factual", "num_questions": 10}],
                variants=[{"name": "v1"}],
                evaluation={"metrics": {}},
            )
            exp_dir2 = manager.create_experiment_dir(config2)
            manager.save_snapshots(exp_dir2, config2, {}, [], {})

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
            manager.save_snapshots(exp_dir, config, {"meal_id": "test"}, [], {})

            info = manager.get_experiment_info(exp_dir.name)

            assert info["name"] == "test_experiment"
            assert info["meal_snapshot"]["meal_id"] == "test"

    @pytest.mark.unit
    def test_get_experiment_info_not_found(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            system_config = self._make_system_config(temp_path)
            manager = ExperimentManager(system_config)

            with pytest.raises(ConfigurationError, match="Experiment not found"):
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

            with open(exp_dir / "manifest.json", encoding="utf-8") as f:
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

            with open(result_path, encoding="utf-8") as f:
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

            result_path = manager.save_variant_result(
                exp_dir, "Variant-A Test!", result
            )

            assert result_path.exists()
            assert "!" not in result_path.name


class TestIsNewFormat:
    @pytest.mark.unit
    def test_new_format_with_name(self):
        config = {
            "name": "my_test_set",
            "generation": {"strategy": "document", "num_questions": 10},
        }
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
        config = {
            "name": "custom_name",
            "generation": {"strategy": "document", "num_questions": 10},
        }
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

    @pytest.mark.unit
    def test_new_format_name_empty_string_auto_generates(self):
        config = {
            "name": "",
            "generation": {"strategy": "document", "num_questions": 10},
        }
        assert get_test_set_name(config) == "document_level_n10"

    @pytest.mark.unit
    def test_new_format_name_none_auto_generates(self):
        config = {
            "name": None,
            "generation": {"strategy": "document", "num_questions": 10},
        }
        assert get_test_set_name(config) == "document_level_n10"

    @pytest.mark.unit
    def test_new_format_name_whitespace_only_auto_generates(self):
        config = {
            "name": "   ",
            "generation": {"strategy": "document", "num_questions": 10},
        }
        assert get_test_set_name(config) == "document_level_n10"

    @pytest.mark.unit
    def test_new_format_name_provided_with_whitespace_trimmed(self):
        config = {
            "name": "  custom_name  ",
            "generation": {"strategy": "document", "num_questions": 10},
        }
        assert get_test_set_name(config) == "custom_name"


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
        data["test_sets"] = [
            {"name": "", "generation": {"strategy": "document", "num_questions": 10}}
        ]
        config = ExperimentConfig.from_dict(data)
        errors = config.validate()
        test_set_errors = [e for e in errors if "Test set" in e]
        assert test_set_errors == []

    @pytest.mark.unit
    def test_new_format_whitespace_name(self):
        data = self._make_config_dict()
        data["test_sets"] = [
            {"name": "   ", "generation": {"strategy": "document", "num_questions": 10}}
        ]
        config = ExperimentConfig.from_dict(data)
        errors = config.validate()
        test_set_errors = [e for e in errors if "Test set" in e]
        assert test_set_errors == []

    @pytest.mark.unit
    def test_new_format_none_name(self):
        data = self._make_config_dict()
        data["test_sets"] = [
            {"name": None, "generation": {"strategy": "document", "num_questions": 10}}
        ]
        config = ExperimentConfig.from_dict(data)
        errors = config.validate()
        test_set_errors = [e for e in errors if "Test set" in e]
        assert test_set_errors == []

    @pytest.mark.unit
    def test_new_format_invalid_on_missing(self):
        data = self._make_config_dict()
        data["test_sets"] = [
            {
                "name": "test",
                "on_missing": "invalid_value",
                "generation": {"strategy": "document", "num_questions": 10},
            }
        ]
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
        assert {"auto", "clean_only", "strict"} == VALID_ON_MISSING_VALUES

    @pytest.mark.unit
    def test_new_format_all_valid_on_missing_values(self):
        for on_missing_val in ["auto", "clean_only", "strict"]:
            data = self._make_config_dict()
            data["test_sets"] = [
                {
                    "name": "test",
                    "on_missing": on_missing_val,
                    "generation": {"strategy": "document", "num_questions": 10},
                }
            ]
            config = ExperimentConfig.from_dict(data)
            errors = config.validate()
            test_set_errors = [e for e in errors if "on_missing" in e]
            assert test_set_errors == [], (
                f"Unexpected error for on_missing='{on_missing_val}'"
            )


class TestExperimentBoundaryConditions:
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
    def test_empty_test_sets_errors(self):
        data = self._make_config_dict(test_sets=[])
        config = ExperimentConfig.from_dict(data)
        errors = config.validate()
        assert "At least one test set must be defined" in errors

    @pytest.mark.unit
    def test_empty_variants_errors(self):
        data = self._make_config_dict(variants=[])
        config = ExperimentConfig.from_dict(data)
        with pytest.warns(DeprecationWarning, match="deprecated configuration format"):
            errors = config.validate()
        assert "At least one variant must be defined" in errors

    @pytest.mark.unit
    def test_empty_metrics_dict_errors(self):
        data = self._make_config_dict()
        data["evaluation"]["metrics"] = {}
        config = ExperimentConfig.from_dict(data)
        with pytest.warns(DeprecationWarning, match="deprecated configuration format"):
            errors = config.validate()
        assert "Evaluation metrics must include 'retrieval' field" in errors

    @pytest.mark.unit
    def test_deep_merge_none_value_overwrites(self):
        base = {"a": 1, "b": {"c": 2}}
        override = {"a": None}
        result = deep_merge(base, override)
        assert result["a"] is None
        assert result["b"] == {"c": 2}

    @pytest.mark.unit
    def test_deep_merge_list_replaced_not_merged(self):
        base = {"items": [1, 2, 3]}
        override = {"items": [4, 5]}
        result = deep_merge(base, override)
        assert result["items"] == [4, 5]

    @pytest.mark.unit
    def test_experiment_manager_list_experiments_corrupted_manifest(
        self, temp_project_dir
    ):
        exp_dir = temp_project_dir / "data" / "exp_reports" / "exp_test_corrupted"
        exp_dir.mkdir(parents=True)
        with open(exp_dir / "manifest.json", "w", encoding="utf-8") as f:
            f.write("invalid json content [")

        system_config = {
            "experiments": {"dir": str(temp_project_dir / "data" / "exp_reports")}
        }
        manager = ExperimentManager(system_config)
        experiments = manager.list_experiments()

        assert len(experiments) == 1
        assert experiments[0]["status"] == "corrupted"

    @pytest.mark.unit
    def test_experiment_manager_load_missing_meal_snapshot(self, temp_project_dir):
        exp_dir = temp_project_dir / "data" / "exp_reports" / "exp_partial"
        exp_dir.mkdir(parents=True)

        manifest = {
            "experiment_id": "exp_partial",
            "name": "partial_exp",
            "description": "Test",
            "created_at": "2026-01-01T00:00:00",
            "status": "running",
            "variants": ["v1"],
            "test_sets": ["factual"],
        }
        with open(exp_dir / "manifest.json", "w", encoding="utf-8") as f:
            json.dump(manifest, f)

        config_snapshot = {
            "data": {"meal": "test"},
            "evaluation": {"metrics": {"retrieval": ["hit_rate"]}},
        }
        with open(exp_dir / "config_snapshot.yaml", "w", encoding="utf-8") as f:
            yaml.dump(config_snapshot, f)

        manager = ExperimentManager({})
        result = manager.load_experiment_result(exp_dir)

        assert result.name == "partial_exp"
        assert result.meal_snapshot == {}

    @pytest.mark.unit
    def test_experiment_manager_load_corrupted_meal_snapshot(self, temp_project_dir):
        exp_dir = temp_project_dir / "data" / "exp_reports" / "exp_bad_meal"
        exp_dir.mkdir(parents=True)

        manifest = {
            "experiment_id": "exp_bad_meal",
            "name": "bad_meal_exp",
            "description": "Test",
            "created_at": "2026-01-01T00:00:00",
            "status": "running",
            "variants": ["v1"],
            "test_sets": ["factual"],
        }
        with open(exp_dir / "manifest.json", "w", encoding="utf-8") as f:
            json.dump(manifest, f)

        with open(exp_dir / "meal_snapshot.json", "w", encoding="utf-8") as f:
            f.write("invalid json")

        with open(exp_dir / "config_snapshot.yaml", "w", encoding="utf-8") as f:
            yaml.dump(
                {
                    "data": {"meal": "test"},
                    "evaluation": {"metrics": {"retrieval": ["hit_rate"]}},
                },
                f,
            )

        manager = ExperimentManager({})
        result = manager.load_experiment_result(exp_dir)

        assert result.name == "bad_meal_exp"
        assert result.meal_snapshot == {}

    @pytest.mark.unit
    def test_experiment_result_from_dict_missing_field(self):
        data = {
            "experiment_id": "exp_1",
            "name": "test",
            "created_at": "2026-01-01",
            "status": "running",
            "config": {
                "name": "test",
                "description": "test",
                "data": {"meal": "test"},
                "test_sets": [{"strategy": "factual", "num_questions": 10}],
                "variants": [{"name": "v1"}],
                "evaluation": {"metrics": {"retrieval": ["hit_rate"]}},
            },
        }
        with pytest.raises(ConfigurationError, match="Missing required fields"):
            ExperimentResult.from_dict(data)

    @pytest.mark.unit
    def test_get_variant_config_returns_first_match(self):
        config = ExperimentConfig(
            name="test",
            description="test",
            data={"meal": "test"},
            test_sets=[{"strategy": "factual", "num_questions": 10}],
            variants=[
                {"name": "v1", "config_overrides": {"chunker": {"chunk_size": 256}}},
                {"name": "v1", "config_overrides": {"chunker": {"chunk_size": 512}}},
            ],
            evaluation={"metrics": {"retrieval": ["hit_rate"]}},
        )
        system_config = {"chunker": {"chunk_size": 128}}
        result = get_variant_config(system_config, config, "v1")
        assert result["chunker"]["chunk_size"] == 256


class TestExperimentExceptionPaths:
    @pytest.mark.unit
    def test_load_experiment_config_not_dict(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, encoding="utf-8"
        ) as f:
            yaml.dump(["item1", "item2", "item3"], f)
            temp_path = f.name

        try:
            with pytest.raises(ConfigurationError, match="must be a dictionary"):
                load_experiment_config(temp_path)
        finally:
            Path(temp_path).unlink()

    @pytest.mark.unit
    def test_load_experiment_config_with_validation_error(self):
        config_data = {
            "name": "",
            "description": "Test",
            "data": {"meal": "test"},
            "test_sets": [{"strategy": "factual", "num_questions": 10}],
            "variants": [{"name": "v1"}],
            "evaluation": {"metrics": {"retrieval": ["hit_rate"]}},
        }

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, encoding="utf-8"
        ) as f:
            yaml.dump(config_data, f)
            temp_path = f.name

        try:
            with (
                pytest.warns(
                    DeprecationWarning, match="deprecated configuration format"
                ),
                pytest.raises(ConfigurationError, match="validation failed"),
            ):
                load_experiment_config(temp_path)
        finally:
            Path(temp_path).unlink()

    @pytest.mark.unit
    def test_experiment_manager_create_dir_os_error(self, temp_project_dir):
        config = ExperimentConfig(
            name="test",
            description="test",
            data={"meal": "test"},
            test_sets=[{"strategy": "factual", "num_questions": 10}],
            variants=[{"name": "v1"}],
            evaluation={"metrics": {"retrieval": ["hit_rate"]}},
        )

        manager = ExperimentManager(
            {"experiments": {"dir": str(temp_project_dir / "data" / "exp_reports")}}
        )

        with (
            patch.object(Path, "mkdir", side_effect=OSError("Permission denied")),
            pytest.raises(OSError, match="Permission denied"),
        ):
            manager.create_experiment_dir(config)

    @pytest.mark.unit
    def test_experiment_manager_save_snapshots_os_error(self, temp_project_dir):
        exp_dir = temp_project_dir / "data" / "exp_reports" / "exp_test"
        exp_dir.mkdir(parents=True)
        (exp_dir / "test_sets").mkdir()
        (exp_dir / "results").mkdir()

        config = ExperimentConfig(
            name="test",
            description="test",
            data={"meal": "test"},
            test_sets=[{"strategy": "factual", "num_questions": 10}],
            variants=[{"name": "v1"}],
            evaluation={"metrics": {"retrieval": ["hit_rate"]}},
        )

        with (
            patch("builtins.open", side_effect=OSError("Disk full")),
            pytest.raises(OSError, match="Disk full"),
        ):
            manager = ExperimentManager({})
            manager.save_snapshots(exp_dir, config, {}, [], {})

    @pytest.mark.unit
    def test_experiment_manager_save_variant_result_os_error(self, temp_project_dir):
        exp_dir = temp_project_dir / "data" / "exp_reports" / "exp_test"
        exp_dir.mkdir(parents=True)
        results_dir = exp_dir / "results"
        results_dir.mkdir()

        with (
            patch("builtins.open", side_effect=OSError("Permission denied")),
            pytest.raises(OSError, match="Permission denied"),
        ):
            manager = ExperimentManager({})
            manager.save_variant_result(exp_dir, "v1", {"metrics": {}})

    @pytest.mark.unit
    def test_experiment_manager_update_manifest_json_error(self, temp_project_dir):
        exp_dir = temp_project_dir / "exp_test"
        exp_dir.mkdir(parents=True)

        with open(exp_dir / "manifest.json", "w", encoding="utf-8") as f:
            f.write("invalid json")

        manager = ExperimentManager({})
        with pytest.raises(json.JSONDecodeError):
            manager.update_manifest_status(exp_dir, "completed")

    @pytest.mark.unit
    def test_load_experiment_config_malformed_yaml(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, encoding="utf-8"
        ) as f:
            f.write(": :\n  - [\ninvalid: yaml: [")
            temp_path = f.name

        try:
            with pytest.raises(yaml.YAMLError):
                load_experiment_config(temp_path)
        finally:
            Path(temp_path).unlink()


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
            deprecation_warnings = [
                x for x in w if issubclass(x.category, DeprecationWarning)
            ]
            assert len(deprecation_warnings) == 1


class TestVariantConfigHash:
    def _make_variant(self, **overrides) -> dict:
        defaults = {
            "name": "test_variant",
            "config_overrides": {
                "chunker": {"chunk_size": 512, "chunk_overlap": 0},
            },
        }
        defaults.update(overrides)
        return defaults

    def _make_merged_config(self, **overrides) -> dict:
        defaults = {
            "chunker": {"chunk_size": 512, "chunk_overlap": 0, "strategy": "fixed"},
            "embedding": {"model_name": "test_model"},
            "retrieval": {"method": "vector", "top_k": 5},
        }
        defaults.update(overrides)
        return defaults

    @pytest.mark.unit
    def test_deterministic(self):
        variant = self._make_variant()
        merged = self._make_merged_config()
        hash1 = compute_variant_config_hash(variant, merged)
        hash2 = compute_variant_config_hash(variant, merged)
        assert hash1 == hash2

    @pytest.mark.unit
    def test_different_overrides_produce_different_hashes(self):
        variant_a = self._make_variant(
            config_overrides={"chunker": {"chunk_size": 512}}
        )
        variant_b = self._make_variant(
            config_overrides={"chunker": {"chunk_size": 1024}}
        )
        merged = self._make_merged_config()
        hash_a = compute_variant_config_hash(variant_a, merged)
        hash_b = compute_variant_config_hash(variant_b, merged)
        assert hash_a != hash_b

    @pytest.mark.unit
    def test_different_merged_config_produces_different_hash(self):
        variant = self._make_variant()
        merged_a = self._make_merged_config(retrieval={"method": "vector", "top_k": 5})
        merged_b = self._make_merged_config(retrieval={"method": "hybrid", "top_k": 5})
        hash_a = compute_variant_config_hash(variant, merged_a)
        hash_b = compute_variant_config_hash(variant, merged_b)
        assert hash_a != hash_b

    @pytest.mark.unit
    def test_same_config_same_hash(self):
        variant = self._make_variant()
        merged = self._make_merged_config()
        hash1 = compute_variant_config_hash(
            variant,
            merged,
            exp_data={"meal": "test"},
            exp_test_sets=[{"strategy": "factual"}],
            exp_evaluation={"metrics": {"retrieval": ["hit_rate"]}},
        )
        hash2 = compute_variant_config_hash(
            variant,
            merged,
            exp_data={"meal": "test"},
            exp_test_sets=[{"strategy": "factual"}],
            exp_evaluation={"metrics": {"retrieval": ["hit_rate"]}},
        )
        assert hash1 == hash2

    @pytest.mark.unit
    def test_different_exp_data_produces_different_hash(self):
        variant = self._make_variant()
        merged = self._make_merged_config()
        hash_a = compute_variant_config_hash(
            variant,
            merged,
            exp_data={"meal": "meal_a"},
        )
        hash_b = compute_variant_config_hash(
            variant,
            merged,
            exp_data={"meal": "meal_b"},
        )
        assert hash_a != hash_b

    @pytest.mark.unit
    def test_different_test_sets_produces_different_hash(self):
        variant = self._make_variant()
        merged = self._make_merged_config()
        hash_a = compute_variant_config_hash(
            variant,
            merged,
            exp_test_sets=[{"strategy": "factual"}],
        )
        hash_b = compute_variant_config_hash(
            variant,
            merged,
            exp_test_sets=[{"strategy": "boundary"}],
        )
        assert hash_a != hash_b

    @pytest.mark.unit
    def test_hash_length(self):
        variant = self._make_variant()
        merged = self._make_merged_config()
        h = compute_variant_config_hash(variant, merged)
        assert len(h) == 12

    @pytest.mark.unit
    def test_variant_without_overrides(self):
        variant = {"name": "bare_variant"}
        merged = self._make_merged_config()
        h = compute_variant_config_hash(variant, merged)
        assert len(h) == 12


class TestExperimentManagerVariantHash:
    def _make_config(self) -> ExperimentConfig:
        return ExperimentConfig(
            name="test_experiment",
            description="Test experiment description",
            data={"meal": "test_meal"},
            test_sets=[
                {"strategy": "factual", "num_questions": 20, "seed": 100},
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

    def _setup_experiment(self, temp_dir: Path):
        system_config = self._make_system_config(temp_dir)
        manager = ExperimentManager(system_config)
        config = self._make_config()
        exp_dir = manager.create_experiment_dir(config)
        manager.save_snapshots(exp_dir, config, {}, [], {})
        return manager, exp_dir

    @pytest.mark.unit
    def test_mark_variant_completed_with_hash(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            manager, exp_dir = self._setup_experiment(Path(temp_dir))

            manager.mark_variant_completed(
                exp_dir, "variant_a", config_hash="abc123def456"
            )

            with open(exp_dir / "manifest.json", encoding="utf-8") as f:
                manifest = json.load(f)
            assert "variant_a" in manifest["completed_variants"]
            assert manifest["variant_config_hashes"]["variant_a"] == "abc123def456"

    @pytest.mark.unit
    def test_mark_variant_completed_without_hash(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            manager, exp_dir = self._setup_experiment(Path(temp_dir))

            manager.mark_variant_completed(exp_dir, "variant_a")

            with open(exp_dir / "manifest.json", encoding="utf-8") as f:
                manifest = json.load(f)
            assert "variant_a" in manifest["completed_variants"]
            assert (
                "variant_config_hashes" not in manifest
                or "variant_a" not in manifest.get("variant_config_hashes", {})
            )

    @pytest.mark.unit
    def test_get_variant_config_hashes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            manager, exp_dir = self._setup_experiment(Path(temp_dir))

            manager.mark_variant_completed(exp_dir, "variant_a", config_hash="hash_a")
            manager.mark_variant_completed(exp_dir, "variant_b", config_hash="hash_b")

            hashes = manager.get_variant_config_hashes(exp_dir)
            assert hashes["variant_a"] == "hash_a"
            assert hashes["variant_b"] == "hash_b"

    @pytest.mark.unit
    def test_get_variant_config_hashes_empty(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            manager, exp_dir = self._setup_experiment(Path(temp_dir))

            hashes = manager.get_variant_config_hashes(exp_dir)
            assert hashes == {}

    @pytest.mark.unit
    def test_invalidate_variant(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            manager, exp_dir = self._setup_experiment(Path(temp_dir))

            manager.mark_variant_completed(exp_dir, "variant_a", config_hash="hash_a")
            manager.mark_variant_completed(exp_dir, "variant_b", config_hash="hash_b")

            manager.invalidate_variant(exp_dir, "variant_a")

            completed = manager.get_completed_variants(exp_dir)
            assert "variant_a" not in completed
            assert "variant_b" in completed

            hashes = manager.get_variant_config_hashes(exp_dir)
            assert "variant_a" not in hashes
            assert "variant_b" in hashes

    @pytest.mark.unit
    def test_invalidate_nonexistent_variant(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            manager, exp_dir = self._setup_experiment(Path(temp_dir))

            manager.invalidate_variant(exp_dir, "nonexistent")

            completed = manager.get_completed_variants(exp_dir)
            assert "nonexistent" not in completed

    @pytest.mark.unit
    def test_manifest_includes_variant_config_hashes_field(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            manager, exp_dir = self._setup_experiment(Path(temp_dir))

            with open(exp_dir / "manifest.json", encoding="utf-8") as f:
                manifest = json.load(f)
            assert "variant_config_hashes" in manifest
            assert manifest["variant_config_hashes"] == {}

    @pytest.mark.unit
    def test_backward_compatible_no_hashes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            manager, exp_dir = self._setup_experiment(Path(temp_dir))

            with open(exp_dir / "manifest.json", encoding="utf-8") as f:
                manifest = json.load(f)
            del manifest["variant_config_hashes"]
            with open(exp_dir / "manifest.json", "w", encoding="utf-8") as f:
                json.dump(manifest, f)

            hashes = manager.get_variant_config_hashes(exp_dir)
            assert hashes == {}

    @pytest.mark.unit
    def test_config_hash_verification_workflow(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            manager, exp_dir = self._setup_experiment(Path(temp_dir))

            variant = {
                "name": "variant_a",
                "config_overrides": {"chunker": {"chunk_size": 512}},
            }
            merged = {"chunker": {"chunk_size": 512, "chunk_overlap": 0}}
            config_hash = compute_variant_config_hash(
                variant,
                merged,
                exp_data={"meal": "test_meal"},
                exp_test_sets=[{"strategy": "factual"}],
                exp_evaluation={"metrics": {"retrieval": ["hit_rate"]}},
            )

            manager.mark_variant_completed(
                exp_dir, "variant_a", config_hash=config_hash
            )

            stored_hashes = manager.get_variant_config_hashes(exp_dir)
            assert stored_hashes["variant_a"] == config_hash

            same_hash = compute_variant_config_hash(
                variant,
                merged,
                exp_data={"meal": "test_meal"},
                exp_test_sets=[{"strategy": "factual"}],
                exp_evaluation={"metrics": {"retrieval": ["hit_rate"]}},
            )
            assert same_hash == config_hash

            changed_variant = {
                "name": "variant_a",
                "config_overrides": {"chunker": {"chunk_size": 1024}},
            }
            changed_merged = {"chunker": {"chunk_size": 1024, "chunk_overlap": 0}}
            changed_hash = compute_variant_config_hash(
                changed_variant,
                changed_merged,
                exp_data={"meal": "test_meal"},
                exp_test_sets=[{"strategy": "factual"}],
                exp_evaluation={"metrics": {"retrieval": ["hit_rate"]}},
            )
            assert changed_hash != config_hash


class TestOldFormatDeprecationRestored:
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
    def test_mixed_formats_emits_warning(self):
        data = self._make_config_dict()
        data["test_sets"] = [
            {
                "name": "new_format",
                "generation": {"strategy": "document", "num_questions": 10},
            },
            {"strategy": "factual", "num_questions": 20},
        ]
        config = ExperimentConfig.from_dict(data)
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            config.validate()
            deprecation_warnings = [
                x for x in w if issubclass(x.category, DeprecationWarning)
            ]
            assert len(deprecation_warnings) == 1

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
        data["test_sets"] = [
            {
                "name": "test",
                "generation": {"strategy": "document", "num_questions": 10},
            }
        ]
        config = ExperimentConfig.from_dict(data)
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            config.validate()
            deprecation_warnings = [
                x for x in w if issubclass(x.category, DeprecationWarning)
            ]
            assert len(deprecation_warnings) == 0
