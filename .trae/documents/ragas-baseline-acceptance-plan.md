# RAGAS 基线验收实验计划

## 验收目标

获得一份结论可信的、完整带有 RAGAS 五大主要指标的实验报告，充分评估一条 RAG 基线的效果。

**RAGAS 五大指标**：faithfulness、answer_relevancy、context_precision、context_recall、answer_correctness

---

## 当前就绪状态评估

### ✅ 已就绪

| 项目 | 状态 | 说明 |
|------|------|------|
| 原始数据 | ✅ | `data/raw/` 含年报+研报 PDF |
| 解析数据 | ✅ | `data/parsed/` 含对应 .md 文件 |
| 分块数据 | ✅ | `data/chunks/` 含对应 .jsonl 文件 |
| 向量索引 | ✅ | `data/vector_store/` 含 Qdrant 索引（含 `financial_reports` 默认集合） |
| RAGAS 评测器代码 | ✅ | `eval/evaluators/ragas_evaluator.py` 已实现 |
| RAGAS 实验配置 | ✅ | `exp_configs/ragas_evaluation/` 含 3 个配置文件 |
| 测试集生成系统 | ✅ | TestSetManager + document 策略已实现 |
| `expected_answer` 字段 | ✅ | 自动生成的测试集含 `answer` 字段，`_collect_rag_samples()` 会将其映射为 `expected_answer` |

### ⚠️ 需要确认/准备

| 项目 | 风险 | 说明 |
|------|------|------|
| API Key 配置 | 🔴 关键 | `.env` 中 `LLM_API_KEY` 必须有效，RAGAS 评测需要 LLM 调用 |
| RAGAS 依赖安装 | 🟡 中等 | 需确认 `ragas`、`langchain-anthropic`、`langchain-community`、`sentence-transformers` 已在 pixi 环境中安装 |
| CUDA 设备 | 🟡 中等 | `config.yaml` 中 `embedding.device: "cuda"`，如无 GPU 需改为 `"cpu"` |
| 测试集规模 | 🟡 中等 | `ragas_only.yaml` 仅 20 题，对于"结论可信"的报告可能偏少 |

---

## Ground Truth（参考答案）策略

### RAGAS 五大指标对 ground_truth 的依赖

| 指标 | 需要 ground_truth？ | 说明 |
|------|---------------------|------|
| faithfulness | ❌ 不需要 | 仅评估回答是否忠实于检索上下文 |
| answer_relevancy | ❌ 不需要 | 仅评估回答与问题的相关性 |
| context_precision | ✅ 需要 | 评估检索上下文中有用信息的比例 |
| context_recall | ✅ 需要 | 评估 ground_truth 中的信息是否被检索到 |
| answer_correctness | ✅ 需要 | 评估回答与 ground_truth 的一致性 |

### 当前 ground_truth 来源

自动生成的测试集中每个问题都有 `answer` 字段（由 LLM 基于源文档生成），评测时 `_collect_rag_samples()` 将其映射为 `expected_answer` 传入 RAGAS。

**自动生成 answer 的质量评估**：
- ✅ 基于源文档生成，内容有据可依
- ⚠️ LLM 可能产生幻觉或遗漏，不如人工标注精确
- ⚠️ 对 context_precision/context_recall/answer_correctness 三个需要 reference 的指标，ground_truth 质量直接影响指标可信度

### 两步走策略

1. **第一步：先用自动生成的 answer 跑一轮实验**——不需要用户额外工作。如果结果合理（指标值在预期范围内），说明自动 ground_truth 质量可接受
2. **第二步：如对结果有疑虑，再对关键问题做人工校验**——用户只需审查和修正部分问题的 answer，不需要全部重做。修正后重新运行评测即可

---

## 实验方案

### 方案选择：使用 `ragas_only.yaml` 配置

该配置覆盖 RAGAS 五大指标（faithfulness + answer_relevancy + context_precision + context_recall + answer_correctness），是最直接的验收路径。

**配置要点**：
- Meal: `meal_ragas`（自动创建，sample_ratio=0.1）
- 测试集: `ragas_only_test`（自动生成，20 题）
- 变体: `baseline_ragas`（无 config_overrides，使用 config.yaml 基线）
- 后端: `["ragas"]`
- 指标: retrieval=[context_precision, context_recall], generation=[faithfulness, answer_relevancy, answer_correctness]

### 实验步骤

#### Step 1: 环境预检（只读操作）

1. 确认 pixi 环境中 RAGAS 相关依赖已安装
   ```bash
   pixi run python -c "import ragas; print(ragas.__version__)"
   pixi run python -c "from langchain_anthropic import ChatAnthropic; print('OK')"
   pixi run python -c "from langchain_community.embeddings import HuggingFaceEmbeddings; print('OK')"
   ```
2. 确认 API Key 可用（不读取 .env，通过运行时测试）
   ```bash
   pixi run python -c "from src.utils import create_llm_client; c = create_llm_client(mode='anthropic'); print('API OK')"
   ```
3. 确认 CUDA/CPU 设备设置
   ```bash
   pixi run python -c "import torch; print('CUDA available:', torch.cuda.is_available())"
   ```

#### Step 2: 冒烟测试（1 题，验证端到端流程）

```bash
pixi run python eval/run_experiment.py --config exp_configs/ragas_evaluation/ragas_quick.yaml
```

- 仅 1 题的快速验证，确认 RAGAS 评测流程可正常运行
- 如果失败，根据错误信息排查

#### Step 3: 正式实验（20 题，RAGAS 五大指标）

```bash
pixi run python eval/run_experiment.py --config exp_configs/ragas_evaluation/ragas_only.yaml
```

- 自动创建 Meal、生成测试集、构建索引、运行评测
- 预计耗时：20 题 × (RAG查询 + RAGAS评测) ≈ 15-30 分钟

#### Step 4: 验收报告审查

1. 检查实验报告输出目录 `data/exp_reports/`
2. 确认五大指标均有数值结果
3. 检查是否有 NaN 或异常值
4. 评估指标可信度：
   - faithfulness: 回答是否忠实于检索上下文
   - answer_relevancy: 回答与问题的相关性
   - context_precision: 检索上下文的精确度
   - context_recall: 检索上下文的召回度
   - answer_correctness: 回答与参考答案的一致性

#### Step 5: 如需增强可信度（可选）

如果 20 题的结果不够可信，可考虑：
- 增加测试题数（修改 `num_questions` 为 35-50）
- 使用双后端对比（`ragas_builtin.yaml`），同时获得 builtin 指标作为交叉验证

---

## 潜在问题与应对

| 问题 | 应对 |
|------|------|
| RAGAS 依赖未安装 | `pixi add ragas langchain-anthropic langchain-community sentence-transformers`（需用户确认） |
| API Key 无效 | 用户需更新 `.env` 中的 `LLM_API_KEY` |
| CUDA 不可用 | 修改 `config.yaml` 中 `embedding.device` 为 `"cpu"` |
| RAGAS 评测超时 | 调整 `config.yaml` 中 `ragas.run_config.timeout` 和 `max_retries` |
| context_precision/context_recall 返回 NaN | 检查 `expected_answer` 是否正确传入 |
| LongCat API 兼容性问题 | RagasEvaluator 已使用 LangchainLLMWrapper + ChatAnthropic 方案兼容 |

---

## 结论

**在确认 API Key 有效和 RAGAS 依赖已安装的前提下，可以直接开始实验。** 建议按 Step 1 → Step 2 → Step 3 的顺序执行，先用冒烟测试验证链路，再运行正式实验。
