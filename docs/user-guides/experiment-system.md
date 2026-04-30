# 实验评测系统使用指南

> 最后更新: 2026-05-01

本文档介绍如何使用自动化评测系统进行 RAG 系统实验。

---

## 概述

自动化评测系统支持：
- **多 Variant 对比实验**：在一个实验中对比多种配置
- **增量实验工作流**：先跑一个 variant，看结果后逐步添加更多 variant，已验证的结果自动复用
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
  - name: "my_test_set"          # 测试集名称（可选，省略时自动推导）
    on_missing: "auto"
    generation:
      strategy: "document"       # 文档级问题生成（推荐）
      num_questions: 20
      seed: 100
      type_distribution:         # 可选：自定义类型分布
        single_fact: 0.30
        multi_fact: 0.25
        reasoning: 0.15
        comparative: 0.15
        missing: 0.10
        irrelevant: 0.05
        adversarial: 0.00

variants:
  - name: "variant_1"
    description: "variant 描述"
    config_overrides:            # 配置覆盖
      chunker:
        chunk_size: 512
        chunk_overlap: 0

evaluation:
  backends: ["builtin"]          # 评测后端：["builtin"], ["ragas"], 或 ["builtin", "ragas"]
  llm_preset: "default"          # LLM preset
  metrics_preset: "core"         # 指标预设：core / extended / full / custom
  resolution_strategy: "priority_fallback"  # 解析策略
  backend_priority: ["builtin", "ragas"]    # 后端优先级

llm:
  question_generation: "default"
  answering: "default"
```

### 配置字段说明

| 字段 | 说明 |
|------|------|
| `name` | 实验名称 |
| `description` | 实验描述 |
| `data.meal` | Meal 名称 |
| `data.create_if_missing` | 自动创建 Meal 的配置 |
| `test_sets[].name` | 测试集名称（可选，省略时自动推导为 `{strategy}_n{num_questions}`） |
| `test_sets[].generation.strategy` | 问题策略（推荐 `document`，传统策略已弃用） |
| `test_sets[].generation.num_questions` | 问题数量 |
| `variants[].name` | Variant 名称 |
| `variants[].config_overrides` | 配置覆盖 |
| `evaluation.backends` | 评测后端列表，支持 `builtin`、`ragas` 或两者兼有 |
| `evaluation.llm_preset` | LLM preset |
| `evaluation.metrics_preset` | 指标预设（core/extended/full/custom），详见 [配置参考](config-reference.md) |
| `evaluation.resolution_strategy` | 解析策略（priority_fallback/comparison） |
| `evaluation.backend_priority` | priority_fallback 模式的后端优先级 |

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
  - name: "my_test_set"
    on_missing: "auto"
    generation:
      strategy: "document"
      num_questions: 20
      type_distribution:          # 可选：自定义类型分布
        single_fact: 0.40
        multi_fact: 0.30
        reasoning: 0.15
        comparative: 0.10
        missing: 0.05
        irrelevant: 0.00
        adversarial: 0.00
```

### 传统策略（已弃用）

以下策略已弃用，将在未来版本移除：

- `factual`：基于单个 chunk 生成事实性问题
- `boundary`：基于相邻 chunk 边界生成问题
- `multi_hop`：基于非相邻 chunk 生成多跳问题

建议迁移到 `document` 策略。

---

## 增量实验工作流

增量实验工作流允许你**逐步构建实验**：先跑一个 variant，检查结果，不满意就调整参数重跑，满意后再添加新的 variant。系统通过 **Config Hash 验证**确保复用的结果确实与当前配置一致。

### 核心概念

| 概念 | 说明 |
|------|------|
| **Config Hash** | 对 variant 的完整配置（config_overrides + merged config + data/test_sets/evaluation）计算的确定性哈希，存储在 `manifest.json` 的 `variant_config_hashes` 字段中 |
| **Resume** | 使用 `--resume` 参数复用已有实验目录，跳过已完成的 variant |
| **Hash 验证** | Resume 时自动比较当前配置的 hash 与存储的 hash，匹配则复用结果，不匹配则自动重跑 |
| **Invalidate** | 当 hash 不匹配时，系统自动将 variant 标记为未完成，强制重跑 |

