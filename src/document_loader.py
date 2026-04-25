from __future__ import annotations

import json
from abc import ABC, abstractmethod
from collections import OrderedDict
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from loguru import logger


@dataclass
class LoadedDocument:
    """Represents a loaded document with its content and metadata.

    Attributes:
        name: Document name (typically the filename without extension).
        content: Full text content of the document.
        source_path: Original file path as a string.
        metadata: Optional dictionary of additional metadata.
    """

    name: str
    content: str
    source_path: str
    metadata: dict[str, Any] | None = None


class DocumentLoader(ABC):
    """Abstract base class for document loaders.

    Provides a unified interface for loading documents from different
    file formats. Concrete implementations handle format-specific parsing.
    """

    @abstractmethod
    def load(self, file_path: Path) -> LoadedDocument:
        """Load a single document from the given file path.

        Args:
            file_path: Path to the document file to load.

        Returns:
            LoadedDocument instance containing the document content and metadata.

        Raises:
            FileNotFoundError: If the file does not exist.
            ValueError: If the file format is invalid or cannot be parsed.
            IOError: If reading the file fails.
        """

    def load_all(
        self,
        directory: Path,
        source_filter: set[str] | None = None,
    ) -> list[LoadedDocument]:
        """Load all supported documents from a directory.

        Recursively scans the directory for files matching this loader's
        supported format and loads each one.

        Args:
            directory: Root directory to scan for documents.
            source_filter: Optional set of relative paths (POSIX format) to
                restrict which files are loaded. If None, all matching files
                are loaded.

        Returns:
            List of LoadedDocument instances for all successfully loaded files.

        Raises:
            FileNotFoundError: If the directory does not exist.
        """
        if not directory.exists():
            raise FileNotFoundError(f"Directory not found: {directory}")

        documents: list[LoadedDocument] = []
        for file_path in self._find_supported_files(directory):
            if source_filter is not None:
                rel_path = file_path.relative_to(directory).as_posix()
                if rel_path not in source_filter:
                    continue

            try:
                doc = self.load(file_path)
                documents.append(doc)
            except Exception as e:
                logger.error(f"Failed to load {file_path}: {str(e)}")

        return documents

    @abstractmethod
    def _find_supported_files(self, directory: Path) -> list[Path]:
        """Find all files supported by this loader in the directory.

        Args:
            directory: Directory to scan.

        Returns:
            List of file paths that this loader can process.
        """


class MarkdownLoader(DocumentLoader):
    """Loader for Markdown (.md) files.

    Loads the entire content of a Markdown file as a single document.
    """

    def load(self, file_path: Path) -> LoadedDocument:
        """Load a Markdown file.

        Args:
            file_path: Path to the .md file.

        Returns:
            LoadedDocument with the file's content.

        Raises:
            FileNotFoundError: If the file does not exist.
            IOError: If reading the file fails.
        """
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        try:
            content = file_path.read_text(encoding="utf-8")
            name = file_path.stem
            source_path = str(file_path)

            return LoadedDocument(
                name=name,
                content=content,
                source_path=source_path,
                metadata={"format": "markdown"},
            )
        except Exception as e:
            logger.error(f"Failed to read Markdown file {file_path}: {str(e)}")
            raise OSError(f"Failed to read file: {file_path}") from e

    def _find_supported_files(self, directory: Path) -> list[Path]:
        """Find all .md files in the directory.

        Args:
            directory: Directory to scan.

        Returns:
            List of paths to .md files.
        """
        return list(directory.rglob("*.md"))


