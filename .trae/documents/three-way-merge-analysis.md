# 三路并行分支归并分析与策略

## 一、分支概览

三条分支均基于同一个基点 `3a56224`（dev 当前 HEAD），无分叉偏移。

| 分支 | 提交数 | 功能定位 |
|------|--------|----------|
| `cleaning` | 13 | 积压 issue 清理、bug 修复、小功能增强 |
| `better-pymupdf4llm` | 8 | 重构 PyMuPDF4LLM 解析逻辑，增加 page_chunks 支持 |
| `try-fitz` | 8 | 新增 PyMuPDF+pdfplumber 解析链路，策略模式架构 |

## 二、冲突分析

### 2.1 单独合并到 dev（无前置合并）

| 合并方向 | 结果 |
|----------|------|
| `cleaning` → `dev` | ✅ 无冲突 |
| `better-pymupdf4llm` → `dev` | ✅ 无冲突 |
| `try-fitz` → `dev` | ✅ 无冲突 |

三条分支单独合并均无冲突，因为它们从同一基点出发。

### 2.2 两两组合冲突

| 合并顺序 | 冲突文件 | 冲突性质 |
|----------|----------|----------|
| `cleaning` → `better-pymupdf4llm` | `src/parser.py`, `tests/test_chunker.py` | 语义冲突 |
| `better-pymupdf4llm` → `cleaning` | `src/parser.py`, `tests/test_chunker.py` | 同上，顺序无关 |
| `cleaning` → `try-fitz` | ✅ 无冲突 | 互不干扰 |
| `try-fitz` → `cleaning` | ✅ 无冲突 | 互不干扰 |
| `better-pymupdf4llm` → `try-fitz` | `config.yaml`, `src/meal.py` | 架构冲突 |
| `try-fitz` → `better-pymupdf4llm` | `config.yaml`, `src/meal.py` | 同上 |

### 2.3 三路全部合并（cleaning + try-fitz + better-pymupdf4llm）

在 `cleaning` + `try-fitz`（无冲突）的基础上再合并 `better-pymupdf4llm`，冲突文件增至 4 个：

| 冲突文件 | 冲突方 | 冲突性质 |
|----------|--------|----------|
| `src/parser.py` | `cleaning` vs `better-pymupdf4llm` | 两种不同的页面感知方案 |
| `tests/test_chunker.py` | `cleaning` vs `better-pymupdf4llm` | 测试导入和测试类冲突 |
| `config.yaml` | `try-fitz` vs `better-pymupdf4llm` | parser 配置结构冲突 |
| `src/meal.py` | `try-fitz` vs `better-pymupdf4llm` | parser hash 计算与集成方式冲突 |

## 三、冲突深度解析

### 3.1 `src/parser.py` — 核心语义冲突

这是最关键的冲突。两个分支对"如何让解析结果携带页面信息"给出了**互斥的方案**：

| | `cleaning` 分支 | `better-pymupdf4llm` 分支 |
|---|---|---|
| **方案** | 注入 HTML 注释标记 `<!-- page: N -->` | 使用 pymupdf4llm 原生 `page_chunks=True` |
| **新增 import** | `import re` | `import json` |
| **新增函数** | `_inject_page_markers()` | 无新函数，修改 `parse_pdf` 签名 |
| **`parse_pdf` 签名** | `(pdf_path, **kwargs) -> str` | `(pdf_path, page_chunks=False, **kwargs) -> str \| list[dict]` |
| **返回值** | 始终返回 str（内嵌标记） | str 或 list[dict]（结构化数据） |
| **输出格式** | `.md` 文件 | `.md` 或 `.pages.json` 文件 |

**关键判断**：`better-pymupdf4llm` 的 `page_chunks` 方案是 `try-fitz` 策略模式架构的**前置依赖**——`try-fitz` 的 `PyMuPDF4LLMParser` 适配器内部就是调用 `page_chunks=True`。而 `cleaning` 的 `_inject_page_markers` 是一种**过渡方案**，在 `page_chunks` 不可用时作为降级手段。

**结论**：`better-pymupdf4llm` 的方案应作为主方案，`cleaning` 的 `_inject_page_markers` 应被废弃或降级为 fallback。

