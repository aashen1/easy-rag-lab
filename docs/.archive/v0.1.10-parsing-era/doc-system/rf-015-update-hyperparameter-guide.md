# \[RF-015] 更新 hyperparameter-guide.md 增加新解析链路讲解

## 任务背景

系统现在支持两种 PDF 解析器：

1. `pymupdf4llm`（主解析器，默认）- 使用 pymupdf4llm 库，支持 Layout 模式
2. `fitz_pdfplumber`（新解析器）- 结合 fitz (PyMuPDF) 和 pdfplumber，支持精确表格提取

当前 `hyperparameter-guide.md` 介绍了 6 大类泛超参数（分块策略、检索方式、重排序、查询改写、检索数量），但**缺少 PDF 解析环节**的介绍。

## 实施步骤

### 步骤 1：更新 hyperparameter-guide.md

在文档开头概述表格中增加"PDF 解析"行，并在"分块策略"章节之前新增"0. PDF 解析策略"章节：

**新增内容要点：**

* 参数位置：`parser.algorithm`

* 两种解析器对比表格

* pymupdf4llm 参数说明（精简版，详细内容引用 pdf-parsing.md）

* fitz\_pdfplumber 参数说明

* 适用场景推荐

### 步骤 2：更新 config-reference.md

补充 `fitz_pdfplumber` 参数说明，更新 `algorithm` 参数说明：

**修改内容：**

* 更新 `algorithm` 参数说明，说明支持两种解析器

* 新增 `fitz_pdfplumber` 参数表格

### 步骤 3：更新 TODO.md 和 backlog.md

* 将 TODO.md 中 \[RF-015] 条目打钩

* 更新 backlog.md 中 \[RF-015] 状态为已完成

## 涉及文件

| 文件                                    | 操作                       |
| ------------------------------------- | ------------------------ |
| `docs/guides/hyperparameter-guide.md` | 新增 PDF 解析策略章节            |
| `docs/config-reference.md`            | 补充 fitz\_pdfplumber 参数说明 |
| `TODO.md`                             | 打钩 \[RF-015] 条目          |
| `docs/backlog.md`                     | 更新 \[RF-015] 状态          |

## 详细内容设计

### hyperparameter-guide.md 新增章节结构

```markdown
## 0. PDF 解析策略

### 参数位置

parser:
  algorithm: "pymupdf4llm"   # "pymupdf4llm" 或 "fitz_pdfplumber"

### 解析器对比

| 解析器 | 优势 | 劣势 | 适用场景 |
|--------|------|------|---------|
| pymupdf4llm | 多栏检测、LLM 友好输出、OCR 兜底 | Layout 模式下部分参数不可用 | 金融研报（双栏排版） |
| fitz_pdfplumber | 精确表格提取、完全参数控制 | 需额外依赖、无 OCR 兜底 | 表格密集型文档 |

### pymupdf4llm 关键参数

（精简版，引用 pdf-parsing.md 获取详情）

### fitz_pdfplumber 关键参数

（参数说明表格）

### 使用建议

（场景推荐）
```

### config-reference.md 修改内容

```markdown
| `algorithm` | `"pymupdf4llm"` | PDF 解析算法。支持 `pymupdf4llm`（推荐）或 `fitz_pdfplumber` |

### fitz_pdfplumber 参数

（新增参数表格）
```
