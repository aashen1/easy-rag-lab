"""Pydantic models for config.yaml validation.

Defines nested Pydantic models that mirror the config.yaml structure,
providing type checking, range validation, and cross-field constraints.
All fields have defaults to maintain backward compatibility.
"""

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class LLMPresetConfig(BaseModel):
    """Configuration for a single LLM preset.

    Attributes:
        model_name: Environment variable name or literal model identifier
        temperature: Sampling temperature (0.0 = deterministic, 2.0 = creative)
        max_tokens: Maximum tokens in the response
        api_key: Environment variable name for the API key
        base_url: Environment variable name for the API base URL
    """

    model_config = {"extra": "allow"}

    model_name: str = Field(
        default="LLM_MODEL_ID", description="Model identifier or env var name"
    )
    temperature: float = Field(
        default=0.0, ge=0.0, le=2.0, description="Sampling temperature"
    )
    max_tokens: int = Field(default=1024, gt=0, description="Max response tokens")
    api_key: str = Field(default="LLM_API_KEY", description="API key env var name")
    base_url: str = Field(default="LLM_BASE_URL", description="Base URL env var name")


class ParserPymupdf4llmConfig(BaseModel):
    """Configuration for pymupdf4llm parser.

    Attributes:
        header: Whether to extract headers
        footer: Whether to extract footers
        page_separators: Whether to add page separators
        write_images: Whether to write images
        page_chunks: Whether to return page chunks
        force_text: Whether to force text extraction
        ignore_code: Whether to ignore code blocks
        use_ocr: Whether to use OCR
        ocr_language: OCR language pack identifier
        show_progress: Whether to show progress bar
        clean_degenerate_tables: Whether to clean degenerate tables
    """

    model_config = {"extra": "allow"}

    header: bool = Field(default=False)
    footer: bool = Field(default=False)
    page_separators: bool = Field(default=False)
    write_images: bool = Field(default=False)
    page_chunks: bool = Field(default=True)
    force_text: bool = Field(default=True)
    ignore_code: bool = Field(default=True)
    use_ocr: bool = Field(default=False)
    ocr_language: str = Field(default="chi_sim+eng")
    show_progress: bool = Field(default=True)
    clean_degenerate_tables: bool = Field(default=True)


class ParserFitzConfig(BaseModel):
    """Configuration for fitz (PyMuPDF) parser.

    Attributes:
        header_filter: Whether to filter headers
        footer_filter: Whether to filter footers
        header_zone_ratio: Top portion of page considered header zone
        footer_zone_ratio: Bottom portion of page considered footer zone
        column_detection: Whether to detect columns
        heading_detection: Whether to detect headings
        noise_patterns: List of regex patterns for noise removal
    """

    model_config = {"extra": "allow"}

    header_filter: bool = Field(default=True)
    footer_filter: bool = Field(default=True)
    header_zone_ratio: float = Field(default=0.10, gt=0, lt=1)
    footer_zone_ratio: float = Field(default=0.10, gt=0, lt=1)
    column_detection: bool = Field(default=True)
    heading_detection: bool = Field(default=True)
    noise_patterns: list[str] = Field(default_factory=list)


class PdfplumberTableSettingsConfig(BaseModel):
    """Table extraction settings for pdfplumber.

    Attributes:
        snap_tolerance: Snap tolerance for table edges
        join_tolerance: Join tolerance for table edges
        edge_min_length: Minimum edge length to consider
        intersection_x_tolerance: X-axis intersection tolerance
        intersection_y_tolerance: Y-axis intersection tolerance
    """

    model_config = {"extra": "allow"}

    snap_tolerance: int = Field(default=5, gt=0)
    join_tolerance: int = Field(default=5, gt=0)
    edge_min_length: int = Field(default=10, gt=0)
    intersection_x_tolerance: int = Field(default=5, gt=0)
    intersection_y_tolerance: int = Field(default=5, gt=0)


