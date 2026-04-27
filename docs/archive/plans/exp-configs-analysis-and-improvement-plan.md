# exp\_configs 配置文件分析与改进计划

## 一、配置文件清单与分析

### 1. 基线类配置

| 文件名                  | 用途           | 数据集                    | 问题数 | 变体数 | LLM配置            |
| -------------------- | ------------ | ---------------------- | --- | --- | ---------------- |
| `baseline.yaml`      | 基线评测         | meal\_baseline (10%采样) | 35  | 1   | sonnet/default混合 |
| `baseline_v01x.yaml` | v0.1.x版本基线评测 | test1 (5%采样)           | 35  | 1   | 全default         |

**问题**：两个基线配置功能相似，主要差异是LLM配置，可合并为一个全default版本。

### 2. 分块参数实验

| 文件名                                 | 用途         | 数据集                                          | 问题数 | 变体数 | LLM配置            |
| ----------------------------------- | ---------- | -------------------------------------------- | --- | --- | ---------------- |
| `chunk_comparison.yaml`             | 分块参数对比（正式） | meal\_chunk\_comparison (20%采样)              | 50  | 6   | 全default         |
| `chunk_smoke_test.yaml`             | 分块参数冒烟测试   | meal\_chunk\_smoke\_test (10%采样)             | 5   | 6   | 全default         |
| `chunking_strategy_comparison.yaml` | 固定分块vs语义分块 | meal\_chunking\_strategy\_comparison (20%采样) | 65  | 4   | sonnet/default混合 |

**特点**：设计合理，但LLM配置不一致。

### 3. 检索方式实验

| 文件名                             | 用途                   | 数据集                                      | 问题数 | 变体数 | LLM配置            |
| ------------------------------- | -------------------- | ---------------------------------------- | --- | --- | ---------------- |
| `retrieval_comparison.yaml`     | BM25/Vector/Hybrid对比 | meal\_retrieval\_comparison (20%采样)      | 65  | 5   | sonnet/default混合 |
| `reranker_comparison.yaml`      | Cross-Encoder重排对比    | meal\_reranker\_comparison (20%采样)       | 65  | 4   | sonnet/default混合 |
| `query_rewrite_comparison.yaml` | HyDE/Multi-Query对比   | meal\_query\_rewrite\_comparison (20%采样) | 65  | 4   | sonnet/default混合 |

**特点**：覆盖检索优化主要方向，但LLM配置不一致。

### 4. 测试类配置

| 文件名                        | 用途               | 数据集                 | 问题数 | 变体数 | LLM配置    |
| -------------------------- | ---------------- | ------------------- | --- | --- | -------- |
| `smoke_test_v017.yaml`     | v0.1.7新功能冒烟测试    | test1 (5%采样)        | 1   | 8   | 全default |
| `quicktest111_v01x.yaml`   | v0.1.x快速冒烟测试     | test1 (5%采样)        | 3   | 1   | 全default |
| `golden_test.yaml`         | 回归测试Golden Suite | golden\_test (3%采样) | 10  | 1   | 无LLM配置   |
| `test_llm_report_321.yaml` | LLM报告功能测试        | test1 (5%采样)        | 6   | 1   | 全default |

**问题**：冒烟测试配置过多，功能重叠，需要整合为大小两种。

### 5. 策略对比实验

| 文件名                        | 用途         | 数据集                                | 问题数 | 变体数 | LLM配置    |
| -------------------------- | ---------- | ---------------------------------- | --- | --- | -------- |
| `strategy_comparison.yaml` | 新旧问题生成策略对比 | meal\_strategy\_comparison (15%采样) | 30  | 1   | 全default |

***

## 二、发现的问题

### 问题1：LLM配置不一致

* 部分配置使用 `question_generation: "sonnet"`

* 部分配置使用 `question_generation: "default"`

* 实际环境只配置了 `default`，sonnet版本无法运行

**解决方案**：统一使用 `default`，在模板中以注释说明可更换。

### 问题2：配置冗余

* `baseline.yaml` 和 `baseline_v01x.yaml` 功能相似，仅LLM配置不同

* `smoke_test_v017.yaml`、`quicktest111_v01x.yaml`、`test_llm_report_321.yaml` 都是冒烟测试，存在重叠

