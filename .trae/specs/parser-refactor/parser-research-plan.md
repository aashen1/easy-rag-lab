# PDF 解析器系统化研究计划

## 问题背景

### 当前困境

1. **解析器选择困难**：pymupdf4llm 和 fitz\_pdfplumber 各有优劣，但没有明确的"最佳组合"
2. **参数空间巨大**：每个解析器都有大量参数，组合起来呈指数级增长
3. **badcase 驱动式优化**：发现问题才修，缺乏系统性
4. **调研报告不落地**：两份调研报告提出了混合方案，但没有说明如何验证和选择

### 核心问题

**如何系统地确定"主力链路+表格补强"的最佳工具选择和参数设定？**

***

## 研究框架设计

### 核心思路：借鉴实验系统的成功经验

当前项目的 `pixi run exp` 系统已经成功解决了 RAG 管线的对比实验问题。我们可以复用这个框架的设计思想：

| 实验系统概念          | 解析器研究对应    |
| --------------- | ---------- |
| Variant         | 解析器配置变体    |
| Config Override | 参数覆盖       |
| Metrics         | 解析质量指标     |
| Test Set        | 标准测试 PDF 集 |
| Report          | 解析质量报告     |

### 关键差异

| 维度   | RAG 实验        | 解析器研究             |
| ---- | ------------- | ----------------- |
| 链路长度 | 完整 RAG 管线     | 只有解析一步            |
| 评测方式 | LLM 评测 + 检索指标 | 人工标注 + 自动指标       |
| 耗时   | 分钟级           | 秒级                |
| 可复用性 | 高（测试集固定）      | 中（需要持续添加 badcase） |

### 架构决策：共享基础设施，独立入口

**结论**：解析评测不并入 RAG 实验系统，而是作为独立入口存在，但复用实验系统的基础设施。

**理由**：

1. **指标体系本质不同**：RAG 指标是端到端质量（hit_rate、faithfulness），解析指标是中间产物质量（表格检出率、单元格空值率）。硬塞会让实验系统支持"部分链路"，复杂度爆炸。

2. **迭代节奏不同**：解析评测秒级反馈，RAG 实验分钟级。混在一起体验差。

3. **但完全独立会重复造轮子**：实验系统已解决配置管理、结果存储、对比报告、增量运行、hash 验证。这些解析评测也需要。

**具体做法**：

```
共享层（复用现有代码）
├── 配置加载（ExperimentConfig 模式）
├── 结果存储（manifest.json + results/）
├── 对比报告生成
├── 增量运行 + hash 验证
└── 目录管理

独立层（各自特有）
├── RAG 实验：完整链路 + 端到端指标 + LLM 评测
└── 解析评测：只跑解析 + 结构质量指标 + 人工评测辅助
```

入口命令分开：

```bash
pixi run exp baseline.yaml              # RAG 端到端实验
pixi run parser-bench baseline.yaml      # 解析器评测
```

配置格式同构但独立：

```yaml
# exp_configs/baseline.yaml — RAG 实验
name: "baseline"
variants:
  - name: "chunk_512"
    config_overrides:
      chunker: { chunk_size: 512 }
evaluation:
  metrics_preset: "core"

# parser_configs/baseline.yaml — 解析评测
name: "parser_baseline"
pipelines:
  - name: "pymupdf4llm_pure"
    primary: { algorithm: "pymupdf4llm" }
    table_enhancer: null
metrics:
  - table_precision
  - table_recall
  - markdown_validity
```

**桥梁**：解析评测找到最佳配置后，手动作为 RAG 实验的 `config_overrides` 使用。不需要自动衔接，因为解析评测频率远高于 RAG 实验。

**未来扩展**：如果以后要评测切块质量，同样模式——`pixi run chunker-bench`，共享基础设施，独立入口。

---

## Phase 1：参数空间梳理

### 核心架构重构：两步链路

**当前问题**：`fitz_pdfplumber_parser.py` 将 fitz 文本提取和 pdfplumber 表格提取强耦合在一起，不通用。

**重构目标**：将 PDF 解析拆为两步接力——主力解析（必做）+ 表格补强（选做），支持任意组合。

