# 技术栈分析与 RAGAS 集成难度评估

> 创建时间: 2026-04-20

## 一、当前技术栈全景

### 1. 核心依赖（pixi.toml 声明）

| 类别 | 依赖 | 版本 | 用途 |
|------|------|------|------|
| **Python** | python | 3.12 | 运行时 |
| **日志** | loguru | 0.7.x | 日志系统 |
| **配置** | pyyaml | 6.x | YAML 解析 |
| **LLM SDK** | anthropic | 0.95.x | Anthropic/LongCat API 调用 |
| **Embedding** | transformers | 5.5.x | HuggingFace BGE 模型 |
| **向量存储** | qdrant-client | 1.17.x | Qdrant 向量数据库 |
| **RAG 框架** | llama-index-core | 0.14.x | RAG 核心组件 |
| **文档处理** | pymupdf4llm | 1.27.x | PDF 解析 |
| **评测** | ragas | **0.4.x（已声明）** | RAG 评测框架 |
| **测试** | pytest | 9.x | 单元测试 |
| **分词** | jieba | 0.42.x | 中文分词（BM25） |
| **机器学习** | scikit-learn | 1.8.x | BM25 实现 |

### 2. 自研模块架构

```
src/
├── pipeline.py              # 主 RAG 流水线（522行）
├── parser.py                # PDF 解析器
├── chunker.py               # 固定长度分块器
├── semantic_chunker.py      # 语义分块器
├── embedder.py              # Embedding 模型封装
├── indexer.py               # 向量索引管理
├── retriever.py             # 向量检索器
├── bm25_retriever.py        # BM25 检索器
├── hybrid_retriever.py      # 混合检索器
├── reranker.py              # 交叉编码器重排
├── query_rewriter.py        # 查询改写（HyDE/Multi-Query）
├── generator.py             # LLM 答案生成
├── test_generator.py        # 测试集生成器
├── meal.py                  # 数据集管理系统
├── experiment.py            # 实验管理系统
└── token_tracker.py         # Token 成本追踪

eval/
├── run_eval.py              # 评测运行器（525行）
├── metrics.py               # 自定义评测指标（622行）
├── experiment_reporter.py   # 实验报告生成
└── visualize.py             # 结果可视化
```

### 3. 评测系统现状

**已实现的评测指标：**
- ✅ 检索质量：Hit Rate, MRR, NDCG（纯数学计算）
- ✅ 生成质量：Faithfulness（自研 LLM-based 实现）
- ✅ 生成质量：Answer Relevancy（自研 LLM-based 实现）

**评测数据格式：**
- 测试集：`eval/test_data.json` 或 Meal 下的 `test_sets/`
- 包含字段：`id`, `question`, `category`, `expected_sources`, `expected_answer`

**评测流程：**
1. `RAGPipeline.query()` → 获取 answer + contexts + sources
2. 计算检索指标：Hit Rate / MRR / NDCG
3. 计算生成指标：Faithfulness / Answer Relevancy（调用 LLM）
4. 汇总统计 → JSON 报告 + 可视化

---

## 二、RAGAS 集成难度分析

### 1. 有利因素（降低难度）

#### ✅ 依赖已声明
- `pixi.toml` 中已有 `ragas = ">=0.4.3, <0.5"`
- 理论上 `pixi install` 即可安装

#### ✅ 评测流程架构相似
RAGAS 的标准输入格式：
```python
Dataset({
    "question": [...],
    "answer": [...],
    "contexts": [...],  # List[List[str]]
    "ground_truth": [...]  # 可选
})
```

与现有 `run_eval.py` 的数据流完全一致：
- 现有：`test_data.json` → pipeline.query() → answer/contexts/sources
- RAGAS：同样的数据 → `ragas.evaluate()`

#### ✅ 指标重合度高
项目已实现的指标恰好是 RAGAS 的核心指标：
- Faithfulness
- Answer Relevancy
- （可扩展）Context Precision, Context Recall, etc.

