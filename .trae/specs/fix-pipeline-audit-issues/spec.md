# 基线链路冒烟问题修复 Spec

## Why

深度勘察报告（`docs/pipeline-deep-audit.md`）揭示了 RAG 基线链路中多个导致评测结果虚高或失真的问题。其中 P6-3（contexts/sources 混淆）是致命级 Bug，直接导致 faithfulness 评估完全失效；其余问题虽非致命，但均为可快速修复的"低悬果实"，修复后可显著提升基线链路的正确性和评测可信度。

## What Changes

- **修复** `BuiltinEvaluator.evaluate_single()` 的 contexts/sources 参数混淆，分离检索来源路径与上下文文本内容
- **修复** `_collect_rag_samples()` 缺失 `chunk_ids` 和 `question_type` 收集
- **修复** `_evaluate_with_builtin()` 传递错误参数给 `evaluate_single()`
- **新增** BGE 模型查询指令前缀支持（`embed_query()` 添加 instruction prefix）
- **新增** System Prompt 可配置化（从 `config.yaml` 读取，不再硬编码）
- **新增** Prompt 中包含来源文档名（解决"引用来源要求模糊"问题）
- **新增** 检索分数阈值过滤（`score_threshold` 配置项）

## Impact

- Affected specs: 评测系统、检索系统、生成系统
- Affected code:
  - `eval/run_experiment.py` — `_collect_rag_samples()`、`_evaluate_with_builtin()`
  - `eval/evaluators/builtin_evaluator.py` — `evaluate_single()` 接口变更
  - `eval/evaluators/base.py` — `EvaluationResult` 可能调整
  - `src/embedder.py` — `embed_query()` 添加 instruction prefix
  - `src/generator.py` — system_prompt 可配置、context 格式包含来源名
  - `src/pipeline.py` — 传递 source 信息给 generator
  - `src/retriever.py` — 添加 score_threshold 过滤
  - `config.yaml` — 新增 `generation.system_prompt`、`retrieval.score_threshold`
  - `tests/` — 相关测试更新

---

## ADDED Requirements

### Requirement: 评测系统 contexts 与 retrieved_sources 分离

系统 SHALL 在评测流程中明确区分"检索到的来源路径"（`retrieved_sources`）和"检索到的上下文文本"（`contexts`），确保检索指标使用来源路径、生成指标使用文本内容。

#### Scenario: Faithfulness 评估使用文本内容

- **WHEN** 评测系统计算 faithfulness 指标
- **THEN** `calculate_faithfulness()` 的 `contexts` 参数 SHALL 接收检索结果的文本内容列表
- **AND** 不 SHALL 接收文件路径列表

#### Scenario: 检索指标使用来源路径

- **WHEN** 评测系统计算 hit_rate / mrr / ndcg 指标
- **THEN** `calculate_hit_rate()` 等函数的 `retrieved_sources` 参数 SHALL 接收来源路径列表
- **AND** 不 SHALL 接收文本内容列表

#### Scenario: Context Precision / Context Recall 使用文本内容

- **WHEN** 评测系统计算 context_precision / context_recall 指标
- **THEN** 这些指标 SHALL 使用文本内容作为 `retrieval_context` 参数

### Requirement: _collect_rag_samples 收集完整数据

`_collect_rag_samples()` SHALL 收集 pipeline 返回的所有评测所需字段。

#### Scenario: 收集 chunk_ids

- **WHEN** pipeline.query() 返回结果中包含 `chunk_ids` 字段
- **THEN** sample 中 SHALL 包含 `chunk_ids` 字段

#### Scenario: 收集 question_type

- **WHEN** 测试集问题数据中包含 `question_type` 字段
- **THEN** sample 中 SHALL 包含 `question_type` 字段

### Requirement: BGE 查询指令前缀

系统 SHALL 在向量化查询时添加 BGE 模型推荐的指令前缀，以提升检索效果。

#### Scenario: 默认添加指令前缀

- **WHEN** 使用 BGE 系列模型（model_name 包含 "bge"）进行查询向量化
- **THEN** `embed_query()` SHALL 自动在查询文本前添加指令前缀 `"为这个句子生成表示以用于检索相关文章："`

#### Scenario: 非BGE模型不添加前缀

- **WHEN** 使用的嵌入模型不是 BGE 系列
- **THEN** `embed_query()` 不 SHALL 添加指令前缀

#### Scenario: 可配置指令前缀

