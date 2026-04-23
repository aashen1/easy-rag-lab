# 实验评测系统使用指南

<!-- status: needs-update -->

> ⚠️ **文档状态**：本文档内容基本准确，但缺少 v0.1.8 新增功能的说明（TestSetManager 集成、等价组支持、问题有效性检查、增量生成、config_snapshot 完整保存、Technology Summary 等）。建议补充更新。

> 最后更新: 2026-04-18

本文档介绍如何使用自动化评测系统进行 RAG 系统实验。

---

## 概述

自动化评测系统支持：
- **多 Variant 对比实验**：在一个实验中对比多种配置
- **自动数据准备**：自动创建 Meal 和测试集
- **文档级问题生成**：基于完整文档生成真实场景问题
- **多维度评测指标**：检索指标 + 生成质量指标
- **多评测后端**：自研评测（builtin）+ RAGAS 评测框架
- **实验复现**：完整保存配置和数据，支持复现
- **报告生成**：自动生成结构化的实验报告

---

## 快速开始

### 运行实验

```bash
# 便捷写法（推荐）
pixi run exp baseline.yaml        # 自动补全为 exp_configs/baseline.yaml
pixi run exp baseline             # 也支持省略 .yaml 后缀

# 完整写法
pixi run python eval/run_experiment.py --config exp_configs/baseline.yaml
```

### 实验管理

```bash
# 列出所有实验
pixi run python eval/run_experiment.py --list

# 查看实验详情
pixi run python eval/run_experiment.py --info exp_20250416_120000

# 对比多个实验
pixi run python eval/run_experiment.py --compare exp_001 exp_002

# 复现实验
pixi run python eval/run_experiment.py --reproduce data/exp_reports/exp_20250416_120000

# 生成 LLM 增强报告
pixi run python eval/run_experiment.py --config exp_configs/baseline.yaml --llm-report
```

---

## 实验配置

实验配置文件位于 `exp_configs/` 目录，采用 YAML 格式：

```yaml
name: "experiment_name"
description: "实验描述"

data:
  meal: "meal_name"              # Meal 名称
  create_if_missing:             # 如果 Meal 不存在，自动创建
    sample_ratio: 0.1            # 采样比例
    seed: 42

test_sets:
  - strategy: "document"         # 文档级问题生成（推荐）
    num_questions: 20
    seed: 100
  - strategy: "factual"          # 传统策略（已弃用）
    num_questions: 20
    seed: 100

variants:
  - name: "variant_1"
    description: "variant 描述"
    config_overrides:            # 配置覆盖
      chunker:
        chunk_size: 512
        chunk_overlap: 0

evaluation:
  llm_preset: "default"
  backends: ["builtin"]          # 评测后端：["builtin"], ["ragas"], 或 ["builtin", "ragas"]
  metrics:
    retrieval:                   # 检索指标
      - "hit_rate"
      - "mrr"
      - "ndcg"
    generation:                  # 生成质量指标
      - "faithfulness"
      - "answer_relevancy"
```

### 配置字段说明

| 字段 | 说明 |
|------|------|
| `name` | 实验名称 |
| `description` | 实验描述 |
| `data.meal` | Meal 名称 |
| `data.create_if_missing` | 自动创建 Meal 的配置 |
| `test_sets[].strategy` | 问题策略（推荐 `document`，传统策略已弃用） |
| `test_sets[].num_questions` | 问题数量 |
| `variants[].name` | Variant 名称 |
| `variants[].config_overrides` | 配置覆盖 |
| `evaluation.llm_preset` | LLM preset |
| `evaluation.backends` | 评测后端列表，支持 `builtin`、`ragas` 或两者兼有 |
| `evaluation.metrics.retrieval` | 检索指标列表 |
| `evaluation.metrics.generation` | 生成质量指标列表 |

---

## 问题生成策略

### 文档级问题生成（推荐）

文档级问题生成（`strategy: "document"`）基于完整的 Markdown 文档生成问题，具有以下优势：

- **真实场景**：模拟用户阅读完整报告后的真实提问
- **多类型覆盖**：支持 6 种问题类型，覆盖不同场景
- **质量可控**：内置真实性检查，过滤学术化表述

**问题类型分布（默认）**：