```
当前架构（强耦合）：
┌──────────────────────────────────────┐
│ fitz_pdfplumber_parser               │
│  ├── fitz 文本提取 ──┐               │
│  └── pdfplumber 表格 ┼─ 耦合在一起    │
│      + 合并逻辑     ─┘               │
└──────────────────────────────────────┘
┌──────────────────────────────────────┐
│ pymupdf4llm_parser                   │
│  └── pymupdf4llm 全量（无表格补强）    │
└──────────────────────────────────────┘

重构后架构（解耦）：
┌─────────────────┐     ┌──────────────────┐
│ 主力解析（必做）  │     │ 表格补强（选做）   │
│ ├─ FitzParser    │────→│ ├─ PdfPlumberEnh  │
│ ├─ PyMuPDF4LLM   │     │ ├─ CamelotEnh     │
│ ├─ MinerU        │     │ └─ None           │
│ └─ ...           │     └──────────────────┘
└─────────────────┘
         ↓
┌─────────────────┐
│ CompositeParser  │  主力 + 补强 = 最终结果
└─────────────────┘
```

**修改规模评估：中等偏小（~400-500 行新代码）**

| 文件 | 改动 | 规模 |
|------|------|------|
| `src/parsers/base.py` | 新增 `TableEnhancer` 基类 | ~50 行 |
| `src/parsers/fitz_parser.py` | 从 fitz_pdfplumber 提取 fitz 部分 | ~200 行（搬代码） |
| `src/parsers/pdfplumber_enhancer.py` | 从 fitz_pdfplumber 提取 pdfplumber 部分 | ~100 行（搬代码） |
| `src/parsers/composite_parser.py` | 新建：主力+补强组合 | ~100 行 |
| `src/parsers/registry.py` | 重构：双注册表 | ~50 行改动 |
| `src/parser.py` | 适配新创建方式 | ~20 行改动 |
| `src/meal/hashes.py` | hash 计算适配 | ~10 行改动 |
| `src/meal/manager.py` | algorithm 读取适配 | ~15 行改动 |
| `config.yaml` | 新配置格式 | ~15 行改动 |
| 4 个测试文件 | 适配新架构 | 中等 |

**风险很低**：核心逻辑都是搬代码，不是重写。

### 1.1 主力解析器参数空间

#### pymupdf4llm — 两种模式，参数完全不同

**关键发现**：pymupdf4llm 有 Layout 和 Legacy 两种模式，通过 `pymupdf4llm.use_layout(True/False)` **全局切换**（不是 to_markdown 的参数），两种模式下可用参数完全不同！

| 维度 | Layout 模式（默认） | Legacy 模式 |
|------|-------------------|------------|
| 核心引擎 | pymupdf-layout 布局分析 | PyMuPDF 内置文本提取 + 自定义逻辑 |
| 多栏检测 | 自动 | 需手动实现 |
| 表格检测 | Layout 模块处理 | 通过 table_strategy 参数控制 |
| 标题检测 | Layout 模块处理 | 通过 hdr_info 参数控制 |
| page_boxes | ✅ 有 | ✅ 有 |
| tables/images/words | ❌ 空列表 | ✅ 可用 |

**Layout 模式参数**（子集，与当前项目相关）：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `page_chunks` | False | 页级输出 |
| `header` | True | 包含页眉 |
| `footer` | True | 包含页脚 |
| `force_text` | True | 保留图表上的文字 |
| `ignore_code` | False | 避免代码块 |
| `use_ocr` | True | OCR 兜底 |
| `ocr_language` | "eng" | OCR 语言 |
| `write_images` | False | 输出图片文件 |
| `page_separators` | False | 页分隔符 |
| `show_progress` | False | 进度条 |

**Legacy 模式额外参数**（Layout 模式下不可用）：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `table_strategy` | "lines_strict" | 表格检测策略：lines/lines_strict/text |
| `hdr_info` | None | 自定义标题检测（callable 或 False） |
| `margins` | 0 | 页面边距 |
| `fontsize_limit` | 3 | 字体大小过滤阈值 |
| `extract_words` | False | 提取单词列表 |
| `ignore_images` | False | 忽略图像 |
| `ignore_graphics` | False | 忽略矢量图形 |
| `graphics_limit` | None | 矢量图形数量限制 |
| `detect_bg_color` | True | 检测背景色 |
| `ignore_alpha` | False | 包含透明文本 |
| `image_size_limit` | 0.05 | 图像尺寸阈值 |
| `use_glyphs` | False | 使用 glyph 编码 |

**page_chunks=True 时的返回结构**（两种模式共有）：

```python
{
    "metadata": {..., "page_number": int},
    "text": str,                    # 页面 Markdown 文本
    "page_boxes": [                 # 布局边界框
        {
            "index": int,           # 0-based 读取顺序
            "class": str,           # "text"/"picture"/"table"
            "bbox": [x0, y0, x1, y1],
            "pos": (start, stop),   # text 切片位置
        }
    ],
    # Legacy 模式额外字段：
    "tables": [...],                # 表格信息
    "images": [...],                # 图像信息
    "words": [...],                 # 单词列表（extract_words=True）
}
```

