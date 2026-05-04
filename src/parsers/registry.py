from __future__ import annotations

from loguru import logger

from src.exceptions import ParsingError
from src.parsers.base import BaseParser, TableEnhancer


class ParserRegistry:
    """Central registry for PDF parser implementations.

    Parsers are registered by name and can be retrieved later via
    ``get()``.  The registry supports lazy imports so that optional
    parser dependencies are only loaded when actually needed.

    The registry maintains two separate registries:
    - **primaries**: Core text-extraction parsers (subclasses of
      ``BaseParser``).
    - **enhancers**: Table-enhancement modules (subclasses of
      ``TableEnhancer``).

    The legacy ``_parsers`` dict and ``get()`` interface are kept for
    backward compatibility.
    """

    _parsers: dict[str, type[BaseParser] | None] = {
        "pymupdf4llm": None,
        "fitz_pdfplumber": None,
    }

    _primaries: dict[str, type[BaseParser] | None] = {
        "pymupdf4llm": None,
        "fitz": None,
    }

    _enhancers: dict[str, type[TableEnhancer] | None] = {
        "pdfplumber": None,
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
            raise ParsingError(f"{parser_class} is not a subclass of BaseParser")
        cls._parsers[name] = parser_class
        logger.debug(f"Registered parser: {name}")

    @classmethod
    def register_primary(cls, name: str, parser_class: type[BaseParser]) -> None:
        """Register a primary parser class under the given name.

        Args:
            name: Unique identifier for the primary parser.
            parser_class: The parser class (subclass of ``BaseParser``).

        Raises:
            TypeError: If *parser_class* is not a subclass of ``BaseParser``.
        """
        if not issubclass(parser_class, BaseParser):
            raise ParsingError(f"{parser_class} is not a subclass of BaseParser")
        cls._primaries[name] = parser_class
        logger.debug(f"Registered primary parser: {name}")

    @classmethod
    def register_enhancer(cls, name: str, enhancer_class: type[TableEnhancer]) -> None:
        """Register a table enhancer class under the given name.

        Args:
            name: Unique identifier for the enhancer.
            enhancer_class: The enhancer class (subclass of ``TableEnhancer``).

        Raises:
            TypeError: If *enhancer_class* is not a subclass of ``TableEnhancer``.
        """
        if not issubclass(enhancer_class, TableEnhancer):
            raise ParsingError(f"{enhancer_class} is not a subclass of TableEnhancer")
        cls._enhancers[name] = enhancer_class
        logger.debug(f"Registered enhancer: {name}")

    @classmethod
    def get(cls, name: str, config: dict | None = None) -> BaseParser:
        """Instantiate and return a parser by name.

        For the built-in names ``"pymupdf4llm"`` and
        ``"fitz_pdfplumber"``, the corresponding modules are lazily
        imported on first access.

        The name ``"fitz_pdfplumber"`` is treated as a composite of
        primary ``"fitz"`` and enhancer ``"pdfplumber"``.

        Args:
            name: Registered parser name.
            config: Optional configuration dict forwarded to the parser
                constructor.

        Returns:
            An instance of the requested parser.

        Raises:
            ValueError: If *name* is not registered.
            ImportError: If the parser module cannot be imported.
        """
        if name == "fitz_pdfplumber":
            return cls.get_composite(
                primary="fitz",
                enhancer="pdfplumber",
                primary_config=config,
                enhancer_config=config,
            )

        if name not in cls._parsers:
            raise ParsingError(
                f"Parser '{name}' is not registered. Available: {cls.list_names()}"
            )

        parser_class = cls._parsers[name]

        if parser_class is None:
            parser_class = cls._lazy_import(name)
            cls._parsers[name] = parser_class

        return parser_class(config=config or {})

    @classmethod
    def get_composite(
        cls,
        primary: str,
        enhancer: str | None = None,
        primary_config: dict | None = None,
        enhancer_config: dict | None = None,
    ) -> BaseParser:
        """Instantiate a primary parser, optionally composed with an enhancer.

        If *enhancer* is ``None``, returns just the primary parser
        instance.  Otherwise, returns a ``CompositeParser`` that
        delegates to the primary parser and then applies the enhancer.

        Args:
            primary: Name of a registered primary parser.
            enhancer: Optional name of a registered table enhancer.
            primary_config: Optional configuration dict forwarded to the
                primary parser constructor.
            enhancer_config: Optional configuration dict forwarded to the
                enhancer constructor.

        Returns:
            A ``BaseParser`` instance (plain primary or composite).

        Raises:
            ParsingError: If *primary* or *enhancer* is not registered.
            ImportError: If a required module cannot be imported.
        """
        if primary not in cls._primaries:
            raise ParsingError(
                f"Primary parser '{primary}' is not registered. "
                f"Available: {cls.list_primaries()}"
            )

        primary_class = cls._primaries[primary]
        if primary_class is None:
            primary_class = cls._lazy_import_primary(primary)
            cls._primaries[primary] = primary_class

        primary_instance = primary_class(config=primary_config or {})

        if enhancer is None:
            return primary_instance

        if enhancer not in cls._enhancers:
            raise ParsingError(
                f"Enhancer '{enhancer}' is not registered. "
                f"Available: {cls.list_enhancers()}"
            )

        enhancer_class = cls._enhancers[enhancer]
        if enhancer_class is None:
            enhancer_class = cls._lazy_import_enhancer(enhancer)
            cls._enhancers[enhancer] = enhancer_class

        enhancer_instance = enhancer_class(config=enhancer_config or {})

        from src.parsers.composite_parser import CompositeParser

        return CompositeParser(primary=primary_instance, enhancer=enhancer_instance)

    @classmethod
    def get_enhancer(
        cls, enhancer_name: str = "pdfplumber", enhancer_options: dict | None = None
    ) -> TableEnhancer:
        """Instantiate and return a table enhancer by name.

        Validates that the enhancer name is registered, performs a lazy
        import if the class has not been loaded yet, and returns a new
        instance configured with *enhancer_options*.

        Args:
            enhancer_name: Name of a registered enhancer (default
                ``"pdfplumber"``).
            enhancer_options: Optional configuration dict forwarded to
                the enhancer constructor.

        Returns:
            A ``TableEnhancer`` instance.

        Raises:
            ParsingError: If *enhancer_name* is not registered.
            ImportError: If the enhancer module cannot be imported.
        """
        if enhancer_name not in cls._enhancers:
            raise ParsingError(
                f"Enhancer '{enhancer_name}' is not registered. "
                f"Available: {cls.list_enhancers()}"
            )

        enhancer_class = cls._enhancers[enhancer_name]
        if enhancer_class is None:
            enhancer_class = cls._lazy_import_enhancer(enhancer_name)
            cls._enhancers[enhancer_name] = enhancer_class

        return enhancer_class(config=enhancer_options or {})

    @classmethod
    def list_names(cls) -> list[str]:
        """Return a sorted list of all registered parser names.

        Returns:
            List of parser name strings.
        """
        return sorted(cls._parsers.keys())

    @classmethod
    def list_primaries(cls) -> list[str]:
        """Return a sorted list of all registered primary parser names.

        Returns:
            List of primary parser name strings.
        """
        return sorted(cls._primaries.keys())

    @classmethod
    def list_enhancers(cls) -> list[str]:
        """Return a sorted list of all registered enhancer names.

        Returns:
            List of enhancer name strings.
        """
        return sorted(cls._enhancers.keys())

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
            raise ParsingError(
                f"Parser '{name}' requires missing dependencies: {str(e)}"
            ) from e

    @classmethod
    def _lazy_import_primary(cls, name: str) -> type[BaseParser]:
        """Lazily import and register a built-in primary parser class.

        Args:
            name: Built-in primary parser name (``"pymupdf4llm"`` or
                ``"fitz"``).

        Returns:
            The imported primary parser class.

        Raises:
            ImportError: If the parser module cannot be imported.
            KeyError: If *name* is not a known built-in primary parser.
        """
        _import_map: dict[str, tuple[str, str]] = {
            "pymupdf4llm": (
                "src.parsers.pymupdf4llm_parser",
                "PyMuPDF4LLMParser",
            ),
            "fitz": (
                "src.parsers.fitz_parser",
                "FitzParser",
            ),
        }

        if name not in _import_map:
            raise KeyError(f"No lazy import mapping for primary parser '{name}'")

        module_path, class_name = _import_map[name]

        try:
            import importlib

            module = importlib.import_module(module_path)
            parser_class = getattr(module, class_name)
            cls._primaries[name] = parser_class
            logger.debug(f"Lazily imported primary parser: {name} -> {class_name}")
            return parser_class
        except ImportError as e:
            logger.error(f"Failed to import primary parser '{name}': {str(e)}")
            raise ParsingError(
                f"Primary parser '{name}' requires missing dependencies: {str(e)}"
            ) from e

    @classmethod
    def _lazy_import_enhancer(cls, name: str) -> type[TableEnhancer]:
        """Lazily import and register a built-in enhancer class.

        Args:
            name: Built-in enhancer name (``"pdfplumber"``).

        Returns:
            The imported enhancer class.

        Raises:
            ImportError: If the enhancer module cannot be imported.
            KeyError: If *name* is not a known built-in enhancer.
        """
        _import_map: dict[str, tuple[str, str]] = {
            "pdfplumber": (
                "src.parsers.pdfplumber_enhancer",
                "PdfPlumberEnhancer",
            ),
        }

        if name not in _import_map:
            raise KeyError(f"No lazy import mapping for enhancer '{name}'")

        module_path, class_name = _import_map[name]

        try:
            import importlib

            module = importlib.import_module(module_path)
            enhancer_class = getattr(module, class_name)
            cls._enhancers[name] = enhancer_class
            logger.debug(f"Lazily imported enhancer: {name} -> {class_name}")
            return enhancer_class
        except ImportError as e:
            logger.error(f"Failed to import enhancer '{name}': {str(e)}")
            raise ParsingError(
                f"Enhancer '{name}' requires missing dependencies: {str(e)}"
            ) from e
