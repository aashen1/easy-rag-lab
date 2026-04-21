# pymupdf4llm 参数精调与页感知分块 Spec

## Why

当前 PDF 解析流程存在两个关键问题：(1) pipeline.py 未传递 parser_options，导致 config.yaml 中的解析参数完全不生效；(2) pymupdf4llm 默认启用 Layout 模式（`use_layout(True)`），但 `ignore_images` 等参数在该模式下不生效，配置与实际行为不一致。此外，当前分块流程缺乏页码关联，无法在 RAG 检索结果中定位到具体页码，限制了溯源能力。

## What Changes

- **修复** pipeline.py 的 `parser_options` 传递缺失（P0 Bug）
- **修正** config.yaml 中 Layout 模式下无效的 `ignore_images` 配置
- **扩展** parser config hash 包含 options，使参数变更触发重新解析
- **新增** `parse_pdf()` 支持 `page_chunks=True` 返回页级字典列表
- **新增** `parse_all_pdfs()` 支持 `.pages.json` 格式的页级输出
- **新增** `chunk_text_page_aware()` 页感知分块函数，每页独立分块、chunk 携带页码元数据
- **新增** `process_parsed_files_page_aware()` 处理 `.pages.json` 文件的分块流程
- **更新** meal.py 的 `build_chunks_if_needed()` 支持页感知分块路径
- **精调** Layout 模式下可用参数：`ignore_code`、`ocr_language`、`force_text`、`page_separators` 联动
- **更新** config.yaml 参数配置

## Impact

- Affected specs: 解析系统、分块系统、Meal 数据管理
- Affected code:
  - `src/parser.py` — `parse_pdf()` 返回类型扩展、`parse_all_pdfs()` 新增 `.pages.json` 输出
  - `src/chunker.py` — 新增 `chunk_text_page_aware()`、`process_parsed_files_page_aware()`
  - `src/pipeline.py` — 修复 `parser_options` 传递、支持页感知分块路径
  - `src/meal.py` — `compute_parser_config_hash()` 扩展、`build_chunks_if_needed()` 页感知适配、`_build_config_snapshot_and_hashes()` 扩展
  - `config.yaml` — 参数精调与新增 `page_chunks` 等配置
  - `tests/test_parser.py` — 新增 page_chunks 相关测试
  - `tests/test_chunker.py` — 新增页感知分块测试

---

## ADDED Requirements

### Requirement: pipeline.py 传递 parser_options

`RAGPipeline.build_index()` SHALL 将 config.yaml 中的 `parser.pymupdf4llm` 配置作为 `parser_options` 传递给 `parse_all_pdfs()`。

#### Scenario: 通过 pipeline 构建索引时参数生效

- **WHEN** 调用 `pipeline.build_index()` 且 config.yaml 中配置了 `parser.pymupdf4llm` 参数
- **THEN** `parse_all_pdfs()` SHALL 接收到 `parser_options=parser_config.get("pymupdf4llm")`
- **AND** `header: false`、`footer: false` 等参数 SHALL 在解析过程中生效

### Requirement: 移除 Layout 模式下无效的 ignore_images 配置

config.yaml 中的 `ignore_images` 参数在 Layout 模式下不生效，SHALL 被移除或注释说明。

#### Scenario: Layout 模式下图片由模块自行处理

- **WHEN** 使用默认 Layout 模式（`use_layout(True)`）
- **THEN** `ignore_images` 参数 SHALL 不出现在 config.yaml 的 `pymupdf4llm` 节中
- **AND** 图片处理由 Layout 模块自行分类，`write_images: false` 控制不写出图片文件

### Requirement: parser config hash 包含 options

`compute_parser_config_hash()` SHALL 将 `pymupdf4llm` 的 options 纳入 hash 计算，使参数变更触发重新解析。

#### Scenario: 不同解析参数产生不同 hash

- **WHEN** `parser.pymupdf4llm` 配置发生变更（如 `page_chunks: false` → `page_chunks: true`）
- **THEN** `compute_parser_config_hash()` SHALL 返回不同的 hash 值
- **AND** Meal 系统的 ArtifactCache SHALL 视为新配置，触发重新解析

#### Scenario: 向后兼容

- **WHEN** 旧 Meal 的 config_snapshot 中不包含 `options` 字段
- **THEN** hash 计算 SHALL 使用空字典作为默认值，不抛出异常

### Requirement: parse_pdf() 支持 page_chunks

`parse_pdf()` SHALL 支持 `page_chunks` 参数，返回页级字典列表而非单一 Markdown 字符串。

#### Scenario: page_chunks=True 返回页级数据

- **WHEN** 调用 `parse_pdf(pdf_path, page_chunks=True)`
- **THEN** 返回值类型 SHALL 为 `list[dict]`
- **AND** 每个 dict SHALL 包含 `"text"`（页 Markdown）和 `"metadata"`（含 `page_number`、`page_count`、`file_path`）

#### Scenario: page_chunks=False 保持现有行为

- **WHEN** 调用 `parse_pdf(pdf_path, page_chunks=False)` 或不传 `page_chunks`
- **THEN** 返回值类型 SHALL 为 `str`（与当前行为一致）

### Requirement: parse_all_pdfs() 支持 .pages.json 输出

`parse_all_pdfs()` SHALL 在 `page_chunks=True` 时将解析结果保存为 `.pages.json` 格式。

#### Scenario: page_chunks=True 时输出 .pages.json

- **WHEN** `parser_options` 中包含 `page_chunks: True`
- **THEN** 每个解析结果 SHALL 保存为 `{filename}.pages.json`（而非 `.md`）
- **AND** JSON 结构 SHALL 为 `list[dict]`，每个 dict 包含 `text`、`metadata`、`toc_items`、`tables` 字段

