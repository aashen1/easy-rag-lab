# 评测系统合并后清洗计划

> 调查日期: 2026-04-21
> 涉及分支: `fix-eval` + `add-ragas` -> `dev`

---

## 一、项目现状总评

### 1.1 整体架构

两个分支合并后，项目形成了**"双轨评测"架构**：

```
┌─────────────────────────────────────────────────────────────┐
│                     实验执行层 (run_experiment.py)            │
├─────────────────────────────────────────────────────────────┤
│  样本收集 (_collect_rag_samples)                              │
│       ↓                                                      │
│  评测分发 (evaluate_test_set)                                 │
│       ↓                                                      │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐   │
│  │ Builtin后端   │    │ RAGAS后端     │    │ Legacy直接   │   │
│  │ (原有系统)    │    │ (新增框架)    │    │ (兼容旧路)   │   │
│  └──────────────┘    └──────────────┘    └──────────────┘   │
│       ↓                      ↓                               │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              聚合指标 (compute_aggregate_metrics)       │   │
│  └──────────────────────────────────────────────────────┘   │
│       ↓                                                      │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              实验报告 (ExperimentReporter)               │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### 1.2 各系统当前状态

| 维度 | 原有评测系统 (fix-eval) | RAGAS系统 (add-ragas) |
|------|------------------------|----------------------|
| **指标覆盖** | 检索指标(HR/MRR/NDCG)、Chunk级、Dedup、FPR、Faithfulness、Answer Relevancy、Context Precision、Context Recall | Faithfulness、Answer Relevancy、Context Precision、Context Recall、Answer Correctness、Semantic Similarity |
| **架构** | 函数式直接调用 + 新Evaluator抽象层 | 面向对象Evaluator (BaseEvaluator子类) |
| **LLM调用** | Anthropic SDK直连 (api_key="dummy" + Bearer头) | LangChain Anthropic + LangchainLLMWrapper |
| **入口** | `eval/run_eval.py` (legacy)、`eval/run_experiment.py` (新) | 通过 `eval/run_experiment.py` 的 `_evaluate_with_ragas` |
| **配置** | `evaluation.backends: ["builtin"]` | `evaluation.backends: ["ragas"]` 或 `["builtin", "ragas"]` |
| **测试** | 有 `test_evaluators.py`、`test_metrics.py`、`test_run_experiment.py` | 仅有 `test_evaluators.py` 中的基础测试 |

---

## 二、配合情况评估

### 2.1 已正确配合的部分 ✅

1. **双后端并行执行**: `evaluate_test_set()` 能正确分发到两个后端，结果合并逻辑正确
2. **指标去重**: builtin后端在双后端模式下会过滤掉RAGAS也支持的指标，避免重复计算
3. **统一结果格式**: `EvaluationResult` dataclass 统一了两个后端的输出
4. **配置验证**: `ExperimentConfig.validate()` 正确校验backend和metrics的兼容性
5. **RAGAS独占指标检测**: 若使用了RAGAS独占指标(answer_correctness/semantic_similarity)但未启用ragas backend，会报错

### 2.2 存在的问题 ⚠️

#### 问题1: **指标命名空间重叠但实现不同**

| 指标名 | builtin实现 | RAGAS实现 | 风险 |
|--------|------------|-----------|------|
| `faithfulness` | 自定义prompt提取statements后验证 | RAGAS自带prompt和逻辑 | 同一实验不同后端结果不可直接对比 |
| `answer_relevancy` | 自定义3维度评分(1-5分转0-1) | RAGAS反向生成问题+embedding相似度 | 计算方法完全不同 |
| `context_precision` | 自定义WCP公式 | RAGAS实现 | 可能结果不一致 |
| `context_recall` | 自定义句子拆分+推断判断 | RAGAS实现 | 可能结果不一致 |

**影响**: 用户若切换backend，指标数值波动可能让人困惑。

#### 问题2: **Legacy路径与新Evaluator抽象层并存**

- `eval/run_experiment.py` 中 `_evaluate_test_set_legacy()` 仍直接调用 `calculate_hit_rate` 等函数
- `eval/run_eval.py` 也直接调用这些函数
- 但 `BuiltinEvaluator` 已经包装了这些函数

**影响**: 代码重复，维护成本高。改指标逻辑需要改多处。

#### 问题3: **RAGAS配置与实际代码不一致**

文档 `docs/guides/ragas-evaluation.md` 提到 `config.yaml` 中应有：
```yaml
evaluation:
  ragas:
    enabled: true
    llm_backend: "anthropic"
    run_config:
      max_workers: 5