### 典型工作流

```bash
# ── 第 1 步：先跑一个 variant ──
pixi run exp my_experiment.yaml
# → 创建实验目录 exp_20260501_120000_my_experiment
# → 跑完 variant_a，结果和 config hash 写入 manifest

# ── 第 2 步：查看结果 ──
pixi run python eval/run_experiment.py --info exp_20260501_120000_my_experiment

# ── 第 3 步：不满意？修改 YAML 中 variant_a 的参数，然后 resume ──
pixi run exp my_experiment.yaml --resume data/exp_reports/exp_20260501_120000_my_experiment
# → 检测到 variant_a 的 config hash 变了
# → 自动 invalidate 并重跑 variant_a

# ── 第 4 步：满意了！在 YAML 中添加 variant_b，再 resume ──
pixi run exp my_experiment.yaml --resume data/exp_reports/exp_20260501_120000_my_experiment
# → variant_a 的 hash 验证通过 ✅ 直接复用已有结果
# → variant_b 是新的，正常跑 ✅

# ── 第 5 步：继续添加更多 variant ──
# 在 YAML 中添加 variant_c, variant_d ...
pixi run exp my_experiment.yaml --resume data/exp_reports/exp_20260501_120000_my_experiment
# → variant_a, variant_b 复用 ✅
# → variant_c, variant_d 新跑 ✅
```

### 选择性重跑

如果只想重跑某一个 variant，而不影响其他已完成的 variant，使用 `--force-variant`：

```bash
# 只重跑 variant_b，其他 variant 继续复用
pixi run exp my_experiment.yaml --resume <exp_dir> --force-variant variant_b
```

也可以同时指定多个 variant：

```bash
pixi run exp my_experiment.yaml --resume <exp_dir> --force-variant variant_a variant_b
```

### 全部重跑

如果需要从头开始，使用 `--force-rerun`：

```bash
pixi run exp my_experiment.yaml --resume <exp_dir> --force-rerun
# → 忽略所有 checkpoint，重跑所有 variant
```

### Hash 验证机制详解

Resume 时，系统对每个已完成的 variant 执行以下验证：

1. **计算当前 hash**：根据 YAML 中的 variant 配置 + 系统配置 + 实验级配置计算 hash
2. **比较存储 hash**：从 `manifest.json` 的 `variant_config_hashes` 中读取之前存储的 hash
3. **判断结果**：
   - **Hash 匹配** → 复用已有结果，跳过该 variant
   - **Hash 不匹配** → 输出警告，自动 invalidate 并重跑
   - **无存储 hash**（旧 manifest）→ 输出警告，安全起见重跑

**Hash 包含的内容**：

| 组成部分 | 说明 |
|---------|------|
| `variant.config_overrides` | variant 的配置覆盖 |
| `merged config`（sanitized） | 合并后的完整管道配置（去除 API key 等敏感信息） |
| `exp_data` | 实验的 data 配置（meal 名称、采样率等） |
| `exp_test_sets` | 测试集配置 |
| `exp_evaluation` | 评测配置 |

> **注意**：修改系统级 `config.yaml` 也会改变 merged config，从而触发 hash 变化。这是预期行为——系统配置的变更确实会影响实验结果。

### 向后兼容

对于在引入 Config Hash 之前创建的实验目录，`manifest.json` 中没有 `variant_config_hashes` 字段。此时系统会：

- 输出警告日志，提示无法验证结果一致性
- 安全起见，**重跑所有已完成的 variant**
- 建议不使用 `--resume`，而是重新开始一次完整实验以生成 hash

### Manifest 结构

`manifest.json` 新增 `variant_config_hashes` 字段：

```json
{
  "experiment_id": "exp_20260501_120000_my_experiment",
  "name": "my_experiment",
  "status": "running",
  "variants": ["variant_a", "variant_b"],
  "completed_variants": ["variant_a"],
  "variant_config_hashes": {
    "variant_a": "a1b2c3d4e5f6"
  },
  "test_sets": ["document"]
}
```

---

## 实验结果

实验结果保存在 `data/exp_reports/` 目录：

