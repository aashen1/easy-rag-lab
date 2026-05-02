from __future__ import annotations

from loguru import logger

from src.parsers.base import BaseParser, ParseResult, TableEnhancer


class CompositeParser(BaseParser):
    """Parser that combines a primary parser with an optional table enhancer.

    Delegates parsing to the primary parser, then applies table enhancement
    if an enhancer is provided.
    """

    def __init__(self, primary: BaseParser, enhancer: TableEnhancer | None = None):
        """Initialize with a primary parser and optional table enhancer.

        Args:
            primary: The primary parser responsible for text extraction.
            enhancer: Optional table enhancement module. If None, this
                parser behaves identically to the primary parser alone.
        """
        self._primary = primary
        self._enhancer = enhancer

    @property
    def name(self) -> str:
        """Return the composite name of primary + enhancer.

        Returns:
            Name string in format "{primary_name}+{enhancer_name}" if
            enhancer is set, otherwise just the primary name.
        """
        if self._enhancer is not None:
            return f"{self._primary.name}+{self._enhancer.name}"
        return self._primary.name

    def parse(self, pdf_path: str) -> ParseResult:
        """Parse a PDF using primary parser, then enhance tables.

        Args:
            pdf_path: Path to the PDF file.

        Returns:
            ParseResult from the primary parser, optionally enhanced
            by the table enhancer.

        Raises:
            FileNotFoundError: If the PDF file does not exist.
            ValueError: If the file is not a valid PDF.
            Exception: If parsing or enhancement fails.
        """
        result = self._primary.parse(pdf_path)

        if self._enhancer is not None:
            logger.debug(
                f"Applying table enhancer '{self._enhancer.name}' to "
                f"result from '{self._primary.name}'"
            )
            result = self._enhancer.enhance(pdf_path, result)

        return result
