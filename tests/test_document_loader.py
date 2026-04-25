import time
from pathlib import Path

import pytest

from src.document_loader import (
    LazyDocumentLoader,
    LoadedDocument,
    MarkdownLoader,
    PagesJsonLoader,
    get_loader,
)


class TestMarkdownLoader:
    def test_load_normal_md_file(self, tmp_path: Path):
        md_file = tmp_path / "test.md"
        md_file.write_text("# Test Document\n\nThis is test content.", encoding="utf-8")

        loader = MarkdownLoader()
        result = loader.load(md_file)

        assert isinstance(result, LoadedDocument)
        assert result.name == "test"
        assert result.content == "# Test Document\n\nThis is test content."
        assert result.source_path == str(md_file)
        assert result.metadata == {"format": "markdown"}

    def test_load_empty_file(self, tmp_path: Path):
        md_file = tmp_path / "empty.md"
        md_file.write_text("", encoding="utf-8")

        loader = MarkdownLoader()
        result = loader.load(md_file)

        assert isinstance(result, LoadedDocument)
        assert result.name == "empty"
        assert result.content == ""
        assert result.metadata == {"format": "markdown"}

    def test_load_file_not_found(self, tmp_path: Path):
        non_existent = tmp_path / "nonexistent.md"

        loader = MarkdownLoader()

        with pytest.raises(FileNotFoundError) as exc_info:
            loader.load(non_existent)

        assert "File not found" in str(exc_info.value)

    def test_load_unicode_content(self, tmp_path: Path):
        md_file = tmp_path / "unicode.md"
        md_file.write_text("# 中文标题\n\n内容包含特殊字符：émoji 🎉", encoding="utf-8")

        loader = MarkdownLoader()
        result = loader.load(md_file)

        assert "中文标题" in result.content
        assert "émoji 🎉" in result.content


class TestPagesJsonLoader:
    def test_load_normal_pages_json_file(self, tmp_path: Path):
        json_file = tmp_path / "report.pages.json"
        json_file.write_text(
            '[{"text": "Page 1 content", "page_number": 1}, {"text": "Page 2 content", "page_number": 2}]',
            encoding="utf-8",
        )

        loader = PagesJsonLoader()
        result = loader.load(json_file)

        assert isinstance(result, LoadedDocument)
        assert result.name == "report"
        assert "Page 1 content" in result.content
        assert "Page 2 content" in result.content
        assert result.metadata["format"] == "pages_json"
        assert result.metadata["total_pages"] == 2
        assert result.metadata["pages_with_text"] == 2

    def test_load_invalid_json_format(self, tmp_path: Path):
        json_file = tmp_path / "invalid.pages.json"
        json_file.write_text("{not valid json}", encoding="utf-8")

        loader = PagesJsonLoader()

        with pytest.raises(ValueError) as exc_info:
            loader.load(json_file)

        assert "Invalid JSON format" in str(exc_info.value)

    def test_load_missing_text_field(self, tmp_path: Path):
        json_file = tmp_path / "no_text.pages.json"
        json_file.write_text(
            '[{"page_number": 1}, {"text": "Page 2 content", "page_number": 2}]',
            encoding="utf-8",
        )

        loader = PagesJsonLoader()
        result = loader.load(json_file)

        assert "Page 2 content" in result.content
        assert result.metadata["pages_with_text"] == 1

    def test_load_missing_page_number_field(self, tmp_path: Path):
        json_file = tmp_path / "no_page.pages.json"
        json_file.write_text(
            '[{"text": "Page 1 content"}, {"text": "Page 2 content", "page_number": 2}]',
            encoding="utf-8",
        )

        loader = PagesJsonLoader()
        result = loader.load(json_file)

        assert "Page 1 content" in result.content
        assert "Page 2 content" in result.content

    def test_load_file_not_found(self, tmp_path: Path):
        non_existent = tmp_path / "nonexistent.pages.json"

        loader = PagesJsonLoader()

        with pytest.raises(FileNotFoundError) as exc_info:
            loader.load(non_existent)

        assert "File not found" in str(exc_info.value)

    def test_load_non_list_json(self, tmp_path: Path):
        json_file = tmp_path / "not_list.pages.json"
        json_file.write_text('{"key": "value"}', encoding="utf-8")

        loader = PagesJsonLoader()

        with pytest.raises(OSError) as exc_info:
            loader.load(json_file)

        assert "Failed to read file" in str(exc_info.value)

    def test_load_empty_pages_list(self, tmp_path: Path):
        json_file = tmp_path / "empty.pages.json"
        json_file.write_text("[]", encoding="utf-8")

        loader = PagesJsonLoader()
        result = loader.load(json_file)

        assert result.content == ""
        assert result.metadata["total_pages"] == 0
        assert result.metadata["pages_with_text"] == 0


