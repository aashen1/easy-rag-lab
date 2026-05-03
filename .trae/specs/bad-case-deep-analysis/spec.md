# Bad Case 深度分析模式 Spec

## Why

项目已具备 Bad Case 收集能力（`case_collector.py`），但分析层面完全空白——无法追溯管线中间步骤、无法标注 Ground Truth、无法自动诊断根因。当用户发现 RAG 回答错误时，只能凭猜测判断是检索问题还是生成问题，效率极低。需要一个交互式深度分析工具，让用户从 Bad Case 标记出发，逐步追溯管线链路，定位根因。

## What Changes

- 新增 `PipelineTrace` 数据模型，捕获 `query()` 各阶段中间结果（改写查询、检索结果、重排序变化、上下文组装、完整 Prompt）
- 扩展 `RAGPipeline.query()` 支持 `capture_trace` 参数，默认关闭，不影响现有行为
- 扩展 `case_collector.py` 存储 trace、ground_truth、diagnosis 数据
- 新增 `ground_truth_finder.py`：根据 PDF + 页码查找对应 chunk
- 新增 `retrieval_analyzer.py`：计算 Ground Truth chunk 在检索链路中的位置和分数
- 新增 `case_diagnoser.py`：6 类根因自动诊断（RC-0~RC-5）+ 修复建议
- 新增 Streamlit 分析页面 `case_analyzer.py`：管线链路总览、逐阶段展开、Ground Truth 标注、诊断报告
- 修改 `qa_demo.py`：查询时默认捕获 trace，标记 Bad Case 后可进入深度分析

## Impact

- Affected code: `src/pipeline.py`（新增参数）、`src/generator.py`（暴露 prompt 构建细节）、`src/case_collector.py`（扩展存储）、`src/app_pages/qa_demo.py`（集成入口）、`src/app.py`（新增 Tab）
- 新增文件: `src/trace_models.py`, `src/ground_truth_finder.py`, `src/retrieval_analyzer.py`, `src/case_diagnoser.py`, `src/app_pages/case_analyzer.py`
- 向后兼容: `capture_trace=False` 为默认值，现有调用链不受影响

---

## ADDED Requirements

### Requirement: Pipeline Trace 捕获

系统 SHALL 在 `RAGPipeline.query()` 中支持 `capture_trace: bool = False` 参数。当 `capture_trace=True` 时，系统 SHALL 在管线各阶段记录 `TraceStep`，并在返回值中增加 `trace` 字段。

#### Scenario: 默认行为不变
- **WHEN** 调用 `pipeline.query(question)` 不传 `capture_trace`
- **THEN** 行为与现有完全一致，返回值不含 `trace` 字段

#### Scenario: 开启 trace 捕获
- **WHEN** 调用 `pipeline.query(question, capture_trace=True)`
- **THEN** 返回值包含 `trace` 字段，类型为 `PipelineTrace`
- **AND** trace 包含 5 个阶段的 `TraceStep`：query_rewrite、retrieval、rerank（如启用）、context_assembly、generation
- **AND** 每个 TraceStep 包含 stage、input_data、output_data、duration_ms、metadata

#### Scenario: 各阶段捕获内容
- **WHEN** trace 捕获开启
- **THEN** query_rewrite 阶段记录原始问题、改写后查询列表、is_multi、策略名
- **AND** retrieval 阶段记录查询文本、top_k、检索结果列表（chunk_id、text、score、metadata）、检索方法
- **AND** rerank 阶段记录排序前后的结果列表及 rerank_score 变化、reranker 模型名
- **AND** context_assembly 阶段记录截断前后的 contexts 数量、拼接后的完整 user_message、max_context_tokens
- **AND** generation 阶段记录 system_prompt、user_message、LLM 回答、token_usage、模型名

### Requirement: Trace 数据模型

系统 SHALL 在 `src/trace_models.py` 中定义 `TraceStep` 和 `PipelineTrace` 数据类。

