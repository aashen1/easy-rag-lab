import sys
from unittest.mock import MagicMock

import numpy as np
import torch

mock_model = MagicMock()
mock_model.config.hidden_size = 1024
mock_model.to.return_value = mock_model
mock_model.half.return_value = mock_model

mock_outputs = MagicMock()
mock_outputs.last_hidden_state = torch.randn(3, 10, 1024)
mock_model.return_value = mock_outputs

mock_tokenizer = MagicMock()
mock_tokenizer.return_value = {
    "input_ids": torch.randint(0, 1000, (3, 10)),
    "attention_mask": torch.ones(3, 10),
}

sys.modules["transformers"] = MagicMock()
sys.modules["transformers"].AutoModel = MagicMock()
sys.modules["transformers"].AutoModel.from_pretrained = MagicMock(return_value=mock_model)
sys.modules["transformers"].AutoTokenizer = MagicMock()
sys.modules["transformers"].AutoTokenizer.from_pretrained = MagicMock(
    return_value=mock_tokenizer
)