#### fitz — 自己设计逻辑，参数即逻辑

fitz 不是通过参数调优，而是通过代码逻辑控制。当前实现的可调逻辑：

| 逻辑模块 | 当前实现 | 可选变体 |
|---------|---------|---------|
| 页眉过滤 | header_zone_ratio + 长度判断 | 可关闭 / 调整比例 |
| 页脚过滤 | footer_zone_ratio + 长度判断 | 可关闭 / 调整比例 |
| 噪声过滤 | 5 个正则模式 | 可自定义模式列表 |
| 多栏检测 | x_center 比例法 | 可关闭 / 换算法 |
| 标题检测 | font_size + bold 阈值 | 可关闭 / 调整阈值 |
| 文本排序 | 先列后行 / 纯行序 | 两种排序策略 |

**fitz 的灵活性在于**：可以自由组合上述逻辑模块，每个模块都可以开关和调参。

### 1.2 表格补强参数空间

#### pdfplumber — 四种策略，水平垂直可独立设置

**关键发现**：pdfplumber 的 `vertical_strategy` 和 `horizontal_strategy` 可以独立设置，形成混合策略！

| 策略 | 原理 | 适用场景 |
|------|------|---------|
| `lines` | 检测矢量线段交叉 | 有边框表格 |
| `lines_strict` | 只用穿过整个区域的线段 | 规范边框表格，减少误检 |
| `text` | 文本位置对齐推断 | 无边框表格 |
| `explicit` | 手动指定线条 | 完全控制 |

**混合策略示例**：

| vertical | horizontal | 适用场景 |
|----------|-----------|---------|
| lines | lines | 有边框表格（默认） |
| lines | text | 有竖线无横线 |
| text | lines | 有横线无竖线 |
| text | text | 完全无边框 |
| lines_strict | lines_strict | 规范边框，减少误检 |

**完整 table_settings 参数**：

| 参数 | 默认值 | 适用策略 | 说明 |
|------|--------|---------|------|
| `vertical_strategy` | "lines" | 全部 | 垂直检测策略 |
| `horizontal_strategy` | "lines" | 全部 | 水平检测策略 |
| `snap_tolerance` | 3 | lines | 线段端点吸附容差 |
| `join_tolerance` | 3 | lines | 共线线段合并容差 |
| `edge_min_length` | 3 | lines | 最小线段长度 |
| `min_edges_vertical` | 2 | lines | 最少垂直线段数 |
| `min_edges_horizontal` | 2 | lines | 最少水平线段数 |
| `intersection_x_tolerance` | 3 | lines | 交叉点 X 容差 |
| `intersection_y_tolerance` | 3 | lines | 交叉点 Y 容差 |
| `min_words_vertical` | 3 | text | 列中最少词数 |
| `min_words_horizontal` | 1 | text | 行中最少词数 |
| `text_tolerance` | 3 | text | 文本对齐容差 |
| `text_x_tolerance` | 3 | text | 水平文本对齐容差 |
| `text_y_tolerance` | 3 | text | 垂直文本对齐容差 |

**质量过滤参数**（我们的增强层自定义）：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `min_columns` | 3 | 最小列数（过滤窄表格） |
| `max_empty_ratio` | 0.5 | 最大空单元格比例 |
| `min_data_rows` | 2 | 最小数据行数 |

### 1.3 网格搜索空间

**完整搜索空间**（指数爆炸，不全做）：

| 维度 | 选项 | 数量 |
|------|------|------|
| pymupdf4llm Layout | 开/关 | 2 |
| pymupdf4llm table_strategy (Legacy) | lines_strict/text | 2 |
| pymupdf4llm force_text | True/False | 2 |
| pymupdf4llm ignore_code | True/False | 2 |
| pymupdf4llm use_ocr | True/False | 2 |
| fitz header_filter | True/False | 2 |
| fitz footer_filter | True/False | 2 |
| fitz column_detection | True/False | 2 |
| pdfplumber vertical_strategy | lines/text/lines_strict | 3 |
| pdfplumber horizontal_strategy | lines/text/lines_strict | 3 |
| pdfplumber snap_tolerance | 3/5/8 | 3 |
| pdfplumber join_tolerance | 3/5/8 | 3 |
| pdfplumber min_words_vertical | 1/3/5 | 3 |
| 表格补强开关 | 开/关 | 2 |
| **总组合** | | **~100,000+** |

**预选典型组合**（基于经验判断，大概率效果好的）：

