# 实验配置文件说明

本目录存放 RAG 系统的实验配置文件，用于定义自动化评测实验的参数和流程。

---

## 目录

1. [目录结构](#目录结构)
2. [模板使用指南](#模板使用指南)
3. [快速开始指南](#快速开始指南)
4. [常见实验场景示例](#常见实验场景示例)
5. [实验报告解读指南](#实验报告解读指南)
6. [LLM 报告模式使用说明](#llm-报告模式使用说明)
7. [配置文件格式](#配置文件格式)
8. [最佳实践](#最佳实践)

---

## 目录结构

```
exp_configs/
├── templates/                  # 模板文件
│   ├── _minimal.yaml          # 极简模板 - 开箱即用
│   ├── _complete.yaml         # 完整模板 - 所有选项
│   ├── _preset_chunk.yaml     # 分块实验预设
│   ├── _preset_retrieval.yaml # 检索实验预设
│   └── _preset_reranker.yaml  # 重排实验预设
├── baseline/                   # 基线实验
│   └── baseline.yaml
├── experiments/                # 正式实验
│   ├── chunk_comparison.yaml
│   ├── chunking_strategy_comparison.yaml
│   ├── retrieval_comparison.yaml
│   ├── reranker_comparison.yaml
│   ├── query_rewrite_comparison.yaml
│   └── strategy_comparison.yaml
├── smoke_tests/                # 冒烟测试
│   ├── smoke_quick.yaml       # 小冒烟测试 - 最小链路
│   └── smoke_full.yaml        # 大冒烟测试 - 全功能覆盖
└── golden_tests/               # 回归测试
    └── golden_test.yaml
```

---

## 模板使用指南

### 极简模板 (`templates/_minimal.yaml`)

**适用场景**：快速开始一个新实验，只需修改少量参数。

**使用方法**：
1. 复制 `templates/_minimal.yaml` 到目标位置
2. 修改 `name` 和 `description`
3. 根据需要调整 `data.meal`、`test_sets` 和 `variants`
4. 运行实验

### 完整模板 (`templates/_complete.yaml`)

**适用场景**：需要了解所有可配置选项，或进行复杂配置。

**包含内容**：
- 数据源配置（采样比例、随机种子）
- 问题集配置（策略、数量、类型分布）
- 变体配置（分块、Embedding、向量存储、检索方式）
- 评测配置（指标、LLM报告）
- LLM配置（问题生成、回答生成）

### 特化模板

| 模板 | 用途 |
|------|------|
| `_preset_chunk.yaml` | 分块参数对比实验 |
| `_preset_retrieval.yaml` | 检索方式对比实验 |
| `_preset_reranker.yaml` | 重排序对比实验 |

### YAML 锚点使用

当配置文件有多个变体共享部分配置时，可使用 YAML 锚点减少重复：

```yaml
# 定义共享配置
x-base-config: &base-config
  retrieval:
    method: "vector"
    top_k: 5

# 使用锚点
variants:
  - name: "variant_1"
    config_overrides:
      <<: *base-config
      chunker:
        chunk_size: 256

  - name: "variant_2"
    config_overrides:
      <<: *base-config
      chunker:
        chunk_size: 512
```

**注意**：锚点只能在同一个文件内使用，无法跨文件引用。

---

## 快速开始指南

### 前置条件

1. **环境准备**
   ```bash
   # 确保已安装 pixi
   pixi --version

   # 安装项目依赖
   pixi install
   ```

2. **配置环境变量**

   参考 `.env.example` 文件，确保以下环境变量已配置：
   - `LLM_API_KEY`: LLM API 密钥
   - `LLM_BASE_URL`: LLM API 基础 URL
   - 其他必要的 API 配置

3. **准备 PDF 文件**

   将金融研报 PDF 文件放入 `data/raw/` 目录：
   ```bash
   # 查看当前 PDF 文件
   ls data/raw/
   ```

### 第一步：创建数据集（Meal）

Meal 是数据集的抽象，包含采样后的 PDF 文件、解析结果和向量索引。

```bash
# 创建一个包含 10% PDF 的测试数据集
pixi run python main.py --create-meal --sample-ratio 0.1 --seed 42

# 或者指定具体数量
pixi run python main.py --create-meal my_dataset --sample-count 5 --seed 42

# 查看已创建的数据集
pixi run python main.py --list-meals
```

**预期输出**：
```
Name                DataID         Status           PDFs   Pages    Chunks Config               Created
-----------------------------------------------------------------------------------------------
my_dataset          abc123def456   ✅ available        5     120      847  sz=512 ov=0          2025-04-16T10:30
```

### 第二步：创建实验配置

在 `exp_configs/` 目录下创建实验配置文件 `my_first_experiment.yaml`：

```yaml
name: "my_first_experiment"
description: "我的第一个 RAG 评测实验"

data:
  meal: "my_dataset"          # 使用刚才创建的数据集
  create_if_missing:          # 如果数据集不存在则自动创建
    sample_ratio: 0.1
    seed: 42

test_sets:
  - name: "factual_test"
    on_missing: "auto"
    generation:
      strategy: "document"
      num_questions: 10
      seed: 100
      type_distribution:
        single_fact: 0.80
        multi_fact: 0.10
        reasoning: 0.05
        comparative: 0.05
        missing: 0.0
        irrelevant: 0.0
        adversarial: 0.0

variants:
  - name: "baseline"
    description: "基线配置"
    config_overrides: {}      # 使用默认配置

evaluation:
  backends: ["builtin"]
  llm_preset: "default"
  metrics:
    retrieval:
      - "hit_rate"
      - "mrr"
      - "ndcg"

llm:
  question_generation: "sonnet"
  answering: "default"
```

### 第三步：运行实验

```bash
# 运行实验
pixi run python eval/run_experiment.py --config exp_configs/my_first_experiment.yaml
```

**预期输出**：
```
2025-04-16 10:35:00 | INFO     | Loading experiment configuration from exp_configs/my_first_experiment.yaml
2025-04-16 10:35:00 | INFO     | Experiment: my_first_experiment
2025-04-16 10:35:00 | INFO     | Step 1: Preparing meal...
2025-04-16 10:35:01 | SUCCESS  | Meal 'my_dataset' is available and valid
2025-04-16 10:35:01 | INFO     | Step 2: Preparing test sets...
2025-04-16 10:35:02 | INFO     | Generating test set 'auto_factual' (factual, 10 questions)...
2025-04-16 10:35:15 | SUCCESS  | Test set 'auto_factual' generated (10 questions)
2025-04-16 10:35:15 | INFO     | Step 3: Running variant evaluations...
2025-04-16 10:35:16 | INFO     | Evaluating variant 1/1: baseline
2025-04-16 10:35:17 | INFO     | Processing question 1/10: q1
2025-04-16 10:35:18 | SUCCESS  | Question q1: HR=1.0000, MRR=1.0000, NDCG=1.0000 (1.23s)
...
2025-04-16 10:36:00 | INFO     | Step 4: Generating experiment report...
2025-04-16 10:36:01 | SUCCESS  | Experiment completed successfully: data/exp_reports/exp_20250416_103500_my_first_experiment

Experiment completed: exp_20250416_103500_my_first_experiment
Results saved to: data/exp_reports/exp_20250416_103500_my_first_experiment
```

### 第四步：查看实验报告

```bash
# 查看实验报告
cat data/exp_reports/exp_20250416_103500_my_first_experiment/experiment_report.md

# 或者在 Windows 上
type data\exp_reports\exp_20250416_103500_my_first_experiment\experiment_report.md
```

### 第五步：查看实验详情

```bash
# 列出所有实验
pixi run python eval/run_experiment.py --list

# 查看特定实验详情
pixi run python eval/run_experiment.py --info exp_20250416_103500_my_first_experiment
```

---

## 常见实验场景示例

### 场景 1：基线评测

**目的**：建立性能基准，为后续优化提供对照。

**配置文件** (`exp_configs/baseline.yaml`)：

```yaml
name: "baseline_evaluation"
description: "基线评测 - 固定长度分块，无优化"

data:
  meal: "meal_baseline"
  create_if_missing:
    sample_ratio: 0.1
    seed: 42

test_sets:
  - name: "single_fact_test"
    on_missing: "auto"
    generation:
      strategy: "document"
      num_questions: 20
      seed: 100
      type_distribution:
        single_fact: 0.80
        multi_fact: 0.10
        reasoning: 0.05
        comparative: 0.05
        missing: 0.0
        irrelevant: 0.0
        adversarial: 0.0
  - name: "multi_fact_test"
    on_missing: "auto"
    generation:
      strategy: "document"
      num_questions: 15
      seed: 101
      type_distribution:
        single_fact: 0.10
        multi_fact: 0.80
        reasoning: 0.05
        comparative: 0.05
        missing: 0.0
        irrelevant: 0.0
        adversarial: 0.0

variants:
  - name: "chunk_512_overlap_0"
    description: "chunk_size=512, overlap=0"
    config_overrides:
      chunker:
        chunk_size: 512
        chunk_overlap: 0

evaluation:
  backends: ["builtin"]
  llm_preset: "default"
  metrics:
    retrieval:
      - "hit_rate"
      - "mrr"
      - "ndcg"

llm:
  question_generation: "sonnet"
  answering: "default"
```

**运行命令**：
```bash
pixi run python eval/run_experiment.py --config exp_configs/baseline.yaml
```

**预期结果**：
- 生成基线性能指标
- 报告保存在 `data/exp_reports/exp_YYYYMMDD_HHMMSS_baseline_evaluation/`

---

### 场景 2：分块参数对比实验

**目的**：探究不同 `chunk_size` 和 `chunk_overlap` 对检索质量的影响。

**配置文件** (`exp_configs/chunk_comparison.yaml`)：

```yaml
name: "chunk_comparison"
description: "分块参数对比实验 - 探究不同 chunk_size 和 overlap 对检索质量的影响"

data:
  meal: "meal_chunk_comparison"
  create_if_missing:
    sample_ratio: 0.2
    seed: 42

test_sets:
  - name: "single_fact_test"
    on_missing: "auto"
    generation:
      strategy: "document"
      num_questions: 30
      seed: 200
      type_distribution:
        single_fact: 0.80
        multi_fact: 0.10
        reasoning: 0.05
        comparative: 0.05
        missing: 0.0
        irrelevant: 0.0
        adversarial: 0.0
  - name: "boundary_test"
    on_missing: "auto"
    generation:
      strategy: "document"
      num_questions: 25
      seed: 201
      type_distribution:
        single_fact: 0.30
        multi_fact: 0.30
        reasoning: 0.15
        comparative: 0.15
        missing: 0.10
        irrelevant: 0.0
        adversarial: 0.0
  - name: "multi_hop_test"
    on_missing: "auto"
    generation:
      strategy: "document"
      num_questions: 15
      seed: 202
      type_distribution:
        single_fact: 0.10
        multi_fact: 0.10
        reasoning: 0.60
        comparative: 0.15
        missing: 0.05
        irrelevant: 0.0
        adversarial: 0.0

variants:
  - name: "chunk_256_overlap_0"
    description: "chunk_size=256, overlap=0 (小块无重叠)"
    config_overrides:
      chunker:
        chunk_size: 256
        chunk_overlap: 0

  - name: "chunk_512_overlap_0"
    description: "chunk_size=512, overlap=0 (中块无重叠)"
    config_overrides:
      chunker:
        chunk_size: 512
        chunk_overlap: 0

  - name: "chunk_512_overlap_50"
    description: "chunk_size=512, overlap=50 (中块小重叠)"
    config_overrides:
      chunker:
        chunk_size: 512
        chunk_overlap: 50

  - name: "chunk_512_overlap_128"
    description: "chunk_size=512, overlap=128 (中块大重叠)"
    config_overrides:
      chunker:
        chunk_size: 512
        chunk_overlap: 128

  - name: "chunk_1024_overlap_0"
    description: "chunk_size=1024, overlap=0 (大块无重叠)"
    config_overrides:
      chunker:
        chunk_size: 1024
        chunk_overlap: 0

  - name: "chunk_1024_overlap_256"
    description: "chunk_size=1024, overlap=256 (大块有重叠)"
    config_overrides:
      chunker:
        chunk_size: 1024
        chunk_overlap: 256

evaluation:
  backends: ["builtin"]
  llm_preset: "default"
  metrics:
    retrieval:
      - "hit_rate"
      - "mrr"
      - "ndcg"

llm:
  question_generation: "sonnet"
  answering: "default"
```

**运行命令**：
```bash
pixi run python eval/run_experiment.py --config exp_configs/chunk_comparison.yaml
```

**预期结果**：
- 6 个变体的对比报告
- 每个变体独立创建向量索引
- 报告中包含最佳变体推荐

**分析要点**：
1. 对比不同 `chunk_size` 的 Hit Rate
2. 观察 `overlap` 对边界问题的影响
3. 权衡检索质量与索引大小

---

### 场景 3：多变体对比实验

**目的**：同时测试多个优化方向的组合效果。

**配置文件** (`exp_configs/multi_variant.yaml`)：

```yaml
name: "multi_variant_comparison"
description: "多变体对比实验 - 测试不同优化策略"

data:
  meal: "meal_multi_variant"
  create_if_missing:
    sample_ratio: 0.15
    seed: 42

test_sets:
  - name: "single_fact_test"
    on_missing: "auto"
    generation:
      strategy: "document"
      num_questions: 25
      seed: 300
      type_distribution:
        single_fact: 0.80
        multi_fact: 0.10
        reasoning: 0.05
        comparative: 0.05
        missing: 0.0
        irrelevant: 0.0
        adversarial: 0.0
  - name: "boundary_test"
    on_missing: "auto"
    generation:
      strategy: "document"
      num_questions: 20
      seed: 301
      type_distribution:
        single_fact: 0.30
        multi_fact: 0.30
        reasoning: 0.15
        comparative: 0.15
        missing: 0.10
        irrelevant: 0.0
        adversarial: 0.0
  - name: "multi_hop_test"
    on_missing: "auto"
    generation:
      strategy: "document"
      num_questions: 10
      seed: 302
      type_distribution:
        single_fact: 0.10
        multi_fact: 0.10
        reasoning: 0.60
        comparative: 0.15
        missing: 0.05
        irrelevant: 0.0
        adversarial: 0.0

variants:
  - name: "baseline"
    description: "基线配置"
    config_overrides:
      chunker:
        chunk_size: 512
        chunk_overlap: 0
      retrieval:
        top_k: 5

  - name: "larger_topk"
    description: "增加检索数量"
    config_overrides:
      retrieval:
        top_k: 10

  - name: "smaller_chunks"
    description: "更小的分块"
    config_overrides:
      chunker:
        chunk_size: 256
        chunk_overlap: 0

  - name: "overlap_chunks"
    description: "带重叠的分块"
    config_overrides:
      chunker:
        chunk_size: 512
        chunk_overlap: 50

  - name: "combined"
    description: "组合优化"
    config_overrides:
      chunker:
        chunk_size: 512
        chunk_overlap: 50
      retrieval:
        top_k: 10

evaluation:
  backends: ["builtin"]
  llm_preset: "default"
  metrics:
    retrieval:
      - "hit_rate"
      - "mrr"
      - "ndcg"

llm:
  question_generation: "sonnet"
  answering: "default"
```

**运行命令**：
```bash
pixi run python eval/run_experiment.py --config exp_configs/multi_variant.yaml
```

---

### 场景 4：实验复现

**目的**：复现已完成的实验，验证结果可重现性。

**步骤**：

1. **查看实验列表**
   ```bash
   pixi run python eval/run_experiment.py --list
   ```

2. **复现特定实验**

   ```bash
   # 完整复现（包含 PDF 哈希验证）
   pixi run python eval/run_experiment.py --reproduce data/exp_reports/exp_20250416_103500_baseline

   # 跳过哈希验证（更快）
   pixi run python eval/run_experiment.py --reproduce data/exp_reports/exp_20250416_103500_baseline --skip-hash-verification

   # 跳过所有验证
   pixi run python eval/run_experiment.py --reproduce data/exp_reports/exp_20250416_103500_baseline --skip-verification
   ```

3. **对比原实验与复现实验**
   ```bash
   pixi run python eval/run_experiment.py --compare exp_20250416_103500_baseline exp_20250416_110000_baseline_reproduced
   ```

**注意事项**：
- 复现实验会创建新的实验目录
- 由于 LLM 的随机性，结果可能略有差异
- PDF 文件必须保持不变（哈希验证）

---

### 场景 5：实验对比分析

**目的**：对比多个实验的结果，找出最佳配置。

**命令**：

```bash
# 对比多个实验（表格输出）
pixi run python eval/run_experiment.py --compare exp_001 exp_002 exp_003

# 对比并保存报告
pixi run python eval/run_experiment.py --compare exp_001 exp_002 --save-report

# 指定报告路径
pixi run python eval/run_experiment.py --compare exp_001 exp_002 --report-path notes/comparison_report.md

# JSON 格式输出
pixi run python eval/run_experiment.py --compare exp_001 exp_002 --output-format json
```

**预期输出**：
```
========================================================================================================================
EXPERIMENT COMPARISON REPORT
========================================================================================================================

------------------------------------------------------------------------------------------------------------------------
SUMMARY: BEST VARIANT PER EXPERIMENT
------------------------------------------------------------------------------------------------------------------------
Experiment                         Variant                  Hit Rate        MRR       NDCG
------------------------------------------------------------------------------------------------------------------------
baseline_evaluation                chunk_512_overlap_0        0.7500     0.6250     0.6850
chunk_comparison                   chunk_512_overlap_50       0.8200     0.7100     0.7600
multi_variant_comparison           combined                   0.8500     0.7800     0.8200
------------------------------------------------------------------------------------------------------------------------
```

---

## 实验报告解读指南

### 报告结构说明

实验报告 (`experiment_report.md`) 包含以下主要部分：

#### 1. 实验概述 (Experiment Overview)

```markdown
## 1. Experiment Overview

- **Total Variants**: 6
- **Successful Variants**: 6
- **Failed Variants**: 0
- **Data ID**: `abc123def456...`
- **Meal Name**: meal_chunk_comparison
- **Timestamp**: 2025-04-16T10:35:00
```

**解读要点**：
- `Total Variants`: 本次实验测试的配置变体数量
- `Successful/Failed Variants`: 成功/失败的变体数量
- `Data ID`: 数据集的唯一标识，用于追踪数据版本

#### 2. 变体对比表 (Variant Comparison Table)

```markdown
## 2. Variant Comparison Table

| Variant | Description | Hit Rate | MRR | NDCG | Questions | Time (s) |
|---------|-------------|----------|-----|------|-----------|----------|
| chunk_512_overlap_50 ⭐ | chunk_size=512, overlap=50 | 0.8200 | 0.7100 | 0.7600 | 70 | 125.45 |
| chunk_512_overlap_128 | chunk_size=512, overlap=128 | 0.8000 | 0.6900 | 0.7400 | 70 | 132.18 |
| chunk_512_overlap_0 | chunk_size=512, overlap=0 | 0.7500 | 0.6250 | 0.6850 | 70 | 118.32 |
| chunk_1024_overlap_256 | chunk_size=1024, overlap=256 | 0.7200 | 0.6000 | 0.6500 | 70 | 145.67 |
| chunk_1024_overlap_0 | chunk_size=1024, overlap=0 | 0.6800 | 0.5500 | 0.6000 | 70 | 138.92 |
| chunk_256_overlap_0 | chunk_size=256, overlap=0 | 0.6500 | 0.5200 | 0.5700 | 70 | 110.25 |
```

**解读要点**：
- ⭐ 标记表示最佳变体
- 按 Hit Rate 降序排列
- `Time (s)` 表示总评测时间

#### 3. 最佳变体详情 (Best Performing Variant)

```markdown
## 3. Best Performing Variant

**Variant**: chunk_512_overlap_50
**Description**: chunk_size=512, overlap=50 (中块小重叠)

**Performance Metrics**:
- Hit Rate: 0.8200
- MRR: 0.7100
- NDCG: 0.7600
- Total Questions: 70
- Total Time: 125.45s

**Configuration**:
```yaml
chunker:
  chunk_size: 512
  chunk_overlap: 50
embedding:
  model_name: BAAI/bge-large-zh-v1.5
retrieval:
  top_k: 5
```
```

### 指标含义解释

#### Hit Rate (命中率)

**定义**：检索结果中是否包含正确答案的比例。

**计算公式**：
```
Hit Rate = (包含正确答案的查询数) / (总查询数)
```

**取值范围**：0.0 ~ 1.0

**解读标准**：
| 范围 | 评价 | 说明 |
|------|------|------|
| ≥ 0.8 | 优秀 | 大多数查询都能找到相关文档 |
| 0.6 ~ 0.8 | 良好 | 多数查询能找到相关文档 |
| 0.4 ~ 0.6 | 中等 | 部分查询能找到相关文档 |
| < 0.4 | 需改进 | 很多查询无法找到相关文档 |

**优化建议**：
- 增大 `top_k` 值
- 改进 Embedding 模型
- 考虑混合检索（BM25 + 向量）

#### MRR (Mean Reciprocal Rank, 平均倒数排名)

**定义**：正确答案在检索结果中排名的倒数平均值。

**计算公式**：
\```
MRR = (1/N) * Σ(1 / rank_i)
\```

**取值范围**：0.0 ~ 1.0

**解读标准**：
| 范围 | 评价 | 说明 |
|------|------|------|
| ≥ 0.7 | 优秀 | 相关文档通常排在前列 |
| 0.5 ~ 0.7 | 良好 | 相关文档排名较靠前 |
| 0.3 ~ 0.5 | 中等 | 相关文档排名中等 |
| < 0.3 | 需改进 | 相关文档排名靠后 |

**优化建议**：
- 添加 Reranker 重排
- 改进查询理解
- 优化 Embedding 质量

#### NDCG (Normalized Discounted Cumulative Gain, 归一化折损累积增益)

**定义**：考虑排序位置的检索质量指标，位置越靠前权重越高。

**计算公式**：
\```
DCG = Σ(rel_i / log2(i + 1))
NDCG = DCG / IDCG
\```

**取值范围**：0.0 ~ 1.0

**解读标准**：
| 范围 | 评价 | 说明 |
|------|------|------|
| ≥ 0.7 | 优秀 | 排序质量很高 |
| 0.5 ~ 0.7 | 良好 | 排序质量较好 |
| 0.3 ~ 0.5 | 中等 | 排序质量一般 |
| < 0.3 | 需改进 | 排序质量较差 |

**优化建议**：
- 综合考虑 Hit Rate 和 MRR 的优化策略
- 关注边界情况的处理

### 如何分析结果

#### 1. 整体性能评估

```markdown
### Performance Analysis

- **Hit Rate (0.8200)**: Excellent retrieval performance.
- **MRR (0.7100)**: Excellent ranking quality.
- **NDCG (0.7600)**: Overall ranking quality metric.
```

**分析步骤**：
1. 首先看 Hit Rate，判断是否能找到相关文档
2. 然后看 MRR，判断相关文档的排名
3. 最后看 NDCG，综合评估排序质量

#### 2. 变体对比分析

**关键问题**：
1. 哪个变体表现最好？为什么？
2. 不同参数如何影响性能？
3. 是否存在性能与效率的权衡？

**分析方法**：
```bash
# 对比两个变体的详细结果
diff data/exp_reports/exp_xxx/results/variant_1.json data/exp_reports/exp_xxx/results/variant_2.json
```

#### 3. 问题类型分析

报告会按问题类型（category）分组展示指标：

```markdown
### Results by Question Category

| Category | Count | Avg Hit Rate | Avg MRR | Avg NDCG |
|----------|-------|--------------|---------|----------|
| factual  | 30    | 0.8500       | 0.7500  | 0.8000   |
| boundary | 25    | 0.7200       | 0.6000  | 0.6500   |
| multi-hop | 15    | 0.6000       | 0.5000  | 0.5500   |
```

**分析要点**：
- `factual` 问题通常表现最好
- `boundary` 问题受分块策略影响大
- `multi-hop` 问题需要综合多个文档

### 如何根据结果优化

#### 1. 低 Hit Rate 优化路径

```
Hit Rate < 0.6
    ├── 增加 top_k (5 → 10 → 20)
    ├── 改进 Embedding 模型
    │   ├── 使用领域专用模型
    │   └── 微调现有模型
    └── 考虑混合检索
        ├── BM25 + 向量
        └── 多路召回
```

#### 2. 低 MRR 优化路径

```
MRR < 0.5
    ├── 添加 Reranker
    │   ├── Cross-Encoder
    │   └── 领域专用 Reranker
    ├── 优化分块策略
    │   ├── 调整 chunk_size
    │   └── 增加 overlap
    └── 改进查询理解
        ├── 查询改写
        └── 查询扩展
```

#### 3. 边界问题优化

```
Boundary 问题表现差
    ├── 增加 chunk_overlap
    ├── 使用语义分块
    └── 考虑父子 chunk 策略
```

---

## LLM 报告模式使用说明

### 何时使用 LLM 报告模式

**适用场景**：
1. **需要深度分析**：LLM 可以提供更深入的分析和见解
2. **复杂实验**：多变体对比实验需要综合分析
3. **报告展示**：需要更专业、更易读的报告格式
4. **优化建议**：需要具体的、针对性的优化建议

**不适用场景**：
1. **快速迭代**：需要快速查看结果时，模板报告更快
2. **成本敏感**：LLM 调用会产生额外 API 费用
3. **离线环境**：无法访问 LLM API 的环境

### 如何启用 LLM 报告模式

#### 方法 1：命令行参数

```bash
# 使用 LLM 生成报告
pixi run python eval/run_experiment.py --config exp_configs/baseline.yaml --llm-report
```

#### 方法 2：配置文件（未来支持）

```yaml
evaluation:
  llm_preset: "default"
  report_mode: "llm"  # 或 "template"
  metrics:
    retrieval:
      - "hit_rate"
      - "mrr"
      - "ndcg"
```

### LLM 报告的特点

#### 1. 结构化分析

LLM 报告包含以下结构化分析：

```markdown
### 1. 实验概述
- 描述实验目的和假设
- 解释评测的意义

### 2. 数据来源分析
- 分析数据特征
- 讨论数据对结果的潜在影响

### 3. 技术选型分析
- 评估所选技术和模型
- 讨论潜在优势和局限性

### 4. 评测结果分析
- 解读检索指标（Hit Rate, MRR, NDCG）
- 分析不同问题类型的性能模式
- 识别潜在瓶颈或问题

### 5. 结论与建议
- 总结关键发现
- 提供可操作的改进建议
- 建议下一步优化方向
```

#### 2. 深度洞察

LLM 报告会提供：
- 数据特征与性能的关联分析
- 技术选型的优劣势分析
- 具体问题的根因分析
- 针对性的优化建议

#### 3. 专业表达

LLM 报告使用更专业、更流畅的表达方式，适合：
- 技术文档归档
- 团队分享
- 项目汇报

### 与程序模板报告的区别

| 特性 | 程序模板报告 | LLM 报告 |
|------|-------------|----------|
| 生成速度 | 快（毫秒级） | 慢（秒级） |
| 成本 | 无额外成本 | 有 API 调用成本 |
| 分析深度 | 基础统计 | 深度分析 |
| 建议质量 | 通用建议 | 针对性建议 |
| 可定制性 | 需修改代码 | 可通过 Prompt 调整 |
| 适用场景 | 快速迭代、自动化流程 | 深度分析、报告展示 |

### 示例对比

#### 程序模板报告片段

```markdown
## 7. Conclusions and Recommendations

### Performance Summary

- **Hit Rate (0.7500)**: Good - Majority of relevant documents are being retrieved.
- **MRR (0.6250)**: Good - Relevant documents appear reasonably early.
- **NDCG (0.6850)**: Ranking quality assessment.

### Recommendations

1. Consider increasing `top_k` to retrieve more candidates.
2. Evaluate embedding model quality for domain-specific content.
3. Consider adding a reranker to improve ranking.
```

#### LLM 报告片段

```markdown
## 4. 评测结果分析

### 4.1 整体性能解读

本次实验的 Hit Rate 为 0.75，表明系统在 75% 的查询中成功检索到了相关文档。这是一个良好的基线表现，但仍存在 25% 的查询未能找到相关内容，需要进一步优化。

### 4.2 问题类型分析

从不同问题类型的表现来看：
- **事实性问题 (Hit Rate: 0.85)**：表现最佳，说明系统对单一文档的信息提取能力较强
- **边界问题 (Hit Rate: 0.65)**：表现中等，可能受分块策略影响，部分跨块信息未能有效关联
- **复杂问题 (Hit Rate: 0.55)**：表现较弱，需要综合多个文档信息的能力有待提升

### 4.3 潜在瓶颈

1. **分块粒度**：当前 chunk_size=512 可能对边界问题不够友好
2. **检索深度**：top_k=5 可能限制了召回率
3. **语义理解**：Embedding 模型对金融领域专业术语的理解可能不够深入

## 5. 结论与建议

### 5.1 关键发现

1. 基线配置在事实性问题上表现良好，但在复杂问题上存在明显短板
2. 边界问题受分块策略影响较大，需要针对性优化
3. 当前配置在效率与效果之间取得了较好的平衡

### 5.2 优化建议

**短期优化（预期提升 5-10%）**：
1. 将 top_k 从 5 增加到 10，提升召回率
2. 增加 chunk_overlap 到 50，改善边界问题表现

**中期优化（预期提升 10-20%）**：
1. 引入 Reranker 模型，提升排序质量
2. 考虑使用金融领域专用 Embedding 模型

**长期优化（预期提升 20%+）**：
1. 实施混合检索策略（BM25 + 向量）
2. 探索语义分块和父子 chunk 策略
```

### 最佳实践

1. **先用模板，后用 LLM**
   - 开发阶段使用模板报告快速迭代
   - 最终评测使用 LLM 报告生成深度分析

2. **保存两种报告**
   ```bash
   # 先生成模板报告
   pixi run python eval/run_experiment.py --config exp_configs/baseline.yaml

   # 再生成 LLM 报告（使用不同文件名）
   # 注意：当前版本会覆盖，建议手动备份
   ```

3. **结合使用**
   - 模板报告用于数据查询和对比
   - LLM 报告用于深度分析和展示

---

## 配置文件格式

实验配置文件采用 YAML 格式，包含以下主要字段：

### 1. 基本信息

```yaml
name: "experiment_name"           # 实验名称（必填）
description: "实验描述信息"         # 实验描述（可选）
```

### 2. 数据源配置 (data)

```yaml
data:
  meal: "meal_name"               # 使用的 meal 名称
  create_if_missing:              # 如果 meal 不存在时的创建参数
    sample_ratio: 0.1             # PDF 采样比例（0.0-1.0）
    seed: 42                      # 随机种子
```

**字段说明**：
- `meal`: 指定使用的预处理数据集名称。如果不存在，系统会根据 `create_if_missing` 参数自动创建。
- `sample_ratio`: 从原始 PDF 中采样的比例，用于快速实验。
- `seed`: 随机种子，确保实验可复现。

### 3. 问题集配置 (test_sets)

```yaml
test_sets:
  - name: "golden_test"
    on_missing: "auto"
    generation:
      strategy: "document"
      num_questions: 20
      seed: 100
      type_distribution:
        single_fact: 0.30
        multi_fact: 0.25
        reasoning: 0.15
        comparative: 0.15
        missing: 0.10
        irrelevant: 0.05
  - name: "golden_test_2"
    on_missing: "auto"
    generation:
      strategy: "document"
      num_questions: 15
      seed: 101
      type_distribution:
        single_fact: 0.10
        multi_fact: 0.80
        reasoning: 0.05
        comparative: 0.05
        missing: 0.0
        irrelevant: 0.0
```

**支持的生成策略**：
- `document`: 基于完整文档生成问题（推荐）
  - 通过 `type_distribution` 控制问题类型分布
  - 类型包括：`single_fact`（单知识点）、`multi_fact`（多知识点）、`reasoning`（推理）、`comparative`（对比）、`missing`（缺失）、`irrelevant`（无关）

**命名规范**：
- 每个 test set 必须有 `name` 字段
- `on_missing` 控制查找失败时的行为：`auto` / `clean_only` / `strict`

### 4. 超参数变体 (variants)

```yaml
variants:
  - name: "variant_name"          # 变体名称
    description: "变体描述"        # 变体描述
    config_overrides:             # 配置覆盖项
      chunker:
        chunk_size: 512
        chunk_overlap: 0
```

**说明**：
- 可以定义多个变体，系统会为每个变体独立运行评测。
- `config_overrides` 中的配置会覆盖 `config.yaml` 中的默认配置。
- 每个变体会创建独立的向量索引，避免相互干扰。

### 5. 评测配置 (evaluation)

```yaml
evaluation:
  llm_preset: "default"           # 用于回答生成的 LLM preset
  metrics:
    retrieval:                    # 检索质量指标
      - "hit_rate"
      - "mrr"
      - "ndcg"
    generation:                   # 生成质量指标（未来扩展）
      - "faithfulness"
      - "answer_relevancy"
```

**支持的指标**：
- `hit_rate`: 命中率，检索结果中是否包含正确答案
- `mrr`: 平均倒数排名
- `ndcg`: 归一化折损累积增益

### 6. LLM 配置 (llm)

```yaml
llm:
  question_generation: "sonnet"   # 用于问题生成的 LLM preset
  answering: "default"            # 用于回答生成的 LLM preset
```

**说明**：
- 使用 `config.yaml` 中定义的 `llm_presets`。
- 不同任务可以使用不同的 LLM 配置。

---

## 最佳实践

### 1. 命名规范

- 实验名称使用小写字母和下划线：`baseline_evaluation`、`chunk_comparison`
- 变体名称清晰描述配置差异：`chunk_512_overlap_0`

### 2. 实验设计

- **单变量原则**：每次实验只改变一个变量，便于分析影响
- **对照组设置**：保留一个基线配置作为对照
- **合理的样本量**：问题数量建议 20-50 个，太少不具代表性，太多耗时过长

### 3. 配置管理

- 将实验配置文件纳入版本控制
- 使用有意义的文件名描述实验目的
- 在 `description` 字段中记录实验假设和目的

### 4. 结果验证

- 使用相同的 `seed` 确保可复现性
- 多次运行验证结果的稳定性
- 对比实验前后保存配置快照

---

## 配置继承机制

实验配置与系统配置 (`config.yaml`) 采用继承机制：

1. 系统加载 `config.yaml` 作为基础配置
2. 加载实验配置文件
3. 将实验配置中的 `config_overrides` 覆盖到基础配置
4. 未指定的配置项使用系统默认值

**示例**：

```yaml
# config.yaml 中的默认配置
chunker:
  chunk_size: 512
  chunk_overlap: 0
  input_dir: "data/parsed"
  output_dir: "data/chunks"

# 实验配置中的覆盖
variants:
  - config_overrides:
      chunker:
        chunk_overlap: 50  # 只覆盖 overlap

# 最终生效的配置
chunker:
  chunk_size: 512          # 继承自 config.yaml
  chunk_overlap: 50        # 被实验配置覆盖
  input_dir: "data/parsed" # 继承自 config.yaml
  output_dir: "data/chunks"# 继承自 config.yaml
```

---

## 实验报告输出

实验完成后，系统会在 `data/exp_reports/` 目录下生成实验报告：

```
data/exp_reports/
└── exp_20250416_120000_baseline/
    ├── manifest.json              # 实验元数据
    ├── config_snapshot.yaml       # 完整配置快照
    ├── meal_snapshot.json         # Meal manifest 快照
    ├── test_sets/                 # 问题集快照
    │   ├── factual.json
    │   └── boundary.json
    ├── results/                   # 评测结果
    │   └── variant_chunk_512_overlap_0.json
    └── experiment_report.md       # 人类可读的实验报告
```

---

## 常见问题

### Q: 如何创建新的实验配置？

A: 复制现有的配置文件，修改 `name`、`description` 和相关参数即可。

### Q: 实验运行失败怎么办？

A: 检查以下几点：
1. PDF 文件是否存在于 `data/raw/` 目录
2. LLM API 配置是否正确（检查 `.env` 文件）
3. 依赖服务（Qdrant）是否正常运行

### Q: 如何对比多个实验的结果？

A: 使用 `--compare` 命令：
```bash
pixi run python eval/run_experiment.py --compare exp_001 exp_002 exp_003
```

### Q: 实验配置中的 seed 有什么作用？

A: `seed` 用于确保实验的可复现性：
- `data.create_if_missing.seed`: 控制 PDF 采样的随机性
- `test_sets[].seed`: 控制问题生成的随机性
- 使用相同的 seed 可以复现完全相同的实验

### Q: LLM 报告模式需要额外配置吗？

A: 不需要额外配置，只需添加 `--llm-report` 参数。系统会使用 `config.yaml` 中 `default` preset 的 API 配置。

---

## 更多信息

详细的系统设计请参考：
- [实验系统设计文档](../.trae/specs/automate-evaluation/spec.md)
- [项目开发规范](../CLAUDE.md)