class PdfplumberQualityFilterConfig(BaseModel):
    """Quality filter settings for pdfplumber tables.

    Attributes:
        min_columns: Minimum number of columns for a valid table
        max_empty_ratio: Maximum ratio of empty cells allowed
        min_data_rows: Minimum number of data rows required
    """

    model_config = {"extra": "allow"}

    min_columns: int = Field(default=3, gt=0)
    max_empty_ratio: float = Field(default=0.5, ge=0, le=1)
    min_data_rows: int = Field(default=2, gt=0)


class ParserPdfplumberConfig(BaseModel):
    """Configuration for pdfplumber table enhancer.

    Attributes:
        strategy: Table extraction strategy
        vertical_strategy: Vertical strategy for table detection
        horizontal_strategy: Horizontal strategy for table detection
        table_settings: Fine-grained table extraction settings
        quality_filter: Quality filter configuration
        replace_policy: How to replace existing content with table data
    """

    model_config = {"extra": "allow"}

    strategy: str = Field(default="text")
    vertical_strategy: str = Field(default="text")
    horizontal_strategy: str = Field(default="text")
    table_settings: PdfplumberTableSettingsConfig = Field(
        default_factory=PdfplumberTableSettingsConfig
    )
    quality_filter: PdfplumberQualityFilterConfig = Field(
        default_factory=PdfplumberQualityFilterConfig
    )
    replace_policy: str = Field(default="better_wins")


class ParserConfig(BaseModel):
    """PDF parser configuration.

    Attributes:
        input_dir: Directory containing raw PDF files
        primary: Primary parser engine name
        table_enhancer: Table enhancement engine name
        pymupdf4llm: pymupdf4llm-specific settings
        fitz: fitz-specific settings
        pdfplumber: pdfplumber-specific settings
    """

    model_config = {"extra": "allow"}

    input_dir: str = Field(default="data/raw")
    primary: Literal["pymupdf4llm", "fitz"] = Field(default="pymupdf4llm")
    table_enhancer: Literal["pdfplumber", "null"] = Field(default="pdfplumber")
    pymupdf4llm: ParserPymupdf4llmConfig = Field(
        default_factory=ParserPymupdf4llmConfig
    )
    fitz: ParserFitzConfig = Field(default_factory=ParserFitzConfig)
    pdfplumber: ParserPdfplumberConfig = Field(default_factory=ParserPdfplumberConfig)


class ChunkerSemanticConfig(BaseModel):
    """Configuration for semantic chunking strategy.

    Attributes:
        similarity_threshold: Cosine similarity threshold for breakpoints
        breakpoint_percentile: Percentile-based threshold (null = disabled)
        min_chunk_size: Minimum tokens per chunk
    """

    model_config = {"extra": "allow"}

    similarity_threshold: float = Field(default=0.5, ge=0, le=1)
    breakpoint_percentile: float | None = Field(default=None)
    min_chunk_size: int = Field(default=100, gt=0)


class ChunkerConfig(BaseModel):
    """Text chunking configuration.

    Attributes:
        strategy: Chunking strategy name
        encoding: Tokenizer encoding name
        chunk_size: Maximum tokens per chunk
        chunk_overlap: Overlap tokens between chunks (fixed strategy)
        cross_page_overlap: Tokens from previous page prepended to current page
        semantic: Semantic chunking configuration
    """

    model_config = {"extra": "allow"}

    strategy: Literal["fixed", "semantic"] = Field(default="fixed")
    encoding: Literal["bge", "cl100k_base"] = Field(default="bge")
    chunk_size: int = Field(default=512, gt=0, description="Max tokens per chunk")
    chunk_overlap: int = Field(
        default=0, ge=0, description="Overlap tokens between chunks"
    )
    cross_page_overlap: int = Field(
        default=0, ge=0, description="Tokens prepended from previous page"
    )
    semantic: ChunkerSemanticConfig = Field(default_factory=ChunkerSemanticConfig)

    @model_validator(mode="after")
    def validate_overlap(self) -> "ChunkerConfig":
        """Ensure chunk_overlap is less than chunk_size."""
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError(
                f"chunk_overlap ({self.chunk_overlap}) must be less than chunk_size ({self.chunk_size})"
            )
        return self


