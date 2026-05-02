# PDF 解析器架构重构与评测系统 Spec

## Why

当前解析器架构存在强耦合问题：`fitz_pdfplumber_parser.py` 将 fitz 文本提取和 pdfplumber 表格提取绑定在一起，无法自由组合主力解析器与表格补强模块。同时缺乏系统化的解析质量评测手段，无法客观比较不同解析器配置的效果差异，只能靠 badcase 驱动式修补。

## What Changes

- 新增 `TableEnhancer` 抽象基类到 `src/parsers/base.py`
- 从 `fitz_pdfplumber_parser.py` 拆出 `src/parsers/fitz_parser.py`（纯 fitz 主力解析器）
- 从 `fitz_pdfplumber_parser.py` 拆出 `src/parsers/pdfplumber_enhancer.py`（pdfplumber 表格补强模块）
- 新建 `src/parsers/composite_parser.py`（主力 + 补强组合逻辑）
- 重构 `src/parsers/registry.py`：双注册表（primary + enhancer），支持任意组合
- 重构 `config.yaml` 解析器配置格式：`primary` + `table_enhancer` 两步链路
- 适配 `src/parser.py`、`src/meal/hashes.py`、`src/meal/manager.py` 使用新配置格式
- 保留 `fitz_pdfplumber` 作为向后兼容的语法糖（`primary: "fitz" + table_enhancer: "pdfplumber"`）
- 新建 `eval/parser_benchmark/` 评测模块（runner、metrics、test_cases、report_generator）
- 新建 `eval/run_parser_benchmark.py` 入口脚本
- 新建 `parser_configs/` 配置目录及基线配置文件
- 新增 pixi task `parser-bench`
- 更新所有相关测试

## Impact

- Affected specs: 解析器子系统、配置系统、meal 数据管理
- Affected code:
  - `src/parsers/base.py` — 新增 `TableEnhancer` 基类
  - `src/parsers/fitz_pdfplumber_parser.py` — 保留为兼容层
  - `src/parsers/fitz_parser.py` — 新建
  - `src/parsers/pdfplumber_enhancer.py` — 新建
  - `src/parsers/composite_parser.py` — 新建
  - `src/parsers/registry.py` — 重构
  - `src/parsers/__init__.py` — 更新导出
  - `src/parser.py` — 适配新配置
  - `src/meal/hashes.py` — 适配新 hash 计算
  - `src/meal/manager.py` — 适配新配置读取
  - `config.yaml` — 新配置格式
  - `pixi.toml` — 新增 parser-bench task
  - `tests/test_parsers_*.py` — 适配新架构
  - `eval/parser_benchmark/` — 新建评测模块

## ADDED Requirements

### Requirement: 两步链路解耦架构

系统 SHALL 将 PDF 解析拆为两步接力——主力解析（必做）+ 表格补强（选做），支持任意组合。

#### Scenario: 纯主力解析（无表格补强）

- **WHEN** 用户配置 `primary: "pymupdf4llm"` 且 `table_enhancer: null`
- **THEN** 系统仅使用 pymupdf4llm 进行解析，不调用任何表格补强模块

#### Scenario: 主力 + 表格补强组合

- **WHEN** 用户配置 `primary: "fitz"` 且 `table_enhancer: "pdfplumber"`
- **THEN** 系统先使用 FitzParser 进行主力解析，再使用 PdfPlumberEnhancer 对结果进行表格补强

#### Scenario: 向后兼容

- **WHEN** 用户配置 `algorithm: "fitz_pdfplumber"`
- **THEN** 系统行为等同于 `primary: "fitz" + table_enhancer: "pdfplumber"`，产出结果一致

### Requirement: TableEnhancer 抽象基类

系统 SHALL 提供 `TableEnhancer` 抽象基类，定义表格补强模块的统一接口。

#### Scenario: 补强模块接口

- **WHEN** 实现一个新的表格补强模块
- **THEN** 该模块必须继承 `TableEnhancer`，实现 `name` 属性和 `enhance(pdf_path, result)` 方法
- **AND** `enhance` 方法接收主力解析器的 `ParseResult`，返回补强后的 `ParseResult`

### Requirement: CompositeParser 组合解析器

系统 SHALL 提供 `CompositeParser`，将主力解析器与表格补强模块组合为单一 `BaseParser` 实例。

#### Scenario: 组合解析器名称

- **WHEN** 使用 `CompositeParser(FitzParser(), PdfPlumberEnhancer())`
- **THEN** `name` 属性返回 `"fitz+pdfplumber"`

#### Scenario: 组合解析器执行流程

- **WHEN** 调用 `CompositeParser.parse(pdf_path)`
- **THEN** 先执行主力解析器的 `parse`，再将结果传给补强模块的 `enhance`

### Requirement: 双注册表

系统 SHALL 在 `ParserRegistry` 中维护两个独立的注册表：`_primaries` 和 `_enhancers`。

#### Scenario: 通过注册表创建组合解析器

- **WHEN** 调用 `ParserRegistry.get(primary="fitz", enhancer="pdfplumber", primary_config={}, enhancer_config={})`
- **THEN** 返回 `CompositeParser(FitzParser(config), PdfPlumberEnhancer(config))` 实例

#### Scenario: 通过注册表创建纯主力解析器

