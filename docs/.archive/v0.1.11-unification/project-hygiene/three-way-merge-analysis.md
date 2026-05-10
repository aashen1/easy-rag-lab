# 三路并行分支归并分析与策略

## 一、分支概览

三条分支均基于同一个基点 `3a56224`（dev 当前 HEAD），无分叉偏移。

| 分支                   | 提交数 | 功能定位                                   |
| -------------------- | --- | -------------------------------------- |
| `cleaning`           | 13  | 积压 issue 清理、bug 修复、小功能增强               |
| `better-pymupdf4llm` | 8   | 重构 PyMuPDF4LLM 解析逻辑，增加 page\_chunks 支持 |
| `try-fitz`           | 8   | 新增 PyMuPDF+pdfplumber 解析链路，策略模式架构      |

## 二、冲突分析

### 2.1 单独合并到 dev（无前置合并）

三条分支单独合并均无冲突，因为它们从同一基点出发。

### 2.2 两两组合冲突

| 合并顺序                              | 冲突文件                                     | 冲突性质           |
| --------------------------------- | ---------------------------------------- | -------------- |
| `cleaning` ↔ `better-pymupdf4llm` | `src/parser.py`, `tests/test_chunker.py` | 语义冲突（两种页面感知方案） |
| `cleaning` ↔ `try-fitz`           | ✅ 无冲突                                    | 互不干扰           |
| `better-pymupdf4llm` ↔ `try-fitz` | `config.yaml`, `src/meal.py`             | 架构冲突           |

### 2.3 三路全部合并

在 `cleaning` + `try-fitz`（无冲突）的基础上再合并 `better-pymupdf4llm`，冲突文件增至 4 个：`src/parser.py`、`tests/test_chunker.py`、`config.yaml`、`src/meal.py`。

## 三、冲突深度解析

### 3.1 `src/parser.py` — 核心语义冲突

两个分支对"如何让解析结果携带页面信息"给出了**互斥的方案**：

| <br />                 | `cleaning` 分支                   | `better-pymupdf4llm` 分支                                        |
| ---------------------- | ------------------------------- | -------------------------------------------------------------- |
| **方案**                 | 注入 HTML 注释标记 `<!-- page: N -->` | 使用 pymupdf4llm 原生 `page_chunks=True`                           |
| **新增 import**          | `import re`                     | `import json`                                                  |
| **新增函数**               | `_inject_page_markers()`        | 无新函数，修改 `parse_pdf` 签名                                         |
| **`parse_pdf`** **签名** | `(pdf_path, **kwargs) -> str`   | `(pdf_path, page_chunks=False, **kwargs) -> str \| list[dict]` |
| **返回值**                | 始终返回 str（内嵌标记）                  | str 或 list\[dict]（结构化数据）                                       |
| **输出格式**               | `.md` 文件                        | `.md` 或 `.pages.json` 文件                                       |

**关键判断**：`better-pymupdf4llm` 的 `page_chunks` 方案是 `try-fitz` 策略模式架构的**前置依赖**——`try-fitz` 的 `PyMuPDF4LLMParser` 适配器内部就是调用 `page_chunks=True`。而 `cleaning` 的 `_inject_page_markers` 是一种**权宜之计**，在 `page_chunks` 不可用时作为降级手段。

**结论**：`cleaning` 的 `_inject_page_markers` 方案被 `page_chunks` 完全替代，应从 cleaning 分支中预先移除。

### 3.2 `tests/test_chunker.py` — 测试代码冲突

`cleaning` 新增了 `TestExtractPageMarkers`、`TestExtractHeadings`、`TestGetPageRange` 等测试类（基于 `<!-- page: N -->` 标记），以及 `test_chunk_metadata_with_page_markers` / `test_chunk_metadata_without_page_markers` 测试。

`better-pymupdf4llm` 修改了导入列表（增加 `chunk_text_page_aware`, `process_parsed_files_page_aware`），并新增了基于 `page_chunks` 的测试。

**结论**：标记相关测试随 `_inject_page_markers` 一起移除；`headings` 提取测试保留（该功能仍有价值）。