| 类型 | 比例 | 说明 |
|------|------|------|
| 单知识点查询 | 30% | 查询具体数据、事实 |
| 多知识点综合 | 25% | 整合多个信息点 |
| 推理型问题 | 15% | 基于信息推理判断 |
| 对比分析 | 15% | 对比多个对象 |
| 缺失知识点 | 10% | 测试拒答能力 |
| 无关问题 | 5% | 测试边界识别 |

**配置示例**：

```yaml
test_sets:
  - strategy: "document"
    num_questions: 20
    type_distribution:          # 可选：自定义类型分布
      single_fact: 0.40
      multi_fact: 0.30
      reasoning: 0.15
      comparative: 0.10
      missing: 0.05
      irrelevant: 0.00
```

### 传统策略（已弃用）

以下策略已弃用，将在未来版本移除：

- `factual`：基于单个 chunk 生成事实性问题
- `boundary`：基于相邻 chunk 边界生成问题
- `multi_hop`：基于非相邻 chunk 生成多跳问题

建议迁移到 `document` 策略。

---

## 实验结果

实验结果保存在 `data/exp_reports/` 目录：

```
data/exp_reports/exp_20250416_120000/
├── manifest.json           # 实验元数据
├── config_snapshot.yaml    # 配置快照
├── meal_snapshot.json      # Meal 快照
├── results/                # 各 variant 结果
│   ├── variant_1.json
│   └── variant_2.json
├── test_sets/              # 测试集
└── experiment_report.md    # 实验报告
```

---

## 评测指标

### 检索质量指标

| 指标 | 说明 | 取值范围 |
|------|------|---------|
| **Hit Rate** | 检索结果中包含正确文档的比例 | 0.0 - 1.0 |
| **MRR** | 平均倒数排名，衡量第一个正确文档的排名 | 0.0 - 1.0 |
| **NDCG** | 归一化折损累积增益，综合考虑排序位置 | 0.0 - 1.0 |

### 生成质量指标

| 指标 | 说明 | 取值范围 |
|------|------|---------|
| **Faithfulness** | 回答的事实陈述是否可从上下文推导 | 0.0 - 1.0 |
| **Answer Relevancy** | 回答与问题的相关程度 | 0.0 - 1.0 |

> 详细指标说明请参阅 [评测指标详解](evaluation-metrics.md)。

### 指标配置

```yaml
evaluation:
  llm_preset: "default"
  backends: ["builtin"]          # 评测后端选择
  metrics:
    retrieval:
      - "hit_rate"
      - "mrr"
      - "ndcg"
    generation:                  # 生成质量指标需要 LLM 调用
      - "faithfulness"
      - "answer_relevancy"
```

**注意**：生成质量指标需要额外的 LLM 调用，会增加评测时间和成本。

### 使用 RAGAS 后端

在实验配置中启用 RAGAS 评测后端：

```yaml
evaluation:
  llm_preset: "default"
  backends: ["builtin", "ragas"]  # 同时使用自研和 RAGAS
  metrics:
    retrieval:
      - "hit_rate"
      - "mrr"
      - "ndcg"
    generation:
      - "faithfulness"            # 两个后端都会计算
      - "answer_relevancy"        # 两个后端都会计算
      - "context_precision"       # RAGAS 特有指标
      - "context_recall"          # RAGAS 特有指标
```

> RAGAS 特有指标（context_precision, context_recall, factual_correctness, semantic_similarity）需要在 `backends` 中包含 `"ragas"` 才能生效。详见 [RAGAS 评测系统指南](ragas-evaluation.md)。

---

## 常见问题

### Q: 如何对比不同 chunk size？

A: 创建一个包含多个 variant 的配置文件，每个 variant 覆盖 `chunker.chunk_size`。

### Q: 如何复现历史实验？

A: 使用 `--reproduce` 命令，指定实验目录路径。

### Q: 如何生成更详细的分析报告？

A: 使用 `--llm-report` 参数，系统会使用 LLM 生成深度分析报告。

---

## 相关文档

- [评测指标详解](evaluation-metrics.md)
- [RAGAS 评测系统指南](ragas-evaluation.md)
- [Meal 系统指南](meal-system.md)
- [配置参考](../config-reference.md)