class PagesJsonLoader(DocumentLoader):
    """Loader for .pages.json files.

    Loads page-level JSON files produced by PDF parsing and concatenates
    all page texts into a single document.
    """

    def load(self, file_path: Path) -> LoadedDocument:
        """Load a .pages.json file and concatenate all pages.

        Args:
            file_path: Path to the .pages.json file.

        Returns:
            LoadedDocument with concatenated text from all pages.

        Raises:
            FileNotFoundError: If the file does not exist.
            ValueError: If the JSON structure is invalid.
            IOError: If reading the file fails.
        """
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        try:
            with open(file_path, encoding="utf-8") as f:
                pages_data = json.load(f)

            if not isinstance(pages_data, list):
                raise ValueError(
                    f"Invalid .pages.json format: expected a list, got {type(pages_data).__name__}"
                )

            page_texts: list[str] = []
            total_pages = len(pages_data)

            for page in pages_data:
                if not isinstance(page, dict):
                    logger.warning(f"Skipping non-dict page entry in {file_path}")
                    continue

                text = page.get("text", "")
                if text:
                    page_texts.append(text)

            content = "\n\n".join(page_texts)
            name = file_path.stem.replace(".pages", "")
            source_path = str(file_path)

            return LoadedDocument(
                name=name,
                content=content,
                source_path=source_path,
                metadata={
                    "format": "pages_json",
                    "total_pages": total_pages,
                    "pages_with_text": len(page_texts),
                },
            )
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in {file_path}: {str(e)}")
            raise ValueError(f"Invalid JSON format: {file_path}") from e
        except Exception as e:
            logger.error(f"Failed to read pages.json file {file_path}: {str(e)}")
            raise OSError(f"Failed to read file: {file_path}") from e

    def _find_supported_files(self, directory: Path) -> list[Path]:
        """Find all .pages.json files in the directory.

        Args:
            directory: Directory to scan.

        Returns:
            List of paths to .pages.json files.
        """
        return list(directory.rglob("*.pages.json"))


_LOADER_REGISTRY: dict[str, type[DocumentLoader]] = {
    ".md": MarkdownLoader,
    ".pages.json": PagesJsonLoader,
}


def get_loader(file_path: Path) -> DocumentLoader:
    """Get the appropriate loader for a file based on its extension.

    Args:
        file_path: Path to the file. The extension is used to determine
            the appropriate loader.

    Returns:
        DocumentLoader instance suitable for the file's format.

    Raises:
        ValueError: If no loader is registered for the file's extension.

    Examples:
        >>> loader = get_loader(Path("document.md"))
        >>> isinstance(loader, MarkdownLoader)
        True
        >>> loader = get_loader(Path("report.pages.json"))
        >>> isinstance(loader, PagesJsonLoader)
        True
    """
    file_name = file_path.name

    for ext, loader_class in _LOADER_REGISTRY.items():
        if file_name.endswith(ext):
            return loader_class()

    supported = ", ".join(_LOADER_REGISTRY.keys())
    raise ValueError(
        f"No loader registered for file '{file_path}'. "
        f"Supported extensions: {supported}"
    )


