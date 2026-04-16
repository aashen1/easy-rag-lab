# 自动化评测系统开发手记

**开发时间**: 2026-04-16  
**开发阶段**: Task 11 - 更新项目文档

---

## 一、做了什么

实现了完整的自动化评测系统，包括以下核心功能：

### 1. 实验运行系统 (`eval/run_experiment.py`)

- **多 Variant 对比实验**: 支持在一个实验中定义多个 variant，自动对比评测结果
- **自动数据准备**: 如果 Meal 或测试集不存在，自动创建
- **实验管理**: 支持列出、查看、对比、复现实验
- **结果持久化**: 所有实验结果、配置快照、Meal 快照完整保存

### 2. Meal 数据管理系统 (`src/meal.py`)

- **数据版本管理**: 通过配置哈希追踪数据版本
- **自动化预处理**: 自动执行 PDF 解析、分块、向量化
- **数据完整性验证**: SHA256 校验确保数据一致性
- **采样策略**: 支持按文档数、页数、比例三种采样方式

### 3. 测试集自动生成 (`src/test_generator.py`)

- **LLM 辅助生成**: 使用 LLM 自动生成测试问题
- **多种问题策略**: 支持 factual（事实型）、boundary（边界型）等策略
- **可配置性**: 问题数量、随机种子、LLM preset 均可配置

### 4. 实验报告生成 (`eval/experiment_reporter.py`)

- **模板报告**: 自动生成结构化的 Markdown 报告
- **LLM 增强报告**: 可选使用 LLM 生成深度分析报告
- **多维度分析**: 按问题类别、难度等维度分析性能

### 5. 实验配置系统 (`exp_configs/*.yaml`)

- **YAML 格式配置**: 清晰易读的配置文件格式
- **Variant 定义**: 支持定义多个实验变体
- **配置覆盖**: Variant 可以覆盖系统配置

---

## 二、为什么这样设计

### 1. 实验可复现性

**问题**: RAG 系统实验涉及大量配置和数据，难以复现。

**解决方案**:
- **配置快照**: 每次实验保存完整的配置快照（`config_snapshot.yaml`）
- **Meal 快照**: 保存数据集的完整信息（PDF 列表、SHA256、统计数据）
- **实验复现命令**: 提供 `--reproduce` 命令，可完整复现历史实验

### 2. 数据版本管理

**问题**: 不同实验可能使用不同的数据集或配置，难以追踪。

**解决方案**:
- **Meal 系统**: 每个数据集版本称为一个 "Meal"，包含唯一 ID
- **配置哈希**: 通过配置哈希（parser、chunker、embedding）追踪数据版本
- **自动创建**: 如果 Meal 不存在，根据配置自动创建

### 3. 自动化测试集生成

**问题**: 手动构造测试集耗时且容易遗漏场景。

**解决方案**:
- **LLM 辅助生成**: 使用 LLM 从文档中自动生成问题
- **多种策略**: 支持不同类型的问题（事实型、边界型等）
- **可扩展**: 易于添加新的问题生成策略

### 4. 多 Variant 对比

**问题**: 需要对比不同配置（如不同 chunk size）的效果。

**解决方案**:
- **Variant 定义**: 在一个实验配置中定义多个 variant
- **共享数据**: 所有 variant 共享同一个 Meal 和测试集
- **自动对比**: 自动生成对比表格和最佳 variant 推荐

---

## 三、遇到的问题与解决思路

### 问题 1: 配置冲突与覆盖

**现象**: 不同 variant 需要不同的配置（如 chunk size），但共享同一个 Meal。

**解决思路**:
1. **Meal 粒度**: Meal 只包含 parser 阶段的配置（PDF 解析）
2. **动态分块**: 每个 variant 根据自己的 chunker 配置动态分块
3. **独立索引**: 每个 variant 使用独立的向量索引（通过 collection name 区分）

**实现**:
```python
# 根据 chunker 配置生成唯一的 chunks 目录
chunker_hash = compute_chunker_config_hash(chunker_config)
chunks_dir = cache.get_chunks_dir(meal_config.data_id, chunker_hash)

# 根据 embedding 配置生成唯一的 collection name
collection_name = generate_collection_name(index_key, prefix)
```

### 问题 2: 测试集与数据集的关联

**现象**: 测试集需要与特定的 Meal 关联，确保问题来源于正确的文档。

**解决思路**:
1. **Meal 绑定**: 测试集生成时绑定到特定的 Meal
2. **Source 追踪**: 每个问题记录来源文档（source_files）
3. **快照保存**: 测试集快照保存 Meal 的 data_id

**实现**:
```python
# 测试集保存在 Meal 目录下
test_sets_dir = meal_dir / "test_sets"

# 测试集包含 Meal 的 data_id
test_set_data = {
    "name": f"auto_{strategy}",
    "meal_data_id": meal_config.data_id,
    "questions": questions,
    ...
}
```

### 问题 3: 实验结果的持久化与查询

**现象**: 实验结果需要长期保存，并支持快速查询和对比。

**解决思路**:
1. **目录结构**: 每个实验一个独立目录，包含所有相关文件
2. **Manifest 文件**: 使用 `manifest.json` 存储实验元数据
3. **ExperimentManager**: 提供统一的实验管理接口

