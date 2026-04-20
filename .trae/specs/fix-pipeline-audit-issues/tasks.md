# Tasks

- [x] Task 1: 修复 P6-3 致命 Bug — contexts/sources 参数混淆
  - [x] Task 1.1: 修改 `BuiltinEvaluator.evaluate_single()` 接口，新增 `retrieved_sources` 参数
  - [x] Task 1.2: 修改 `_collect_rag_samples()` 收集 `chunk_ids` 和 `question_type`
  - [x] Task 1.3: 修改 `_evaluate_with_builtin()` 正确传递 `contexts`（文本）和 `retrieved_sources`（路径）
  - [x] Task 1.4: 更新 `evaluate_batch()` 传递 `retrieved_sources`
  - [x] Task 1.5: 编写/更新测试验证修复

- [x] Task 2: 修复 P4-1 — BGE 查询指令前缀
  - [x] Task 2.1: 修改 `Embedder.__init__()` 检测 BGE 模型并设置默认指令前缀
  - [x] Task 2.2: 修改 `embed_query()` 在向量化前添加指令前缀
  - [x] Task 2.3: 在 `config.yaml` 的 `embedding` 节添加 `query_instruction` 配置项
  - [x] Task 2.4: 编写测试验证指令前缀行为

- [x] Task 3: 修复 P5-1 — System Prompt 可配置化
  - [x] Task 3.1: 在 `config.yaml` 新增 `generation` 节及 `system_prompt` 配置项
  - [x] Task 3.2: 修改 `Generator.__init__()` 接收 `system_prompt` 参数
  - [x] Task 3.3: 修改 `RAGPipeline.__init__()` 从配置读取 system_prompt 传给 Generator
  - [x] Task 3.4: 确保实验配置的 `config_overrides` 可覆盖 system_prompt
  - [x] Task 3.5: 编写测试验证配置化行为

- [x] Task 4: 修复 P5-4 — Prompt 包含来源文档名
  - [x] Task 4.1: 修改 `Generator.generate()` 新增 `sources` 参数
  - [x] Task 4.2: 修改 context 格式化逻辑，包含来源文档名
  - [x] Task 4.3: 修改 `RAGPipeline.query()` 传递 `sources` 给 Generator
  - [x] Task 4.4: 编写测试验证 Prompt 格式

- [x] Task 5: 修复 P4-2 — 检索分数阈值过滤
  - [x] Task 5.1: 在 `config.yaml` 的 `retrieval` 节添加 `score_threshold` 配置项（默认 0）
  - [x] Task 5.2: 修改 `Retriever.__init__()` 接收 `score_threshold` 参数
  - [x] Task 5.3: 修改 `Retriever.retrieve()` 在返回结果前过滤低分结果
  - [x] Task 5.4: 修改 `RAGPipeline._setup_retrievers()` 传递 score_threshold
  - [x] Task 5.5: 编写测试验证过滤行为

- [x] Task 6: 将复杂问题维护到 backlog.md
  - [x] Task 6.1: 检查已有 backlog 避免重复
  - [x] Task 6.2: 添加 P2-1（评测链路修复后考虑非零 overlap）→ OPT-005
  - [x] Task 6.3: 添加 P3-1（512 token截断冲突）→ INV-012
  - [x] Task 6.4: 添加 P5-3（无Context长度控制）→ FEAT-019
  - [x] Task 6.5: 添加 P1-1（表格解析质量）→ INV-013
  - [x] Task 6.6: 添加 P1-3（页眉页脚污染）→ FEAT-020
  - [x] Task 6.7: 添加 P2-3（chunk_id命名脆弱）→ RF-011
  - [x] Task 6.8: 添加 P6-4（检索无文档级去重-检索器层面）→ FEAT-021
  - [x] Task 6.9: 添加 P6-5（expected_sources标注错误）→ BUG-017
  - [x] Task 6.10: 添加 P6-1（normalize_source过于宽松）→ RF-012
  - [x] Task 6.11: 更新 `docs/pipeline-deep-audit.md` 标注已修复和已入库的问题

# Task Dependencies

- Task 1 (P6-3) 是独立任务，无依赖，但优先级最高
- Task 4 (P5-4) 依赖 Task 3 (P5-1) 因为都涉及 Generator 修改，建议先完成 Task 3 再做 Task 4
- Task 2, 5 互相独立，可并行
- Task 6 在所有修复完成后执行
