# RAGAS 集成计划

## 调研总结

### 当前评测系统现状

| 维度 | 现状 |
|------|------|
| **检索指标** | `hit_rate`, `mrr`, `ndcg`（自实现，纯计算） |
| **生成指标** | `faithfulness`, `answer_relevancy`（自实现，LLM-as-Judge） |
| **LLM 后端** | Anthropic SDK 直连 LongCat API |
| **评测模式** | 逐条串行调用 |
| **数据格式** | `id`, `question`, `source_files`, `expected_answer`（无 ground_truth、无 contexts 存储） |
| **RAGAS 依赖** | `pixi.toml` 已声明 `ragas>=0.4.3,<0.5`，但代码中未使用 |

### RAGAS 框架能力

| 指标 | 所需输入 | 说明 |
|------|---------|------|
| **Faithfulness** | question, answer, contexts | 回答是否基于上下文（与现有指标对齐） |
| **AnswerRelevancy** | question, answer | 回答与问题的相关性（与现有指标对齐） |
| **ContextPrecision** | question, contexts, reference | 检索结果排序质量（**新增**） |
| **ContextRecall** | question, contexts, reference | 检索结果覆盖度（**新增**） |
| **FactualCorrectness** | response, reference | 事实正确性（**新增**） |
| **SemanticSimilarity** | response, reference | 语义相似度（**新增**） |

### 关键挑战与对策

| 挑战 | 对策 |
|------|------|
| **LLM 后端适配**：RAGAS 需要 LangChain LLM，项目用 Anthropic SDK | 使用 `ChatOpenAI` 配置 OpenAI 兼容端点连接 LongCat API，或使用 `langchain-anthropic` |
| **缺少 ground_truth**：现有测试数据大多无标准答案 | 测试数据中 `expected_answer` 可作为 `reference`；自动生成的测试集需补充 ground_truth 字段 |
| **contexts 数据**：RAGAS 需要 contexts 列表，当前在评测时才获取 | 评测流程中 pipeline.query() 已返回 contexts，直接传入 RAGAS |
| **中文 Prompt**：RAGAS 默认英文评估 prompt | RAGAS 0.4.x 的 LLM 对中文有理解能力，先验证效果，必要时自定义 prompt |
| **evaluate() 已弃用**：RAGAS 0.4.x 推荐用 `@experiment` | 仍支持 `evaluate()` 函数，且更简单；后续可迁移到新 API |

---

## 实施步骤

### Step 1: 新增 RAGAS 适配层 — `eval/ragas_adapter.py`

创建 RAGAS 适配模块，封装 LLM/Embeddings 配置和数据转换逻辑：

1. **LLM 适配器** `create_ragas_llm()`：
   - 接收项目的 `llm_config`（含 api_key, base_url, model_name）
   - 使用 `ChatOpenAI(base_url=..., api_key=..., model=...)` 创建 LangChain LLM
   - 用 `LangchainLLMWrapper` 包装为 RAGAS 兼容的 LLM
   - 支持通过配置选择 `langchain-openai` 或 `langchain-anthropic`

2. **Embeddings 适配器** `create_ragas_embeddings()`：
   - 使用项目现有的 BGE 模型或 OpenAI 兼容的 Embeddings API
   - 用 `LangchainEmbeddingsWrapper` 包装

3. **数据转换器** `build_ragas_dataset()`：
   - 输入：评测结果列表（含 question, answer, contexts, expected_answer/source_files）
   - 输出：`EvaluationDataset` 或 `Dataset`（HuggingFace）
   - 字段映射：`expected_answer` → `reference`，`contexts` 保持为列表

4. **指标工厂** `create_ragas_metrics()`：
   - 根据配置的指标名称列表，创建对应的 RAGAS 指标实例
   - 支持的指标：`faithfulness`, `answer_relevancy`, `context_precision`, `context_recall`, `factual_correctness`, `semantic_similarity`
   - 每个指标注入 LLM/Embeddings

### Step 2: 扩展配置系统

1. **`src/experiment.py`**：
   - 扩展 `VALID_GENERATION_METRICS`，新增 RAGAS 指标名：
     ```python
     VALID_GENERATION_METRICS = {
         "faithfulness", "answer_relevancy",
         "context_precision", "context_recall",
         "factual_correctness", "semantic_similarity",
     }
     ```
   - 新增 `VALID_RAGAS_METRICS` 常量区分 RAGAS 特有指标
   - `ExperimentConfig.validate()` 中增加对 RAGAS 指标的验证

2. **`config.yaml`**：
   - 在 `evaluation` 段下新增 `ragas` 配置：
     ```yaml
     evaluation:
       ragas:
         enabled: true
         llm_backend: "openai_compatible"  # 或 "anthropic"
         embeddings_backend: "local"       # 使用本地 BGE 或 "openai"
         run_config:
           max_workers: 5
           timeout: 60
           max_retries: 3
     ```

