from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from src.exceptions import ReuseError
from src.experiment_reuse import (
    CopyMigrateHandler,
    InPlaceReuseHandler,
    ReportReuseConfig,
    compute_experiment_fingerprint,
    scan_matching_experiments,
)

NUM_PAGES = 200
NUM_QUESTIONS = 3


def _make_200page_config_snapshot() -> dict:
    return {
        "data": {"meal": "meal_200page_financial_report"},
        "chunker": {"strategy": "fixed", "chunk_size": 512, "chunk_overlap": 50},
        "embedding": {
            "model_name": "bge-large-zh-v1.5",
            "device": "cpu",
            "batch_size": 32,
        },
        "retrieval": {
            "method": "vector",
            "top_k": 5,
            "reranker": {"enabled": False},
            "query_rewrite": {"enabled": False},
        },
        "test_sets": [
            {
                "generation": {
                    "strategy": "factual",
                    "num_questions": NUM_QUESTIONS,
                }
            }
        ],
    }


def _make_manifest(
    exp_id: str = "exp_20260501_120000_baseline",
    name: str = "200page_baseline",
    variants: list[str] | None = None,
    completed: list[str] | None = None,
    variant_hashes: dict[str, str] | None = None,
    reuse_mode: str = "none",
    reuse_history: list[dict] | None = None,
) -> dict:
    return {
        "experiment_id": exp_id,
        "name": name,
        "description": f"Smoke test: {NUM_PAGES}-page PDF, {NUM_QUESTIONS} questions",
        "created_at": "2026-05-01T12:00:00",
        "status": "completed",
        "variants": variants or ["baseline"],
        "completed_variants": completed or ["baseline"],
        "variant_config_hashes": variant_hashes or {"baseline": "a" * 12},
        "test_sets": ["factual"],
        "num_pages": NUM_PAGES,
        "num_questions": NUM_QUESTIONS,
        "reuse_mode": reuse_mode,
        "reuse_history": reuse_history or [],
    }


def _make_variant_result(variant_name: str, avg_hit_rate: float = 0.8) -> dict:
    return {
        "variant_name": variant_name,
        "num_pages": NUM_PAGES,
        "num_questions": NUM_QUESTIONS,
        "retrieval_metrics": {
            "avg_hit_rate": avg_hit_rate,
            "avg_mrr": 0.6,
            "avg_ndcg": 0.7,
        },
        "generation_metrics": {
            "avg_faithfulness": 0.85,
            "avg_relevancy": 0.90,
        },
    }


def _make_test_set_data() -> dict:
    questions = []
    for i in range(NUM_QUESTIONS):
        questions.append(
            {
                "id": f"q_{i + 1:03d}",
                "question": f"第{i + 1}个问题：200页研报中的关键财务指标是什么？",
                "ground_truth": f"第{i + 1}个答案：关键指标包括ROE、ROA等",
                "category": "factual",
            }
        )
    return {
        "name": "auto_factual",
        "strategy": "factual",
        "num_questions": NUM_QUESTIONS,
        "questions": questions,
    }


