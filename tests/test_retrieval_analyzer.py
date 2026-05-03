import pytest

from src.retrieval_analyzer import compute_ground_truth_metrics
from src.trace_models import PipelineTrace, TraceStep


@pytest.mark.unit
class TestComputeGroundTruthMetrics:
    def test_gt_found_in_retrieval(self):
        trace = PipelineTrace(
            trace_id="t1",
            question="What is revenue?",
            steps=[
                TraceStep(
                    stage="retrieval",
                    input_data={"query": "revenue", "top_k": 5},
                    output_data={
                        "results": [
                            {"chunk_id": "chunk_a", "score": 0.9, "source": "doc1.pdf"},
                            {"chunk_id": "chunk_b", "score": 0.8, "source": "doc2.pdf"},
                        ],
                        "count": 2,
                    },
                ),
            ],
        )
        metrics = compute_ground_truth_metrics(trace, ["chunk_a"])
        assert metrics["found_in_retrieval"] is True
        assert metrics["retrieval_rank"] == 1
        assert metrics["retrieval_score"] == 0.9

    def test_gt_not_in_retrieval(self):
        trace = PipelineTrace(
            trace_id="t2",
            question="What is profit?",
            steps=[
                TraceStep(
                    stage="retrieval",
                    input_data={"query": "profit", "top_k": 5},
                    output_data={
                        "results": [
                            {"chunk_id": "chunk_x", "score": 0.7, "source": "doc1.pdf"},
                            {"chunk_id": "chunk_y", "score": 0.6, "source": "doc2.pdf"},
                        ],
                        "count": 2,
                    },
                ),
            ],
        )
        metrics = compute_ground_truth_metrics(trace, ["chunk_a"])
        assert metrics["found_in_retrieval"] is False
        assert metrics["retrieval_rank"] is None
        assert metrics["retrieval_score"] is None

    def test_gt_found_in_rerank(self):
        trace = PipelineTrace(
            trace_id="t3",
            question="What is growth?",
            steps=[
                TraceStep(
                    stage="retrieval",
                    input_data={"query": "growth", "top_k": 5},
                    output_data={
                        "results": [
                            {"chunk_id": "chunk_a", "score": 0.5, "source": "doc1.pdf"},
                            {"chunk_id": "chunk_b", "score": 0.9, "source": "doc2.pdf"},
                        ],
                        "count": 2,
                    },
                ),
                TraceStep(
                    stage="rerank",
                    input_data={"query": "growth"},
                    output_data={
                        "results": [
                            {
                                "chunk_id": "chunk_a",
                                "score": 0.95,
                                "source": "doc1.pdf",
                            },
                            {
                                "chunk_id": "chunk_b",
                                "score": 0.85,
                                "source": "doc2.pdf",
                            },
                        ],
                        "count": 2,
                    },
                ),
            ],
        )
        metrics = compute_ground_truth_metrics(trace, ["chunk_a"])
        assert metrics["found_in_rerank"] is True
        assert metrics["rerank_rank"] == 1
        assert metrics["rerank_score"] == 0.95

    def test_no_rerank_step(self):
        trace = PipelineTrace(
            trace_id="t4",
            question="What is debt?",
            steps=[
                TraceStep(
                    stage="retrieval",
                    input_data={"query": "debt", "top_k": 5},
                    output_data={
                        "results": [
                            {"chunk_id": "chunk_a", "score": 0.8, "source": "doc1.pdf"},
                        ],
                        "count": 1,
                    },
                ),
            ],
        )
        metrics = compute_ground_truth_metrics(trace, ["chunk_a"])
        assert metrics["found_in_rerank"] is False
        assert metrics["rerank_rank"] is None
        assert metrics["rerank_score"] is None

    def test_context_dropped(self):
        trace = PipelineTrace(
            trace_id="t5",
            question="What is margin?",
            steps=[
                TraceStep(
                    stage="retrieval",
                    input_data={"query": "margin", "top_k": 5},
                    output_data={
                        "results": [
                            {"chunk_id": "chunk_b", "score": 0.9, "source": "doc2.pdf"},
                            {"chunk_id": "chunk_c", "score": 0.8, "source": "doc3.pdf"},
                            {"chunk_id": "chunk_a", "score": 0.7, "source": "doc1.pdf"},
                        ],
                        "count": 3,
                    },
                ),
                TraceStep(
                    stage="context_assembly",
                    input_data={
                        "chunks": [
                            {"chunk_id": "chunk_b"},
                            {"chunk_id": "chunk_c"},
                            {"chunk_id": "chunk_a"},
                        ],
                    },
                    output_data={"final_context_count": 2},
                ),
            ],
        )
        metrics = compute_ground_truth_metrics(trace, ["chunk_a"])
        assert metrics["found_in_retrieval"] is True
        assert metrics["retrieval_rank"] == 3
        assert metrics["found_in_context"] is False
        assert metrics["context_dropped"] is True

    def test_gt_in_context(self):
        trace = PipelineTrace(
            trace_id="t6",
            question="What is EBITDA?",
            steps=[
                TraceStep(
                    stage="retrieval",
                    input_data={"query": "EBITDA", "top_k": 5},
                    output_data={
                        "results": [
                            {"chunk_id": "chunk_a", "score": 0.9, "source": "doc1.pdf"},
                            {"chunk_id": "chunk_b", "score": 0.8, "source": "doc2.pdf"},
                        ],
                        "count": 2,
                    },
                ),
                TraceStep(
                    stage="context_assembly",
                    input_data={
                        "chunks": [
                            {"chunk_id": "chunk_a"},
                            {"chunk_id": "chunk_b"},
                        ],
                    },
                    output_data={"final_context_count": 2},
                ),
            ],
        )
        metrics = compute_ground_truth_metrics(trace, ["chunk_a"])
        assert metrics["found_in_context"] is True
        assert metrics["context_dropped"] is False

    def test_dict_trace_input(self):
        trace_dict = {
            "trace_id": "t7",
            "question": "What is ROI?",
            "steps": [
                {
                    "stage": "retrieval",
                    "input_data": {"query": "ROI", "top_k": 5},
                    "output_data": {
                        "results": [
                            {
                                "chunk_id": "chunk_a",
                                "score": 0.85,
                                "source": "doc1.pdf",
                            },
                        ],
                        "count": 1,
                    },
                },
            ],
        }
        metrics = compute_ground_truth_metrics(trace_dict, ["chunk_a"])
        assert metrics["found_in_retrieval"] is True
        assert metrics["retrieval_rank"] == 1
        assert metrics["retrieval_score"] == 0.85

    def test_empty_ground_truth(self):
        trace = PipelineTrace(
            trace_id="t8",
            question="What is cash flow?",
            steps=[
                TraceStep(
                    stage="retrieval",
                    input_data={"query": "cash flow", "top_k": 5},
                    output_data={
                        "results": [
                            {"chunk_id": "chunk_a", "score": 0.9, "source": "doc1.pdf"},
                        ],
                        "count": 1,
                    },
                ),
            ],
        )
        metrics = compute_ground_truth_metrics(trace, [])
        assert metrics["found_in_retrieval"] is False
        assert metrics["retrieval_rank"] is None
        assert metrics["retrieval_score"] is None
        assert metrics["found_in_rerank"] is False
        assert metrics["rerank_rank"] is None
        assert metrics["rerank_score"] is None
        assert metrics["found_in_context"] is False
        assert metrics["context_dropped"] is False