**解决方案**：合并冗余配置，统一使用default。

### 问题3：缺少模板文件体系

* 没有极简模板供快速上手

* 没有完整模板供参考所有选项

* 没有特化模板供常见实验参考

**解决方案**：建立三层模板体系。

### 问题4：冒烟测试设计不合理

* 当前有多个冒烟测试，职责不清

* 缺少"大冒烟"（全功能覆盖）和"小冒烟"（最小链路）的区分

**解决方案**：重新设计大小两种冒烟测试。

### 问题5：YAML锚点的实际价值

**锚点的局限性**：
* YAML锚点只能在**同一个文件内**复用配置片段
* 无法跨文件引用（需要工具链支持如 `!include` 标签）
* 在单个配置文件内，锚点只是把配置"挪了个位置"，总行数不会减少

**锚点的真正价值**：
* 当有**多个变体**共享部分配置时，避免重复写相同字段
* 修改时只需改一处，所有引用处自动生效

```yaml
# 没有锚点：每个变体都要重复写 retrieval 基础配置
variants:
  - name: "baseline"
    config_overrides:
      retrieval:
        method: "vector"
        top_k: 5

  - name: "with_reranker"
    config_overrides:
      retrieval:
        method: "vector"    # 重复
        top_k: 5            # 重复
        reranker:
          enabled: true

# 有锚点：基础配置只写一次
x-base-retrieval: &base-retrieval
  method: "vector"
  top_k: 5

variants:
  - name: "baseline"
    config_overrides:
      retrieval: *base-retrieval

  - name: "with_reranker"
    config_overrides:
      retrieval:
        <<: *base-retrieval
        reranker:
          enabled: true
```

**结论**：锚点适合变体较多的配置（如 chunk_comparison.yaml 有 6 个变体），对于单变体配置价值不大。

***

## 三、改进方案

### 方案1：建立三层模板体系

```
exp_configs/
├── templates/                      # 模板目录
│   ├── _minimal.yaml              # 极简模板 - 开箱即用
│   ├── _complete.yaml             # 完整模板 - 所有选项
│   ├── _preset_chunk.yaml         # 特化模板 - 分块实验
│   ├── _preset_retrieval.yaml     # 特化模板 - 检索实验
│   └── _preset_reranker.yaml      # 特化模板 - 重排实验
```

#### 极简模板 (`_minimal.yaml`)

设计原则：

* 最少必填项，复制即用

* 只需修改 `name` 和 `description` 即可运行

* 使用合理的默认值

```yaml
name: "my_experiment"              # 必填：实验名称
description: "实验描述"             # 必填：实验描述

data:
  meal: "my_meal"                  # 数据集名称
  create_if_missing:
    sample_ratio: 0.1              # 采样比例
    seed: 42

test_sets:
  - strategy: "document"
    num_questions: 10

variants:
  - name: "baseline"
    description: "基线配置"
    config_overrides: {}

evaluation:
  llm_preset: "default"
  metrics:
    retrieval:
      - "hit_rate"
      - "mrr"
      - "ndcg"
    generation:
      - "faithfulness"
      - "answer_relevancy"

llm:
  question_generation: "default"   # 可选：更换为 "sonnet" 等
  answering: "default"
```

#### 完整模板 (`_complete.yaml`)

设计原则：

* 展示所有可能的配置选项

* 详细注释说明每个字段

* 供用户参考扩容

