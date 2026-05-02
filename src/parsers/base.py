from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ParsedPage:
    """Represents a single parsed page from a PDF document.

    Attributes:
        page_number: 1-indexed page number within the document.
        text: Extracted text content in Markdown format.
        metadata: Optional metadata associated with the page
            (e.g. section title, header/footer flags).
    """

    page_number: int
    text: str
    metadata: dict = field(default_factory=dict)


@dataclass
class ParseResult:
    """Holds the complete result of parsing a PDF document.

    Attributes:
        pages: Ordered list of parsed pages from the document.
        metadata: Document-level metadata (e.g. file path, page count,
            parser name, parsing timestamp).
    """

    pages: list[ParsedPage] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


class TableEnhancer(ABC):
    """Abstract base class for table enhancement modules.

    A TableEnhancer receives the ParseResult from a primary parser,
    detects table regions, re-extracts tables using a specialized
    library, and replaces the original tables with improved versions.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the unique identifier of this enhancer.

        Returns:
            Enhancer name string used for registration and lookup.
        """

    @abstractmethod
    def enhance(self, pdf_path: str, result: ParseResult) -> ParseResult:
        """Enhance table regions in a parsed result.

        Args:
            pdf_path: Path to the original PDF file (the enhancer may
                need to re-access the raw PDF for table extraction).
            result: ParseResult from the primary parser.

        Returns:
            ParseResult with enhanced table regions.

        Raises:
            FileNotFoundError: If the PDF file does not exist.
            Exception: If enhancement fails for any other reason.
        """


class BaseParser(ABC):
    """Abstract base class for all PDF parsers.

    Every concrete parser must implement the ``name`` property and the
    ``parse`` method.  The registry instantiates parsers via this
    interface so that the rest of the pipeline remains parser-agnostic.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the unique identifier of this parser.

        Returns:
            Parser name string used for registration and lookup.
        """

    @abstractmethod
    def parse(self, pdf_path: str) -> ParseResult:
        """Parse a PDF file and return per-page Markdown text.

        Args:
            pdf_path: Absolute or relative path to the PDF file.

        Returns:
            A ``ParseResult`` containing the extracted pages and
            document-level metadata.

        Raises:
            FileNotFoundError: If the PDF file does not exist.
            ValueError: If the file is not a valid PDF.
            Exception: If parsing fails for any other reason.
        """
