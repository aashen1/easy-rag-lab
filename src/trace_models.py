from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

TRACE_STAGES = (
    "query_rewrite",
    "retrieval",
    "rerank",
    "context_assembly",
    "generation",
)

ROOT_CAUSES: dict[str, tuple[str, str]] = {
    "RC-0": ("healthy", "管线正常"),
    "RC-1": ("retrieval_miss", "正确 chunk 未被召回"),
    "RC-2": ("rank_too_low", "正确 chunk 被召回但排名靠后"),
    "RC-3": ("context_dropped", "正确 chunk 被截断丢弃"),
    "RC-4": ("generation_failure", "上下文包含正确信息但 LLM 未正确使用"),
    "RC-5": ("query_mismatch", "查询与文档词汇不匹配"),
}

SEVERITY_LEVELS = ("low", "medium", "high", "critical")


@dataclass
class TraceStep:
    """A single step in the RAG pipeline trace.

    Attributes:
        stage: Pipeline stage name (one of TRACE_STAGES).
        input_data: Input payload for this step.
        output_data: Output payload from this step.
        duration_ms: Wall-clock duration in milliseconds.
        metadata: Optional extra metadata for the step.
    """

    stage: str
    input_data: dict[str, Any]
    output_data: dict[str, Any]
    duration_ms: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the step to a plain dictionary.

        Returns:
            Dictionary representation of the trace step.
        """
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TraceStep:
        """Reconstruct a TraceStep from a dictionary.

        Args:
            data: Dictionary containing trace step data.

        Returns:
            TraceStep instance populated from the dictionary.

        Raises:
            KeyError: If required fields (stage, input_data, output_data)
                are missing from the input dictionary.
        """
        return cls(
            stage=data["stage"],
            input_data=data["input_data"],
            output_data=data["output_data"],
            duration_ms=data.get("duration_ms", 0.0),
            metadata=data.get("metadata", {}),
        )


@dataclass
class PipelineTrace:
    """Full trace of a RAG pipeline invocation.

    Attributes:
        trace_id: Unique identifier for this trace.
        question: The original user question.
        steps: Ordered list of pipeline steps.
        created_at: ISO-8601 timestamp of trace creation.
    """

    trace_id: str
    question: str
    steps: list[TraceStep] = field(default_factory=list)
    created_at: str = ""

    def __post_init__(self) -> None:
        if not self.created_at:
            self.created_at = datetime.now().isoformat()

    def to_dict(self) -> dict[str, Any]:
        """Serialize the trace to a plain dictionary.

        Returns:
            Dictionary representation with nested steps also serialized.
        """
        d = asdict(self)
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PipelineTrace:
        """Reconstruct a PipelineTrace from a dictionary.

        Args:
            data: Dictionary containing pipeline trace data.

        Returns:
            PipelineTrace instance with steps deserialized from nested dicts.

        Raises:
            KeyError: If required fields (trace_id, question) are missing.
        """
        steps = [TraceStep.from_dict(s) for s in data.get("steps", [])]
        return cls(
            trace_id=data["trace_id"],
            question=data["question"],
            steps=steps,
            created_at=data.get("created_at", ""),
        )


@dataclass
class GroundTruth:
    """Ground-truth annotation for a RAG evaluation sample.

    Attributes:
        answer_text: Expected answer text.
        source_pdf: Source PDF filename.
        source_page: Page number within the source PDF.
        chunk_ids: IDs of the relevant chunks.
        annotated_at: ISO-8601 timestamp of annotation.
        annotator: Name or identifier of the annotator.
    """

    answer_text: str = ""
    source_pdf: str = ""
    source_page: int | None = None
    chunk_ids: list[str] | None = None
    annotated_at: str = ""
    annotator: str = "user"

    def to_dict(self) -> dict[str, Any]:
        """Serialize the ground truth to a plain dictionary.

        Returns:
            Dictionary representation of the ground truth.
        """
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GroundTruth:
        """Reconstruct a GroundTruth from a dictionary.

        Args:
            data: Dictionary containing ground truth data.

        Returns:
            GroundTruth instance populated from the dictionary.
        """
        return cls(
            answer_text=data.get("answer_text", ""),
            source_pdf=data.get("source_pdf", ""),
            source_page=data.get("source_page"),
            chunk_ids=data.get("chunk_ids"),
            annotated_at=data.get("annotated_at", ""),
            annotator=data.get("annotator", "user"),
        )


@dataclass
class DiagnosisResult:
    """Diagnosis result identifying a root cause in the RAG pipeline.

    Attributes:
        root_cause: Human-readable root cause name.
        root_cause_id: Structured root cause identifier (e.g. RC-0).
        severity: Severity level (one of SEVERITY_LEVELS).
        finding: Description of what was found.
        fix_suggestion: Suggested fix for the issue.
        config_patch: Configuration changes that may address the issue.
        confidence: Confidence score between 0.0 and 1.0.
    """

    root_cause: str
    root_cause_id: str
    severity: str
    finding: str
    fix_suggestion: str = ""
    config_patch: dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        """Serialize the diagnosis result to a plain dictionary.

        Returns:
            Dictionary representation of the diagnosis result.
        """
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DiagnosisResult:
        """Reconstruct a DiagnosisResult from a dictionary.

        Args:
            data: Dictionary containing diagnosis result data.

        Returns:
            DiagnosisResult instance populated from the dictionary.

        Raises:
            KeyError: If required fields (root_cause, root_cause_id,
                severity, finding) are missing.
        """
        return cls(
            root_cause=data["root_cause"],
            root_cause_id=data["root_cause_id"],
            severity=data["severity"],
            finding=data["finding"],
            fix_suggestion=data.get("fix_suggestion", ""),
            config_patch=data.get("config_patch", {}),
            confidence=data.get("confidence", 1.0),
        )