### 3.2 `tests/test_chunker.py` — 测试代码冲突

`cleaning` 新增了 `TestExtractPageMarkers`、`TestExtractHeadings`、`TestGetPageRange` 等测试类（基于 `<!-- page: N -->` 标记），以及 `test_chunk_metadata_with_page_markers` / `test_chunk_metadata_without_page_markers` 测试。

`better-pymupdf4llm` 修改了导入列表（增加 `chunk_text_page_aware`, `process_parsed_files_page_aware`），并新增了基于 `page_chunks` 的测试。

**结论**：需重写测试，基于 `page_chunks` 方案。

### 3.3 `config.yaml` — 配置结构冲突

`better-pymupdf4llm` 在 `parser.pymupdf4llm` 下新增了 `page_chunks: true`、`force_text`、`ignore_code`、`use_ocr` 等参数。

`try-fitz` 新增了 `parser.fitz_pdfplumber` 整个子配置段（header_filter、table_strategy 等），同时 `pymupdf4llm` 下保持 `page_separators: true`、`ignore_images: true` 的旧参数。

**结论**：需要合并两边的配置项。`try-fitz` 的 `pymupdf4llm` 参数应更新为 `better-pymupdf4llm` 的优化版本，`fitz_pdfplumber` 段直接保留。

### 3.4 `src/meal.py` — 架构集成冲突

这是**最复杂的冲突**，涉及两种不同的 parser 集成架构：

| | `better-pymupdf4llm` | `try-fitz` |
|---|---|---|
| **hash 计算** | `options: parser_config.get("options", parser_config.get("pymupdf4llm", {}))` | `options: parser_config.get(algorithm, {})` |
| **config_snapshot** | `"options": parser_config.get("pymupdf4llm", {})` | `"options": parser_config.get(parser_config.get("algorithm", "pymupdf4llm"), {})` |
| **解析调用** | 仍用 `from src.parser import parse_all_pdfs` | 改用 `ParserRegistry.get(algorithm, parser_options)` |
| **缓存隔离** | 无 parser_hash 隔离 | `parser_hash` 隔离不同解析器的缓存目录 |
| **输出格式** | 支持 `.pages.json` 和 `.md` 双格式 | 统一输出 `.md`（通过 `BaseParser` 接口） |

**关键判断**：`try-fitz` 的架构是**上位替代**——它引入了 `ParserRegistry` + `BaseParser` 策略模式，使得 `better-pymupdf4llm` 的 `page_chunks` 功能可以通过 `PyMuPDF4LLMParser` 适配器实现。`try-fitz` 的 `parser_hash` 隔离也是 `better-pymupdf4llm` 缺失但需要的功能。

**结论**：`try-fitz` 的架构应为主框架，`better-pymupdf4llm` 的 `page_chunks` 逻辑应融入 `PyMuPDF4LLMParser` 适配器（实际上 `try-fitz` 已经这么做了）。

## 四、归并策略推荐

### 推荐策略：`cleaning` 先入 → `try-fitz` 架构合入 → `better-pymupdf4llm` 功能融入

**归并顺序与理由**：

```
dev ← cleaning ← try-fitz ← better-pymupdf4llm（手动解决冲突）
```

#### Step 1: 合并 `cleaning` 到 `dev`（无冲突）

`cleaning` 是纯 bug 修复和小功能增强，与任何分支都不冲突，应最先合入作为稳定基线。

#### Step 2: 合并 `try-fitz` 到 `dev`（无冲突）

`try-fitz` 引入策略模式架构（`BaseParser`、`ParserRegistry`、`PyMuPDF4LLMParser`、`FitzPdfPlumberParser`），这是后续所有 parser 功能的**架构基础**。与 `cleaning` 无冲突，可直接合入。

#### Step 3: 合并 `better-pymupdf4llm` 到 `dev`（需手动解决 4 个冲突文件）

这是最关键的一步。`better-pymupdf4llm` 的**功能价值**需要保留，但其**实现方式**已被 `try-fitz` 的架构覆盖：

