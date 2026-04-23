# RAGAS 评测系统使用指南

<!-- status: needs-update -->

> ⚠️ **文档状态**：本文档缺少 v0.1.8 新增 builtin 指标（Chunk-level、Dedup、FPR）的说明，且 "已知未修复问题" 章节中的部分问题（如 context_precision 聚合位置）可能已在后续修复中解决。建议核对并更新。

> 最后更新: 2026-04-21

本文档介绍如何使用 RAGAS 评测后端进行 RAG 系统评测，以及如何与自研评测系统并行使用。

---

## 1. RAGAS 框架简介

RAGAS（Retrieval Augmented Generation Assessment）是一个主流的开源 RAG 评测框架，提供了丰富的生成质量指标。本项目已集成 RAGAS 作为可选评测后端，与现有自研评测系统并行存在。

### 1.1 五大主流指标

本项目重点适配以下五个 RAGAS 主流指标：

| 指标 | 需要 GT | 评测对象 | 核心问题 | 计算方式简述 |
|------|---------|---------|---------|-------------|
| **Faithfulness** | ❌ | 生成 | 答案有没有瞎编？ | 从答案中提取事实陈述，逐一验证是否可从检索上下文推导 |
| **Answer Relevancy** | ❌ | 生成 | 答案有没有跑题？ | 从答案生成反向问题，计算与原问题的语义相似度 |
| **Context Precision** | ✅ | 检索 | 检索结果精不精？ | 判断每个检索上下文是否与参考答案相关，计算加权累积精确度 |
| **Context Recall** | ✅ | 检索 | 检索有没有漏？ | 将参考答案拆分为句子，逐一判断是否可从检索上下文推断 |
| **Answer Correctness** | ✅ | 端到端 | 答案对不对？ | 事实重叠 F1 + 语义相似度的加权平均 |

> **GT** = Ground Truth（标准答案），在测试数据中对应 `expected_answer` 字段。

### 1.2 评测后端对比

| 特性 | 自研（builtin） | RAGAS |
|------|----------------|-------|
| **检索指标** | hit_rate, mrr, ndcg, chunk_*, dedup_*, false_positive_rate, context_precision, context_recall | context_precision, context_recall |
| **生成指标** | faithfulness, answer_relevancy | faithfulness, answer_relevancy, answer_correctness, semantic_similarity |
| **LLM 调用方式** | 统一 LLM 客户端工厂（`create_llm_client`） | 统一 LLM 客户端工厂（`create_llm_client`，langchain 模式） |
| **评测模式** | 逐条串行 | 批量并行（推荐） |
| **额外依赖** | 无 | ragas, langchain-anthropic, langchain-community |

### 1.3 RAGAS 特有指标

除五大主流指标外，RAGAS 还提供以下特有指标：

| 指标 | 所需输入 | 说明 |
|------|---------|------|
| **semantic_similarity** | response, reference | 回答与参考答案的语义相似度（基于 Embedding 余弦相似度） |

> **注意**：`context_precision`、`context_recall`、`answer_correctness`、`semantic_similarity` 需要 `reference`（参考答案）才能计算。测试数据中的 `expected_answer` 字段将自动映射为 `reference`。其中 `context_precision` 和 `context_recall` 两个后端均支持，但计算方式不同。

---

## 2. 当前支持状态与验证方法

### 2.1 各指标支持状态

经过 v0.1.8 版本的修复，五大主流指标在 RAGAS 后端的支持情况如下：

| 指标 | 配置位置 | 数据流 | 状态 |
|------|---------|--------|------|
| **Faithfulness** | `generation` | `question` → `user_input`, `answer` → `response`, `contexts` → `retrieved_contexts` | ✅ 完整支持 |
| **Answer Relevancy** | `generation` | `question` → `user_input`, `answer` → `response` | ✅ 完整支持 |
| **Context Precision** | `retrieval` 或 `generation` | `question` → `user_input`, `contexts` → `retrieved_contexts`, `expected_answer` → `reference` | ✅ 完整支持 |
| **Context Recall** | `retrieval` 或 `generation` | `question` → `user_input`, `contexts` → `retrieved_contexts`, `expected_answer` → `reference` | ✅ 完整支持 |
| **Answer Correctness** | `generation` | `answer` → `response`, `expected_answer` → `reference` | ✅ 完整支持 |

