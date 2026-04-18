# 自动化评测系统 Spec

## Why

当前RAG项目的评测链路各个环节基本具备，但运行评测仍然比较"零碎"，缺少一键式"生成测试集 → 跑评测 → 出报告"的自动化流程。用户希望像组织实验报告一样，将数据来源、技术选型、超参数选取、问题集设置、评测方式、评测结果全部放在一个易于人类阅读的文档中，并支持多组超参数的对比实验。

## What Changes

- 新增实验配置文件系统（`exp_configs/` 目录），支持定义多组实验配置
- 新增实验报告目录结构（`data/exp_reports/`），完整记录实验资产
- 新增自动化评测脚本（`eval/run_experiment.py`），一键执行完整评测流程
- 新增实验报告生成器，生成人类可读的Markdown实验报告
- 重构配置系统，引入实验配置与系统配置的分离
- **BREAKING**: 调整 `config.yaml` 结构，将实验相关配置分离到独立的实验配置文件

## Impact

- Affected specs: 评测流程、配置管理、实验管理
- Affected code: 
  - `eval/run_eval.py` - 需要适配新的实验配置
  - `config.yaml` - 结构调整
  - `main.py` - 可能需要添加实验相关命令
  - 新增 `eval/run_experiment.py` - 实验自动化脚本
  - 新增 `eval/experiment_reporter.py` - 报告生成器
  - 新增 `src/experiment.py` - 实验管理核心模块

## ADDED Requirements

### Requirement: 实验配置文件系统

系统应提供独立的实验配置文件系统，支持用户定义多组实验配置。

#### Scenario: 创建实验配置文件
- **WHEN** 用户想要定义一组实验
- **THEN** 用户可以在 `exp_configs/` 目录下创建YAML格式的实验配置文件
- **AND** 配置文件可以指定使用的meal、问题集、超参数变体等

#### Scenario: 实验配置继承系统配置
- **WHEN** 用户定义实验配置时只指定部分超参数
- **THEN** 系统应从 `config.yaml` 中继承未指定的配置项
- **AND** 实验配置中的值应覆盖系统配置中的同名项

### Requirement: 实验报告目录结构

系统应为每次实验生成完整的实验报告目录，包含所有实验资产。

#### Scenario: 生成实验报告目录
- **WHEN** 实验执行完成
- **THEN** 系统应在 `data/exp_reports/` 下创建以实验ID命名的目录
- **AND** 目录应包含：实验配置快照、meal manifest快照、问题集快照、评测结果JSON、Markdown实验报告

#### Scenario: 实验资产完整性
- **WHEN** 用户查看实验报告目录
- **THEN** 用户应能找到所有必要的实验资产
- **AND** 小型资产（配置文件、问题集）应直接复制到目录中
- **AND** 大型资产（PDF文件）应记录路径和hash，便于验证

### Requirement: 自动化评测流程

系统应提供一键式自动化评测流程，从预处理到报告生成。

#### Scenario: 执行完整实验流程
- **WHEN** 用户运行 `pixi run python eval/run_experiment.py --config exp_configs/my_exp.yaml`
- **THEN** 系统应自动执行：检查/创建meal → 检查/生成问题集 → 运行评测 → 生成报告
- **AND** 整个过程应无需人工干预

#### Scenario: 预处理自动化
- **WHEN** 实验指定的meal不存在
- **THEN** 系统应根据实验配置自动创建meal
- **AND** 如果PDF文件已存在，系统应自动完成解析、分块、向量化

#### Scenario: 问题集自动化
- **WHEN** 实验指定的问题集不存在
- **THEN** 系统应根据实验配置自动调用LLM生成问题集
- **AND** 问题集应保存到meal的test_sets目录

### Requirement: 多超参数对比实验

系统应支持在一次实验中对比多组超参数的效果。

#### Scenario: 定义多组超参数变体
- **WHEN** 用户在实验配置中定义多个超参数变体
- **THEN** 系统应为每个变体创建独立的评测任务
- **AND** 每个变体应有独立的向量索引（基于配置hash区分）

