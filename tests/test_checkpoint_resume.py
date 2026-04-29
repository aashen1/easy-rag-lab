import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from eval.runner.evaluation import (
    _load_question_checkpoint,
    _save_question_checkpoint,
    collect_rag_samples,
)
from eval.runner.metrics import merge_result, namespace_result
from src.experiment import ExperimentManager


class TestQuestionLevelCheckpoint:
    def test_save_and_load_checkpoint(self, tmp_path):
        checkpoint_path = tmp_path / "test_variant_checkpoint.json"
        samples = [
            {"question_id": "q1", "question": "What?", "answer": "A1"},
            {"question_id": "q2", "question": "How?", "answer": "A2"},
        ]

        _save_question_checkpoint(
            checkpoint_path=checkpoint_path,
            variant_name="test_variant",
            experiment_name="test_exp",
            samples=samples,
            total_questions=5,
            model_name="gpt-4",
        )

        assert checkpoint_path.exists()

        loaded = _load_question_checkpoint(checkpoint_path)
        assert loaded is not None
        assert len(loaded) == 2
        assert loaded[0]["question_id"] == "q1"
        assert loaded[1]["question_id"] == "q2"

        with open(checkpoint_path, encoding="utf-8") as f:
            data = json.load(f)
        assert data["variant_name"] == "test_variant"
        assert data["experiment_name"] == "test_exp"
        assert data["model_name"] == "gpt-4"
        assert data["completed_questions"] == 2
        assert data["total_questions"] == 5

    def test_load_checkpoint_nonexistent_file(self, tmp_path):
        checkpoint_path = tmp_path / "nonexistent.json"
        result = _load_question_checkpoint(checkpoint_path)
        assert result is None

    def test_load_checkpoint_corrupted_file(self, tmp_path):
        checkpoint_path = tmp_path / "corrupted.json"
        checkpoint_path.write_text("invalid json {{{", encoding="utf-8")
        result = _load_question_checkpoint(checkpoint_path)
        assert result is None

    def test_load_checkpoint_empty_samples(self, tmp_path):
        checkpoint_path = tmp_path / "empty.json"
        data = {
            "variant_name": "v1",
            "samples": [],
            "completed_questions": 0,
            "total_questions": 5,
        }
        with open(checkpoint_path, "w", encoding="utf-8") as f:
            json.dump(data, f)

        result = _load_question_checkpoint(checkpoint_path)
        assert result is None

    def test_save_checkpoint_io_error(self, tmp_path):
        checkpoint_path = tmp_path / "readonly_dir" / "checkpoint.json"
        checkpoint_path.parent.mkdir()
        checkpoint_path.parent.chmod(0o444)

        try:
            _save_question_checkpoint(
                checkpoint_path=checkpoint_path,
                variant_name="v1",
                experiment_name="exp1",
                samples=[{"question_id": "q1"}],
                total_questions=5,
                model_name="gpt-4",
            )
        finally:
            checkpoint_path.parent.chmod(0o755)


