# 混合解析链路实现计划

## 目标

实现一条最佳默认链路：**pymupdf4llm Layout 为主 + pdfplumber text 表格补强**

## 设计思路

| 组件   | 工具                 | 职责               |
| ---- | ------------------ | ---------------- |
| 主链路  | pymupdf4llm Layout | 文本提取、标题检测、OCR 兜底 |
| 表格补强 | pdfplumber text    | 高质量表格提取（每行一条数据）  |

## 核心问题与解决方案

### 问题 1：如何避免 pdfplumber 误检？

pdfplumber `text` 策略会把正常段落误检为表格。解决方案：

1. **只对有表格的页面启用**：先用 pymupdf4llm 检测哪些页面有 markdown 表格
2. **表格质量过滤**：

   * 列数 ≥ 3（过滤窄表格）

   * 空单元格比例 < 50%

   * 数据行数 ≥ 2（过滤只有表头的表格）
3. **只替换不追加**：只替换 pymupdf4llm 已检测到的表格区域，不追加新表格

### 问题 2：如何处理 `<br>` 压缩格式？

pymupdf4llm 的表格是 `<br>` 压缩格式（多公司挤在一行）。解决方案：

1. 定位 markdown 表格在文本中的位置（行号范围）
2. 用 pdfplumber text 策略重新提取该页的表格
3. 用 pdfplumber 表格替换原表格区域

### 问题 3：如何处理 pdfplumber 表格质量不如原生的情况？

有些表格 pdfplumber 处理得不如 pymupdf4llm（如简单表格）。解决方案：

1. 对比两种表格的质量指标（行数、列数、空单元格比例）
2. 选择质量更高的版本

## 实现步骤

### Step 1: 创建混合解析器类

文件：`src/parsers/hybrid_parser.py`

```python
class HybridParser(BaseParser):
    """
    混合解析器：pymupdf4llm Layout + pdfplumber text 表格补强
    
    流程：
    1. pymupdf4llm Layout 解析全文
    2. 检测有表格的页面
    3. 对这些页面用 pdfplumber text 提取表格
    4. 质量过滤 + 替换
    """
    
    def __init__(self, config: dict):
        self.primary_parser = PyMuPDF4LLMParser(config)
        self.table_enhance_strategy = config.get("table_enhance_strategy", "text")
        self.quality_threshold = config.get("quality_threshold", {
            "min_columns": 3,
            "max_empty_ratio": 0.5,
            "min_data_rows": 2,
        })
    
    def parse(self, pdf_path: str) -> ParseResult:
        # 1. 主链路解析
        primary_result = self.primary_parser.parse(pdf_path)
        
        # 2. 表格补强
        enhanced_pages = self._enhance_tables(pdf_path, primary_result.pages)
        
        return ParseResult(pages=enhanced_pages, metadata=primary_result.metadata)
```

### Step 2: 实现表格检测与定位

```python
def _find_table_pages(self, pages: list[ParsedPage]) -> dict[int, list[tuple[int, int]]]:
    """
    检测哪些页面有表格，返回 {page_idx: [(table_start_line, table_end_line), ...]}
    """
    table_pages = {}
    for page in pages:
        page_idx = page.page_number - 1
        spans = self._find_md_table_spans(page.text)
        if spans:
            table_pages[page_idx] = spans
    return table_pages
```

### Step 3: 实现 pdfplumber 表格提取与质量过滤

```python
def _extract_plumber_tables(self, pdf_path: str, page_idx: int) -> list[str]:
    """
    用 pdfplumber text 策略提取表格，并进行质量过滤
    """
    strategy = {
        "vertical_strategy": "text",
        "horizontal_strategy": "text",
        "min_words_vertical": 3,
        "min_words_horizontal": 1,
    }
    # ... 提取表格
    # ... 质量过滤
    return filtered_tables

def _filter_low_quality_tables(self, tables: list[str]) -> list[str]:
    """
    过滤低质量表格：
    - 列数 < min_columns 的丢弃
    - 空单元格比例 > max_empty_ratio 的丢弃
    - 数据行数 < min_data_rows 的丢弃
    """
    filtered = []
    for table_md in tables:
        quality = self._assess_table_quality(table_md)
        if quality["columns"] >= self.quality_threshold["min_columns"]:
            if quality["empty_ratio"] <= self.quality_threshold["max_empty_ratio"]:
                if quality["data_rows"] >= self.quality_threshold["min_data_rows"]:
                    filtered.append(table_md)
    return filtered
```

### Step 4: 实现表格替换逻辑

```python
def _replace_tables(self, page_text: str, plumber_tables: list[str]) -> str:
    """
    用 pdfplumber 表格替换原生表格
    """
    if not plumber_tables:
        return page_text
    
    lines = page_text.split("\n")
    spans = self._find_md_table_spans(page_text)
    
    # 从后往前替换，避免行号偏移
    for (start, end), plumber_table in zip(reversed(spans), reversed(plumber_tables)):
        replace_lines = plumber_table.split("\n")
        lines[start:end] = replace_lines
    
    return "\n".join(lines)
```

### Step 5: 更新注册表

文件：`src/parsers/registry.py`

```python
_parsers = {
    "pymupdf4llm": None,
    "fitz_pdfplumber": None,
    "hybrid": None,  # 新增
}
```

### Step 6: 更新配置

文件：`config.yaml`

```yaml
parser:
  algorithm: "hybrid"  # 新的默认值
  hybrid:
    primary: "pymupdf4llm"
    table_enhance_strategy: "text"
    quality_threshold:
      min_columns: 3
      max_empty_ratio: 0.5
      min_data_rows: 2
    # 继承 pymupdf4llm 的所有配置
    header: false
    footer: false
    page_chunks: true
    # ...
```

### Step 7: 添加测试

文件：`tests/test_hybrid_parser.py`

测试用例：

1. 基本解析功能
2. 表格检测正确性
3. 表格替换正确性
4. 质量过滤有效性
5. 与纯 pymupdf4llm 的对比

## 预期效果

| 指标   | pymupdf4llm Layout | 混合链路  | 提升   |
| ---- | ------------------ | ----- | ---- |
| 文本质量 | ⭐⭐⭐⭐⭐              | ⭐⭐⭐⭐⭐ | 持平   |
| 表格质量 | ⭐⭐⭐                | ⭐⭐⭐⭐⭐ | +2   |
| 误检率  | 0%                 | < 10% | 可接受  |
| 耗时   | \~4s               | \~6s  | +50% |

## 风险与缓解

| 风险                   | 缓解措施                  |
| -------------------- | --------------------- |
| pdfplumber 误检破坏好文本   | 只替换已有表格区域，不追加新表格      |
| 某些表格 pdfplumber 处理更差 | 质量对比，选择更优版本           |
| 性能下降                 | 只对有表格的页面启用 pdfplumber |

## 文件清单

| 文件                                | 操作   |
| --------------------------------- | ---- |
| `src/parsers/hybrid_parser.py`    | 新建   |
| `src/parsers/registry.py`         | 修改   |
| `config.yaml`                     | 修改   |
| `tests/test_hybrid_parser.py`     | 新建   |
| `docs/user-guides/pdf-parsing.md` | 更新文档 |

