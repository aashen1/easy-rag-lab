from __future__ import annotations

import json

import pytest
import yaml

from src.exceptions import ReuseError
from src.experiment_reuse import (
    CopyMigrateHandler,
    ExperimentFingerprint,
    IncrementalPlan,
    InPlaceReuseHandler,
    ReportReuseConfig,
    ReuseHistoryEntry,
    compute_experiment_fingerprint,
)


class TestReportReuseConfig:
    def test_default_config(self):
        config = ReportReuseConfig()
        assert config.mode == "none"
        assert config.target_dir is None
        assert config.source_dir is None
        assert config.backup_before_append is True
        assert not config.is_enabled()

    def test_in_place_config(self):
        config = ReportReuseConfig(mode="in_place", target_dir="/tmp/exp_001")
        assert config.is_enabled()
        assert config.is_in_place()
        assert not config.is_copy_migrate()

    def test_copy_migrate_config(self):
        config = ReportReuseConfig(mode="copy_migrate", source_dir="/tmp/exp_001")
        assert config.is_enabled()
        assert config.is_copy_migrate()
        assert not config.is_in_place()

    def test_to_dict_roundtrip(self):
        config = ReportReuseConfig(
            mode="in_place",
            target_dir="/tmp/exp_001",
            backup_before_append=False,
        )
        d = config.to_dict()
        restored = ReportReuseConfig.from_dict(d)
        assert restored.mode == config.mode
        assert restored.target_dir == config.target_dir
        assert restored.backup_before_append == config.backup_before_append

    def test_from_dict_none(self):
        config = ReportReuseConfig.from_dict(None)
        assert config.mode == "none"

    def test_validate_in_place_without_target(self):
        config = ReportReuseConfig(mode="in_place", target_dir=None)
        errors = config.validate()
        assert any("target_dir" in e for e in errors)

    def test_validate_copy_migrate_without_source(self):
        config = ReportReuseConfig(mode="copy_migrate", source_dir=None)
        errors = config.validate()
        assert any("source_dir" in e for e in errors)

    def test_validate_invalid_mode(self):
        config = ReportReuseConfig(mode="invalid")
        errors = config.validate()
        assert any("Invalid reuse mode" in e for e in errors)

    def test_validate_valid_in_place(self):
        config = ReportReuseConfig(mode="in_place", target_dir="/tmp/exp")
        errors = config.validate()
        assert len(errors) == 0


class TestExperimentFingerprint:
    def _make_fingerprint(self, **overrides) -> ExperimentFingerprint:
        defaults = {
            "meal_name": "meal_baseline",
            "chunker_config_hash": "abc12345",
            "embedding_config_hash": "def67890",
            "retrieval_method": "vector",
            "retrieval_top_k": 5,
            "reranker_enabled": False,
            "query_rewrite_enabled": False,
            "test_set_strategy": "factual",
            "test_set_count": 20,
        }
        defaults.update(overrides)
        return ExperimentFingerprint(**defaults)

    def test_matches_identical(self):
        fp1 = self._make_fingerprint()
        fp2 = self._make_fingerprint()
        assert fp1.matches(fp2)

    def test_matches_different_top_k(self):
        fp1 = self._make_fingerprint(retrieval_top_k=5)
        fp2 = self._make_fingerprint(retrieval_top_k=10)
        assert fp1.matches(fp2)

    def test_no_match_different_meal(self):
        fp1 = self._make_fingerprint(meal_name="meal_a")
        fp2 = self._make_fingerprint(meal_name="meal_b")
        assert not fp1.matches(fp2)

    def test_no_match_different_chunker(self):
        fp1 = self._make_fingerprint(chunker_config_hash="abc12345")
        fp2 = self._make_fingerprint(chunker_config_hash="xyz99999")
        assert not fp1.matches(fp2)

    def test_no_match_different_retrieval(self):
        fp1 = self._make_fingerprint(retrieval_method="vector")
        fp2 = self._make_fingerprint(retrieval_method="hybrid")
        assert not fp1.matches(fp2)

    def test_diff(self):
        fp1 = self._make_fingerprint(retrieval_top_k=5, reranker_enabled=False)
        fp2 = self._make_fingerprint(retrieval_top_k=10, reranker_enabled=True)
        diff = fp1.diff(fp2)
        assert "retrieval_top_k" in diff
        assert "reranker_enabled" in diff

    def test_compute_hash_deterministic(self):
        fp = self._make_fingerprint()
        assert fp.compute_hash() == fp.compute_hash()

    def test_to_dict_roundtrip(self):
        fp = self._make_fingerprint()
        d = fp.to_dict()
        restored = ExperimentFingerprint.from_dict(d)
        assert restored.meal_name == fp.meal_name
        assert restored.chunker_config_hash == fp.chunker_config_hash


