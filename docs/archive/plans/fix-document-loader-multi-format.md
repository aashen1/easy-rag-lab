# 修复计划：统一文档加载器支持多格式解析结果

## 问题概述

当 `parser.pymupdf4llm.page_chunks=True` 时，`test_generator._load_full_documents()` 无法加载文档，导致 `No documents found for meal` 错误。

### 根因

`_load_full_documents()` 只支持 `.md` 格式：

```python
md_files = list(parsed_dir.rglob("*.md"))  # 只搜索 .md 文件
```

但 `page_chunks=True` 时，解析器输出的是 `.pages.json` 格式。

***

## 现有解析链路分析

| 链路                 | Parser                                  | 输出格式         | 文件后缀          | Chunker 支持                          |
| ------------------ | --------------------------------------- | ------------ | ------------- | ----------------------------------- |
| 1. 原始 PDF→MD       | pymupdf4llm (page\_chunks=False)        | 单文件 Markdown | `.md`         | `process_parsed_files()`            |
| 2. 优化 PDF→MD       | pymupdf4llm (page\_chunks=False + 优化参数) | 单文件 Markdown | `.md`         | `process_parsed_files()`            |
| 3. PDF→JSON        | pymupdf4llm (page\_chunks=True)         | 页级 JSON      | `.pages.json` | `process_parsed_files_page_aware()` |
| 4. fitz+pdfplumber | FitzPdfPlumberParser                    | 单文件 Markdown | `.md`         | `process_parsed_files()`            |

### 第四条链路详细分析

**FitzPdfPlumberParser** 的实现逻辑：

1. **返回类型**：`ParseResult`，包含多个 `ParsedPage`（每页一个）
2. **每页内容**：Markdown 格式的文本（包含表格、标题等结构化元素）
3. **输出文件**：由于没有 `page_chunks` 配置项，`_parse_pdfs_with_registry()` 会将所有页面拼接成一个 `.md` 文件

**关键代码**（`meal.py:1298-1302`）：

```python
else:  # use_page_chunks=False
    with open(output_file, "w", encoding="utf-8") as f:
        for page in result.pages:
            f.write(page.text)
            f.write("\n\n")
```

**结论**：第四条链路与链路 1、2 相同，都是输出 `.md` 格式，使用 `process_parsed_files()` 进行分块。无需特殊处理。

**关键发现**：Chunker 已经通过 `build_chunks_if_needed()` 实现了格式自动检测：

```python
has_pages_json = parsed_dir.exists() and any(parsed_dir.rglob("*.pages.json"))
if has_pages_json:
    process_parsed_files_page_aware(...)
else:
    process_parsed_files(...)
```

***

## 修复方案

### 设计原则

1. **复用 Chunker 的格式检测逻辑**：与 `build_chunks_if_needed()` 保持一致
2. **最小改动**：只修改 `test_generator.py`，不引入新的抽象层
3. **向后兼容**：现有 `.md` 格式继续正常工作
4. **可扩展**：为未来更多 PDF→MD/JSON 链路预留接口（如 unstructured、marker、docling 等）

### 实现步骤

#### Step 1: 修改 `_load_full_documents()` 方法

**文件**: `src/test_generator.py`

**改动内容**:

1. 添加格式检测逻辑（复用 `build_chunks_if_needed()` 的模式）
2. 支持 `.pages.json` 格式的文档加载
3. 更新 `source_filter` 构建逻辑

**伪代码**:

```python
def _load_full_documents(self, meal_config: MealConfig) -> dict[str, dict[str, str]]:
    parsed_dir = self._resolve_parsed_dir(meal_config)
    if not parsed_dir or not parsed_dir.exists():
        logger.warning(f"Parsed directory not found: {parsed_dir}")
        return {}

    # 检测格式：优先检测 .pages.json，否则回退到 .md
    has_pages_json = any(parsed_dir.rglob("*.pages.json"))

    if has_pages_json:
        return self._load_pages_json_documents(parsed_dir, meal_config)
    else:
        return self._load_md_documents(parsed_dir, meal_config)

def _load_pages_json_documents(self, parsed_dir: Path, meal_config: MealConfig) -> dict[str, dict[str, str]]:
    """从 .pages.json 文件加载文档内容。"""
    # 构建 source_filter（使用 .pages.json 后缀）
    source_filter = set()
    for mf in meal_config.pdf_files:
        pages_rel = str(Path(mf.path).with_suffix(".pages.json")).replace("\\", "/")
        source_filter.add(pages_rel)

    documents = {}
    pages_files = list(parsed_dir.rglob("*.pages.json"))

    for pages_file in pages_files:
        rel_path = str(pages_file.relative_to(parsed_dir)).replace("\\", "/")
        if source_filter and rel_path not in source_filter:
            continue

        try:
            with open(pages_file, encoding="utf-8") as f:
                pages_data = json.load(f)

            # 拼接所有页面的文本
            full_text = "\n\n".join(
                page.get("text", "")
                for page in sorted(pages_data, key=lambda p: p.get("page_number", 0))
            )

            doc_name = pages_file.stem.replace(".pages", "")
            documents[doc_name] = {
                "content": full_text,
                "source_path": rel_path,
            }
        except Exception as e:
            logger.error(f"Failed to load {pages_file}: {str(e)}")

    return documents

def _load_md_documents(self, parsed_dir: Path, meal_config: MealConfig) -> dict[str, dict[str, str]]:
    """从 .md 文件加载文档内容（原有逻辑）。"""
    # ... 原有的 .md 加载逻辑 ...
```

#### Step 2: 更新 `_resolve_parsed_dir()` 方法

**文件**: `src/test_generator.py`

**改动内容**: 确保 `parsed_dir` 解析逻辑正确处理 `parser_hash`。

当前 `_resolve_parsed_dir()` 没有使用 `parser_hash`，但 `ArtifactCache.get_parsed_dir()` 支持该参数。如果未来需要区分不同 parser 配置的输出，可以扩展此方法。

**当前代码已足够**，无需修改。

#### Step 3: 添加单元测试

**文件**: `tests/test_test_generator.py`（新建或修改现有）

**测试用例**:

1. 测试 `.md` 格式文档加载
2. 测试 `.pages.json` 格式文档加载
3. 测试混合格式场景（如果存在）
4. 测试空目录场景
5. 测试 source\_filter 过滤

***

## 风险评估

| 风险                 | 影响 | 缓解措施                           |
| ------------------ | -- | ------------------------------ |
| 现有 `.md` 格式回归      | 高  | 添加单元测试确保向后兼容                   |
| `.pages.json` 格式变更 | 中  | 使用稳定的字段（`text`, `page_number`） |

***

## 验收标准

1. `page_chunks=True` 时，`generate_document_based_questions()` 能正常生成问题
2. `page_chunks=False` 时，现有功能不受影响
3. 单元测试覆盖两种格式
4. 代码通过 `pixi run lint` 检查

***

## 后续优化（可选）

### 1. 统一文档加载器

**目标**：创建 `src/document_loader.py`，提供统一的文档加载接口，支持多种解析器输出格式。

**背景**：主流 RAG PDF 解析工具的输出格式包括：

| 工具              | 输出格式                    | 特点                                  |
| --------------- | ----------------------- | ----------------------------------- |
| pymupdf4llm     | Markdown / JSON (pages) | 当前已支持                               |
| fitz+pdfplumber | Markdown                | 当前已支持                               |
| Docling         | Markdown / JSON / HTML  | IBM 开源，保留结构信息                       |
| Unstructured    | Element 列表              | 支持多种策略（fast/auto/hi\_res/ocr\_only） |
| Marker          | Markdown                | 专为学术 PDF 优化                         |

**设计方案**：