#### ✅ 基于 LlamaIndex
- 项目已使用 `llama-index-core`
- RAGAS 官方支持 LlamaIndex 集成

#### ✅ 代码规范严格
- 类型标注、docstring、异常处理完备
- 便于在现有框架上优雅扩展

### 2. 不利因素（增加难度）

#### ❌ RAGAS 0.4.x 的 API 变更
RAGAS 在 0.4.x 版本进行了重大 API 重构：
- 旧版（0.2.x/0.3.x）：`ragas.evaluate(metrics=[...])`
- 新版（0.4.x）：引入了新的 `EvaluationDataset`、`SingleTurnSample` 等抽象

**需要调研的点：**
- 0.4.x 的确切 API 格式
- 与当前数据格式的适配代码量

#### ❌ 中文支持
RAGAS 原生针对英文优化：
- Faithfulness 的 statement extraction prompt 是英文的
- 本项目已有中文 prompt（见 `metrics.py` 的 `FAITHFULNESS_STATEMENT_PROMPT`）

**需要解决的问题：**
- 是否需要自定义 RAGAS 的 LLM evaluator
- 还是直接用 RAGAS 的默认英文 prompt（不适用于中文场景）

#### ❌ 自定义指标与 RAGAS 指标并存
当前项目已有成熟的自研指标实现（`eval/metrics.py`）：
- 622 行代码，包含完整的 prompt、验证逻辑
- 与 RAGAS 的实现方式不同（RAGAS 使用 LangChain）

**决策点：**
- 完全替换为 RAGAS？
- 还是双轨并存（对比实验）？

#### ❌ LLM 客户端不兼容
- RAGAS 默认使用 LangChain 的 LLM wrapper
- 本项目使用 Anthropic SDK 直接调用 LongCat API
- 需要创建兼容的 LLM 适配器

#### ❌ 测试数据格式差异
当前测试集包含：
- `expected_sources`（文档级）
- `expected_answer`（golden answer）

RAGAS 需要：
- `ground_truth`（期望答案）
- `contexts`（检索到的上下文）

需要数据转换层。

### 3. 技术难点详细分析

#### 难点 1：LLM Evaluator 适配

**问题描述：**
RAGAS 需要通过 `llm` 和 `embeddings` 参数来配置评测时使用的模型。官方示例：
```python
from ragas import evaluate
from ragas.embeddings import HuggingfaceEmbeddings
from ragas.llms import LangchainLLM

# 需要 LangChain 格式的 LLM
llm = LangchainLLM(llm=ChatAnthropic(...))
```

**本项目现状：**
- 直接使用 Anthropic SDK
- 不调用 LangChain
- 使用自定义的 client 创建逻辑（`_create_llm_client()`）

**解决思路：**
1. 方案 A：引入 LangChain 作为中间层（增加依赖）
2. 方案 B：实现自定义的 RAGAS LLM adapter（需要研究 RAGAS 的接口契约）
3. 方案 C：使用 RAGAS 的通用 LLM 接口（如果 0.4.x 提供）

**难度评估：** 🔴 中高
- 需要深入研究 RAGAS 0.4.x 的 LLM 抽象接口
- 预计需要 20-50 行适配代码

#### 难点 2：中文 Prompt 自定义

**问题描述：**
RAGAS 内置的 Faithfulness 评测使用英文 prompt：
```python
# RAGAS 内部
prompt = """Extract statements from this answer..."""
```

而本项目已有成熟的中文 prompt：
```python
# metrics.py
FAITHFULNESS_STATEMENT_PROMPT = """请分析以下回答，提取其中的所有事实陈述..."""
```

**解决思路：**
1. 方案 A：继承 RAGAS 的 `Faithfulness` 类，重写 prompt
2. 方案 B：使用 RAGAS 的自定义 metric 机制
3. 方案 C：保留自研实现，RAGAS 仅用于对比实验