**关键改进**（v0.1.8）：
- `context_precision` 和 `context_recall` 现在可以放在 `retrieval` 配置项下（语义更准确），也可放在 `generation` 下（向后兼容）
- 当 `reference` 缺失时，需要 `reference` 的指标会记录 warning 并优雅降级，不再导致程序崩溃
- RAGAS 指标导入优先使用公开 API，提升版本兼容性

### 2.2 自动测试验证

项目包含以下自动测试，可验证 RAGAS 评测链路的核心逻辑：

```bash
# 运行所有 RAGAS 相关测试
pixi run pytest tests/test_evaluators.py -v -k "Ragas"
pixi run pytest tests/test_experiment.py -v -k "context_precision or context_recall or ragas"
pixi run pytest tests/test_run_experiment.py -v -k "ragas or llm_retrieval"
```

**关键测试用例**：

| 测试文件 | 测试类/方法 | 验证内容 |
|---------|-----------|---------|
| `test_experiment.py` | `test_context_precision_in_retrieval_with_ragas_backend` | `context_precision` 在 `retrieval` 下 + RAGAS 后端可通过验证 |
| `test_experiment.py` | `test_context_precision_in_retrieval_with_builtin_backend` | `context_precision` 在 `retrieval` 下 + builtin 后端可通过验证 |
| `test_experiment.py` | `test_context_precision_in_retrieval_without_supported_backend` | 无支持后端时报错 |
| `test_experiment.py` | `test_non_builtin_generation_metrics_require_ragas` | `answer_correctness` 等需要 RAGAS 后端 |
| `test_evaluators.py` | `TestRagasEvaluatorReferenceWarning` | `reference` 缺失时的优雅降级 |
| `test_evaluators.py` | `TestRagasEvaluator` | RAGAS 评测器基本功能 |
| `test_run_experiment.py` | `test_compute_aggregate_llm_retrieval_from_*` | 指标聚合路径统一性 |

### 2.3 手动冒烟测试

自动测试使用 mock 验证逻辑正确性，但无法验证与 RAGAS 框架和 LLM API 的实际集成。手动冒烟测试用于验证端到端链路：

**最小冒烟测试**（仅验证 RAGAS 可运行）：

```bash
# 1. 确保 .env 中配置了 LLM_API_KEY 和 LLM_BASE_URL
# 2. 运行快速冒烟实验配置
pixi run python eval/run_experiment.py --config exp_configs/ragas_evaluation/ragas_quick.yaml
```

此配置仅计算 `faithfulness` 和 `answer_relevancy`（不需要 GT），生成 1 个问题，用于验证基本链路。

**完整五指标冒烟测试**（需要 GT）：

```bash
# 使用 ragas_only 配置，包含全部五个主流指标
pixi run python eval/run_experiment.py --config exp_configs/ragas_evaluation/ragas_only.yaml
```

此配置计算 `context_precision`、`context_recall`、`faithfulness`、`answer_relevancy`、`answer_correctness`，需要测试数据中包含 `expected_answer` 字段。

**验证要点**：
- 实验报告成功生成，无报错
- 报告中包含所有请求的指标分数
- `context_precision`/`context_recall` 出现在报告的检索指标区域
- 需要 GT 的指标未返回 NaN

---

## 3. 新用户完整实验指南

以下步骤引导一个刚 clone 本代码库的新用户，从零跑出一个包含五个 RAGAS 指标的完整实验报告。

### 3.1 环境准备

```bash
# 1. Clone 代码库并进入目录
git clone <repo-url> && cd ash-easy-rag

# 2. 安装 pixi（如果尚未安装）
# 参见 https://pixi.sh/latest/ 安装指南

# 3. 安装项目依赖（pixi 会自动根据 pixi.toml / pyproject.toml 安装）
pixi install

# 4. 配置环境变量（复制模板并填写）
cp .env.example .env
# 编辑 .env，至少填写：
#   LLM_API_KEY=your-api-key
#   LLM_BASE_URL=https://your-api-endpoint
#   LLM_MODEL_ID=your-model-id
```

### 3.2 准备文档数据

```bash
# 将 PDF 文件放入 data/raw/ 目录
mkdir -p data/raw
cp /path/to/your/reports/*.pdf data/raw/

# 解析文档并构建向量索引
pixi run python src/main.py --ingest
```

### 3.3 准备测试数据（含 Ground Truth）

五个 RAGAS 指标中，`context_precision`、`context_recall`、`answer_correctness` 需要 Ground Truth（`expected_answer` 字段）。测试数据有两种来源：

