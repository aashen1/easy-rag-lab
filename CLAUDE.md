## 项目简介

- **功能**：金融研报 RAG 问答系统
- **文档来源**：企业年报 PDF、行业研报 PDF，位于`data/raw/`
- **开发目标**：学习 RAG 核心原理，系统性探究超参数与技术选型对回答质量的影响

---

## 开发规范

### 版本控制
- 每个开发步骤独立提交，commit message 须清晰描述变更内容
- **commit message 仅允许英文 ASCII 字符**，遵循 Conventional Commits 格式（如 `feat:`、`fix:`、`docs:`）

### 测试
- 使用 Red/Green TDD 进行开发
- 每步开发必须附带 pytest 测试，确保行为符合预期
- 测试文件与源文件保持对应关系（如 `src/parser.py` → `tests/test_parser.py`）

### 代码质量
- **日志**：使用 `loguru`，禁止使用 `print`
- **类型标注**：所有公共函数必须标注参数类型与返回值类型
- **Docstring**：所有公共函数须包含功能描述、参数说明（Args）、返回值说明（Returns）、异常说明（Raises）
- **异常处理**：所有 IO 操作（PDF 读取、网络请求、文件写入）必须有 `try/except`，捕获异常后记录日志并优雅降级，禁止让程序直接崩溃
- **代码格式化**：使用 `autopep8` 自动格式化；如需固定 import 顺序，使用 `# noqa` 标注

### 配置与环境
- **超参数与配置**：所有超参数、模型名、路径等均写入 `config.yaml`，禁止在代码中硬编码
- **环境变量**：变量命名参考 `.env.example`，敏感信息（API Key 等）不得提交至仓库
- **依赖选型**：如需变更任何依赖或技术选型，须先告知，不得擅自替换

### 持久化
- 文档解析结果、向量索引等中间产物必须落盘，避免每次启动时重建

### 开发手记
- 每个开发阶段在 `notes/` 目录下新建命名清晰的 `.md` 文件
- 内容须覆盖：做了什么、为什么这样做、遇到的问题与解决思路

------

## 当前目标

**阶段：MVP RAG + Baseline 评测 ✅ 已完成**

~~目标是跑通最小可运行的 RAG 链路，拿到可量化的 baseline 评测结果，为后续优化提供对照基准。**本阶段不引入任何优化手段**，所有技术选型以"能跑、够简单"为准则。~~

注：`pixi.toml`中可能带有一些不在当前计划中的依赖库，无需关注也不要使用。

### 交付范围

**链路（Pipeline）** ✅

- PDF 解析（`pymupdf4llm`） → 固定长度分块（fixed-size chunk，指定`overlap=0`）→ Embedding（`BAAI/bge-large-zh-v1.5`） → 向量存储（`qdrant`） → Top-K 检索 → LLM 生成回答
- （基座模型使用Anthropic SDK调用LongCat在线API，调用方式参考 [LongCat-API适配性分析.md](plgd\ref-info\LongCat-API适配性分析.md) ）

**评测（Evaluation）** ✅

- 构造一批覆盖典型问题类型的问答对作为测试集（Q&A pairs），问题来自真实研报场景
- 对每条问题跑完整链路，记录检索结果与生成回答
- 计算以下指标，输出结构化评测报告：
  - **检索质量**：Hit Rate、MRR、NDCG ✅
  - **生成质量**：RAGAS 中的 Faithfulness、Answer Relevancy（不依赖人工标注）⚠️ 待实现
- 评测脚本独立可复现，结果落盘到 `eval/results/`

### 本阶段明确不做

- 混合检索（BM25 + 向量）
- 重排（Reranker）
- 语义分块、滑动窗口、父子 chunk 等 chunk 策略
- 查询改写、HyDE、Multi-Query
- 任何 Prompt 工程优化

> 上述内容列入 Backlog，待 baseline 结果出来后按收益优先级逐步引入。

### 完成标准 ✅