| # | 主力 | 主力关键参数 | 表格补强 | 补强关键参数 | 说明 |
|---|------|------------|---------|------------|------|
| 1 | pymupdf4llm Layout | force_text=T, ignore_code=T, use_ocr=T | None | - | 当前默认 |
| 2 | pymupdf4llm Layout | 同上 | pdfplumber | v=lines, h=lines | 有边框表格补强 |
| 3 | pymupdf4llm Layout | 同上 | pdfplumber | v=text, h=text | 无边框表格补强 |
| 4 | pymupdf4llm Layout | 同上 | pdfplumber | v=lines, h=text | 混合策略 |
| 5 | pymupdf4llm Legacy | table_strategy=text | None | - | Legacy 自带表格 |
| 6 | pymupdf4llm Legacy | table_strategy=lines_strict | None | - | Legacy 严格线条 |
| 7 | pymupdf4llm Legacy | table_strategy=text | pdfplumber | v=lines, h=lines | Legacy+补强 |
| 8 | fitz | header_filter=T, footer_filter=T, column_detection=T | None | - | 纯 fitz |
| 9 | fitz | 同上 | pdfplumber | v=lines, h=lines | 当前 fitz_pdfplumber 等价 |
| 10 | fitz | 同上 | pdfplumber | v=text, h=text | text 策略变体 |
| 11 | fitz | 同上 | pdfplumber | v=lines, h=text | 混合策略 |
| 12 | fitz | column_detection=F | pdfplumber | v=lines, h=lines | 无多栏检测 |

**已有网格测试**：项目中 `scripts/pdf_grid_test.py` 已实现 8×6=48 组合的网格测试，覆盖了上述大部分组合。这个脚本应作为评测系统的起点。

### 1.4 表格补强的精准触发

**核心问题**：如何让补强步骤只对主力中发现的表格来补做，节约计算量和减少误判？

**方案：基于 page_boxes 的精准定位**

pymupdf4llm 的 page_chunks 返回中包含 `page_boxes`，其中 `class="table"` 的条目精确标记了表格区域。这比用正则匹配 markdown 表格更可靠。

```python
# 精准触发流程
for page_data in result:
    page_boxes = page_data.get("page_boxes", [])
    table_boxes = [b for b in page_boxes if b["class"] == "table"]
    
    if not table_boxes:
        continue  # 该页无表格，跳过补强
    
    # 只对有表格的页面调用 pdfplumber
    # 可选：用 bbox 限定 pdfplumber 的搜索区域
    for box in table_boxes:
        bbox = box["bbox"]  # [x0, y0, x1, y1]
        # 方案 A：整页提取后按 bbox 匹配
        # 方案 B：crop 到 bbox 区域再提取（更精准但可能丢失跨区域表格）
```

**误判防护**：

| 防护层 | 机制 | 说明 |
|--------|------|------|
| L1 页面级 | 只对有 table box 的页面调用 pdfplumber | 节约计算量 |
| L2 表格级 | 质量过滤（min_columns, max_empty_ratio, min_data_rows） | 过滤低质量表格 |
| L3 替换级 | 只替换主力已检测到的表格区域，不追加新表格 | 防止误检 |
| L4 对比级 | 对比补强前后表格质量，选择更优版本 | 防止补强反而变差 |

**配置化设计**：所有防护层参数都可通过配置调整，不写死逻辑。

```yaml
table_enhancer: "pdfplumber"
pdfplumber:
  strategy: "lines"
  # 补强触发条件
  trigger:
    require_primary_table: true   # 只在主力检测到表格时才补强
    use_page_boxes: true          # 使用 page_boxes 精准定位
  # 质量过滤
  quality_filter:
    min_columns: 3
    max_empty_ratio: 0.5
    min_data_rows: 2
  # 替换策略
  replace_policy: "better_wins"   # better_wins / always_replace / never_replace
  # pdfplumber 原生参数
  table_settings:
    snap_tolerance: 5
    join_tolerance: 5
    edge_min_length: 10
```

***

## Phase 2：评测指标设计

### 2.1 自动评测指标

| 指标               | 计算方式                   | 意义    |
| ---------------- | ---------------------- | ----- |
| **表格检出率**        | 检出的表格数 / 真实表格数         | 召回    |
| **表格精确率**        | 正确表格数 / 检出的表格数         | 准确    |
| **表格行数准确率**      | 1 - \|预测行数-真实行数\|/真实行数 | 结构完整性 |
| **表格列数准确率**      | 1 - \|预测列数-真实列数\|/真实列数 | 结构完整性 |
| **单元格空值率**       | 空单元格数 / 总单元格数          | 数据完整性 |
| **Markdown 合法性** | 通过 markdown parser 的比例 | 格式正确性 |

