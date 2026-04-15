import sys
from unittest.mock import MagicMock

import numpy as np

mock_flag_model = MagicMock()
mock_flag_model.model.config.hidden_size = 1024
mock_flag_model.encode.return_value = np.random.rand(3, 1024)

sys.modules["FlagEmbedding"] = MagicMock()
sys.modules["FlagEmbedding"].FlagModel = MagicMock(
    return_value=mock_flag_model)
