from dataclasses import dataclass
from typing import Any


@dataclass
class TestCaseResult:
    __test__ = False
    id: str
    question: str
    answer: str | None
    retrieval: dict[str, float] | None = None
    generation: dict[str, float] | None = None
    llm_retrieval: dict[str, float] | None = None
    sources: list[str] | None = None
    error: str | None = None
    time_seconds: float = 0.0
    category: str | None = None


@dataclass
class VariantResult:
    variant_name: str
    variant_description: str | None = None
    retrieval_metrics: dict[str, float] | None = None
    generation_metrics: dict[str, float] | None = None
    llm_retrieval_metrics: dict[str, float] | None = None
    config_snapshot: dict[str, Any] | None = None
    total_questions: int = 0
    total_time_seconds: float = 0.0
    error: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "VariantResult":
        return cls(
            variant_name=data.get("variant_name", "unnamed"),
            variant_description=data.get("variant_description"),
            retrieval_metrics=data.get("retrieval_metrics"),
            generation_metrics=data.get("generation_metrics"),
            llm_retrieval_metrics=data.get("llm_retrieval_metrics"),
            config_snapshot=data.get("config_snapshot"),
            total_questions=data.get("total_questions", 0),
            total_time_seconds=data.get("total_time_seconds", 0.0),
            error=data.get("error"),
        )


@dataclass
class ReportExperimentResult:
    timestamp: str
    total_test_cases: int
    total_time_seconds: float
    avg_time_per_case: float
    retrieval_metrics: dict[str, float]
    results: list[TestCaseResult]
    generation_metrics: dict[str, float] | None = None
    llm_retrieval_metrics: dict[str, float] | None = None
    meal_data_id: str | None = None
    meal_name: str | None = None
    config_snapshot: dict[str, Any] | None = None
    config_hashes: dict[str, str] | None = None
    pdf_files: list[dict[str, Any]] | None = None
    stats: dict[str, Any] | None = None
    variant_results: list[VariantResult] | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ReportExperimentResult":
        results = []
        for r in data.get("results", []):
            results.append(
                TestCaseResult(
                    id=r.get("id", ""),
                    question=r.get("question", ""),
                    answer=r.get("answer"),
                    retrieval=r.get("retrieval"),
                    generation=r.get("generation"),
                    llm_retrieval=r.get("llm_retrieval"),
                    sources=r.get("sources"),
                    error=r.get("error"),
                    time_seconds=r.get("time_seconds", 0.0),
                    category=r.get("category"),
                )
            )

        variant_results = None
        if "variant_results" in data:
            variant_results = [
                VariantResult.from_dict(vr) for vr in data.get("variant_results", [])
            ]

        return cls(
            timestamp=data.get("timestamp", ""),
            total_test_cases=data.get("total_test_cases", 0),
            total_time_seconds=data.get("total_time_seconds", 0.0),
            avg_time_per_case=data.get("avg_time_per_case", 0.0),
            retrieval_metrics=data.get("retrieval_metrics", {}),
            results=results,
            generation_metrics=data.get("generation_metrics"),
            llm_retrieval_metrics=data.get("llm_retrieval_metrics"),
            meal_data_id=data.get("meal_data_id"),
            meal_name=data.get("meal_name"),
            config_snapshot=data.get("config_snapshot"),
            config_hashes=data.get("config_hashes"),
            pdf_files=data.get("pdf_files"),
            stats=data.get("stats"),
            variant_results=variant_results,
        )