### 3.3 `config.yaml` — 配置结构冲突

`better-pymupdf4llm` 在 `parser.pymupdf4llm` 下新增了 `page_chunks: true`、`force_text`、`ignore_code`、`use_ocr` 等优化参数。

`try-fitz` 新增了 `parser.fitz_pdfplumber` 整个子配置段，同时 `pymupdf4llm` 下保持旧参数。

**结论**：需要合并两边的配置项。`pymupdf4llm` 段采用 `better-pymupdf4llm` 的优化版本，`fitz_pdfplumber` 段保留 `try-fitz` 的配置。

### 3.4 `src/meal.py` — 架构集成冲突

这是**最复杂的冲突**，涉及两种不同的 parser 集成架构：

| <br />      | `better-pymupdf4llm`                                                          | `try-fitz`                                         |
| ----------- | ----------------------------------------------------------------------------- | -------------------------------------------------- |
| **hash 计算** | `options: parser_config.get("options", parser_config.get("pymupdf4llm", {}))` | `options: parser_config.get(algorithm, {})`        |
| **解析调用**    | 仍用 `from src.parser import parse_all_pdfs`                                    | 改用 `ParserRegistry.get(algorithm, parser_options)` |
| **缓存隔离**    | 无 parser\_hash 隔离                                                             | `parser_hash` 隔离不同解析器的缓存目录                         |
| **输出格式**    | 支持 `.pages.json` 和 `.md` 双格式                                                  | 统一输出 `.md`（通过 `BaseParser` 接口）                     |

**关键判断**：`try-fitz` 的架构是**上位替代**——`ParserRegistry` + `BaseParser` 策略模式使得 `better-pymupdf4llm` 的 `page_chunks` 功能可通过 `PyMuPDF4LLMParser` 适配器实现。`parser_hash` 隔离也是 `better-pymupdf4llm` 缺失但需要的功能。

**结论**：`try-fitz` 的架构应为主框架，`better-pymupdf4llm` 的 `page_chunks` 逻辑已由 `PyMuPDF4LLMParser` 适配器覆盖。

## 四、归并策略

### 推荐方案：预处理 cleaning → 三路 `--no-ff` merge

```
dev ← cleaning(预处理后) ← try-fitz ← better-pymupdf4llm(手动解决冲突)
```

### 4.1 为什么选择 merge 而非 rebase

| 维度            | `--no-ff` merge              | rebase 后 merge           |
| ------------- | ---------------------------- | ------------------------ |
| **历史保真**      | ✅ 保留分支上每个开发 commit 的原始粒度和时间戳 | ❌ 重写 commit hash，原始时间线丢失 |
| **冲突解决**      | 冲突只在 merge commit 中解决一次      | 每次 rebase 都可能遇到冲突，需反复解决  |
| **可回溯性**      | ✅ 可清晰看到每个分支的完整开发过程           | ❌ rebase 后难以追溯原始分支边界     |
| **安全性**       | ✅ 非破坏性操作，随时可 revert          | ❌ 破坏性操作，rebase 出错难以恢复    |
| **commit 整洁** | 分支内 commit 保持原样（含 WIP 等）     | 历史更线性，但丢失了分支上下文          |

**选择** **`--no-ff`** **merge 的理由**：

1. **你明确希望保留各分支上开发 commit 的粒度**——`--no-ff` merge 完美满足，每个分支的 commit 原样保留在 dev 历史中，merge commit 作为功能级分界线
2. **三条分支共 29 个 commit**，rebase 需要逐个处理冲突，工作量大且风险高
3. **并行开发的分支历史本身就是有价值的上下文**——merge commit 清晰标记了"这三组改动是并行开发的"
4. **`--no-ff`** **产生的 merge commit 可以撰写功能级描述**，让 dev 分支的演进一目了然

### 4.2 预处理：在 cleaning 分支中 revert 页面标记权宜方案

**目标**：将 cleaning 分支中与 `better-pymupdf4llm` 冲突的"权宜之计"预先移除，使后续合并更顺畅。

**需要 revert 的 commit**：`056886f`（`feat: add page number markers and heading metadata to chunks (INV-010)`）

