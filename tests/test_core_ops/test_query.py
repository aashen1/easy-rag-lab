from __future__ import annotations

from unittest.mock import MagicMock


class TestQueryRag:
    def test_query_rag_delegates_to_pipeline(self):
        from src.core.ops.query import query_rag

        mock_pipeline = MagicMock()
        mock_pipeline.query.return_value = {
            "question": "What is ROE?",
            "answer": "ROE is Return on Equity.",
            "sources": ["a.pdf"],
        }

        result = query_rag("What is ROE?", mock_pipeline)

        assert result["question"] == "What is ROE?"
        assert result["answer"] == "ROE is Return on Equity."
        mock_pipeline.query.assert_called_once_with("What is ROE?")

    def test_query_rag_passes_question_verbatim(self):
        from src.core.ops.query import query_rag

        mock_pipeline = MagicMock()
        mock_pipeline.query.return_value = {"question": "test", "answer": "ans"}

        query_rag("test question", mock_pipeline)
        mock_pipeline.query.assert_called_once_with("test question")
