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

------

### `artifacts/`

由 ArtifactCache 系统管理，按数据指纹（data_id）和配置哈希自动组织。

```
artifacts/
├── _pointers/                    # 全量解析快捷指针
│   ├── full_parsed.pointer       # 指向当前全量解析产物
│   └── full_chunks.pointer       # 指向当前全量分块产物
└── {data_id[:16]}/               # 数据指纹前16字符
    ├── manifest.json             # 缓存元数据（含 pdf_inventory、config_hashes）
    ├── parsed_{parser_hash}/     # 解析产物（Markdown / pages.json）
    └── chunks_{chunker_hash}/    # 分块产物（JSONL）
```

- `data_id`：所有 PDF 文件 SHA-256 哈希的组合哈希，前 16 字符作为目录名
- `parser_hash`：解析器配置哈希，前 8 字符，区分不同解析器配置
- `chunker_hash`：分块器配置哈希，前 8 字符，区分不同分块配置

重新生成：
```bash
pixi run python src/parser.py    # 解析 → artifacts/{data_id}/parsed_{hash}/
pixi run python src/chunker.py   # 分块 → artifacts/{data_id}/chunks_{hash}/
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

### `meals/`

Meal（数据套餐）管理目录，每个 Meal 对应一个子目录。

```
meals/
└── {meal_name}/
    ├── manifest.json         # Meal 元数据（data_id、config_hashes、collection_name）
    └── test_sets/            # 该 Meal 的测试集
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