class TestCollectRagSamplesCheckpointResume:
    def _make_test_set(self, num_questions=5):
        questions = []
        for i in range(num_questions):
            questions.append(
                {
                    "id": f"q{i + 1}",
                    "question": f"Question {i + 1}?",
                    "source_files": [f"doc{i}.pdf"],
                    "question_type": "factual",
                }
            )
        return {"name": "test_set", "questions": questions}

    def test_collect_from_scratch_no_checkpoint(self, tmp_path):
        pipeline = MagicMock()
        pipeline.query.return_value = {
            "answer": "Test answer",
            "contexts": ["ctx1"],
            "sources": ["doc1.pdf"],
            "chunk_ids": ["doc1::chunk::001"],
            "token_usage": None,
        }

        test_set = self._make_test_set(3)
        checkpoint_dir = tmp_path / "checkpoints"

        samples = collect_rag_samples(
            pipeline=pipeline,
            test_set=test_set,
            checkpoint_dir=checkpoint_dir,
            variant_name="v1",
            experiment_name="exp1",
            model_name="gpt-4",
        )

        assert len(samples) == 3
        assert pipeline.query.call_count == 3
        assert checkpoint_dir.exists()

        checkpoint_path = checkpoint_dir / "v1_checkpoint.json"
        assert checkpoint_path.exists()

    def test_resume_from_partial_checkpoint(self, tmp_path):
        checkpoint_dir = tmp_path / "checkpoints"
        checkpoint_dir.mkdir()

        existing_samples = [
            {
                "question_id": "q1",
                "question": "Question 1?",
                "answer": "A1",
                "contexts": ["c1"],
            },
            {
                "question_id": "q2",
                "question": "Question 2?",
                "answer": "A2",
                "contexts": ["c2"],
            },
        ]

        _save_question_checkpoint(
            checkpoint_path=checkpoint_dir / "v1_checkpoint.json",
            variant_name="v1",
            experiment_name="exp1",
            samples=existing_samples,
            total_questions=5,
            model_name="gpt-4",
        )

        pipeline = MagicMock()
        pipeline.query.return_value = {
            "answer": "Resumed answer",
            "contexts": ["ctx"],
            "sources": ["doc.pdf"],
            "chunk_ids": ["doc::chunk::001"],
            "token_usage": None,
        }

        test_set = self._make_test_set(5)
        samples = collect_rag_samples(
            pipeline=pipeline,
            test_set=test_set,
            checkpoint_dir=checkpoint_dir,
            variant_name="v1",
            experiment_name="exp1",
            model_name="gpt-4",
        )

        assert len(samples) == 5
        assert samples[0]["question_id"] == "q1"
        assert samples[1]["question_id"] == "q2"
        assert samples[2]["answer"] == "Resumed answer"
        assert pipeline.query.call_count == 3

    def test_resume_all_completed_from_checkpoint(self, tmp_path):
        checkpoint_dir = tmp_path / "checkpoints"
        checkpoint_dir.mkdir()

        all_samples = [
            {
                "question_id": f"q{i + 1}",
                "question": f"Question {i + 1}?",
                "answer": f"A{i + 1}",
                "contexts": [f"c{i + 1}"],
            }
            for i in range(3)
        ]

        _save_question_checkpoint(
            checkpoint_path=checkpoint_dir / "v1_checkpoint.json",
            variant_name="v1",
            experiment_name="exp1",
            samples=all_samples,
            total_questions=3,
            model_name="gpt-4",
        )

        pipeline = MagicMock()
        test_set = self._make_test_set(3)

        samples = collect_rag_samples(
            pipeline=pipeline,
            test_set=test_set,
            checkpoint_dir=checkpoint_dir,
            variant_name="v1",
            experiment_name="exp1",
            model_name="gpt-4",
        )

        assert len(samples) == 3
        pipeline.query.assert_not_called()

    def test_no_checkpoint_dir_means_no_checkpoint(self, tmp_path):
        pipeline = MagicMock()
        pipeline.query.return_value = {
            "answer": "A",
            "contexts": ["c"],
            "sources": ["s"],
            "chunk_ids": [],
            "token_usage": None,
        }

        test_set = self._make_test_set(2)
        samples = collect_rag_samples(
            pipeline=pipeline,
            test_set=test_set,
            checkpoint_dir=None,
            variant_name="v1",
            experiment_name="exp1",
        )

        assert len(samples) == 2
        assert pipeline.query.call_count == 2

    def test_checkpoint_saved_after_each_question(self, tmp_path):
        checkpoint_dir = tmp_path / "checkpoints"
        pipeline = MagicMock()
        pipeline.query.return_value = {
            "answer": "A",
            "contexts": ["c"],
            "sources": ["s"],
            "chunk_ids": [],
            "token_usage": None,
        }

        test_set = self._make_test_set(3)
        collect_rag_samples(
            pipeline=pipeline,
            test_set=test_set,
            checkpoint_dir=checkpoint_dir,
            variant_name="v1",
            experiment_name="exp1",
        )

        checkpoint_path = checkpoint_dir / "v1_checkpoint.json"
        assert checkpoint_path.exists()

        with open(checkpoint_path, encoding="utf-8") as f:
            data = json.load(f)
        assert data["completed_questions"] == 3
        assert data["total_questions"] == 3

    def test_variant_name_sanitized_in_checkpoint_filename(self, tmp_path):
        checkpoint_dir = tmp_path / "checkpoints"
        pipeline = MagicMock()
        pipeline.query.return_value = {
            "answer": "A",
            "contexts": ["c"],
            "sources": ["s"],
            "chunk_ids": [],
            "token_usage": None,
        }

        test_set = self._make_test_set(1)
        collect_rag_samples(
            pipeline=pipeline,
            test_set=test_set,
            checkpoint_dir=checkpoint_dir,
            variant_name="Chunk-512 Overlap 0",
            experiment_name="exp1",
        )

        expected_path = checkpoint_dir / "chunk_512_overlap_0_checkpoint.json"
        assert expected_path.exists()

    def test_rejected_questions_filtered_out(self, tmp_path):
        pipeline = MagicMock()
        pipeline.query.return_value = {
            "answer": "A",
            "contexts": ["c"],
            "sources": ["s"],
            "chunk_ids": [],
            "token_usage": None,
        }

        test_set = {
            "name": "test_set",
            "questions": [
                {
                    "id": "q1",
                    "question": "Valid?",
                    "metadata": {"review_status": "approved"},
                },
                {
                    "id": "q2",
                    "question": "Rejected?",
                    "metadata": {"review_status": "rejected"},
                },
                {"id": "q3", "question": "Also valid?"},
            ],
        }

        samples = collect_rag_samples(
            pipeline=pipeline,
            test_set=test_set,
            checkpoint_dir=tmp_path / "checkpoints",
            variant_name="v1",
        )

        assert len(samples) == 2
        assert samples[0]["question_id"] == "q1"
        assert samples[1]["question_id"] == "q3"