```
data/exp_reports/exp_20260416_120000/
├── manifest.json           # 实验元数据（含 variant_config_hashes）
├── config_snapshot.yaml    # 配置快照
├── meal_snapshot.json      # Meal 快照
├── results/                # 各 variant 结果
│   ├── variant_1.json
│   └── variant_2.json
├── checkpoints/            # 问题级断点（运行中）
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

评测系统采用 **指标预设 + 解析策略** 两层架构，用户只需选择预设即可：

```yaml
# 日常实验：core 预设
evaluation:
  backends: ["builtin"]
  llm_preset: "default"
  metrics_preset: "core"
  resolution_strategy: "priority_fallback"
  backend_priority: ["builtin", "ragas"]
```

**指标预设说明**：

| 预设 | 包含指标 | LLM 调用/题 | 适用场景 |
|------|---------|------------|---------|
| `core` | hit_rate, mrr, ndcg, recall@k, faithfulness, answer_relevancy | ~3 次 | 日常实验 |
| `extended` | core + chunk/dedup/context_precision/context_recall | ~11 次 | 深度诊断 |
| `full` | extended + fpr/diversity/answer_correctness/semantic_similarity | ~15+ 次 | 版本发布 |
| `custom` | 用户自定义 | 取决于选择 | 精细化需求 |

> 详细指标说明请参阅 [评测指标详解](evaluation-metrics.md)，预设和解析策略的完整说明请参阅 [配置参考](config-reference.md)。

**自定义指标**：如需精细控制，使用 `custom` 预设：

```yaml
evaluation:
  backends: ["builtin", "ragas"]
  metrics_preset: "custom"
  custom_metrics:
    retrieval: [hit_rate, mrr, ndcg, recall_3, recall_5, recall_10]
    generation: [faithfulness, answer_correctness]
  resolution_strategy: "priority_fallback"
  backend_priority: ["ragas", "builtin"]
```

**注意**：生成质量指标需要额外的 LLM 调用，会增加评测时间和成本。

### 使用 RAGAS 后端

在实验配置中启用 RAGAS 评测后端：

```yaml
# 双后端 + priority_fallback：重叠指标只计算一次
evaluation:
  backends: ["builtin", "ragas"]
  llm_preset: "default"
  metrics_preset: "full"
  resolution_strategy: "priority_fallback"
  backend_priority: ["builtin", "ragas"]
```

```yaml
# 双后端 + comparison：重叠指标双后端各算一次，结果加前缀区分
evaluation:
  backends: ["builtin", "ragas"]
  llm_preset: "default"
  metrics_preset: "full"
  resolution_strategy: "comparison"
```

> RAGAS 专属指标（answer_correctness, semantic_similarity）需要在 `backends` 中包含 `"ragas"` 才能生效。详见 [RAGAS 评测系统指南](ragas-evaluation.md)。

---

## 常见问题

### Q: 如何对比不同 chunk size？

A: 创建一个包含多个 variant 的配置文件，每个 variant 覆盖 `chunker.chunk_size`。

### Q: 如何复现历史实验？

A: 使用 `--reproduce` 命令，指定实验目录路径。

### Q: 如何生成更详细的分析报告？

A: 使用 `--llm-report` 参数，系统会使用 LLM 生成深度分析报告。

### Q: 增量实验时，修改了系统 config.yaml 会怎样？

A: 系统级配置的变更会影响所有 variant 的 merged config，导致 hash 变化。Resume 时系统会检测到 hash 不匹配，自动重跑受影响的 variant。这是预期行为——系统配置变更确实影响实验结果。

### Q: 只想重跑一个 variant，不想影响其他已完成的怎么办？

A: 使用 `--force-variant variant_name` 参数，只重跑指定的 variant，其他已完成的 variant 继续复用。

### Q: 旧的实验目录没有 variant_config_hashes，能 resume 吗？

A: 可以，但系统无法验证结果一致性，会发出警告并安全地重跑所有已完成的 variant。建议重新开始一次完整实验以生成 hash。

---

## 相关文档

- [评测指标详解](evaluation-metrics.md)
- [RAGAS 评测系统指南](ragas-evaluation.md)
- [Meal 系统指南](meal-system.md)
- [配置参考](config-reference.md)
