import contextlib
import shutil
import warnings
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from streamlit.testing.v1 import AppTest

from src.meal.models import MealConfig, MealFile

warnings.simplefilter("always", DeprecationWarning)


def pytest_configure(config):
    basetemp = config.getoption("basetemp", default=None)
    if basetemp is not None:
        basetemp_path = Path(basetemp)
        if basetemp_path.is_absolute():
            target = basetemp_path
        else:
            target = Path(config.rootdir) / basetemp_path
        if target.exists():
            with contextlib.suppress(OSError):
                shutil.rmtree(target)


@pytest.fixture
def mock_embedder():
    embedder = MagicMock()
    embedder.embedding_dim = 1024
    embedder.get_embedding_dimension.return_value = 1024
    embedder.embed_query.return_value = np.ones(1024, dtype=np.float32)
    embedder.embed_texts.return_value = np.ones((3, 1024), dtype=np.float32)
    return embedder


@pytest.fixture
def mock_qdrant_client():
    client = MagicMock()

    mock_collection_info = MagicMock()
    mock_collection_info.points_count = 100
    mock_collection_info.status.value = "green"
    client.get_collection.return_value = mock_collection_info

    mock_collections_response = MagicMock()
    mock_collections_response.collections = []
    client.get_collections.return_value = mock_collections_response

    return client


@pytest.fixture
def mock_anthropic_client():
    client = MagicMock()

    mock_usage = MagicMock()
    mock_usage.input_tokens = 100
    mock_usage.output_tokens = 50

    mock_content = MagicMock()
    mock_content.text = "This is a test answer from the LLM."

    mock_message = MagicMock()
    mock_message.content = [mock_content]
    mock_message.usage = mock_usage
    client.messages.create.return_value = mock_message

    return client


@pytest.fixture
def temp_project_dir(tmp_path):
    (tmp_path / "data" / "raw").mkdir(parents=True)
    (tmp_path / "data" / "parsed").mkdir(parents=True)
    (tmp_path / "data" / "chunks").mkdir(parents=True)
    (tmp_path / "data" / "artifacts").mkdir(parents=True)
    (tmp_path / "data" / "meals").mkdir(parents=True)
    (tmp_path / "data" / "exp_reports").mkdir(parents=True)
    (tmp_path / "data" / "vector_store").mkdir(parents=True)
    (tmp_path / "exp_configs").mkdir(parents=True)
    (tmp_path / "logs").mkdir(parents=True)

    yield tmp_path


# =============================================================================
# Streamlit AppTest UI fixtures
# =============================================================================

_UI_MOCK_CONFIG = {
    "parser": {"input_dir": "data/raw"},
    "retrieval": {
        "method": "vector",
        "top_k": 5,
        "reranker": {"enabled": False},
        "query_rewrite": {"enabled": False, "strategy": "hyde"},
    },
    "llm": {"provider": "anthropic", "model": "claude-sonnet-4-20250514"},
    "embedding": {"model_name": "BAAI/bge-large-zh-v1.5"},
    "vector_store": {"provider": "qdrant"},
}

_UI_MOCK_QUERY_RESULT = {
    "question": "什么是ROE？",
    "answer": "ROE（Return on Equity）是股东权益回报率，衡量公司盈利能力的重要指标。",
    "sources": ["annual_reports/2023/company_a/report.pdf"],
    "scores": [0.95],
    "contexts": ["ROE 是衡量公司盈利能力的重要指标..."],
    "chunk_ids": ["chunk_001"],
    "token_usage": {
        "input_tokens": 500,
        "output_tokens": 200,
        "total_tokens": 700,
    },
}

_UI_MOCK_MEAL = MealConfig(
    data_id="test_meal_001",
    name="测试Meal",
    created_at="2025-01-01T00:00:00",
    sampling_config={"mode": "count", "value": 5},
    collection_name="meal_test_meal_001",
    pdf_files=[
        MealFile(
            path="annual_reports/2023/company_a/report.pdf",
            sha256="abc123",
            size_bytes=1024000,
        ),
    ],
)


def _build_mock_pipeline():
    pipeline = MagicMock()
    pipeline.query.return_value = _UI_MOCK_QUERY_RESULT
    return pipeline


def _build_mock_pdf_server():
    server = MagicMock()
    server.base_url = "http://localhost:8502"
    server.port = 8502
    server.serve_dir = "data/raw"
    return server


@pytest.fixture
def ui_mock_config():
    with patch("src.utils.load_config", return_value=_UI_MOCK_CONFIG):
        yield _UI_MOCK_CONFIG


@pytest.fixture
def ui_mock_logger():
    with patch("src.utils.setup_logger"):
        yield


@pytest.fixture
def ui_mock_pipeline():
    pipeline = _build_mock_pipeline()
    with patch("src.app_pages.qa_demo.get_pipeline", return_value=pipeline):
        yield pipeline


@pytest.fixture
def ui_mock_meals():
    with patch(
        "src.app_pages.qa_demo.get_meals",
        return_value=[_UI_MOCK_MEAL],
    ):
        yield [_UI_MOCK_MEAL]


@pytest.fixture
def ui_mock_create_meal():
    new_meal = MealConfig(
        data_id="new_meal_001",
        name="新建Meal",
        created_at="2025-01-02T00:00:00",
        sampling_config={"mode": "count", "value": 5},
        collection_name="meal_new_meal_001",
        pdf_files=[],
    )
    with patch(
        "src.app_pages.qa_demo.create_new_meal",
        return_value=new_meal,
    ) as m:
        yield m


@pytest.fixture
def ui_mock_pdf_server():
    server = _build_mock_pdf_server()
    with patch(
        "src.app_pages.qa_demo.get_or_create_pdf_server",
        return_value=server,
    ):
        yield server


@pytest.fixture
def ui_mock_pdf_page_count():
    with patch(
        "src.app_pages.qa_demo._get_pdf_page_count",
        return_value=10,
    ):
        yield


@pytest.fixture
def app(
    ui_mock_config, ui_mock_logger, ui_mock_pipeline, ui_mock_meals, ui_mock_pdf_server
):
    at = AppTest.from_file("src/app.py")
    at.run(timeout=30)
    yield at


@pytest.fixture
def app_with_pdf(
    ui_mock_config,
    ui_mock_logger,
    ui_mock_pipeline,
    ui_mock_meals,
    ui_mock_pdf_server,
    ui_mock_pdf_page_count,
):
    at = AppTest.from_file("src/app.py")
    at.session_state["_pdf_preview_path"] = (
        "data/raw/annual_reports/2023/company_a/report.pdf"
    )
    at.session_state["_pdf_preview_name"] = "report.pdf"
    at.session_state["_pdf_preview_page"] = 1
    at.run(timeout=30)
    yield at
