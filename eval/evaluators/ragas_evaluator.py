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

from typing import Any, Dict, List, Optional

from loguru import logger

from eval.evaluators.base import BaseEvaluator, EvaluationResult


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

    def __init__(self, config: Optional[Dict[str, Any]] = None):
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

    def _create_llm(self, llm_config: Dict[str, str]) -> Any:
        """
        Create RAGAS-compatible LLM using LangchainLLMWrapper.

        Uses ChatAnthropic with api_key='dummy' and the real key passed
        via the Authorization: Bearer header, matching the pattern used
        by the project's Generator class. This is required because the
        LongCat API proxy expects the key in the Authorization header
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
            from langchain_anthropic import ChatAnthropic
            from ragas.llms import LangchainLLMWrapper

            base_url = llm_config["base_url"].rstrip("/")
            if not base_url.endswith("/anthropic"):
                base_url = f"{base_url}/anthropic"

            chat_model = ChatAnthropic(
                model=llm_config["model_name"],
                api_key="dummy",
                base_url=base_url,
                default_headers={
                    "Authorization": f"Bearer {llm_config['api_key']}",
                    "Content-Type": "application/json",
                },
                max_tokens=llm_config.get("max_tokens", 4096),
                temperature=llm_config.get("temperature", 0.0),
            )

            return LangchainLLMWrapper(chat_model)

        except ImportError as e:
            error_msg = f"Failed to import RAGAS dependencies: {str(e)}"
            logger.error(error_msg)
            raise ImportError(
                f"{error_msg}. Please install with: pixi add langchain-anthropic ragas"
            )

    def _create_embeddings(self, config: Dict[str, Any]) -> Any:
        """
        Create RAGAS-compatible embeddings using LangChain HuggingFaceEmbeddings.

        Uses langchain_community HuggingFaceEmbeddings which provides the
        embed_query() method required by RAGAS AnswerRelevancy metric.
        The ragas.embeddings.HuggingFaceEmbeddings only provides embed_text()
        which is incompatible.

        Args:
            config: Configuration dictionary containing embedding settings.

        Returns:
            LangChain HuggingFaceEmbeddings instance compatible with RAGAS.
        """
        try:
            from langchain_community.embeddings import HuggingFaceEmbeddings

            embedding_config = config.get("embedding", {})
            model_name = embedding_config.get(
                "model_name", "BAAI/bge-large-zh-v1.5"
            )
            device = embedding_config.get("device", "cuda")

            return HuggingFaceEmbeddings(
                model_name=model_name,
                model_kwargs={"device": device},
            )

        except ImportError as e:
            error_msg = f"Failed to import embeddings dependencies: {str(e)}"
            logger.error(error_msg)
            raise ImportError(
                f"{error_msg}. Please install with: pixi add langchain-community sentence-transformers ragas"
            )

    def _build_ragas_dataset(
        self, samples: List[Dict[str, Any]]
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
            from ragas import SingleTurnSample, EvaluationDataset

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
        metric_names: List[str],
        llm: Any,
        embeddings: Optional[Any] = None,
    ) -> List[Any]:
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
            from ragas.metrics import (
                _Faithfulness as Faithfulness,
                _AnswerRelevancy as AnswerRelevancy,
                _ContextPrecision as ContextPrecision,
                _ContextRecall as ContextRecall,
                _AnswerCorrectness as AnswerCorrectness,
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
    def supported_retrieval_metrics(self) -> List[str]:
        """
        Get list of supported retrieval metrics.

        Note: RAGAS doesn't provide traditional retrieval metrics
        like hit_rate, mrr, ndcg. Use builtin evaluator for those.

        Returns:
            Empty list (RAGAS focuses on generation metrics).
        """
        return self._retrieval_metrics

    @property
    def supported_generation_metrics(self) -> List[str]:
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
        contexts: List[str],
        expected_sources: Optional[List[str]] = None,
        expected_answer: Optional[str] = None,
        llm_config: Optional[Dict[str, str]] = None,
        generation_metrics: Optional[List[str]] = None,
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

            result = evaluate(
                dataset=dataset,
                metrics=metrics,
                llm=self._llm,
                embeddings=self._embeddings,
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
        samples: List[Dict[str, Any]],
        llm_config: Optional[Dict[str, str]] = None,
        generation_metrics: Optional[List[str]] = None,
    ) -> List[EvaluationResult]:
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

            eval_result = evaluate(
                dataset=dataset,
                metrics=metrics,
                llm=self._llm,
                embeddings=self._embeddings,
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
