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

    __test__ = False
    pass


class EvaluationError(RAGPipelineError):
    """Raised when evaluation computation fails."""

    pass


class ReuseError(RAGPipelineError):
    """Raised when experiment report reuse operations fail."""

    pass


class FingerprintMismatchError(ReuseError):
    """Raised when experiment fingerprints do not match during copy-migrate."""

    def __init__(self, message: str, diff: dict[str, tuple[str, str]] | None = None):
        super().__init__(message)
        self.diff = diff


class ConflictDetectedError(ReuseError):
    """Raised when variant name conflicts are detected during reuse."""

    def __init__(self, message: str, conflicting_variants: list[str] | None = None):
        super().__init__(message)
        self.conflicting_variants = conflicting_variants or []