```python
# src/document_loader.py

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any

@dataclass
class LoadedDocument:
    """统一的文档表示。"""
    name: str
    content: str
    source_path: str
    metadata: dict[str, Any] = None

class DocumentLoader(ABC):
    """文档加载器基类。"""

    @abstractmethod
    def load(self, file_path: Path) -> LoadedDocument:
        """加载单个文档。"""
        pass

    @abstractmethod
    def load_all(self, directory: Path, source_filter: set[str] | None = None) -> list[LoadedDocument]:
        """加载目录下所有文档。"""
        pass

class MarkdownLoader(DocumentLoader):
    """加载 .md 格式文档。"""
    def load(self, file_path: Path) -> LoadedDocument:
        content = file_path.read_text(encoding="utf-8")
        return LoadedDocument(
            name=file_path.stem,
            content=content,
            source_path=str(file_path),
        )

class PagesJsonLoader(DocumentLoader):
    """加载 .pages.json 格式文档。"""
    def load(self, file_path: Path) -> LoadedDocument:
        import json
        with open(file_path, encoding="utf-8") as f:
            pages = json.load(f)

        full_text = "\n\n".join(
            p.get("text", "")
            for p in sorted(pages, key=lambda x: x.get("page_number", 0))
        )

        return LoadedDocument(
            name=file_path.stem.replace(".pages", ""),
            content=full_text,
            source_path=str(file_path),
            metadata={"page_count": len(pages)},
        )

def get_loader(file_path: Path) -> DocumentLoader:
    """根据文件扩展名自动选择加载器。"""
    suffix = file_path.suffix.lower()
    loaders = {
        ".md": MarkdownLoader(),
        ".json": PagesJsonLoader(),  # 检测 .pages.json
    }
    if suffix == ".json" and ".pages" in file_path.stem:
        return loaders[".json"]
    return loaders.get(suffix, MarkdownLoader())
```

**集成方式**：

修改 `test_generator._load_full_documents()` 使用统一加载器：

```python
from src.document_loader import get_loader, LoadedDocument

def _load_full_documents(self, meal_config: MealConfig) -> dict[str, dict[str, str]]:
    parsed_dir = self._resolve_parsed_dir(meal_config)
    if not parsed_dir or not parsed_dir.exists():
        return {}

    # 自动检测所有支持的格式
    all_files = list(parsed_dir.rglob("*.md")) + list(parsed_dir.rglob("*.pages.json"))

    documents = {}
    for file_path in all_files:
        loader = get_loader(file_path)
        doc = loader.load(file_path)
        documents[doc.name] = {
            "content": doc.content,
            "source_path": doc.source_path,
        }

    return documents
```

### 2. 性能优化

**问题**：当前实现一次性加载所有文档到内存，对于大型文档集可能造成内存压力。

**优化方案**：

#### 方案 A：懒加载（Lazy Loading）

```python
class LazyDocumentLoader:
    """懒加载文档，只在需要时读取文件内容。"""

    def __init__(self, directory: Path):
        self._directory = directory
        self._file_index = self._build_index()
        self._cache: dict[str, LoadedDocument] = {}

    def _build_index(self) -> dict[str, Path]:
        """构建文件索引，不加载内容。"""
        index = {}
        for f in self._directory.rglob("*.md"):
            index[f.stem] = f
        for f in self._directory.rglob("*.pages.json"):
            name = f.stem.replace(".pages", "")
            index[name] = f
        return index

    def get(self, doc_name: str) -> LoadedDocument:
        """按需加载文档，带缓存。"""
        if doc_name in self._cache:
            return self._cache[doc_name]

        if doc_name not in self._file_index:
            raise KeyError(f"Document not found: {doc_name}")

        loader = get_loader(self._file_index[doc_name])
        doc = loader.load(self._file_index[doc_name])
        self._cache[doc_name] = doc
        return doc

    def iter_documents(self) -> Iterator[LoadedDocument]:
        """迭代器模式，避免一次性加载所有文档。"""
        for doc_name in self._file_index:
            yield self.get(doc_name)
```

#### 方案 B：流式处理（Streaming）

对于超大文档（如 100+ 页的年报），可以使用流式处理：

```python
class StreamingPagesJsonLoader:
    """流式加载 .pages.json，逐页处理。"""

    def __init__(self, file_path: Path, chunk_size: int = 10):
        self._file_path = file_path
        self._chunk_size = chunk_size

    def iter_pages(self) -> Iterator[dict]:
        """逐页迭代，不一次性加载整个文件。"""
        import json
        with open(self._file_path, encoding="utf-8") as f:
            pages = json.load(f)
            for i in range(0, len(pages), self._chunk_size):
                yield pages[i:i + self._chunk_size]
```

**推荐**：先实现懒加载（方案 A），因为：

1. 实现简单，改动小
2. 对于问题生成场景，通常只需要访问部分文档
3. 缓存机制避免重复加载
