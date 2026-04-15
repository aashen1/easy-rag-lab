# data/

本目录存放 RAG 流水线产生的所有数据，**除本文件外均已被 .gitignore 忽略**，不提交至仓库。

克隆仓库后须手动补充 `raw/` 中的源文件，其余目录由脚本自动生成。

---

## 目录结构

### `raw/`
原始 PDF 文件，手动放入，不由脚本生成。
```

raw/ 
├── annual_reports/   # 企业年报 
└── research_reports/ # 行业研报

```
命名建议：`{机构/公司}_{年份}_{简短标题}.pdf`，例如：
- `贵州茅台_2023_年度报告.pdf`
- `中金公司_2024_消费行业研报.pdf`

---

### `parsed/`
由 `src/parser.py` 生成，每个 PDF 对应一个同名 `.md` 文件。

pymupdf4llm 将 PDF 转为 Markdown，保留标题层级与表格结构。

重新生成：
```bash
pixi run python src/parser.py
```

------

### `chunks/`

由 `src/chunker.py` 生成，每个来源文件对应一个 `.jsonl` 文件，每行为一个 chunk。

chunk 字段结构：

```json
{
  "chunk_id": "贵州茅台_2023_年度报告_042",
  "text": "...",
  "metadata": {
    "source": "贵州茅台_2023_年度报告.pdf",
    "category": "annual_report",
    "chunk_index": 42,
    "char_count": 312,
    "token_count": 256
  }
}
```

重新生成：

```bash
pixi run python src/chunker.py
```

------

### `vector_store/`

Qdrant 本地持久化目录，由 `src/indexer.py` 在首次运行时自动创建。

目录结构由 Qdrant 内部管理，不要手动修改。

重新生成（**会清空现有索引**）：

```bash
pixi run python src/indexer.py --rebuild
```

------

## 完整重建流程

```bash
# 1. 确保 raw/ 中已放入 PDF
# 2. 按顺序执行
pixi run python src/parser.py
pixi run python src/chunker.py
pixi run python src/indexer.py --rebuild
```

各步骤产物落盘后，后续启动无需重建。

------

## 当前超参数（与 config.yaml 保持同步）

| 参数            | 当前值                 | 说明                |
| --------------- | ---------------------- | ------------------- |
| chunk_size      | 512 tokens             | 单块最大 token 数   |
| chunk_overlap   | 0 tokens               | 相邻块重叠 token 数 |
| embedding_model | BAAI/bge-large-zh-v1.5 | 本地 BGE 模型       |
| top_k           | 5                      | 检索返回块数        |

> 超参数变更后须重新执行完整重建流程，否则向量索引与当前配置不一致。