```yaml
# ============================================================
# 完整实验配置模板 - 展示所有可用选项
# ============================================================

name: "complete_template"
description: "完整配置模板 - 包含所有可用选项的示例"

# ------------------------------------------------------------
# 数据源配置
# ------------------------------------------------------------
data:
  meal: "my_meal"                  # 数据集名称
  create_if_missing:               # 如果数据集不存在则自动创建
    sample_ratio: 0.1              # PDF采样比例 (0.0-1.0)
    sample_count: null             # 或指定具体数量（与sample_ratio二选一）
    seed: 42                       # 随机种子，确保可复现

# ------------------------------------------------------------
# 问题集配置
# ------------------------------------------------------------
test_sets:
  - strategy: "document"           # 问题生成策略
    num_questions: 20              # 问题数量
    seed: 100                      # 随机种子
    type_distribution:             # 问题类型分布（可选）
      single_fact: 0.30            # 单知识点
      multi_fact: 0.25             # 多知识点
      reasoning: 0.15              # 推理型
      comparative: 0.15            # 对比型
      missing: 0.10                # 缺失信息
      irrelevant: 0.05             # 无关问题

# ------------------------------------------------------------
# 变体配置 - 核心实验参数
# ------------------------------------------------------------
variants:
  - name: "baseline"
    description: "基线配置"
    config_overrides: {}

  - name: "custom_chunk"
    description: "自定义分块配置"
    config_overrides:
      chunker:
        strategy: "fixed"          # fixed | semantic
        chunk_size: 512
        chunk_overlap: 50
        # 语义分块额外配置（strategy: semantic时）
        semantic:
          similarity_threshold: 0.5
          min_chunk_size: 100
          breakpoint_percentile: 25

  - name: "custom_embedding"
    description: "自定义Embedding配置"
    config_overrides:
      embedding:
        model_name: "BAAI/bge-large-zh-v1.5"  # Embedding模型名称
        device: "cuda"                         # 运行设备: cuda | cpu
        batch_size: 32                         # 批处理大小

  - name: "custom_vector_store"
    description: "自定义向量存储配置"
    config_overrides:
      vector_store:
        type: "qdrant"               # 向量存储类型
        collection_name: "my_collection"
        persist_dir: "data/vector_store"
        distance: "Cosine"           # 距离度量: Cosine | Euclidean | Dot

  - name: "hybrid_retrieval"
    description: "混合检索配置"
    config_overrides:
      retrieval:
        method: "hybrid"           # vector | bm25 | hybrid
        top_k: 5
        bm25:                      # BM25参数（method: bm25 或 hybrid时）
          k1: 1.5                  # 词频饱和参数
          b: 0.75                  # 长度归一化参数
        hybrid:                    # 混合检索参数（method: hybrid时）
          fusion: "rrf"            # rrf | weighted
          rrf_k: 60                # RRF融合参数
          vector_weight: 0.7       # 加权融合参数
          bm25_weight: 0.3
        reranker:
          enabled: true
          model_name: "BAAI/bge-reranker-large"
          top_n: 3
        query_rewrite:
          enabled: true
          strategy: "hyde"         # hyde | multi_query
          num_queries: 3           # multi_query时的子查询数

# ------------------------------------------------------------
# 评测配置
# ------------------------------------------------------------
evaluation:
  llm_preset: "default"
  llm_report: false                # 是否生成LLM报告
  metrics:
    retrieval:
      - "hit_rate"
      - "mrr"
      - "ndcg"
    generation:
      - "faithfulness"
      - "answer_relevancy"

# ------------------------------------------------------------
# LLM配置
# ------------------------------------------------------------
llm:
  question_generation: "default"   # 问题生成LLM preset
  answering: "default"             # 回答生成LLM preset
  # 可选preset: default, sonnet, ...（根据config.yaml中的定义）
```

### 方案2：设计大小两种冒烟测试

#### 小冒烟测试 (`smoke_quick.yaml`)

设计原则：

* 最小链路，快速验证

* 节约token，适合调试时反复跑

* 能识别明显异常（指标为0、宕机等）

```yaml
name: "smoke_quick"
description: "快速冒烟测试 - 最小链路验证，用于调试时快速检查"

data:
  meal: "smoke_quick"
  create_if_missing:
    sample_ratio: 0.03
    seed: 42

test_sets:
  - strategy: "document"
    num_questions: 1

variants:
  - name: "baseline"
    description: "基线配置 - 验证基本流程"
    config_overrides: {}

evaluation:
  llm_preset: "default"
  metrics:
    retrieval:
      - "hit_rate"
      - "mrr"
      - "ndcg"
    generation:
      - "faithfulness"
      - "answer_relevancy"

llm:
  question_generation: "default"
  answering: "default"
```

#### 大冒烟测试 (`smoke_full.yaml`)

设计原则：

* 覆盖所有可选实验项

* 覆盖所有问题类型

* 测试两种报告功能

* token花销较高，用于发布前验证

