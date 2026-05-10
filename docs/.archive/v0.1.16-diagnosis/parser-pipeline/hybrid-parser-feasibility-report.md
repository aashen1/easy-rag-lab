# 混合解析器可行性调研报告

## 背景

当前项目中存在两个 PDF 解析器：

| 解析器 | 优势 | 劣势 |
|--------|------|------|
| **pymupdf4llm** | Layout 模式自动处理多栏、OCR 兜底、开箱即用 | 表格解析质量差，复杂表格经常解析成一坨 |
| **fitz_pdfplumber** | pdfplumber 表格提取精确、参数完全可控 | 多栏检测是自实现的简单版本，无 OCR 支持 |

**用户需求**：结合两者优势 —— pymupdf4llm 的 Layout 模式（多栏检测）+ pdfplumber 的表格提取

---

## 技术可行性分析

### 关键发现：pymupdf4llm 的 `page_boxes` 结构

根据 [pymupdf4llm CHANGES.md](https://github.com/pymupdf/pymupdf4llm/blob/main/CHANGES.md) v0.2.8 的更新：

```python
# page_chunks=True 时返回的数据结构
{
    "text": "整页 Markdown 文本...",
    "metadata": {...},
    "page_boxes": [
        {
            "index": 0,                    # 0-based 阅读顺序索引
            "class": "table",              # 区域类型：table/section-header/body-text 等
            "bbox": pymupdf.IRect(...),    # 边界框坐标
            "pos": (start, stop)           # 在 text 中的位置切片
        },
        ...
    ]
}
```

**关键点**：
- `class="table"` 可以精确识别表格区域
- `bbox` 提供表格在页面上的坐标
- `pos` 提供表格文本在 Markdown 输出中的位置

### 混合方案设计

```
┌─────────────────────────────────────────────────────────────────┐
│                    混合解析流程                                   │
├─────────────────────────────────────────────────────────────────┤
│  1. pymupdf4llm (Layout 模式)                                    │
│     ├─ 多栏检测 ✅                                                │
│     ├─ OCR 兜底 ✅                                                │
│     ├─ 文本提取 ✅                                                │
│     └─ 输出: page_boxes (含表格 bbox 和 pos)                      │
│                                                                  │
│  2. 识别表格区域                                                  │
│     └─ 筛选 page_boxes 中 class="table" 的条目                    │
│                                                                  │
│  3. pdfplumber 表格提取                                           │
│     ├─ 使用 bbox 定位表格区域                                      │
│     └─ 重新提取表格 → Markdown                                    │
│                                                                  │
│  4. 合并结果                                                      │
│     ├─ 用 pdfplumber 表格替换 pymupdf4llm 表格                    │
│     └─ 输出最终 Markdown                                          │
└─────────────────────────────────────────────────────────────────┘
```

---

## 实现方案

### 方案 A：新增 `pymupdf4llm_pdfplumber` 解析器（推荐）

创建新解析器 `src/parsers/pymupdf4llm_pdfplumber_parser.py`：

```python
class PyMuPDF4LLMPdfPlumberParser(BaseParser):
    """混合解析器：pymupdf4llm Layout 模式 + pdfplumber 表格提取

    流程：
    1. pymupdf4llm 提取整页 Markdown（保留多栏检测）
    2. 从 page_boxes 识别表格区域
    3. pdfplumber 重新提取表格
    4. 替换原表格文本
    """

    def parse(self, pdf_path: str) -> ParseResult:
        # 1. pymupdf4llm 提取
        result = pymupdf4llm.to_markdown(
            pdf_path,
            page_chunks=True,
            **self._options
        )

        pages = []
        for page_data in result:
            text = page_data["text"]
            page_boxes = page_data.get("page_boxes", [])

            # 2. 识别表格区域
            table_boxes = [b for b in page_boxes if b["class"] == "table"]

            if table_boxes:
                # 3. pdfplumber 重新提取表格
                new_tables = self._extract_tables_with_pdfplumber(
                    pdf_path,
                    page_data["metadata"]["page_number"] - 1,
                    table_boxes
                )

                # 4. 替换表格文本
                text = self._replace_tables(text, table_boxes, new_tables)

            pages.append(ParsedPage(...))

        return ParseResult(pages=pages, ...)
```

**优势**：
- 不影响现有解析器
- 可独立测试和调优
- 用户可选择使用

**工作量**：中等（约 200-300 行代码）

---

### 方案 B：修改现有 `pymupdf4llm_parser.py`

在现有解析器中添加可选的表格增强模式：

```yaml
parser:
  algorithm: "pymupdf4llm"
  pymupdf4llm:
    page_chunks: true
    enhance_tables: true  # 新增参数
```

**优势**：
- 无需新增解析器
- 配置简单

**劣势**：
- 增加现有解析器复杂度
- 违反单一职责原则

---

## 技术风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| `page_boxes` 格式变化 | pymupdf4llm 版本升级可能导致兼容性问题 | 锁定 pymupdf4llm 版本，添加版本检查 |
| bbox 坐标系差异 | pymupdf4llm 和 pdfplumber 的坐标可能不一致 | 测试验证，必要时做坐标转换 |
| 表格替换位置计算 | `pos` 切片可能不准确 | 添加边界检查，fallback 到原表格 |
| 性能开销 | 双重解析增加耗时 | 仅在有表格的页面调用 pdfplumber |

---

## 实现步骤

### Phase 1：原型验证（1-2 小时）

1. 编写脚本验证 `page_boxes` 结构
2. 测试 bbox 坐标是否能用于 pdfplumber
3. 验证表格替换逻辑

### Phase 2：解析器实现（2-3 小时）

1. 创建 `PyMuPDF4LLMPdfPlumberParser` 类
2. 实现 `_extract_tables_with_pdfplumber()` 方法
3. 实现 `_replace_tables()` 方法
4. 注册到 `ParserRegistry`

### Phase 3：测试与文档（1-2 小时）

1. 编写单元测试
2. 用问题 PDF（如食品饮料周报）验证效果
3. 更新 `pdf-parsing.md` 文档

---

## 预期效果

**Before（pymupdf4llm 单独解析）**：
```markdown
|证券代码<br>证券简称|收盘价<br>（0313）<br>总市值...|
|---|---|
|600519.SH<br>贵州茅台<br>000858.SZ<br>五粮液...|...
```

**After（混合解析器）**：
```markdown
|证券代码|证券简称|收盘价|总市值(亿元)|...|
|---|---|---|---|---|
|600519.SH|贵州茅台|1413.64|17702.6|...|
|000858.SZ|五粮液|102.95|3996.1|...|
```

---

## 结论

**可行性**：✅ 技术可行

**推荐方案**：方案 A - 新增 `pymupdf4llm_pdfplumber` 解析器

**预估工作量**：4-7 小时

**建议优先级**：中高（可显著改善表格密集型文档的解析质量）
