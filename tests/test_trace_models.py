import pytest

from src.trace_models import (
    ROOT_CAUSES,
    SEVERITY_LEVELS,
    TRACE_STAGES,
    DiagnosisResult,
    GroundTruth,
    PipelineTrace,
    TraceStep,
)


@pytest.mark.unit
class TestTraceStep:
    def test_to_dict(self):
        step = TraceStep(
            stage="retrieval",
            input_data={"query": "test"},
            output_data={"docs": ["d1"]},
            duration_ms=12.5,
            metadata={"key": "val"},
        )
        d = step.to_dict()
        assert d["stage"] == "retrieval"
        assert d["input_data"] == {"query": "test"}
        assert d["output_data"] == {"docs": ["d1"]}
        assert d["duration_ms"] == 12.5
        assert d["metadata"] == {"key": "val"}

    def test_from_dict(self):
        data = {
            "stage": "generation",
            "input_data": {"ctx": "c"},
            "output_data": {"ans": "a"},
            "duration_ms": 5.0,
            "metadata": {"x": 1},
        }
        step = TraceStep.from_dict(data)
        assert step.stage == "generation"
        assert step.input_data == {"ctx": "c"}
        assert step.output_data == {"ans": "a"}
        assert step.duration_ms == 5.0
        assert step.metadata == {"x": 1}

    def test_roundtrip(self):
        step = TraceStep(
            stage="rerank",
            input_data={"q": "q"},
            output_data={"ranked": [1, 2]},
            duration_ms=3.0,
            metadata={"m": "n"},
        )
        result = TraceStep.from_dict(step.to_dict())
        assert result == step

    def test_defaults(self):
        step = TraceStep(
            stage="retrieval",
            input_data={},
            output_data={},
        )
        assert step.duration_ms == 0.0
        assert step.metadata == {}


@pytest.mark.unit
class TestPipelineTrace:
    def test_to_dict(self):
        step = TraceStep(stage="retrieval", input_data={}, output_data={})
        trace = PipelineTrace(
            trace_id="t1",
            question="What?",
            steps=[step],
            created_at="2026-01-01T00:00:00",
        )
        d = trace.to_dict()
        assert d["trace_id"] == "t1"
        assert d["question"] == "What?"
        assert len(d["steps"]) == 1
        assert d["steps"][0]["stage"] == "retrieval"
        assert d["created_at"] == "2026-01-01T00:00:00"

    def test_from_dict(self):
        data = {
            "trace_id": "t2",
            "question": "How?",
            "steps": [
                {"stage": "generation", "input_data": {}, "output_data": {}},
            ],
            "created_at": "2026-05-01T12:00:00",
        }
        trace = PipelineTrace.from_dict(data)
        assert trace.trace_id == "t2"
        assert trace.question == "How?"
        assert len(trace.steps) == 1
        assert isinstance(trace.steps[0], TraceStep)
        assert trace.steps[0].stage == "generation"

    def test_roundtrip(self):
        step = TraceStep(
            stage="rerank", input_data={"a": 1}, output_data={"b": 2}, duration_ms=7.5
        )
        trace = PipelineTrace(
            trace_id="t3",
            question="Why?",
            steps=[step],
            created_at="2026-03-15T10:30:00",
        )
        result = PipelineTrace.from_dict(trace.to_dict())
        assert result == trace

    def test_created_at_auto_fill(self):
        trace = PipelineTrace(trace_id="t4", question="Q?")
        assert trace.created_at != ""
        assert "T" in trace.created_at

    def test_created_at_preserved(self):
        trace = PipelineTrace(
            trace_id="t5",
            question="Q?",
            created_at="2026-06-01T08:00:00",
        )
        assert trace.created_at == "2026-06-01T08:00:00"