```yaml
name: "smoke_full"
description: "完整冒烟测试 - 覆盖所有功能，用于发布前验证"

data:
  meal: "smoke_full"
  create_if_missing:
    sample_ratio: 0.05
    seed: 42

test_sets:
  - strategy: "document"
    num_questions: 6
    type_distribution:
      single_fact: 0.20
      multi_fact: 0.20
      reasoning: 0.15
      comparative: 0.15
      missing: 0.15
      irrelevant: 0.15

variants:
  - name: "baseline"
    description: "基线配置"
    config_overrides: {}

  - name: "bm25"
    description: "BM25稀疏检索"
    config_overrides:
      retrieval:
        method: "bm25"
        top_k: 5

  - name: "hybrid_rrf"
    description: "混合检索 - RRF融合"
    config_overrides:
      retrieval:
        method: "hybrid"
        top_k: 5
        hybrid:
          fusion: "rrf"
          rrf_k: 60

  - name: "reranker"
    description: "向量检索 + Cross-Encoder重排"
    config_overrides:
      retrieval:
        method: "vector"
        top_k: 5
        reranker:
          enabled: true
          model_name: "BAAI/bge-reranker-large"
          top_n: 3

  - name: "hyde"
    description: "HyDE查询改写"
    config_overrides:
      retrieval:
        method: "vector"
        top_k: 5
        query_rewrite:
          enabled: true
          strategy: "hyde"

  - name: "multi_query"
    description: "Multi-Query查询改写"
    config_overrides:
      retrieval:
        method: "vector"
        top_k: 5
        query_rewrite:
          enabled: true
          strategy: "multi_query"
          num_queries: 3

  - name: "semantic_chunk"
    description: "语义分块策略"
    config_overrides:
      chunker:
        strategy: "semantic"
        chunk_size: 512
        semantic:
          similarity_threshold: 0.5
          min_chunk_size: 100

evaluation:
  llm_preset: "default"
  llm_report: true                 # 测试LLM报告功能
  metrics:
    retrieval:
      - "hit_rate"
      - "mrr"
      - "ndcg"
    generation:
      - "faithfulness"
      - "answer_relevancy"

llm:
  question_generation: "default"
  answering: "default"
```

### 方案3：YAML锚点实现配置复用

**适用场景**：当一个配置文件有多个变体（variants）共享部分配置时，锚点可以减少重复。

**示例：分块参数对比实验（6个变体）**

```yaml
# 定义共享的基础配置锚点
x-base-config: &base-config
  retrieval:
    method: "vector"
    top_k: 5

# 使用锚点简化变体定义
variants:
  - name: "chunk_256_overlap_0"
    description: "small chunk, no overlap"
    config_overrides:
      <<: *base-config
      chunker:
        chunk_size: 256
        chunk_overlap: 0

  - name: "chunk_256_overlap_32"
    description: "small chunk, small overlap"
    config_overrides:
      <<: *base-config
      chunker:
        chunk_size: 256
        chunk_overlap: 32

  - name: "chunk_1024_overlap_0"
    description: "large chunk, no overlap"
    config_overrides:
      <<: *base-config
      chunker:
        chunk_size: 1024
        chunk_overlap: 0

  # ... 更多变体
```

**注意**：锚点只能在同一个文件内使用，无法跨文件引用。如需跨文件复用，需要实现配置预处理工具。

### 方案4：清理后的配置文件结构

```
exp_configs/
├── README.md
├── templates/                      # 模板目录
│   ├── _minimal.yaml              # 极简模板
│   ├── _complete.yaml             # 完整模板
│   ├── _preset_chunk.yaml         # 分块实验预设
│   ├── _preset_retrieval.yaml     # 检索实验预设
│   └── _preset_reranker.yaml      # 重排实验预设
├── baseline/                       # 基线实验
│   └── baseline.yaml              # 统一的基线配置
├── experiments/                    # 正式实验
│   ├── chunk_comparison.yaml
│   ├── chunking_strategy_comparison.yaml
│   ├── retrieval_comparison.yaml
│   ├── reranker_comparison.yaml
│   └── query_rewrite_comparison.yaml
├── smoke_tests/                    # 冒烟测试
│   ├── smoke_quick.yaml           # 小冒烟测试
│   └── smoke_full.yaml            # 大冒烟测试
└── golden_tests/                   # 回归测试
    └── golden_test.yaml
```