**方式 A：自动生成**（推荐入门方式）

实验配置中使用 `on_missing: "auto"` 并指定 `generation` 策略，系统会自动生成包含 `expected_answer` 的测试集：

```yaml
test_sets:
  - name: "my_ragas_test"
    on_missing: "auto"
    generation:
      strategy: "document"
      num_questions: 20
```

> 自动生成的 `expected_answer` 由 LLM 生成，质量取决于 LLM 能力，适合快速验证链路。如需高精度评测，建议手动标注。

**方式 B：手动标注**

创建 JSON 文件，每个问题包含 `answer` 字段作为 Ground Truth：

```json
{
  "metadata": { "name": "manual_test", ... },
  "questions": [
    {
      "id": 1,
      "question": "贵州茅台2023年营收是多少？",
      "answer": "1505.60亿元",
      "question_type": "single_fact",
      "source_files": ["贵州茅台2023年年报.pdf"]
    }
  ]
}
```

将文件放入 `data/meals/<meal_name>/test_sets/` 目录下。

### 3.4 创建实验配置

创建一个包含五个 RAGAS 指标的实验配置文件：

```yaml
name: "my_first_ragas_eval"
description: "首次RAGAS五指标完整评测"

data:
  meal: "my_meal"              # 与 data/meals/ 下的目录名对应
  create_if_missing:
    sample_ratio: 0.1
    seed: 42

test_sets:
  - name: "ragas_five_metrics"
    on_missing: "auto"
    generation:
      strategy: "document"
      num_questions: 20

variants:
  - name: "baseline"
    description: "基线配置"
    config_overrides: {}

evaluation:
  backends: ["ragas"]
  llm_preset: "default"
  metrics:
    retrieval:
      - "context_precision"    # 检索指标：精不精
      - "context_recall"       # 检索指标：有没有漏
    generation:
      - "faithfulness"         # 生成指标：有没有瞎编
      - "answer_relevancy"     # 生成指标：有没有跑题
      - "answer_correctness"   # 端到端指标：对不对

llm:
  question_generation: "default"
  answering: "default"
```

> 也可直接使用项目自带的模板：`exp_configs/ragas_evaluation/ragas_only.yaml`

### 3.5 运行实验

```bash
pixi run python eval/run_experiment.py --config exp_configs/ragas_evaluation/ragas_only.yaml
```

### 3.6 查看结果

实验完成后，结果保存在 `data/exp_reports/` 下：

```
data/exp_reports/exp_YYYYMMDD_HHMMSS_ragas_only_evaluation/
  experiment_report.md       # 评测报告（含所有指标分数）
  config_snapshot.yaml       # 实验配置快照
  results/
    baseline_ragas.json      # 逐题详细结果
```

打开 `experiment_report.md` 查看各指标的平均分数和逐题详情。

### 3.7 双后端对比（可选）

如需同时获得 builtin 检索指标和 RAGAS 生成指标，可使用双后端配置：

```bash
pixi run python eval/run_experiment.py --config exp_configs/ragas_evaluation/ragas_builtin.yaml
```

此模式下，`faithfulness` 和 `answer_relevancy` 会由两个后端分别计算并添加前缀（`builtin_faithfulness` vs `ragas_faithfulness`），便于对比。

---

## 4. 已知未修复问题

以下问题仅影响 RAGAS 评测链路，截至 v0.1.8 尚未修复：

### 4.1 RAGAS 框架版本兼容性风险

**问题**：当前 RAGAS 指标导入使用 `ragas.metrics._metrics` 公开 API（优先）和 `ragas.metrics` 私有类（fallback）。RAGAS 框架处于快速迭代期（当前锁定 `>=0.4.3, <0.5`），API 可能随时变更。

**影响**：RAGAS 升级到 0.5.x 时，导入路径可能 break。

**临时方案**：锁定 RAGAS 版本范围，升级前在测试环境验证。

### 4.2 `context_precision`/`context_recall` 在 `generation` 下时聚合位置不一致

**问题**：如果用户将 `context_precision`/`context_recall` 放在 `generation` 配置项下（旧写法），RAGAS 后端会将它们放在结果的 `generation` 字典中，而非 `llm_retrieval` 字典。虽然 `compute_aggregate_metrics` 已做统一处理（从两个来源聚合），但在逐题结果中，这些指标的位置取决于配置方式。

