# ASH Easy RAG - 金融研报问答系统

一个简单易学的 RAG（检索增强生成）系统，用于金融研报的智能问答。

![Version](https://img.shields.io/badge/version-v0.1.8-blue)![Status](https://img.shields.io/badge/status-active-green)![License](https://img.shields.io/badge/license-AGPL--3.0-blue)

## 项目简介

本项目旨在构建一个最小可运行的 RAG 系统，用于金融研报的智能问答，并建立 baseline 评测基准。

### 核心功能

- **PDF 解析**：支持 pymupdf4llm 和 fitz_pdfplumber 两种解析器
- **文本分块**：固定长度 / 语义分块，可配置 chunk_size 和 overlap
- **向量检索**：BAAI/bge-large-zh-v1.5 Embedding + Qdrant 向量存储
- **混合检索**：BM25 + 向量检索 + Reranker 重排 + 查询改写
- **智能问答**：基于检索结果生成准确回答
- **评测系统**：RAGAS + Builtin 双线评测，五大核心指标 + Recall@K
- **实验管理**：多变体对比实验，自动生成 LLM 分析报告
- **Meal 体系**：数据集快照管理，测试集版本追踪
- **Artifact 体系**：中间产物缓存与 Pointer 指针机制，避免重复计算
- **对抗性评测**：adversarial 问题类型支持，数值精度校验

### 技术栈

- **PDF 解析**：pymupdf4llm / fitz_pdfplumber
- **Embedding**：BAAI/bge-large-zh-v1.5（本地）
- **向量存储**：Qdrant（本地持久化）
- **LLM**：兼容 OpenAI API 格式的 LLM 服务（支持 Anthropic Claude 等）
- **RAG 框架**：llama-index
- **评测**：RAGAS + 自研 Builtin 指标
- **环境管理**：pixi

---

## 快速开始

### 1. 环境准备

项目使用 pixi 管理 Python 环境。参考 [官方文档](https://pixi.prefix.dev/latest/installation/)。

> **GPU 说明**：本地 Embedding 模型（BAAI/bge-large-zh-v1.5）需要 CUDA 支持，具体版本无硬性要求。

```bash
# 安装 pixi 后
pixi install
```

### 2. 配置环境变量

复制 `.env.example` 为 `.env` 并填写 API Key。

### 3. 准备数据

将 PDF 文件放入 `data/raw/` 目录。

### 4. 开始使用

```bash
# 单次问答
pixi run python main.py --query "中芯国际2024年的营业收入是多少？"

# 交互式问答
pixi run interactive

# 构建向量索引
pixi run python main.py --build-index --sample-count 5

# 运行实验
pixi run exp baseline

# 运行单元测试
pixi run test

# 代码检查与格式化
pixi run lint
```

---

## 文档

详细文档请参阅 [docs/](docs/) 目录：

- [快速上手指南](docs/getting-started.md)
- [系统架构](docs/architecture.md)
- [CLI 参考](docs/cli-reference.md)
- [配置参考](docs/config-reference.md)
- [使用指南](docs/guides/)
- [项目方法论](docs/methodology.md)
- [待办事项](docs/backlog.md)
- [版本历史](docs/version-history.md)

---

## 项目结构

```
ash-easy-rag/
├── main.py              # 主入口（CLI + 交互式问答）
├── config.yaml          # 配置文件
├── src/                 # 核心模块
│   ├── parsers/         # PDF 解析器（pymupdf4llm / fitz_pdfplumber）
│   ├── chunker.py       # 固定长度分块
│   ├── semantic_chunker.py  # 语义分块
│   ├── embedder.py      # 向量嵌入
│   ├── indexer.py       # 索引构建
│   ├── retriever.py     # 向量检索
│   ├── bm25_retriever.py    # BM25 检索
│   ├── hybrid_retriever.py  # 混合检索
│   ├── reranker.py      # 重排序
│   ├── query_rewriter.py    # 查询改写
│   ├── generator.py     # 答案生成
│   ├── pipeline.py      # RAG 管线
│   ├── experiment.py    # 实验管理
│   ├── meal.py          # Meal 数据集快照管理
│   ├── artifact_cli.py  # Artifact 命令行工具
│   └── ...              # 其他模块
├── eval/                # 评测模块
├── tests/               # 单元测试
├── exp_configs/         # 实验配置
├── scripts/             # 辅助脚本
├── data/                # 数据目录
└── docs/                # 文档
```

---

## 开发规范

- **日志**：使用 `loguru`，禁止使用 `print`
- **类型标注**：所有公共函数必须标注参数类型与返回值类型
- **提交规范**：commit message 使用英文 ASCII 字符，遵循 Conventional Commits

完整开发规范详见 [CLAUDE.md](CLAUDE.md) 和 [docs/guides/development/](docs/guides/development/)。

---

## License

AGPL-3.0 License (see: https://www.gnu.org/licenses/agpl-3.0.txt)

说明：本项目使用了 `pymupdf` 与 `pymupdf4llm` 作为 PDF 解析链路，因此选择开源为 AGPL-3.0 许可证。

---

## 技术栈

- [PyMuPDF4LLM](https://github.com/pymupdf/PyMuPDF4LLM) - PDF 解析
- [pdfplumber](https://github.com/jsvine/pdfplumber) - PDF 表格提取
- [transformers](https://huggingface.co/docs/transformers/) - Embedding 模型
- [Qdrant](https://qdrant.tech/) - 向量数据库
- [llama-index](https://www.llamaindex.ai/) - RAG 框架
- [RAGAS](https://docs.ragas.io/) - RAG 评测框架
- [Anthropic](https://www.anthropic.com/) - Claude API
- [pixi](https://pixi.prefix.dev/) - Python 环境管理