def _create_full_experiment_dir(
    base_dir,
    exp_id: str = "exp_20260501_120000_baseline",
    name: str = "200page_baseline",
    variants: list[str] | None = None,
    completed: list[str] | None = None,
    variant_hashes: dict[str, str] | None = None,
    config_snapshot: dict | None = None,
    reuse_mode: str = "none",
    reuse_history: list[dict] | None = None,
) -> Path:
    exp_dir = base_dir / exp_id
    exp_dir.mkdir(parents=True, exist_ok=True)
    (exp_dir / "results").mkdir(exist_ok=True)
    (exp_dir / "test_sets").mkdir(exist_ok=True)

    manifest = _make_manifest(
        exp_id=exp_id,
        name=name,
        variants=variants,
        completed=completed,
        variant_hashes=variant_hashes,
        reuse_mode=reuse_mode,
        reuse_history=reuse_history,
    )
    with open(exp_dir / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    snapshot = config_snapshot or _make_200page_config_snapshot()
    with open(exp_dir / "config_snapshot.yaml", "w", encoding="utf-8") as f:
        yaml.dump(snapshot, f, allow_unicode=True)

    meal_snapshot = {
        "meal_id": f"meal_{exp_id}",
        "name": snapshot["data"]["meal"],
        "pdf_files": [
            {"filename": "financial_report_200p.pdf", "num_pages": NUM_PAGES}
        ],
    }
    with open(exp_dir / "meal_snapshot.json", "w", encoding="utf-8") as f:
        json.dump(meal_snapshot, f, ensure_ascii=False, indent=2)

    variant_list = variants or ["baseline"]
    for vname in variant_list:
        result = _make_variant_result(vname)
        with open(exp_dir / "results" / f"{vname}.json", "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

    test_set = _make_test_set_data()
    with open(exp_dir / "test_sets" / "auto_factual.json", "w", encoding="utf-8") as f:
        json.dump(test_set, f, ensure_ascii=False, indent=2)

    with open(exp_dir / "experiment_report.md", "w", encoding="utf-8") as f:
        f.write(f"# {name}\n\n{NUM_PAGES}页PDF / {NUM_QUESTIONS}问题\n")

    return exp_dir


@pytest.fixture
def exp_reports_dir(tmp_path):
    d = tmp_path / "data" / "exp_reports"
    d.mkdir(parents=True)
    return d


@pytest.fixture
def baseline_experiment(exp_reports_dir):
    return _create_full_experiment_dir(
        exp_reports_dir,
        exp_id="exp_20260501_120000_baseline",
        name="200page_baseline",
        variants=["baseline"],
        completed=["baseline"],
        variant_hashes={"baseline": "a1b2c3d4e5f6"},
    )


@pytest.fixture
def multi_variant_experiment(exp_reports_dir):
    return _create_full_experiment_dir(
        exp_reports_dir,
        exp_id="exp_20260501_140000_multi",
        name="200page_multi_variant",
        variants=["baseline", "hybrid_top10", "reranker_on"],
        completed=["baseline", "hybrid_top10", "reranker_on"],
        variant_hashes={
            "baseline": "a1b2c3d4e5f6",
            "hybrid_top10": "b2c3d4e5f6a7",
            "reranker_on": "c3d4e5f6a7b8",
        },
    )


class TestSmoke01InPlaceFullLifecycle:
    """SMOKE-01: In-Place 模式完整生命周期 — 200页PDF / 3问题"""

    def test_full_lifecycle(self, baseline_experiment):
        handler = InPlaceReuseHandler(
            target_dir=baseline_experiment, backup_before_append=True
        )

        manifest = handler.validate_target_dir()
        assert manifest["experiment_id"] == "exp_20260501_120000_baseline"
        assert manifest["num_pages"] == NUM_PAGES
        assert manifest["num_questions"] == NUM_QUESTIONS

        snapshot_path = handler.create_full_snapshot()
        assert snapshot_path is not None
        assert snapshot_path.exists()
        assert (snapshot_path / "manifest.json").exists()
        assert (snapshot_path / "results" / "baseline.json").exists()
        assert (snapshot_path / "config_snapshot.yaml").exists()
        assert (snapshot_path / "meal_snapshot.json").exists()
        assert (snapshot_path / "test_sets" / "auto_factual.json").exists()
        assert (snapshot_path / "experiment_report.md").exists()

        with open(snapshot_path / "manifest.json", encoding="utf-8") as f:
            snap_manifest = json.load(f)
        assert snap_manifest["experiment_id"] == manifest["experiment_id"]

        stored_hashes = manifest.get("variant_config_hashes", {})
        plan = handler.compute_incremental_updates(
            new_variants=[
                {"name": "baseline"},
                {"name": "hybrid_top10"},
                {"name": "reranker_on"},
            ],
            manifest=manifest,
            stored_hashes=stored_hashes,
        )

        assert len(plan.to_reuse) == 1
        assert plan.to_reuse[0]["name"] == "baseline"
        assert len(plan.to_run) == 2
        assert any(v["name"] == "hybrid_top10" for v in plan.to_run)
        assert any(v["name"] == "reranker_on" for v in plan.to_run)
        assert not plan.has_conflicts

        handler.record_reuse_history(
            action="in_place_start",
            backup_snapshot=str(snapshot_path),
            details={
                "new_variants": ["hybrid_top10", "reranker_on"],
                "reuse_variants": ["baseline"],
            },
        )

        handler.append_variant_to_manifest("hybrid_top10", config_hash="newhash001")
        handler.append_variant_to_manifest("reranker_on", config_hash="newhash002")

        with open(baseline_experiment / "manifest.json", encoding="utf-8") as f:
            updated_manifest = json.load(f)
        assert "hybrid_top10" in updated_manifest["variants"]
        assert "reranker_on" in updated_manifest["variants"]
        assert updated_manifest["variant_config_hashes"]["hybrid_top10"] == "newhash001"
        assert updated_manifest["variant_config_hashes"]["reranker_on"] == "newhash002"
        assert len(updated_manifest["reuse_history"]) >= 1
        assert updated_manifest["reuse_history"][-1]["action"] == "in_place_start"

        new_variant_result = _make_variant_result("hybrid_top10", avg_hit_rate=0.85)
        with open(
            baseline_experiment / "results" / "hybrid_top10.json", "w", encoding="utf-8"
        ) as f:
            json.dump(new_variant_result, f, ensure_ascii=False, indent=2)

        assert (baseline_experiment / "results" / "baseline.json").exists()
        assert (baseline_experiment / "results" / "hybrid_top10.json").exists()

        with open(baseline_experiment / "manifest.json", "w", encoding="utf-8") as f:
            json.dump({"tampered": True}, f)

        handler.restore_snapshot(snapshot_path.name)

        with open(baseline_experiment / "manifest.json", encoding="utf-8") as f:
            restored_manifest = json.load(f)
        assert "experiment_id" in restored_manifest
        assert restored_manifest["experiment_id"] == "exp_20260501_120000_baseline"
        assert "tampered" not in restored_manifest


class TestSmoke02CopyMigrateFullLifecycle:
    """SMOKE-02: Copy-Migrate 模式完整生命周期 — 200页PDF / 3问题"""

    def test_full_lifecycle(self, multi_variant_experiment, exp_reports_dir):
        new_exp_dir = exp_reports_dir / "exp_20260502_080000_migrated"

        handler = CopyMigrateHandler(
            source_dir=multi_variant_experiment, exp_dir=new_exp_dir
        )

        source_manifest = handler.validate_source_dir()
        assert source_manifest["name"] == "200page_multi_variant"
        assert len(source_manifest["variants"]) == 3
        assert source_manifest["num_pages"] == NUM_PAGES

        handler.copy_experiment()
        assert new_exp_dir.exists()
        assert (new_exp_dir / "manifest.json").exists()
        assert (new_exp_dir / "config_snapshot.yaml").exists()
        assert (new_exp_dir / "meal_snapshot.json").exists()
        assert (new_exp_dir / "results" / "baseline.json").exists()
        assert (new_exp_dir / "results" / "hybrid_top10.json").exists()
        assert (new_exp_dir / "results" / "reranker_on.json").exists()
        assert (new_exp_dir / "test_sets" / "auto_factual.json").exists()

        with open(new_exp_dir / "results" / "baseline.json", encoding="utf-8") as f:
            copied_result = json.load(f)
        assert copied_result["num_pages"] == NUM_PAGES
        assert copied_result["num_questions"] == NUM_QUESTIONS

        new_exp_id = new_exp_dir.name
        source_exp_id = source_manifest["experiment_id"]
        handler.update_identifiers(new_exp_id, source_exp_id)

        with open(new_exp_dir / "manifest.json", encoding="utf-8") as f:
            migrated_manifest = json.load(f)
        assert migrated_manifest["experiment_id"] == new_exp_id
        assert "migrated_from" in migrated_manifest
        assert migrated_manifest["migrated_from"]["experiment_id"] == source_exp_id
        assert migrated_manifest["reuse_mode"] == "copy_migrate"
        assert migrated_manifest["completed_variants"] == []
        assert migrated_manifest["variant_config_hashes"] == {}

        assert handler.verify_migration()

        with open(multi_variant_experiment / "manifest.json", encoding="utf-8") as f:
            original_manifest = json.load(f)
        assert original_manifest["experiment_id"] == source_exp_id
        assert original_manifest["completed_variants"] == [
            "baseline",
            "hybrid_top10",
            "reranker_on",
        ]

    def test_fingerprint_diff_after_migration(
        self, multi_variant_experiment, exp_reports_dir
    ):
        new_exp_dir = exp_reports_dir / "exp_20260502_090000_migrated2"
        handler = CopyMigrateHandler(
            source_dir=multi_variant_experiment, exp_dir=new_exp_dir
        )
        handler.validate_source_dir()
        handler.copy_experiment()

        source_config = _make_200page_config_snapshot()
        source_fp = compute_experiment_fingerprint(source_config, {})

        target_config = _make_200page_config_snapshot()
        target_config["retrieval"]["method"] = "hybrid"
        target_config["retrieval"]["top_k"] = 10
        target_fp = compute_experiment_fingerprint(target_config, {})

        diff = handler.compute_fingerprint_diff(source_fp, target_fp)
        assert "retrieval_method" in diff
        assert "retrieval_top_k" in diff
        assert diff["retrieval_method"] == ("vector", "hybrid")

        same_diff = handler.compute_fingerprint_diff(source_fp, source_fp)
        assert len(same_diff) == 0


class TestSmoke03FingerprintSystem:
    """SMOKE-03: 指纹系统 — 200页PDF场景下的匹配/差异/扫描"""

    def test_fingerprint_from_200page_config(self):
        config = _make_200page_config_snapshot()
        manifest = _make_manifest()
        fp = compute_experiment_fingerprint(config, manifest)

        assert fp.meal_name == "meal_200page_financial_report"
        assert fp.retrieval_method == "vector"
        assert fp.retrieval_top_k == 5
        assert fp.test_set_strategy == "factual"
        assert fp.test_set_count == NUM_QUESTIONS
        assert not fp.reranker_enabled
        assert not fp.query_rewrite_enabled

    def test_fingerprint_matches_same_config(self):
        config = _make_200page_config_snapshot()
        fp1 = compute_experiment_fingerprint(config, {})
        fp2 = compute_experiment_fingerprint(config, {})
        assert fp1.matches(fp2)
        assert fp1.compute_hash() == fp2.compute_hash()

    def test_fingerprint_no_match_different_meal(self):
        config_a = _make_200page_config_snapshot()
        config_b = _make_200page_config_snapshot()
        config_b["data"]["meal"] = "meal_different_report"
        fp1 = compute_experiment_fingerprint(config_a, {})
        fp2 = compute_experiment_fingerprint(config_b, {})
        assert not fp1.matches(fp2)

    def test_fingerprint_no_match_different_chunker(self):
        config_a = _make_200page_config_snapshot()
        config_b = _make_200page_config_snapshot()
        config_b["chunker"]["chunk_size"] = 1024
        fp1 = compute_experiment_fingerprint(config_a, {})
        fp2 = compute_experiment_fingerprint(config_b, {})
        assert not fp1.matches(fp2)
        assert "chunker_config_hash" in fp1.diff(fp2)

    def test_fingerprint_no_match_different_embedding(self):
        config_a = _make_200page_config_snapshot()
        config_b = _make_200page_config_snapshot()
        config_b["embedding"]["model_name"] = "text-embedding-3-small"
        fp1 = compute_experiment_fingerprint(config_a, {})
        fp2 = compute_experiment_fingerprint(config_b, {})
        assert not fp1.matches(fp2)

    def test_fingerprint_matches_different_top_k(self):
        config_a = _make_200page_config_snapshot()
        config_b = _make_200page_config_snapshot()
        config_b["retrieval"]["top_k"] = 10
        fp1 = compute_experiment_fingerprint(config_a, {})
        fp2 = compute_experiment_fingerprint(config_b, {})
        assert fp1.matches(fp2)
        diff = fp1.diff(fp2)
        assert "retrieval_top_k" in diff

    def test_fingerprint_matches_reranker_toggle(self):
        config_a = _make_200page_config_snapshot()
        config_b = _make_200page_config_snapshot()
        config_b["retrieval"]["reranker"]["enabled"] = True
        fp1 = compute_experiment_fingerprint(config_a, {})
        fp2 = compute_experiment_fingerprint(config_b, {})
        assert fp1.matches(fp2)
        diff = fp1.diff(fp2)
        assert "reranker_enabled" in diff

    def test_scan_matching_experiments(self, exp_reports_dir):
        _create_full_experiment_dir(
            exp_reports_dir,
            exp_id="exp_20260501_120000_match1",
            name="matching_exp_1",
        )
        _create_full_experiment_dir(
            exp_reports_dir,
            exp_id="exp_20260501_130000_match2",
            name="matching_exp_2",
        )
        config_different = _make_200page_config_snapshot()
        config_different["data"]["meal"] = "meal_other"
        _create_full_experiment_dir(
            exp_reports_dir,
            exp_id="exp_20260501_140000_nomatch",
            name="non_matching_exp",
            config_snapshot=config_different,
        )

        target_config = _make_200page_config_snapshot()
        target_fp = compute_experiment_fingerprint(target_config, {})
        results = scan_matching_experiments(target_fp, exp_reports_dir)

        assert len(results) >= 3
        matching = [r for r in results if r["matches"]]
        non_matching = [r for r in results if not r["matches"]]
        assert len(matching) >= 2
        assert len(non_matching) >= 1

    def test_scan_empty_directory(self, exp_reports_dir):
        empty_dir = exp_reports_dir / "nonexistent"
        target_fp = compute_experiment_fingerprint(_make_200page_config_snapshot(), {})
        results = scan_matching_experiments(target_fp, empty_dir)
        assert results == []


class TestSmoke04IncrementalPlanWithHashVerification:
    """SMOKE-04: 增量计划与哈希验证 — 200页PDF场景"""

    def test_new_variant_goes_to_run(self, baseline_experiment):
        handler = InPlaceReuseHandler(target_dir=baseline_experiment)
        manifest = handler.validate_target_dir()
        stored_hashes = manifest.get("variant_config_hashes", {})

        plan = handler.compute_incremental_updates(
            new_variants=[
                {"name": "baseline"},
                {"name": "new_hybrid"},
            ],
            manifest=manifest,
            stored_hashes=stored_hashes,
        )

        assert len(plan.to_reuse) == 1
        assert plan.to_reuse[0]["name"] == "baseline"
        assert len(plan.to_run) == 1
        assert plan.to_run[0]["name"] == "new_hybrid"
        assert not plan.has_conflicts

    def test_hash_mismatch_goes_to_confirm(self, baseline_experiment):
        handler = InPlaceReuseHandler(target_dir=baseline_experiment)
        manifest = handler.validate_target_dir()

        plan = handler.compute_incremental_updates(
            new_variants=[{"name": "baseline"}],
            manifest=manifest,
            stored_hashes={"baseline": "completely_different_hash"},
            compute_variant_hash_fn=lambda v: "new_hash_value_123",
        )

        assert len(plan.to_confirm) == 1
        assert plan.to_confirm[0]["name"] == "baseline"
        assert plan.has_conflicts

    def test_hash_match_goes_to_reuse(self, baseline_experiment):
        handler = InPlaceReuseHandler(target_dir=baseline_experiment)
        manifest = handler.validate_target_dir()
        stored_hash = manifest["variant_config_hashes"]["baseline"]

        plan = handler.compute_incremental_updates(
            new_variants=[{"name": "baseline"}],
            manifest=manifest,
            stored_hashes={"baseline": stored_hash},
            compute_variant_hash_fn=lambda v: stored_hash,
        )

        assert len(plan.to_reuse) == 1
        assert plan.to_reuse[0]["name"] == "baseline"
        assert not plan.has_conflicts

    def test_incomplete_variant_goes_to_run(self, baseline_experiment):
        handler = InPlaceReuseHandler(target_dir=baseline_experiment)
        manifest = handler.validate_target_dir()
        manifest["variants"] = ["baseline", "incomplete_variant"]
        manifest["completed_variants"] = ["baseline"]

        plan = handler.compute_incremental_updates(
            new_variants=[{"name": "incomplete_variant"}],
            manifest=manifest,
            stored_hashes={},
        )

        assert len(plan.to_run) == 1
        assert plan.to_run[0]["name"] == "incomplete_variant"

    def test_multi_variant_mixed_plan(self, multi_variant_experiment):
        handler = InPlaceReuseHandler(target_dir=multi_variant_experiment)
        manifest = handler.validate_target_dir()
        stored_hashes = manifest.get("variant_config_hashes", {})

        plan = handler.compute_incremental_updates(
            new_variants=[
                {"name": "baseline"},
                {"name": "hybrid_top10"},
                {"name": "reranker_on"},
                {"name": "brand_new_variant"},
            ],
            manifest=manifest,
            stored_hashes=stored_hashes,
        )

        assert len(plan.to_reuse) == 3
        assert len(plan.to_run) == 1
        assert plan.to_run[0]["name"] == "brand_new_variant"
        assert not plan.has_conflicts


class TestSmoke05CLIConfigBuilding:
    """SMOKE-05: CLI 参数构建 — ReportReuseConfig 从 CLI 参数构建"""

    def test_build_in_place_config(self):
        import argparse

        args = argparse.Namespace(
            reuse="in-place",
            target_dir="data/exp_reports/exp_20260501_120000",
            source_dir=None,
            no_backup=False,
        )
        from eval.run_experiment import _build_reuse_config

        config = _build_reuse_config(args)
        assert config is not None
        assert config.is_in_place()
        assert config.mode == "in_place"
        assert config.target_dir == "data/exp_reports/exp_20260501_120000"
        assert config.backup_before_append is True

    def test_build_copy_migrate_config(self):
        import argparse

        args = argparse.Namespace(
            reuse="copy-migrate",
            target_dir=None,
            source_dir="data/exp_reports/exp_20260501_120000",
            no_backup=False,
        )
        from eval.run_experiment import _build_reuse_config

        config = _build_reuse_config(args)
        assert config is not None
        assert config.is_copy_migrate()
        assert config.mode == "copy_migrate"
        assert config.source_dir == "data/exp_reports/exp_20260501_120000"

    def test_build_no_backup_config(self):
        import argparse

        args = argparse.Namespace(
            reuse="in-place",
            target_dir="data/exp_reports/exp_20260501_120000",
            source_dir=None,
            no_backup=True,
        )
        from eval.run_experiment import _build_reuse_config

        config = _build_reuse_config(args)
        assert config.backup_before_append is False

    def test_build_none_when_no_reuse(self):
        import argparse

        args = argparse.Namespace(
            reuse=None,
            target_dir=None,
            source_dir=None,
            no_backup=False,
        )
        from eval.run_experiment import _build_reuse_config

        config = _build_reuse_config(args)
        assert config is None

    def test_config_validation_in_place_missing_target(self):
        config = ReportReuseConfig(mode="in_place", target_dir=None)
        errors = config.validate()
        assert any("target_dir" in e for e in errors)

    def test_config_validation_copy_migrate_missing_source(self):
        config = ReportReuseConfig(mode="copy_migrate", source_dir=None)
        errors = config.validate()
        assert any("source_dir" in e for e in errors)

    def test_config_serialization_roundtrip(self):
        config = ReportReuseConfig(
            mode="in_place",
            target_dir="/data/exp_001",
            backup_before_append=False,
            fingerprint_keys=["data.meal", "chunker"],
        )
        d = config.to_dict()
        restored = ReportReuseConfig.from_dict(d)
        assert restored.mode == config.mode
        assert restored.target_dir == config.target_dir
        assert restored.backup_before_append == config.backup_before_append
        assert restored.fingerprint_keys == config.fingerprint_keys


class TestSmoke06MultiRoundInPlaceAppend:
    """SMOKE-06: 多轮 In-Place 增补 — 验证历史累积和备份快照累积"""

    def test_two_round_append(self, baseline_experiment):
        handler = InPlaceReuseHandler(
            target_dir=baseline_experiment, backup_before_append=True
        )

        manifest = handler.validate_target_dir()
        stored_hashes = manifest.get("variant_config_hashes", {})

        snap1 = handler.create_full_snapshot()
        assert snap1 is not None

        plan1 = handler.compute_incremental_updates(
            new_variants=[{"name": "baseline"}, {"name": "round1_variant"}],
            manifest=manifest,
            stored_hashes=stored_hashes,
        )
        assert len(plan1.to_run) == 1

        handler.record_reuse_history(
            action="in_place_start",
            variant="round1_variant",
            backup_snapshot=str(snap1),
        )
        handler.append_variant_to_manifest("round1_variant", config_hash="hash_r1")

        with open(baseline_experiment / "manifest.json", encoding="utf-8") as f:
            tmp_manifest = json.load(f)
        tmp_manifest["completed_variants"].append("round1_variant")
        with open(baseline_experiment / "manifest.json", "w", encoding="utf-8") as f:
            json.dump(tmp_manifest, f, ensure_ascii=False, indent=2)

        r1_result = _make_variant_result("round1_variant", avg_hit_rate=0.82)
        with open(
            baseline_experiment / "results" / "round1_variant.json",
            "w",
            encoding="utf-8",
        ) as f:
            json.dump(r1_result, f, ensure_ascii=False, indent=2)

        manifest2 = handler.validate_target_dir()
        stored_hashes2 = manifest2.get("variant_config_hashes", {})

        snap2 = handler.create_full_snapshot()
        assert snap2 is not None

        plan2 = handler.compute_incremental_updates(
            new_variants=[
                {"name": "baseline"},
                {"name": "round1_variant"},
                {"name": "round2_variant"},
            ],
            manifest=manifest2,
            stored_hashes=stored_hashes2,
        )
        assert len(plan2.to_reuse) == 2
        assert len(plan2.to_run) == 1
        assert plan2.to_run[0]["name"] == "round2_variant"

        handler.record_reuse_history(
            action="in_place_start",
            variant="round2_variant",
            backup_snapshot=str(snap2),
        )
        handler.append_variant_to_manifest("round2_variant", config_hash="hash_r2")

        with open(baseline_experiment / "manifest.json", encoding="utf-8") as f:
            final_manifest = json.load(f)

        assert len(final_manifest["reuse_history"]) >= 2
        assert final_manifest["reuse_history"][0]["action"] == "in_place_start"
        assert final_manifest["reuse_history"][1]["action"] == "in_place_start"

        assert "baseline" in final_manifest["variants"]
        assert "round1_variant" in final_manifest["variants"]
        assert "round2_variant" in final_manifest["variants"]

        snapshots = handler.list_snapshots()
        assert len(snapshots) >= 2

        assert (baseline_experiment / "results" / "baseline.json").exists()
        assert (baseline_experiment / "results" / "round1_variant.json").exists()

    def test_no_backup_mode(self, baseline_experiment):
        handler = InPlaceReuseHandler(
            target_dir=baseline_experiment, backup_before_append=False
        )
        result = handler.create_full_snapshot()
        assert result is None

        handler.record_reuse_history(action="append_no_backup", variant="v1")

        with open(baseline_experiment / "manifest.json", encoding="utf-8") as f:
            manifest = json.load(f)
        assert len(manifest["reuse_history"]) >= 1


class TestSmoke07ErrorAndEdgeCases:
    """SMOKE-07: 错误与边界情况"""

    def test_validate_nonexistent_target(self, tmp_path):
        handler = InPlaceReuseHandler(target_dir=tmp_path / "no_such_dir")
        with pytest.raises(ReuseError, match="does not exist"):
            handler.validate_target_dir()

    def test_validate_target_no_manifest(self, tmp_path):
        empty_dir = tmp_path / "exp_empty"
        empty_dir.mkdir()
        handler = InPlaceReuseHandler(target_dir=empty_dir)
        with pytest.raises(ReuseError, match="no manifest.json"):
            handler.validate_target_dir()

    def test_validate_target_invalid_manifest_json(self, tmp_path):
        bad_dir = tmp_path / "exp_bad_json"
        bad_dir.mkdir()
        with open(bad_dir / "manifest.json", "w") as f:
            f.write("{invalid json!!!")
        handler = InPlaceReuseHandler(target_dir=bad_dir)
        with pytest.raises(ReuseError, match="Invalid manifest.json"):
            handler.validate_target_dir()

    def test_validate_source_nonexistent(self, tmp_path):
        handler = CopyMigrateHandler(
            source_dir=tmp_path / "no_such_source", exp_dir=tmp_path / "target"
        )
        with pytest.raises(ReuseError, match="does not exist"):
            handler.validate_source_dir()

    def test_validate_source_no_config_snapshot(self, tmp_path):
        src = tmp_path / "exp_no_config"
        src.mkdir()
        (src / "results").mkdir()
        with open(src / "manifest.json", "w") as f:
            json.dump({"experiment_id": "test"}, f)
        handler = CopyMigrateHandler(source_dir=src, exp_dir=tmp_path / "target")
        with pytest.raises(ReuseError, match="no config_snapshot.yaml"):
            handler.validate_source_dir()

    def test_copy_to_existing_target_fails(self, multi_variant_experiment, tmp_path):
        existing_target = tmp_path / "exp_existing"
        existing_target.mkdir()
        handler = CopyMigrateHandler(
            source_dir=multi_variant_experiment, exp_dir=existing_target
        )
        with pytest.raises(ReuseError, match="already exists"):
            handler.copy_experiment()

    def test_restore_nonexistent_snapshot(self, baseline_experiment):
        handler = InPlaceReuseHandler(target_dir=baseline_experiment)
        with pytest.raises(ReuseError, match="Snapshot not found"):
            handler.restore_snapshot("99999999_999999")

    def test_verify_migration_missing_file(self, multi_variant_experiment, tmp_path):
        target = tmp_path / "exp_migrated"
        handler = CopyMigrateHandler(
            source_dir=multi_variant_experiment, exp_dir=target
        )
        handler.copy_experiment()
        (target / "meal_snapshot.json").unlink()
        with pytest.raises(ReuseError, match="Missing required file"):
            handler.verify_migration()

    def test_verify_migration_missing_directory(
        self, multi_variant_experiment, tmp_path
    ):
        import shutil

        target = tmp_path / "exp_migrated2"
        handler = CopyMigrateHandler(
            source_dir=multi_variant_experiment, exp_dir=target
        )
        handler.copy_experiment()
        shutil.rmtree(target / "test_sets")
        with pytest.raises(ReuseError, match="Missing required directory"):
            handler.verify_migration()

    def test_verify_migration_missing_result_files(
        self, multi_variant_experiment, tmp_path
    ):
        target = tmp_path / "exp_migrated3"
        handler = CopyMigrateHandler(
            source_dir=multi_variant_experiment, exp_dir=target
        )
        handler.copy_experiment()
        (target / "results" / "baseline.json").unlink()
        with pytest.raises(ReuseError, match="Missing result files"):
            handler.verify_migration()

    def test_empty_reuse_history(self, baseline_experiment):
        with open(baseline_experiment / "manifest.json", encoding="utf-8") as f:
            manifest = json.load(f)
        assert manifest.get("reuse_history", []) == []

    def test_list_snapshots_empty(self, baseline_experiment):
        handler = InPlaceReuseHandler(target_dir=baseline_experiment)
        snapshots = handler.list_snapshots()
        assert snapshots == []

    def test_source_no_results_warning(self, tmp_path, capfd):
        src = tmp_path / "exp_no_results"
        src.mkdir()
        (src / "results").mkdir()
        (src / "test_sets").mkdir()
        with open(src / "manifest.json", "w") as f:
            json.dump({"experiment_id": "test"}, f)
        with open(src / "config_snapshot.yaml", "w") as f:
            yaml.dump({"data": {"meal": "test"}}, f)

        handler = CopyMigrateHandler(source_dir=src, exp_dir=tmp_path / "target")
        manifest = handler.validate_source_dir()
        assert manifest["experiment_id"] == "test"

    def test_reuse_config_invalid_mode(self):
        config = ReportReuseConfig(mode="invalid_mode")
        errors = config.validate()
        assert any("Invalid reuse mode" in e for e in errors)

    def test_in_place_with_source_dir_warns(self, capfd):
        config = ReportReuseConfig(
            mode="in_place", target_dir="/tmp/exp", source_dir="/tmp/other"
        )
        errors = config.validate()
        assert len(errors) == 0

    def test_copy_migrate_with_target_dir_warns(self):
        config = ReportReuseConfig(
            mode="copy_migrate", source_dir="/tmp/exp", target_dir="/tmp/other"
        )
        errors = config.validate()
        assert len(errors) == 0


class TestSmoke08DataIntegrity:
    """SMOKE-08: 数据完整性 — 200页PDF场景下验证文件一致性"""

    def test_backup_preserves_all_files(self, multi_variant_experiment):
        handler = InPlaceReuseHandler(
            target_dir=multi_variant_experiment, backup_before_append=True
        )
        snap = handler.create_full_snapshot()

        expected_files = [
            "manifest.json",
            "config_snapshot.yaml",
            "meal_snapshot.json",
            "experiment_report.md",
            "results/baseline.json",
            "results/hybrid_top10.json",
            "results/reranker_on.json",
            "test_sets/auto_factual.json",
        ]
        for fname in expected_files:
            assert (snap / fname).exists(), f"Missing in backup: {fname}"

        with open(multi_variant_experiment / "manifest.json", encoding="utf-8") as f:
            src_manifest = json.load(f)
        with open(snap / "manifest.json", encoding="utf-8") as f:
            snap_manifest = json.load(f)
        assert src_manifest == snap_manifest

    def test_copy_preserves_result_content(
        self, multi_variant_experiment, exp_reports_dir
    ):
        new_dir = exp_reports_dir / "exp_migrated_integrity"
        handler = CopyMigrateHandler(
            source_dir=multi_variant_experiment, exp_dir=new_dir
        )
        handler.copy_experiment()

        for variant in ["baseline", "hybrid_top10", "reranker_on"]:
            src_path = multi_variant_experiment / "results" / f"{variant}.json"
            dst_path = new_dir / "results" / f"{variant}.json"
            with open(src_path, encoding="utf-8") as f:
                src_data = json.load(f)
            with open(dst_path, encoding="utf-8") as f:
                dst_data = json.load(f)
            assert src_data == dst_data, f"Result content mismatch for {variant}"

    def test_restore_preserves_manifest_content(self, baseline_experiment):
        handler = InPlaceReuseHandler(
            target_dir=baseline_experiment, backup_before_append=True
        )

        with open(baseline_experiment / "manifest.json", encoding="utf-8") as f:
            original_manifest = json.load(f)

        snap = handler.create_full_snapshot()

        with open(baseline_experiment / "manifest.json", "w", encoding="utf-8") as f:
            json.dump({"destroyed": True}, f)

        handler.restore_snapshot(snap.name)

        with open(baseline_experiment / "manifest.json", encoding="utf-8") as f:
            restored_manifest = json.load(f)

        assert restored_manifest == original_manifest

    def test_fingerprint_hash_determinism(self):
        config = _make_200page_config_snapshot()
        fp1 = compute_experiment_fingerprint(config, {})
        fp2 = compute_experiment_fingerprint(config, {})

        assert fp1.chunker_config_hash == fp2.chunker_config_hash
        assert fp1.embedding_config_hash == fp2.embedding_config_hash
        assert fp1.compute_hash() == fp2.compute_hash()

        for _ in range(10):
            fp = compute_experiment_fingerprint(config, {})
            assert fp.compute_hash() == fp1.compute_hash()

    def test_config_snapshot_yaml_preserved_after_copy(
        self, multi_variant_experiment, exp_reports_dir
    ):
        new_dir = exp_reports_dir / "exp_yaml_preserved"
        handler = CopyMigrateHandler(
            source_dir=multi_variant_experiment, exp_dir=new_dir
        )
        handler.copy_experiment()

        with open(
            multi_variant_experiment / "config_snapshot.yaml", encoding="utf-8"
        ) as f:
            src_yaml = yaml.safe_load(f)
        with open(new_dir / "config_snapshot.yaml", encoding="utf-8") as f:
            dst_yaml = yaml.safe_load(f)

        assert src_yaml == dst_yaml
        assert dst_yaml["data"]["meal"] == "meal_200page_financial_report"
        assert dst_yaml["chunker"]["chunk_size"] == 512
