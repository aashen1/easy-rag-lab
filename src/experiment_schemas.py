from typing import Any

from pydantic import BaseModel, ValidationInfo, model_validator

from src.experiment import (
    VALID_EVALUATION_BACKENDS,
    VALID_FORCE_OVERWRITE_STAGES,
    VALID_GENERATION_METRICS,
    VALID_ON_MISSING_VALUES,
    VALID_RAGAS_METRICS,
    VALID_RETRIEVAL_METRICS,
    is_new_format,
)
from src.experiment_reuse import VALID_REUSE_MODES


class ExperimentConfigSchema(BaseModel):
    model_config = {"extra": "allow"}

    name: Any
    description: Any
    data: Any
    test_sets: Any
    variants: Any
    evaluation: Any
    force_overwrite: Any = []

    @model_validator(mode="after")
    def validate_experiment(self, info: ValidationInfo) -> "ExperimentConfigSchema":
        ctx = info.context or {}
        errors: list[str] = ctx.setdefault("errors", [])

        self._validate_name(errors)
        self._validate_description(errors)
        self._validate_data(errors)
        self._validate_test_sets(errors, ctx)
        self._validate_variants(errors)
        self._validate_evaluation(errors)
        self._validate_retrieval_granularity(errors)
        self._validate_force_overwrite(errors)
        self._validate_reuse(errors)

        return self

    def _validate_name(self, errors: list[str]) -> None:
        if not self.name or not self.name.strip():
            errors.append("Experiment name cannot be empty")

    def _validate_description(self, errors: list[str]) -> None:
        if not self.description or not self.description.strip():
            errors.append("Experiment description cannot be empty")

    def _validate_data(self, errors: list[str]) -> None:
        if isinstance(self.data, dict) and "meal" not in self.data:
            errors.append("Data configuration must include 'meal' field")

    def _validate_test_sets(self, errors: list[str], ctx: dict[str, Any]) -> None:
        if not self.test_sets:
            errors.append("At least one test set must be defined")
            return

        if not isinstance(self.test_sets, list):
            return

        has_old_format = False
        for i, test_set in enumerate(self.test_sets):
            if not isinstance(test_set, dict):
                continue

            if is_new_format(test_set):
                self._validate_new_format_test_set(i, test_set, errors)
            else:
                has_old_format = True
                self._validate_old_format_test_set(i, test_set, errors)

        ctx["has_old_format"] = has_old_format

    def _validate_new_format_test_set(
        self, idx: int, test_set: dict[str, Any], errors: list[str]
    ) -> None:
        name = test_set.get("name")
        if name is not None and not isinstance(name, str):
            errors.append(f"Test set {idx} 'name' must be a string if provided")

        if "generation" in test_set:
            generation = test_set["generation"]
            if not isinstance(generation, dict):
                errors.append(f"Test set {idx} 'generation' must be a dictionary")
            else:
                if "strategy" not in generation:
                    errors.append(
                        f"Test set {idx} 'generation' missing 'strategy' field"
                    )
                if "num_questions" not in generation:
                    errors.append(
                        f"Test set {idx} 'generation' missing 'num_questions' field"
                    )

        if "on_missing" in test_set:
            on_missing = test_set["on_missing"]
            if on_missing not in VALID_ON_MISSING_VALUES:
                errors.append(
                    f"Test set {idx} invalid 'on_missing' value: '{on_missing}'. "
                    f"Valid options: {sorted(VALID_ON_MISSING_VALUES)}"
                )

    def _validate_old_format_test_set(
        self, idx: int, test_set: dict[str, Any], errors: list[str]
    ) -> None:
        if "strategy" not in test_set:
            errors.append(f"Test set {idx} missing 'strategy' field")
        if "num_questions" not in test_set:
            errors.append(f"Test set {idx} missing 'num_questions' field")

    def _validate_variants(self, errors: list[str]) -> None:
        if not self.variants:
            errors.append("At least one variant must be defined")
            return

        if not isinstance(self.variants, list):
            return

        for i, variant in enumerate(self.variants):
            if isinstance(variant, dict) and "name" not in variant:
                errors.append(f"Variant {i} missing 'name' field")

    def _validate_evaluation(self, errors: list[str]) -> None:
        if not isinstance(self.evaluation, dict):
            return

        VALID_METRICS_PRESETS = {"core", "extended", "full", "custom"}
        has_metrics = "metrics" in self.evaluation
        has_preset = "metrics_preset" in self.evaluation

        if not has_metrics and not has_preset:
            errors.append(
                "Evaluation configuration must include 'metrics' or 'metrics_preset' field"
            )

        if has_preset:
            self._validate_metrics_preset(errors, VALID_METRICS_PRESETS)

        if has_metrics:
            self._validate_metrics(errors)

    def _validate_metrics_preset(
        self, errors: list[str], valid_presets: set[str]
    ) -> None:
        metrics_preset = self.evaluation["metrics_preset"]
        if metrics_preset not in valid_presets:
            errors.append(
                f"Invalid metrics_preset: '{metrics_preset}'. "
                f"Valid options: {sorted(valid_presets)}"
            )

        if metrics_preset == "custom":
            custom_metrics = self.evaluation.get("custom_metrics")
            if custom_metrics is None:
                errors.append(
                    "custom_metrics must be provided when metrics_preset='custom'"
                )
            elif not isinstance(custom_metrics, dict):
                errors.append("custom_metrics must be a dictionary")
            else:
                self._validate_custom_metrics(errors, custom_metrics)

    def _validate_custom_metrics(
        self, errors: list[str], custom_metrics: dict[str, Any]
    ) -> None:
        if "retrieval" not in custom_metrics:
            errors.append("custom_metrics must include 'retrieval' field")
        else:
            invalid_retrieval = [
                m
                for m in custom_metrics["retrieval"]
                if m not in VALID_RETRIEVAL_METRICS
            ]
            if invalid_retrieval:
                errors.append(
                    f"Invalid retrieval metrics in custom_metrics: {invalid_retrieval}. "
                    f"Valid options: {sorted(VALID_RETRIEVAL_METRICS)}"
                )

        if "generation" in custom_metrics:
            all_valid_generation = VALID_GENERATION_METRICS | VALID_RAGAS_METRICS
            invalid_generation = [
                m for m in custom_metrics["generation"] if m not in all_valid_generation
            ]
            if invalid_generation:
                errors.append(
                    f"Invalid generation metrics in custom_metrics: {invalid_generation}. "
                    f"Valid options: {sorted(all_valid_generation)}"
                )

    def _validate_metrics(self, errors: list[str]) -> None:
        metrics = self.evaluation["metrics"]
        if not isinstance(metrics, dict):
            errors.append("Evaluation 'metrics' must be a dictionary")
            return

        backends = self.evaluation.get("backends", ["builtin"])
        if not isinstance(backends, list):
            errors.append("Evaluation 'backends' must be a list")
        else:
            invalid_backends = [
                b for b in backends if b not in VALID_EVALUATION_BACKENDS
            ]
            if invalid_backends:
                errors.append(
                    f"Invalid evaluation backends: {invalid_backends}. "
                    f"Valid options: {sorted(VALID_EVALUATION_BACKENDS)}"
                )

        if "retrieval" not in metrics:
            errors.append("Evaluation metrics must include 'retrieval' field")
        else:
            self._validate_retrieval_metrics(errors, metrics, backends)

        if "generation" in metrics:
            self._validate_generation_metrics(errors, metrics, backends)

    def _validate_retrieval_metrics(
        self, errors: list[str], metrics: dict[str, Any], backends: Any
    ) -> None:
        retrieval_metrics = metrics["retrieval"]
        if not isinstance(retrieval_metrics, list):
            errors.append("Retrieval metrics must be a list")
            return

        invalid_retrieval = [
            m for m in retrieval_metrics if m not in VALID_RETRIEVAL_METRICS
        ]
        if invalid_retrieval:
            errors.append(
                f"Invalid retrieval metrics: {invalid_retrieval}. "
                f"Valid options: {sorted(VALID_RETRIEVAL_METRICS)}"
            )

        llm_retrieval_in_retrieval = [
            m for m in retrieval_metrics if m in {"context_precision", "context_recall"}
        ]
        if (
            llm_retrieval_in_retrieval
            and "ragas" not in backends
            and "builtin" not in backends
        ):
            errors.append(
                f"LLM-based retrieval metrics {llm_retrieval_in_retrieval} require "
                f"'builtin' or 'ragas' in evaluation.backends"
            )

    def _validate_generation_metrics(
        self, errors: list[str], metrics: dict[str, Any], backends: Any
    ) -> None:
        generation_metrics = metrics["generation"]
        if not isinstance(generation_metrics, list):
            errors.append("Generation metrics must be a list")
            return

        all_valid_generation = VALID_GENERATION_METRICS | VALID_RAGAS_METRICS
        invalid_generation = [
            m for m in generation_metrics if m not in all_valid_generation
        ]
        if invalid_generation:
            errors.append(
                f"Invalid generation metrics: {invalid_generation}. "
                f"Valid options: {sorted(all_valid_generation)}"
            )

        non_builtin_generation = [
            m for m in generation_metrics if m not in VALID_GENERATION_METRICS
        ]
        if non_builtin_generation and "ragas" not in backends:
            errors.append(
                f"Metrics {non_builtin_generation} in generation require "
                f"'ragas' in evaluation.backends (not supported by builtin backend)"
            )

    def _validate_retrieval_granularity(self, errors: list[str]) -> None:
        if not isinstance(self.evaluation, dict):
            return

        if "retrieval_granularity" in self.evaluation:
            valid_granularities = {"chunk", "document", "both"}
            granularity = self.evaluation["retrieval_granularity"]
            if granularity not in valid_granularities:
                errors.append(
                    f"Invalid retrieval_granularity: '{granularity}'. "
                    f"Valid options: {sorted(valid_granularities)}"
                )

    def _validate_force_overwrite(self, errors: list[str]) -> None:
        if self.force_overwrite and self.force_overwrite != "all":
            if not isinstance(self.force_overwrite, list):
                errors.append(
                    "force_overwrite must be a list of stage names or the string 'all'"
                )
            else:
                invalid_stages = [
                    s
                    for s in self.force_overwrite
                    if s not in VALID_FORCE_OVERWRITE_STAGES
                ]
                if invalid_stages:
                    errors.append(
                        f"Invalid force_overwrite stages: {invalid_stages}. "
                        f"Valid options: {sorted(VALID_FORCE_OVERWRITE_STAGES)}"
                    )

    def _validate_reuse(self, errors: list[str]) -> None:
        reuse = getattr(self, "reuse", None)
        if reuse is None:
            return

        if not isinstance(reuse, dict):
            errors.append("reuse configuration must be a dictionary")
            return

        mode = reuse.get("mode", "none")
        if mode not in VALID_REUSE_MODES:
            errors.append(
                f"Invalid reuse mode: '{mode}'. "
                f"Valid options: {sorted(VALID_REUSE_MODES)}"
            )

        if mode == "in_place" and not reuse.get("target_dir"):
            errors.append("In-place reuse mode requires 'target_dir' to be specified")

        if mode == "copy_migrate" and not reuse.get("source_dir"):
            errors.append(
                "Copy-migrate reuse mode requires 'source_dir' to be specified"
            )
