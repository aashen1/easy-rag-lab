import pytest

from src.case_diagnoser import diagnose
from src.trace_models import GroundTruth, PipelineTrace, TraceStep


def _make_retrieval_step(results: list[dict]) -> TraceStep:
    return TraceStep(
        stage="retrieval",
        input_data={"query": "test query"},
        output_data={"results": results},
    )


def _make_rerank_step(results: list[dict]) -> TraceStep:
    return TraceStep(
        stage="rerank",
        input_data={"query": "test query"},
        output_data={"results": results},
    )


def _make_context_step(chunks: list[dict], final_context_count: int) -> TraceStep:
    return TraceStep(
        stage="context_assembly",
        input_data={"chunks": chunks},
        output_data={"final_context_count": final_context_count},
    )


def _make_generation_step(answer: str) -> TraceStep:
    return TraceStep(
        stage="generation",
        input_data={"context": "some context"},
        output_data={"answer": answer},
    )


def _make_query_rewrite_step(rewritten_queries: list[str]) -> TraceStep:
    return TraceStep(
        stage="query_rewrite",
        input_data={"query": "original query"},
        output_data={"rewritten_queries": rewritten_queries},
    )


@pytest.mark.unit
class TestDiagnose:
    def test_rc0_healthy(self):
        gt_chunk_id = "chunk_gt_1"
        retrieval_step = _make_retrieval_step(
            [{"chunk_id": gt_chunk_id, "score": 0.95}]
        )
        context_step = _make_context_step(
            [{"chunk_id": gt_chunk_id}], final_context_count=3
        )
        generation_step = _make_generation_step("Revenue is 50 billion yuan")
        trace = PipelineTrace(
            trace_id="t1",
            question="What is the revenue?",
            steps=[retrieval_step, context_step, generation_step],
        )
        gt = GroundTruth(
            answer_text="Revenue is 50 billion",
            chunk_ids=[gt_chunk_id],
        )
        result = diagnose(trace, gt)
        assert result.root_cause_id == "RC-0"
        assert result.severity == "low"
        assert result.confidence == 1.0
        assert result.config_patch == {}

    def test_rc1_retrieval_miss(self):
        retrieval_step = _make_retrieval_step(
            [{"chunk_id": "chunk_other", "score": 0.8}]
        )
        context_step = _make_context_step(
            [{"chunk_id": "chunk_other"}], final_context_count=3
        )
        generation_step = _make_generation_step("I don't know")
        trace = PipelineTrace(
            trace_id="t2",
            question="What is the revenue?",
            steps=[retrieval_step, context_step, generation_step],
        )
        gt = GroundTruth(
            answer_text="Revenue is 50 billion",
            chunk_ids=["chunk_gt_1"],
        )
        result = diagnose(trace, gt)
        assert result.root_cause_id == "RC-1"
        assert result.severity == "high"
        assert result.confidence == 0.8
        assert "retrieval.top_k" in result.config_patch

    def test_rc2_rank_too_low(self):
        gt_chunk_id = "chunk_gt_1"
        results = [
            {"chunk_id": f"chunk_other_{i}", "score": 0.9 - i * 0.05} for i in range(4)
        ]
        results.append({"chunk_id": gt_chunk_id, "score": 0.5})
        retrieval_step = _make_retrieval_step(results)
        context_step = _make_context_step(
            [{"chunk_id": f"chunk_other_{i}"} for i in range(4)],
            final_context_count=3,
        )
        generation_step = _make_generation_step("Some answer")
        trace = PipelineTrace(
            trace_id="t3",
            question="What is the revenue?",
            steps=[retrieval_step, context_step, generation_step],
        )
        gt = GroundTruth(
            answer_text="Revenue is 50 billion",
            chunk_ids=[gt_chunk_id],
        )
        result = diagnose(trace, gt)
        assert result.root_cause_id == "RC-2"
        assert result.severity == "medium"
        assert result.confidence == 0.8

    def test_rc3_context_dropped(self):
        gt_chunk_id = "chunk_gt_1"
        retrieval_step = _make_retrieval_step([{"chunk_id": gt_chunk_id, "score": 0.7}])
        context_step = _make_context_step(
            [{"chunk_id": gt_chunk_id}], final_context_count=0
        )
        generation_step = _make_generation_step("I don't know")
        trace = PipelineTrace(
            trace_id="t4",
            question="What is the revenue?",
            steps=[retrieval_step, context_step, generation_step],
        )
        gt = GroundTruth(
            answer_text="Revenue is 50 billion",
            chunk_ids=[gt_chunk_id],
        )
        result = diagnose(trace, gt)
        assert result.root_cause_id == "RC-3"
        assert result.severity == "high"
        assert result.confidence == 0.8
        assert "generation.max_context_tokens" in result.config_patch

    def test_rc4_generation_failure(self):
        gt_chunk_id = "chunk_gt_1"
        retrieval_step = _make_retrieval_step(
            [{"chunk_id": gt_chunk_id, "score": 0.95}]
        )
        context_step = _make_context_step(
            [{"chunk_id": gt_chunk_id}], final_context_count=3
        )
        generation_step = _make_generation_step("The answer is completely wrong")
        trace = PipelineTrace(
            trace_id="t5",
            question="What is the revenue?",
            steps=[retrieval_step, context_step, generation_step],
        )
        gt = GroundTruth(
            answer_text="Revenue is 50 billion",
            chunk_ids=[gt_chunk_id],
        )
        result = diagnose(trace, gt)
        assert result.root_cause_id == "RC-4"
        assert result.severity == "medium"
        assert result.confidence == 0.8

    def test_rc5_query_mismatch(self):
        retrieval_step = _make_retrieval_step(
            [{"chunk_id": "chunk_other", "score": 0.8}]
        )
        rewrite_step = _make_query_rewrite_step(
            ["what is the total revenue", "revenue breakdown"]
        )
        context_step = _make_context_step(
            [{"chunk_id": "chunk_other"}], final_context_count=3
        )
        generation_step = _make_generation_step("I don't know")
        trace = PipelineTrace(
            trace_id="t6",
            question="What is the revenue?",
            steps=[rewrite_step, retrieval_step, context_step, generation_step],
        )
        gt = GroundTruth(
            answer_text="Revenue is 50 billion",
            chunk_ids=["chunk_gt_1"],
        )
        result = diagnose(trace, gt)
        assert result.root_cause_id == "RC-5"
        assert result.severity == "medium"
        assert result.confidence == 0.6
        assert "retrieval.query_rewrite.enabled" in result.config_patch

    def test_empty_ground_truth(self):
        retrieval_step = _make_retrieval_step(
            [{"chunk_id": "chunk_other", "score": 0.8}]
        )
        generation_step = _make_generation_step("Some answer")
        trace = PipelineTrace(
            trace_id="t7",
            question="What is the revenue?",
            steps=[retrieval_step, generation_step],
        )
        gt = GroundTruth(
            answer_text="Revenue is 50 billion",
            chunk_ids=[],
        )
        result = diagnose(trace, gt)
        assert result.root_cause_id == "RC-1"
        assert result.severity == "high"

    def test_dict_inputs(self):
        gt_chunk_id = "chunk_gt_1"
        trace_dict = {
            "trace_id": "t8",
            "question": "What is the revenue?",
            "steps": [
                {
                    "stage": "retrieval",
                    "input_data": {"query": "test"},
                    "output_data": {
                        "results": [{"chunk_id": gt_chunk_id, "score": 0.95}]
                    },
                },
                {
                    "stage": "context_assembly",
                    "input_data": {"chunks": [{"chunk_id": gt_chunk_id}]},
                    "output_data": {"final_context_count": 3},
                },
                {
                    "stage": "generation",
                    "input_data": {"context": "some context"},
                    "output_data": {"answer": "Revenue is 50 billion yuan"},
                },
            ],
        }
        gt_dict = {
            "answer_text": "Revenue is 50 billion",
            "source_pdf": "report.pdf",
            "source_page": 12,
            "chunk_ids": [gt_chunk_id],
        }
        result = diagnose(trace_dict, gt_dict)
        assert result.root_cause_id == "RC-0"
        assert result.severity == "low"
        assert result.confidence == 1.0