**难度评估：** 🟡 中等
- RAGAS 支持自定义 metric（需要继承基类）
- 预计需要 50-100 行自定义代码

#### 难点 3：数据格式转换

**问题描述：**
当前数据流：
```python
# run_eval.py
result = pipeline.query(question)
# result = {"answer": "...", "contexts": [...], "sources": [...]}
```

RAGAS 需要：
```python
# RAGAS 0.4.x
from ragas import SingleTurnSample
sample = SingleTurnSample(
    user_input=question,
    response=answer,
    retrieved_contexts=contexts,
    reference=ground_truth  # 可选
)
```

**解决思路：**
添加一个转换函数：
```python
def to_ragas_format(eval_results: List[Dict]) -> EvaluationDataset:
    samples = []
    for r in eval_results:
        samples.append(SingleTurnSample(
            user_input=r["question"],
            response=r["answer"],
            retrieved_contexts=r["contexts"],
        ))
    return EvaluationDataset(samples=samples)
```

**难度评估：** 🟢 低
- 纯数据映射，预计 20-30 行代码

#### 难点 4：评测流程集成

**问题描述：**
需要在 `run_eval.py` 中新增 RAGAS 评测路径，同时保持现有流程不变。

**解决思路：**
```python
# run_eval.py 新增
def run_ragas_evaluation(
    results: List[Dict],
    metrics: List[str],
    llm_config: Dict,
) -> Dict:
    """使用 RAGAS 框架执行评测"""
    dataset = to_ragas_format(results)
    # 配置 LLM 和 Embeddings
    # 调用 ragas.evaluate()
    # 返回结果
    pass
```

**难度评估：** 🟡 中等
- 需要 100-150 行代码
- 需要处理异常和日志

---

## 三、集成方案建议

### 方案 A：渐进式集成（推荐）

**策略：**
1. 保留现有自研评测系统（`eval/metrics.py`）
2. 新增 `eval/ragas_eval.py` 模块
3. 通过配置开关选择使用哪种评测方式
4. 初期用于对比实验（对比自研 vs RAGAS 的评测结果）

**优点：**
- 风险低，不影响现有功能
- 可以对比两种实现，验证评测准确性
- 为后续选择提供数据支持

**预计工作量：**
- 数据转换层：50 行
- LLM 适配层：50-100 行
- 评测集成：100-150 行
- 测试用例：100 行
- **总计：300-400 行代码**

**难度评级：** ⭐⭐☆☆☆（中等偏低）

### 方案 B：完全替换

**策略：**
1. 用 RAGAS 替换所有自研评测代码
2. 删除 `eval/metrics.py` 中的 LLM-based 指标
3. 保留数学计算类指标（Hit Rate, MRR, NDCG）

**优点：**
- 代码更简洁
- 与业界标准对齐
- 可利用 RAGAS 的更多指标（Context Precision, etc.）

**缺点：**
- 风险较高
- 丢失针对中文优化的 prompt
- 需要重新调优 RAGAS 的默认行为

**预计工作量：**
- 重构 `eval/metrics.py`：200 行
- 重构 `run_eval.py`：150 行
- 中文 prompt 适配：100 行
- 测试用例：150 行
- **总计：600 行代码**

**难度评级：** ⭐⭐⭐☆☆（中等）

### 方案 C：仅使用 RAGAS 的指标定义

**策略：**
1. 不引入 RAGAS 的评测流程
2. 仅参考 RAGAS 的指标定义和计算方法
3. 保持完全自研的实现

**优点：**
- 零集成风险
- 完全可控
- 针对性优化（中文场景）

**缺点：**
- 无法利用 RAGAS 的生态
- 需要自行维护评测代码

**预计工作量：**
- **无需额外代码**（已实现）

**难度评级：** ⭐☆☆☆☆（极低）

---

