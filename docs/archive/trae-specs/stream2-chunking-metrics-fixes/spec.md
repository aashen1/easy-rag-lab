# Stream 2 — 分块层 + 指标工具层 Issue 链修复 Spec

## Why

当前分块层和指标工具层存在五个相互关联的问题：chunk_id 使用下划线分隔导致含下划线的文件名解析歧义；normalize_source 仅取 stem 无法区分不同目录下的同名文档；chunk_overlap=0 导致跨 chunk 边界信息丢失；chunk 元数据缺少页码和标题层级信息；tiktoken 与 BGE tokenizer 的 token 计数差异未量化，可能导致向量化截断。这些问题需要按依赖顺序系统性修复。

## What Changes

- **RF-013**: chunk_id 分隔符从 `_` 改为 `::chunk::`，`_parse_chunk_id` 支持新旧格式向后兼容
- **RF-014**: `normalize_source` 增加 `include_parent` 参数，默认返回 `{parent_dir}/{stem}` 格式
- **INV-015**: 创建 tokenizer 差异量化分析脚本，量化 tiktoken cl100k_base 与 BGE WordPiece 的 token 计数差异
- **INV-010**: parser 输出页码标记，chunker/semantic_chunker 在元数据中增加 `page_start`、`page_end`、`headings` 字段
- **OPT-007**: 创建 overlap 对比实验配置，根据实验结果更新基线 chunk_overlap 默认值

## Impact

- Affected code: `src/chunker.py`, `src/semantic_chunker.py`, `src/parser.py`, `eval/metrics/utils.py`, `eval/metrics/chunk.py`, `eval/metrics/dedup.py`, `eval/metrics/retrieval.py`, `eval/evaluators/builtin_evaluator.py`, `config.yaml`
- Affected tests: `tests/test_chunker.py`, `tests/test_metrics.py`, 以及所有硬编码旧格式 chunk_id 的测试文件
- **BREAKING**: chunk_id 格式变更（`_` → `::chunk::`），但 `_parse_chunk_id` 向后兼容旧格式

---

## ADDED Requirements

### Requirement: INV-015 — tiktoken/BGE tokenizer 差异量化

系统 SHALL 提供分析脚本 `scripts/analyze_tokenizer_diff.py`，对现有 chunks JSONL 文件中的文本分别用 tiktoken cl100k_base 和 BGE WordPiece tokenizer 计数，输出统计报告。

#### Scenario: 分析脚本正常运行
- **WHEN** 运行 `pixi run python scripts/analyze_tokenizer_diff.py --input_dir <chunks_dir>`
- **THEN** 输出包含：总 chunk 数、两种 tokenizer 的 token 数分布（min/max/mean/median）、超出 BGE 512 token 的 chunk 数和占比
- **AND** 结论明确：是否需要调整 chunk_size 或切换 tokenizer

#### Scenario: 无 chunks 数据
- **WHEN** 指定目录下无 JSONL 文件
- **THEN** 脚本输出提示信息，不崩溃

### Requirement: RF-013 — chunk_id 命名规范化

系统 SHALL 将 chunk_id 格式从 `{source_name}_{chunk_index:03d}` 改为 `{source_name}::chunk::{chunk_index:03d}`。

#### Scenario: 新格式 chunk_id 生成
- **WHEN** chunker 或 semantic_chunker 处理文件生成 chunks
- **THEN** chunk_id 格式为 `{source_name}::chunk::{index:03d}`

#### Scenario: 新格式 chunk_id 解析
- **WHEN** `_parse_chunk_id` 接收 `"贵州茅台2023年年度报告_英文版_::chunk::003"`
- **THEN** 返回 `("贵州茅台2023年年度报告_英文版_", 3)`

#### Scenario: 旧格式 chunk_id 向后兼容
- **WHEN** `_parse_chunk_id` 接收 `"贵州茅台2023年年度报告_英文版__003"`（旧格式）
- **THEN** 返回 `("贵州茅台2023年年度报告_英文版_", 3)`（仍能正确解析）