class TestLazyDocumentLoader:
    def test_init_builds_index_without_loading(self, tmp_path: Path):
        (tmp_path / "doc1.md").write_text("Content 1", encoding="utf-8")
        (tmp_path / "doc2.pages.json").write_text(
            '[{"text": "Page 1", "page_number": 1}]', encoding="utf-8"
        )

        loader = LazyDocumentLoader(tmp_path)

        assert len(loader._index) == 2
        assert len(loader._cache) == 0
        assert "doc1" in loader._index
        assert "doc2" in loader._index

    def test_get_loads_and_caches_document(self, tmp_path: Path):
        (tmp_path / "test.md").write_text("Test content", encoding="utf-8")

        loader = LazyDocumentLoader(tmp_path)

        assert len(loader._cache) == 0

        doc = loader.get("test")

        assert isinstance(doc, LoadedDocument)
        assert doc.content == "Test content"
        assert len(loader._cache) == 1
        assert "test" in loader._cache

    def test_get_returns_cached_document(self, tmp_path: Path):
        (tmp_path / "test.md").write_text("Original content", encoding="utf-8")

        loader = LazyDocumentLoader(tmp_path)

        doc1 = loader.get("test")
        doc1_modified = LoadedDocument(
            name="test",
            content="Modified content",
            source_path=doc1.source_path,
            metadata=doc1.metadata,
        )
        loader._cache["test"] = (doc1_modified, loader._index["test"].stat().st_mtime)

        doc2 = loader.get("test")

        assert doc2.content == "Modified content"
        assert len(loader._cache) == 1

    def test_get_raises_keyerror_for_unknown_document(self, tmp_path: Path):
        (tmp_path / "existing.md").write_text("Content", encoding="utf-8")

        loader = LazyDocumentLoader(tmp_path)

        with pytest.raises(KeyError) as exc_info:
            loader.get("nonexistent")

        assert "not found in index" in str(exc_info.value)

    def test_iter_documents_yields_all_documents(self, tmp_path: Path):
        (tmp_path / "doc1.md").write_text("Content 1", encoding="utf-8")
        (tmp_path / "doc2.md").write_text("Content 2", encoding="utf-8")

        loader = LazyDocumentLoader(tmp_path)
        documents = list(loader.iter_documents())

        assert len(documents) == 2
        contents = {doc.content for doc in documents}
        assert "Content 1" in contents
        assert "Content 2" in contents

    def test_iter_documents_caches_loaded_documents(self, tmp_path: Path):
        (tmp_path / "doc1.md").write_text("Content 1", encoding="utf-8")
        (tmp_path / "doc2.md").write_text("Content 2", encoding="utf-8")

        loader = LazyDocumentLoader(tmp_path)

        assert len(loader._cache) == 0

        list(loader.iter_documents())

        assert len(loader._cache) == 2

    def test_init_raises_for_nonexistent_directory(self, tmp_path: Path):
        non_existent = tmp_path / "nonexistent"

        with pytest.raises(FileNotFoundError) as exc_info:
            LazyDocumentLoader(non_existent)

        assert "Directory not found" in str(exc_info.value)

    def test_document_names_property(self, tmp_path: Path):
        (tmp_path / "alpha.md").write_text("A", encoding="utf-8")
        (tmp_path / "beta.pages.json").write_text(
            '[{"text": "B", "page_number": 1}]', encoding="utf-8"
        )

        loader = LazyDocumentLoader(tmp_path)
        names = loader.document_names

        assert "alpha" in names
        assert "beta" in names

    def test_cached_count_property(self, tmp_path: Path):
        (tmp_path / "doc1.md").write_text("Content 1", encoding="utf-8")
        (tmp_path / "doc2.md").write_text("Content 2", encoding="utf-8")

        loader = LazyDocumentLoader(tmp_path)

        assert loader.cached_count == 0

        loader.get("doc1")
        assert loader.cached_count == 1

        loader.get("doc2")
        assert loader.cached_count == 2

    def test_clear_cache(self, tmp_path: Path):
        (tmp_path / "doc.md").write_text("Content", encoding="utf-8")

        loader = LazyDocumentLoader(tmp_path)
        loader.get("doc")

        assert loader.cached_count == 1

        loader.clear_cache()

        assert loader.cached_count == 0

    def test_cache_invalidation_on_source_change(self, tmp_path: Path):
        doc_file = tmp_path / "test.md"
        doc_file.write_text("original content", encoding="utf-8")
        loader = LazyDocumentLoader(tmp_path)
        doc1 = loader.get("test")
        assert "original content" in doc1.content
        time.sleep(0.1)
        doc_file.write_text("modified content", encoding="utf-8")
        import os

        os.utime(str(doc_file), (time.time() + 1, time.time() + 1))
        doc2 = loader.get("test")
        assert "modified content" in doc2.content

    def test_lru_eviction(self, tmp_path: Path):
        for i in range(5):
            doc_file = tmp_path / f"doc_{i}.md"
            doc_file.write_text(f"content {i}", encoding="utf-8")
        loader = LazyDocumentLoader(tmp_path)
        loader._max_cache_size = 3
        loader.get("doc_0")
        loader.get("doc_1")
        loader.get("doc_2")
        assert len(loader._cache) == 3
        loader.get("doc_3")
        assert len(loader._cache) == 3
        assert "doc_0" not in loader._cache