#### Scenario: 对比实验报告
- **WHEN** 多组超参数实验完成
- **THEN** 实验报告应包含各变体的对比表格
- **AND** 报告应高亮显示最佳表现的配置

### Requirement: 人类可读的实验报告

系统应生成Markdown格式的实验报告，便于人类阅读。

实验报告中的**目的、结论与建议**等叙述性文本与主观内容，支持两种模式：

1. 由程序模板print预置文本，给出标准报告
2. 提供实验配置与结果指标给LLM，由LLM进行分析并撰写更加易读的实验报告

#### Scenario: 生成Markdown报告
- **WHEN** 实验评测完成
- **THEN** 系统应生成 `report.md` 文件
- **AND** 报告应包含：实验概述、配置详情、评测指标汇总、详细结果分析

#### Scenario: 报告内容完整性
- **WHEN** 用户阅读实验报告
- **THEN** 报告应包含：
  - 实验目的与假设
  - 数据来源（meal信息、PDF列表）
  - 技术选型（各环节使用的工具/模型）
  - 超参数配置（完整配置快照）
  - 问题集信息（策略、数量、难度分布）
  - 评测指标（Hit Rate、MRR、NDCG、后续版本加入更多指标时能方便扩展）
  - 结论与建议（程序生成或LLM解读）

### Requirement: 实验复现性

系统应确保实验可以被完整复现。

#### Scenario: 实验资产打包
- **WHEN** 用户想要分享或存档实验
- **THEN** 用户可以将实验报告目录打包带走
- **AND** 目录中应包含所有必要的配置和中间产物快照

#### Scenario: 实验复现
- **WHEN** 用户将实验资产放回项目并运行复现命令
- **THEN** 系统应验证PDF文件和配置的完整性
- **AND** 系统应使用快照中的配置重新运行评测
- **AND** 结果应与原实验基本一致（考虑LLM随机性）

## MODIFIED Requirements

### Requirement: 配置文件结构

原有 `config.yaml` 需要调整结构，将实验相关配置分离。

**原结构**:
```yaml
active_mode: "default"
llm_presets: ...
parser: ...
chunker: ...
embedding: ...
vector_store: ...
retrieval: ...
evaluation: ...
test_generation: ...
```

**新结构**:
```yaml
# 系统默认配置（保持不变）
active_mode: "default"
llm_presets: ...

# 数据处理配置（保持不变）
parser: ...
chunker: ...
embedding: ...
vector_store: ...
retrieval: ...

# 评测配置（移除，由实验配置管理）
# evaluation: ...  # 移除

# 测试生成配置（保持不变）
test_generation: ...

# 新增：实验相关配置
experiments:
  dir: "data/exp_reports"  # 实验报告存放目录
  configs_dir: "exp_configs"  # 实验配置文件目录
```

## REMOVED Requirements

### Requirement: 独立的evaluation配置段

**Reason**: 评测相关配置（test_data_path、results_dir、metrics）应移至实验配置文件中管理，因为不同实验可能有不同的评测设置。

**Migration**: 将 `config.yaml` 中的 `evaluation` 段移除，相关配置在实验配置文件中指定。

---

## 设计方案详解

### 1. 实验配置文件格式

```yaml
# experiments/baseline.yaml
name: "baseline_evaluation"
description: "基线评测 - 固定长度分块，无优化"

# 数据源配置
data:
  meal: "meal_baseline"  # 使用现有meal，或指定创建参数
  create_if_missing:
    sample_ratio: 0.1
    seed: 42

# 问题集配置
test_sets:
  - strategy: "factual"
    num_questions: 20
    seed: 100
  - strategy: "boundary"
    num_questions: 15
    seed: 101

# 超参数变体（支持多个变体对比）
variants:
  - name: "chunk_512_overlap_0"
    description: "chunk_size=512, overlap=0"
    config_overrides:
      chunker:
        chunk_size: 512
        chunk_overlap: 0
  
  - name: "chunk_512_overlap_50"
    description: "chunk_size=512, overlap=50"
    config_overrides:
      chunker:
        chunk_size: 512
        chunk_overlap: 50

# 评测配置
evaluation:
  llm_preset: "default"
  metrics:
    retrieval:
      - "hit_rate"
      - "mrr"
      - "ndcg"
    generation:  # 未来扩展
      - "faithfulness"
      - "answer_relevancy"

# LLM配置（用于问题生成和回答）
llm:
  question_generation: "sonnet"
  answering: "default"
```