### 2.2 人工评测维度

| 维度        | 评分标准           |
| --------- | -------------- |
| **表格可读性** | 1-5 分，数据是否清晰可读 |
| **文本完整性** | 1-5 分，是否有遗漏或重复 |
| **标题层级**  | 1-5 分，标题是否正确识别 |
| **多栏处理**  | 1-5 分，阅读顺序是否正确 |

### 2.3 Badcase 驱动指标

当发现新的 badcase 时：

1. 记录 badcase 的特征（表格类型、文档类型等）
2. 添加到测试集
3. 重新运行所有解析器变体
4. 对比结果，找出最佳配置

***

## Phase 3：测试集构建

### 3.1 测试集分层

| 层级          | 类型         | 来源      | 数量 |
| ----------- | ---------- | ------- | -- |
| **L1 基础**   | 简单单栏文档     | 已有数据    | 5  |
| **L2 表格**   | 含表格的文档     | 已有数据    | 10 |
| **L3 复杂表格** | 多级表头、合并单元格 | badcase | 5  |
| **L4 多栏**   | 多栏布局       | 已有数据    | 5  |
| **L5 混合**   | 表格+多栏+图片   | 真实研报    | 10 |

### 3.2 标注数据格式

```json
{
  "pdf_path": "data/raw/research_reports/xxx.pdf",
  "page_number": 5,
  "ground_truth": {
    "tables": [
      {
        "bbox": [x0, y0, x1, y1],
        "rows": 15,
        "columns": 4,
        "header_row": true
      }
    ],
    "paragraphs": 3,
    "headings": ["## 四、重点公司盈利预测"]
  }
}
```

### 3.3 当前 badcase 分析

用户提供的 badcase：`食品饮料行业ETF周报：茅台C端改革持续进行.pdf`

问题特征：

* 表格有多级表头（证券代码/证券简称合并）

* 单元格内有换行（`600519.SH<br>贵州茅台`）

* 表格数据密集

***

## Phase 4：实验框架实现

### 4.1 目录结构

```
# 配置文件（项目根目录，与 exp_configs/ 同级）
parser_configs/                 # 解析器评测配置目录
├── baseline.yaml               # 基线配置
├── table_focus.yaml            # 表格优化配置
└── hybrid.yaml                 # 混合配置

# 代码实现（eval/ 目录下）
eval/
├── parser_benchmark/           # 新增：解析器评测模块
│   ├── __init__.py
│   ├── runner.py               # 评测运行器
│   ├── metrics.py              # 指标计算
│   ├── test_cases.py           # 测试用例管理
│   └── report_generator.py     # 报告生成
└── run_parser_benchmark.py     # 新增：入口脚本
```

### 4.2 配置文件格式

#### 设计原则：模块化 + 链路组合

解析器评测系统采用**模块化设计**，支持：

1. **主力链路（Primary）**：负责整体文档解析（文本、布局、OCR 等）
2. **表格补强（Table Enhancer）**：可选的表格提取增强模块
3. **自由组合**：主力链路 + 表格补强可以任意搭配

```
┌─────────────────────────────────────────────────────────────┐
│                    解析器链路组合示意                          │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  主力链路（Primary Pipeline）                                  │
│  ├── pymupdf4llm    ─┐                                       │
│  ├── fitz           ─┼─ 可选其一                              │
│  ├── minerU         ─┤                                       │
│  ├── docling        ─┤                                       │
│  └── unstructured   ─┘                                       │
│                                                              │
│  表格补强（Table Enhancer，可选）                               │
│  ├── pdfplumber     ─┐                                       │
│  ├── camelot        ─┼─ 可选其一或 None                       │
│  ├── tabula         ─┤                                       │
│  └── img2table      ─┘                                       │
│                                                              │
│  组合示例：                                                    │
│  • pymupdf4llm + None（纯 pymupdf4llm）                       │
│  • pymupdf4llm + pdfplumber（混合链路）                        │
│  • minerU + None（minerU 自带高质量表格）                       │
│  • fitz + camelot（fitz 文本 + camelot 表格）                  │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

#### 配置文件格式

```yaml
# parser_configs/baseline.yaml
name: "parser_baseline"
description: "解析器基线对比"