class EmbeddingConfig(BaseModel):
    """Embedding model configuration.

    Attributes:
        model_name: Name of the embedding model
        device: Device for inference (cuda/cpu)
        batch_size: Batch size for embedding
        query_instruction: Instruction prefix for queries (null = auto-detect)
    """

    model_config = {"extra": "allow"}

    model_name: str = Field(default="BAAI/bge-large-zh-v1.5")
    device: str = Field(default="cuda")
    batch_size: int = Field(default=32, gt=0)
    query_instruction: str | None = Field(default=None)


class VectorStoreConfig(BaseModel):
    """Vector store configuration.

    Attributes:
        type: Vector store backend type
        collection_name: Name of the vector collection
        persist_dir: Directory for persistent storage
        distance: Distance metric for similarity search
    """

    model_config = {"extra": "allow"}

    type: Literal["qdrant"] = Field(default="qdrant")
    collection_name: str = Field(default="financial_reports")
    persist_dir: str = Field(default="data/vector_store")
    distance: Literal["Cosine", "Euclid", "Dot"] = Field(default="Cosine")


class BM25Config(BaseModel):
    """BM25 retrieval parameters.

    Attributes:
        k1: Term frequency saturation parameter
        b: Length normalization parameter
    """

    model_config = {"extra": "allow"}

    k1: float = Field(default=1.5, gt=0)
    b: float = Field(default=0.75, ge=0, le=1)


class HybridConfig(BaseModel):
    """Hybrid retrieval fusion parameters.

    Attributes:
        fusion: Fusion strategy name
        rrf_k: RRF constant (higher dampens rank impact)
        vector_weight: Weight for vector scores in weighted fusion
        bm25_weight: Weight for BM25 scores in weighted fusion
    """

    model_config = {"extra": "allow"}

    fusion: Literal["rrf", "weighted"] = Field(default="rrf")
    rrf_k: int = Field(default=60, gt=0)
    vector_weight: float = Field(default=0.7, ge=0, le=1)
    bm25_weight: float = Field(default=0.3, ge=0, le=1)


class RerankerConfig(BaseModel):
    """Cross-encoder reranking configuration.

    Attributes:
        enabled: Whether reranking is enabled
        model_name: Name of the cross-encoder model
        device: Device for reranker inference
        top_n: Number of results to keep after reranking
    """

    model_config = {"extra": "allow"}

    enabled: bool = Field(default=False)
    model_name: str = Field(default="BAAI/bge-reranker-large")
    device: str = Field(default="cuda")
    top_n: int = Field(default=3, gt=0)


class QueryRewriteConfig(BaseModel):
    """Query rewriting configuration.

    Attributes:
        enabled: Whether query rewriting is enabled
        strategy: Rewriting strategy name
        num_queries: Number of sub-queries for multi_query strategy
    """

    model_config = {"extra": "allow"}

    enabled: bool = Field(default=False)
    strategy: Literal["hyde", "multi_query"] = Field(default="hyde")
    num_queries: int = Field(default=3, gt=0)


class RetrievalConfig(BaseModel):
    """Retrieval configuration.

    Attributes:
        method: Retrieval method name
        top_k: Number of results to retrieve
        score_threshold: Minimum similarity score to include
        bm25: BM25 parameters
        hybrid: Hybrid retrieval parameters
        reranker: Reranking configuration
        query_rewrite: Query rewriting configuration
    """

    model_config = {"extra": "allow"}

    method: Literal["vector", "bm25", "hybrid"] = Field(default="vector")
    top_k: int = Field(default=5, gt=0)
    score_threshold: float = Field(default=0.3, ge=0, le=1)
    bm25: BM25Config = Field(default_factory=BM25Config)
    hybrid: HybridConfig = Field(default_factory=HybridConfig)
    reranker: RerankerConfig = Field(default_factory=RerankerConfig)
    query_rewrite: QueryRewriteConfig = Field(default_factory=QueryRewriteConfig)