class TestGetLoader:
    def test_returns_markdown_loader_for_md_file(self, tmp_path: Path):
        md_file = tmp_path / "document.md"

        loader = get_loader(md_file)

        assert isinstance(loader, MarkdownLoader)

    def test_returns_pages_json_loader_for_pages_json_file(self, tmp_path: Path):
        pages_file = tmp_path / "report.pages.json"

        loader = get_loader(pages_file)

        assert isinstance(loader, PagesJsonLoader)

    def test_raises_for_unsupported_extension(self, tmp_path: Path):
        unsupported_file = tmp_path / "document.txt"

        with pytest.raises(ValueError) as exc_info:
            get_loader(unsupported_file)

        assert "No loader registered" in str(exc_info.value)

    def test_handles_various_md_filenames(self, tmp_path: Path):
        test_cases = [
            "simple.md",
            "with-dash.md",
            "with_underscore.md",
        ]

        for filename in test_cases:
            file_path = tmp_path / filename
            loader = get_loader(file_path)
            assert isinstance(loader, MarkdownLoader), f"Failed for {filename}"

    def test_handles_various_pages_json_filenames(self, tmp_path: Path):
        test_cases = [
            "report.pages.json",
            "data.pages.json",
        ]

        for filename in test_cases:
            file_path = tmp_path / filename
            loader = get_loader(file_path)
            assert isinstance(loader, PagesJsonLoader), f"Failed for {filename}"