class LazyDocumentLoader:
    """Lazy loader for documents with caching support.

    Scans a directory and builds an index of available documents on
    initialization, but only loads document content on demand. Loaded
    documents are cached for subsequent access.

    Attributes:
        directory: Root directory containing documents.
        _index: Mapping from document names to file paths.
        _cache: Cache of already loaded documents.
    """

    def __init__(self, directory: Path, max_cache_size: int = 128) -> None:
        """Initialize the lazy loader and build the file index.

        Scans the directory for supported document files (.md and .pages.json)
        without loading their contents.

        Args:
            directory: Root directory to scan for documents.
            max_cache_size: Maximum number of documents to keep in cache.
                When exceeded, the least recently used document is evicted.

        Raises:
            FileNotFoundError: If the directory does not exist.
        """
        if not directory.exists():
            raise FileNotFoundError(f"Directory not found: {directory}")

        self.directory = directory
        self._index: dict[str, Path] = self._build_index()
        self._cache: OrderedDict[str, tuple[LoadedDocument, float]] = OrderedDict()
        self._max_cache_size = max_cache_size

        logger.info(
            f"LazyDocumentLoader initialized with {len(self._index)} documents indexed"
        )

    def _build_index(self) -> dict[str, Path]:
        """Scan directory and build a mapping of document names to file paths.

        Searches for .md and .pages.json files recursively within the directory.
        For .pages.json files, the document name is the filename without the
        '.pages.json' suffix. For .md files, it's the filename without '.md'.

        Returns:
            Dictionary mapping document names to their file paths.
        """
        index: dict[str, Path] = {}

        md_files = list(self.directory.rglob("*.md"))
        for file_path in md_files:
            doc_name = file_path.stem
            index[doc_name] = file_path
            logger.debug(f"Indexed markdown document: {doc_name} -> {file_path}")

        pages_files = list(self.directory.rglob("*.pages.json"))
        for file_path in pages_files:
            doc_name = file_path.stem.replace(".pages", "")
            index[doc_name] = file_path
            logger.debug(f"Indexed pages.json document: {doc_name} -> {file_path}")

        return index

    def get(self, doc_name: str) -> LoadedDocument:
        """Load and return a document by name, with caching.

        If the document has been loaded before, returns the cached version.
        Otherwise, loads the document from disk and caches it for future access.

        Args:
            doc_name: Name of the document to load (filename without extension,
                or without '.pages' for .pages.json files).

        Returns:
            LoadedDocument instance containing the document content and metadata.

        Raises:
            KeyError: If no document with the given name exists in the index.
            ValueError: If the file format is invalid or cannot be parsed.
            IOError: If reading the file fails.
        """
        if doc_name in self._cache:
            cached_doc, cached_mtime = self._cache[doc_name]
            current_mtime = self._index[doc_name].stat().st_mtime
            if current_mtime == cached_mtime:
                self._cache.move_to_end(doc_name)
                logger.debug(f"Returning cached document: {doc_name}")
                return cached_doc
            logger.debug(f"Cache stale for document: {doc_name}, reloading")

        if doc_name not in self._index:
            raise KeyError(
                f"Document '{doc_name}' not found in index. "
                f"Available documents: {list(self._index.keys())}"
            )

        file_path = self._index[doc_name]

        try:
            loader = get_loader(file_path)
            document = loader.load(file_path)
            self._cache[doc_name] = (document, file_path.stat().st_mtime)
            if len(self._cache) > self._max_cache_size:
                self._cache.popitem(last=False)
            logger.info(f"Loaded and cached document: {doc_name}")
            return document
        except Exception as e:
            logger.error(f"Failed to load document '{doc_name}': {str(e)}")
            raise

    def iter_documents(self) -> Iterator[LoadedDocument]:
        """Iterate over all documents, loading them on demand.

        Uses a generator to yield documents one at a time, avoiding the
        memory overhead of loading all documents at once. Each document
        is loaded only when requested and cached for subsequent access.

        Yields:
            LoadedDocument instances for all indexed documents.

        Raises:
            ValueError: If a file format is invalid or cannot be parsed.
            IOError: If reading a file fails.

        Note:
            Errors during loading are logged but do not stop iteration.
            Failed documents are skipped and a warning is logged.
        """
        for doc_name in self._index:
            try:
                document = self.get(doc_name)
                yield document
            except Exception as e:
                logger.warning(
                    f"Skipping document '{doc_name}' due to loading error: {str(e)}"
                )
                continue

    @property
    def document_names(self) -> list[str]:
        """Get list of all indexed document names.

        Returns:
            List of document names available for loading.
        """
        return list(self._index.keys())

    @property
    def cached_count(self) -> int:
        """Get the number of currently cached documents.

        Returns:
            Number of documents that have been loaded and cached.
        """
        return len(self._cache)

    def clear_cache(self) -> None:
        """Clear the document cache.

        Removes all cached documents, forcing them to be reloaded from disk
        on the next access.
        """
        self._cache.clear()
        logger.info("Document cache cleared")