#### Scenario: TraceStep 结构
- **WHEN** 创建 TraceStep
- **THEN** 包含字段: stage (str)、input_data (dict)、output_data (dict)、duration_ms (float)、metadata (dict)
- **AND** 提供 `to_dict()` 方法用于 JSON 序列化

#### Scenario: PipelineTrace 结构
- **WHEN** 创建 PipelineTrace
- **THEN** 包含字段: trace_id (str)、question (str)、steps (list[TraceStep])、created_at (str)
- **AND** 提供 `to_dict()` 和 `from_dict()` 类方法用于序列化/反序列化

### Requirement: Case 存储扩展

系统 SHALL 扩展 `case_collector.py`，支持存储 trace、ground_truth、diagnosis 数据。

#### Scenario: 保存带 trace 的 case
- **WHEN** 调用 `save_case(..., trace=pipeline_trace)`
- **THEN** 在 case 目录下写入 `pipeline_trace.json`

#### Scenario: 保存 Ground Truth
- **WHEN** 调用 `save_ground_truth(case_id, ground_truth)`
- **THEN** 在 case 目录下写入 `ground_truth.json`
- **AND** 更新 manifest 中的 `has_ground_truth` 字段为 true

#### Scenario: 保存诊断结果
- **WHEN** 调用 `save_diagnosis(case_id, diagnosis)`
- **THEN** 在 case 目录下写入 `diagnosis.json`
- **AND** 更新 manifest 中的 `has_diagnosis` 字段为 true 和 `root_cause` 字段

#### Scenario: 加载扩展数据
- **WHEN** 调用 `load_case(case_id)`
- **THEN** 返回值包含 `pipeline_trace`、`ground_truth`、`diagnosis` 键（如对应文件存在）

### Requirement: Ground Truth 标注模型

系统 SHALL 在 `src/trace_models.py` 中定义 `GroundTruth` 数据类。

#### Scenario: GroundTruth 结构
- **WHEN** 创建 GroundTruth
- **THEN** 包含字段: answer_text (str)、source_pdf (str)、source_page (int | None)、chunk_ids (list[str] | None)、annotated_at (str)、annotator (str, 默认 "user")
- **AND** 提供 `to_dict()` 和 `from_dict()` 方法

### Requirement: Ground Truth Chunk 查找

系统 SHALL 提供 `find_chunks_by_source_page()` 函数，根据 PDF 文件名和页码查找对应的 chunk。

#### Scenario: 精确查找
- **WHEN** 调用 `find_chunks_by_source_page(source_pdf, page_number, chunks_dir)`
- **THEN** 从 chunks JSONL 文件中查找 metadata.source 匹配且 metadata.page_numbers 包含 page_number 的 chunk
- **AND** 返回匹配的 chunk 列表（含 chunk_id、text、metadata）

#### Scenario: 模糊查找
- **WHEN** 精确匹配无结果
- **THEN** 回退到页码范围匹配（page_number 在 chunk 的 page_numbers 范围内）
- **AND** 返回匹配的 chunk 列表

#### Scenario: 无匹配
- **WHEN** 无任何匹配
- **THEN** 返回空列表

### Requirement: 检索质量分析

系统 SHALL 提供 `compute_ground_truth_metrics()` 函数，计算 Ground Truth chunk 在检索链路中的表现。

#### Scenario: 分析检索结果
- **WHEN** 调用 `compute_ground_truth_metrics(trace, ground_truth_chunk_ids)`
- **THEN** 返回包含以下字段的字典:
  - `found_in_retrieval` (bool): 是否在检索结果中
  - `retrieval_rank` (int | None): 检索排名（1-based）
  - `retrieval_score` (float | None): 检索分数
  - `found_in_rerank` (bool): 是否在重排序结果中
  - `rerank_rank` (int | None): 重排序排名
  - `rerank_score` (float | None): 重排序分数
  - `found_in_context` (bool): 是否在最终上下文中
  - `context_dropped` (bool): 是否被截断丢弃

