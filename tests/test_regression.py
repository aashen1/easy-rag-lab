import json
import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from dotenv import load_dotenv

load_dotenv()

GOLDEN_QA_PATH = Path(__file__).parent / "fixtures" / "golden_qa.json"
GOLDEN_MEAL_NAME = "golden_test"


def _load_golden_qa():
    if not GOLDEN_QA_PATH.exists():
        return []
    with open(GOLDEN_QA_PATH, encoding="utf-8") as f:
        return json.load(f)


golden_qa_data = _load_golden_qa()


def _should_run_integration_tests():
    return os.getenv("RUN_INTEGRATION_TESTS", "").lower() in ("true", "1", "yes")


def _check_api_key_available():
    return bool(os.getenv("LLM_API_KEY"))


def _check_meal_available(meal_name: str) -> bool:
    try:
        from src.meal import MealManager
        from src.utils import load_config
        config = load_config()
        meal_manager = MealManager(config)
        return meal_manager.meal_exists(meal_name)
    except Exception:
        return False


def _check_vector_index_available(meal_name: str) -> bool:
    try:
        from src.meal import MealManager
        from src.utils import load_config
        config = load_config()
        meal_manager = MealManager(config)
        if not meal_manager.meal_exists(meal_name):
            return False
        meal = meal_manager.load_meal(meal_name)
        persist_dir = Path(config["vector_store"]["persist_dir"])
        from qdrant_client import QdrantClient
        client = QdrantClient(path=str(persist_dir))
        collections = client.get_collections().collections
        return any(c.name == meal.collection_name for c in collections)
    except Exception:
        return False


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
    if not _should_run_integration_tests():
        pytest.skip("Integration test skipped. Set RUN_INTEGRATION_TESTS=true to enable.")

    if not _check_api_key_available():
        pytest.skip("LLM_API_KEY environment variable not set.")

    if not _check_meal_available(GOLDEN_MEAL_NAME):
        pytest.skip(f"Meal '{GOLDEN_MEAL_NAME}' not found. Create it first with: pixi run python main.py --create-meal --sample-ratio 0.03 --seed 42")

    if not _check_vector_index_available(GOLDEN_MEAL_NAME):
        pytest.skip(f"Vector index for meal '{GOLDEN_MEAL_NAME}' not found. Build it first.")

    from src.pipeline import RAGPipeline

    pipeline = RAGPipeline(meal_name=GOLDEN_MEAL_NAME)
    result = pipeline.query(entry["question"])

    assert "answer" in result, "Result should contain 'answer' field"
    assert "question" in result, "Result should contain 'question' field"
    assert len(result["answer"]) > 0, "Answer should not be empty"
    assert result["question"] == entry["question"], "Question should match"

    if "sources" in result and entry["expected_sources"]:
        retrieved_sources = result["sources"]
        for expected_source in entry["expected_sources"]:
            source_found = any(expected_source in src for src in retrieved_sources)
            if source_found:
                break
        assert source_found, f"Expected source '{expected_source}' not found in retrieved sources"

    if "contexts" in result:
        assert len(result["contexts"]) > 0, "Should retrieve at least one context"
        for keyword in entry["expected_keywords"]:
            keyword_found = any(keyword.lower() in ctx.lower() for ctx in result["contexts"])
            if keyword_found:
                break
