import contextlib
import shutil
import warnings
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

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