pipelines:
  # 纯主力链路（无表格补强）
  - name: "pymupdf4llm_pure"
    primary:
      algorithm: "pymupdf4llm"
      config:
        page_chunks: true
        header: false
        footer: false
        force_text: true
        ignore_code: true
        use_ocr: true
    table_enhancer: null  # 不使用表格补强

  # 主力链路 + 表格补强
  - name: "pymupdf4llm_pdfplumber"
    primary:
      algorithm: "pymupdf4llm"
      config:
        page_chunks: true
        force_text: true
    table_enhancer:
      algorithm: "pdfplumber"
      strategy: "text"  # lines / text / explicit
      config:
        min_columns: 3
        max_empty_ratio: 0.5

  # 另一个主力链路
  - name: "fitz_pdfplumber_lines"
    primary:
      algorithm: "fitz"
      config:
        header_filter: true
        footer_filter: true
        column_detection: true
    table_enhancer:
      algorithm: "pdfplumber"
      strategy: "lines"

  # 自带高质量表格的主力链路（无需补强）
  - name: "minerU_pure"
    primary:
      algorithm: "minerU"
      config:
        # minerU 的参数
    table_enhancer: null  # minerU 自带高质量表格，无需补强

  # 使用其他表格补强库
  - name: "fitz_camelot"
    primary:
      algorithm: "fitz"
      config:
        column_detection: true
    table_enhancer:
      algorithm: "camelot"
      flavor: "lattice"  # lattice / stream

test_pdfs:
  - "data/raw/research_reports/食品饮料行业ETF周报：茅台C端改革持续进行.pdf"

output_dir: "data/parser_reports"
```

#### 解析器注册表重构

```python
# src/parsers/registry.py 重构设计

class ParserRegistry:
    _primaries: dict[str, type[BaseParser] | None] = {
        "pymupdf4llm": None,
        "fitz": None,
    }
    _enhancers: dict[str, type[TableEnhancer] | None] = {
        "pdfplumber": None,
    }

    @classmethod
    def get(cls, primary: str, enhancer: str | None = None,
            primary_config: dict | None = None,
            enhancer_config: dict | None = None) -> BaseParser:
        """创建解析器链路：主力 + 可选表格补强"""
        primary_parser = cls._get_primary(primary, primary_config)
        
        if enhancer is None:
            return primary_parser
        
        enhancer_module = cls._get_enhancer(enhancer, enhancer_config)
        return CompositeParser(primary_parser, enhancer_module)
```

#### TableEnhancer 基类

```python
# src/parsers/base.py 新增

