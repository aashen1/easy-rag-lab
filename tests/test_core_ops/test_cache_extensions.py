from __future__ import annotations

import json
from unittest.mock import patch

import pytest


class TestArtifactCacheUpdateManifestEntry:
    def test_update_existing_key(self, tmp_path):
        from src.meal.cache import ArtifactCache

        cache = ArtifactCache(artifacts_dir=tmp_path, raw_dir=tmp_path)

        data_id = "test_data_12345678"
        short_id = data_id[:16]
        manifest_dir = tmp_path / short_id
        manifest_dir.mkdir(parents=True)
        manifest_file = manifest_dir / "manifest.json"
        manifest_file.write_text(
            json.dumps({"description": "old", "tags": ["old_tag"]}),
            encoding="utf-8",
        )

        result = cache.update_manifest_entry(data_id, "description", "new description")

        assert result is True
        updated = json.loads(manifest_file.read_text(encoding="utf-8"))
        assert updated["description"] == "new description"
        assert updated["tags"] == ["old_tag"]

    def test_update_nonexistent_manifest_returns_false(self, tmp_path):
        from src.meal.cache import ArtifactCache

        cache = ArtifactCache(artifacts_dir=tmp_path, raw_dir=tmp_path)

        result = cache.update_manifest_entry("nonexistent", "key", "value")
        assert result is False

    def test_empty_data_id_raises(self, tmp_path):
        from src.meal.cache import ArtifactCache

        cache = ArtifactCache(artifacts_dir=tmp_path, raw_dir=tmp_path)

        with pytest.raises(ValueError, match="data_id must not be empty"):
            cache.update_manifest_entry("", "key", "value")

    def test_empty_key_raises(self, tmp_path):
        from src.meal.cache import ArtifactCache

        cache = ArtifactCache(artifacts_dir=tmp_path, raw_dir=tmp_path)

        with pytest.raises(ValueError, match="key must not be empty"):
            cache.update_manifest_entry("data_id", "", "value")

    def test_save_failure_rolls_back(self, tmp_path):
        from src.meal.cache import ArtifactCache

        cache = ArtifactCache(artifacts_dir=tmp_path, raw_dir=tmp_path)

        data_id = "test_data_12345678"
        short_id = data_id[:16]
        manifest_dir = tmp_path / short_id
        manifest_dir.mkdir(parents=True)
        manifest_file = manifest_dir / "manifest.json"
        manifest_file.write_text(
            json.dumps({"description": "original"}),
            encoding="utf-8",
        )

        with patch.object(cache, "save_manifest", return_value=False):
            result = cache.update_manifest_entry(
                data_id, "description", "should not persist"
            )

        assert result is False
        current = json.loads(manifest_file.read_text(encoding="utf-8"))
        assert current["description"] == "original"
