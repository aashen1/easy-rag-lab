from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestMealConfigCreationMode:
    def test_default_creation_mode_is_random(self):
        from src.meal.models import MealConfig

        config = MealConfig(
            data_id="test",
            name="test_meal",
            created_at="2025-01-01",
            sampling_config={"mode": "count", "value": 5},
            collection_name="meal_test",
            pdf_files=[],
        )

        assert config.creation_mode == "random"

    def test_creation_mode_can_be_manual(self):
        from src.meal.models import MealConfig

        config = MealConfig(
            data_id="test",
            name="test_meal",
            created_at="2025-01-01",
            sampling_config={"mode": "manual", "value": 0},
            collection_name="meal_test",
            pdf_files=[],
            creation_mode="manual",
        )

        assert config.creation_mode == "manual"

    def test_from_dict_defaults_to_random(self):
        from src.meal.models import MealConfig

        data = {
            "data_id": "test",
            "name": "test_meal",
            "created_at": "2025-01-01",
            "sampling_config": {"mode": "count", "value": 5},
            "collection_name": "meal_test",
            "pdf_files": [],
        }

        config = MealConfig.from_dict(data)
        assert config.creation_mode == "random"


class TestMealManagerCreateMealManual:
    def test_requires_pdf_files_or_source_dir(self):
        from src.exceptions import MealError
        from src.meal.manager import MealManager

        mock_config = {"meal": {"data_dir": "data/meals"}}
        mgr = MealManager(mock_config)

        with pytest.raises(
            MealError, match="Must provide either pdf_files or source_dir"
        ):
            mgr.create_meal_manual(name="test_meal")

    def test_creation_mode_set_to_manual(self):
        from src.meal.manager import MealManager
        from src.meal.models import MealConfig

        mock_config = {"meal": {"data_dir": "data/meals"}}
        mgr = MealManager(mock_config)

        mock_meal = MealConfig(
            data_id="test",
            name="test_meal",
            created_at="2025-01-01",
            sampling_config={"mode": "manual"},
            collection_name="meal_test",
            pdf_files=[],
            stats={"total_pages": 0, "total_chunks": 0},
        )

        mock_path = MagicMock()
        mock_path.is_absolute.return_value = True
        mock_path.exists.return_value = True
        mock_path.stat.return_value.st_size = 1000
        mock_path.relative_to.return_value.as_posix.return_value = "test.pdf"

        with (
            patch.object(mgr, "meal_exists", return_value=False),
            patch.object(
                mgr,
                "_build_config_snapshot_and_hashes",
                return_value=({}, {"chunker": "h1", "parser": "h2"}),
            ),
            patch.object(mgr, "cache") as mock_cache,
            patch.object(mgr, "_build_pipeline", return_value=mock_meal),
            patch("src.meal.manager.Path", return_value=mock_path),
            patch("src.meal.manager.compute_file_sha256", return_value="abc"),
            patch("src.meal.manager.compute_data_id", return_value="did"),
            patch("src.meal.manager.compute_index_key", return_value="ik"),
            patch("src.meal.manager.generate_collection_name", return_value="col"),
        ):
            mock_cache.ensure_dirs.return_value = ("parsed", "chunks")
            result = mgr.create_meal_manual(
                name="test_meal",
                pdf_files=["/fake/test.pdf"],
            )

        assert result.creation_mode == "manual"
