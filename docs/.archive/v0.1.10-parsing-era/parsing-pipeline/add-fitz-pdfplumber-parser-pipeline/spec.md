# 多解析器框架与 fitz+pdfplumber 链路 Spec

## Why

当前 RAG 系统的 PDF→MD 解析仅依赖 pymupdf4llm 单一链路，金融研报/年报中的复杂表格、多栏布局、页眉页脚等场景解析质量不佳。需要引入 fitz+pdfplumber 作为可选的替代解析链路，并建立多解析器框架以支持 A/B 对比实验，为后续引入更多解析方案预留扩展能力。

## What Changes

- **新增** `src/parsers/` 包，实现解析器抽象基类 `BaseParser` 与策略模式框架
- **新增** `FitzPdfPlumberParser` 实现，使用 fitz 做文本/布局提取 + pdfplumber 做表格补强
- **新增** `PymuPDF4LLMParser` 适配器，将现有 `parser.py` 的 `parse_pdf()` 包装为 `BaseParser` 接口
- **新增** `ParserRegistry` 工厂，根据配置字符串选择解析器实现
- **新增** 页级解析结果数据结构 `ParsedPage`，携带 `page_number` 元数据
- **修改** `config.yaml` 的 `parser` 段，支持 `algorithm` 字段选择解析器及各解析器专属配置
- **修改** `meal.py` 的 `compute_parser_config_hash()`，将 `algorithm` + `options` 纳入 hash 计算
- **修改** `meal.py` 的 `create_meal()` / `repair_meal()`，通过 `ParserRegistry` 调用解析器
- **修改** `ArtifactCache`，按 `parser_hash` 隔离不同解析器的产物
- **新增** pytest 测试覆盖所有新增模块

## Impact

- Affected specs: 解析子系统、Meal 管线、Artifact 缓存
- Affected code:
  - `src/parsers/` — 全新包（BaseParser、FitzPdfPlumberParser、PymuPDF4LLMParser、registry）
  - `src/parser.py` — 保留不动，被 PymuPDF4LLMParser 委托调用
  - `src/meal.py` — 修改解析调用方式、config hash 计算、artifact 目录结构
  - `config.yaml` — 扩展 parser 配置结构
  - `tests/` — 新增测试文件

---

## ADDED Requirements

### Requirement: 解析器抽象基类 BaseParser

系统 SHALL 提供解析器抽象基类，定义统一的 PDF 解析接口，使不同解析实现可互换使用。

#### Scenario: 解析单个 PDF 文件

- **WHEN** 调用 `parser.parse(pdf_path)` 方法
- **THEN** 返回 `ParseResult` 对象，包含 `pages: list[ParsedPage]` 和 `metadata: dict`

#### Scenario: 解析结果携带页码元数据

- **WHEN** 解析器完成 PDF 解析
- **THEN** 每个 `ParsedPage` SHALL 包含 `page_number: int`（1-indexed）、`text: str`（Markdown 格式）、`metadata: dict`

#### Scenario: 解析器名称标识

- **WHEN** 访问 `parser.name` 属性
- **THEN** 返回该解析器的唯一标识字符串（如 `"pymupdf4llm"`、`"fitz_pdfplumber"`）

#### Scenario: 解析失败优雅降级

- **WHEN** PDF 解析过程中发生异常
- **THEN** SHALL 记录日志并抛出异常，不 SHALL 静默返回空结果

### Requirement: FitzPdfPlumberParser 实现

系统 SHALL 提供 fitz+pdfplumber 组合解析器，使用 fitz 做文本和布局提取，pdfplumber 做表格专项提取。

#### Scenario: 文本提取

- **WHEN** FitzPdfPlumberParser 处理 PDF 页面
- **THEN** 使用 `fitz.Page.get_text("dict")` 提取文本块，保留字体大小、粗体等元信息
- **AND** 利用 span 的 `size` 和 `flags` 字段检测标题层级，生成 Markdown 标题标记

#### Scenario: 表格提取

- **WHEN** 页面包含表格
- **THEN** 使用 `pdfplumber.Page.find_tables()` 提取表格
- **AND** 将 pdfplumber 提取的表格转为 Markdown 表格格式
- **AND** 用 pdfplumber 表格结果替换 fitz 在同一 bbox 区域的文本输出