#### Scenario: page_chunks=False 时输出 .md

- **WHEN** `parser_options` 中不包含 `page_chunks` 或 `page_chunks: False`
- **THEN** 输出格式 SHALL 保持 `.md`（与当前行为一致）

#### Scenario: 跳过已解析文件时识别 .pages.json

- **WHEN** `force=False` 且 `page_chunks=True`
- **THEN** SHALL 检查 `.pages.json` 文件是否存在（而非 `.md`）来决定是否跳过

### Requirement: 页感知分块 chunk_text_page_aware()

系统 SHALL 提供页感知分块函数，每页独立分块，每个 chunk 携带页码元数据。

#### Scenario: 每页独立分块

- **WHEN** 调用 `chunk_text_page_aware(page_chunks, chunk_size=512)`
- **THEN** 每页的文本 SHALL 独立分块，不产生跨页 chunk
- **AND** 每个 chunk 的 metadata SHALL 包含 `page_number` 字段

#### Scenario: chunk_id 包含页码信息

- **WHEN** 生成 chunk_id
- **THEN** 格式 SHALL 为 `{source_name}_p{page_number}_{chunk_index:03d}`

#### Scenario: 空页跳过

- **WHEN** 某页的 `text` 为空或仅含空白
- **THEN** SHALL 跳过该页，不产生 chunk

### Requirement: process_parsed_files_page_aware()

系统 SHALL 提供处理 `.pages.json` 文件的页感知分块流程。

#### Scenario: 读取 .pages.json 并分块

- **WHEN** 调用 `process_parsed_files_page_aware(input_dir, output_dir, ...)`
- **THEN** SHALL 扫描 input_dir 中的 `.pages.json` 文件
- **AND** 对每个文件调用 `chunk_text_page_aware()` 进行分块
- **AND** 输出标准 JSONL 格式到 output_dir

#### Scenario: 输出 JSONL 中 chunk 包含页码元数据

- **WHEN** 写出 chunk 数据到 JSONL
- **THEN** 每个 chunk 的 metadata SHALL 包含 `page_number` 字段
- **AND** `strategy` 字段 SHALL 为 `"page_aware_fixed"`

### Requirement: meal.py 支持页感知分块路径

`build_chunks_if_needed()` SHALL 自动检测解析结果格式并选择对应的分块流程。

#### Scenario: 存在 .pages.json 时使用页感知分块

- **WHEN** parsed_dir 中存在 `.pages.json` 文件
- **THEN** SHALL 调用 `process_parsed_files_page_aware()` 进行分块

#### Scenario: 仅存在 .md 时使用原有分块

- **WHEN** parsed_dir 中仅存在 `.md` 文件
- **THEN** SHALL 调用 `process_parsed_files()` 进行分块（向后兼容）

### Requirement: Layout 模式参数精调

在 `use_layout(True)` 模式下，SHALL 精调以下可用参数：

#### Scenario: ignore_code=True

- **WHEN** 解析金融研报 PDF
- **THEN** `ignore_code` SHALL 设为 `True`，避免财务数据表格被错误标记为代码块

#### Scenario: ocr_language 支持中文

- **WHEN** 处理中文研报且需要 OCR
- **THEN** `ocr_language` SHALL 设为 `"chi_sim+eng"`，同时支持中文和英文 OCR

#### Scenario: page_chunks 与 page_separators 联动

- **WHEN** `page_chunks=True`
- **THEN** `page_separators` SHALL 自动设为 `False`（避免冗余的页分隔符）
- **WHEN** `page_chunks=False`
- **THEN** `page_separators` SHALL 保持 `True`（提供页码信息）

#### Scenario: force_text 保持 True

- **WHEN** 解析金融研报
- **THEN** `force_text` SHALL 保持 `True`，保留叠加在图表上的文本标注

---

## MODIFIED Requirements

### Requirement: parse_pdf() 返回类型

`parse_pdf()` 的返回类型 SHALL 从 `str` 扩展为 `str | list[dict]`。

**变更**: 新增 `page_chunks: bool = False` 参数。当 `page_chunks=True` 时返回 `list[dict]`，否则返回 `str`。

#### Scenario: 默认行为不变

- **WHEN** 不传 `page_chunks` 参数
- **THEN** 返回类型 SHALL 为 `str`（与当前行为一致）

### Requirement: compute_parser_config_hash() 计算范围

`compute_parser_config_hash()` SHALL 将 `pymupdf4llm` 的 options 纳入 hash 计算。

**变更**: `relevant` 字典从仅包含 `algorithm` 扩展为同时包含 `options`。

#### Scenario: 包含 options 的 hash 计算

- **WHEN** `parser_config` 中包含 `pymupdf4llm` 或 `options` 子键
- **THEN** hash 计算 SHALL 包含这些 options 的完整内容

### Requirement: _build_config_snapshot_and_hashes() 快照范围

`_build_config_snapshot_and_hashes()` SHALL 在 config_snapshot 的 parser 节中包含完整的 options。

**变更**: parser 快照从仅包含 `algorithm` 和 `input_dir` 扩展为同时包含 `options`。

---

## REMOVED Requirements

### Requirement: ignore_images 配置项

**Reason**: `ignore_images` 在 Layout 模式（`use_layout(True)`）下不生效，图片由 Layout 模块自行分类处理，`write_images: false` 已足够控制不写出图片文件。

**Migration**: 从 config.yaml 中移除 `ignore_images: true`，添加注释说明 Layout 模式下的图片处理行为。
