from __future__ import annotations

from loguru import logger

from src.parsers.base import BaseParser


class ParserRegistry:
    """Central registry for PDF parser implementations.

    Parsers are registered by name and can be retrieved later via
    ``get()``.  The registry supports lazy imports so that optional
    parser dependencies are only loaded when actually needed.
    """

    _parsers: dict[str, type[BaseParser] | None] = {
        "pymupdf4llm": None,
        "fitz_pdfplumber": None,
    }

    @classmethod
    def register(cls, name: str, parser_class: type[BaseParser]) -> None:
        """Register a parser class under the given name.

        Args:
            name: Unique identifier for the parser.
            parser_class: The parser class (subclass of ``BaseParser``).

        Raises:
            TypeError: If *parser_class* is not a subclass of ``BaseParser``.
        """
        if not issubclass(parser_class, BaseParser):
            raise TypeError(f"{parser_class} is not a subclass of BaseParser")
        cls._parsers[name] = parser_class
        logger.debug(f"Registered parser: {name}")

    @classmethod
    def get(cls, name: str, config: dict | None = None) -> BaseParser:
        """Instantiate and return a parser by name.

        For the built-in names ``"pymupdf4llm"`` and
        ``"fitz_pdfplumber"``, the corresponding modules are lazily
        imported on first access.

        Args:
            name: Registered parser name.
            config: Optional configuration dict forwarded to the parser
                constructor.

        Returns:
            An instance of the requested parser.

        Raises:
            KeyError: If *name* is not registered.
            ImportError: If the parser module cannot be imported.
        """
        if name not in cls._parsers:
            raise KeyError(
                f"Parser '{name}' is not registered. Available: {cls.list_names()}"
            )

        parser_class = cls._parsers[name]

        if parser_class is None:
            parser_class = cls._lazy_import(name)
            cls._parsers[name] = parser_class

        return parser_class(config=config or {})

    @classmethod
    def list_names(cls) -> list[str]:
        """Return a sorted list of all registered parser names.

        Returns:
            List of parser name strings.
        """
        return sorted(cls._parsers.keys())

    @classmethod
    def _lazy_import(cls, name: str) -> type[BaseParser]:
        """Lazily import and register a built-in parser class.

        Args:
            name: Built-in parser name (``"pymupdf4llm"`` or
                ``"fitz_pdfplumber"``).

        Returns:
            The imported parser class.

        Raises:
            ImportError: If the parser module cannot be imported.
            KeyError: If *name* is not a known built-in parser.
        """
        _import_map: dict[str, tuple[str, str]] = {
            "pymupdf4llm": (
                "src.parsers.pymupdf4llm_parser",
                "PyMuPDF4LLMParser",
            ),
            "fitz_pdfplumber": (
                "src.parsers.fitz_pdfplumber_parser",
                "FitzPdfPlumberParser",
            ),
        }

        if name not in _import_map:
            raise KeyError(f"No lazy import mapping for parser '{name}'")

        module_path, class_name = _import_map[name]

        try:
            import importlib

            module = importlib.import_module(module_path)
            parser_class = getattr(module, class_name)
            cls._parsers[name] = parser_class
            logger.debug(f"Lazily imported parser: {name} -> {class_name}")
            return parser_class
        except ImportError as e:
            logger.error(f"Failed to import parser '{name}': {str(e)}")
            raise ImportError(
                f"Parser '{name}' requires missing dependencies: {str(e)}"
            ) from e