#### Scenario: 含下划线的文件名不再产生歧义
- **WHEN** source_name 为 `"2023年度报告_英文版_"`，chunk_index 为 3
- **THEN** chunk_id 为 `"2023年度报告_英文版_::chunk::003"`，解析时 doc_stem 为 `"2023年度报告_英文版_"`，无歧义

### Requirement: RF-014 — normalize_source 匹配精度提升

系统 SHALL 增强 `normalize_source` 函数，支持返回 `{parent_dir}/{stem}` 格式，避免不同目录下同名文档被误判。

#### Scenario: 含父目录的路径
- **WHEN** `normalize_source("annual_reports/2025/贵州茅台.md", include_parent=True)`
- **THEN** 返回 `"2025/贵州茅台"`

#### Scenario: 无父目录的路径
- **WHEN** `normalize_source("贵州茅台.md", include_parent=True)`
- **THEN** 返回 `"贵州茅台"`

#### Scenario: 父目录为当前目录
- **WHEN** `normalize_source("./贵州茅台.md", include_parent=True)`
- **THEN** 返回 `"贵州茅台"`

#### Scenario: 向后兼容
- **WHEN** `normalize_source("annual_reports/2025/贵州茅台.md", include_parent=False)`
- **THEN** 返回 `"贵州茅台"`（旧行为不变）

#### Scenario: normalize_source_with_equivalence 适配
- **WHEN** `normalize_source_with_equivalence` 内部调用 `normalize_source`
- **THEN** 传递 `include_parent` 参数，等价组匹配逻辑正常工作

### Requirement: INV-010 — 元数据增强（PDF 页码 + MD 标题层级）

系统 SHALL 在 chunk 元数据中增加 PDF 页码范围和 MD 标题层级信息。

#### Scenario: 解析后的 MD 文件包含页码标记
- **WHEN** parser 处理含 page_separators 的 PDF
- **THEN** 输出的 MD 文件中包含 `<!-- page: N -->` 形式的页码标记

#### Scenario: chunk 元数据包含页码范围
- **WHEN** chunker 处理含页码标记的 MD 文件
- **THEN** 每个 chunk 的 metadata 包含 `page_start`（int | None）和 `page_end`（int | None）字段

#### Scenario: chunk 元数据包含标题层级
- **WHEN** chunker 处理含 Markdown 标题的 MD 文件
- **THEN** 每个 chunk 的 metadata 包含 `headings`（list[str]）字段，记录该 chunk 包含的标题列表

#### Scenario: 无页码标记的旧 MD 文件兼容
- **WHEN** chunker 处理不含页码标记的 MD 文件
- **THEN** `page_start` 和 `page_end` 为 None，不崩溃

### Requirement: OPT-007 — 基线 chunk_overlap 非零优化

系统 SHALL 提供 overlap 对比实验配置，并根据实验结果更新基线默认值。

#### Scenario: overlap 对比实验配置可用
- **WHEN** 运行 `pixi run python -m exp.run --config exp_configs/experiments/overlap_comparison.yaml`
- **THEN** 对比 overlap 值 0、32、64、128 的实验正常运行

#### Scenario: 基线默认值更新
- **WHEN** 实验完成后
- **THEN** `config.yaml` 中 `chunker.chunk_overlap` 更新为实验推荐值

---

## MODIFIED Requirements

### Requirement: _parse_chunk_id 解析逻辑

原实现使用 `rfind("_")` 分割 chunk_id，现改为优先按 `::chunk::` 分割，旧格式 fallback 到 `rfind("_")`。

### Requirement: normalize_source 函数签名

原签名 `normalize_source(source: str) -> str`，现改为 `normalize_source(source: str, include_parent: bool = True) -> str`，默认行为变更（返回含父目录的格式）。

### Requirement: chunker/semantic_chunker 输出格式

chunk_id 格式从 `{source_name}_{index:03d}` 改为 `{source_name}::chunk::{index:03d}`，metadata 增加 `page_start`、`page_end`、`headings` 可选字段。

---

## REMOVED Requirements

无移除的需求。
