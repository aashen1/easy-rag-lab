"""
RAGAS evaluator that integrates the RAGAS evaluation framework.

This evaluator provides access to RAGAS metrics including:
- Faithfulness
- Answer Relevancy
- Context Precision
- Context Recall
- Answer Correctness
- Semantic Similarity

Uses LangchainLLMWrapper with ChatAnthropic for LongCat API compatibility,
which preserves the Authorization: Bearer header required by the proxy.
"""

from typing import Any

from loguru import logger

from eval.evaluators.base import BaseEvaluator, EvaluationResult, EvaluationSample
from eval.evaluators.error_handler import log_evaluation_error
from src.exceptions import EvaluationError

REFERENCE_REQUIRED_METRICS = {
    "context_precision",
    "context_recall",
    "answer_correctness",
    "semantic_similarity",
}


class RagasEvaluator(BaseEvaluator):
    """
    Evaluator that uses the RAGAS framework for evaluation.

    This evaluator integrates RAGAS metrics with the project's
    evaluation system, using LangchainLLMWrapper with ChatAnthropic
    for LongCat API compatibility.

    Args:
        config: Configuration dictionary containing:
            - llm_config: LLM configuration (api_key, base_url, model_name)
            - embedding_config: Embedding configuration (optional)
            - ragas_config: RAGAS-specific configuration

    Returns:
        RagasEvaluator instance.
    """

    def __init__(self, config: dict[str, Any] | None = None):
        """
        Initialize the RAGAS evaluator.

        Args:
            config: Optional configuration dictionary.
        """
        super().__init__(config)
        self._llm = None
        self._embeddings = None
        self._retrieval_metrics = []
        self._generation_metrics = [
            "faithfulness",
            "answer_relevancy",
            "context_precision",
            "context_recall",
            "answer_correctness",
            "semantic_similarity",
        ]
        self._ragas_config: dict[str, Any] = (
            self.config.get("ragas", {}) if self.config else {}
        )
        self._run_config: dict[str, Any] = self._ragas_config.get("run_config", {})
        self._embedding_config: dict[str, Any] = self._ragas_config.get("embedding", {})

    def _create_llm(self, llm_config: dict[str, str]) -> Any:
        """
        Create RAGAS-compatible LLM using LangchainLLMWrapper.

        Uses ChatAnthropic with api_key='dummy' and the real key passed
        via the Authorization: Bearer header, matching the pattern used
        by src.llm_client.create_anthropic_client. This is required because
        the LongCat API proxy expects the key in the Authorization header
        rather than the x-api-key header that the Anthropic SDK uses.

        The LangchainLLMWrapper preserves these custom headers through
        to the actual HTTP calls, unlike llm_factory + instructor which
        strips them during client patching.

        Args:
            llm_config: Dictionary containing api_key, base_url, model_name.

        Returns:
            RAGAS-compatible LangchainLLMWrapper instance.
        """
        try:
            from src.utils import create_llm_client

            max_tokens = self._ragas_config.get("max_tokens", 4096)

            llm_config_with_tokens = {
                **llm_config,
                "max_tokens": max_tokens,
            }

            return create_llm_client(
                llm_config=llm_config_with_tokens, mode="langchain"
            )
        except ImportError as e:
            error_msg = f"Failed to create LLM client: {str(e)}"
            logger.error(error_msg)
            raise EvaluationError(
                f"{error_msg}. Please install with: pixi add langchain-anthropic ragas"
            ) from e

    def _create_embeddings(self, config: dict[str, Any]) -> Any:
        """
        Create RAGAS-compatible embeddings using native RAGAS HuggingFaceEmbeddings
        with legacy interface wrapper for compatibility.

        Uses ragas.embeddings.HuggingFaceEmbeddings (modern interface, embed_text)
        wrapped to also provide legacy interface methods (embed_query, embed_documents)
        for full compatibility with all RAGAS metrics in concurrent execution.

        Args:
            config: Configuration dictionary containing embedding settings.

        Returns:
            RAGAS-compatible HuggingFaceEmbeddings instance with both modern and legacy interfaces.
        """
        try:
            from ragas.embeddings import (
                HuggingFaceEmbeddings as RagasHuggingFaceEmbeddings,
            )

            fallback_config = config.get("embedding", {})
            embedding_config = self._embedding_config or fallback_config
            model_name = self._ragas_config.get(
                "embedding_model"
            ) or embedding_config.get("model_name", "BAAI/bge-large-zh-v1.5")
            device = self._ragas_config.get("device") or embedding_config.get(
                "device", "cuda"
            )

            embeddings = RagasHuggingFaceEmbeddings(
                model=model_name,
                device=device,
            )

            class HybridHuggingFaceEmbeddings:
                """
                Wrapper providing both modern (embed_text) and legacy (embed_query, embed_documents)
                interfaces for RAGAS HuggingFaceEmbeddings.

                This ensures compatibility with all RAGAS metrics, including those that may
                still use legacy interface in concurrent execution contexts.
                """

                def __init__(self, inner):
                    self._inner = inner

                def embed_text(self, text: str, **kwargs):
                    return self._inner.embed_text(text, **kwargs)

                def embed_texts(self, texts: list, **kwargs):
                    return self._inner.embed_texts(texts, **kwargs)

                async def aembed_text(self, text: str, **kwargs):
                    return await self._inner.aembed_text(text, **kwargs)

                async def aembed_texts(self, texts: list, **kwargs):
                    return await self._inner.aembed_texts(texts, **kwargs)

                def embed_query(self, text: str, **kwargs):
                    return self._inner.embed_text(text, **kwargs)

                def embed_documents(self, texts: list, **kwargs):
                    return self._inner.embed_texts(texts, **kwargs)

                async def aembed_query(self, text: str, **kwargs):
                    return await self._inner.aembed_text(text, **kwargs)

                async def aembed_documents(self, texts: list, **kwargs):
                    return await self._inner.aembed_texts(texts, **kwargs)

                def __getattr__(self, name):
                    return getattr(self._inner, name)

            return HybridHuggingFaceEmbeddings(embeddings)

        except ImportError as e:
            error_msg = f"Failed to import RAGAS embeddings: {str(e)}"
            logger.error(error_msg)
            raise EvaluationError(f"{error_msg}. Please install ragas properly.") from e

    def _build_run_config(self) -> Any | None:
        """
        Build a RAGAS RunConfig from self._run_config.

        Returns:
            RunConfig instance if ragas provides it, otherwise None.
        """
        try:
            from ragas import RunConfig

            return RunConfig(
                max_workers=self._run_config.get("max_workers", 5),
                timeout=self._run_config.get("timeout", 60),
                max_retries=self._run_config.get("max_retries", 3),
            )
        except ImportError:
            logger.debug("RunConfig not available in this ragas version, skipping")
            return None

    def _build_ragas_dataset(self, samples: list[EvaluationSample]) -> Any:
        """
        Build RAGAS EvaluationDataset from EvaluationSample objects.

        Args:
            samples: List of EvaluationSample objects.

        Returns:
            RAGAS EvaluationDataset instance.
        """
        try:
            from ragas import EvaluationDataset, SingleTurnSample

            ragas_samples = []
            for sample in samples:
                reference = sample.expected_answer
                ragas_sample = SingleTurnSample(
                    user_input=sample.question,
                    response=sample.answer,
                    retrieved_contexts=sample.contexts,
                    reference=reference if reference else None,
                )
                ragas_samples.append(ragas_sample)

            return EvaluationDataset(samples=ragas_samples)

        except ImportError as e:
            error_msg = f"Failed to import RAGAS dataset classes: {str(e)}"
            logger.error(error_msg)
            raise EvaluationError(error_msg) from e

    def _create_metrics(
        self,
        metric_names: list[str],
        llm: Any,
        embeddings: Any | None = None,
    ) -> list[Any]:
        """
        Create RAGAS metric instances based on configuration.

        Args:
            metric_names: List of metric names to create.
            llm: LLM instance for LLM-based metrics.
            embeddings: Optional embeddings instance.

        Returns:
            List of RAGAS metric instances.
        """
        try:
            metric_map = {}
            try:
                from ragas.metrics._metrics import (
                    AnswerCorrectness,
                    AnswerRelevancy,
                    ContextPrecision,
                    ContextRecall,
                    Faithfulness,
                    SemanticSimilarity,
                )

                metric_map = {
                    "faithfulness": Faithfulness,
                    "answer_relevancy": AnswerRelevancy,
                    "context_precision": ContextPrecision,
                    "context_recall": ContextRecall,
                    "answer_correctness": AnswerCorrectness,
                    "semantic_similarity": SemanticSimilarity,
                }
            except ImportError:
                from ragas.metrics import (
                    _AnswerCorrectness as AnswerCorrectness,
                )
                from ragas.metrics import (
                    _AnswerRelevancy as AnswerRelevancy,
                )
                from ragas.metrics import (
                    _ContextPrecision as ContextPrecision,
                )
                from ragas.metrics import (
                    _ContextRecall as ContextRecall,
                )
                from ragas.metrics import (
                    _Faithfulness as Faithfulness,
                )
                from ragas.metrics import (
                    _SemanticSimilarity as SemanticSimilarity,
                )

                metric_map = {
                    "faithfulness": Faithfulness,
                    "answer_relevancy": AnswerRelevancy,
                    "context_precision": ContextPrecision,
                    "context_recall": ContextRecall,
                    "answer_correctness": AnswerCorrectness,
                    "semantic_similarity": SemanticSimilarity,
                }

            metrics = []
            for name in metric_names:
                if name in metric_map:
                    metric_cls = metric_map[name]
                    if name == "semantic_similarity":
                        metric = (
                            metric_cls(embeddings=embeddings)
                            if embeddings
                            else metric_cls()
                        )
                    elif name in ("answer_relevancy", "answer_correctness"):
                        metric = (
                            metric_cls(llm=llm, embeddings=embeddings)
                            if llm
                            else metric_cls()
                        )
                    else:
                        metric = metric_cls(llm=llm) if llm else metric_cls()
                    metrics.append(metric)
                    logger.debug(f"Created RAGAS metric: {name}")
                else:
                    logger.warning(f"Unknown RAGAS metric: {name}")

            return metrics

        except ImportError as e:
            error_msg = f"Failed to import RAGAS metrics: {str(e)}"
            logger.error(error_msg)
            raise EvaluationError(error_msg) from e

    @property
    def name(self) -> str:
        """
        Get the evaluator name.

        Returns:
            Evaluator name string.
        """
        return "ragas"

    @property
    def supported_retrieval_metrics(self) -> list[str]:
        """
        Get list of supported retrieval metrics.

        Note: RAGAS doesn't provide traditional retrieval metrics
        like hit_rate, mrr, ndcg. Use builtin evaluator for those.

        Returns:
            Empty list (RAGAS focuses on generation metrics).
        """
        return self._retrieval_metrics

    @property
    def supported_generation_metrics(self) -> list[str]:
        """
        Get list of supported generation metrics.

        Returns:
            List of RAGAS generation metric names.
        """
        return self._generation_metrics

    def evaluate_single(self, sample: EvaluationSample) -> EvaluationResult:
        """
        Evaluate a single sample using RAGAS metrics.

        Note: RAGAS is optimized for batch evaluation. For single samples,
        consider using batch evaluation for better performance.

        Args:
            sample: EvaluationSample containing all data needed for evaluation.

        Returns:
            EvaluationResult containing the evaluation scores.
        """
        question_id = sample.question_id
        question = sample.question
        answer = sample.answer
        contexts = sample.contexts
        expected_answer = sample.expected_answer
        llm_config = sample.llm_config
        generation_metrics = sample.generation_metrics
        if generation_metrics is None:
            generation_metrics = self._generation_metrics

        if expected_answer is None:
            ref_required = [
                m for m in generation_metrics if m in REFERENCE_REQUIRED_METRICS
            ]
            if ref_required:
                logger.warning(
                    f"Metrics {ref_required} require reference (expected_answer) "
                    f"but none provided for {question_id}. Skipping these metrics."
                )
                generation_metrics = [
                    m for m in generation_metrics if m not in REFERENCE_REQUIRED_METRICS
                ]

        if not generation_metrics:
            return EvaluationResult(
                question_id=question_id,
                question=question,
                answer=answer,
                contexts=contexts,
                retrieval_metrics={},
                generation_metrics={},
            )

        generation_results = {}
        error = None

        try:
            if not llm_config:
                raise EvaluationError("llm_config is required for RAGAS evaluation")

            if self._llm is None:
                self._llm = self._create_llm(llm_config)

            if self._embeddings is None and self.config:
                self._embeddings = self._create_embeddings(self.config)

            metrics = self._create_metrics(
                generation_metrics, self._llm, self._embeddings
            )

            dataset = self._build_ragas_dataset([sample])

            from ragas import evaluate

            run_config = self._build_run_config()

            result = evaluate(
                dataset=dataset,
                metrics=metrics,
                run_config=run_config,
                show_progress=False,
                raise_exceptions=True,
            )

            if hasattr(result, "scores") and result.scores:
                score_dict = (
                    result.scores[0]
                    if isinstance(result.scores, list)
                    else result.scores
                )
                if isinstance(score_dict, dict):
                    for metric_name, score in score_dict.items():
                        if score is not None:
                            try:
                                generation_results[metric_name] = float(score)
                            except (TypeError, ValueError):
                                logger.warning(
                                    f"Could not convert score for {metric_name}: {score}"
                                )

        except Exception as e:
            error = log_evaluation_error("RAGAS evaluation", question_id, e)

        return EvaluationResult(
            question_id=question_id,
            question=question,
            answer=answer,
            contexts=contexts,
            retrieval_metrics={},
            generation_metrics=generation_results,
            error=error,
        )

    def _has_reference(self, sample: EvaluationSample) -> bool:
        """
        Check if a sample has a valid reference for metrics that require it.

        Args:
            sample: EvaluationSample object.

        Returns:
            True if sample has a valid reference, False otherwise.
        """
        reference = sample.expected_answer
        return bool(reference)

    def _run_ragas_evaluation(
        self,
        samples: list[EvaluationSample],
        indices: list[int],
        metric_names: list[str],
        run_config: Any,
        log_message: str,
    ) -> dict[int, EvaluationResult]:
        """
        Run RAGAS evaluation on a subset of samples.

        Args:
            samples: List of EvaluationSample objects to evaluate.
            indices: Original indices of the samples.
            metric_names: List of metric names to compute.
            run_config: RAGAS run configuration.
            log_message: Message to log before evaluation.

        Returns:
            Dictionary mapping original indices to EvaluationResult objects.
        """
        metrics = self._create_metrics(metric_names, self._llm, self._embeddings)
        dataset = self._build_ragas_dataset(samples)

        logger.info(log_message)

        from ragas import evaluate

        eval_result = evaluate(
            dataset=dataset,
            metrics=metrics,
            run_config=run_config,
            show_progress=True,
            raise_exceptions=False,
        )

        results: dict[int, EvaluationResult] = {}

        if hasattr(eval_result, "scores") and eval_result.scores:
            for j, score_dict in enumerate(eval_result.scores):
                generation_results = {}
                if isinstance(score_dict, dict):
                    for metric_name in metric_names:
                        if (
                            metric_name in score_dict
                            and score_dict[metric_name] is not None
                        ):
                            try:
                                generation_results[metric_name] = float(
                                    score_dict[metric_name]
                                )
                            except (TypeError, ValueError):
                                logger.warning(
                                    f"Could not convert score for {metric_name}: {score_dict[metric_name]}"
                                )

                results[indices[j]] = EvaluationResult(
                    question_id=samples[j].question_id,
                    question=samples[j].question,
                    answer=samples[j].answer,
                    contexts=samples[j].contexts,
                    retrieval_metrics={},
                    generation_metrics=generation_results,
                )

        return results

    def evaluate_batch(
        self,
        samples: list[EvaluationSample],
        llm_config: dict[str, str] | None = None,
        retrieval_metrics: list[str] | None = None,
        generation_metrics: list[str] | None = None,
    ) -> list[EvaluationResult]:
        """
        Evaluate a batch of samples using RAGAS metrics.

        This is the recommended way to use RAGAS for better performance.

        Args:
            samples: List of EvaluationSample objects.
            llm_config: Optional LLM configuration.
            retrieval_metrics: Optional list of retrieval metrics to compute.
            generation_metrics: Optional list of generation metrics to compute.

        Returns:
            List of EvaluationResult objects.
        """
        if generation_metrics is None:
            generation_metrics = self._generation_metrics

        ref_required_metrics = [
            m for m in generation_metrics if m in REFERENCE_REQUIRED_METRICS
        ]
        non_ref_metrics = [
            m for m in generation_metrics if m not in REFERENCE_REQUIRED_METRICS
        ]

        samples_with_ref = [
            (i, s) for i, s in enumerate(samples) if self._has_reference(s)
        ]
        samples_without_ref = [
            (i, s) for i, s in enumerate(samples) if not self._has_reference(s)
        ]

        if samples_without_ref and ref_required_metrics:
            logger.info(
                f"{len(samples_without_ref)} samples lack reference, "
                f"skipping {ref_required_metrics} for them"
            )

        results: list[EvaluationResult | None] = [None] * len(samples)

        try:
            if not llm_config:
                raise EvaluationError("llm_config is required for RAGAS evaluation")

            if self._llm is None:
                self._llm = self._create_llm(llm_config)

            if self._embeddings is None and self.config:
                self._embeddings = self._create_embeddings(self.config)

            run_config = self._build_run_config()

            if samples_with_ref:
                ref_samples = [s for _, s in samples_with_ref]
                ref_indices = [i for i, _ in samples_with_ref]

                ref_results = self._run_ragas_evaluation(
                    samples=ref_samples,
                    indices=ref_indices,
                    metric_names=generation_metrics,
                    run_config=run_config,
                    log_message=f"Running RAGAS evaluation on {len(ref_samples)} samples with reference...",
                )
                results = [
                    ref_results.get(i) if ref_results.get(i) is not None else r
                    for i, r in enumerate(results)
                ]

            if samples_without_ref and non_ref_metrics:
                non_ref_samples = [s for _, s in samples_without_ref]
                non_ref_indices = [i for i, _ in samples_without_ref]

                non_ref_results = self._run_ragas_evaluation(
                    samples=non_ref_samples,
                    indices=non_ref_indices,
                    metric_names=non_ref_metrics,
                    run_config=run_config,
                    log_message=f"Running RAGAS evaluation on {len(non_ref_samples)} samples without reference...",
                )
                results = [
                    non_ref_results.get(i) if non_ref_results.get(i) is not None else r
                    for i, r in enumerate(results)
                ]

            for i, result in enumerate(results):
                if result is None:
                    results[i] = EvaluationResult(
                        question_id=samples[i].question_id,
                        question=samples[i].question,
                        answer=samples[i].answer,
                        contexts=samples[i].contexts,
                        retrieval_metrics={},
                        generation_metrics={},
                        error="Failed to evaluate sample",
                    )

        except Exception as e:
            error_msg = log_evaluation_error("RAGAS batch evaluation", "", e)
            for i, sample in enumerate(samples):
                if results[i] is None:
                    results[i] = EvaluationResult(
                        question_id=sample.question_id,
                        question=sample.question,
                        answer=sample.answer,
                        contexts=sample.contexts,
                        retrieval_metrics={},
                        generation_metrics={},
                        error=error_msg,
                    )

        return [r for r in results if r is not None]