class TestVariantLevelCheckpointResume:
    def _create_experiment_dir(self, tmp_path: Path, completed_variants=None):
        exp_dir = tmp_path / "exp_test"
        exp_dir.mkdir()

        manifest = {
            "name": "test_exp",
            "status": "running",
            "variants": ["v1", "v2", "v3"],
            "completed_variants": completed_variants or [],
            "created_at": "2026-01-01T00:00:00",
        }
        with open(exp_dir / "manifest.json", "w", encoding="utf-8") as f:
            json.dump(manifest, f)

        results_dir = exp_dir / "results"
        results_dir.mkdir()

        return exp_dir

    def test_get_completed_variants_empty(self, tmp_path):
        exp_dir = self._create_experiment_dir(tmp_path)
        manager = ExperimentManager({"experiments": {"base_dir": str(tmp_path)}})

        completed = manager.get_completed_variants(exp_dir)
        assert completed == []

    def test_get_completed_variants_with_completed(self, tmp_path):
        exp_dir = self._create_experiment_dir(tmp_path, completed_variants=["v1", "v2"])
        manager = ExperimentManager({"experiments": {"base_dir": str(tmp_path)}})

        completed = manager.get_completed_variants(exp_dir)
        assert set(completed) == {"v1", "v2"}

    def test_mark_variant_completed(self, tmp_path):
        exp_dir = self._create_experiment_dir(tmp_path)
        manager = ExperimentManager({"experiments": {"base_dir": str(tmp_path)}})

        manager.mark_variant_completed(exp_dir, "v1")

        completed = manager.get_completed_variants(exp_dir)
        assert "v1" in completed

    def test_mark_variant_completed_idempotent(self, tmp_path):
        exp_dir = self._create_experiment_dir(tmp_path)
        manager = ExperimentManager({"experiments": {"base_dir": str(tmp_path)}})

        manager.mark_variant_completed(exp_dir, "v1")
        manager.mark_variant_completed(exp_dir, "v1")

        completed = manager.get_completed_variants(exp_dir)
        assert completed.count("v1") == 1

    def test_save_and_load_variant_result(self, tmp_path):
        exp_dir = self._create_experiment_dir(tmp_path)
        manager = ExperimentManager({"experiments": {"base_dir": str(tmp_path)}})

        result = {
            "variant_name": "v1",
            "total_questions": 10,
            "retrieval_metrics": {"avg_hit_rate": 0.85},
        }

        manager.save_variant_result(exp_dir, "v1", result)

        loaded = manager.load_variant_result(exp_dir, "v1")
        assert loaded is not None
        assert loaded["variant_name"] == "v1"
        assert loaded["retrieval_metrics"]["avg_hit_rate"] == 0.85

    def test_load_variant_result_not_found(self, tmp_path):
        exp_dir = self._create_experiment_dir(tmp_path)
        manager = ExperimentManager({"experiments": {"base_dir": str(tmp_path)}})

        loaded = manager.load_variant_result(exp_dir, "nonexistent")
        assert loaded is None

    def test_update_manifest_field(self, tmp_path):
        exp_dir = self._create_experiment_dir(tmp_path)
        manager = ExperimentManager({"experiments": {"base_dir": str(tmp_path)}})

        manager.update_manifest_field(exp_dir, "completed_variants", [])

        with open(exp_dir / "manifest.json", encoding="utf-8") as f:
            manifest = json.load(f)
        assert manifest["completed_variants"] == []

    def test_variant_result_filename_sanitized(self, tmp_path):
        exp_dir = self._create_experiment_dir(tmp_path)
        manager = ExperimentManager({"experiments": {"base_dir": str(tmp_path)}})

        result = {"variant_name": "Chunk-512 Overlap 0"}
        manager.save_variant_result(exp_dir, "Chunk-512 Overlap 0", result)

        expected_path = exp_dir / "results" / "chunk_512_overlap_0.json"
        assert expected_path.exists()

    def test_full_variant_resume_flow(self, tmp_path):
        exp_dir = self._create_experiment_dir(tmp_path, completed_variants=["v1"])

        v1_result = {
            "variant_name": "v1",
            "total_questions": 5,
            "retrieval_metrics": {"avg_hit_rate": 0.9},
        }
        manager = ExperimentManager({"experiments": {"base_dir": str(tmp_path)}})
        manager.save_variant_result(exp_dir, "v1", v1_result)

        completed = manager.get_completed_variants(exp_dir)
        assert "v1" in completed

        loaded = manager.load_variant_result(exp_dir, "v1")
        assert loaded is not None
        assert loaded["variant_name"] == "v1"

        manager.mark_variant_completed(exp_dir, "v2")
        completed = manager.get_completed_variants(exp_dir)
        assert "v2" in completed