class GenerationConfig(BaseModel):
    """Answer generation configuration.

    Attributes:
        system_prompt: Custom system prompt (null = use hardcoded default)
        max_context_tokens: Maximum total input tokens
    """

    model_config = {"extra": "allow"}

    system_prompt: str | None = Field(default=None)
    max_context_tokens: int = Field(default=8000, gt=0)


class ProfilingConfig(BaseModel):
    """Performance profiling configuration.

    Attributes:
        enabled: Whether profiling is enabled
        monitor_interval: Resource monitoring sampling interval in seconds
        generate_charts: Whether to generate visualization charts
    """

    model_config = {"extra": "allow"}

    enabled: bool = Field(default=True)
    monitor_interval: float = Field(default=0.5, gt=0)
    generate_charts: bool = Field(default=True)


class ReuseConfig(BaseModel):
    """Experiment report reuse configuration.

    Attributes:
        mode: Reuse mode name
        backup_before_append: Whether to create snapshot backup before appending (in_place mode)
    """

    model_config = {"extra": "allow"}

    mode: Literal["none", "in_place", "copy_migrate"] = Field(default="none")
    backup_before_append: bool = Field(default=True)


class ExperimentsConfig(BaseModel):
    """Experiment management configuration.

    Attributes:
        dir: Directory for experiment reports
        configs_dir: Directory for experiment configuration files
        profiling: Profiling configuration
        reuse: Reuse configuration
    """

    model_config = {"extra": "allow"}

    dir: str = Field(default="data/exp_reports")
    configs_dir: str = Field(default="exp_configs")
    profiling: ProfilingConfig = Field(default_factory=ProfilingConfig)
    reuse: ReuseConfig = Field(default_factory=ReuseConfig)


class MealsConfig(BaseModel):
    """Meal data management configuration.

    Attributes:
        dir: Directory for meal data
        collection_prefix: Prefix for collection names
        default_name: Default meal name
    """

    model_config = {"extra": "allow"}

    dir: str = Field(default="data/meals")
    collection_prefix: str = Field(default="m_")
    default_name: str = Field(default="all")


class ArtifactsConfig(BaseModel):
    """Artifacts storage configuration.

    Attributes:
        dir: Directory for artifact storage
    """

    model_config = {"extra": "allow"}

    dir: str = Field(default="data/artifacts")


class LLMEvaluatorSubConfig(BaseModel):
    """Sub-configuration for a single LLM evaluator metric.

    Attributes:
        temperature: Sampling temperature for this metric
        max_tokens: Maximum tokens for this metric
    """

    model_config = {"extra": "allow"}

    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    max_tokens: int = Field(default=512, gt=0)


class LLMEvaluatorReportGenerationConfig(BaseModel):
    """Configuration for LLM evaluator report generation.

    Attributes:
        model_name: Model identifier or env var name
        temperature: Sampling temperature
        max_tokens: Maximum tokens
    """

    model_config = {"extra": "allow"}

    model_name: str = Field(default="LLM_MODEL_ID")
    temperature: float = Field(default=0.3, ge=0.0, le=2.0)
    max_tokens: int = Field(default=4096, gt=0)