### 2. 实验报告目录结构

```
data/exp_reports/
└── exp_20250416_120000_baseline/  # 实验ID（时间戳+实验名）
    ├── manifest.json              # 实验元数据
    ├── config_snapshot.yaml       # 完整配置快照（合并系统配置和实验配置）
    ├── meal_snapshot.json         # Meal manifest快照
    ├── test_sets/                 # 问题集快照
    │   ├── factual.json
    │   └── boundary.json
    ├── results/                   # 评测结果
    │   ├── variant_chunk_512_overlap_0.json
    │   └── variant_chunk_512_overlap_50.json
    └── report.md                  # 人类可读的实验报告
```

### 3. 实验报告Markdown模板

```markdown
# 实验报告：baseline_evaluation

**实验时间**: 2025-04-16 12:00:00  
**实验ID**: exp_20250416_120000_baseline

---

## 1. 实验概述

### 1.1 实验目的
评估不同分块参数对RAG系统检索质量的影响。

### 1.2 实验假设
增加chunk_overlap可能提高边界问题的检索准确率。

---

## 2. 数据来源

### 2.1 Meal信息
- **名称**: meal_baseline
- **Data ID**: abc123def456
- **PDF数量**: 10
- **总页数**: 150
- **总块数**: 1200

### 2.2 PDF文件列表
| 文件名 | 大小 | 页数 | SHA256 |
|--------|------|------|--------|
| report1.pdf | 2.3MB | 25 | abc123... |
| report2.pdf | 1.8MB | 18 | def456... |

---

## 3. 技术选型

| 环节 | 工具/模型 | 配置 |
|------|----------|------|
| PDF解析 | pymupdf4llm | algorithm: pymupdf4llm |
| 分块 | Fixed-size | chunk_size: 512/512, overlap: 0/50 |
| Embedding | BAAI/bge-large-zh-v1.5 | device: cuda |
| 向量存储 | Qdrant | distance: Cosine |
| 检索 | Top-K | top_k: 5 |
| LLM | Claude-3 | preset: default |

---

## 4. 问题集信息

### 4.1 事实性问题 (factual)
- **数量**: 20题
- **难度**: easy
- **生成策略**: 单chunk随机采样

### 4.2 边界问题 (boundary)
- **数量**: 15题
- **难度**: medium
- **生成策略**: 相邻chunk配对

---

## 5. 评测结果

### 5.1 总体对比

| 变体 | Hit Rate | MRR | NDCG@5 | 平均耗时 |
|------|----------|-----|--------|----------|
| chunk_512_overlap_0 | 0.72 | 0.65 | 0.68 | 2.3s |
| chunk_512_overlap_50 | **0.78** | **0.71** | **0.74** | 2.5s |

### 5.2 按问题类型分析

#### 事实性问题
| 变体 | Hit Rate | MRR | NDCG@5 |
|------|----------|-----|--------|
| chunk_512_overlap_0 | 0.85 | 0.78 | 0.82 |
| chunk_512_overlap_50 | 0.87 | 0.80 | 0.84 |

#### 边界问题
| 变体 | Hit Rate | MRR | NDCG@5 |
|------|----------|-----|--------|
| chunk_512_overlap_0 | 0.55 | 0.48 | 0.52 |
| chunk_512_overlap_50 | **0.68** | **0.61** | **0.65** |

---

## 6. 结论与建议

### 6.1 主要发现
1. 增加overlap=50后，边界问题的检索准确率提升约13%
2. 事实性问题提升不明显（约2%）
3. 整体检索质量提升约6%

### 6.2 建议
- 推荐使用 overlap=50 作为默认配置
- 对于边界敏感的场景，可考虑进一步增加overlap
- 后续可测试语义分块策略

---

## 7. 实验资产

本实验的完整资产已保存在 `data/exp_reports/exp_20250416_120000_baseline/` 目录中。

### 7.1 文件清单
- `manifest.json` - 实验元数据
- `config_snapshot.yaml` - 完整配置快照
- `meal_snapshot.json` - Meal manifest快照
- `test_sets/*.json` - 问题集快照
- `results/*.json` - 详细评测结果

### 7.2 复现方法
1. 确保PDF文件存在于 `data/raw/` 目录
2. 运行: `pixi run python eval/run_experiment.py --reproduce data/exp_reports/exp_20250416_120000_baseline`
```

### 4. 核心模块设计

#### 4.1 ExperimentManager (src/experiment.py)

```python
class ExperimentConfig:
    """实验配置"""
    name: str
    description: str
    data: Dict[str, Any]  # meal配置
    test_sets: List[Dict]  # 问题集配置
    variants: List[Dict]  # 超参数变体
    evaluation: Dict[str, Any]  # 评测配置
    
class ExperimentResult:
    """实验结果"""
    experiment_id: str
    timestamp: str
    config: ExperimentConfig
    meal_snapshot: Dict
    test_set_snapshots: List[Dict]
    variant_results: List[Dict]
    
class ExperimentManager:
    """实验管理器"""
    def load_experiment_config(self, config_path: str) -> ExperimentConfig
    def create_experiment_dir(self, config: ExperimentConfig) -> Path
    def save_snapshots(self, exp_dir: Path, config: ExperimentConfig, ...)
    def generate_report(self, exp_dir: Path, result: ExperimentResult) -> None
    def reproduce_experiment(self, exp_dir: Path) -> ExperimentResult
```

#### 4.2 ExperimentReporter (eval/experiment_reporter.py)

```python
class ExperimentReporter:
    """实验报告生成器"""
    def generate_markdown_report(
        self, 
        exp_dir: Path, 
        result: ExperimentResult
    ) -> str
    def _generate_overview_section(self, ...) -> str
    def _generate_data_section(self, ...) -> str
    def _generate_results_section(self, ...) -> str
    def _generate_comparison_table(self, ...) -> str
```

#### 4.3 run_experiment.py (eval/run_experiment.py)

```python
def run_experiment(config_path: str, skip_preprocessing: bool = False):
    """执行完整实验流程"""
    # 1. 加载实验配置
    exp_config = load_experiment_config(config_path)
    
    # 2. 准备数据源（meal）
    meal_config = prepare_meal(exp_config.data)
    
    # 3. 准备问题集
    test_sets = prepare_test_sets(exp_config.test_sets, meal_config)
    
    # 4. 为每个变体运行评测
    for variant in exp_config.variants:
        # 4.1 应用配置覆盖
        merged_config = merge_config(base_config, variant.config_overrides)
        
        # 4.2 创建/获取对应的向量索引
        collection_name = get_or_create_collection(merged_config, meal_config)
        
        # 4.3 运行评测
        results = run_evaluation(pipeline, test_sets)
        
        # 4.4 保存结果
        save_variant_results(exp_dir, variant.name, results)
    
    # 5. 生成报告
    generate_experiment_report(exp_dir, all_results)
```

### 5. 命令行接口

```bash
# 运行实验
pixi run python eval/run_experiment.py --config experiments/baseline.yaml

# 列出所有实验
pixi run python eval/run_experiment.py --list

# 查看实验详情
pixi run python eval/run_experiment.py --info exp_20250416_120000_baseline

# 复现实验
pixi run python eval/run_experiment.py --reproduce data/exp_reports/exp_20250416_120000_baseline

# 对比多个实验
pixi run python eval/run_experiment.py --compare exp_001 exp_002 exp_003
```

### 6. 向后兼容性考虑

由于项目处于0.1.x版本，本次升级采用破坏性变更策略：

1. **移除** `config.yaml` 中的 `evaluation` 段
2. **新增** `experiments/` 目录存放实验配置
3. **新增** `data/exp_reports/` 目录存放实验报告
4. **保留** 现有的 `eval/run_eval.py` 作为底层评测接口
5. **新增** `eval/run_experiment.py` 作为高级自动化接口

现有用户需要：
- 将评测相关配置迁移到实验配置文件
- 使用新的 `run_experiment.py` 脚本进行自动化评测