**影响**：逐题结果中指标位置不一致，可能影响自定义的结果解析逻辑。

**临时方案**：统一将 `context_precision`/`context_recall` 放在 `retrieval` 配置项下。

### 4.3 自动生成的 Ground Truth 质量有限

**问题**：自动生成的 `expected_answer` 由 LLM 生成，可能存在幻觉或不准确。这直接影响 `context_precision`、`context_recall`、`answer_correctness` 三个需要 GT 的指标的可信度。

**影响**：基于自动 GT 的指标分数仅供参考，不适合作为正式评测依据。

**临时方案**：对关键测试集进行手动标注，覆盖核心问题。

### 4.4 RAGAS `evaluate()` 的 `raise_exceptions` 行为差异

**问题**：`evaluate_single` 使用 `raise_exceptions=True`，遇到错误会直接抛异常；`evaluate_batch` 使用 `raise_exceptions=False`，错误时静默返回 NaN。两种模式的行为不一致。

**影响**：单条评测模式下，一个样本的错误可能中断整个评测流程。

**临时方案**：优先使用 `evaluate_batch`（默认行为），避免使用 `evaluate_single`。

---

## 5. 后续优化方向

### 5.1 RAGAS 版本升级与 API 适配

当前锁定 RAGAS `>=0.4.3, <0.5`。RAGAS 0.5.x 可能引入 breaking changes（如 `SingleTurnSample` API 变更、指标类重命名等）。建议：

- 建立 RAGAS 版本兼容性矩阵
- 添加版本检测逻辑，自动选择正确的导入路径
- 在 CI 中增加 RAGAS 集成测试

### 5.2 Ground Truth 手动标注工具

目前缺少结构化的 GT 标注工具。建议：

- 开发交互式标注 CLI 或 Web 界面
- 支持对自动生成的 `expected_answer` 进行审核和修正
- 标注结果直接写入 test set JSON，与 TestSetManager 集成

### 5.3 指标结果统一归一化

当前 `context_precision`/`context_recall` 在 builtin 和 RAGAS 两个后端使用不同的 prompt 和评分逻辑，分数不可直接对比。建议：

- 在报告中增加后端间分数的相关性分析
- 提供归一化选项，将两个后端的分数映射到同一尺度
- 记录每次评测的 prompt 版本，便于追溯差异来源

### 5.4 RAGAS 评测缓存与增量计算

RAGAS 评测调用 LLM 成本较高，当前每次实验都重新计算所有指标。建议：

- 实现评测结果缓存（基于 question + answer + contexts 的 hash）
- 支持增量评测：仅对新增或变更的样本重新计算
- 提供缓存失效策略（如 prompt 版本变更时自动失效）

### 5.5 RAGAS 指标与 Builtin 指标的深度对比分析

双后端模式目前仅提供并排展示，缺少深度分析。建议：

- 自动生成后端间差异报告（哪些题目差异大、差异方向是否一致）
- 对差异大的样本进行根因分析（prompt 差异 vs 评分逻辑差异）
- 提供置信区间估计，帮助判断差异是否具有统计显著性

### 5.6 RAGAS 评测的 Token 消耗追踪

RAGAS 评测的 LLM 调用次数和 Token 消耗目前未被追踪。建议：

- 在 RAGAS 评测结果中记录 Token 使用量
- 与现有 Token 追踪系统（`docs/guides/token-tracking.md`）集成
- 提供评测成本预估功能

---

## 配置详解

### config.yaml 中的 RAGAS 配置

```yaml
evaluation:
  # 评测后端列表：支持 "builtin"、"ragas" 或两者兼有
  backends: ["builtin"]

  # RAGAS 专用配置
  ragas:
    enabled: false                    # 是否启用 RAGAS
    llm_backend: "anthropic"          # LLM 后端：推荐 "anthropic"（兼容 LongCat API）
    embeddings_backend: "local"       # Embeddings 后端："local"（BGE）或 "openai"
    run_config:
      max_workers: 5                  # 并行评测的最大工作线程数
      timeout: 60                     # 单次评测超时时间（秒）
      max_retries: 3                  # 失败重试次数
    embedding:                        # Embeddings 模型配置（可选，覆盖全局 embedding 配置）
      model_name: "BAAI/bge-large-zh-v1.5"  # RAGAS 使用的 Embeddings 模型
      device: "cuda"                  # 运行设备："cuda" 或 "cpu"
```

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `ragas.enabled` | `false` | 是否启用 RAGAS 评测 |
| `ragas.llm_backend` | `"anthropic"` | LLM 接口类型。`"anthropic"` 使用 LangChain Anthropic 接口连接 LongCat API |
| `ragas.embeddings_backend` | `"local"` | Embeddings 接口。`"local"` 使用本地 BGE 模型，`"openai"` 使用 OpenAI 兼容接口 |
| `ragas.run_config.max_workers` | `5` | RAGAS 批量评测的并行度 |
| `ragas.run_config.timeout` | `60` | 单次评测超时时间（秒） |
| `ragas.run_config.max_retries` | `3` | 评测失败时的重试次数 |
| `ragas.embedding.model_name` | `"BAAI/bge-large-zh-v1.5"` | RAGAS 使用的 Embeddings 模型名称 |
| `ragas.embedding.device` | `"cuda"` | Embeddings 模型运行设备 |