class LLMEvaluatorConfig(BaseModel):
    """LLM evaluator configuration for metrics computation.

    Attributes:
        model_name: Model identifier or env var name
        base_url: Base URL env var name
        extract_statements: Config for extract_statements metric
        verify_statements: Config for verify_statements metric
        faithfulness: Config for faithfulness metric
        answer_relevancy: Config for answer_relevancy metric
        context_precision: Config for context_precision metric
        context_recall: Config for context_recall metric
        context_relevance: Config for context_relevance metric
        infer_check: Config for infer_check metric
        report_generation: Config for report generation
    """

    model_config = {"extra": "allow"}

    model_name: str = Field(default="LLM_MODEL_ID")
    base_url: str = Field(default="LLM_BASE_URL")
    extract_statements: LLMEvaluatorSubConfig = Field(
        default_factory=lambda: LLMEvaluatorSubConfig(temperature=0.0, max_tokens=1024)
    )
    verify_statements: LLMEvaluatorSubConfig = Field(
        default_factory=lambda: LLMEvaluatorSubConfig(temperature=0.0, max_tokens=1024)
    )
    faithfulness: LLMEvaluatorSubConfig = Field(
        default_factory=lambda: LLMEvaluatorSubConfig(temperature=0.0, max_tokens=512)
    )
    answer_relevancy: LLMEvaluatorSubConfig = Field(
        default_factory=lambda: LLMEvaluatorSubConfig(temperature=0.0, max_tokens=512)
    )
    context_precision: LLMEvaluatorSubConfig = Field(
        default_factory=lambda: LLMEvaluatorSubConfig(temperature=0.0, max_tokens=256)
    )
    context_recall: LLMEvaluatorSubConfig = Field(
        default_factory=lambda: LLMEvaluatorSubConfig(temperature=0.0, max_tokens=256)
    )
    context_relevance: LLMEvaluatorSubConfig = Field(
        default_factory=lambda: LLMEvaluatorSubConfig(temperature=0.0, max_tokens=256)
    )
    infer_check: LLMEvaluatorSubConfig = Field(
        default_factory=lambda: LLMEvaluatorSubConfig(temperature=0.0, max_tokens=64)
    )
    report_generation: LLMEvaluatorReportGenerationConfig = Field(
        default_factory=LLMEvaluatorReportGenerationConfig
    )


class EvaluationRagasRunConfig(BaseModel):
    """RAGAS run configuration.

    Attributes:
        max_workers: Maximum number of parallel workers
        timeout: Timeout in seconds for each evaluation
        max_retries: Maximum number of retries on failure
    """

    model_config = {"extra": "allow"}

    max_workers: int = Field(default=10, gt=0)
    timeout: int = Field(default=180, gt=0)
    max_retries: int = Field(default=3, ge=0)


class EvaluationRagasConfig(BaseModel):
    """RAGAS evaluation backend configuration.

    Attributes:
        enabled: Whether RAGAS backend is enabled
        llm_backend: LLM backend for RAGAS
        embeddings_backend: Embeddings backend for RAGAS
        max_tokens: Maximum tokens for RAGAS evaluation
        run_config: RAGAS run configuration
    """

    model_config = {"extra": "allow"}

    enabled: bool = Field(default=False)
    llm_backend: str = Field(default="anthropic")
    embeddings_backend: str = Field(default="local")
    max_tokens: int = Field(default=8192, gt=0)
    run_config: EvaluationRagasRunConfig = Field(
        default_factory=EvaluationRagasRunConfig
    )


class EvaluationConfig(BaseModel):
    """Evaluation system configuration.

    Attributes:
        backends: List of evaluation backend names
        normalize_source_include_parent: Whether to include parent in normalized source
        resolution_strategy: Strategy for resolving metrics from multiple backends
        backend_priority: Priority order for backends
        metrics_preset: Preset name for metric selection
        ragas: RAGAS-specific configuration
        concurrent_queries: Number of concurrent query evaluations
        builtin_concurrent_workers: Number of concurrent workers for builtin backend
    """

    model_config = {"extra": "allow"}

    backends: list[Literal["builtin", "ragas"]] = Field(
        default_factory=lambda: ["builtin"]
    )
    normalize_source_include_parent: bool = Field(default=True)
    resolution_strategy: Literal["priority_fallback", "comparison"] = Field(
        default="priority_fallback"
    )
    backend_priority: list[str] = Field(default_factory=lambda: ["builtin", "ragas"])
    metrics_preset: Literal["core", "extended", "full", "custom"] = Field(
        default="core"
    )
    ragas: EvaluationRagasConfig = Field(default_factory=EvaluationRagasConfig)
    concurrent_queries: int = Field(default=10, gt=0)
    builtin_concurrent_workers: int = Field(default=10, gt=0)