**但这个 commit 是"混合型"的**，包含两类改动：

1. **应移除的**（被 `page_chunks` 方案替代）：

   * `src/parser.py`：`_inject_page_markers()` 函数及其调用

   * `src/chunker.py`：`_extract_page_markers()`、`_get_page_range()` 函数及其调用

   * `src/semantic_chunker.py`：同上（与 chunker.py 对称的改动）

   * `tests/test_parser.py`：`TestInjectPageMarkers` 测试类

   * `tests/test_chunker.py`：`TestExtractPageMarkers`、`TestGetPageRange` 测试类

2. **应保留的**（仍有独立价值，不被其他分支覆盖）：

   * `src/chunker.py` / `src/semantic_chunker.py`：`_extract_headings()` 函数

   * `src/chunker.py` / `src/semantic_chunker.py`：chunk 元数据中 `headings` 字段

   * `src/chunker.py` / `src/semantic_chunker.py`：`::chunk::` 分隔符（替代 `_`）

   * `tests/test_chunker.py`：`TestExtractHeadings` 测试类

   * `tests/test_chunker.py`：chunk\_id 格式断言更新

**预处理方案**：不能简单 `git revert 056886f`，因为会丢失有价值部分。采用**手动编辑**方式：

1. 切换到 `cleaning` 分支
2. 手动编辑以下文件，移除页面标记相关代码，保留 headings 和 chunk\_id 改动：

   * `src/parser.py`：删除 `import re`、`_inject_page_markers()` 函数、`md_text = _inject_page_markers(md_text)` 调用

   * `src/chunker.py`：删除 `import re`、`_extract_page_markers()`、`_get_page_range()` 函数及其在 `process_parsed_files` 中的调用；保留 `_extract_headings()`、`headings` 字段、`::chunk::` 分隔符

   * `src/semantic_chunker.py`：同上

   * `tests/test_parser.py`：删除 `TestInjectPageMarkers` 测试类及其导入

   * `tests/test_chunker.py`：删除 `TestExtractPageMarkers`、`TestGetPageRange` 测试类及其导入；保留 `TestExtractHeadings`、chunk\_id 格式断言
3. 提交：`refactor: remove page marker injection in favor of page_chunks approach (revert INV-010 partial)`

**预处理后的效果**：

* `cleaning` ↔ `better-pymupdf4llm` 在 `src/parser.py` 上的冲突**消失**（cleaning 不再修改 parser.py）

* `tests/test_chunker.py` 的冲突**大幅简化**（只剩导入列表和新增测试类的合并，不再有方案冲突）

* `src/chunker.py` 的自动合并**可能成功**（两边修改不同区域：cleaning 改 headings/chunk\_id，better-pymupdf4llm 新增 page\_aware 函数）

### 4.3 `src/parser.py` 的最终处置

**不保留 legacy 入口**。合并完成后 `src/parser.py` 应被删除或完全重定向到 `src/parsers/` 模块，理由：

1. `try-fitz` 的 `ParserRegistry` 是唯一的正式入口
2. `better-pymupdf4llm` 的 `parse_pdf(page_chunks=True)` 功能已由 `PyMuPDF4LLMParser` 适配器实现
3. 保留两个入口会造成调用者困惑

**具体做法**：在合并 `better-pymupdf4llm` 解决冲突时，将 `src/parser.py` 重写为对 `src/parsers/` 的薄转发层，并在文件头部标注 deprecated。后续可单独 commit 删除该文件。

### 4.4 Merge Commit Message 规范

每个 merge commit 使用 `--no-ff`，撰写英文功能级描述：

