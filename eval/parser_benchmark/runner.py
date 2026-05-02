from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime
from pathlib import Path

import yaml
from loguru import logger

from eval.parser_benchmark.metrics import (
    DocumentMetrics,
    compute_document_metrics,
    compute_page_metrics,
)
from eval.parser_benchmark.report_generator import ReportGenerator
from eval.parser_benchmark.test_cases import TestCaseManager
from src.parsers.registry import ParserRegistry


class ParserBenchmarkRunner:
    """Runs parser benchmarks across multiple pipeline configurations."""

    def __init__(self, config_path: str | Path):
        """Initialize with a benchmark configuration file.

        Args:
            config_path: Path to the YAML benchmark configuration.
        """
        self._config_path = Path(config_path)
        with open(self._config_path, encoding="utf-8") as f:
            self._config = yaml.safe_load(f)

        self._name = self._config.get("name", "unnamed")
        self._description = self._config.get("description", "")
        self._pipelines = self._config.get("pipelines", [])
        self._output_dir = Path(self._config.get("output_dir", "data/parser_reports"))
        self._test_case_manager = TestCaseManager()

    def run(self, force: bool = False) -> dict:
        """Run the benchmark across all pipelines and test PDFs.

        Args:
            force: If True, re-run even if cached results exist.

        Returns:
            Dict with benchmark results summary.
        """
        test_pdfs = self._config.get("test_pdfs", [])
        test_cases = self._test_case_manager.load_from_config(test_pdfs)

        if not test_cases:
            logger.warning("No valid test PDFs found")
            return {"status": "no_test_cases"}

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        run_dir = self._output_dir / f"bench_{self._name}_{timestamp}"
        run_dir.mkdir(parents=True, exist_ok=True)

        all_results: dict[str, list[DocumentMetrics]] = {}

        for pipeline in self._pipelines:
            pipeline_name = pipeline["name"]
            logger.info(f"Running pipeline: {pipeline_name}")

            parser = self._create_parser(pipeline)
            pipeline_results: list[DocumentMetrics] = []

            samples_dir = run_dir / "parsed_samples" / pipeline_name
            samples_dir.mkdir(parents=True, exist_ok=True)

            for case in test_cases:
                pdf_path = case["pdf_path"]
                pdf_name = Path(pdf_path).stem

                result_path = run_dir / "results" / f"{pipeline_name}_{pdf_name}.json"

                if not force and result_path.exists():
                    logger.info(f"Skipping (cached): {pipeline_name} / {pdf_name}")
                    try:
                        with open(result_path, encoding="utf-8") as f:
                            cached = json.load(f)
                        doc_metrics = DocumentMetrics(
                            pipeline_name=cached["pipeline_name"],
                            pdf_path=cached["pdf_path"],
                            page_count=cached["page_count"],
                            total_chars=cached["total_chars"],
                            total_words=cached["total_words"],
                            total_tables=cached["total_tables"],
                            avg_table_rows=cached["avg_table_rows"],
                            avg_table_cols=cached["avg_table_cols"],
                            avg_table_empty_ratio=cached["avg_table_empty_ratio"],
                            total_headings=cached["total_headings"],
                            markdown_valid_pages=cached["markdown_valid_pages"],
                            markdown_valid_ratio=cached["markdown_valid_ratio"],
                            parse_time_seconds=cached.get("parse_time_seconds", 0.0),
                        )
                        pipeline_results.append(doc_metrics)
                        continue
                    except Exception as e:
                        logger.warning(f"Failed to load cached result: {str(e)}")

                try:
                    start_time = time.time()
                    result = parser.parse(pdf_path)
                    parse_time = time.time() - start_time

                    page_metrics_list = []
                    for page in result.pages:
                        pm = compute_page_metrics(page.text, page.page_number)
                        page_metrics_list.append(pm)

                    doc_metrics = compute_document_metrics(
                        pipeline_name=pipeline_name,
                        pdf_path=pdf_path,
                        page_metrics_list=page_metrics_list,
                        parse_time_seconds=parse_time,
                    )
                    pipeline_results.append(doc_metrics)

                    result_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(result_path, "w", encoding="utf-8") as f:
                        json.dump(
                            self._metrics_to_dict(doc_metrics),
                            f,
                            ensure_ascii=False,
                            indent=2,
                        )

                    sample_path = samples_dir / f"{pdf_name}.md"
                    with open(sample_path, "w", encoding="utf-8") as f:
                        for page in result.pages:
                            f.write(f"--- Page {page.page_number} ---\n\n")
                            f.write(page.text)
                            f.write("\n\n")

                    logger.success(
                        f"Completed: {pipeline_name} / {pdf_name} ({parse_time:.2f}s)"
                    )

                except Exception as e:
                    logger.error(f"Failed: {pipeline_name} / {pdf_path}: {str(e)}")

            all_results[pipeline_name] = pipeline_results

        manifest = {
            "name": self._name,
            "description": self._description,
            "timestamp": timestamp,
            "config_path": str(self._config_path),
            "pipelines": [p["name"] for p in self._pipelines],
            "test_pdfs": test_pdfs,
            "created_at": datetime.now().isoformat(),
        }
        manifest_path = run_dir / "manifest.json"
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)

        report_gen = ReportGenerator(run_dir)
        report_gen.generate(all_results)

        logger.success(f"Benchmark complete: {run_dir}")
        return {"status": "success", "run_dir": str(run_dir)}

    def _create_parser(self, pipeline: dict):
        """Create a parser instance from a pipeline config.

        Args:
            pipeline: Pipeline configuration dict.

        Returns:
            BaseParser instance.
        """
        primary_cfg = pipeline.get("primary", {})
        primary_name = primary_cfg.get("algorithm", "pymupdf4llm")
        primary_config = primary_cfg.get("config", {})

        enhancer_cfg = pipeline.get("table_enhancer")
        enhancer_name = None
        enhancer_config = {}

        if enhancer_cfg is not None:
            enhancer_name = enhancer_cfg.get("algorithm")
            enhancer_config = enhancer_cfg.get("config", {})

        return ParserRegistry.get_composite(
            primary=primary_name,
            enhancer=enhancer_name,
            primary_config=primary_config,
            enhancer_config=enhancer_config,
        )

    @staticmethod
    def _compute_config_hash(pipeline: dict, pdf_path: str) -> str:
        """Compute a deterministic hash for a pipeline + PDF combination.

        Args:
            pipeline: Pipeline configuration dict.
            pdf_path: Path to the test PDF.

        Returns:
            First 12 characters of the SHA-256 hex digest.
        """
        payload = {"pipeline": pipeline, "pdf": pdf_path}
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[
            :12
        ]

    @staticmethod
    def _metrics_to_dict(metrics: DocumentMetrics) -> dict:
        """Convert DocumentMetrics to a JSON-serializable dict.

        Args:
            metrics: DocumentMetrics instance.

        Returns:
            Dict suitable for JSON serialization.
        """
        return {
            "pipeline_name": metrics.pipeline_name,
            "pdf_path": metrics.pdf_path,
            "page_count": metrics.page_count,
            "total_chars": metrics.total_chars,
            "total_words": metrics.total_words,
            "total_tables": metrics.total_tables,
            "avg_table_rows": metrics.avg_table_rows,
            "avg_table_cols": metrics.avg_table_cols,
            "avg_table_empty_ratio": metrics.avg_table_empty_ratio,
            "total_headings": metrics.total_headings,
            "markdown_valid_pages": metrics.markdown_valid_pages,
            "markdown_valid_ratio": metrics.markdown_valid_ratio,
            "parse_time_seconds": metrics.parse_time_seconds,
        }