class LLMRetryConfig(BaseModel):
    """LLM API retry configuration.

    Attributes:
        max_retries: Maximum number of retries for 429/overload errors
        base_delay: Initial retry delay in seconds
        max_delay: Maximum retry delay in seconds
    """

    model_config = {"extra": "allow"}

    max_retries: int = Field(default=5, ge=0)
    base_delay: float = Field(default=1.0, gt=0)
    max_delay: float = Field(default=60.0, gt=0)

    @model_validator(mode="after")
    def validate_delays(self) -> "LLMRetryConfig":
        """Ensure base_delay is not greater than max_delay."""
        if self.base_delay > self.max_delay:
            raise ValueError(
                f"base_delay ({self.base_delay}) must not exceed max_delay ({self.max_delay})"
            )
        return self


class TestGenerationValidationConfig(BaseModel):
    """Validation configuration for test generation.

    Attributes:
        check_proper_nouns: Whether to validate proper nouns in questions
    """

    model_config = {"extra": "allow"}

    check_proper_nouns: bool = Field(default=False)


class TestGenerationHybridConfig(BaseModel):
    """Configuration for hybrid test generation strategy.

    Attributes:
        enabled: Whether hybrid test generation is enabled
        segment_size: Size of text segments for question generation
        compact_segment_max_chars: Maximum characters for compact segments
        segment_sampling_strategy: Strategy for sampling segments
        quote_fuzzy_match_threshold: Threshold for fuzzy matching quotes
        multi_hop_candidate_count: Number of candidates for multi-hop questions
    """

    model_config = {"extra": "allow"}

    enabled: bool = Field(default=True)
    segment_size: int = Field(default=8000, gt=0)
    compact_segment_max_chars: int = Field(default=6000, gt=0)
    segment_sampling_strategy: str = Field(default="random")
    quote_fuzzy_match_threshold: float = Field(default=0.85, ge=0, le=1)
    multi_hop_candidate_count: int = Field(default=3, gt=0)


class TestGenerationDocumentLevelQualityControlConfig(BaseModel):
    """Quality control for document-level test generation.

    Attributes:
        enable_authenticity_check: Whether to check question authenticity
        enable_llm_evaluation: Whether to use LLM for quality evaluation
        min_authenticity_score: Minimum authenticity score threshold
    """

    model_config = {"extra": "allow"}

    enable_authenticity_check: bool = Field(default=True)
    enable_llm_evaluation: bool = Field(default=False)
    min_authenticity_score: int = Field(default=12, gt=0)


class TestGenerationDocumentLevelConfig(BaseModel):
    """Configuration for document-level test generation.

    Attributes:
        enabled: Whether document-level test generation is enabled
        default_num_questions: Default number of questions per document
        type_distribution: Distribution of question types
        quality_control: Quality control configuration
        max_retries: Maximum retries for generation
    """

    model_config = {"extra": "allow"}

    enabled: bool = Field(default=True)
    default_num_questions: int = Field(default=20, gt=0)
    type_distribution: dict[str, float] = Field(
        default_factory=lambda: {
            "single_fact": 0.30,
            "multi_fact": 0.25,
            "reasoning": 0.15,
            "comparative": 0.15,
            "missing": 0.10,
            "irrelevant": 0.05,
        }
    )
    quality_control: TestGenerationDocumentLevelQualityControlConfig = Field(
        default_factory=TestGenerationDocumentLevelQualityControlConfig
    )
    max_retries: int = Field(default=3, ge=0)