1. ✅ `python main.py --query "..."` 能端到端返回回答
2. ✅ `python eval/run_eval.py` 能自动跑完测试集并输出报告
3. ⚠️ 评测报告（含各项指标数值）提交至 `notes/` 作为 baseline 存档（待运行）

---

## 自动化评测系统

项目已实现完整的自动化评测系统，支持多 variant 对比实验、自动数据准备、实验复现等功能。

### 核心组件

1. **实验运行器** (`eval/run_experiment.py`)
   - 支持多 variant 对比实验
   - 自动创建 Meal 和测试集
   - 实验结果持久化
   - 支持实验复现和对比

2. **实验配置** (`exp_configs/*.yaml`)
   - YAML 格式的实验配置文件
   - 支持定义多个 variant
   - 支持多种测试集策略

3. **Meal 系统** (`src/meal.py`)
   - 数据版本管理
   - 自动化数据预处理
   - 配置哈希追踪

4. **测试集生成器** (`src/test_generator.py`)
   - 自动生成测试问题
   - 支持多种问题策略（factual, boundary 等）
   - LLM 辅助生成

### 快速开始

```bash
# 运行实验
pixi run python eval/run_experiment.py --config exp_configs/baseline.yaml

# 列出所有实验
pixi run python eval/run_experiment.py --list

# 查看实验详情
pixi run python eval/run_experiment.py --info exp_20250416_120000

# 对比多个实验
pixi run python eval/run_experiment.py --compare exp_001 exp_002

# 复现实验
pixi run python eval/run_experiment.py --reproduce data/exp_reports/exp_20250416_120000
```

### 实验配置说明

实验配置文件位于 `exp_configs/` 目录，采用 YAML 格式：

```yaml
name: "experiment_name"
description: "实验描述"

data:
  meal: "meal_name"  # Meal 名称
  create_if_missing:  # 如果 Meal 不存在，自动创建
    sample_ratio: 0.1  # 采样比例
    seed: 42

test_sets:
  - strategy: "factual"  # 问题策略
    num_questions: 20
    seed: 100

variants:
  - name: "variant_name"
    description: "variant 描述"
    config_overrides:  # 配置覆盖
      chunker:
        chunk_size: 512
        chunk_overlap: 0

evaluation:
  llm_preset: "default"
  metrics:
    retrieval:
      - "hit_rate"
      - "mrr"
      - "ndcg"
```

### 实验结果

实验结果保存在 `data/exp_reports/` 目录：

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

### 评测指标

**检索质量指标**：
- **Hit Rate**：命中率，检索结果中包含正确文档的比例
- **MRR**：平均倒数排名，衡量第一个正确文档的排名
- **NDCG**：归一化折损累积增益，综合考虑排序位置

**生成质量指标**（计划中）：
- Faithfulness：回答的忠实度
- Answer Relevancy：回答的相关性

---

## 下一阶段目标

**阶段：优化与迭代**

基于 baseline 评测结果，按优先级逐步引入优化手段，系统性提升 RAG 系统性能。

### 计划优化项（按优先级排序）

#### 1. 高优先级（立即实施）
- [x] 运行完整的 baseline 评测，生成评测报告
- [ ] 实现生成质量指标（Faithfulness、Answer Relevancy）
- [ ] 解决 FlagEmbedding 依赖兼容性问题（如需要）

#### 2. 中优先级（短期 1-2 周）
- [ ] 混合检索（BM25 + 向量）
- [ ] Reranker 重排
- [ ] 查询改写

#### 3. 低优先级（中长期）
- [ ] 语义分块
- [ ] 滑动窗口
- [ ] Prompt 工程
- [ ] 父子 chunk
- [ ] HyDE
- [ ] Multi-Query
- [ ] 缓存机制

### 优化原则

1. **数据驱动**：每次优化前后都要运行评测，量化改进效果
2. **增量迭代**：一次只引入一个优化手段，便于定位问题
3. **文档记录**：每个优化阶段都要在 `notes/` 中记录实验结果和分析

----

