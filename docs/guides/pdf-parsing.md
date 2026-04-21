# PDF 解析指南：pymupdf4llm 详细说明与最佳实践

<!-- status: active -->

> 最后更新: 2026-04-22

本文档介绍 ASH Easy RAG 系统中 PDF 解析环节的技术细节、参数配置和最佳实践。

---

## 概述

系统使用 [pymupdf4llm](https://pymupdf.readthedocs.io/en/latest/pymupdf4llm/) 作为 PDF 解析引擎，它是 PyMuPDF 的 LLM 友好封装，能将 PDF 页面转换为结构化的 Markdown 文本。

### 核心设计决策

| 决策 | 选择 | 理由 |
|------|------|------|
| 解析引擎 | pymupdf4llm | LLM 友好的 Markdown 输出，内置 Layout 模式 |
| Layout 模式 | `use_layout(True)`（默认） | 金融研报双栏排版普遍，Layout 模块的多栏检测是核心能力 |
| 页级输出 | `page_chunks=True` | RAG 系统需要页码关联，支持检索结果溯源到具体页码 |
| 输出格式 | `.pages.json` | 页级 JSON 格式，每页独立 dict，含元数据 |

---

## Layout 模式详解

pymupdf4llm 默认启用 PyMuPDF Layout 模块（`use_layout(True)`），这是本系统的核心依赖。

### Layout 模式的优势

- **多栏检测**：自动识别双栏/多栏布局，正确排序阅读顺序（金融研报最常见需求）
- **图片/图表分类**：Layout 模块自动将内容分类为 picture/text/table
- **表格识别**：内置表格检测，将表格转换为 Markdown 表格格式
- **页眉页脚处理**：支持 `header`/`footer` 参数过滤
- **OCR 兜底**：自动对需要 OCR 的页面执行识别

### Layout 模式的限制

| 限制 | 说明 | 缓解措施 |
|------|------|---------|
| `ignore_images` 不生效 | Layout 模式下忽略此参数 | `write_images: false` 控制不写出图片文件 |
| `table_strategy` 不可用 | 需要 `use_layout(False)` | 依赖 Layout 模块内置表格识别 |
| `margins` 不可用 | 需要 `use_layout(False)` | `header: false`/`footer: false` 过滤页眉页脚 |
| `hdr_info` 不可用 | 需要 `use_layout(False)` | Layout 模块有内置噪声处理 |

> ⚠️ **不建议切换到 `use_layout(False)`**。放弃 Layout 模块意味着失去多栏检测能力，需要自行实现等价功能，得不偿失。

---

## 参数详解

### 当前推荐配置

```yaml
parser:
  algorithm: "pymupdf4llm"
  pymupdf4llm:
    header: false
    footer: false
    page_separators: false
    write_images: false
    page_chunks: true
    force_text: true
    ignore_code: true
    use_ocr: true
    ocr_language: "chi_sim+eng"
    show_progress: true
```

### 参数逐一说明

#### `header: false` / `footer: false`

- **作用**：过滤 PDF 页面的页眉和页脚区域
- **Layout 模式生效**：✅
- **推荐值**：`false`（金融研报的页眉页脚通常包含公司 logo、页码等噪声）
- **注意**：过滤不完全时，部分残留仍可能出现

#### `page_separators: false`

- **作用**：是否在每页末尾插入 `--- end of page=n ---` 分隔符
- **Layout 模式生效**：✅
- **推荐值**：`false`（当 `page_chunks=True` 时冗余，每页已是独立 dict）
- **联动**：`page_chunks=True` 时设为 `false`；`page_chunks=False` 时设为 `true`

#### `write_images: false`

- **作用**：是否将 PDF 中的图片保存为文件
- **Layout 模式生效**：✅
- **推荐值**：`false`（RAG 系统不需要图片文件，仅提取文本）
- **注意**：Layout 模式自动分类图片区域，此参数仅控制是否写出文件

#### `page_chunks: true`

- **作用**：启用页级输出，每个 PDF 页面返回独立字典
- **Layout 模式生效**：✅
- **推荐值**：`true`
- **输出格式**：`.pages.json` 文件，包含每页的 `text`、`metadata`、`toc_items`、`tables`
- **向后兼容**：设为 `false` 时输出传统 `.md` 文件

`.pages.json` 结构示例：

```json
[
  {
    "text": "该页 Markdown 文本...",
    "metadata": {
      "page_number": 1,
      "page_count": 20,
      "file_path": "report.pdf"
    },
    "toc_items": [...],
    "tables": [...]
  }
]
```

#### `force_text: true`

- **作用**：即使文本与图片/图形重叠也强制提取
- **Layout 模式生效**：✅
- **推荐值**：`true`（金融研报中常有数据标注叠加在图表上，这些文本对 RAG 有价值）

#### `ignore_code: true`

- **作用**：不将等宽文本行格式化为代码块
- **Layout 模式生效**：✅
- **推荐值**：`true`（金融研报中的财务数据表格有时被识别为等宽文本，错误地包裹在 `` ``` `` 代码块中）
- **注意**：如果文档中确实包含代码（如技术报告），应设为 `false`

#### `use_ocr: true`

- **作用**：自动对需要 OCR 的页面执行识别
- **Layout 模式生效**：✅
- **推荐值**：`true`（保留兜底能力，电子版研报触发概率低）

#### `ocr_language: "chi_sim+eng"`

- **作用**：OCR 识别使用的语言包
- **Layout 模式生效**：✅
- **推荐值**：`"chi_sim+eng"`（同时支持中文和英文 OCR）
- **前置条件**：需安装 Tesseract 中文语言包（`chi_sim`）

#### `show_progress: true`

- **作用**：显示解析进度条
- **Layout 模式生效**：✅
- **推荐值**：`true`

---

## 页感知分块流程

启用 `page_chunks=True` 后，分块流程从传统的"全文分块"变为"页感知分块"：

### 传统流程（`page_chunks=False`）

```
PDF → .md (全文 Markdown) → chunk_text() → JSONL (无页码)
```

### 页感知流程（`page_chunks=True`）

```
PDF → .pages.json (页级 JSON) → chunk_text_page_aware() → JSONL (含页码元数据)
```

### 页感知分块特性

- **每页独立分块**：不产生跨页 chunk，避免页边界处内容被截断
- **页码元数据**：每个 chunk 的 `metadata` 包含 `page_number` 字段
- **chunk_id 格式**：`{source_name}_p{page_number}_{chunk_index:03d}`（如 `report_p5_000`）
- **空页跳过**：空白页不产生 chunk
- **策略标识**：`metadata.strategy` 为 `"page_aware_fixed"`

### chunk 输出示例

```json
{
  "chunk_id": "report_p5_000",
  "text": "该页的 Markdown 文本内容...",
  "metadata": {
    "source": "annual_reports/report.pages.json",
    "page_number": 5,
    "category": "annual_report",
    "strategy": "page_aware_fixed",
    "chunk_index": "p5_000",
    "char_count": 2340,
    "token_count": 498,
    "start_token": 0,
    "end_token": 498
  }
}
```

---

## 参数传递机制

系统中有两个入口调用 PDF 解析：

### 1. pipeline.py（直接构建索引）

`RAGPipeline.build_index()` 调用 `parse_all_pdfs()` 时传递 `parser_options`：

```python
parse_results = parse_all_pdfs(
    input_dir=parser_config["input_dir"],
    output_dir=parser_config["output_dir"],
    force=force_parse,
    pdf_files=sampled_pdf_files,
    parser_options=parser_config.get("pymupdf4llm"),
)
```

### 2. meal.py（Meal 数据管理）

`MealManager.create_meal()` 调用 `parse_all_pdfs()` 时同样传递 `parser_options`：

```python
parse_all_pdfs(
    input_dir=parser_config["input_dir"],
    output_dir=str(parsed_dir),
    force=True,
    pdf_files=sampled_pdfs,
    parser_options=parser_config.get("pymupdf4llm"),
)
```

### Config Hash 与缓存失效

`compute_parser_config_hash()` 将 `pymupdf4llm` 的 options 纳入 hash 计算。当解析参数变更时，hash 值改变，Meal 系统的 ArtifactCache 会触发重新解析，确保缓存一致性。

---

## 最佳实践

### 金融研报推荐配置

```yaml
parser:
  algorithm: "pymupdf4llm"
  pymupdf4llm:
    header: false           # 过滤页眉噪声
    footer: false           # 过滤页脚噪声
    page_separators: false  # page_chunks=True 时冗余
    write_images: false     # 不需要图片文件
    page_chunks: true       # 启用页级输出
    force_text: true        # 保留图表上的数据标注
    ignore_code: true       # 避免财务数据被标记为代码块
    use_ocr: true           # OCR 兜底
    ocr_language: "chi_sim+eng"  # 中英文 OCR
    show_progress: true     # 显示进度
```

### 不同文档类型的调优建议

| 文档类型 | `ignore_code` | `force_text` | `page_chunks` | 备注 |
|---------|---------------|--------------|---------------|------|
| 金融年报 | `true` | `true` | `true` | 财务数据密集，需避免代码块误标 |
| 行业研报 | `true` | `true` | `true` | 双栏排版普遍，图表数据标注多 |
| 技术报告 | `false` | `true` | `true` | 可能包含合法代码块 |
| 简报/通知 | `true` | `false` | `true` | 单栏排版为主，图表叠加少 |

### 常见问题排查

| 问题 | 可能原因 | 解决方案 |
|------|---------|---------|
| 财务数据被包裹在代码块中 | `ignore_code: false` | 设置 `ignore_code: true` |
| 页眉页脚噪声混入正文 | `header: true` 或 `footer: true` | 设置 `header: false`、`footer: false` |
| 中文扫描件 OCR 结果乱码 | `ocr_language` 仅配置英文 | 设置 `ocr_language: "chi_sim+eng"`，确认 Tesseract 中文包已安装 |
| 双栏排版阅读顺序错乱 | 使用了 `use_layout(False)` | 保持默认 Layout 模式，不要切换 |
| chunk 无页码信息 | `page_chunks: false` | 设置 `page_chunks: true` 启用页级输出 |
| 解析参数变更后缓存未更新 | 旧版 `compute_parser_config_hash` 不含 options | 已在 v0.1.9 修复，options 纳入 hash 计算 |

---

## 与其他方案的对比

| 维度 | pymupdf4llm (Layout 模式) | fitz 原生 | pdfplumber |
|------|--------------------------|----------|------------|
| 多栏检测 | ✅ 自动 | ❌ 需自行实现 | ❌ 需自行实现 |
| 表格识别 | ✅ 内置 | ❌ 需自行实现 | ✅ 精细控制 |
| 图片分类 | ✅ 自动 | ⚠️ 需参数控制 | ⚠️ 需参数控制 |
| 页眉页脚过滤 | ✅ 参数支持 | ⚠️ margins 裁剪 | ⚠️ margins 裁剪 |
| OCR 兜底 | ✅ 自动触发 | ✅ 自动触发 | ❌ 需额外集成 |
| LLM 友好输出 | ✅ Markdown | ❌ 需自行转换 | ❌ 需自行转换 |
| 参数控制力 | ⚠️ Layout 模式下部分参数不可用 | ✅ 完全控制 | ✅ 完全控制 |

**结论**：对于金融研报场景，pymupdf4llm Layout 模式的多栏检测和 LLM 友好输出是核心优势，换库成本远大于参数精调。

---

## Fallback 到旧版傻瓜式解析

重构后的系统**完全兼容**旧版解析行为。只需修改 `config.yaml` 中的参数，整条链路（parser → chunker → meal/pipeline）会自动适配，无需改动任何代码。

### 旧版配置（v0.1.8 之前的默认行为）

```yaml
parser:
  algorithm: "pymupdf4llm"
  pymupdf4llm:
    header: true            # 保留页眉（旧版默认）
    footer: true            # 保留页脚（旧版默认）
    page_separators: true   # 插入页分隔符
    write_images: false
    page_chunks: false      # 关闭页级输出 → 输出 .md 文件
    force_text: true
    ignore_code: false      # 允许代码块格式化（旧版默认）
    use_ocr: true
    ocr_language: "eng"     # 仅英文 OCR（旧版默认）
    show_progress: true
```

### 新版配置（当前推荐）

```yaml
parser:
  algorithm: "pymupdf4llm"
  pymupdf4llm:
    header: false
    footer: false
    page_separators: false
    write_images: false
    page_chunks: true       # 启用页级输出 → 输出 .pages.json
    force_text: true
    ignore_code: true
    use_ocr: true
    ocr_language: "chi_sim+eng"
    show_progress: true
```

### 关键差异对照

| 参数 | 旧版 | 新版 | 影响 |
|------|------|------|------|
| `page_chunks` | `false` | `true` | **最核心差异**。`false` → 输出 `.md`（全文合并），`true` → 输出 `.pages.json`（每页独立 dict） |
| `header` | `true` | `false` | 页眉噪声是否混入正文 |
| `footer` | `true` | `false` | 页脚/页码噪声是否混入正文 |
| `ignore_code` | `false` | `true` | 财务表格是否被误标为代码块 |
| `ocr_language` | `"eng"` | `"chi_sim+eng"` | 中文扫描件 OCR 是否可用 |
| `page_separators` | `true` | `false` | 页分隔符（`page_chunks=true` 时冗余） |

### 自动适配机制

切换 `page_chunks` 参数后，下游链路会自动适配：

| 环节 | `page_chunks: false` | `page_chunks: true` |
|------|----------------------|---------------------|
| **parser 输出** | `.md` 文件 | `.pages.json` 文件 |
| **chunker 路径** | `process_parsed_files()` | `process_parsed_files_page_aware()` |
| **chunk 策略** | `fixed` | `page_aware_fixed` |
| **chunk 元数据** | 无 `page_number` | 含 `page_number` |
| **pipeline 路径** | `process_parsed_files()` | `process_parsed_files_page_aware()` |
| **meal 检测** | 扫描 `.md` 文件 | 扫描 `.pages.json` 文件 |

### 对比实验操作步骤

1. **创建旧版 Meal**：使用旧版 config.yaml 参数运行 `main.py --build-index`，Meal 系统会根据 parser hash 生成独立的缓存目录
2. **创建新版 Meal**：使用新版 config.yaml 参数运行 `main.py --build-index`，Meal 系统会生成另一个独立的缓存目录
3. **对比评估**：使用相同的 test set 分别对两个 Meal 运行评估，对比指标差异

> ⚠️ **重要**：由于 `compute_parser_config_hash()` 已将 options 纳入 hash 计算，切换参数后 Meal 系统会自动触发重新解析，不会复用旧版缓存。两个版本的解析产物和向量索引完全隔离，可安全对比。

### 最小化对比实验

如果只想验证单一参数的影响（如 `ignore_code`），只需修改该参数，其他保持不变：

```yaml
# 实验 A：ignore_code=false（旧版行为）
parser:
  pymupdf4llm:
    page_chunks: true
    ignore_code: false      # 仅此参数不同

# 实验 B：ignore_code=true（新版行为）
parser:
  pymupdf4llm:
    page_chunks: true
    ignore_code: true       # 仅此参数不同
```

Meal 系统会为两个配置生成不同的 hash，确保实验隔离。

---

## 相关文档

- [配置文件参考手册](../config-reference.md) — 完整的 `parser` 配置项说明
- [系统架构](../architecture.md) — 解析模块在整体架构中的位置
- [基线链路深度勘察](../pipeline-deep-audit.md) — 解析环节的详细问题分析
- [Meal 系统指南](meal-system.md) — ArtifactCache 与解析缓存机制