3. **实验配置 YAML**：
   - `evaluation.metrics.generation` 中可直接使用 RAGAS 指标名：
     ```yaml
     evaluation:
       metrics:
         generation:
           - "faithfulness"
           - "answer_relevancy"
           - "context_precision"
           - "context_recall"
     ```

### Step 3: 集成到评测流程

1. **`eval/run_eval.py`**：
   - 在 `run_evaluation()` 中，当检测到 RAGAS 指标时，走 RAGAS 评测路径
   - 流程：
     a. 逐条调用 `pipeline.query()` 获取 answer + contexts
     b. 收集所有评测数据（question, answer, contexts, reference）
     c. 构建 `EvaluationDataset`
     d. 调用 `ragas.evaluate()` 批量计算 RAGAS 指标
     e. 将结果合并到现有报告格式中
   - 保留原有自实现指标的并行计算能力（检索指标仍用自实现）

2. **`eval/run_experiment.py`**：
   - `evaluate_test_set()` 中增加 RAGAS 指标计算
   - `compute_aggregate_metrics()` 扩展以包含 RAGAS 指标
   - `run_variant_evaluation()` 中传递 RAGAS 配置

3. **混合评测模式**：
   - 检索指标（hit_rate, mrr, ndcg）→ 继续使用自实现（RAGAS 不提供这些）
   - 生成指标 → 根据配置选择自实现或 RAGAS
   - 支持同时运行两套指标进行对比

### Step 4: 测试数据 ground_truth 增强

1. **`src/test_generator.py`**：
   - 自动生成的测试集中，已有 `expected_answer` 字段
   - 将 `expected_answer` 映射为 RAGAS 的 `reference` 字段
   - 对于 `document` 策略生成的问题，确保 `expected_answer` 质量足够作为 reference

2. **手工标注数据**：
   - `eval/test_data.json` 中已有 `expected_answer`，可直接使用

### Step 5: 报告系统扩展

1. **`eval/experiment_reporter.py`**：
   - 报告模板增加 RAGAS 指标列
   - 支持 Context Precision、Context Recall 等新指标的展示
   - 对比报告中增加 RAGAS 指标对比行

2. **输出格式**：
   - `baseline_report.json` 中 `generation_metrics` 增加 RAGAS 指标
   - 实验结果 JSON 中增加 `ragas_metrics` 段

### Step 6: 依赖安装

1. **`pixi.toml`**：
   - 新增 `langchain-openai` 依赖（用于 OpenAI 兼容端点连接 LongCat API）
   - 确认 `ragas>=0.4.3,<0.5` 已存在
   - 可选：`langchain-anthropic`（如果需要 Anthropic 原生 SDK 集成）

### Step 7: 测试

1. **`tests/test_ragas_adapter.py`**（新建）：
   - 测试 LLM 适配器创建
   - 测试 Embeddings 适配器创建
   - 测试数据转换（项目格式 → RAGAS EvaluationDataset）
   - 测试指标工厂（根据配置创建正确的指标实例）
   - 使用 mock 测试 `ragas.evaluate()` 调用

2. **`tests/test_metrics.py`**（扩展）：
   - 增加 RAGAS 指标名称验证测试
   - 增加 `VALID_GENERATION_METRICS` 扩展验证

3. **`tests/test_run_eval.py`**（扩展）：
   - 测试 RAGAS 指标配置的加载和传递
   - 测试混合评测模式（自实现 + RAGAS）

---

## 文件变更清单

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `eval/ragas_adapter.py` | **新建** | RAGAS 适配层（LLM/Embeddings/数据转换/指标工厂） |
| `eval/metrics.py` | 修改 | 新增 RAGAS 指标名称常量 |
| `eval/run_eval.py` | 修改 | 集成 RAGAS 评测路径 |
| `eval/run_experiment.py` | 修改 | 集成 RAGAS 到实验流程 |
| `eval/experiment_reporter.py` | 修改 | 报告增加 RAGAS 指标展示 |
| `src/experiment.py` | 修改 | 扩展 VALID_GENERATION_METRICS，增加验证 |
| `config.yaml` | 修改 | 新增 ragas 配置段 |
| `pixi.toml` | 修改 | 新增 langchain-openai 依赖 |
| `tests/test_ragas_adapter.py` | **新建** | RAGAS 适配层测试 |
| `tests/test_metrics.py` | 修改 | 扩展指标验证测试 |
| `tests/test_run_eval.py` | 修改 | 扩展评测流程测试 |

---

## 设计原则

1. **渐进式集成**：RAGAS 作为可选评测后端，不替换现有自实现指标
2. **配置驱动**：所有 RAGAS 相关参数通过 config.yaml 和实验配置控制
3. **向后兼容**：现有评测流程和结果格式不受影响
4. **混合评测**：检索指标继续用自实现，生成指标可选 RAGAS
5. **LLM 复用**：RAGAS 评估 LLM 复用项目已有的 LLM 预设配置
