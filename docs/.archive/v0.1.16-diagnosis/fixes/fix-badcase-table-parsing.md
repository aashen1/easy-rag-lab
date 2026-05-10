# Plan: 修复 Bad Case — 食品饮料ETF周报表格解析质量问题

## 问题描述

**Bad Case ID**: `bc_20260502_073922_a0f321`
**查询**: 香飘飘的2026年3月13日收盘价？
**期望答案**: 13.04 元
**实际结果**: 系统回答"无法回答"，检索完全失败

**根因**: pymupdf4llm Layout 模式将第14页的长表格（表6：食品饮料板块重点公司盈利预测与估值）解析为4列 Markdown 表格，但每个单元格内用 `<br>` 堆叠了所有公司的数据。例如：

```
|证券代码<br>证券简称|收盘价<br>（0313）<br>总市值<br>（亿元）|EPS<br>TTM<br>2025E|PE<br>TTM<br>2025E|
|600519.SH<br>贵州茅台<br>000858.SZ<br>五粮液<br>...<br>603711.SH<br>香飘飘<br>...|1,413.64<br>17,702.6<br>...<br>13.04<br>53.8<br>...|...|...|
```

香飘飘与其收盘价 13.04 分别出现在不同位置，被 `<br>` 分隔，无法正确关联。后续分块时进一步碎片化，导致检索完全失效。

## 调研结论

### 三种解析方案对比

| 方案                          | 表格处理方式                          | table\_strategy 可控性                | 对本表格的预期效果  |
| --------------------------- | ------------------------------- | ---------------------------------- | ---------- |
| pymupdf4llm Layout 模式（当前默认） | MuPDF Layout 内置表格检测             | ❌ 不支持，参数被静默忽略                      | 差：长表格被压成单行 |
| pymupdf4llm Legacy 模式       | pymupdf\_rag 内置 `find_tables()` | ✅ 支持 `lines_strict`/`lines`/`text` | 待验证：可能更好   |
| fitz + pdfplumber           | pdfplumber `find_tables()` 精确提取 | ✅ 完全可控                             | 待验证：理论上最好  |

### 关键发现

1. pymupdf4llm Layout 模式的 `table_strategy` 参数**完全不生效**，被 `**kwargs` 静默忽略
2. pymupdf4llm Legacy 模式通过 `use_layout(False)` 切换，支持 `table_strategy` 参数
3. fitz+pdfplumber 已有完整实现（`FitzPdfPlumberParser`），但未作为默认链路

## 实施计划

### Step 1: 编写对比测试脚本

创建 `scripts/compare_parsers_table.py`，针对 bad case 的 PDF 第14页，分别用三种方式解析并输出结果：

1. **pymupdf4llm Layout 模式**（当前默认，作为 baseline）
2. **pymupdf4llm Legacy 模式**（`use_layout(False)`，测试 `table_strategy="text"` 和 `"lines"`）
3. **fitz + pdfplumber**（当前配置 + 调整 `table_strategy` 为 `"text"` 对比）

脚本输出每种的第14页 Markdown 内容，重点看表格是否正确展开为多行。

### Step 2: 运行对比测试，确定最优方案

根据输出结果判断：

* 如果 pymupdf4llm Legacy 模式能正确解析 → 方案A：切换到 Legacy 模式

* 如果 fitz+pdfplumber 能正确解析 → 方案B：切换默认解析器为 fitz\_pdfplumber

* 如果两者都能 → 选效果更好、对整体文档影响更小的方案

* 如果都不行 → 方案C：考虑混合策略或调参

### Step 3: 实施选定方案

根据 Step 2 结果，可能的实施路径：

**方案A: 切换 pymupdf4llm 到 Legacy 模式**

* 在 `PyMuPDF4LLMParser` 中添加 `use_layout` 配置项

* 修改 `config.yaml` 添加 `use_layout: false` 和 `table_strategy` 参数

* 需要验证 Legacy 模式对其他文档的影响

**方案B: 切换默认解析器为 fitz\_pdfplumber**

* 修改 `config.yaml` 中 `parser.algorithm` 为 `"fitz_pdfplumber"`

* 修复 pipeline.py 中硬编码读取 `pymupdf4llm` 子键的问题

* 需要验证 fitz\_pdfplumber 对其他文档的影响

**方案C: 混合策略（如果单一方案不够好）**

* 保持 pymupdf4llm 作为默认，但对表格密集页面使用 pdfplumber 补充

* 或在解析后增加表格质量检测，对低质量表格用 pdfplumber 重新提取

### Step 4: 重新解析该 PDF 并验证

1. 用选定方案重新解析 bad case 的 PDF（仅此一份）
2. 检查第14页表格是否正确展开
3. 重新运行该 PDF 的分块和索引流程
4. 验证 bad case 查询是否能正确召回

## 风险与注意事项

1. **Legacy 模式限制**: pymupdf4llm Legacy 模式缺少 Layout 模式的多栏检测、标题识别等高级功能
2. **pdfplumber 表格策略**: `text` 策略适合无边框表格但可能误检测，`lines` 策略更精确但依赖表格线
3. **Pipeline 兼容性**: 当前 pipeline.py 硬编码读取 `pymupdf4llm` 子键，切换到 fitz\_pdfplumber 需要修复此问题
4. **后续全量验证**: 本次只针对单个 PDF 验证，后续如需切换默认解析器，需全量回归测试