> **配置读取优先级**：`ragas.embedding.model_name` 优先于 `ragas.embedding_model`（旧字段），两者均未设置时回退到全局 `embedding.model_name`。`ragas.embedding.device` 未设置时回退到全局 `embedding.device`。

### 实验配置中的评测后端

实验配置 YAML 中的 `evaluation.backends` 字段控制使用哪些评测后端：

```yaml
evaluation:
  backends: ["builtin"]    # 仅自研评测
```

```yaml
evaluation:
  backends: ["ragas"]      # 仅 RAGAS 评测
```

```yaml
evaluation:
  backends: ["builtin", "ragas"]  # 同时使用两个评测系统
```

> 当 `backends` 中包含 `"ragas"` 时，`config.yaml` 中的 `ragas.enabled` 应设为 `true`。

---

## 后端选择指南

### 仅使用自研评测

适用于：快速评测、关注检索指标与生成指标、无需额外依赖。

```yaml
evaluation:
  backends: ["builtin"]
  metrics:
    retrieval:
      - "hit_rate"
      - "mrr"
      - "ndcg"
      - "chunk_hit_rate"
      - "chunk_mrr"
      - "chunk_ndcg"
      - "dedup_hit_rate"
      - "dedup_mrr"
      - "dedup_ndcg"
      - "false_positive_rate"
      - "context_precision"
      - "context_recall"
    generation:
      - "faithfulness"
      - "answer_relevancy"
```

> **builtin 检索指标说明**：
> - **基础指标**：`hit_rate`、`mrr`、`ndcg` — 基于文档级别的检索评估
> - **chunk 级别指标**：`chunk_hit_rate`、`chunk_mrr`、`chunk_ndcg` — 基于切块级别的检索评估
> - **去重指标**：`dedup_hit_rate`、`dedup_mrr`、`dedup_ndcg` — 去除同一文档重复结果后的检索评估
> - **FPR**：`false_positive_rate` — 针对无关问题的误检率
> - **LLM 检索指标**：`context_precision`、`context_recall` — 需要调用 LLM，需提供 `llm_config`

### 仅使用 RAGAS 评测

适用于：需要更丰富的生成质量指标、需要与业界标准对齐。

```yaml
evaluation:
  backends: ["ragas"]
  metrics:
    retrieval:
      - "context_precision"    # RAGAS 支持的检索指标
      - "context_recall"
    generation:
      - "faithfulness"
      - "answer_relevancy"
      - "answer_correctness"
      - "semantic_similarity"
```

> **注意**：RAGAS 不提供传统检索指标（hit_rate, mrr, ndcg）。如果需要这些指标，请同时启用 builtin 后端。

### 双后端并行评测（推荐）

适用于：全面评测、对比两套指标结果。

```yaml
evaluation:
  backends: ["builtin", "ragas"]
  metrics:
    retrieval:
      - "hit_rate"
      - "mrr"
      - "ndcg"
      - "context_precision"    # 两个后端分别计算
      - "context_recall"       # 两个后端分别计算
    generation:
      - "faithfulness"
      - "answer_relevancy"
      - "answer_correctness"
```

此模式下：
- **传统检索指标**（hit_rate, mrr, ndcg）由 builtin 后端计算
- **faithfulness, answer_relevancy** 由两个后端分别计算，可对比结果差异
- **context_precision, context_recall** 由两个后端分别计算（计算方式不同）
- **answer_correctness, semantic_similarity** 仅由 RAGAS 后端计算

### 指标命名空间前缀

