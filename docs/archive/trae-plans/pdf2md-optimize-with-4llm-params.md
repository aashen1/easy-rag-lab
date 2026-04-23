# PDF→MD 解析优化计划：pymupdf4llm 参数精调

> **目标**：在不更换库的前提下，通过参数精调和流程重构，最大化 pymupdf4llm 对金融研报/年报 PDF 的解析质量
>
> **约束**：保持使用 pymupdf4llm，不引入 fitz 原生或 pdfplumber 等替代库
>
> **版本**：v0.1.9 前置优化

***

## 1. 现状诊断与关键发现

### 1.1 当前配置与实际行为的不一致

**config.yaml 中的配置**（[config.yaml:67-76](file:///b:/project/ash-easy-rag/config.yaml#L67-L76)）：

```yaml
parser:
  algorithm: "pymupdf4llm"
  pymupdf4llm:
    header: false
    footer: false
    page_separators: true
    ignore_images: true
    write_images: false
```

**问题 1：pipeline.py 未传递 parser\_options**

[pipeline.py:178-183](file:///b:/project/ash-easy-rag/src/pipeline.py#L178-L183) 调用 `parse_all_pdfs()` 时缺少 `parser_options` 参数：

```python
parse_results = parse_all_pdfs(
    input_dir=parser_config["input_dir"],
    output_dir=parser_config["output_dir"],
    force=force_parse,
    pdf_files=sampled_pdf_files,
    # ❌ 缺少: parser_options=parser_config.get("pymupdf4llm")
)
```

而 [meal.py:628-633](file:///b:/project/ash-easy-rag/src/meal.py#L628-L633) 正确传递了。这意味着通过 pipeline.py 构建索引时，config.yaml 中配置的参数**完全不生效**。

**问题 2：`use_layout()`** **开关的隐含影响**

这是本次调研的**最关键发现**。pymupdf4llm 默认启用 PyMuPDF Layout 模块（`use_layout(True)`），但许多重要参数**仅在** **`use_layout(False)`** **时生效**：

| 参数                 | 需要 use\_layout(False)? | 当前配置    | 实际是否生效                     |
| ------------------ | ---------------------- | ------- | -------------------------- |
| `header`           | ❌ 不需要                  | `false` | ✅ 生效（Layout 模式也支持）         |
| `footer`           | ❌ 不需要                  | `false` | ✅ 生效（Layout 模式也支持）         |
| `page_separators`  | ❌ 不需要                  | `true`  | ✅ 生效                       |
| `ignore_images`    | ✅ **需要**               | `true`  | ❌ **不生效**（Layout 模式下忽略此参数） |
| `write_images`     | ❌ 不需要                  | `false` | ✅ 生效                       |
| `table_strategy`   | ✅ **需要**               | 未配置     | ❌ 无法生效                     |
| `margins`          | ✅ **需要**               | 未配置     | ❌ 无法生效                     |
| `hdr_info`         | ✅ **需要**               | 未配置     | ❌ 无法生效                     |
| `fontsize_limit`   | ✅ **需要**               | 未配置     | ❌ 无法生效                     |
| `image_size_limit` | ✅ **需要**               | 未配置     | ❌ 无法生效                     |
| `detect_bg_color`  | ✅ **需要**               | 未配置     | ❌ 无法生效                     |
| `graphics_limit`   | ✅ **需要**               | 未配置     | ❌ 无法生效                     |
| `page_chunks`      | ❌ 不需要                  | 未配置     | ✅ 可生效                      |

**结论**：当前 `ignore_images: true` 配置在 Layout 模式下**不生效**，图片仍在被处理（只是不写出文件，但图片区域的文本提取行为可能受影响）。

### 1.2 use\_layout(True) vs use\_layout(False) 的取舍

| 维度          | use\_layout(True)（当前默认）          | use\_layout(False)         |
| ----------- | -------------------------------- | -------------------------- |
| **多栏检测**    | ✅ 自动识别双栏/多栏布局                    | ❌ 需自行处理                    |
| **图片/图表识别** | ✅ Layout 模块分类 picture/text/table | ⚠️ 依赖参数控制                  |
| **表格检测**    | ✅ Layout 模块内置表格识别                | ✅ 通过 `table_strategy` 精细控制 |
| **页眉页脚**    | ✅ 内置支持 `header/footer` 参数        | ✅ 通过 `margins` 裁剪          |
| **参数控制力**   | ❌ 大量参数不可用                        | ✅ 全部参数可用                   |
| **OCR 兜底**  | ✅ 自动触发                           | ✅ 自动触发                     |
| **输出稳定性**   | ✅ Layout 模块提供稳定输出                | ⚠️ 参数组合多，需调试               |

**核心决策**：

* **保持** **`use_layout(True)`**：金融研报的双栏布局非常普遍，Layout 模块的多栏检测能力至关重要。放弃 Layout 模块意味着需要自行实现等价功能，违背"不换库"原则。

* **在 Layout 模式下最大化可用参数**：`header`、`footer`、`page_chunks`、`page_separators`、`write_images`、`force_text`、`use_ocr`、`ignore_code` 等参数在 Layout 模式下仍然有效。

* **不依赖需要** **`use_layout(False)`** **的参数**：`table_strategy`、`margins`、`hdr_info`、`ignore_images` 等参数暂不使用，因为放弃 Layout 模块得不偿失。

### 1.3 对两份分析文档的回应

#### 对"换库方案"（switch-to-fitz）的回应

该方案建议用 fitz + pdfplumber 替代 pymupdf4llm，核心诉求是：

| 诉求     | pymupdf4llm 能否满足 | 方式                                                  |
| ------ | ---------------- | --------------------------------------------------- |
| 页码绑定   | ✅ **可以**         | `page_chunks=True` 返回每页 dict，含 `page_number`        |
| 页眉页脚过滤 | ✅ **可以**         | `header=False, footer=False`（Layout 模式下生效）          |
| 表格结构保留 | ⚠️ **部分可以**      | Layout 模式内置表格识别，但复杂表格仍可能有问题                         |
| 多栏排序   | ✅ **可以**         | Layout 模块自动处理（这是不换库的核心理由）                           |
| 噪声过滤   | ⚠️ **部分可以**      | `margins` 需要 `use_layout(False)`，但 Layout 模式有内置噪声处理 |

**结论**：pymupdf4llm 在 Layout 模式下已能满足大部分诉求，无需换库。唯一短板是复杂表格的精细控制（`table_strategy` 需要 `use_layout(False)`），但这可以通过后处理或其他方式弥补。

#### 对"保持4llm方案"（stay-on-4llm）的回应

该方案的分析方向正确，但有以下遗漏/滞后：

1. **未发现** **`use_layout()`** **开关的影响**：方案中建议使用 `table_strategy`、`margins`、`hdr_info` 等参数，但未说明这些参数需要 `use_layout(False)`，在当前默认 Layout 模式下不生效。
2. **未发现 pipeline.py 的 bug**：参数传递缺失导致配置不生效。
3. **未考虑当前代码已有的** **`parser_options`** **传递机制**：parser.py 和 meal.py 已支持 `parser_options`，但 pipeline.py 遗漏了。
4. **`ignore_images: true`** **在 Layout 模式下不生效**：当前配置可能未达到预期效果。

***

## 2. 优化方案设计

### 2.1 优化层次与优先级

```
层次 0（紧急）：修复已知 bug → 确保已有配置真正生效
层次 1（高优）：启用 page_chunks → 建立页码关联
层次 2（高优）：参数精调 → 最大化 Layout 模式下的解析质量
层次 3（中优）：后处理增强 → 补偿 Layout 模式的参数限制
层次 4（低优）：实验验证 → 量化优化效果
```

### 2.2 层次 0：修复已知 Bug

#### T0-1：修复 pipeline.py 的 parser\_options 传递

**文件**：[src/pipeline.py:178-183](file:///b:/project/ash-easy-rag/src/pipeline.py#L178-L183)

**变更**：

```python
# 修改前
parse_results = parse_all_pdfs(
    input_dir=parser_config["input_dir"],
    output_dir=parser_config["output_dir"],
    force=force_parse,
    pdf_files=sampled_pdf_files,
)

# 修改后
parse_results = parse_all_pdfs(
    input_dir=parser_config["input_dir"],
    output_dir=parser_config["output_dir"],
    force=force_parse,
    pdf_files=sampled_pdf_files,
    parser_options=parser_config.get("pymupdf4llm"),
)
```

**影响**：修复后，`header: false`、`footer: false`、`page_separators: true` 等配置将在 pipeline.py 流程中生效。

#### T0-2：修正 config.yaml 中无效的 ignore\_images 配置

**文件**：[config.yaml:75](file:///b:/project/ash-easy-rag/config.yaml#L75)

**变更**：由于 `ignore_images` 在 Layout 模式下不生效，应移除此配置项或添加注释说明。Layout 模式下图片由模块自行分类处理，`write_images: false` 已足够控制不写出图片文件。

```yaml
parser:
  algorithm: "pymupdf4llm"
  pymupdf4llm:
    header: false
    footer: false
    page_separators: true
    # ignore_images: true    # Layout 模式下不生效，由 Layout 模块自行处理
    write_images: false
```

#### T0-3：扩展 parser config hash 包含 options

**文件**：[src/meal.py:126-127](file:///b:/project/ash-easy-rag/src/meal.py#L126-L127)

**变更**：使不同解析参数产生不同的 parser hash，触发重新解析。

```python
# 修改前
relevant = {"algorithm": parser_config.get("algorithm", "pymupdf4llm")}

# 修改后
relevant = {
    "algorithm": parser_config.get("algorithm", "pymupdf4llm"),
    "options": parser_config.get("options", parser_config.get("pymupdf4llm", {})),
}
```

同步更新 `_build_config_snapshot_and_hashes()` 中的 config\_snapshot 以包含完整的 parser options。

### 2.3 层次 1：启用 page\_chunks 建立页码关联

#### T1-1：扩展 parse\_pdf() 支持页级输出

**文件**：[src/parser.py](file:///b:/project/ash-easy-rag/src/parser.py)

**设计**：

```python
def parse_pdf(pdf_path: str, page_chunks: bool = False, **kwargs) -> str | list[dict]:
    """Parse a single PDF file and convert its content to Markdown text.

    Args:
        pdf_path: Path to the PDF file.
        page_chunks: If True, return a list of page dictionaries instead of
            a single merged string. Each dict contains "text" (page Markdown)
            and "metadata" (with "page_number", "page_count", "file_path").
        **kwargs: Additional keyword arguments passed to pymupdf4llm.to_markdown.

    Returns:
        Markdown string, or list of page dicts when page_chunks=True.
    """
    # ... existing validation ...
    try:
        result = pymupdf4llm.to_markdown(str(pdf_file), page_chunks=page_chunks, **kwargs)
        if page_chunks:
            logger.success(f"Parsed PDF (page_chunks): {pdf_path} -> {len(result)} pages")
        else:
            logger.success(f"Successfully parsed PDF: {pdf_path}")
        return result
    except Exception as e:
        # ... existing error handling ...
```

#### T1-2：扩展 parse\_all\_pdfs() 处理页级输出

**设计**：当 `page_chunks=True` 时，将结果保存为 JSON 格式而非单个 MD 文件。

* 输出文件名：`{filename}.pages.json`

* JSON 结构：

  ```json
  [
    {
      "text": "该页 Markdown 文本",
      "metadata": {
        "page_number": 1,
        "page_count": 20,
        "file_path": "report.pdf"
      },
      "toc_items": [...],
      "tables": [...]
    },
    ...
  ]
  ```

* 向后兼容：当 `page_chunks=False`（默认）时，行为不变，仍输出 `.md` 文件

#### T1-3：更新 config.yaml 启用 page\_chunks

```yaml
parser:
  algorithm: "pymupdf4llm"
  pymupdf4llm:
    header: false
    footer: false
    page_separators: true
    write_images: false
    page_chunks: true    # 新增：启用页级输出
```

#### T1-4：实现页感知分块

**文件**：[src/chunker.py](file:///b:/project/ash-easy-rag/src/chunker.py)

新增 `chunk_text_page_aware()` 函数：

```python
def chunk_text_page_aware(
    page_chunks: list[dict],
    chunk_size: int = 512,
    overlap: int = 0,
    encoding_name: str = "cl100k_base",
) -> list[dict[str, Any]]:
    """Split page-level parsed results into chunks with page metadata.

    Each page is chunked independently (no cross-page chunks).
    Every chunk carries a page_number in its metadata.
    """
```

新增 `process_parsed_files_page_aware()` 函数：读取 `.pages.json` 文件，调用页感知分块，输出标准 JSONL 格式。

#### T1-5：更新 meal.py 支持页感知分块流程

**文件**：[src/meal.py](file:///b:/project/ash-easy-rag/src/meal.py)

修改 `build_chunks_if_needed()`：

* 检测解析结果格式：若存在 `.pages.json` 则使用页感知分块流程

* 否则回退到现有 `.md` → 固定分块流程（向后兼容）

### 2.4 层次 2：参数精调

在 Layout 模式（`use_layout(True)`）下，以下参数**可以生效**，应进行精调：

#### T2-1：force\_text 参数

**当前行为**：默认 `force_text=True`，即使文本与图片/图形重叠也会提取文本。

**建议**：保持 `force_text=True`。金融研报中常有文字叠加在图表上的情况（如数据标注），保留这些文本对 RAG 有价值。

#### T2-2：ignore\_code 参数

**当前行为**：默认 `ignore_code=False`，等宽文本行会被格式化为代码块。

**问题**：金融研报中的财务数据表格有时被识别为等宽文本，错误地包裹在代码块中。

**建议**：实验 `ignore_code=True`，观察对金融文档的影响。如果表格数据不再被错误标记为代码块，则设为默认。

#### T2-3：use\_ocr 参数

**当前行为**：默认 `use_ocr=True`，自动对需要 OCR 的页面执行识别。

**建议**：保持 `use_ocr=True`。当前数据源为电子版研报，OCR 触发概率低，但保留兜底能力。

#### T2-4：ocr\_language 参数

**当前行为**：默认 `ocr_language="eng"`，仅支持英文 OCR。

**问题**：中文研报若需 OCR，英文语言包无法正确识别。

**建议**：改为 `ocr_language="chi_sim+eng"`，同时支持中文和英文 OCR。需确认 Tesseract 中文语言包已安装。

#### T2-5：page\_separators 参数

**当前行为**：已配置 `page_separators: true`，在每页末尾插入 `--- end of page=n ---`。

**问题**：当启用 `page_chunks=True` 后，页分隔符变得冗余（每页已是独立 dict）。

**建议**：当 `page_chunks=True` 时，自动设置 `page_separators=False`（避免重复信息）。当 `page_chunks=False` 时，保持 `page_separators=True`（提供页码信息）。

#### T2-6：show\_progress 参数

**建议**：添加 `show_progress: true` 到配置中，便于观察解析进度。

#### T2-7：更新后的 config.yaml

```yaml
parser:
  input_dir: "data/raw"
  output_dir: "data/parsed"
  algorithm: "pymupdf4llm"
  pymupdf4llm:
    header: false
    footer: false
    page_separators: false     # page_chunks=True 时冗余，改为 false
    write_images: false
    page_chunks: true          # 启用页级输出
    force_text: true           # 保留叠加在图表上的文本
    ignore_code: true          # 避免财务数据被错误标记为代码块
    use_ocr: true              # 保留 OCR 兜底
    ocr_language: "chi_sim+eng"  # 中英文 OCR
    show_progress: true        # 显示解析进度
```

### 2.5 层次 3：后处理增强

#### T3-1：页码元数据注入 chunk

在页感知分块流程中，每个 chunk 的 metadata 自动包含 `page_number`：

```json
{
  "chunk_id": "report_001_p5",
  "text": "...",
  "metadata": {
    "source": "reports/2026光伏.md",
    "page_number": 5,
    "category": "research_report",
    "chunk_index": 1,
    "token_count": 498,
    "strategy": "page_aware_fixed"
  }
}
```

#### T3-2：MD 文本后处理（可选）

在 parse\_pdf() 返回结果后，可添加轻量后处理步骤：

1. **去除残留页码噪声**：正则匹配孤立数字行（如 `^\d+$`），在页眉页脚过滤后仍可能残留
2. **去除重复声明文本**：如"请务必阅读末页声明"等研报通用声明
3. **表格结构修复**：检测 MD 表格中空行或格式异常，尝试修复

这些后处理应作为可选步骤，通过配置开关控制。

### 2.6 层次 4：实验验证

#### T4-1：建立解析质量评估脚本

编写脚本对比不同参数组合的解析结果：

```python
# 对比实验设计
configs = {
    "baseline": {},  # 默认参数
    "current_config": {"header": False, "footer": False, "page_separators": True, "ignore_images": True, "write_images": False},
    "optimized": {"header": False, "footer": False, "page_chunks": True, "ignore_code": True, "force_text": True, "ocr_language": "chi_sim+eng"},
}
```

评估指标：

* 页眉页脚噪声出现次数（人工检查）

* 表格结构保留率（对比原文与 MD 表格）

* chunk 页码准确率

* 下游检索 hit\_rate / faithfulness

#### T4-2：选取代表性 PDF 进行 A/B 测试

选取 3-5 份代表性金融 PDF：

* 年报（表格密集、多栏排版）

* 研报（双栏排版、图表多）

* 简报（单栏排版、文字为主）

***

## 3. 实施任务清单

| ID   | 任务                                        | 层次 | 优先级 | 依赖   | 规模 |
| ---- | ----------------------------------------- | -- | --- | ---- | -- |
| T0-1 | 修复 pipeline.py 的 parser\_options 传递       | 0  | P0  | 无    | 小  |
| T0-2 | 修正 config.yaml 中无效的 ignore\_images        | 0  | P0  | 无    | 小  |
| T0-3 | 扩展 parser config hash 包含 options          | 0  | P0  | T0-2 | 小  |
| T1-1 | 扩展 parse\_pdf() 支持 page\_chunks           | 1  | P0  | T0-1 | 中  |
| T1-2 | 扩展 parse\_all\_pdfs() 处理页级输出              | 1  | P0  | T1-1 | 中  |
| T1-3 | 更新 config.yaml 启用 page\_chunks            | 1  | P0  | T1-2 | 小  |
| T1-4 | 实现 chunk\_text\_page\_aware()             | 1  | P0  | T1-2 | 中  |
| T1-5 | 更新 meal.py 支持页感知分块                        | 1  | P0  | T1-4 | 中  |
| T2-1 | 精调 force\_text/ignore\_code/ocr\_language | 2  | P1  | T0-1 | 小  |
| T2-2 | 更新 config.yaml 参数精调结果                     | 2  | P1  | T2-1 | 小  |
| T3-1 | 页码元数据注入 chunk                             | 1  | P0  | T1-4 | 小  |
| T3-2 | MD 文本后处理（可选）                              | 3  | P2  | T1-1 | 中  |
| T4-1 | 建立解析质量评估脚本                                | 4  | P1  | T1-5 | 中  |
| T4-2 | A/B 测试与效果验证                               | 4  | P1  | T4-1 | 中  |
| T5-1 | 更新单元测试                                    | 贯穿 | P0  | 各任务  | 中  |

***

## 4. 风险与缓解

| 风险                                                | 影响 | 缓解措施                                                               |
| ------------------------------------------------- | -- | ------------------------------------------------------------------ |
| `page_chunks=True` 改变输出格式，破坏现有缓存逻辑                | 中  | 新格式使用 `.pages.json` 扩展名，与旧 `.md` 共存；ArtifactCache 按 parser hash 隔离 |
| `ignore_code=True` 可能影响代码块的正确识别                   | 低  | 先在小样本上测试，确认金融文档中无合法代码块                                             |
| `ocr_language="chi_sim+eng"` 需要安装 Tesseract 中文语言包 | 低  | 检查环境是否已安装；若未安装则回退到 "eng"                                           |
| 页感知分块导致 chunk 数量增加（每页边界强制切断）                      | 低  | 可在页边界处设置小 overlap 缓解                                               |
| Layout 模式下无法使用 `table_strategy` 精细控制表格            | 中  | 依赖 Layout 模块内置表格识别；若效果不佳，考虑后处理修复                                   |

***

## 5. 决策总结

| 问题                         | 决策             | 理由                                              |
| -------------------------- | -------------- | ----------------------------------------------- |
| 是否切换到 `use_layout(False)`？ | ❌ **否**        | 金融研报双栏排版普遍，Layout 模块的多栏检测是核心能力，放弃后需自行实现等价功能     |
| 是否启用 `page_chunks=True`？   | ✅ **是**        | 页码关联是 RAG 系统的基础需求，且 page\_chunks 在 Layout 模式下可用 |
| 是否使用 `ignore_code=True`？   | ✅ **是**（实验验证后） | 金融文档中财务数据被错误标记为代码块是已知问题                         |
| 是否修改 `ocr_language`？       | ✅ **是**        | 中文研报需要中文 OCR 支持                                 |
| 是否实现后处理？                   | ⚠️ **可选**      | 优先保证参数精调效果，后处理作为锦上添花                            |
| 是否需要换库？                    | ❌ **否**        | pymupdf4llm 在 Layout 模式下已能满足核心需求，换库成本远大于参数精调    |

***

## 6. 与 stay-on-4llm 方案的差异

本计划与 [pdf2md-stay-on-4llm-plan.md](file:///b:/project/ash-easy-rag/.trae/documents/pdf2md-stay-on-4llm-plan.md) 的主要差异：

1. **发现** **`use_layout()`** **开关的关键影响**：原方案建议使用 `table_strategy`、`margins`、`hdr_info` 等参数，但未意识到这些参数在默认 Layout 模式下不生效。本计划明确在 Layout 模式下只使用可用参数。
2. **发现 pipeline.py 的 bug**：原方案未发现参数传递缺失问题。
3. **简化实施范围**：原方案包含语义分块页感知适配等较复杂的改动，本计划优先聚焦于参数修复和 page\_chunks 启用，降低实施风险。
4. **新增** **`ignore_code`** **和** **`ocr_language`** **精调**：原方案未涉及这两个参数。
5. **明确** **`ignore_images`** **在 Layout 模式下无效**：原方案未指出此问题。

