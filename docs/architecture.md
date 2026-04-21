# 系统架构

<!-- status: active -->

> 最后更新: 2026-04-19

本文档描述系统的整体架构、模块关系和数据流。

---

## 概要

ASH Easy RAG 是一个金融研报问答系统，采用经典的 RAG（检索增强生成）架构。系统将 PDF 文档转换为向量索引，通过语义检索找到相关内容，再由 LLM 生成回答。

---

## 核心链路

```
PDF 解析 → 分块 → Embedding → 向量索引 → 检索 → [重排序] → [查询改写] → LLM 生成
   │         │        │           │          │          │           │          │
 parser   chunker  embedder    indexer   retriever  reranker  query_rewriter  generator
            │
         semantic_chunker
```

> 方括号 `[]` 中的模块为可选优化组件，通过配置启用。

---

## 模块说明

### 核心模块 (`src/`)

| 模块 | 功能 | 输入 | 输出 |
|------|------|------|------|
| `parser.py` | PDF 解析 | PDF 文件 | 页级 JSON (`.pages.json`) 或 Markdown (`.md`) |
| `chunker.py` | 固定文本分块 | Markdown / 页级 JSON | JSONL 分块文件（含页码元数据） |
| `semantic_chunker.py` | 语义文本分块 | Markdown 文件 | JSONL 分块文件 |
| `embedder.py` | 向量化 | 文本块 | 向量 |
| `indexer.py` | 向量索引 | 向量 | Qdrant 集合 |
| `retriever.py` | 向量语义检索 | 查询 | 相关文档块 |
| `bm25_retriever.py` | BM25 稀疏检索 | 查询 | 相关文档块 |
| `hybrid_retriever.py` | 混合检索融合 | 查询 | 相关文档块 |
| `reranker.py` | Cross-Encoder 重排序 | 查询 + 候选文档 | 精排文档 |
| `query_rewriter.py` | 查询改写 | 原始查询 | 改写后查询 |
| `generator.py` | LLM 生成 | 查询 + 上下文 | 回答 |
| `pipeline.py` | 流水线编排 | 配置 | 端到端问答 |

### 数据管理模块

| 模块 | 功能 |
|------|------|
| `meal.py` | 数据集版本管理（Meal 系统） |
| `sampler.py` | PDF 采样 |
| `test_generator.py` | 测试集生成 |
| `experiment.py` | 实验管理 |
| `token_tracker.py` | Token 追踪与成本估算 |

### 评测模块 (`eval/`)

| 模块 | 功能 |
|------|------|
| `metrics.py` | 评测指标计算（Hit Rate, MRR, NDCG, Faithfulness, Answer Relevancy） |
| `evaluators/base.py` | 评测器抽象基类，定义统一接口 |
| `evaluators/builtin_evaluator.py` | 自研评测器，封装现有指标计算 |
| `evaluators/ragas_evaluator.py` | RAGAS 评测器，集成 RAGAS 框架指标 |
| `run_eval.py` | 基础评测脚本（已废弃，请使用 `run_experiment.py`） |
| `run_experiment.py` | 自动化实验系统 |
| `experiment_reporter.py` | 实验报告生成 |
| `visualize.py` | 实验结果可视化（对比柱状图、趋势折线图） |

---

## 数据流

```
data/raw/           # 原始 PDF
    ↓ parser (page_chunks=True)
data/parsed/        # 解析后的页级 JSON (.pages.json) 或 Markdown (.md)
    ↓ chunker (page_aware_fixed)
data/chunks/        # 分块后的 JSONL（含页码元数据）
    ↓ embedder + indexer
data/vector_store/  # Qdrant 向量索引
    ↓ retriever + generator
回答
```

---

## Meal 系统

Meal 是数据集版本管理系统，核心概念：

- **Meal**：一个数据集配置，包含 PDF 文件列表、配置快照、向量索引
- **Data ID**：基于 PDF 文件 SHA256 计算的数据集唯一标识
- **Collection**：Qdrant 向量集合，相同 Data ID + 配置共享 Collection

详见 [Meal 系统指南](guides/meal-system.md)。

---

## 实验系统

自动化评测系统支持：

- 多 Variant 对比实验
- 自动数据准备
- 实验复现
- 报告生成

详见 [实验系统指南](guides/experiment-system.md)。

---

## 项目结构

```
ash-easy-rag/
├── main.py              # 主入口（CLI）
├── interactive.py       # 交互式问答
├── config.yaml          # 配置文件
├── src/                 # 核心模块
│   ├── parser.py
│   ├── chunker.py
│   ├── semantic_chunker.py
│   ├── embedder.py
│   ├── indexer.py
│   ├── retriever.py
│   ├── bm25_retriever.py
│   ├── hybrid_retriever.py
│   ├── reranker.py
│   ├── query_rewriter.py
│   ├── generator.py
│   ├── pipeline.py
│   ├── meal.py
│   ├── sampler.py
│   ├── test_generator.py
│   ├── experiment.py
│   └── token_tracker.py
├── eval/                # 评测模块
│   ├── metrics.py
│   ├── evaluators/      # 评测器抽象层
│   │   ├── base.py      # 评测器基类
│   │   ├── builtin_evaluator.py  # 自研评测器
│   │   └── ragas_evaluator.py    # RAGAS 评测器
│   ├── run_eval.py          # 已废弃
│   ├── run_experiment.py
│   ├── experiment_reporter.py
│   └── visualize.py
├── tests/               # 单元测试
├── exp_configs/         # 实验配置
├── data/                # 数据目录
│   ├── raw/             # 原始 PDF
│   ├── parsed/          # 解析后的 Markdown
│   ├── chunks/          # 分块后的 JSONL
│   ├── vector_store/    # Qdrant 持久化
│   ├── meals/           # Meal 数据
│   └── exp_reports/     # 实验报告
└── docs/                # 文档
```

---

## 与其他模块的关系

- **配置**：所有模块通过 `config.yaml` 配置
- **日志**：使用 `loguru` 统一日志
- **测试**：`tests/` 目录包含所有模块的单元测试