class TestModelChangeDetection:
    def test_model_change_warning_on_checkpoint_load(self, tmp_path):
        checkpoint_dir = tmp_path / "checkpoints"
        checkpoint_dir.mkdir()

        _save_question_checkpoint(
            checkpoint_path=checkpoint_dir / "v1_checkpoint.json",
            variant_name="v1",
            experiment_name="exp1",
            samples=[{"question_id": "q1", "answer": "A1"}],
            total_questions=5,
            model_name="gpt-3.5-turbo",
        )

        loaded = _load_question_checkpoint(checkpoint_dir / "v1_checkpoint.json")
        assert loaded is not None

        with open(checkpoint_dir / "v1_checkpoint.json", encoding="utf-8") as f:
            data = json.load(f)
        assert data["model_name"] == "gpt-3.5-turbo"


class TestIndexerCacheMechanism:
    def test_indexer_cache_reuses_same_hash(self):
        from src.meal import compute_chunker_config_hash

        config_a = {"chunk_size": 512, "chunk_overlap": 0}
        config_b = {"chunk_size": 512, "chunk_overlap": 0}
        config_c = {"chunk_size": 256, "chunk_overlap": 0}

        hash_a = compute_chunker_config_hash(config_a)
        hash_b = compute_chunker_config_hash(config_b)
        hash_c = compute_chunker_config_hash(config_c)

        assert hash_a == hash_b
        assert hash_a != hash_c

    def test_indexer_cache_dict_behavior(self):
        cache: dict[str, Any] = {}

        from src.meal import compute_chunker_config_hash

        config = {"chunk_size": 512, "chunk_overlap": 0}
        h = compute_chunker_config_hash(config)

        mock_indexer = MagicMock()
        cache[h] = mock_indexer

        assert h in cache
        assert cache[h] is mock_indexer

        config2 = {"chunk_size": 512, "chunk_overlap": 0}
        h2 = compute_chunker_config_hash(config2)
        assert h2 in cache
        assert cache[h2] is mock_indexer


