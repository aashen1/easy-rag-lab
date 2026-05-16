from __future__ import annotations

from datetime import datetime
from pathlib import Path

from loguru import logger

from src.utils import load_config


class BaseReporter:
    """Base class for reporters with common save functionality."""

    def _save_report(
        self,
        report: str,
        session_id: str,
        report_type: str,
        reports_dir: str | Path | None = None,
    ) -> Path:
        if reports_dir is None:
            reports_dir = Path(
                load_config()
                .get("agent", {})
                .get("maintenance_reports_dir", "data/maintenance_reports")
            )
        else:
            reports_dir = Path(reports_dir)
        try:
            reports_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            logger.error(f"Failed to create reports directory {reports_dir}: {e}")
            raise

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{report_type}_{session_id}_{timestamp}.md"
        filepath = reports_dir / filename

        try:
            filepath.write_text(report, encoding="utf-8")
        except OSError as e:
            logger.error(f"Failed to write {report_type} report to {filepath}: {e}")
            raise
        logger.info(f"{report_type.capitalize()} report saved to {filepath}")
        return filepath
