# ASH Easy RAG - 金融研报问答系统

一个简单易学的 RAG（检索增强生成）系统，用于金融研报的智能问答。

## 🎯 项目简介

本项目旨在构建一个最小可运行的 RAG 系统，用于金融研报的智能问答，并建立 baseline 评测基准。

### 核心功能

- **PDF 解析**：使用 pymupdf4llm 将 PDF 转换为 Markdown
- **文本分块**：固定长度分块（512 tokens, overlap=0）
- **向量检索**：使用 BAAI/bge-large-zh-v1.5 进行 Embedding，Qdrant 进行向量存储
- **智能问答**：基于检索结果生成准确回答

### 技术栈

- **PDF 解析**：pymupdf4llm
- **分块策略**：固定长度分块（overlap=0）
- **Embedding**：BAAI/bge-large-zh-v1.5（本地）
- **向量存储**：Qdrant（本地持久化）
- **LLM**：LongCat API（Anthropic SDK）
- **评测框架**：自定义评测脚本

---

## 📦 安装与配置

### 1. 环境准备

项目使用 pixi 管理 Python 环境：

```bash
# 安装 pixi（如果尚未安装）
# Windows:
winget install prefix-dev.pixi

# 初始化环境
pixi install
```

### 2. 配置环境变量

复制 `.env.example` 为 `.env` 并填写必要的配置：

```bash
cp .env.example .env
```

编辑 `.env` 文件：

```env
# LLM API Configuration
LLM_API_KEY="your-api-key-here"
LLM_BASE_URL="https://api.longcat.chat/"
LLM_MODEL_ID="LongCat-Flash-Lite"
```

### 3. 准备数据

将 PDF 文件放入 `data/raw/` 目录：

```
data/raw/
├── annual_reports/     # 企业年报
│   ├── 2023/
│   └── 2024/
└── research_reports/   # 行业研报
```

---

## 🚀 快速开始

### 1. 构建向量索引

首次使用需要构建向量索引：

```bash
# 构建完整索引（跳过已解析的 PDF）
pixi run python main.py --build-index

# 或使用采样进行快速测试（仅处理 5 个 PDF）
pixi run python main.py --build-index --sample-size 5

# 强制重新解析所有 PDF
pixi run python main.py --build-index --force-parse

# 重建向量索引（清空现有索引，不重解析 PDF）
pixi run python main.py --rebuild

# 完全重建（重解析 PDF + 重建索引）
pixi run python main.py --rebuild --force-parse
```

### 2. 执行问答

```bash
# 单次查询
pixi run python main.py --query "贵州茅台2023年的营业收入是多少？"

# 使用不同的 LLM preset
pixi run python main.py --query "工商银行2024年的净利润是多少？" --llm-preset opus
```

---

## 📊 评测系统

### 运行评测

```bash
# 运行完整评测
pixi run python eval/run_eval.py

# 快速评测（采样 5 个问题）
pixi run python eval/run_eval.py --sample-size 5

# 构建索引后立即评测
pixi run python eval/run_eval.py --build-index
```

### 评测指标

**检索质量指标**：
- **Hit Rate**：命中率，检索结果中包含正确文档的比例
- **MRR**：平均倒数排名，衡量第一个正确文档的排名
- **NDCG**：归一化折损累积增益，综合考虑排序位置

**生成质量指标**：
- 基于检索结果的回答质量评估

### 查看评测结果

评测结果保存在 `eval/results/baseline_report.json`：

```json
{
  "timestamp": "2026-04-15T...",
  "total_test_cases": 10,
  "total_time_seconds": 45.2,
  "retrieval_metrics": {
    "avg_hit_rate": 0.85,
    "avg_mrr": 0.72,
    "avg_ndcg": 0.78
  }
}
```

---

## 📁 项目结构

