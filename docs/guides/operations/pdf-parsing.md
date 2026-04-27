# PDF 解析指南：双引擎方案详解与最佳实践

<!-- status: active -->

> 最后更新: 2026-04-23

本文档介绍 Easy RAG Lab 系统中 PDF 解析环节的技术细节、参数配置和最佳实践。系统支持两种解析方案：

1. **pymupdf4llm**：LLM 友好的封装方案，开箱即用
2. **fitz_pdfplumber**：底层组合方案，精细控制

---

## 概述

### 方案选择总览

| 方案 | 特点 | 适用场景 |
|------|------|---------|
| **pymupdf4llm** | 开箱即用，Layout 模式自动处理多栏、表格、OCR | 快速部署，金融研报双栏排版 |
| **fitz_pdfplumber** | 精细控制，自定义噪声过滤、表格策略 | 需要调优特定场景，复杂表格处理 |

### 核心设计决策

| 决策 | 选择 | 理由 |
|------|------|------|
| 解析引擎 | 双引擎支持 | 不同场景有不同最优解 |
| 页级输出 | 默认启用 | RAG 系统需要页码关联，支持检索结果溯源到具体页码 |
| 输出格式 | `.pages.json` | 页级 JSON 格式，每页独立 dict，含元数据 |

---

## 方案一：pymupdf4llm