class TestGenerationConfig(BaseModel):
    """Test set generation configuration.

    Attributes:
        default_strategy: Default generation strategy
        default_num_questions: Default number of questions
        max_retries: Maximum retries for generation
        model_name: Model identifier or env var name
        temperature: Sampling temperature
        max_tokens: Maximum tokens for generation
        supplement_max_tokens: Maximum tokens for supplement generation
        initial_max_tokens: Maximum tokens for initial generation
        concurrent_generation: Concurrency level for generation
        validation: Validation configuration
        hybrid: Hybrid test generation configuration
        document_level: Document-level test generation configuration
    """

    model_config = {"extra": "allow"}

    default_strategy: Literal["hybrid", "document_level"] = Field(default="hybrid")
    default_num_questions: int = Field(default=20, gt=0)
    max_retries: int = Field(default=3, ge=0)
    model_name: str = Field(default="LLM_MODEL_ID")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=1024, gt=0)
    supplement_max_tokens: int = Field(default=1024, gt=0)
    initial_max_tokens: int = Field(default=512, gt=0)
    concurrent_generation: int = Field(default=5, gt=0)
    validation: TestGenerationValidationConfig = Field(
        default_factory=TestGenerationValidationConfig
    )
    hybrid: TestGenerationHybridConfig = Field(
        default_factory=TestGenerationHybridConfig
    )
    document_level: TestGenerationDocumentLevelConfig = Field(
        default_factory=TestGenerationDocumentLevelConfig
    )


class TokenCostModelConfig(BaseModel):
    """Token cost configuration for a single model.

    Attributes:
        input_price_per_1k: Input price per 1K tokens
        output_price_per_1k: Output price per 1K tokens
        conversion_factor: Cost conversion factor relative to base model
    """

    model_config = {"extra": "allow"}

    input_price_per_1k: float = Field(default=0.001, ge=0)
    output_price_per_1k: float = Field(default=0.002, ge=0)
    conversion_factor: float = Field(default=1.0, gt=0)


class TokenCostConfig(BaseModel):
    """Token cost configuration for all models.

    Attributes:
        models: Mapping of model name to cost configuration
    """

    model_config = {"extra": "allow"}

    models: dict[str, TokenCostModelConfig] = Field(default_factory=dict)


class QueryHistoryConfig(BaseModel):
    """Query history configuration.

    Attributes:
        max_entries: Maximum number of history entries to keep
        dir: Directory for query history storage
    """

    model_config = {"extra": "allow"}

    max_entries: int = Field(default=10, gt=0)
    dir: str = Field(default="data/query_history")


class LoggingConfig(BaseModel):
    """Logging configuration.

    Attributes:
        level: Log level name
        format: Log format string
        log_dir: Directory for log files
        rotation: Log rotation size
        retention: Log retention period
    """

    model_config = {"extra": "allow"}

    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO"
    )
    format: str = Field(
        default="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
    )
    log_dir: str = Field(default="logs")
    rotation: str = Field(default="10 MB")
    retention: str = Field(default="7 days")


class AgentCheckpointConfig(BaseModel):
    """Agent checkpoint configuration.

    Attributes:
        db_path: Path to the checkpoint database file
    """

    model_config = {"extra": "allow"}

    db_path: str = Field(default="data/agent_checkpoints.db")


class AgentDefaultsConfig(BaseModel):
    """Default values for agent operations.

    Attributes:
        parser_name: Default parser engine name
        enhancer_name: Default table enhancer name
        chunk_size: Default chunk size
        chunk_overlap: Default chunk overlap
        collection_name: Default vector collection name
        thread_id: Default thread ID for agent sessions
        mode: Default agent mode
        delete_count_threshold: Threshold for light mode deletion alert
        full_mode_delete_threshold: Threshold for full mode deletion alert
    """

    model_config = {"extra": "allow"}

    parser_name: str = Field(default="pymupdf4llm")
    enhancer_name: str = Field(default="pdfplumber")
    chunk_size: int = Field(default=512, gt=0)
    chunk_overlap: int = Field(default=0, ge=0)
    collection_name: str = Field(default="financial_reports")
    thread_id: str = Field(default="maintenance-session")
    mode: Literal["light", "full"] = Field(default="light")
    delete_count_threshold: int = Field(default=3, gt=0)
    full_mode_delete_threshold: int = Field(default=10, gt=0)
    experience_persist_path: str = Field(default="data/agent_experience.json")


