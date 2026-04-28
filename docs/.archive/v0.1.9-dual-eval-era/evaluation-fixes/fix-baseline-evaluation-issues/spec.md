# 基线评估链路修复 Spec

## Why

基线评估实验（`exp_20260423_015208`）的检索指标（Hit Rate/MRR/NDCG）全部为 0，评测结果不可信。深度勘察报告识别出多个阻塞级和高优先级问题，需要按优先级逐步修复，使链路产出第一份可信的评测结果。

## What Changes

- **修复 Source 路径跨平台归一化**：chunker 写入 source 字段时统一使用 POSIX 格式（正斜杠），evaluator 无等价组时也进行归一化比较
- **修复等价组推断逻辑**：等价组 group_key 加入父目录信息，避免不同目录下同名文件被错误归组
- **修复 Generator 来源名称显示**：清理 `.pages` 后缀，使 LLM 看到干净的来源名称
- **启用 Score Threshold 配置**：将 `score_threshold` 从 0 调整为合理初始值
- **启用 Context 截断保护**：将 `max_context_tokens` 从 null 设为合理值
- **统一 Chunker 与 Embedder 的 Tokenizer**：chunker 改用 BGE tokenizer 切分，消除 tokenizer 不匹配导致的截断问题
- **增加跨页 Chunk Overlap 选项**：在 `page_aware_fixed` 策略中支持跨页上下文保留

## Impact

- Affected specs: 评测链路可靠性、检索指标计算、生成质量
- Affected code: `src/chunker.py`, `src/generator.py`, `src/meal.py`, `src/embedder.py`, `eval/metrics/utils.py`, `eval/evaluators/builtin_evaluator.py`, `config.yaml`

## ADDED Requirements

### Requirement: Source 路径跨平台归一化

系统 SHALL 在所有写入 source 路径的位置统一使用 POSIX 格式（正斜杠），确保 Windows/Linux/macOS 路径格式一致。

#### Scenario: Chunker 写入 source 字段
- **WHEN** chunker 在 JSONL 中写入 `source` 字段
- **THEN** source 值使用 POSIX 格式（正斜杠），不包含平台特定的路径分隔符

#### Scenario: Evaluator 无等价组时比较 source
- **WHEN** evaluator 在无等价组的情况下比较 retrieved 和 expected 的 source
- **THEN** 比较前对双方路径进行归一化处理（POSIX 格式 + 去除冗余后缀）

### Requirement: 等价组推断加入父目录信息

系统 SHALL 在推断等价组时将父目录信息纳入 group_key，避免不同目录下同名文件被错误归组。

#### Scenario: 不同目录下同名文件
- **WHEN** 存在 `annual_reports/2023/云南白药/2023年年度报告.pdf` 和 `annual_reports/2023/隆基绿能/2023年年度报告.pdf`
- **THEN** 两者被归入不同的等价组（group_key 包含父目录区分信息）

#### Scenario: 同一目录下的同名不同版本文件
- **WHEN** 存在 `annual_reports/2023/云南白药/2023年年度报告.pdf` 和 `annual_reports/2023/云南白药/2023年年度报告_英文版_.pdf`
- **THEN** 两者被归入同一等价组（符合当前后缀剥离逻辑）

### Requirement: Generator 来源名称清理

系统 SHALL 在 Generator 构建 Prompt 时清理来源名称中的 `.pages` 后缀，使 LLM 看到干净的文档名。

#### Scenario: Page-aware 模式下的来源名称
- **WHEN** source 为 `research_reports/2026现代女性精力管理现状报告.pages.json`
- **THEN** LLM 看到的来源名称为 `2026现代女性精力管理现状报告`（不含 `.pages` 后缀）

#### Scenario: 非 page-aware 模式下的来源名称
- **WHEN** source 为 `annual_reports/2023/贵州茅台2023年年度报告.md`
- **THEN** LLM 看到的来源名称为 `贵州茅台2023年年度报告`（保持现有行为）

### Requirement: Score Threshold 合理配置

系统 SHALL 将 `score_threshold` 默认值设为合理阈值（0.3），过滤低相似度检索结果。

#### Scenario: 相似度低于阈值
- **WHEN** 检索结果的相似度分数低于 `score_threshold`
- **THEN** 该结果被过滤，不传递给 LLM

#### Scenario: 相似度高于阈值
- **WHEN** 检索结果的相似度分数高于 `score_threshold`
- **THEN** 该结果正常返回

### Requirement: Context 截断保护启用

系统 SHALL 将 `max_context_tokens` 设为合理值（8000），防止上下文超出模型窗口。

#### Scenario: 上下文 token 总数超过限制
- **WHEN** system_prompt + contexts + query 的总 token 数超过 `max_context_tokens`
- **THEN** 系统截断 contexts 使总 token 数不超过限制

#### Scenario: 上下文 token 总数未超限
- **WHEN** 总 token 数未超过 `max_context_tokens`
- **THEN** 不进行截断

### Requirement: Chunker 使用 Embedding Tokenizer 切分

系统 SHALL 在 chunker 中支持使用与 embedder 相同的 tokenizer（BGE tokenizer）进行 token 计数和切分，消除 tiktoken 与 BGE tokenizer 的不一致。

#### Scenario: 使用 BGE tokenizer 切分
- **WHEN** config.yaml 中 `chunker.encoding` 设为 `bge` 或 embedder 模型对应的 tokenizer
- **THEN** chunker 使用 BGE tokenizer 进行 token 计数和切分，确保 chunk token 数与 embedder 一致

#### Scenario: 向后兼容 tiktoken
- **WHEN** config.yaml 中 `chunker.encoding` 设为 `cl100k_base`（默认值）
- **THEN** chunker 使用 tiktoken 进行 token 计数和切分（保持现有行为）

### Requirement: 跨页 Chunk Overlap 支持

系统 SHALL 在 `page_aware_fixed` 策略中支持跨页上下文保留，通过 `cross_page_overlap` 配置项控制。

#### Scenario: 启用跨页 overlap
- **WHEN** `cross_page_overlap` 设为正值（如 64）
- **THEN** 上一页的最后 N 个 tokens 与下一页的开头重叠，保留跨页上下文

#### Scenario: 禁用跨页 overlap（默认）
- **WHEN** `cross_page_overlap` 设为 0 或 null
- **THEN** 每页独立分块，无跨页重叠（保持现有行为）

## MODIFIED Requirements

### Requirement: normalize_source 跨平台路径处理

`normalize_source` 函数 SHALL 在内部统一使用 `Path.as_posix()` 处理路径，确保输入路径无论是 Windows 反斜杠还是 POSIX 正斜杠，输出格式一致。

## REMOVED Requirements

无移除的需求。