***

## 四、实施步骤

### 步骤1：创建模板文件体系

1. 创建 `templates/` 目录
2. 创建 `_minimal.yaml` 极简模板
3. 创建 `_complete.yaml` 完整模板
4. 创建 `_preset_*.yaml` 特化模板

### 步骤2：重新设计冒烟测试

1. 创建 `smoke_tests/` 目录
2. 创建 `smoke_quick.yaml` 小冒烟测试
3. 创建 `smoke_full.yaml` 大冒烟测试

### 步骤3：整理现有配置

1. 创建 `baseline/` 目录，合并两个baseline配置
2. 创建 `experiments/` 目录，移动正式实验配置
3. 创建 `golden_tests/` 目录，移动golden\_test配置
4. 统一所有配置的LLM设置为 `default`

### 步骤4：更新文档

1. 更新 README.md 添加模板使用说明
2. 添加配置继承机制说明
3. 添加命名规范

### 步骤5：清理冗余文件

1. 删除 `baseline_v01x.yaml`（已合并）
2. 删除 `quicktest111_v01x.yaml`（已合并到smoke\_quick）
3. 删除 `test_llm_report_321.yaml`（已合并到smoke\_full）
4. 删除 `smoke_test_v017.yaml`（已被smoke\_full替代）
5. 删除 `chunk_smoke_test.yaml`（功能被smoke测试覆盖）

***

## 五、预期效果

| 改进项   | 改进前              | 改进后           |
| ----- | ---------------- | ------------- |
| 模板体系  | 无模板，需参考现有配置      | 三层模板：极简/完整/特化 |
| 冒烟测试  | 4个重叠的测试配置        | 2个职责清晰的测试     |
| LLM配置 | 混用sonnet/default | 统一使用default   |
| 目录结构  | 平铺，无分类           | 按用途分类组织       |
| 配置复用  | 无机制              | YAML锚点（多变体场景） |
| 配置数量  | 13个              | 11个（减少冗余）     |

***

## 六、文件变更清单

### 新建文件

| 文件路径                               | 说明     |
| ---------------------------------- | ------ |
| `templates/_minimal.yaml`          | 极简模板   |
| `templates/_complete.yaml`         | 完整模板   |
| `templates/_preset_chunk.yaml`     | 分块实验预设 |
| `templates/_preset_retrieval.yaml` | 检索实验预设 |
| `templates/_preset_reranker.yaml`  | 重排实验预设 |
| `smoke_tests/smoke_quick.yaml`     | 小冒烟测试  |
| `smoke_tests/smoke_full.yaml`      | 大冒烟测试  |

### 移动文件

| 原路径                                 | 新路径                                             |
| ----------------------------------- | ----------------------------------------------- |
| `baseline.yaml`                     | `baseline/baseline.yaml`                        |
| `chunk_comparison.yaml`             | `experiments/chunk_comparison.yaml`             |
| `chunking_strategy_comparison.yaml` | `experiments/chunking_strategy_comparison.yaml` |
| `retrieval_comparison.yaml`         | `experiments/retrieval_comparison.yaml`         |
| `reranker_comparison.yaml`          | `experiments/reranker_comparison.yaml`          |
| `query_rewrite_comparison.yaml`     | `experiments/query_rewrite_comparison.yaml`     |
| `strategy_comparison.yaml`          | `experiments/strategy_comparison.yaml`          |
| `golden_test.yaml`                  | `golden_tests/golden_test.yaml`                 |

### 删除文件

| 文件路径                       | 删除原因                 |
| -------------------------- | -------------------- |
| `baseline_v01x.yaml`       | 与baseline.yaml合并     |
| `quicktest111_v01x.yaml`   | 合并到smoke\_quick.yaml |
| `test_llm_report_321.yaml` | 合并到smoke\_full.yaml  |
| `smoke_test_v017.yaml`     | 被smoke\_full.yaml替代  |
| `chunk_smoke_test.yaml`    | 功能被smoke测试覆盖         |

### 修改文件

| 文件路径        | 修改内容            |
| ----------- | --------------- |
| `README.md` | 添加模板使用说明、命名规范   |
| 各实验配置       | 统一LLM配置为default |