```
# Step 1: cleaning 合并
Merge branch 'cleaning' into dev

Consolidate backlog issue fixes and minor enhancements:
- Fix BUG-017: pytest basetemp FileExistsError on Windows
- Add context length control (FEAT-023)
- Add tokenizer diff analysis script (INV-015)
- Add include_parent parameter to normalize_source
- Add overlap comparison experiment config (OPT-007)
- Update chunk_id format to ::chunk:: separator (RF-013)
- Add heading metadata extraction for chunks
- Style and import cleanup across eval and test modules

# Step 2: try-fitz 合并
Merge branch 'try-fitz' into dev

Introduce multi-parser framework with strategy pattern:
- Add parser abstraction layer (BaseParser, ParseResult, ParsedPage)
- Add ParserRegistry with lazy import support
- Add PyMuPDF4LLM parser adapter with page_chunks support
- Add FitzPdfPlumber parser with table extraction and column detection
- Integrate ParserRegistry into meal pipeline with parser hash isolation
- Extend config.yaml with fitz_pdfplumber parser settings

# Step 3: better-pymupdf4llm 合并
Merge branch 'better-pymupdf4llm' into dev

Optimize PyMuPDF4LLM parsing and add page-aware chunking:
- Optimize pymupdf4llm params (force_text, ignore_code, use_ocr, etc.)
- Add page-aware chunking pipeline (chunk_text_page_aware, process_parsed_files_page_aware)
- Include parser options in config hash and snapshot
- Update PDF parsing docs and add optimization guides

Conflicts resolved:
- src/parser.py: deprecated in favor of src/parsers/ module
- config.yaml: merged pymupdf4llm optimized params with fitz_pdfplumber config
- src/meal.py: adopted ParserRegistry architecture, integrated page_chunks awareness
- tests/test_chunker.py: consolidated page-aware and heading extraction tests
```

## 五、执行步骤

### Phase 1: 预处理 cleaning 分支

1. `git checkout cleaning`
2. 手动编辑 `src/parser.py`：移除 `import re`、`_inject_page_markers()` 函数及其调用
3. 手动编辑 `src/chunker.py`：移除 `import re`、`_extract_page_markers()`、`_get_page_range()` 及其调用；保留 `_extract_headings()`、`headings` 字段、`::chunk::` 分隔符
4. 手动编辑 `src/semantic_chunker.py`：同上
5. 手动编辑 `tests/test_parser.py`：移除 `TestInjectPageMarkers` 及其导入
6. 手动编辑 `tests/test_chunker.py`：移除 `TestExtractPageMarkers`、`TestGetPageRange` 及其导入；保留 `TestExtractHeadings`
7. `pixi run lint` + `pixi run test` 验证
8. 提交：`refactor: remove page marker injection in favor of page_chunks approach`
9. `git push origin cleaning`

### Phase 2: 三路合并到 dev

1. `git checkout dev`
2. `git merge --no-ff cleaning` → 无冲突，使用上述 commit message
3. `git merge --no-ff try-fitz` → 无冲突，使用上述 commit message
4. `git merge --no-ff better-pymupdf4llm` → 解决剩余冲突：

   * `src/parser.py`：重写为 deprecated 转发层

   * `config.yaml`：合并 pymupdf4llm 优化参数 + fitz\_pdfplumber 配置

   * `src/meal.py`：采用 ParserRegistry 架构，融入 page\_chunks 感知

   * `tests/test_chunker.py`：合并测试
5. `pixi run lint` + `pixi run test` 验证
6. `git push origin dev`

### Phase 3: 清理

1. 可选：删除本地和远端的三个 feature 分支
2. 可选：后续单独 commit 删除 `src/parser.py` deprecated 入口

## 六、风险与注意事项

* **预处理后仍可能有** **`src/chunker.py`** **的自动合并冲突**：cleaning 保留了 `_extract_headings` 和 `::chunk::` 改动，better-pymupdf4llm 新增了 `chunk_text_page_aware` 等函数。由于两边修改不同区域，自动合并大概率成功，但需验证。

* **`src/meal.py`** **是最复杂的冲突**：`try-fitz` 的 `_parse_pdfs_with_registry` 方法目前统一输出 `.md`，而 `better-pymupdf4llm` 的 `page_chunks` 感知逻辑需要 `.pages.json` 支持。合并时需要决定：是让 `PyMuPDF4LLMParser` 在 `page_chunks=True` 时输出 `.pages.json`，还是统一由 `BaseParser` 输出 `.md` 并在 chunker 层面处理页面信息。

* **合并完成后应进行端到端测试**，验证两种 parser 链路均可正常工作。