class TestComputeExperimentFingerprint:
    def test_basic_fingerprint(self):
        config_snapshot = {
            "data": {"meal": "meal_baseline"},
            "chunker": {"strategy": "fixed", "chunk_size": 512},
            "embedding": {"model_name": "bge-large-zh"},
            "retrieval": {"method": "vector", "top_k": 5},
            "test_sets": [{"generation": {"strategy": "factual", "num_questions": 20}}],
        }
        manifest = {}
        fp = compute_experiment_fingerprint(config_snapshot, manifest)
        assert fp.meal_name == "meal_baseline"
        assert fp.retrieval_method == "vector"
        assert fp.retrieval_top_k == 5
        assert fp.test_set_strategy == "factual"
        assert fp.test_set_count == 20

    def test_empty_config(self):
        fp = compute_experiment_fingerprint({}, {})
        assert fp.meal_name == "unknown"
        assert fp.retrieval_method == "vector"
        assert fp.test_set_strategy == "unknown"


class TestReuseHistoryEntry:
    def test_to_dict_minimal(self):
        entry = ReuseHistoryEntry(timestamp="2026-05-01T12:00:00", action="append")
        d = entry.to_dict()
        assert d["timestamp"] == "2026-05-01T12:00:00"
        assert d["action"] == "append"
        assert "variant" not in d

    def test_to_dict_full(self):
        entry = ReuseHistoryEntry(
            timestamp="2026-05-01T12:00:00",
            action="append_variant",
            variant="new_reranker",
            backup_snapshot="/tmp/backup/20260501_120000",
            details={"key": "value"},
        )
        d = entry.to_dict()
        assert d["variant"] == "new_reranker"
        assert d["backup_snapshot"] == "/tmp/backup/20260501_120000"

    def test_from_dict_roundtrip(self):
        entry = ReuseHistoryEntry(
            timestamp="2026-05-01T12:00:00",
            action="append",
            variant="test",
        )
        d = entry.to_dict()
        restored = ReuseHistoryEntry.from_dict(d)
        assert restored.timestamp == entry.timestamp
        assert restored.action == entry.action
        assert restored.variant == entry.variant


class TestIncrementalPlan:
    def test_no_conflicts(self):
        plan = IncrementalPlan(
            to_run=[{"name": "v3"}],
            to_reuse=[{"name": "v1"}],
            to_confirm=[],
        )
        assert not plan.has_conflicts

    def test_has_conflicts(self):
        plan = IncrementalPlan(
            to_run=[],
            to_reuse=[],
            to_confirm=[{"name": "v1"}],
        )
        assert plan.has_conflicts