### Requirement: 根因诊断引擎

系统 SHALL 提供 `diagnose()` 函数，根据 trace 和 ground truth 自动诊断 bad case 根因。

#### Scenario: RC-0 healthy
- **WHEN** Ground Truth chunk 在 top-1 且答案与 Ground Truth 匹配
- **THEN** 返回 root_cause="healthy"、severity="low"

#### Scenario: RC-1 retrieval_miss
- **WHEN** Ground Truth chunk 不在检索结果中
- **THEN** 返回 root_cause="retrieval_miss"、severity="high"
- **AND** fix_suggestion 包含增大 top_k 或更换检索方法的建议

#### Scenario: RC-2 rank_too_low
- **WHEN** Ground Truth chunk 在检索结果中但排名 > 3
- **THEN** 返回 root_cause="rank_too_low"、severity="medium"
- **AND** fix_suggestion 包含启用 reranker 的建议

#### Scenario: RC-3 context_dropped
- **WHEN** Ground Truth chunk 被上下文截断丢弃
- **THEN** 返回 root_cause="context_dropped"、severity="high"
- **AND** fix_suggestion 包含增大 max_context_tokens 的建议

#### Scenario: RC-4 generation_failure
- **WHEN** Ground Truth chunk 在最终上下文中但答案不匹配
- **THEN** 返回 root_cause="generation_failure"、severity="medium"
- **AND** fix_suggestion 包含调整系统提示词或更换模型的建议

#### Scenario: RC-5 query_mismatch
- **WHEN** 查询改写后仍无法命中正确 chunk（改写查询的检索结果中也不含 Ground Truth chunk）
- **THEN** 返回 root_cause="query_mismatch"、severity="medium"
- **AND** fix_suggestion 包含调整查询改写策略的建议

#### Scenario: 诊断结果结构
- **WHEN** 诊断完成
- **THEN** 返回 `DiagnosisResult` 包含: root_cause (str)、root_cause_id (str, 如 "RC-1")、severity (str)、finding (str)、fix_suggestion (str)、config_patch (dict)、confidence (float)

### Requirement: 交互式分析 UI — Case 列表

系统 SHALL 在 Streamlit 中新增 "🔍 Bad Case 分析" Tab，展示所有 bad case 列表。

#### Scenario: 列表展示
- **WHEN** 用户进入 Bad Case 分析 Tab
- **THEN** 展示所有 bad case 列表（按时间倒序）
- **AND** 每条显示: 问题预览、创建时间、诊断状态标签（已诊断/未诊断）、根因标签（如已诊断）

#### Scenario: 进入分析
- **WHEN** 用户点击某个 case
- **THEN** 进入该 case 的深度分析视图

### Requirement: 交互式分析 UI — 管线链路总览

系统 SHALL 在 case 分析视图中展示管线链路流水线图。

#### Scenario: 链路展示
- **WHEN** case 包含 pipeline_trace 数据
- **THEN** 展示 5 个阶段的流水线图，每个阶段显示关键指标（耗时、输入/输出数量）
- **AND** 正常阶段绿色标识，问题阶段红色标识

#### Scenario: 无 trace 数据
- **WHEN** case 不包含 pipeline_trace 数据
- **THEN** 显示提示"该 case 未捕获管线追踪数据"

### Requirement: 交互式分析 UI — 逐阶段展开

系统 SHALL 支持用户点击某阶段查看完整输入/输出。

#### Scenario: 检索阶段展开
- **WHEN** 用户点击检索阶段
- **THEN** 展示每个 chunk 的文本（截断显示）、分数、来源文件名、页码

#### Scenario: 重排序阶段展开
- **WHEN** 用户点击重排序阶段
- **THEN** 展示排序变化（原始排名 → 重排序后排名）、分数对比（原始 score vs rerank_score）

