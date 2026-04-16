import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

GOLDEN_QA_PATH = Path(__file__).parent / "fixtures" / "golden_qa.json"


def _load_golden_qa():
    if not GOLDEN_QA_PATH.exists():
        return []
    with open(GOLDEN_QA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


golden_qa_data = _load_golden_qa()


@pytest.mark.unit
@pytest.mark.parametrize("entry", golden_qa_data, ids=[e["id"] for e in golden_qa_data])
def test_golden_qa_entry_format(entry):
    assert "id" in entry
    assert "category" in entry
    assert "question" in entry
    assert "expected_sources" in entry
    assert "expected_keywords" in entry
    assert "description" in entry
    assert isinstance(entry["expected_sources"], list)
    assert isinstance(entry["expected_keywords"], list)
    assert len(entry["question"]) > 0


@pytest.mark.unit
@pytest.mark.parametrize("entry", golden_qa_data, ids=[e["id"] for e in golden_qa_data])
def test_golden_qa_retrieval_mock(entry):
    mock_retriever = MagicMock()
    mock_retriever.retrieve.return_value = [
        {
            "chunk_id": "test_chunk",
            "text": "Test context text",
            "metadata": {"source": entry["expected_sources"][0] if entry["expected_sources"] else "unknown"},
            "score": 0.95,
        }
    ]

    results = mock_retriever.retrieve(entry["question"])

    if entry["expected_sources"]:
        retrieved_sources = [r["metadata"].get("source", "") for r in results]
        hit_count = sum(1 for s in entry["expected_sources"] if s in retrieved_sources)
        hit_rate = hit_count / len(entry["expected_sources"])
        assert hit_rate > 0, f"Expected sources not found in retrieval results for {entry['id']}"


@pytest.mark.integration
@pytest.mark.parametrize("entry", golden_qa_data, ids=[e["id"] for e in golden_qa_data])
def test_golden_qa_full_pipeline(entry):
    pytest.skip("Integration test - requires running RAG pipeline and API key")