当使用双后端（`["builtin", "ragas"]`）时，生成指标和 LLM 检索指标会自动添加后端名称前缀以区分来源：

| 原始指标名 | builtin 结果键名 | RAGAS 结果键名 |
|-----------|----------------|---------------|
| `faithfulness` | `builtin_faithfulness` | `ragas_faithfulness` |
| `answer_relevancy` | `builtin_answer_relevancy` | `ragas_answer_relevancy` |
| `context_precision` | `builtin_context_precision` | `ragas_context_precision` |
| `context_recall` | `builtin_context_recall` | `ragas_context_recall` |

当仅使用单个后端时，不添加前缀，指标键名保持原始名称（如 `faithfulness`、`answer_relevancy`）。

> **注意**：传统检索指标（hit_rate, mrr, ndcg 等）不受前缀影响，始终由 builtin 后端计算，保持原始名称。

---

## RAGAS 指标详解

### Faithfulness（忠实度）

回答中的事实陈述是否可以从检索到的上下文中推导出来。

- **所需输入**：question, answer, contexts
- **取值范围**：0.0 - 1.0
- **与自研指标的关系**：语义相同，计算方式不同（RAGAS 使用自己的 prompt 和评分逻辑）

### Answer Relevancy（回答相关性）

回答与问题的相关程度。

- **所需输入**：question, answer
- **取值范围**：0.0 - 1.0
- **与自研指标的关系**：语义相似，但 RAGAS 的计算方式基于生成反向问题并计算相似度

### Context Precision（上下文精确度）

检索结果中，相关文档是否排在靠前的位置。

- **所需输入**：question, contexts, **reference**
- **取值范围**：0.0 - 1.0
- **两个后端均支持**：builtin 使用自定义 prompt 逐条判断上下文相关性；RAGAS 使用框架自带逻辑
- **配置位置**：`retrieval`（推荐）或 `generation`

**解读**：
- **0.8+**：相关文档排名靠前，检索排序质量优秀
- **0.5-0.8**：部分相关文档排名靠后，可优化
- **< 0.5**：相关文档排名靠后，需要改进检索或添加重排序

**改进建议**：
- 启用 Reranker 重排序
- 优化 Embedding 模型
- 调整 `top_k` 参数

### Context Recall（上下文召回率）

检索结果是否覆盖了回答所需的所有信息。

- **所需输入**：question, contexts, **reference**
- **取值范围**：0.0 - 1.0
- **两个后端均支持**：builtin 使用自定义 prompt 逐句判断信息覆盖度；RAGAS 使用框架自带逻辑
- **配置位置**：`retrieval`（推荐）或 `generation`

**解读**：
- **0.8+**：检索结果信息覆盖充分
- **0.5-0.8**：部分关键信息未被检索到
- **< 0.5**：大量关键信息缺失

**改进建议**：
- 增加 `top_k` 值
- 调整 `chunk_size` 和 `chunk_overlap`
- 考虑混合检索（BM25 + 向量）

### Answer Correctness（答案正确性）

答案正确性综合评估生成答案与参考答案的匹配程度，包含两个关键方面：
- **事实相似性**：使用 claim-level 对比，计算 TP/FP/FN，得出 F1 分数
- **语义相似度**：基于 Embedding 向量的余弦相似度

最终分数是两者的加权平均（默认权重各 0.5）。

- **所需输入**：response, **reference**
- **取值范围**：0.0 - 1.0
- **自研系统无此指标**

> 此指标高度依赖参考答案的质量。如果 `expected_answer` 不够准确，此指标可能不可靠。

### Semantic Similarity（语义相似度）

回答与参考答案的语义相似度，基于 Embedding 向量的余弦相似度。

- **所需输入**：response, **reference**
- **取值范围**：0.0 - 1.0
- **自研系统无此指标**

---

## LongCat API 适配

两个评测后端均通过统一的 LLM 客户端工厂 `create_llm_client()`（位于 `src/utils.py`）连接 LongCat API，适配方式如下：

1. **统一工厂**：`create_llm_client(llm_config, mode)` 支持两种模式
   - `mode="sdk"`：返回 Anthropic SDK 客户端（builtin 后端使用）
   - `mode="langchain"`：返回 `LangchainLLMWrapper(ChatAnthropic)` （RAGAS 后端使用）