class TableEnhancer(ABC):
    """表格补强模块基类。
    
    接收主力解析器的 ParseResult，检测表格区域，
    用更专业的表格提取库重新提取，替换原表格。
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """补强模块唯一标识"""

    @abstractmethod
    def enhance(self, pdf_path: str, result: ParseResult) -> ParseResult:
        """对解析结果进行表格补强
        
        Args:
            pdf_path: PDF 文件路径（补强模块可能需要重新访问原始 PDF）
            result: 主力解析器的输出
            
        Returns:
            表格补强后的 ParseResult
        """
```

#### CompositeParser 实现

```python
# src/parsers/composite_parser.py

class CompositeParser(BaseParser):
    """组合解析器：主力解析 + 表格补强"""

    def __init__(self, primary: BaseParser, enhancer: TableEnhancer):
        self._primary = primary
        self._enhancer = enhancer

    @property
    def name(self) -> str:
        return f"{self._primary.name}+{self._enhancer.name}"

    def parse(self, pdf_path: str) -> ParseResult:
        # 1. 主力解析
        result = self._primary.parse(pdf_path)
        # 2. 表格补强
        return self._enhancer.enhance(pdf_path, result)
```

#### PdfPlumberEnhancer 实现（从 fitz_pdfplumber 拆出）

```python
# src/parsers/pdfplumber_enhancer.py

class PdfPlumberEnhancer(TableEnhancer):
    """使用 pdfplumber 重新提取表格，替换主力解析器的表格区域"""

    def __init__(self, config: dict | None = None):
        self._strategy = config.get("strategy", "lines") if config else "lines"
        self._min_columns = config.get("min_columns", 3)
        self._max_empty_ratio = config.get("max_empty_ratio", 0.5)
        self._min_data_rows = config.get("min_data_rows", 2)
        self._table_settings = config.get("table_settings", DEFAULT_TABLE_SETTINGS)

    def enhance(self, pdf_path: str, result: ParseResult) -> ParseResult:
        enhanced_pages = []
        for page in result.pages:
            # 检测该页是否有 markdown 表格
            table_spans = self._find_md_table_spans(page.text)
            if not table_spans:
                enhanced_pages.append(page)
                continue
            
            # 用 pdfplumber 重新提取该页表格
            plumber_tables = self._extract_tables(pdf_path, page.page_number - 1)
            
            # 质量过滤
            plumber_tables = self._filter_low_quality(plumber_tables)
            
            if plumber_tables:
                # 替换原表格
                new_text = self._replace_tables(page.text, table_spans, plumber_tables)
                enhanced_pages.append(
                    ParsedPage(page_number=page.page_number, text=new_text, metadata=page.metadata)
                )
            else:
                enhanced_pages.append(page)
        
        return ParseResult(pages=enhanced_pages, metadata=result.metadata)
```

#### FitzParser 实现（从 fitz_pdfplumber 拆出）

```python
# src/parsers/fitz_parser.py

class FitzParser(BaseParser):
    """纯 fitz 文本提取解析器（不含表格补强）"""

    def __init__(self, config: dict | None = None):
        self._header_filter = config.get("header_filter", True)
        self._footer_filter = config.get("footer_filter", True)
        self._column_detection = config.get("column_detection", True)
        # ... 其他 fitz 参数

    @property
    def name(self) -> str:
        return "fitz"

    def parse(self, pdf_path: str) -> ParseResult:
        doc = fitz.open(str(pdf_path))
        pages = []
        for page_idx in range(len(doc)):
            page = doc[page_idx]
            blocks = self._extract_page_blocks(page, page_idx + 1)
            md_text = self._blocks_to_markdown(blocks)
            pages.append(ParsedPage(page_number=page_idx + 1, text=md_text, ...))
        doc.close()
        return ParseResult(pages=pages, ...)
    
    # 复用 fitz_pdfplumber_parser.py 中的：
    # _extract_page_blocks, _detect_columns, _is_noise,
    # _detect_heading, _blocks_to_markdown
    # 不包含 _extract_tables_with_pdfplumber, _merge_text_and_tables
```

### 4.3 运行命令

```bash
# 运行单个配置
pixi run parser-bench baseline.yaml

# 对比多个配置
pixi run parser-bench baseline.yaml table_focus.yaml --compare

# 添加 badcase 并重新评测
pixi run parser-bench baseline.yaml --add-badcase path/to/new.pdf
```

### 4.4 输出报告

```
data/parser_reports/exp_20260502_120000/
├── manifest.json              # 评测元数据
├── results/
│   ├── pymupdf4llm_default.json
│   ├── fitz_pdfplumber_lines.json
│   └── comparison.json        # 对比结果
├── parsed_samples/            # 解析样本（供人工检查）
│   ├── pymupdf4llm_default/
│   │   └── 食品饮料行业ETF周报.md
│   └── fitz_pdfplumber_lines/
│       └── 食品饮料行业ETF周报.md
└── report.md                  # 可读报告
```

***

## Phase 5：持续优化机制

### 5.1 Badcase 处理流程

```
发现 badcase
    ↓
添加到测试集（带标注）
    ↓
运行所有解析器变体
    ↓
对比结果，找出最佳配置
    ↓
更新默认配置
    ↓
记录优化历史
```

### 5.2 配置演进追踪

类似实验系统的 `variant_config_hashes`，解析器配置也应该有版本追踪：

```json
{
  "config_name": "pymupdf4llm_default",
  "config_hash": "a1b2c3d4",
  "created_at": "2026-05-02",
  "badcases_addressed": ["食品饮料行业ETF周报"],
  "metrics": {
    "table_precision": 0.85,
    "table_recall": 0.90
  }
}
```

### 5.3 知识积累

每次解决一个 badcase，记录：

1. 问题特征（表格类型、文档类型）
2. 解决方案（哪个参数/哪个解析器）
3. 适用范围（是否通用）

形成"解析器决策树"：

```
文档类型？
├── 金融研报
│   ├── 有复杂表格？ → fitz_pdfplumber (text 策略)
│   └── 简单表格？ → pymupdf4llm
├── 学术论文
│   └── 多栏？ → fitz_pdfplumber (column_detection=true)
└── ...
```

***

## 实施步骤

### Step 1：架构重构 — 两步链路解耦

1. 新增 `TableEnhancer` 基类到 `base.py`
2. 从 `fitz_pdfplumber_parser.py` 拆出 `fitz_parser.py`（主力）+ `pdfplumber_enhancer.py`（表格补强）
3. 新建 `composite_parser.py`（主力+补强组合逻辑）
4. 重构 `registry.py`：双注册表（primary + enhancer）
5. 适配 `parser.py`、`meal/hashes.py`、`meal/manager.py`
6. 更新 `config.yaml` 新配置格式
7. 更新测试

**新配置格式**（支持所有参数，不写死逻辑）：

```yaml
parser:
  primary: "pymupdf4llm"           # 主力解析器: pymupdf4llm / fitz
  
  # pymupdf4llm 参数（Layout 和 Legacy 共用 + Legacy 专属）
  pymupdf4llm:
    # 模式切换（关键！全局状态，需特殊处理）
    use_layout: true               # true=Layout模式, false=Legacy模式
    # Layout + Legacy 共用参数
    page_chunks: true
    header: false
    footer: false
    page_separators: false
    write_images: false
    force_text: true
    ignore_code: true
    use_ocr: true
    ocr_language: "chi_sim+eng"
    show_progress: false
    # Legacy 专属参数（use_layout=false 时生效）
    table_strategy: "lines_strict"  # lines / lines_strict / text
    hdr_info: null                  # null=自动, false=禁用, callable=自定义
    margins: 0
    fontsize_limit: 3
    extract_words: false
    ignore_images: false
    ignore_graphics: false
    graphics_limit: null
    detect_bg_color: true
    ignore_alpha: false
    image_size_limit: 0.05
    use_glyphs: false
    # 项目自定义后处理
    clean_degenerate_tables: true
  
  # fitz 参数（逻辑模块化，每个模块可开关）
  fitz:
    header_filter: true
    footer_filter: true
    header_zone_ratio: 0.10
    footer_zone_ratio: 0.10
    column_detection: true
    noise_patterns:
      - "请务必阅读.{0,20}声明"
      - "^\\s*\\d+\\s*$"
      - "^\\s*\\d+\\s*/\\s*\\d+\\s*$"
      - "(?:内部资料|机密|仅供参考).{0,30}$"
      - "^(?:www\\.|http).+$"
    heading_detection: true         # 可关闭标题检测
    heading_thresholds:             # 标题检测阈值
      h1: {font_size: 16, bold: true}
      h2: {font_size: 14, bold: true}
      h3: {font_size: 12, bold: true}
      h4: {font_size: 11, bold: true, max_length: 100}
  
  # 表格补强（null = 不补强）
  table_enhancer: "pdfplumber"      # pdfplumber / null
  
  # pdfplumber 参数
  pdfplumber:
    # 策略（水平垂直可独立设置）
    vertical_strategy: "lines"      # lines / lines_strict / text
    horizontal_strategy: "lines"    # lines / lines_strict / text
    # lines 策略参数
    snap_tolerance: 5
    join_tolerance: 5
    edge_min_length: 10
    min_edges_vertical: 2
    min_edges_horizontal: 2
    intersection_x_tolerance: 5
    intersection_y_tolerance: 5
    # text 策略参数
    min_words_vertical: 3
    min_words_horizontal: 1
    text_tolerance: 3
    text_x_tolerance: 3
    text_y_tolerance: 3
    # 补强触发条件
    trigger:
      require_primary_table: true   # 只在主力检测到表格时才补强
      use_page_boxes: true          # 使用 page_boxes 精准定位（pymupdf4llm 时可用）
    # 质量过滤
    quality_filter:
      min_columns: 3
      max_empty_ratio: 0.5
      min_data_rows: 2
    # 替换策略
    replace_policy: "better_wins"   # better_wins / always_replace / never_replace
```

**向后兼容**：`fitz_pdfplumber` 作为 `primary: "fitz" + table_enhancer: "pdfplumber"` 的语法糖保留。

### Step 2：最小可行评测

1. 创建 `eval/parser_benchmark/` 目录结构
2. 实现评测脚本，跑基线网格 6 种组合
3. 用 badcase PDF 验证

### Step 3：指标体系实现

1. 实现自动评测指标
2. 设计人工评测表格
3. 生成对比报告

### Step 4：测试集构建（持续）

1. 整理现有 PDF 文档
2. 标注关键特征
3. 添加更多 badcase

### Step 5：文档和流程固化

1. 更新 `docs/user-guides/pdf-parsing.md`
2. 添加 `docs/dev-guides/parser-benchmark.md`
3. 配置 pixi task

***

## 预期成果

1. **明确的默认配置**：知道在什么场景下用什么解析器、什么参数
2. **可复现的评测流程**：任何人都可以运行评测、添加 badcase
3. **持续优化的机制**：badcase 驱动的迭代改进
4. **知识沉淀**：解析器决策树、最佳实践文档

***

## 待确认问题

1. **fitz_pdfplumber_parser.py 的去留**：重构后是否保留为兼容层，还是直接删除？
2. **评测指标的优先级**：自动指标 vs 人工评测，先实现哪个？
3. **测试集的规模**：初始测试集用多少个 PDF？

---

## 下一步行动

1. 确认计划 → 开始 Step 1（架构重构）
2. 重构完成后 → Step 2（最小可行评测，跑基线网格 6 种组合）
3. 根据评测结果 → 确定最佳链路