class TestMergeResult:
    def test_merge_generation_metrics(self):
        target = {
            "id": "q1",
            "generation": {"builtin_faithfulness": 0.9},
        }
        source = {
            "id": "q1",
            "generation": {"ragas_faithfulness": 0.85},
        }

        merge_result(target, source)

        assert "builtin_faithfulness" in target["generation"]
        assert "ragas_faithfulness" in target["generation"]
        assert target["generation"]["ragas_faithfulness"] == 0.85

    def test_merge_llm_retrieval_metrics(self):
        target = {
            "id": "q1",
            "llm_retrieval": {"context_precision": 0.8},
        }
        source = {
            "id": "q1",
            "llm_retrieval": {"context_recall": 0.7},
        }

        merge_result(target, source)

        assert target["llm_retrieval"]["context_precision"] == 0.8
        assert target["llm_retrieval"]["context_recall"] == 0.7

    def test_merge_creates_missing_keys(self):
        target = {"id": "q1"}
        source = {
            "id": "q1",
            "generation": {"faithfulness": 0.9},
            "llm_retrieval": {"context_precision": 0.8},
        }

        merge_result(target, source)

        assert "generation" in target
        assert target["generation"]["faithfulness"] == 0.9
        assert "llm_retrieval" in target
        assert target["llm_retrieval"]["context_precision"] == 0.8

    def test_merge_ragas_error(self):
        target = {"id": "q1"}
        source = {"id": "q1", "ragas_error": "API timeout"}

        merge_result(target, source)

        assert target["ragas_error"] == "API timeout"

    def test_merge_empty_source_generation(self):
        target = {"id": "q1", "generation": {"faithfulness": 0.9}}
        source = {"id": "q1", "generation": {}}

        merge_result(target, source)

        assert target["generation"]["faithfulness"] == 0.9


class TestNamespaceResult:
    def test_namespace_generation_metrics(self):
        result = {
            "id": "q1",
            "generation": {"faithfulness": 0.9, "answer_relevancy": 0.8},
        }

        namespaced = namespace_result(result, "ragas")

        assert "ragas_faithfulness" in namespaced["generation"]
        assert "ragas_answer_relevancy" in namespaced["generation"]
        assert "faithfulness" not in namespaced["generation"]
        assert namespaced["generation"]["ragas_faithfulness"] == 0.9

    def test_namespace_llm_retrieval_metrics(self):
        result = {
            "id": "q1",
            "llm_retrieval": {"context_precision": 0.8, "context_recall": 0.7},
        }

        namespaced = namespace_result(result, "ragas")

        assert "ragas_context_precision" in namespaced["llm_retrieval"]
        assert "ragas_context_recall" in namespaced["llm_retrieval"]
        assert namespaced["llm_retrieval"]["ragas_context_precision"] == 0.8

    def test_namespace_empty_generation(self):
        result = {"id": "q1", "generation": {}}

        namespaced = namespace_result(result, "builtin")

        assert namespaced["generation"] == {}

    def test_namespace_no_generation_key(self):
        result = {"id": "q1", "retrieval": {"hit_rate": 1.0}}

        namespaced = namespace_result(result, "builtin")

        assert "generation" not in namespaced


class TestCLIForceRerun:
    def test_force_rerun_flag_in_argparse(self):
        import argparse

        parser = argparse.ArgumentParser()
        parser.add_argument("--config", type=str)
        parser.add_argument("--force-rerun", action="store_true")

        args = parser.parse_args(["--config", "test.yaml", "--force-rerun"])
        assert args.force_rerun is True

    def test_no_force_rerun_flag_default(self):
        import argparse

        parser = argparse.ArgumentParser()
        parser.add_argument("--config", type=str)
        parser.add_argument("--force-rerun", action="store_true")

        args = parser.parse_args(["--config", "test.yaml"])
        assert args.force_rerun is False