- **WHEN** 用户在 `config.yaml` 的 `embedding` 节中配置了 `query_instruction` 字段
- **THEN** 使用用户配置的指令前缀
- **AND** 若配置为空字符串，则不添加前缀

#### Scenario: 文档向量化不添加前缀

- **WHEN** 使用 `embed_texts()` 对文档文本进行向量化
- **THEN** 不 SHALL 添加指令前缀

### Requirement: System Prompt 可配置

系统 SHALL 支持通过配置文件自定义生成阶段的 System Prompt。

#### Scenario: 使用自定义 System Prompt

- **WHEN** `config.yaml` 的 `generation.system_prompt` 字段有值
- **THEN** Generator 使用配置中的 system_prompt

#### Scenario: 使用默认 System Prompt

- **WHEN** `config.yaml` 的 `generation.system_prompt` 字段为空或不存在
- **THEN** Generator 使用当前硬编码的默认 system_prompt

#### Scenario: 实验配置覆盖 System Prompt

- **WHEN** 实验配置的 `config_overrides` 中包含 `generation.system_prompt`
- **THEN** 使用实验配置中的 system_prompt 覆盖系统配置

### Requirement: Prompt 包含来源文档名

系统 SHALL 在传给 LLM 的 Prompt 中包含每个参考资料的来源文档名，使 LLM 能够真正引用来源。

#### Scenario: 参考资料附带文档名

- **WHEN** Generator 构建 user message
- **THEN** 每条参考资料的格式 SHALL 从 `参考资料 N:\n{text}` 变更为 `参考资料 N（来源：{source_name}）:\n{text}`
- **AND** `source_name` 为文档的文件名（不含路径和扩展名）

### Requirement: 检索分数阈值过滤

系统 SHALL 支持配置检索结果的最低相似度分数阈值，低于阈值的结果将被过滤。

#### Scenario: 配置分数阈值

- **WHEN** `config.yaml` 的 `retrieval.score_threshold` 字段有值（如 0.3）
- **THEN** Retriever 在返回结果前 SHALL 过滤掉 score 低于阈值的结果

#### Scenario: 未配置分数阈值

- **WHEN** `config.yaml` 的 `retrieval.score_threshold` 字段不存在或为 0
- **THEN** Retriever 不进行分数过滤（保持当前行为）

#### Scenario: 过滤后结果不足 top_k

- **WHEN** 分数过滤后剩余结果少于 top_k
- **THEN** 返回过滤后的全部结果（不补充低分结果）

---

## MODIFIED Requirements

### Requirement: BuiltinEvaluator.evaluate_single() 接口

`evaluate_single()` SHALL 新增 `retrieved_sources` 参数，与 `contexts` 参数分离。

**变更**: 新增 `retrieved_sources: Optional[List[str]] = None` 参数。当提供 `retrieved_sources` 时，检索指标使用 `retrieved_sources`；否则回退使用 `contexts`（向后兼容）。

#### Scenario: 同时提供 contexts 和 retrieved_sources

- **WHEN** 调用 `evaluate_single()` 时同时提供 `contexts` 和 `retrieved_sources`
- **THEN** 检索指标使用 `retrieved_sources`，生成指标使用 `contexts`

#### Scenario: 仅提供 contexts（向后兼容）

- **WHEN** 调用 `evaluate_single()` 时仅提供 `contexts`
- **THEN** 检索指标和生成指标都使用 `contexts`（旧行为）

### Requirement: Generator.generate() 接口

`Generator.generate()` SHALL 支持接收来源信息并包含在 Prompt 中。

**变更**: 新增 `sources: Optional[List[str]] = None` 参数。当提供时，在 context 格式化中包含来源文档名。

#### Scenario: 提供来源信息

- **WHEN** 调用 `generate()` 时提供 `sources` 参数
- **THEN** 参考资料格式为 `参考资料 N（来源：{source_name}）:\n{text}`

#### Scenario: 不提供来源信息

- **WHEN** 调用 `generate()` 时不提供 `sources` 参数
- **THEN** 参考资料格式保持 `参考资料 N:\n{text}`（向后兼容）

### Requirement: RAGPipeline.query() 传递来源信息

`RAGPipeline.query()` SHALL 将检索结果的来源信息传递给 Generator。

**变更**: 调用 `generator.generate()` 时传入 `sources` 参数。

#### Scenario: 查询时传递来源

- **WHEN** `pipeline.query()` 调用 `generator.generate()`
- **THEN** SHALL 传入 `sources=sources` 参数

---

## REMOVED Requirements

无移除的需求。所有变更保持向后兼容。
