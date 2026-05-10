# Checklist

## P6-3: contexts/sources 参数混淆修复

- [x] `BuiltinEvaluator.evaluate_single()` 新增 `retrieved_sources` 参数，检索指标使用 `retrieved_sources`，生成指标使用 `contexts`
- [x] `_collect_rag_samples()` 收集 `chunk_ids` 和 `question_type` 字段
- [x] `_evaluate_with_builtin()` 正确传递 `contexts=sample["contexts"]` 和 `retrieved_sources=sample["retrieved_sources"]`
- [x] `evaluate_batch()` 传递 `retrieved_sources` 参数
- [x] 向后兼容：仅提供 `contexts` 时检索指标仍使用 `contexts`
- [x] Faithfulness 评估收到的是文本内容而非文件路径
- [x] 相关测试通过

## P4-1: BGE 查询指令前缀

- [x] `embed_query()` 对 BGE 模型自动添加指令前缀
- [x] `embed_texts()` 不添加指令前缀
- [x] `config.yaml` 的 `embedding.query_instruction` 可配置
- [x] 非 BGE 模型不添加前缀
- [x] 相关测试通过

## P5-1: System Prompt 可配置化

- [x] `config.yaml` 新增 `generation` 节及 `system_prompt` 配置项
- [x] `Generator.__init__()` 接收 `system_prompt` 参数
- [x] 配置为空时使用默认硬编码 prompt
- [x] 实验配置的 `config_overrides` 可覆盖 system_prompt
- [x] 相关测试通过

## P5-4: Prompt 包含来源文档名

- [x] `Generator.generate()` 新增 `sources` 参数
- [x] 参考资料格式包含来源文档名：`参考资料 N（来源：{source_name}）:\n{text}`
- [x] `RAGPipeline.query()` 传递 `sources` 给 Generator
- [x] 不提供 `sources` 时保持旧格式（向后兼容）
- [x] 相关测试通过

## P4-2: 检索分数阈值过滤

- [x] `config.yaml` 新增 `retrieval.score_threshold` 配置项（默认 0）
- [x] `Retriever` 支持分数阈值过滤
- [x] 阈值为 0 时不进行过滤
- [x] 过滤后结果不足 top_k 时返回全部过滤后结果
- [x] 相关测试通过

## Backlog 维护

- [x] 复杂问题已入库 backlog.md，无重复
- [x] `docs/pipeline-deep-audit.md` 已更新标注修复状态