#### Scenario: 生成阶段展开
- **WHEN** 用户点击生成阶段
- **THEN** 展示完整 system_prompt、user_message、LLM 回答

### Requirement: 交互式分析 UI — Ground Truth 标注

系统 SHALL 支持用户在分析视图中标注 Ground Truth。

#### Scenario: 标注流程
- **WHEN** 用户选择 PDF 文件（下拉框，来自 Meal 快照中的 PDF 列表）和页码
- **AND** 可选输入正确答案文本
- **AND** 点击"查找 Chunk"
- **THEN** 系统展示匹配的 chunk 列表
- **AND** 用户确认后保存 ground_truth

#### Scenario: 已有 Ground Truth
- **WHEN** case 已有 ground_truth 数据
- **THEN** 展示已标注的 Ground Truth 信息，支持重新标注

### Requirement: 交互式分析 UI — 诊断报告

系统 SHALL 在标注 Ground Truth 后自动执行诊断并展示报告。

#### Scenario: 自动诊断
- **WHEN** 用户保存 Ground Truth 后
- **THEN** 系统自动调用 `diagnose()` 执行根因诊断
- **AND** 展示诊断报告: 根因分类（大号标签 + 颜色编码）、严重程度、发现描述、修复建议、配置补丁

#### Scenario: 已有诊断
- **WHEN** case 已有 diagnosis 数据
- **THEN** 直接展示诊断报告，无需重新诊断

### Requirement: 深度分析入口集成

系统 SHALL 在标记 Bad Case 后提供进入深度分析的入口。

#### Scenario: 标记后提示
- **WHEN** 用户在问答页面点击 Badcase 按钮
- **THEN** 保存 case（现有逻辑不变）
- **AND** 弹出 toast 提示"已保存，可到「🔍 Bad Case 分析」标签页进行深度分析"

#### Scenario: 查询时捕获 trace
- **WHEN** 用户在问答页面发起查询
- **THEN** 自动以 `capture_trace=True` 执行查询
- **AND** trace 数据存入 `st.session_state.messages` 的对应消息中
- **AND** 保存 case 时自动附带 trace 数据

## MODIFIED Requirements

### Requirement: RAGPipeline.query() 签名

现有签名: `query(self, question, return_contexts=True, config_overrides=None)`

修改为: `query(self, question, return_contexts=True, config_overrides=None, capture_trace=False)`

当 `capture_trace=False`（默认）时，行为完全不变。当 `capture_trace=True` 时，返回值增加 `trace` 键。

### Requirement: Generator.generate() 暴露 prompt 构建细节

现有 `generate()` 方法内部构建 system_prompt 和 user_message，但不返回这些中间数据。修改为：当 `capture_trace=True` 时（通过新参数 `return_prompt_details: bool = False`），返回值从纯字符串改为包含 answer、system_prompt、user_message、truncated_count 的字典。

**BREAKING**: 无。`return_prompt_details=False` 为默认值，保持返回纯字符串的现有行为。

### Requirement: case_collector.save_case() 签名

现有签名: `save_case(case_type, question, result, config_overrides, base_config, meal_config=None, meal_name=None)`

修改为: `save_case(case_type, question, result, config_overrides, base_config, meal_config=None, meal_name=None, trace=None)`

新增可选参数 `trace: PipelineTrace | None = None`。当 trace 不为 None 时，写入 `pipeline_trace.json`。

### Requirement: qa_demo.py 消息结构

现有 assistant 消息结构:
```python
{"role": "assistant", "result": {...}, "config_overrides": {...}, "meal_name": "..."}
```

修改为:
```python
{"role": "assistant", "result": {...}, "config_overrides": {...}, "meal_name": "...", "trace": {...} | None}
```

新增 `trace` 键，存储 `PipelineTrace.to_dict()` 的结果。

## REMOVED Requirements

无。所有现有功能保持不变。
