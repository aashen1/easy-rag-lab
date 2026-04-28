# 统一文档加载器与性能优化 Spec

## Why

当前 `test_generator._load_full_documents()` 的实现存在两个问题：
1. **扩展性差**：每次新增解析器输出格式都需要修改 `_load_full_documents()` 方法，违反开闭原则
2. **性能隐患**：一次性加载所有文档到内存，对于大型文档集可能造成内存压力

## What Changes

- 创建 `src/document_loader.py`，提供统一的文档加载接口
- 实现 `MarkdownLoader` 和 `PagesJsonLoader` 两个具体加载器
- 实现 `LazyDocumentLoader` 懒加载机制，按需加载文档并缓存
- 重构 `test_generator._load_full_documents()` 使用新的统一加载器

## Impact

- Affected specs: 文档加载能力
- Affected code: `src/test_generator.py`, 新增 `src/document_loader.py`

## ADDED Requirements

### Requirement: 统一文档加载器接口

系统应提供统一的文档加载接口，支持多种解析器输出格式。

#### Scenario: 加载 Markdown 文档
- **WHEN** 用户使用 `MarkdownLoader` 加载 `.md` 文件
- **THEN** 系统返回 `LoadedDocument` 对象，包含文档名称、内容和源路径

#### Scenario: 加载 Pages JSON 文档
- **WHEN** 用户使用 `PagesJsonLoader` 加载 `.pages.json` 文件
- **THEN** 系统解析 JSON 文件，拼接所有页面文本，返回 `LoadedDocument` 对象

#### Scenario: 自动选择加载器
- **WHEN** 用户调用 `get_loader(file_path)` 获取加载器
- **THEN** 系统根据文件扩展名自动选择合适的加载器

### Requirement: 懒加载机制

系统应支持懒加载，避免一次性加载所有文档到内存。

#### Scenario: 构建文件索引
- **WHEN** 初始化 `LazyDocumentLoader` 时
- **THEN** 系统仅扫描目录构建文件索引，不加载文档内容

#### Scenario: 按需加载文档
- **WHEN** 用户调用 `get(doc_name)` 获取文档
- **THEN** 系统检查缓存，若未缓存则加载文档并缓存

#### Scenario: 迭代访问文档
- **WHEN** 用户使用 `iter_documents()` 迭代访问文档
- **THEN** 系统按需加载文档，避免一次性加载所有文档

### Requirement: 重构现有代码

系统应重构 `test_generator._load_full_documents()` 使用新的统一加载器。

#### Scenario: 使用懒加载器
- **WHEN** `_load_full_documents()` 被调用时
- **THEN** 系统使用 `LazyDocumentLoader` 加载文档，保持原有功能不变

## MODIFIED Requirements

无

## REMOVED Requirements

无
