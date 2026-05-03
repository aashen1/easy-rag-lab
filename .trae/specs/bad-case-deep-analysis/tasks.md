# Tasks

- [x] Task 1: 创建 Trace 数据模型 (`src/trace_models.py`)
  - [x] 1.1 定义 `TraceStep` dataclass (stage, input_data, output_data, duration_ms, metadata) + to_dict()
  - [x] 1.2 定义 `PipelineTrace` dataclass (trace_id, question, steps, created_at) + to_dict() / from_dict()
  - [x] 1.3 定义 `GroundTruth` dataclass (answer_text, source_pdf, source_page, chunk_ids, annotated_at, annotator) + to_dict() / from_dict()
  - [x] 1.4 定义 `DiagnosisResult` dataclass (root_cause, root_cause_id, severity, finding, fix_suggestion, config_patch, confidence) + to_dict() / from_dict()
  - [x] 1.5 编写 `tests/test_trace_models.py`：序列化/反序列化、字段完整性

- [x] Task 2: 改造 `RAGPipeline.query()` 支持 trace 捕获
  - [x] 2.1 新增 `capture_trace: bool = False` 参数
  - [x] 2.2 在 query_rewrite 阶段记录 TraceStep（原始问题 → 改写查询列表 + is_multi + 策略名）
  - [x] 2.3 在 retrieval 阶段记录 TraceStep（查询文本 + top_k → 检索结果列表 + 检索方法）
  - [x] 2.4 在 rerank 阶段记录 TraceStep（排序前结果 → 排序后结果 + rerank_score + 模型名）
  - [x] 2.5 在 context_assembly 阶段记录 TraceStep（截断前 contexts 数 → 截断后 contexts + 完整 user_message + max_context_tokens）
  - [x] 2.6 在 generation 阶段记录 TraceStep（system_prompt + user_message → LLM 回答 + token_usage + 模型名）
  - [x] 2.7 组装 PipelineTrace 并附加到返回值
  - [x] 2.8 改造 `Generator.generate()` 新增 `return_prompt_details: bool = False` 参数，暴露 system_prompt / user_message / truncated_count

- [x] Task 3: 扩展 Case 存储 (`src/case_collector.py`)
  - [x] 3.1 `save_case()` 新增 `trace: PipelineTrace | None = None` 参数，写入 `pipeline_trace.json`
  - [x] 3.2 新增 `save_ground_truth(case_id, ground_truth)` 函数，写入 `ground_truth.json`，更新 manifest
  - [x] 3.3 新增 `save_diagnosis(case_id, diagnosis)` 函数，写入 `diagnosis.json`，更新 manifest
  - [x] 3.4 `load_case()` 扩展：读取 pipeline_trace / ground_truth / diagnosis
  - [x] 3.5 扩展 `tests/test_case_collector.py`：覆盖新增存储和读取

- [x] Task 4: Ground Truth Chunk 查找引擎 (`src/ground_truth_finder.py`)
  - [x] 4.1 实现 `find_chunks_by_source_page(source_pdf, page_number, chunks_dir)`：从 JSONL 文件按 metadata.source + metadata.page_numbers 查找
  - [x] 4.2 实现模糊匹配回退：页码范围匹配
  - [x] 4.3 编写 `tests/test_ground_truth_finder.py`

- [x] Task 5: 检索质量分析器 (`src/retrieval_analyzer.py`)
  - [x] 5.1 实现 `compute_ground_truth_metrics(trace, ground_truth_chunk_ids)`：计算 found_in_retrieval / retrieval_rank / retrieval_score / found_in_rerank / rerank_rank / rerank_score / found_in_context / context_dropped
  - [x] 5.2 编写 `tests/test_retrieval_analyzer.py`

- [x] Task 6: 根因诊断引擎 (`src/case_diagnoser.py`)
  - [x] 6.1 实现 `diagnose(trace, ground_truth, metrics)` 函数：RC-0~RC-5 分类逻辑
  - [x] 6.2 为每类根因实现 severity / finding / fix_suggestion / config_patch 生成
  - [x] 6.3 编写 `tests/test_case_diagnoser.py`：6 类根因 + 边界情况

- [x] Task 7: Streamlit 分析页面 (`src/app_pages/case_analyzer.py`)
  - [x] 7.1 Case 列表视图：展示 bad case 列表（时间倒序、问题预览、诊断状态、根因标签）
  - [x] 7.2 管线链路总览：5 阶段流水线图（HTML/CSS），颜色编码
  - [x] 7.3 逐阶段展开视图：检索（chunk 文本/分数/来源/页码）、重排序（排序变化/分数对比）、生成（完整 prompt/回复）
  - [x] 7.4 Ground Truth 标注界面：PDF 下拉 + 页码输入 + 答案输入 + chunk 查找 + 确认保存
  - [x] 7.5 诊断报告视图：根因标签 + 严重程度 + 发现描述 + 修复建议 + 配置补丁
  - [x] 7.6 遵循 streamlit-api-migration 规则：使用 `st.html()` 替代 `st.components.v1.html()`

- [x] Task 8: 集成深度分析入口
  - [x] 8.1 修改 `src/app.py`：新增 "🔍 Bad Case 分析" Tab
  - [x] 8.2 修改 `qa_demo.py`：查询时 `capture_trace=True`，trace 存入 session_state.messages
  - [x] 8.3 修改 `_do_save_case()`：保存时附带 trace 数据
  - [x] 8.4 标记 Bad Case 后弹出 toast："已保存，可到「🔍 Bad Case 分析」标签页进行深度分析"

# Task Dependencies

- Task 2 depends on Task 1 (Trace 数据模型)
- Task 3 depends on Task 1 (Trace/GroundTruth/DiagnosisResult 模型)
- Task 5 depends on Task 1 (PipelineTrace 模型)
- Task 6 depends on Task 1 + Task 5 (DiagnosisResult 模型 + metrics)
- Task 7 depends on Task 1 + Task 3 + Task 4 + Task 5 + Task 6 (所有后端模块)
- Task 8 depends on Task 2 + Task 3 + Task 7 (pipeline 改造 + 存储 + UI)
