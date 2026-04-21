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

from eval.evaluators.base import BaseEvaluator, EvaluationResult

REFERENCE_REQUIRED_METRICS = {"context_precision", "context_recall", "answer_correctness", "semantic_similarity"}


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
        self._embedding_config: dict[str, Any] = self._ragas_config.get(
            "embedding", {}
        )

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

            return create_llm_client(llm_config=llm_config_with_tokens, mode="langchain")
        except ImportError as e:
            error_msg = f"Failed to create LLM client: {str(e)}"
            logger.error(error_msg)
            raise ImportError(
                f"{error_msg}. Please install with: pixi add langchain-anthropic ragas"
            )

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
            model_name = (
                self._ragas_config.get("embedding_model")
                or embedding_config.get("model_name", "BAAI/bge-large-zh-v1.5")
            )
            device = (
                self._ragas_config.get("device")
                or embedding_config.get("device", "cuda")
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
            raise ImportError(
                f"{error_msg}. Please install ragas properly."
            )

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

    def _build_ragas_dataset(
        self, samples: list[dict[str, Any]]
    ) -> Any:
        """
        Build RAGAS EvaluationDataset from sample dictionaries.

        Args:
            samples: List of sample dictionaries containing:
                - question_id: Unique identifier
                - question: Question text
                - answer: Generated answer
                - contexts: Retrieved contexts
                - expected_answer: Optional reference answer

        Returns:
            RAGAS EvaluationDataset instance.
        """
        try:
            from ragas import EvaluationDataset, SingleTurnSample

            ragas_samples = []
            for sample in samples:
                ragas_sample = SingleTurnSample(
                    user_input=sample.get("question", ""),
                    response=sample.get("answer", ""),
                    retrieved_contexts=sample.get("contexts", []),
                    reference=sample.get("expected_answer"),
                )
                ragas_samples.append(ragas_sample)

            return EvaluationDataset(samples=ragas_samples)

        except ImportError as e:
            error_msg = f"Failed to import RAGAS dataset classes: {str(e)}"
            logger.error(error_msg)
            raise ImportError(error_msg)

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
                        metric = metric_cls(embeddings=embeddings) if embeddings else metric_cls()
                    elif name in ("answer_relevancy", "answer_correctness"):
                        metric = metric_cls(llm=llm, embeddings=embeddings) if llm else metric_cls()
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
            raise ImportError(error_msg)

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

    def evaluate_single(
        self,
        question_id: str,
        question: str,
        answer: str,
        contexts: list[str],
        expected_sources: list[str] | None = None,
        expected_answer: str | None = None,
        llm_config: dict[str, str] | None = None,
        generation_metrics: list[str] | None = None,
    ) -> EvaluationResult:
        """
        Evaluate a single sample using RAGAS metrics.

        Note: RAGAS is optimized for batch evaluation. For single samples,
        consider using batch evaluation for better performance.

        Args:
            question_id: Unique identifier for the question.
            question: The question text.
            answer: The generated answer.
            contexts: List of retrieved context strings.
            expected_sources: Optional list of expected source documents (not used by RAGAS).
            expected_answer: Optional expected answer for reference.
            llm_config: Optional LLM configuration.
            generation_metrics: Optional list of generation metrics to compute.

        Returns:
            EvaluationResult containing the evaluation scores.
        """
        if generation_metrics is None:
            generation_metrics = self._generation_metrics

        if expected_answer is None:
            ref_required = [m for m in generation_metrics if m in REFERENCE_REQUIRED_METRICS]
            if ref_required:
                logger.warning(
                    f"Metrics {ref_required} require reference (expected_answer) "
                    f"but none provided for {question_id}. Skipping these metrics."
                )
                generation_metrics = [m for m in generation_metrics if m not in REFERENCE_REQUIRED_METRICS]

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
                raise ValueError("llm_config is required for RAGAS evaluation")

            if self._llm is None:
                self._llm = self._create_llm(llm_config)

            if self._embeddings is None and self.config:
                self._embeddings = self._create_embeddings(self.config)

            metrics = self._create_metrics(
                generation_metrics, self._llm, self._embeddings
            )

            sample = {
                "question_id": question_id,
                "question": question,
                "answer": answer,
                "contexts": contexts,
                "expected_answer": expected_answer,
            }

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
                score_dict = result.scores[0] if isinstance(result.scores, list) else result.scores
                if isinstance(score_dict, dict):
                    for metric_name, score in score_dict.items():
                        if score is not None:
                            try:
                                generation_results[metric_name] = float(score)
                            except (TypeError, ValueError):
                                logger.warning(f"Could not convert score for {metric_name}: {score}")

        except Exception as e:
            error = str(e)
            logger.error(f"RAGAS evaluation failed for {question_id}: {error}")

        return EvaluationResult(
            question_id=question_id,
            question=question,
            answer=answer,
            contexts=contexts,
            retrieval_metrics={},
            generation_metrics=generation_results,
            error=error,
        )

    def evaluate_batch(
        self,
        samples: list[dict[str, Any]],
        llm_config: dict[str, str] | None = None,
        generation_metrics: list[str] | None = None,
    ) -> list[EvaluationResult]:
        """
        Evaluate a batch of samples using RAGAS metrics.

        This is the recommended way to use RAGAS for better performance.

        Args:
            samples: List of sample dictionaries.
            llm_config: Optional LLM configuration.
            generation_metrics: Optional list of generation metrics to compute.

        Returns:
            List of EvaluationResult objects.
        """
        if generation_metrics is None:
            generation_metrics = self._generation_metrics

        samples_without_ref = [
            s for s in samples
            if s.get("expected_answer") is None
        ]
        if samples_without_ref:
            ref_required = [m for m in generation_metrics if m in REFERENCE_REQUIRED_METRICS]
            if ref_required:
                logger.warning(
                    f"Metrics {ref_required} require reference (expected_answer) "
                    f"but {len(samples_without_ref)}/{len(samples)} samples lack it. "
                    f"These metrics may return NaN for those samples."
                )

        results = []

        try:
            if not llm_config:
                raise ValueError("llm_config is required for RAGAS evaluation")

            if self._llm is None:
                self._llm = self._create_llm(llm_config)

            if self._embeddings is None and self.config:
                self._embeddings = self._create_embeddings(self.config)

            metrics = self._create_metrics(
                generation_metrics, self._llm, self._embeddings
            )

            dataset = self._build_ragas_dataset(samples)

            logger.info(f"Running RAGAS evaluation on {len(samples)} samples...")

            from ragas import evaluate

            run_config = self._build_run_config()

            eval_result = evaluate(
                dataset=dataset,
                metrics=metrics,
                run_config=run_config,
                show_progress=True,
                raise_exceptions=False,
            )

            if hasattr(eval_result, "scores") and eval_result.scores:
                for i, score_dict in enumerate(eval_result.scores):
                    generation_results = {}
                    if isinstance(score_dict, dict):
                        for metric_name in generation_metrics:
                            if metric_name in score_dict and score_dict[metric_name] is not None:
                                try:
                                    generation_results[metric_name] = float(score_dict[metric_name])
                                except (TypeError, ValueError):
                                    logger.warning(f"Could not convert score for {metric_name}: {score_dict[metric_name]}")

                    results.append(
                        EvaluationResult(
                            question_id=samples[i].get("question_id", f"sample_{i}"),
                            question=samples[i].get("question", ""),
                            answer=samples[i].get("answer", ""),
                            contexts=samples[i].get("contexts", []),
                            retrieval_metrics={},
                            generation_metrics=generation_results,
                        )
                    )
            elif hasattr(eval_result, "to_pandas"):
                df = eval_result.to_pandas()
                for i, row in df.iterrows():
                    generation_results = {}
                    for metric_name in generation_metrics:
                        if metric_name in row and row[metric_name] is not None:
                            try:
                                generation_results[metric_name] = float(row[metric_name])
                            except (TypeError, ValueError):
                                logger.warning(f"Could not convert score for {metric_name}: {row[metric_name]}")

                    results.append(
                        EvaluationResult(
                            question_id=samples[i].get("question_id", f"sample_{i}"),
                            question=samples[i].get("question", ""),
                            answer=samples[i].get("answer", ""),
                            contexts=samples[i].get("contexts", []),
                            retrieval_metrics={},
                            generation_metrics=generation_results,
                        )
                    )
            else:
                for i, sample in enumerate(samples):
                    results.append(
                        EvaluationResult(
                            question_id=sample.get("question_id", f"sample_{i}"),
                            question=sample.get("question", ""),
                            answer=sample.get("answer", ""),
                            contexts=sample.get("contexts", []),
                            retrieval_metrics={},
                            generation_metrics={},
                            error="Failed to parse RAGAS results",
                        )
                    )

        except Exception as e:
            error_msg = str(e)
            logger.error(f"RAGAS batch evaluation failed: {error_msg}")
            for i, sample in enumerate(samples):
                results.append(
                    EvaluationResult(
                        question_id=sample.get("question_id", f"sample_{i}"),
                        question=sample.get("question", ""),
                        answer=sample.get("answer", ""),
                        contexts=sample.get("contexts", []),
                        retrieval_metrics={},
                        generation_metrics={},
                        error=error_msg,
                    )
                )

        return results