```

但代码中 `RagasEvaluator.__init__()` 只接收 `config`，从未读取 `evaluation.ragas` 下的任何配置项。`max_workers`、`timeout`、`max_retries` 等参数完全未使用。

#### 问题4: **RAGAS缺少chunk级指标集成**

原有系统新增了chunk_hit_rate、chunk_mrr、chunk_ndcg等细粒度指标，但RAGAS evaluator完全不支持这些。双后端模式下RAGAS结果中没有chunk级信息。

#### 问题5: **TestSetManager与RAGAS实验配置格式冲突**

RAGAS的示例配置 `ragas_only.yaml` 和 `ragas_builtin.yaml` 使用的是**旧格式** test_sets（无name字段）：
```yaml
test_sets:
  - strategy: "document"
    num_questions: 20
```

而fix-eval分支主推的**新格式**是：
```yaml
test_sets:
  - name: "golden_test"
    on_missing: "auto"
    generation:
      strategy: "document"
      num_questions: 20
```

虽然旧格式有兼容处理，但RAGAS配置示例没有展示新格式的最佳实践。

#### 问题6: **run_eval.py 与 run_experiment.py 功能重叠**

`eval/run_eval.py` 是旧的独立评测脚本，`eval/run_experiment.py` 是新的实验系统。两者都能跑评测，但：
- `run_eval.py` 不支持backend配置
- `run_eval.py` 不支持RAGAS
- `run_eval.py` 的输出格式与experiment系统不一致

#### 问题7: **metrics.py 过于庞大 (1334行)**

包含：
- 检索指标 (hit_rate, mrr, ndcg)
- chunk级指标
- dedup指标
- FPR
- Faithfulness (含LLM调用)
- Answer Relevancy (含LLM调用)
- Context Precision (含LLM调用)
- Context Recall (含LLM调用)
- 各种工具函数

这是一个明显的"上帝模块"。

#### 问题8: **LLM客户端创建重复**

`metrics.py` 中 `_create_llm_client()` 与 `ragas_evaluator.py` 中 `_create_llm()` 都处理了 `api_key="dummy" + Bearer` 的LongCat适配逻辑，但实现方式不同（一个直接用Anthropic SDK，一个用LangChain）。

#### 问题9: **RAGAS依赖导入错误提示建议用pip**

`ragas_evaluator.py` 的ImportError提示：
```python
raise ImportError(f"{error_msg}. Please install with: pixi add langchain-anthropic ragas")
```

但用户规则禁止运行pip，这里应该提示用pixi（实际已经用了pixi，但ragas本身已在pixi.toml中，这个提示是多余的）。

#### 问题10: **文档中RAGAS配置节在config.yaml中不存在**

`docs/guides/ragas-evaluation.md` 详细描述了 `config.yaml` 中的 `evaluation.ragas` 配置，但实际的 `config.yaml` 中完全没有这个节。

---

## 三、清洗工作项

### 🔴 高优先级（影响正确性/一致性）

#### CLEAN-001: 统一指标命名，区分builtin与ragas同名指标

**问题**: faithfulness、answer_relevancy等同名指标在不同后端计算方式不同，但结果存在同一个key下。

**方案**: 
- 在结果中增加命名空间前缀，如 `ragas_faithfulness` vs `builtin_faithfulness`
- 或在ExperimentReporter中明确标注来源

**涉及文件**: `eval/run_experiment.py`、 `eval/evaluators/*.py`

#### CLEAN-002: 修复RAGAS配置与实际代码不一致

**问题**: 文档描述了一套config.yaml配置，但代码完全不读这些配置。

**方案**:
- 方案A: 删除文档中的虚假配置描述，改为纯代码内配置
- 方案B: 让RagasEvaluator实际读取config中的evaluation.ragas配置

**建议**: 采用方案B，将embedding模型、max_tokens、temperature等参数从硬编码改为读取配置。

**涉及文件**: `eval/evaluators/ragas_evaluator.py`, `config.yaml`, `docs/guides/ragas-evaluation.md`

#### CLEAN-003: 将RAGAS示例配置更新为新格式

**问题**: `exp_configs/ragas_evaluation/*.yaml` 使用旧格式test_sets。

**方案**: 更新为new format，添加name和on_missing字段。

**涉及文件**: `exp_configs/ragas_evaluation/*.yaml`

### 🟡 中优先级（架构/代码质量）

#### CLEAN-004: 提取LLM客户端创建为统一工具函数

**问题**: `_create_llm_client()` 和 `_create_llm()` 重复实现LongCat适配。

**方案**: 在 `src/utils.py` 中创建统一工厂函数，支持两种模式（直接SDK / LangChain）。

**涉及文件**: `src/utils.py`, `eval/metrics.py`, `eval/evaluators/ragas_evaluator.py`

#### CLEAN-005: 拆分metrics.py为子模块

**问题**: 1334行的上帝模块。

**方案**: 按指标类型拆分：
```
eval/metrics/
  __init__.py          # 统一导出
  retrieval.py         # hit_rate, mrr, ndcg
  chunk.py             # chunk_hit_rate, chunk_mrr, chunk_ndcg
  dedup.py             # dedup_*
  fpr.py               # false_positive_rate
  generation.py        # faithfulness, answer_relevancy
  llm_retrieval.py     # context_precision, context_recall
  utils.py             # normalize_source, _create_llm_client等
```

**涉及文件**: `eval/metrics.py` -> `eval/metrics/*.py`

#### CLEAN-006: 统一Legacy路径到Evaluator抽象层

**问题**: `_evaluate_test_set_legacy()` 和 `run_eval.py` 直接调用metric函数。

**方案**: 
- `run_eval.py` 改造为使用BuiltinEvaluator
- `_evaluate_test_set_legacy()` 改为委托给BuiltinEvaluator
- 保留legacy函数但标记为deprecated

**涉及文件**: `eval/run_experiment.py`, `eval/run_eval.py`

#### CLEAN-007: 让RAGAS Evaluator支持chunk级指标

**问题**: RAGAS后端的结果中缺少chunk_retrieval、dedup_retrieval、false_positive_rate。

**方案**: 在 `RagasEvaluator.evaluate_single/batch` 中，若样本包含chunk_ids，则调用builtin的chunk/dedup/fpr计算函数，将结果合并到retrieval_metrics中。

**涉及文件**: `eval/evaluators/ragas_evaluator.py`

### 🟢 低优先级（文档/配置/测试）

#### CLEAN-008: 补充RAGAS集成测试

**问题**: `test_evaluators.py` 中只有RagasEvaluator的基础单元测试，没有集成测试。

**方案**: 在 `test_run_experiment.py` 或新建 `test_ragas_integration.py` 中测试：
- 双backend并行执行
- 结果合并逻辑
- RAGAS独占指标验证

**涉及文件**: `tests/test_evaluators.py`, `tests/test_run_experiment.py`

#### CLEAN-009: 删除/归档过时的独立run_eval.py

**问题**: `eval/run_eval.py` 功能已被 `run_experiment.py` 完全覆盖。

**方案**: 
- 评估是否有脚本或文档还引用run_eval.py
- 如无引用，删除或移到 `eval/legacy/`

**涉及文件**: `eval/run_eval.py`

#### CLEAN-010: 在config.yaml中添加evaluation.ragas配置节

**问题**: 文档描述了但config.yaml中不存在。

**方案**: 添加最小配置模板：
```yaml
evaluation:
  ragas:
    embedding_model: "BAAI/bge-large-zh-v1.5"
    device: "cuda"
```

**涉及文件**: `config.yaml`

---

## 四、执行顺序建议

```
Phase 1: 高优先级（正确性修复）
  ├── CLEAN-001: 统一指标命名空间
  ├── CLEAN-002: 修复RAGAS配置读取
  └── CLEAN-003: 更新RAGAS示例配置

Phase 2: 中优先级（架构重构）
  ├── CLEAN-004: 统一LLM客户端
  ├── CLEAN-005: 拆分metrics.py
  ├── CLEAN-006: 统一Legacy路径
  └── CLEAN-007: RAGAS支持chunk指标

Phase 3: 低优先级（完善补充）
  ├── CLEAN-008: 补充RAGAS集成测试
  ├── CLEAN-009: 归档run_eval.py
  └── CLEAN-010: 补充config.yaml模板
```

---

## 五、风险与注意事项

1. **metrics.py拆分**会影响所有import了该模块的文件，需要全局检查
2. **指标命名空间变更**会影响历史实验结果的对比，需要评估是否向后兼容
3. **RAGAS配置读取变更**不应破坏现有无配置的使用方式（保持默认值fallback）
4. **run_eval.py删除**前必须确认没有任何地方引用它

---

## 六、当前backlog关联

| 清洗项 | 关联backlog项 | 说明 |
|--------|--------------|------|
| CLEAN-004 | RF-005 | Anthropic客户端创建统一抽象 |
| CLEAN-005 | RF-002 | 项目结构整理 |
| CLEAN-006 | RF-001 | CLI输出规范化（相关） |
| CLEAN-002 | RF-004 | 硬编码配置值提取到config.yaml |