class TestCheckpointCleanupAfterCompletion:
    def test_checkpoint_file_cleaned_after_variant_completion(self, tmp_path):
        checkpoint_dir = tmp_path / "checkpoints"
        checkpoint_dir.mkdir()

        checkpoint_path = checkpoint_dir / "v1_checkpoint.json"
        _save_question_checkpoint(
            checkpoint_path=checkpoint_path,
            variant_name="v1",
            experiment_name="exp1",
            samples=[{"question_id": "q1", "answer": "A1"}],
            total_questions=1,
            model_name="gpt-4",
        )

        assert checkpoint_path.exists()

        checkpoint_path.unlink()
        assert not checkpoint_path.exists()


class TestEndToEndCheckpointFlow:
    def test_full_question_level_resume_flow(self, tmp_path):
        checkpoint_dir = tmp_path / "checkpoints"

        pipeline = MagicMock()
        pipeline.query.side_effect = [
            {
                "answer": "A1",
                "contexts": ["c1"],
                "sources": ["s1"],
                "chunk_ids": [],
                "token_usage": None,
            },
            {
                "answer": "A2",
                "contexts": ["c2"],
                "sources": ["s2"],
                "chunk_ids": [],
                "token_usage": None,
            },
        ]

        test_set = {
            "name": "test_set",
            "questions": [
                {"id": "q1", "question": "Q1?", "source_files": ["doc1.pdf"]},
                {"id": "q2", "question": "Q2?", "source_files": ["doc2.pdf"]},
            ],
        }

        samples = collect_rag_samples(
            pipeline=pipeline,
            test_set=test_set,
            checkpoint_dir=checkpoint_dir,
            variant_name="v1",
            experiment_name="exp1",
            model_name="gpt-4",
        )

        assert len(samples) == 2
        assert pipeline.query.call_count == 2

        checkpoint_path = checkpoint_dir / "v1_checkpoint.json"
        assert checkpoint_path.exists()

        pipeline2 = MagicMock()
        pipeline2.query.return_value = {
            "answer": "A2_new",
            "contexts": ["c2_new"],
            "sources": ["s2_new"],
            "chunk_ids": [],
            "token_usage": None,
        }

        samples2 = collect_rag_samples(
            pipeline=pipeline2,
            test_set=test_set,
            checkpoint_dir=checkpoint_dir,
            variant_name="v1",
            experiment_name="exp1",
            model_name="gpt-4",
        )

        assert len(samples2) == 2
        assert pipeline2.query.call_count == 0

    def test_interrupt_and_resume_simulation(self, tmp_path):
        checkpoint_dir = tmp_path / "checkpoints"
        checkpoint_dir.mkdir()

        _save_question_checkpoint(
            checkpoint_path=checkpoint_dir / "v1_checkpoint.json",
            variant_name="v1",
            experiment_name="exp1",
            samples=[
                {"question_id": "q1", "question": "Q1?", "answer": "A1"},
                {"question_id": "q2", "question": "Q2?", "answer": "A2"},
            ],
            total_questions=5,
            model_name="gpt-4",
        )

        pipeline = MagicMock()
        pipeline.query.return_value = {
            "answer": "A3",
            "contexts": ["c3"],
            "sources": ["s3"],
            "chunk_ids": [],
            "token_usage": None,
        }

        test_set = {
            "name": "test_set",
            "questions": [
                {"id": "q1", "question": "Q1?"},
                {"id": "q2", "question": "Q2?"},
                {"id": "q3", "question": "Q3?"},
            ],
        }

        samples = collect_rag_samples(
            pipeline=pipeline,
            test_set=test_set,
            checkpoint_dir=checkpoint_dir,
            variant_name="v1",
            experiment_name="exp1",
            model_name="gpt-4",
        )

        assert len(samples) == 3
        assert samples[0]["question_id"] == "q1"
        assert samples[0]["answer"] == "A1"
        assert samples[2]["question_id"] == "q3"
        assert samples[2]["answer"] == "A3"
        assert pipeline.query.call_count == 1