#### Scenario: 页眉页脚过滤

- **WHEN** 配置中启用页眉页脚过滤（`header_filter: true` 或 `footer_filter: true`）
- **THEN** 基于文本块的 y 坐标位置（页面顶部/底部比例区域）和内容模式匹配过滤噪声

#### Scenario: 多栏布局检测

- **WHEN** 页面存在双栏排版
- **THEN** 通过文本块 bbox 的 x 坐标分布检测栏数
- **AND** 按左栏→右栏→y 坐标排序重组阅读顺序

#### Scenario: 图片处理

- **WHEN** 页面包含图片
- **THEN** 在 Markdown 中输出 `[图片: 页{page_number}]` 占位标记（不提取图片二进制数据）

#### Scenario: 解析器可配置

- **WHEN** 在 config.yaml 中配置 fitz_pdfplumber 选项
- **THEN** SHALL 支持以下可配置项：
  - `header_filter: bool` — 是否过滤页眉
  - `footer_filter: bool` — 是否过滤页脚
  - `header_zone_ratio: float` — 页眉区域占页面高度比例（默认 0.10）
  - `footer_zone_ratio: float` — 页脚区域占页面高度比例（默认 0.10）
  - `noise_patterns: list[str]` — 噪声文本正则模式列表
  - `table_strategy: str` — pdfplumber 表格策略（"lines" / "text"）
  - `table_settings: dict` — pdfplumber find_tables() 的完整设置
  - `column_detection: bool` — 是否启用多栏检测

### Requirement: PymuPDF4LLMParser 适配器

系统 SHALL 提供 PymuPDF4LLMParser 适配器，将现有 `parser.py` 的 `parse_pdf()` 包装为 `BaseParser` 接口。

#### Scenario: 委托现有函数

- **WHEN** 调用 `PymuPDF4LLMParser.parse(pdf_path)`
- **THEN** 委托调用 `parser.parse_pdf(pdf_path, **options)`
- **AND** 将返回的整篇 Markdown 文本包装为单页 `ParseResult`（`page_number=1`）

#### Scenario: 支持 page_chunks 模式

- **WHEN** 配置中启用 `page_chunks: true`
- **THEN** 调用 `pymupdf4llm.to_markdown(pdf_path, page_chunks=True)`
- **AND** 将每页结果映射为独立的 `ParsedPage`

#### Scenario: 透传 pymupdf4llm 参数

- **WHEN** 配置中包含 pymupdf4llm 专属参数（header, footer, table_strategy 等）
- **THEN** 透传给 `pymupdf4llm.to_markdown()` 调用

### Requirement: 解析器注册表 ParserRegistry

系统 SHALL 提供解析器注册表，根据配置字符串选择并实例化对应的解析器。

#### Scenario: 按名称获取解析器

- **WHEN** 调用 `ParserRegistry.get("fitz_pdfplumber", config)`
- **THEN** 返回 `FitzPdfPlumberParser` 实例，使用 config 中的专属配置初始化

#### Scenario: 未知解析器名称

- **WHEN** 调用 `ParserRegistry.get("unknown_parser", config)`
- **THEN** SHALL 抛出 `ValueError`，列出所有已注册的解析器名称

#### Scenario: 默认解析器

- **WHEN** 配置中未指定 `algorithm` 或值为空
- **THEN** SHALL 使用 `"pymupdf4llm"` 作为默认解析器（向后兼容）

#### Scenario: 注册自定义解析器

- **WHEN** 调用 `ParserRegistry.register("custom", CustomParserClass)`
- **THEN** 后续可通过 `ParserRegistry.get("custom")` 获取该解析器实例

### Requirement: 配置文件扩展

系统 SHALL 在 `config.yaml` 的 `parser` 段支持多解析器配置。

#### Scenario: 配置结构