| 冲突文件 | 解决策略 |
|----------|----------|
| `src/parser.py` | **保留 try-fitz 架构**。`better-pymupdf4llm` 的 `page_chunks` 功能已由 `PyMuPDF4LLMParser` 适配器实现，`parse_pdf` 的 `page_chunks` 参数不再需要。`cleaning` 的 `_inject_page_markers` 也被废弃。`src/parser.py` 最终应保留 `try-fitz` 版本（或考虑将其标记为 legacy，因为 `try-fitz` 的 `ParserRegistry` 才是正式入口）。 |
| `tests/test_chunker.py` | **合并两边测试**。删除基于 `<!-- page: N -->` 标记的测试（`TestExtractPageMarkers` 等），保留 `better-pymupdf4llm` 的 `page_chunks` 测试和 `cleaning` 的非标记相关测试。 |
| `config.yaml` | **合并配置**。`pymupdf4llm` 段采用 `better-pymupdf4llm` 的优化参数（`page_chunks: true` 等），`fitz_pdfplumber` 段保留 `try-fitz` 的配置。 |
| `src/meal.py` | **采用 try-fitz 架构**。`parser_hash` 隔离和 `ParserRegistry` 调用方式保留，但需要将 `better-pymupdf4llm` 的 `page_chunks` 感知逻辑（`.pages.json` 格式检测、`process_parsed_files_page_aware` 调用）融入 `try-fitz` 的 `_parse_pdfs_with_registry` 方法中。 |

### 为什么不选其他顺序？

| 替代方案 | 问题 |
|----------|------|
| `better-pymupdf4llm` 先入 | `page_chunks` 方案是"半成品"——它直接修改 `parse_pdf` 签名而非通过策略模式，后续 `try-fitz` 合入时需大量重构 |
| `try-fitz` 先于 `cleaning` | 虽无冲突，但 `cleaning` 包含 bug 修复，应先建立稳定基线 |
| 三路 octopus merge | Git octopus 策略不支持有冲突的合并，且无法精细控制冲突解决 |
| Rebase 后合并 | 三条分支都有大量提交，rebase 工作量大且容易引入隐蔽错误 |

### 最终架构愿景

合并完成后的架构：

```
src/parsers/              # try-fitz 引入的策略模式
├── base.py               # BaseParser, ParsedPage, ParseResult
├── registry.py           # ParserRegistry
├── pymupdf4llm_parser.py # 内置 page_chunks 支持（来自 better-pymupdf4llm 的功能）
└── fitz_pdfplumber_parser.py  # 新链路

src/parser.py             # 保留为 legacy 兼容入口，或标记 deprecated
src/chunker.py            # 包含 page-aware chunking（来自 better-pymupdf4llm）
src/meal.py               # 通过 ParserRegistry 调用，parser_hash 隔离缓存
config.yaml               # pymupdf4llm 优化参数 + fitz_pdfplumber 配置
```

## 五、执行步骤

1. **切换到 dev 分支**
2. **合并 cleaning**（`git merge --no-ff cleaning`）→ 无冲突，直接提交
3. **合并 try-fitz**（`git merge --no-ff try-fitz`）→ 无冲突，直接提交
4. **合并 better-pymupdf4llm**（`git merge --no-ff better-pymupdf4llm`）→ 4 个冲突文件需手动解决：
   - `src/parser.py`：接受 try-fitz 版本（或标记 legacy）
   - `tests/test_chunker.py`：合并测试，删除标记相关测试
   - `config.yaml`：合并两边的配置项
   - `src/meal.py`：以 try-fitz 架构为主，融入 page_chunks 感知逻辑
5. **运行 lint 和测试**：`pixi run lint` + `pixi run test`，确保合并后代码质量
6. **推送 dev 到远端**

## 六、风险与注意事项

- `src/parser.py` 合并后可能需要考虑是否保留为 legacy 入口，还是完全迁移到 `src/parsers/` 模块
- `better-pymupdf4llm` 的 `process_parsed_files_page_aware` 在 `src/chunker.py` 中，该函数与 `try-fitz` 的 `BaseParser` 输出格式（统一 `.md`）存在设计张力——需要确认 `PyMuPDF4LLMParser` 输出的是合并的 `.md` 还是保留 `.pages.json` 格式
- 合并完成后应进行一次完整的端到端测试，验证两种 parser 链路均可正常工作