@pytest.mark.unit
class TestGroundTruth:
    def test_to_dict(self):
        gt = GroundTruth(
            answer_text="Revenue is 50B",
            source_pdf="report.pdf",
            source_page=12,
            chunk_ids=["c1", "c2"],
            annotated_at="2026-05-01T10:00:00",
            annotator="expert",
        )
        d = gt.to_dict()
        assert d["answer_text"] == "Revenue is 50B"
        assert d["source_pdf"] == "report.pdf"
        assert d["source_page"] == 12
        assert d["chunk_ids"] == ["c1", "c2"]
        assert d["annotated_at"] == "2026-05-01T10:00:00"
        assert d["annotator"] == "expert"

    def test_from_dict(self):
        data = {
            "answer_text": "Yes",
            "source_pdf": "doc.pdf",
            "source_page": 5,
            "chunk_ids": ["c3"],
            "annotated_at": "2026-04-01T09:00:00",
            "annotator": "bot",
        }
        gt = GroundTruth.from_dict(data)
        assert gt.answer_text == "Yes"
        assert gt.source_pdf == "doc.pdf"
        assert gt.source_page == 5
        assert gt.chunk_ids == ["c3"]
        assert gt.annotated_at == "2026-04-01T09:00:00"
        assert gt.annotator == "bot"

    def test_roundtrip(self):
        gt = GroundTruth(
            answer_text="No",
            source_pdf="f.pdf",
            source_page=3,
            chunk_ids=["c4"],
            annotated_at="2026-02-01T00:00:00",
            annotator="user",
        )
        result = GroundTruth.from_dict(gt.to_dict())
        assert result == gt

    def test_defaults(self):
        gt = GroundTruth()
        assert gt.answer_text == ""
        assert gt.source_pdf == ""
        assert gt.source_page is None
        assert gt.chunk_ids is None
        assert gt.annotator == "user"


@pytest.mark.unit
class TestDiagnosisResult:
    def test_to_dict(self):
        dr = DiagnosisResult(
            root_cause="retrieval_miss",
            root_cause_id="RC-1",
            severity="high",
            finding="Correct chunk not retrieved",
            fix_suggestion="Increase top_k",
            config_patch={"retrieval": {"top_k": 20}},
            confidence=0.85,
        )
        d = dr.to_dict()
        assert d["root_cause"] == "retrieval_miss"
        assert d["root_cause_id"] == "RC-1"
        assert d["severity"] == "high"
        assert d["finding"] == "Correct chunk not retrieved"
        assert d["fix_suggestion"] == "Increase top_k"
        assert d["config_patch"] == {"retrieval": {"top_k": 20}}
        assert d["confidence"] == 0.85

    def test_from_dict(self):
        data = {
            "root_cause": "rank_too_low",
            "root_cause_id": "RC-2",
            "severity": "medium",
            "finding": "Chunk ranked too low",
            "fix_suggestion": "Enable reranker",
            "config_patch": {"reranker": {"enabled": True}},
            "confidence": 0.7,
        }
        dr = DiagnosisResult.from_dict(data)
        assert dr.root_cause == "rank_too_low"
        assert dr.root_cause_id == "RC-2"
        assert dr.severity == "medium"
        assert dr.finding == "Chunk ranked too low"
        assert dr.fix_suggestion == "Enable reranker"
        assert dr.config_patch == {"reranker": {"enabled": True}}
        assert dr.confidence == 0.7

    def test_roundtrip(self):
        dr = DiagnosisResult(
            root_cause="generation_failure",
            root_cause_id="RC-4",
            severity="critical",
            finding="LLM ignored context",
            fix_suggestion="Adjust prompt",
            config_patch={"prompt": {"template": "v2"}},
            confidence=0.6,
        )
        result = DiagnosisResult.from_dict(dr.to_dict())
        assert result == dr

    def test_defaults(self):
        dr = DiagnosisResult(
            root_cause="healthy",
            root_cause_id="RC-0",
            severity="low",
            finding="All good",
        )
        assert dr.fix_suggestion == ""
        assert dr.config_patch == {}
        assert dr.confidence == 1.0


@pytest.mark.unit
class TestConstants:
    def test_trace_stages(self):
        assert len(TRACE_STAGES) == 5

    def test_root_causes(self):
        assert len(ROOT_CAUSES) == 6
        for i in range(6):
            assert f"RC-{i}" in ROOT_CAUSES

    def test_severity_levels(self):
        assert len(SEVERITY_LEVELS) == 4