2. **URL 适配**：自动在 `base_url` 后追加 `/anthropic` 路径
3. **认证方式**：通过 `default_headers` 传递 Bearer Token 认证（`api_key="dummy"` + 真实 key 在 Header 中）
4. **LLM 包装**：RAGAS 模式下使用 `LangchainLLMWrapper` 将 LangChain LLM 包装为 RAGAS 兼容格式

> 环境变量 `LLM_API_KEY`、`LLM_BASE_URL`、`LLM_MODEL_ID` 的配置方式与自研评测系统完全一致，无需额外设置。

---

## 编程接口

### 直接使用评测器

如果需要在代码中直接使用评测器：

```python
from eval.evaluators import BuiltinEvaluator, RagasEvaluator

# 创建 RAGAS 评测器（config 参数中的 ragas 子键会被读取）
ragas = RagasEvaluator(config={
    "ragas": {
        "run_config": {"max_workers": 5, "timeout": 60, "max_retries": 3},
        "embedding": {"model_name": "BAAI/bge-large-zh-v1.5", "device": "cuda"},
    }
})
result = ragas.evaluate_single(
    question_id="q001",
    question="贵州茅台2023年营收是多少？",
    answer="贵州茅台2023年实现营业收入1505.60亿元。",
    contexts=["贵州茅台2023年年度报告显示，公司实现营业收入1505.60亿元。"],
    expected_answer="1505.60亿元",
    llm_config={
        "api_key": "your-api-key",
        "base_url": "https://your-api-endpoint",
        "model_name": "your-model-id",
    },
    generation_metrics=["faithfulness", "context_precision"],
)
```

### 批量评测

RAGAS 推荐使用批量评测以获得更好的性能：

```python
ragas = RagasEvaluator()

samples = [
    {
        "question_id": "q001",
        "question": "问题1",
        "answer": "回答1",
        "contexts": ["上下文1"],
        "expected_answer": "参考答案1",
    },
    {
        "question_id": "q002",
        "question": "问题2",
        "answer": "回答2",
        "contexts": ["上下文2"],
        "expected_answer": "参考答案2",
    },
]

results = ragas.evaluate_batch(
    samples=samples,
    llm_config={
        "api_key": "your-api-key",
        "base_url": "https://your-api-endpoint",
        "model_name": "your-model-id",
    },
    generation_metrics=["faithfulness", "answer_relevancy", "context_precision"],
)
```

---

## 常见问题

### Q: RAGAS 评测报 ImportError 怎么办？

A: RAGAS 需要额外的依赖包。运行以下命令安装：

```bash
pixi add langchain-anthropic langchain-community
```

### Q: RAGAS 指标需要参考答案（reference），但测试数据没有怎么办？

A: `context_precision`、`context_recall`、`answer_correctness`、`semantic_similarity` 需要 `reference` 才能计算。如果测试数据中没有 `expected_answer` 字段：
- `evaluate_batch` 会记录 warning，这些指标可能返回 NaN
- `evaluate_single` 会自动跳过需要 `reference` 的指标，仅计算不需要 `reference` 的指标

建议：
- 使用 `document` 策略生成测试集，会自动包含 `expected_answer`
- 手动标注关键测试数据的参考答案

### Q: 自研和 RAGAS 的 faithfulness 结果为什么不同？

A: 两者的计算方式不同：
- **自研**：使用自定义 prompt，通过 LLM 判断每个陈述是否可从上下文推导
- **RAGAS**：使用 RAGAS 框架自带的 prompt 和评分逻辑

两者都是有效的评测方式，差异反映了不同评估策略的特点。双后端并行评测可以提供更全面的视角。

### Q: RAGAS 评测速度慢怎么办？

A: 尝试以下优化：
- 增大 `ragas.run_config.max_workers`（默认 5）
- 减少评测指标数量
- 使用批量评测而非逐条评测
- 检查 API 调用的速率限制

### Q: context_precision 和 context_recall 应该放在 retrieval 还是 generation 下？

A: **推荐放在 `retrieval` 下**，因为它们语义上是检索指标。v0.1.8 起两种位置均支持：
- 放在 `retrieval` 下：结果出现在 `llm_retrieval` 字典中，聚合到 `avg_context_precision`/`avg_context_recall`
- 放在 `generation` 下：结果出现在 `generation` 字典中，聚合路径相同但逐题结果位置不同

为保持一致性，建议统一使用 `retrieval` 位置。

---

## 相关文档

- [评测指标详解](evaluation-metrics.md)
- [实验系统指南](experiment-system.md)
- [测试集管理](test-set-management.md)