class TestInPlaceReuseHandler:
    @pytest.fixture()
    def experiment_dir(self, tmp_path):
        exp_dir = tmp_path / "exp_20260501_120000_test"
        exp_dir.mkdir()
        (exp_dir / "results").mkdir()
        (exp_dir / "test_sets").mkdir()

        manifest = {
            "experiment_id": "exp_20260501_120000_test",
            "name": "test",
            "description": "test experiment",
            "created_at": "2026-05-01T12:00:00",
            "status": "completed",
            "variants": ["baseline", "hybrid"],
            "completed_variants": ["baseline", "hybrid"],
            "variant_config_hashes": {
                "baseline": "abc123def456",
                "hybrid": "789xyz012345",
            },
            "test_sets": ["factual"],
        }
        with open(exp_dir / "manifest.json", "w", encoding="utf-8") as f:
            json.dump(manifest, f)

        with open(exp_dir / "config_snapshot.yaml", "w", encoding="utf-8") as f:
            yaml.dump({"data": {"meal": "test_meal"}}, f)

        with open(exp_dir / "meal_snapshot.json", "w", encoding="utf-8") as f:
            json.dump({"name": "test_meal"}, f)

        with open(exp_dir / "experiment_report.md", "w", encoding="utf-8") as f:
            f.write("# Test Report\n")

        baseline_result = {
            "variant_name": "baseline",
            "retrieval_metrics": {"avg_hit_rate": 0.8},
        }
        with open(exp_dir / "results" / "baseline.json", "w", encoding="utf-8") as f:
            json.dump(baseline_result, f)

        return exp_dir

    def test_validate_target_dir(self, experiment_dir):
        handler = InPlaceReuseHandler(target_dir=experiment_dir)
        manifest = handler.validate_target_dir()
        assert manifest["name"] == "test"

    def test_validate_target_dir_not_exists(self, tmp_path):
        handler = InPlaceReuseHandler(target_dir=tmp_path / "nonexistent")
        with pytest.raises(ReuseError, match="does not exist"):
            handler.validate_target_dir()

    def test_validate_target_dir_no_manifest(self, tmp_path):
        exp_dir = tmp_path / "exp_no_manifest"
        exp_dir.mkdir()
        handler = InPlaceReuseHandler(target_dir=exp_dir)
        with pytest.raises(ReuseError, match="no manifest.json"):
            handler.validate_target_dir()

    def test_create_full_snapshot(self, experiment_dir):
        handler = InPlaceReuseHandler(
            target_dir=experiment_dir, backup_before_append=True
        )
        snapshot_path = handler.create_full_snapshot()
        assert snapshot_path is not None
        assert snapshot_path.exists()
        assert (snapshot_path / "manifest.json").exists()
        assert (snapshot_path / "results" / "baseline.json").exists()
        assert (snapshot_path / "experiment_report.md").exists()

    def test_create_full_snapshot_disabled(self, experiment_dir):
        handler = InPlaceReuseHandler(
            target_dir=experiment_dir, backup_before_append=False
        )
        result = handler.create_full_snapshot()
        assert result is None

    def test_backup_root(self, experiment_dir):
        handler = InPlaceReuseHandler(target_dir=experiment_dir)
        assert (
            handler.backup_root
            == experiment_dir.parent / f"{experiment_dir.name}_backup"
        )

    def test_list_snapshots_empty(self, experiment_dir):
        handler = InPlaceReuseHandler(target_dir=experiment_dir)
        snapshots = handler.list_snapshots()
        assert len(snapshots) == 0

    def test_list_snapshots_after_create(self, experiment_dir):
        handler = InPlaceReuseHandler(
            target_dir=experiment_dir, backup_before_append=True
        )
        handler.create_full_snapshot()
        snapshots = handler.list_snapshots()
        assert len(snapshots) == 1
        assert "timestamp" in snapshots[0]

    def test_restore_snapshot(self, experiment_dir):
        handler = InPlaceReuseHandler(
            target_dir=experiment_dir, backup_before_append=True
        )
        snapshot_path = handler.create_full_snapshot()
        snapshot_timestamp = snapshot_path.name

        with open(experiment_dir / "manifest.json", "w", encoding="utf-8") as f:
            json.dump({"modified": True}, f)

        handler.restore_snapshot(snapshot_timestamp)

        with open(experiment_dir / "manifest.json", encoding="utf-8") as f:
            manifest = json.load(f)
        assert "name" in manifest

    def test_restore_snapshot_not_found(self, experiment_dir):
        handler = InPlaceReuseHandler(target_dir=experiment_dir)
        with pytest.raises(ReuseError, match="Snapshot not found"):
            handler.restore_snapshot("99999999_999999")

    def test_compute_incremental_updates_new_variant(self, experiment_dir):
        handler = InPlaceReuseHandler(target_dir=experiment_dir)
        manifest = handler.validate_target_dir()
        stored_hashes = manifest.get("variant_config_hashes", {})

        plan = handler.compute_incremental_updates(
            new_variants=[
                {"name": "baseline"},
                {"name": "hybrid"},
                {"name": "new_reranker"},
            ],
            manifest=manifest,
            stored_hashes=stored_hashes,
        )

        assert any(v.get("name") == "new_reranker" for v in plan.to_run)
        assert any(v.get("name") == "baseline" for v in plan.to_reuse)

    def test_compute_incremental_updates_hash_mismatch(self, experiment_dir):
        handler = InPlaceReuseHandler(target_dir=experiment_dir)
        manifest = handler.validate_target_dir()
        stored_hashes = {"baseline": "different_hash_value"}

        plan = handler.compute_incremental_updates(
            new_variants=[{"name": "baseline"}],
            manifest=manifest,
            stored_hashes=stored_hashes,
            compute_variant_hash_fn=lambda v: "new_hash_value",
        )

        assert len(plan.to_confirm) == 1
        assert plan.has_conflicts

    def test_record_reuse_history(self, experiment_dir):
        handler = InPlaceReuseHandler(target_dir=experiment_dir)
        handler.record_reuse_history(
            action="append_variant",
            variant="new_reranker",
            backup_snapshot="/tmp/backup/20260501",
        )

        with open(experiment_dir / "manifest.json", encoding="utf-8") as f:
            manifest = json.load(f)
        assert "reuse_history" in manifest
        assert len(manifest["reuse_history"]) == 1
        assert manifest["reuse_history"][0]["action"] == "append_variant"

    def test_append_variant_to_manifest(self, experiment_dir):
        handler = InPlaceReuseHandler(target_dir=experiment_dir)
        handler.append_variant_to_manifest("new_reranker", config_hash="newhash123")

        with open(experiment_dir / "manifest.json", encoding="utf-8") as f:
            manifest = json.load(f)
        assert "new_reranker" in manifest["variants"]
        assert manifest["variant_config_hashes"]["new_reranker"] == "newhash123"


