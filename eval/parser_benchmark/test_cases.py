from __future__ import annotations

import json
from pathlib import Path

from loguru import logger


class TestCaseManager:
    """Manages test PDF files and their ground truth annotations."""

    def __init__(self, test_cases_dir: str | Path | None = None):
        """Initialize with optional test cases directory.

        Args:
            test_cases_dir: Directory containing test PDF files and
                annotations. If None, no local test cases are loaded.
        """
        self._dir = Path(test_cases_dir) if test_cases_dir else None
        self._cases: list[dict] = []

    def load_from_config(self, test_pdfs: list[str]) -> list[dict]:
        """Load test cases from benchmark config's test_pdfs list.

        Args:
            test_pdfs: List of PDF file paths from benchmark config.

        Returns:
            List of test case dicts with pdf_path and optional
            ground_truth.
        """
        cases = []
        for pdf_path in test_pdfs:
            path = Path(pdf_path)
            if not path.exists():
                logger.warning(f"Test PDF not found: {pdf_path}")
                continue

            case = {"pdf_path": str(path)}

            annotation_path = path.with_suffix(".annotation.json")
            if annotation_path.exists():
                try:
                    with open(annotation_path, encoding="utf-8") as f:
                        case["ground_truth"] = json.load(f)
                except Exception as e:
                    logger.warning(
                        f"Failed to load annotation for {pdf_path}: {str(e)}"
                    )

            cases.append(case)

        self._cases = cases
        return cases

    @property
    def cases(self) -> list[dict]:
        """Return the list of loaded test cases."""
        return self._cases
