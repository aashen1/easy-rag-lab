# Easy RAG Lab - “金融文档问答”评测实验室

![Version](https://img.shields.io/badge/version-v0.1.13-blue)![Status](https://img.shields.io/badge/status-active-green)![License](https://img.shields.io/badge/license-AGPL--3.0-blue)

## 项目简介

RAG（检索增强生成）作为让大模型从海量文档中提取目标信息的一种手段，基本已经成为目前大模型工具的标配。

但从PDF到AI回答的整个处理链路中存在大量的“零部件”，例如PDF解析策略、分块策略、召回策略等，各步都有多种可选的超参数配置与技术选择。

本项目旨在构建一个“RAG 实验室”，以金融领域的企业年报/行业研报为目标数据源，开展对 RAG 系统各“零部件”对最终问答效果影响的对比研究。

> 本项目几乎全部代码由 AI 生成与维护。关于开发手记与演进状态，请参考`docs/`目录下的相关归档；关于作者对于截止v0.1.13的整个开发历程的一些感想，请参考[这篇随笔](docs\dev-story.md)。

### 核心功能

本项目的构成可以分为 RAG 链路本身和测试系统两部分来看。

RAG链路：

- **PDF 解析**：支持 `pymupdf4llm` 和 `fitz+pdfplumber` 两条解析链路
- **文本分块**：固定长度 / 语义分块，指定 `chunk_size` 和 `overlap`
- **向量检索**：BAAI/bge-large-zh-v1.5 Embedding（使用`Transformers`库调用） + Qdrant 向量存储（local模式）
- **混合检索**：BM25 + 向量检索 + Reranker 重排 + 查询改写
- **智能问答**：基于检索结果生成准确回答，大模型调用在线API（目前支持 Anthropic SDK）

测试系统：

- **指标评测**：RAGAS + 内部实现双线评测，支持众多常用指标 + Recall@K
- **实验管理**：多变体对比实验，自动生成 LLM 分析报告
- **Meal**：（名称取自“套餐”）数据集快照管理，测试集版本追踪
- **Artifact**：中间产物缓存与 Pointer 指针机制，避免重复计算
- **Exp**：自定义实验脚本，一键运行多种变体对比实验
- **TestSet**：使用大模型生成指定数量的问题集，随后搭配交互式审核脚本，修改或剔除质量不理想的问题，方便地打造高质量测试集

### 本项目使用的软件

- [PyMuPDF4LLM](https://github.com/pymupdf/PyMuPDF4LLM) - PDF 解析
- [pdfplumber](https://github.com/jsvine/pdfplumber) - PDF 表格提取
- [transformers](https://huggingface.co/docs/transformers/) - Embedding 模型
- [Qdrant](https://qdrant.tech/) - 向量数据库
- [RAGAS](https://docs.ragas.io/) - RAG 评测框架
- [pixi](https://pixi.prefix.dev/) - Python 环境管理


### 本项目使用的开发工具与测试用API
- [字节 TRAE CN](https://www.trae.cn/) - 主力开发工具（常用模型：GLM-5.1、GLM-5、Qwen-3.6Plus、Kimi-K2.6等，排名按开发者个人使用偏好递减，不代表模型能力）
- [美团 LongCat AI](https://longcat.chat/) - API 调用（LongCat-Flash-Lite 模型）

> 重要：本项目的 LLM 代码调用为适应 LongCat API 配置，使用了特殊的`api_key="dummy"`形式，使用其他 API 源可能存在问题。


---

## 快速开始

### 1. 环境准备

项目使用 pixi 管理 Python 环境。参考 [官方文档](https://pixi.prefix.dev/latest/installation/)。

**重要说明**：目前项目的`pixi.toml`是按照开发者个人的机器进行配置，推荐首先修改其中几处：

1.  torch 版本（可自行调整更宽松的版本）
2. `find-links`设置（建议删除、修改为您的本地缓存路径，或者指定为在线URL），以避免可能出现的配置问题。
3. 镜像源配置：目前使用中科大`pypi`镜像，请按照您的网络环境相应调整

> **GPU 说明**：本地 Embedding 模型（BAAI/bge-large-zh-v1.5）需要 CUDA 支持以获得更加理想的速度

```bash
# 安装 pixi 并调整 pixi.toml 后
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

# Streamlit Web 可视化界面 (beta)
pixi run web

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
- [待办事项](.issues/)
- [版本历史](docs/version-history.md)

---

## 项目结构

```
easy-rag-lab/
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

`AGPL-3.0` License (see: https://www.gnu.org/licenses/agpl-3.0.txt)

说明：本项目使用了 `pymupdf` 与 `pymupdf4llm` 作为 PDF 解析工具，因此选择开源为 `AGPL-3.0` 许可证。