[pymupdf4llm](https://pymupdf.readthedocs.io/en/latest/pymupdf4llm/) 是 PyMuPDF 的 LLM 友好封装，能将 PDF 页面转换为结构化的 Markdown 文本。

### 核心特性

| 特性 | 说明 |
|------|------|
| 解析引擎 | pymupdf4llm |
| Layout 模式 | `use_layout(True)`（默认） |
| 多栏检测 | ✅ 自动（Layout 模块内置） |
| 表格识别 | ✅ 内置（转换为 Markdown 表格） |
| OCR 兜底 | ✅ 自动触发 |

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

## 方案二：fitz_pdfplumber

`fitz_pdfplumber` 是一种底层组合方案，使用 fitz (PyMuPDF) 进行文本提取和布局分析，使用 pdfplumber 进行精确的表格提取。

### 核心设计理念

```
┌─────────────────────────────────────────────────────────────┐
│                    fitz_pdfplumber 解析流程                  │
├─────────────────────────────────────────────────────────────┤
│  PDF 文件                                                    │
│     │                                                        │
│     ├─→ fitz (PyMuPDF)                                       │
│     │     ├─ 文本块提取                                       │
│     │     ├─ 多栏检测                                         │
│     │     ├─ 页眉页脚过滤                                     │
│     │     └─ 噪声过滤                                         │
│     │                                                        │
│     ├─→ pdfplumber                                           │
│     │     └─ 表格提取（精确边框识别）                          │
│     │                                                        │
│     └─→ 合并：表格替换重叠文本区域                             │
│           │                                                  │
│           ↓                                                  │
│     Markdown 输出                                            │
└─────────────────────────────────────────────────────────────┘
```

### 核心特性

| 特性 | 说明 |
|------|------|
| 文本提取 | fitz (PyMuPDF) |
| 表格提取 | pdfplumber（精确边框识别） |
| 多栏检测 | ✅ 自实现（基于文本块位置分析） |
| 页眉页脚过滤 | ✅ 可配置区域比例 |
| 噪声过滤 | ✅ 正则表达式模式匹配 |
| 标题检测 | ✅ 基于字号和加粗状态 |

### 参数详解

#### 当前推荐配置

```yaml
parser:
  algorithm: "fitz_pdfplumber"
  fitz_pdfplumber:
    header_filter: true
    footer_filter: true
    header_zone_ratio: 0.10
    footer_zone_ratio: 0.10
    table_strategy: "lines"
    table_settings:
      snap_tolerance: 5
      join_tolerance: 5
      edge_min_length: 10
      intersection_x_tolerance: 5
      intersection_y_tolerance: 5
    column_detection: true
    noise_patterns:
      - "请务必阅读.{0,20}声明"
      - "^\\s*\\d+\\s*$"
      - "^\\s*\\d+\\s*/\\s*\\d+\\s*$"
      - "(?:内部资料|机密|仅供参考).{0,30}$"
      - "^(?:www\\.|http).+$"
```

#### 参数逐一说明

##### `header_filter: true` / `footer_filter: true`

- **作用**：启用页眉/页脚区域过滤
- **推荐值**：`true`（金融研报的页眉页脚通常包含公司 logo、页码等噪声）
- **联动**：与 `header_zone_ratio` / `footer_zone_ratio` 配合使用

##### `header_zone_ratio: 0.10` / `footer_zone_ratio: 0.10`

- **作用**：定义页眉/页脚区域占页面高度的比例
- **推荐值**：`0.10`（即页面顶部/底部 10% 的区域）
- **过滤逻辑**：位于该区域内且文本长度 < 80 字符的文本块会被过滤

##### `table_strategy: "lines"`

- **作用**：pdfplumber 表格检测策略
- **可选值**：
  - `"lines"`：基于表格线检测（推荐，适合有边框的表格）
  - `"text"`：基于文本位置推断（适合无边框表格）
  - `"explicit"`：仅使用显式表格线

##### `table_settings`

pdfplumber `find_tables()` 的详细配置：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `snap_tolerance` | 5 | 线段对齐容差 |
| `join_tolerance` | 5 | 线段连接容差 |
| `edge_min_length` | 10 | 最小边长度 |
| `intersection_x_tolerance` | 5 | 水平交叉容差 |
| `intersection_y_tolerance` | 5 | 垂直交叉容差 |

##### `column_detection: true`

- **作用**：启用多栏检测
- **推荐值**：`true`
- **检测逻辑**：基于文本块中心点分布，判断是否为双栏布局
- **排序策略**：双栏时按"左栏优先、从上到下"排序

##### `noise_patterns`

- **作用**：正则表达式列表，匹配需要过滤的噪声文本
- **默认模式**：
  - 页码：`^\s*\d+\s*$`
  - 页码分式：`^\s*\d+\s*/\s*\d+\s*$`
  - 声明文本：`请务必阅读.{0,20}声明`
  - URL：`^(?:www\.|http).+$`
  - 机密标记：`(?:内部资料|机密|仅供参考).{0,30}$`

### 解析流程详解

#### 1. 文本块提取（fitz）

```python
# 使用 fitz 提取文本块
raw_blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]

# 提取每个块的：
# - 文本内容
# - 字号（用于标题检测）
# - 加粗状态（用于标题检测）
# - 边界框（用于位置排序和表格重叠检测）
```

#### 2. 表格提取（pdfplumber）

```python
# 使用 pdfplumber 提取表格
plumber_tables = page.find_tables(table_settings=settings)

# 转换为 Markdown 表格格式
md_table = _table_to_markdown(table.extract())
```

#### 3. 合并文本与表格

```python
# 表格替换重叠的文本区域
for text_block in text_blocks:
    if overlaps_table(text_block, table_blocks):
        remove(text_block)

# 按位置排序后输出
combined = text_blocks + table_blocks
combined.sort(key=lambda b: b.bbox[1])  # 按 y 坐标排序
```

### 标题检测机制

基于字号和加粗状态自动检测标题：

| 条件 | Markdown 级别 |
|------|---------------|
| 字号 > 16 且加粗 | `#` (H1) |
| 字号 > 14 且加粗 | `##` (H2) |
| 字号 > 12 且加粗 | `###` (H3) |
| 字号 > 11 且加粗且长度 < 100 | `####` (H4) |

### 与 pymupdf4llm 的关键差异

| 维度 | pymupdf4llm | fitz_pdfplumber |
|------|-------------|-----------------|
| **多栏检测** | Layout 模块内置 | 自实现（基于位置分析） |
| **表格提取** | Layout 模块内置 | pdfplumber 精确控制 |
| **页眉页脚过滤** | Layout 模块内置 | 区域比例 + 长度判断 |
| **噪声过滤** | 无内置 | 正则表达式模式匹配 |
| **标题检测** | 无内置 | 字号 + 加粗状态 |
| **OCR 支持** | ✅ 自动触发 | ❌ 需额外集成 |
| **参数控制力** | ⚠️ Layout 模式下受限 | ✅ 完全控制 |

---

## 双引擎对比与选择指南

### 功能对比矩阵

| 维度 | pymupdf4llm | fitz_pdfplumber |
|------|-------------|-----------------|
| **多栏检测** | ✅ 自动（Layout 模块） | ✅ 自实现 |
| **表格识别** | ✅ 内置 | ✅ pdfplumber 精细控制 |
| **页眉页脚过滤** | ✅ 参数支持 | ✅ 区域比例控制 |
| **噪声过滤** | ❌ 无内置 | ✅ 正则表达式 |
| **标题检测** | ❌ 无内置 | ✅ 字号 + 加粗 |
| **OCR 兜底** | ✅ 自动触发 | ❌ 需额外集成 |
| **LLM 友好输出** | ✅ Markdown | ✅ Markdown |
| **参数控制力** | ⚠️ Layout 模式下部分参数不可用 | ✅ 完全控制 |
| **部署复杂度** | ✅ 开箱即用 | ⚠️ 需调优参数 |

### 选择决策树

```
开始
  │
  ├─ 文档是否包含扫描页面？
  │   ├─ 是 → pymupdf4llm（内置 OCR）
  │   └─ 否 ↓
  │
  ├─ 是否需要精细控制噪声过滤？
  │   ├─ 是 → fitz_pdfplumber
  │   └─ 否 ↓
  │
  ├─ 表格是否复杂（合并单元格、嵌套表格）？
  │   ├─ 是 → fitz_pdfplumber（pdfplumber 更精确）
  │   └─ 否 ↓
  │
  ├─ 是否需要快速部署？
  │   ├─ 是 → pymupdf4llm（开箱即用）
  │   └─ 否 ↓
  │
  └─ 默认推荐 → pymupdf4llm
```

### 场景推荐

| 场景 | 推荐方案 | 理由 |
|------|---------|------|
| 金融研报（双栏排版） | pymupdf4llm | Layout 模式自动处理多栏 |
| 扫描件 PDF | pymupdf4llm | 内置 OCR 兜底 |
| 复杂表格文档 | fitz_pdfplumber | pdfplumber 表格提取更精确 |
| 需要自定义噪声过滤 | fitz_pdfplumber | 正则表达式灵活配置 |
| 快速原型验证 | pymupdf4llm | 开箱即用，无需调优 |
| 生产环境调优 | fitz_pdfplumber | 参数完全可控 |

---

## 对比实验方法

### 实验设计原则

1. **控制变量**：每次只改变一个参数或方案
2. **隔离缓存**：Meal 系统自动为不同配置生成独立缓存
3. **统一评估**：使用相同的测试集和评估指标

### 实验步骤

#### 1. 准备测试集

```bash
# 生成测试集（如果还没有）
pixi run python main.py --generate-test-set --num-questions 50
```

#### 2. 配置实验 A（pymupdf4llm）

```yaml
# config.yaml
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

#### 3. 运行实验 A

```bash
# 构建索引
pixi run python main.py --build-index

# 运行评估
pixi run python main.py --evaluate --test-set data/test_sets/default.jsonl

# 记录 Meal ID（如 meal_20260423_a1b2c3）
```

#### 4. 配置实验 B（fitz_pdfplumber）

```yaml
# config.yaml
parser:
  algorithm: "fitz_pdfplumber"
  fitz_pdfplumber:
    header_filter: true
    footer_filter: true
    header_zone_ratio: 0.10
    footer_zone_ratio: 0.10
    table_strategy: "lines"
    column_detection: true
```

#### 5. 运行实验 B

```bash
# 构建索引（Meal 系统会自动创建新的缓存目录）
pixi run python main.py --build-index

# 运行评估
pixi run python main.py --evaluate --test-set data/test_sets/default.jsonl

# 记录 Meal ID（如 meal_20260423_d4e5f6）
```

#### 6. 对比结果

```bash
# 查看两个 Meal 的评估报告
pixi run python main.py --compare-meals meal_20260423_a1b2c3 meal_20260423_d4e5f6
```

### 关键评估指标

| 指标 | 说明 | 关注点 |
|------|------|--------|
| **Faithfulness** | 回答对上下文的忠实度 | 解析质量是否影响幻觉 |
| **Answer Relevancy** | 回答与问题的相关性 | 解析是否保留关键信息 |
| **Context Precision** | 检索上下文的精确度 | 解析是否引入噪声 |
| **Context Recall** | 检索上下文的召回率 | 解析是否丢失信息 |

### 实验记录模板

```markdown
## 解析方案对比实验

### 实验配置
- 日期：YYYY-MM-DD
- 测试集：data/test_sets/default.jsonl
- 文档数量：N

### 实验组
| 组别 | 方案 | 关键参数 |
|------|------|---------|
| A | pymupdf4llm | header=false, footer=false, ignore_code=true |
| B | fitz_pdfplumber | header_filter=true, footer_filter=true, table_strategy=lines |

### 评估结果
| 指标 | A (pymupdf4llm) | B (fitz_pdfplumber) | 差异 |
|------|-----------------|---------------------|------|
| Faithfulness | X.XX | X.XX | +X.XX |
| Answer Relevancy | X.XX | X.XX | +X.XX |
| Context Precision | X.XX | X.XX | +X.XX |
| Context Recall | X.XX | X.XX | +X.XX |

### 结论
[记录实验发现和建议]
```

### 最小化对比实验

如果只想验证单一参数的影响：

```yaml
# 实验 A：fitz_pdfplumber 默认噪声过滤
parser:
  algorithm: "fitz_pdfplumber"
  fitz_pdfplumber:
    noise_patterns:
      - "请务必阅读.{0,20}声明"
      - "^\\s*\\d+\\s*$"

# 实验 B：fitz_pdfplumber 无噪声过滤
parser:
  algorithm: "fitz_pdfplumber"
  fitz_pdfplumber:
    noise_patterns: []  # 空列表 = 不过滤
```

Meal 系统会为两个配置生成不同的 hash，确保实验隔离。

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