class AgentConfig(BaseModel):
    """Agent configuration.

    Attributes:
        checkpoint: Checkpoint configuration
        trashbin_dir: Directory for trashbin
        maintenance_reports_dir: Directory for maintenance reports
        subprocess_timeout: Timeout for subprocess operations
        defaults: Default values for agent operations
    """

    model_config = {"extra": "allow"}

    checkpoint: AgentCheckpointConfig = Field(default_factory=AgentCheckpointConfig)
    trashbin_dir: str = Field(default=".trashbin")
    maintenance_reports_dir: str = Field(default="data/maintenance_reports")
    subprocess_timeout: int = Field(default=30, gt=0)
    defaults: AgentDefaultsConfig = Field(default_factory=AgentDefaultsConfig)


class AppConfig(BaseModel):
    """Root configuration model for config.yaml.

    Validates the entire configuration structure including type checking,
    range validation, and cross-field constraints.

    Attributes:
        active_mode: Currently active LLM preset name
        data_dir: Root directory for data files
        llm_presets: Mapping of preset names to LLM configurations
        parser: PDF parser configuration
        chunker: Text chunking configuration
        embedding: Embedding model configuration
        vector_store: Vector store configuration
        retrieval: Retrieval configuration
        generation: Answer generation configuration
        experiments: Experiment management configuration
        meals: Meal data management configuration
        artifacts: Artifacts storage configuration
        llm_evaluator: LLM evaluator configuration
        evaluation: Evaluation system configuration
        llm_retry: LLM API retry configuration
        test_generation: Test set generation configuration
        token_cost: Token cost configuration
        query_history: Query history configuration
        logging: Logging configuration
        agent: Agent configuration
    """

    model_config = {"extra": "allow"}

    active_mode: str = Field(default="default", description="Active LLM preset name")
    data_dir: str = Field(default="data", description="Root data directory")
    llm_presets: dict[str, LLMPresetConfig] = Field(
        default_factory=lambda: {"default": LLMPresetConfig()},
        description="LLM preset configurations",
    )
    parser: ParserConfig = Field(default_factory=ParserConfig)
    chunker: ChunkerConfig = Field(default_factory=ChunkerConfig)
    embedding: EmbeddingConfig = Field(default_factory=EmbeddingConfig)
    vector_store: VectorStoreConfig = Field(default_factory=VectorStoreConfig)
    retrieval: RetrievalConfig = Field(default_factory=RetrievalConfig)
    generation: GenerationConfig = Field(default_factory=GenerationConfig)
    experiments: ExperimentsConfig = Field(default_factory=ExperimentsConfig)
    meals: MealsConfig = Field(default_factory=MealsConfig)
    artifacts: ArtifactsConfig = Field(default_factory=ArtifactsConfig)
    llm_evaluator: LLMEvaluatorConfig = Field(default_factory=LLMEvaluatorConfig)
    evaluation: EvaluationConfig = Field(default_factory=EvaluationConfig)
    llm_retry: LLMRetryConfig = Field(default_factory=LLMRetryConfig)
    test_generation: TestGenerationConfig = Field(default_factory=TestGenerationConfig)
    token_cost: TokenCostConfig = Field(default_factory=TokenCostConfig)
    query_history: QueryHistoryConfig = Field(default_factory=QueryHistoryConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    agent: AgentConfig = Field(default_factory=AgentConfig)

    @model_validator(mode="after")
    def validate_active_mode(self) -> "AppConfig":
        """Ensure active_mode references an existing LLM preset."""
        if self.active_mode not in self.llm_presets:
            raise ValueError(
                f"active_mode '{self.active_mode}' not found in llm_presets. "
                f"Available presets: {sorted(self.llm_presets.keys())}"
            )
        return self
