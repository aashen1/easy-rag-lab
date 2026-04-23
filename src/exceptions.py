class RAGPipelineError(Exception):
    """Base exception for all RAG pipeline errors."""

    pass


class ConfigurationError(RAGPipelineError):
    """Raised when configuration validation fails."""

    pass


class ParsingError(RAGPipelineError):
    """Raised when PDF/document parsing fails."""

    pass


class RetrievalError(RAGPipelineError):
    """Raised when retrieval execution fails."""

    pass


class IndexingError(RAGPipelineError):
    """Raised when index building or querying fails."""

    pass


class GenerationError(RAGPipelineError):
    """Raised when LLM generation or API call fails."""

    pass


class MealError(RAGPipelineError):
    """Raised when meal management operations fail."""

    pass


class TestSetError(RAGPipelineError):
    """Raised when test set management operations fail."""

    pass


class EvaluationError(RAGPipelineError):
    """Raised when evaluation computation fails."""

    pass
