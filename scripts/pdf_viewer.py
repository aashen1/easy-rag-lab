"""PDF viewer and chunk context extraction for golden test set review.

Provides functionality to:
1. Detect and launch external PDF viewers (SumatraPDF, Edge) at specific pages
2. Locate PDF pages for questions using chunk metadata and parsed pages
3. Extract chunk text content for inline display during review

Usage:
    from scripts.pdf_viewer import PDFViewer

    viewer = PDFViewer(data_dir="data")
    pdf_path, page = viewer.locate_page_for_question(question)
    viewer.open_at_page(pdf_path, page)
    chunks = viewer.get_chunks_for_question(question)
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from loguru import logger

FUZZY_MATCH_THRESHOLD = 0.6
CHUNK_DISPLAY_MAX_CHARS = 500
PAGE_TEXT_DISPLAY_MAX_CHARS = 800

SUMATRA_CANDIDATES = [
    r"C:\Program Files\SumatraPDF\SumatraPDF.exe",
    r"C:\Program Files (x86)\SumatraPDF\SumatraPDF.exe",
    r"C:\Users\{}\AppData\Local\SumatraPDF\SumatraPDF.exe".format(
        os.environ.get("USERNAME", "")
    ),
]

EDGE_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]


class PDFViewer:
    """PDF viewer launcher and chunk context extractor.

    Detects available PDF viewers on the system, opens PDFs at specific
    pages, locates relevant pages for questions, and extracts chunk
    text for inline display.

    Args:
        data_dir: Root data directory path. Defaults to "data".
    """

    def __init__(self, data_dir: str | Path = "data") -> None:
        self.data_dir = Path(data_dir)
        self.artifacts_dir = self.data_dir / "artifacts"
        self.raw_dir = self.data_dir / "raw"
        self._viewer_path: str | None = None
        self._viewer_type: str | None = None
        self._parsed_dir: Path | None = None
        self._chunks_dir: Path | None = None
        self._pages_cache: dict[str, list[dict[str, Any]]] = {}
        self._chunks_cache: dict[str, list[dict[str, Any]]] = {}

    @property
    def viewer_path(self) -> str | None:
        """Path to the detected PDF viewer executable.

        Returns:
            Path string or None if no viewer found.
        """
        if self._viewer_path is None:
            self._detect_viewer()
        return self._viewer_path

    @property
    def viewer_type(self) -> str | None:
        """Type of the detected PDF viewer.

        Returns:
            One of "sumatra", "edge", or None if no viewer found.
        """
        if self._viewer_type is None:
            self._detect_viewer()
        return self._viewer_type

    @property
    def parsed_dir(self) -> Path | None:
        """Resolved parsed artifacts directory via pointer.

        Returns:
            Path to parsed directory, or None if not available.
        """
        if self._parsed_dir is None:
            self._resolve_artifact_dirs()
        return self._parsed_dir

    @property
    def chunks_dir(self) -> Path | None:
        """Resolved chunks artifacts directory via pointer.

        Returns:
            Path to chunks directory, or None if not available.
        """
        if self._chunks_dir is None:
            self._resolve_artifact_dirs()
        return self._chunks_dir

    def open_at_page(self, pdf_path: str | Path, page_number: int) -> bool:
        """Open a PDF file at a specific page using the detected viewer.

        Args:
            pdf_path: Absolute or relative path to the PDF file.
            page_number: 1-based page number to open.

        Returns:
            True if the viewer was launched successfully, False otherwise.
        """
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            logger.error(f"PDF file not found: {pdf_path}")
            return False

        if not self.viewer_path:
            logger.warning("No PDF viewer detected, cannot open PDF")
            return False

        try:
            if self.viewer_type == "sumatra":
                cmd = [
                    self.viewer_path,
                    "-reuse-instance",
                    "-page",
                    str(page_number),
                    str(pdf_path),
                ]
            elif self.viewer_type == "edge":
                file_url = pdf_path.as_uri()
                cmd = [
                    self.viewer_path,
                    f"{file_url}#page={page_number}",
                ]
            else:
                cmd = [self.viewer_path, str(pdf_path)]

            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            logger.info(f"Opened {pdf_path.name} at page {page_number}")
            return True
        except Exception as e:
            logger.error(f"Failed to open PDF: {e}")
            return False

    def locate_page_for_question(
        self, question: dict[str, Any]
    ) -> tuple[Path | None, int | None]:
        """Locate the PDF file and page number for a question.

        Uses chunk metadata (page_number) first, then falls back to
        fuzzy matching ground_truth_excerpt against parsed pages.

        Args:
            question: Question dictionary from golden test set.

        Returns:
            Tuple of (pdf_path, page_number). Either may be None if
            location fails.
        """
        source_files = question.get("source_files", [])
        if not source_files:
            return None, None

        source_file = source_files[0]
        pdf_path = self.raw_dir / source_file
        if not pdf_path.exists():
            pdf_path = self.raw_dir / Path(source_file).with_suffix(".pdf")
        if not pdf_path.exists():
            logger.debug(f"PDF not found for source: {source_file}")
            pdf_path = None

        page_number = self._get_page_from_chunks(question)
        if page_number is None:
            page_number = self._get_page_from_parsed(question, source_file)

        return pdf_path, page_number

    def get_chunks_for_question(
        self, question: dict[str, Any], max_chunks: int = 3
    ) -> list[dict[str, Any]]:
        """Get relevant chunk data for a question.

        Looks up chunks by chunk_id from source_chunks, or falls back
        to fuzzy matching ground_truth_excerpt against chunk text.

        Args:
            question: Question dictionary from golden test set.
            max_chunks: Maximum number of chunks to return.

        Returns:
            List of chunk dictionaries with chunk_id, text, page_number, etc.
        """
        source_files = question.get("source_files", [])
        if not source_files:
            return []

        source_file = source_files[0]
        all_chunks = self._load_chunks_for_source(source_file)
        if not all_chunks:
            return []

        source_chunk_ids = question.get("source_chunks", [])
        if source_chunk_ids:
            matched = []
            for chunk in all_chunks:
                if chunk.get("chunk_id") in source_chunk_ids:
                    matched.append(chunk)
                if len(matched) >= max_chunks:
                    break
            if matched:
                return matched

        excerpt = question.get("ground_truth_excerpt", "")
        if excerpt:
            return self._fuzzy_match_chunks(all_chunks, excerpt, max_chunks)

        return []

    def get_page_text(self, source_file: str, page_number: int) -> str | None:
        """Get the text content of a specific page from parsed results.

        Args:
            source_file: Relative path of the source file.
            page_number: 1-based page number.

        Returns:
            Page text content, or None if not found.
        """
        pages = self._load_pages_for_source(source_file)
        for page in pages:
            if page.get("page_number") == page_number:
                text = page.get("text", "")
                if len(text) > PAGE_TEXT_DISPLAY_MAX_CHARS:
                    return text[:PAGE_TEXT_DISPLAY_MAX_CHARS] + "..."
                return text
        return None

    def format_chunk_display(self, chunks: list[dict[str, Any]]) -> str:
        """Format chunk data for display in the review interface.

        Args:
            chunks: List of chunk dictionaries.

        Returns:
            Formatted string for terminal display.
        """
        if not chunks:
            return "  (no chunk context available)"

        lines = []
        for chunk in chunks:
            chunk_id = chunk.get("chunk_id", "unknown")
            metadata = chunk.get("metadata", {})
            page_num = metadata.get("page_number", "?")
            token_count = metadata.get("token_count", "?")
            text = chunk.get("text", "")
            if len(text) > CHUNK_DISPLAY_MAX_CHARS:
                text = text[:CHUNK_DISPLAY_MAX_CHARS] + "..."

            lines.append(
                f"  ┌─ CHUNK [{chunk_id}] Page {page_num} | {token_count} tokens ─┐"
            )
            for line in text.split("\n"):
                if line.strip():
                    display_line = line.strip()
                    if len(display_line) > 72:
                        display_line = display_line[:72] + "..."
                    lines.append(f"  │ {display_line}")
            lines.append("  └──────────────────────────────────────────────────┘")

        return "\n".join(lines)

    def _detect_viewer(self) -> None:
        """Detect available PDF viewer on the system."""
        for candidate in SUMATRA_CANDIDATES:
            if Path(candidate).exists():
                self._viewer_path = candidate
                self._viewer_type = "sumatra"
                logger.info(f"Detected SumatraPDF at {candidate}")
                return

        sumatra_in_path = shutil.which("SumatraPDF")
        if sumatra_in_path:
            self._viewer_path = sumatra_in_path
            self._viewer_type = "sumatra"
            logger.info(f"Detected SumatraPDF in PATH: {sumatra_in_path}")
            return

        for candidate in EDGE_CANDIDATES:
            if Path(candidate).exists():
                self._viewer_path = candidate
                self._viewer_type = "edge"
                logger.info(f"Detected Edge at {candidate}")
                return

        edge_in_path = shutil.which("msedge")
        if edge_in_path:
            self._viewer_path = edge_in_path
            self._viewer_type = "edge"
            logger.info(f"Detected Edge in PATH: {edge_in_path}")
            return

        logger.warning("No PDF viewer detected (SumatraPDF or Edge recommended)")
        self._viewer_path = None
        self._viewer_type = None

    def _resolve_artifact_dirs(self) -> None:
        """Resolve parsed and chunks artifact directories via pointers."""
        try:
            from src.meal import ArtifactCache

            cache = ArtifactCache(self.artifacts_dir, self.raw_dir)
            self._parsed_dir = cache.resolve_pointer("full_parsed")
            self._chunks_dir = cache.resolve_pointer("full_chunks")
        except Exception as e:
            logger.warning(f"Failed to resolve artifact directories: {e}")
            self._parsed_dir = None
            self._chunks_dir = None

    def _get_page_from_chunks(self, question: dict[str, Any]) -> int | None:
        """Get page number from chunk metadata.

        Args:
            question: Question dictionary.

        Returns:
            Page number or None.
        """
        source_files = question.get("source_files", [])
        source_chunk_ids = question.get("source_chunks", [])
        if not source_files or not source_chunk_ids:
            return None

        all_chunks = self._load_chunks_for_source(source_files[0])
        for chunk in all_chunks:
            if chunk.get("chunk_id") in source_chunk_ids:
                page = chunk.get("metadata", {}).get("page_number")
                if page is not None:
                    return int(page)
        return None

    def _get_page_from_parsed(
        self, question: dict[str, Any], source_file: str
    ) -> int | None:
        """Get page number by fuzzy matching excerpt against parsed pages.

        Args:
            question: Question dictionary.
            source_file: Relative path of the source file.

        Returns:
            Page number or None.
        """
        excerpt = question.get("ground_truth_excerpt", "")
        if not excerpt:
            return None

        pages = self._load_pages_for_source(source_file)
        best_score = 0.0
        best_page = None

        for page in pages:
            page_text = page.get("text", "")
            if not page_text:
                continue
            score = SequenceMatcher(None, excerpt[:200], page_text[:2000]).ratio()
            if score > best_score:
                best_score = score
                best_page = page.get("page_number")

        if best_score >= FUZZY_MATCH_THRESHOLD and best_page is not None:
            return int(best_page)
        return None

    def _load_pages_for_source(self, source_file: str) -> list[dict[str, Any]]:
        """Load parsed pages for a source file.

        Args:
            source_file: Relative path of the source file.

        Returns:
            List of page dictionaries.
        """
        if source_file in self._pages_cache:
            return self._pages_cache[source_file]

        pages = []
        if self.parsed_dir and self.parsed_dir.exists():
            pages_file = self.parsed_dir / Path(source_file).with_suffix(".pages.json")
            if not pages_file.exists():
                stem = Path(source_file).stem
                for f in self.parsed_dir.rglob(f"{stem}.pages.json"):
                    pages_file = f
                    break

            if pages_file.exists():
                try:
                    with open(pages_file, encoding="utf-8") as f:
                        pages = json.load(f)
                    logger.debug(f"Loaded {len(pages)} pages from {pages_file}")
                except Exception as e:
                    logger.warning(f"Failed to load pages from {pages_file}: {e}")

        self._pages_cache[source_file] = pages
        return pages

    def _load_chunks_for_source(self, source_file: str) -> list[dict[str, Any]]:
        """Load chunks for a source file from JSONL.

        Args:
            source_file: Relative path of the source file.

        Returns:
            List of chunk dictionaries.
        """
        if source_file in self._chunks_cache:
            return self._chunks_cache[source_file]

        chunks = []
        if self.chunks_dir and self.chunks_dir.exists():
            stem = Path(source_file).stem.split(".")[0]
            for jsonl_file in self.chunks_dir.rglob("*.jsonl"):
                try:
                    with open(jsonl_file, encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if not line:
                                continue
                            chunk = json.loads(line)
                            chunk_source = chunk.get("metadata", {}).get("source", "")
                            chunk_stem = Path(chunk_source).stem.split(".")[0]
                            if chunk_stem == stem:
                                chunks.append(chunk)
                except Exception as e:
                    logger.warning(f"Failed to load chunks from {jsonl_file}: {e}")
                    continue

            chunks.sort(key=lambda c: str(c.get("metadata", {}).get("chunk_index", "")))
            logger.debug(f"Loaded {len(chunks)} chunks for {source_file}")

        self._chunks_cache[source_file] = chunks
        return chunks

    @staticmethod
    def _fuzzy_match_chunks(
        chunks: list[dict[str, Any]],
        excerpt: str,
        max_chunks: int = 3,
    ) -> list[dict[str, Any]]:
        """Find chunks that fuzzy-match an excerpt string.

        Uses substring containment first, then falls back to
        longest common subsequence ratio for fuzzy matching.

        Args:
            chunks: All chunks for a source file.
            excerpt: Text to match against chunk text.
            max_chunks: Maximum number of chunks to return.

        Returns:
            List of best-matching chunk dictionaries.
        """
        scored = []
        excerpt_lower = excerpt.lower()
        for chunk in chunks:
            text = chunk.get("text", "").lower()
            if not text:
                continue

            if excerpt_lower in text:
                scored.append((1.0, chunk))
                continue

            match = SequenceMatcher(
                None, excerpt_lower[:300], text[:1000]
            ).find_longest_match(
                0, min(len(excerpt_lower), 300), 0, min(len(text), 1000)
            )
            if match.size > 0:
                coverage = match.size / len(excerpt_lower)
                if coverage >= FUZZY_MATCH_THRESHOLD:
                    scored.append((coverage, chunk))

        scored.sort(key=lambda x: -x[0])
        return [chunk for _, chunk in scored[:max_chunks]]