- **WHEN** 用户在 config.yaml 中编写 parser 配置
- **THEN** SHALL 支持以下结构：
  ```yaml
  parser:
    input_dir: "data/raw"
    output_dir: "data/parsed"
    algorithm: "fitz_pdfplumber"    # 选择解析器
    pymupdf4llm:                    # pymupdf4llm 专属配置
      header: false
      footer: false
      page_separators: true
      ignore_images: true
      write_images: false
    fitz_pdfplumber:                # fitz+pdfplumber 专属配置
      header_filter: true
      footer_filter: true
      table_strategy: "lines"
      table_settings:
        snap_tolerance: 5
        join_tolerance: 5
        edge_min_length: 10
      column_detection: true
      noise_patterns:
        - "请务必阅读.{0,20}声明"
        - "^\\s*\\d+\\s*/\\s*\\d+\\s*$"
  ```

#### Scenario: 向后兼容

- **WHEN** 现有配置中 `algorithm` 为 `"pymupdf4llm"` 或未指定
- **THEN** 行为与当前完全一致

### Requirement: Meal 管线集成

系统 SHALL 在 Meal 管线中通过 ParserRegistry 调用解析器，并将解析器配置纳入缓存隔离。

#### Scenario: 通过 Registry 调用解析器

- **WHEN** `MealManager.create_meal()` 执行解析步骤
- **THEN** SHALL 通过 `ParserRegistry.get(algorithm, config)` 获取解析器实例
- **AND** 调用 `parser.parse(pdf_path)` 获取 `ParseResult`
- **AND** 将 `ParseResult.pages` 的文本写入 .md 文件

#### Scenario: 解析器配置纳入 hash

- **WHEN** 计算 `parser_config_hash`
- **THEN** SHALL 将 `algorithm` 和对应解析器的 `options` 纳入 hash 计算
- **AND** 不同解析器或不同参数产生不同的 hash，触发重新解析

#### Scenario: 产物按 parser hash 隔离

- **WHEN** 不同解析器处理同一份 PDF
- **THEN** 解析产物 SHALL 存储在不同的 artifact 目录中（通过 parser hash 区分）

### Requirement: A/B 对比实验框架预留

系统 SHALL 预留 A/B 对比实验的基础设施，使不同解析器的结果可在同一测试集上对比。

#### Scenario: 等价组支持不同解析器

- **WHEN** 使用不同 `algorithm` 配置创建两个 Meal
- **THEN** 两个 Meal 可共享相同的 PDF 文件集和测试集
- **AND** 通过 Meal 的 `config_snapshot.parser.algorithm` 字段区分解析器

#### Scenario: 实验配置覆盖解析器

- **WHEN** 实验配置的 `config_overrides` 中包含 `parser.algorithm`
- **THEN** 使用实验配置指定的解析器覆盖系统默认

---

## MODIFIED Requirements

### Requirement: compute_parser_config_hash 扩展

`compute_parser_config_hash()` SHALL 将解析器算法名称和对应选项纳入 hash 计算。

**变更**: hash 计算范围从 `{"algorithm": ...}` 扩展为 `{"algorithm": ..., "options": {...}}`。

#### Scenario: 包含解析器选项

- **WHEN** 计算 parser config hash
- **THEN** SHALL 包含 `algorithm` 和对应解析器的 `options`（如 `pymupdf4llm` 或 `fitz_pdfplumber` 的配置项）

#### Scenario: 向后兼容

- **WHEN** 旧配置仅包含 `algorithm` 而无 `options`
- **THEN** hash 计算结果 SHALL 与旧版一致（options 默认为空 dict）

### Requirement: ArtifactCache 解析产物目录结构

`ArtifactCache` SHALL 支持按 parser hash 隔离解析产物。

**变更**: `get_parsed_dir()` 增加 `parser_hash` 参数，解析产物存储在 `parsed_{parser_hash}/` 子目录中。

#### Scenario: 不同解析器产物隔离

- **WHEN** parser_hash 为 "a1b2c3d4"
- **THEN** 解析产物目录为 `{artifact_group}/parsed_a1b2c3d4/`

#### Scenario: 向后兼容

- **WHEN** 不提供 parser_hash 参数
- **THEN** 使用默认目录 `parsed/`（兼容旧数据）

---

## REMOVED Requirements

无移除的需求。所有变更保持向后兼容。