```
ash-easy-rag/
├── config.yaml              # 超参数配置
├── .env.example             # 环境变量模板
├── main.py                  # 主入口（CLI）
├── src/
│   ├── __init__.py
│   ├── utils.py             # 工具函数
│   ├── parser.py            # PDF 解析模块
│   ├── chunker.py           # 分块模块
│   ├── embedder.py          # Embedding 模块
│   ├── indexer.py           # 向量索引模块
│   ├── retriever.py         # 检索模块
│   ├── generator.py         # LLM 生成模块
│   └── pipeline.py          # 完整流水线
├── eval/
│   ├── __init__.py
│   ├── test_data.json       # 测试集
│   ├── metrics.py           # 评测指标
│   ├── run_eval.py          # 评测脚本
│   └── results/             # 评测结果
├── tests/                   # 单元测试
├── notes/                   # 开发笔记
└── data/
    ├── raw/                 # 原始 PDF
    ├── parsed/              # 解析后的 Markdown
    ├── chunks/              # 分块后的 JSONL
    └── vector_store/        # Qdrant 持久化
```

---

## 🔧 手动执行步骤

如果你想逐步执行每个阶段：

### 步骤 1：解析 PDF

```bash
pixi run python src/parser.py
```

将 `data/raw/` 中的 PDF 转换为 Markdown，保存到 `data/parsed/`。

### 步骤 2：分块

```bash
pixi run python src/chunker.py
```

将 Markdown 文件分块，保存到 `data/chunks/`。

### 步骤 3：构建向量索引

```bash
pixi run python src/indexer.py
```

将分块数据向量化并存储到 Qdrant。

### 步骤 4：测试检索

```bash
pixi run python src/retriever.py
```

测试检索功能。

### 步骤 5：测试生成

```bash
pixi run python src/generator.py
```

测试 LLM 生成功能。

---

## ⚙️ 配置说明

### config.yaml

```yaml
# LLM 配置（支持多 preset）
active_mode: "default"

llm_presets:
  default:
    model_name: "LLM_MODEL_ID"
    temperature: 0.0
    max_tokens: 1024
    api_key_env_var: "LLM_API_KEY"
    base_url_env_var: "LLM_BASE_URL"

# 分块配置
chunker:
  chunk_size: 512        # 每块最大 token 数
  chunk_overlap: 0       # 相邻块重叠 token 数

# Embedding 配置
embedding:
  model_name: "BAAI/bge-large-zh-v1.5"
  device: "cuda"         # 或 "cpu"
  batch_size: 32

# 检索配置
retrieval:
  top_k: 5               # 检索返回块数
```

---

## 🧪 测试

运行单元测试：

```bash
# 运行所有测试
pixi run pytest tests/ -v

# 运行特定模块测试
pixi run pytest tests/test_parser.py -v
pixi run pytest tests/test_chunker.py -v
pixi run pytest tests/test_embedder.py -v
```

---

## 📈 性能优化建议

1. **采样测试**：使用 `--sample-size` 参数进行快速测试
2. **GPU 加速**：确保 `embedding.device` 设置为 `cuda`
3. **批处理**：调整 `embedding.batch_size` 以优化性能
4. **索引持久化**：向量索引会自动保存，无需每次重建

---

## 🐛 常见问题

### Q: 如何更换 LLM 模型？

A: 修改 `.env` 文件中的 `LLM_MODEL_ID`，或使用 `--llm-preset` 参数选择不同的 preset。

### Q: 如何调整检索数量？

A: 修改 `config.yaml` 中的 `retrieval.top_k` 参数。

### Q: 如何处理大量 PDF？

A: 使用 `--sample-size` 参数进行采样测试，或分批处理。

---

## 📝 开发规范

- **日志**：使用 `loguru`，禁止使用 `print`
- **类型标注**：所有公共函数必须标注参数类型与返回值类型
- **Docstring**：所有公共函数须包含功能描述、参数说明、返回值说明
- **异常处理**：所有 IO 操作必须有 `try/except`
- **提交规范**：commit message 使用英文 ASCII 字符，遵循 Conventional Commits

---

## 📄 License

MIT License

---

## 🙏 致谢

- [pymupdf4llm](https://github.com/pymupdf/PyMuPDF4LLM) - PDF 解析
- [FlagEmbedding](https://github.com/FlagOpen/FlagEmbedding) - Embedding 模型
- [Qdrant](https://qdrant.tech/) - 向量数据库
- [LongCat](https://longcat.chat/) - LLM API