class TestCopyMigrateHandler:
    @pytest.fixture()
    def source_experiment(self, tmp_path):
        src_dir = tmp_path / "exp_20260501_120000_source"
        src_dir.mkdir()
        (src_dir / "results").mkdir()
        (src_dir / "test_sets").mkdir()

        manifest = {
            "experiment_id": "exp_20260501_120000_source",
            "name": "source_experiment",
            "description": "Source for migration",
            "created_at": "2026-05-01T12:00:00",
            "status": "completed",
            "variants": ["baseline"],
            "completed_variants": ["baseline"],
            "variant_config_hashes": {"baseline": "abc123def456"},
            "test_sets": ["factual"],
        }
        with open(src_dir / "manifest.json", "w", encoding="utf-8") as f:
            json.dump(manifest, f)

        with open(src_dir / "config_snapshot.yaml", "w", encoding="utf-8") as f:
            yaml.dump({"data": {"meal": "test_meal"}}, f)

        with open(src_dir / "meal_snapshot.json", "w", encoding="utf-8") as f:
            json.dump({"name": "test_meal"}, f)

        baseline_result = {"variant_name": "baseline", "retrieval_metrics": {}}
        with open(src_dir / "results" / "baseline.json", "w", encoding="utf-8") as f:
            json.dump(baseline_result, f)

        return src_dir

    def test_validate_source_dir(self, source_experiment):
        target = source_experiment.parent / "exp_new"
        handler = CopyMigrateHandler(source_dir=source_experiment, exp_dir=target)
        manifest = handler.validate_source_dir()
        assert manifest["name"] == "source_experiment"

    def test_validate_source_dir_not_exists(self, tmp_path):
        handler = CopyMigrateHandler(
            source_dir=tmp_path / "nonexistent", exp_dir=tmp_path / "target"
        )
        with pytest.raises(ReuseError, match="does not exist"):
            handler.validate_source_dir()

    def test_copy_experiment(self, source_experiment, tmp_path):
        target = tmp_path / "exp_migrated"
        handler = CopyMigrateHandler(source_dir=source_experiment, exp_dir=target)
        handler.copy_experiment()
        assert target.exists()
        assert (target / "manifest.json").exists()
        assert (target / "results" / "baseline.json").exists()

    def test_copy_experiment_target_exists(self, source_experiment, tmp_path):
        target = tmp_path / "exp_migrated"
        target.mkdir()
        handler = CopyMigrateHandler(source_dir=source_experiment, exp_dir=target)
        with pytest.raises(ReuseError, match="already exists"):
            handler.copy_experiment()

    def test_update_identifiers(self, source_experiment, tmp_path):
        target = tmp_path / "exp_migrated"
        handler = CopyMigrateHandler(source_dir=source_experiment, exp_dir=target)
        handler.copy_experiment()
        handler.update_identifiers(
            new_experiment_id="exp_20260502_140000_migrated",
            source_exp_id="exp_20260501_120000_source",
        )

        with open(target / "manifest.json", encoding="utf-8") as f:
            manifest = json.load(f)
        assert manifest["experiment_id"] == "exp_20260502_140000_migrated"
        assert "migrated_from" in manifest
        assert (
            manifest["migrated_from"]["experiment_id"] == "exp_20260501_120000_source"
        )
        assert manifest["reuse_mode"] == "copy_migrate"

    def test_verify_migration(self, source_experiment, tmp_path):
        target = tmp_path / "exp_migrated"
        handler = CopyMigrateHandler(source_dir=source_experiment, exp_dir=target)
        handler.copy_experiment()
        assert handler.verify_migration()

    def test_verify_migration_missing_file(self, source_experiment, tmp_path):
        target = tmp_path / "exp_migrated"
        handler = CopyMigrateHandler(source_dir=source_experiment, exp_dir=target)
        handler.copy_experiment()
        (target / "meal_snapshot.json").unlink()
        with pytest.raises(ReuseError, match="Missing required file"):
            handler.verify_migration()

    def test_compute_fingerprint_diff(self, source_experiment, tmp_path):
        target = tmp_path / "exp_migrated"
        handler = CopyMigrateHandler(source_dir=source_experiment, exp_dir=target)

        fp1 = ExperimentFingerprint(
            meal_name="meal_a",
            chunker_config_hash="abc12345",
            embedding_config_hash="def67890",
            retrieval_method="vector",
            retrieval_top_k=5,
            reranker_enabled=False,
            query_rewrite_enabled=False,
            test_set_strategy="factual",
            test_set_count=20,
        )
        fp2 = ExperimentFingerprint(
            meal_name="meal_a",
            chunker_config_hash="abc12345",
            embedding_config_hash="def67890",
            retrieval_method="hybrid",
            retrieval_top_k=10,
            reranker_enabled=True,
            query_rewrite_enabled=False,
            test_set_strategy="factual",
            test_set_count=20,
        )

        diff = handler.compute_fingerprint_diff(fp1, fp2)
        assert "retrieval_method" in diff
        assert "retrieval_top_k" in diff
        assert "reranker_enabled" in diff