- **WHEN** 调用 `ParserRegistry.get(primary="pymupdf4llm", enhancer=None, primary_config={})`
- **THEN** 返回 `PyMuPDF4LLMParser(config)` 实例

#### Scenario: 向后兼容旧接口

- **WHEN** 调用 `ParserRegistry.get(name="fitz_pdfplumber", config={})`
- **THEN** 行为等同于 `ParserRegistry.get(primary="fitz", enhancer="pdfplumber", primary_config=config, enhancer_config=config)`

### Requirement: 新配置格式

系统 SHALL 支持以下 `config.yaml` 解析器配置格式：

```yaml
parser:
  primary: "pymupdf4llm"
  table_enhancer: "pdfplumber"    # 或 null
  pymupdf4llm: { ... }
  fitz: { ... }
  pdfplumber: { ... }
```

#### Scenario: 读取主力解析器配置

- **WHEN** `config.yaml` 中 `parser.primary` 为 `"pymupdf4llm"`
- **THEN** 系统从 `parser.pymupdf4llm` 读取该解析器的参数

#### Scenario: 读取表格补强配置

- **WHEN** `config.yaml` 中 `parser.table_enhancer` 为 `"pdfplumber"`
- **THEN** 系统从 `parser.pdfplumber` 读取补强模块的参数

#### Scenario: 表格补强关闭

- **WHEN** `config.yaml` 中 `parser.table_enhancer` 为 `null` 或不存在
- **THEN** 系统不使用任何表格补强模块

### Requirement: PdfPlumberEnhancer 表格补强模块

系统 SHALL 提供 `PdfPlumberEnhancer`，从 `fitz_pdfplumber_parser.py` 的 pdfplumber 表格提取逻辑拆出，支持配置化参数。

#### Scenario: 精准触发

- **WHEN** 主力解析结果中某页不包含 markdown 表格
- **THEN** 该页跳过 pdfplumber 补强，直接保留主力结果

#### Scenario: 质量过滤

- **WHEN** pdfplumber 提取的表格列数 < `min_columns` 或空单元格比例 > `max_empty_ratio` 或数据行数 < `min_data_rows`
- **THEN** 该表格被过滤，不替换主力结果

#### Scenario: 表格替换

- **WHEN** pdfplumber 提取的表格通过质量过滤
- **THEN** 用 pdfplumber 表格替换主力解析结果中对应位置的 markdown 表格

### Requirement: FitzParser 主力解析器

系统 SHALL 提供 `FitzParser`，从 `fitz_pdfplumber_parser.py` 的 fitz 文本提取逻辑拆出，不含任何 pdfplumber 相关代码。

#### Scenario: 纯文本解析

- **WHEN** 使用 FitzParser 解析 PDF
- **THEN** 返回仅包含 fitz 文本提取结果的 ParseResult，不含 pdfplumber 表格

#### Scenario: 参数化逻辑模块

- **WHEN** 配置 `header_filter: false`
- **THEN** FitzParser 不执行页眉过滤逻辑

### Requirement: 解析器评测系统

系统 SHALL 提供独立的解析器评测入口 `pixi run parser-bench <config>`，复用实验系统的基础设施（配置管理、结果存储、对比报告、增量运行、hash 验证），但独立于 RAG 实验系统。

#### Scenario: 运行基线评测

- **WHEN** 执行 `pixi run parser-bench baseline.yaml`
- **THEN** 系统对配置中所有 pipeline 变体运行解析，计算自动指标，生成报告

#### Scenario: 评测结果存储

- **WHEN** 评测完成
- **THEN** 结果存储在 `data/parser_reports/` 目录下，包含 manifest.json、各变体结果 JSON、解析样本和可读报告

#### Scenario: 自动评测指标

- **WHEN** 评测运行
- **THEN** 系统计算以下自动指标：表格检出率、表格精确率、表格行数准确率、表格列数准确率、单元格空值率、Markdown 合法性

### Requirement: 解析器评测配置格式

系统 SHALL 支持以下评测配置格式：

```yaml
name: "parser_baseline"
description: "解析器基线对比"
pipelines:
  - name: "pymupdf4llm_pure"
    primary:
      algorithm: "pymupdf4llm"
      config: { ... }
    table_enhancer: null
test_pdfs:
  - "data/raw/research_reports/xxx.pdf"
output_dir: "data/parser_reports"
```

#### Scenario: 多 pipeline 对比

- **WHEN** 配置中定义多个 pipeline
- **THEN** 系统对每个 pipeline 运行所有测试 PDF，生成对比报告

## MODIFIED Requirements

### Requirement: ParserRegistry 接口

原有 `ParserRegistry.get(name, config)` 接口保持可用（向后兼容），新增 `ParserRegistry.get(primary, enhancer, primary_config, enhancer_config)` 接口。

### Requirement: config.yaml parser 配置格式

原有 `parser.algorithm` + `parser.pymupdf4llm` / `parser.fitz_pdfplumber` 格式 SHALL 继续可用（向后兼容），同时新增 `parser.primary` + `parser.table_enhancer` 格式。当 `parser.primary` 存在时，使用新格式；否则回退到旧格式。

### Requirement: compute_parser_config_hash

hash 计算 SHALL 适配新配置格式，包含 `primary`、`table_enhancer` 及各自参数，确保不同组合产生不同 hash。

## REMOVED Requirements

无。所有现有功能保持向后兼容。