**目录结构**:
```
data/exp_reports/exp_20250416_120000/
├── manifest.json           # 实验元数据
├── config_snapshot.yaml    # 配置快照
├── meal_snapshot.json      # Meal 快照
├── results/                # 各 variant 结果
│   ├── variant_1.json
│   └── variant_2.json
└── experiment_report.md    # 实验报告
```

### 问题 4: 数据完整性验证

**现象**: PDF 文件可能被修改或删除，导致实验无法复现。

**解决思路**:
1. **SHA256 校验**: 记录每个 PDF 文件的 SHA256 哈希值
2. **验证机制**: 复现实验时验证 PDF 文件完整性
3. **优雅降级**: 提供跳过验证的选项（`--skip-verification`）

**实现**:
```python
def verify_experiment_assets(exp_dir, system_config, verify_pdf_hashes=True):
    # 1. 检查必需文件
    # 2. 验证 PDF 文件存在
    # 3. 验证 SHA256 哈希（可选）
    return AssetVerificationResult(...)
```

---

## 四、关键技术决策

### 1. 使用 YAML 作为配置格式

**理由**:
- 可读性好，易于人工编辑
- 支持注释，便于文档化
- Python 生态支持良好（PyYAML）

### 2. Meal 作为数据版本单位

**理由**:
- Meal 包含完整的数据处理流水线（PDF → chunks → vectors）
- 通过配置哈希自动追踪版本
- 避免重复处理相同数据

### 3. Variant 共享 Meal 和测试集

**理由**:
- 确保对比的公平性（相同的数据和测试集）
- 减少数据准备时间
- 只改变需要对比的配置（如 chunk size）

### 4. 自动生成测试集

**理由**:
- 减少人工标注成本
- LLM 可以生成高质量的问题
- 支持大规模测试

---

## 五、使用示例

### 1. 运行基线实验

```bash
# 使用默认配置运行实验
pixi run python eval/run_experiment.py --config exp_configs/baseline.yaml
```

### 2. 对比不同 chunk size

创建配置文件 `exp_configs/chunk_comparison.yaml`:

```yaml
name: "chunk_size_comparison"
description: "对比不同 chunk size 的效果"

data:
  meal: "meal_test"
  create_if_missing:
    sample_ratio: 0.1
    seed: 42

test_sets:
  - strategy: "factual"
    num_questions: 20
    seed: 100

variants:
  - name: "chunk_256"
    description: "chunk_size=256"
    config_overrides:
      chunker:
        chunk_size: 256
        chunk_overlap: 0

  - name: "chunk_512"
    description: "chunk_size=512"
    config_overrides:
      chunker:
        chunk_size: 512
        chunk_overlap: 0

  - name: "chunk_1024"
    description: "chunk_size=1024"
    config_overrides:
      chunker:
        chunk_size: 1024
        chunk_overlap: 0

evaluation:
  llm_preset: "default"
  metrics:
    retrieval:
      - "hit_rate"
      - "mrr"
      - "ndcg"
```

运行实验:

```bash
pixi run python eval/run_experiment.py --config exp_configs/chunk_comparison.yaml
```

### 3. 复现历史实验

```bash
# 复现实验（包含数据验证）
pixi run python eval/run_experiment.py --reproduce data/exp_reports/exp_20250416_120000

# 跳过数据验证（更快）
pixi run python eval/run_experiment.py --reproduce data/exp_reports/exp_20250416_120000 --skip-verification
```

### 4. 对比多个实验

```bash
# 对比三个实验
pixi run python eval/run_experiment.py --compare exp_001 exp_002 exp_003

# 保存对比报告
pixi run python eval/run_experiment.py --compare exp_001 exp_002 --save-report
```

---

## 六、后续优化方向

### 1. 生成质量指标

当前只实现了检索质量指标，计划添加：
- **Faithfulness**: 回答是否基于检索到的文档
- **Answer Relevancy**: 回答是否切题

### 2. 更多的测试集策略

当前支持 factual 和 boundary，计划添加：
- **reasoning**: 推理型问题
- **comparison**: 对比型问题
- **temporal**: 时间相关型问题

### 3. 实验可视化

计划添加：
- Web 界面查看实验结果
- 图表化展示性能对比
- 实验历史趋势分析

### 4. 分布式实验

支持：
- 多机并行运行实验
- 实验队列管理
- 资源调度

---

## 七、总结

本次开发实现了完整的自动化评测系统，解决了 RAG 系统实验中的以下核心问题：

1. **可复现性**: 通过配置快照、Meal 快照、SHA256 校验确保实验可复现
2. **数据管理**: 通过 Meal 系统实现数据版本管理
3. **自动化**: 自动创建数据集、测试集，减少人工干预
4. **对比分析**: 支持多 variant 对比，自动生成分析报告

系统设计遵循了以下原则：
- **配置驱动**: 所有参数通过配置文件控制
- **数据驱动**: 实验结果完整保存，支持深度分析
- **可扩展性**: 易于添加新的评测指标、测试策略
- **易用性**: 提供清晰的命令行接口和文档

该系统为后续的 RAG 系统优化提供了坚实的实验基础，可以快速验证各种优化策略的效果。