## 四、关键决策点

### 1. 是否需要引入 RAGAS？

**当前自研实现的优势：**
- ✅ 已针对中文场景优化（中文 prompt）
- ✅ 已集成到现有评测流程
- ✅ 异常处理完善
- ✅ 与实验管理系统深度集成

**RAGAS 的价值：**
- 业界标准，便于横向对比
- 更多指标（Context Precision, Context Recall, etc.）
- 活跃的社区和持续更新

**建议：**
先采用方案 A（渐进式），运行对比实验后再决定是否完全替换。

### 2. RAGAS 0.4.x 是否稳定？

需要验证：
- 0.4.x 的 API 是否稳定
- 文档是否完善
- 是否有 breaking changes

### 3. LLM 适配的工作量

取决于 RAGAS 0.4.x 的接口设计：
- 如果支持通用 LLM 接口 → 工作量小
- 如果需要 LangChain → 需要引入额外依赖

---

## 五、实施路线图（方案 A）

### Phase 1：调研与验证（1-2 天）

1. 安装 RAGAS 0.4.x
2. 阅读 0.4.x 的文档和 API
3. 编写最小示例验证：
   ```python
   from ragas import evaluate, SingleTurnSample, EvaluationDataset
   
   dataset = EvaluationDataset(samples=[...])
   result = evaluate(dataset=dataset, metrics=[...])
   ```
4. 确认 LLM 适配方式

**产出：** `docs/guides/ragas-integration.md`

### Phase 2：核心实现（2-3 天）

1. 创建 `eval/ragas_eval.py`
2. 实现数据转换函数
3. 实现 LLM 适配器
4. 实现自定义中文 metric（如需）
5. 集成到 `run_eval.py`（配置开关）

**产出：** 可运行的 RAGAS 评测模块

### Phase 3：对比实验（1-2 天）

1. 使用相同测试集运行两种评测
2. 对比结果差异
3. 分析差异原因
4. 撰写对比报告

**产出：** `data/eval/ragas_comparison.json`

### Phase 4：文档与测试（1 天）

1. 更新 `docs/guides/evaluation-metrics.md`
2. 添加 pytest 测试
3. 更新 `config.yaml`（RAGAS 配置）

**产出：** 完整的文档和测试

---

## 六、风险评估

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| RAGAS 0.4.x API 不稳定 | 中 | 中 | 锁定版本，使用 `>=0.4.3, <0.5` |
| 中文评测效果不佳 | 高 | 高 | 保留自研实现作为备份 |
| LLM 适配复杂 | 中 | 中 | 提前调研，准备 Plan B |
| 依赖冲突 | 低 | 高 | pixi 管理依赖，隔离环境 |
| 评测结果不一致 | 高 | 低 | 这正是对比实验的目的 |

---

## 七、结论

**总体难度评估：⭐⭐☆☆☆（中等偏低）**

**理由：**
1. 依赖已声明，安装无障碍
2. 数据流程高度一致，转换成本低
3. 现有代码架构清晰，易于扩展
4. 项目规范严格，代码质量高

**主要难点：**
1. LLM 客户端适配（需研究 RAGAS 0.4.x 接口）
2. 中文 prompt 自定义（需继承 RAGAS 基类）

**建议：**
采用**方案 A（渐进式集成）**，保留自研系统，新增 RAGAS 模块用于对比实验。这样既能利用 RAGAS 的生态优势，又不会破坏现有功能。

**预计总工作量：2-4 天**

---

## 八、下一步行动

1. **立即执行：** 安装 RAGAS 0.4.x 并验证 API
2. **调研重点：** RAGAS 0.4.x 的 LLM 适配方式
3. **决策点：** 确认 RAGAS 是否支持自定义 LLM client
4. **输出文档：** 创建 `docs/guides/ragas-integration.md`

---

*文档状态: active*
*作者: AI Assistant*
*版本: v0.1.0*
