# P0 双路径清理计划书：完成 Phase C 迁移，统一到 `core/ops` 原子层

> 目标：保留 `core/ops` 作为共享原子操作层，将实验系统迁移到调用 `core/ops`，实现单一链路
> 基准文档：`architecture-slim-plan.md` P0 + `maintenance-agent` 系列 spec（Phase C 迁移路径）
> 生成日期：2026-05-06

***

## 问题本质

### 原始设计意图

添加 Agent 时，把实验系统里的函数抽离成原子化工具（`core/ops`），**实验系统和 Agent 都调用这些原子工具**，形成一条链路：

```
实验系统 ──→ core/ops（原子操作）──→ src/ 底层模块
Agent   ──→ core/ops（原子操作）──→ src/ 底层模块
```

### AI 做了一半留下的烂摊子

AI 只完成了 Phase A/B（创建 `core/ops` + Agent 调用 `core/ops`），**Phase C（实验系统迁移到** **`core/ops`）没做**。结果：

```
Agent   ──→ core/ops ──→ src/ 底层模块     ← 新链路（做了一半）
实验系统 ──────────────→ src/ 底层模块     ← 老链路（没改）
Meal    ──→ core/ops(仅parse) + src/ 底层模块  ← 混合链路
```

改一处用两处的问题：如果修了 `core/ops` 里的逻辑，实验系统不走这条路，就白修了。

### 目标：完成 Phase C

```
实验系统 ──→ core/ops ──→ src/ 底层模块     ← 统一！
Agent   ──→ core/ops ──→ src/ 底层模块     ← 统一！
Meal    ──→ core/ops ──→ src/ 底层模块     ← 统一！
```

***

## 当前双路径详细清单

### 已统一（Phase C 已完成）✅

| 操作      | 实验系统调用                                      | Agent 调用                                  | 状态   |
| ------- | ------------------------------------------- | ----------------------------------------- | ---- |
| 解析      | `parser.py` → `core/ops.parse.parse_pdf()`  | `tools.py` → `core/ops.parse.parse_pdf()` | ✅ 统一 |
| Meal 解析 | `manager.py` → `core/ops.parse.parse_pdf()` | 同上                                        | ✅ 统一 |

### 未统一（Phase C 未做）❌

| 操作           | 实验系统调用（绕过 core/ops）                                                          | Agent 调用（走 core/ops）                                                         | 差异                                         |
| ------------ | ---------------------------------------------------------------------------- | ---------------------------------------------------------------------------- | ------------------------------------------ |
| 分块           | `chunker.process_parsed_files_page_aware()` → `chunk_text_page_aware()`      | `core/ops.chunk.chunk_parsed()` → `chunk_text_page_aware()`                  | 同一底层函数，但实验系统跳过了 `chunk_parsed` 的策略分发和元数据合并 |
| 分块(fixed)    | `chunker.process_parsed_files()` → `chunk_text()`                            | `core/ops.chunk.chunk_parsed(strategy="fixed")` → `chunk_text()`             | 同上                                         |
| 分块(semantic) | `semantic_chunker.process_parsed_files_semantic()` → `chunk_text_semantic()` | `core/ops.chunk.chunk_parsed(strategy="semantic")` → `chunk_text_semantic()` | 同上                                         |
| 嵌入           | `Embedder.embed_texts()` 直接调用                                                | `core/ops.embed.embed_chunks()` → `embedder.embed_texts()`                   | 极薄封装                                       |
| 索引           | `VectorIndexer.build_index()` 直接调用                                           | `core/ops.index.index_chunks()` → `VectorIndexer`                            | core/ops 内部构造 VectorIndexer                |
| 增量索引         | `VectorIndexer.delete_by_source()` + `upsert_chunks()` 直接调用                  | `core/ops.index.delete_source_and_reindex()`                                 | 同上                                         |
| 单页增强         | `ParserRegistry.get_enhancer().enhance_page()` 直接调用                          | `core/ops.parse.enhance_page()`                                              | 极薄封装                                       |
| 单表格增强        | `ParserRegistry.get_enhancer().enhance_table()` 直接调用                         | `core/ops.parse.enhance_table()`                                             | 极薄封装                                       |

### 死代码

| 函数                           | 调用者 | 处理 |
| ---------------------------- | --- | -- |
| `core/ops.query.query_rag()` | 无   | 删除 |

### `core/ops` 自身问题

| 问题                                                          | 位置                         | 影响                           |
| ----------------------------------------------------------- | -------------------------- | ---------------------------- |
| `index_chunks()` 依赖 `src.agent.config` 取默认 collection\_name | `core/ops/index.py` L42-44 | 共享层不应依赖 Agent 模块             |
| `index_chunks()` 每次调用都创建+关闭 VectorIndexer                   | `core/ops/index.py` L49-68 | 批量场景下效率低，且调用方无法复用 indexer 实例 |

***

## 具体步骤

### Step 1：修复 `core/ops` 自身问题

#### 1a. 移除 `index_chunks()` 对 Agent 模块的依赖

**当前**（`src/core/ops/index.py` L42-44）：

```python
if collection_name is None:
    from src.agent.config import get_agent_default
    collection_name = get_agent_default("collection_name", "financial_reports")
```

**改为**：`collection_name` 改为必填参数，不再提供默认值。调用方（Agent tools、实验系统）自己负责传入。

同步修改 `delete_source_and_reindex()` 的相同逻辑（L98-100）。

#### 1b. `index_chunks()` 支持外部传入 VectorIndexer

新增可选参数 `indexer: VectorIndexer | None = None`：

* 传入时：复用该 indexer，不创建也不关闭

* 不传入时：创建新 indexer，用完关闭（当前行为，向后兼容）

同步修改 `delete_source_and_reindex()`。

### Step 2：实验系统分块迁移到 `core/ops.chunk_parsed()`

**核心思路**：批量分块函数（`process_parsed_files` / `process_parsed_files_page_aware` / `process_parsed_files_semantic`）内部改为调用 `chunk_parsed()`，而非直接调用底层 `chunk_text()` / `chunk_text_page_aware()` / `chunk_text_semantic()`。

**关键转换**：`chunk_parsed()` 接收 `ParseResult` 对象，而批量函数从文件读取。需要添加辅助函数将文件数据转为 `ParseResult`。

#### 2a. 在 `src/core/ops/chunk.py` 中新增辅助函数

```python
def _parse_result_from_pages_json(pages_data: list[dict], source: str) -> ParseResult:
    """将 .pages.json 文件数据转为 ParseResult"""

def _parse_result_from_md(text: str, source: str) -> ParseResult:
    """将 .md 文件文本转为 ParseResult（单页）"""
```

#### 2b. 重构 `src/chunker.py` 的 `process_parsed_files()`

```python
# 当前：直接调用 chunk_text()
chunks = chunk_text(text, chunk_size, overlap, encoding_name, model_name)

# 改为：构造 ParseResult → 调用 chunk_parsed()
from src.core.ops.chunk import chunk_parsed, _parse_result_from_md
parse_result = _parse_result_from_md(text, source=source_name)
chunks = chunk_parsed(parse_result, strategy="fixed", chunk_size=chunk_size,
                      overlap=overlap, encoding_name=encoding_name, model_name=model_name)
```

#### 2c. 重构 `src/chunker.py` 的 `process_parsed_files_page_aware()`

```python
# 当前：直接调用 chunk_text_page_aware()
chunks = chunk_text_page_aware(page_chunks_data, source_name=source_name, ...)

# 改为：构造 ParseResult → 调用 chunk_parsed()
from src.core.ops.chunk import chunk_parsed, _parse_result_from_pages_json
parse_result = _parse_result_from_pages_json(page_chunks_data, source=source_name)
chunks = chunk_parsed(parse_result, strategy="page_aware", chunk_size=chunk_size,
                      overlap=overlap, encoding_name=encoding_name, model_name=model_name,
                      cross_page_overlap=cross_page_overlap)
```

#### 2d. 重构 `src/semantic_chunker.py` 的 `process_parsed_files_semantic()`

类似 2b，改为调用 `chunk_parsed(strategy="semantic", ...)`。

### Step 3：实验系统嵌入+索引迁移到 `core/ops`

#### 3a. 重构 `src/meal/builders.py` 的 `build_index_from_chunks()`

```python
# 当前：直接创建 Embedder + VectorIndexer
embedder = Embedder(...)
indexer = VectorIndexer(...)
indexer.build_index(chunks_dir, embedder, ...)
return indexer

# 改为：读取 chunks → core/ops.embed_chunks() → core/ops.index_chunks()
from src.core.ops.embed import embed_chunks
from src.core.ops.index import index_chunks

all_chunks = _read_chunks_from_dir(chunks_dir)  # 从 .jsonl 文件读取
embedder = Embedder(...)
embeddings = embed_chunks(all_chunks, embedder, batch_size=...)
indexer = VectorIndexer(...)  # 仍需创建，供后续查询使用
indexed = index_chunks(all_chunks, embedder, collection_name=collection_name, indexer=indexer)
return indexer
```

**注意**：`build_index_from_chunks()` 返回 `VectorIndexer` 实例供后续使用。利用 Step 1b 新增的 `indexer` 参数，可以复用同一个实例。

#### 3b. 重构 `src/pipeline.py` 的 `build_index()` 中的索引构建

当前 `pipeline.build_index()` L399-405：

```python
self.indexer.build_index(chunks_dir=str(chunks_dir), embedder=self.embedder, ...)
```

改为通过 `core/ops` 调用：

```python
from src.core.ops.index import index_chunks
# 读取 chunks、嵌入、索引
all_chunks = _read_chunks_from_dir(chunks_dir)
indexed = index_chunks(all_chunks, self.embedder,
                       collection_name=self.indexer.collection_name,
                       indexer=self.indexer)
```

### Step 4：清理 Agent tools 中的混用

当前 Agent tools 同时导入 `core/ops` 和底层模块（`Embedder`、`VectorIndexer`）。这是合理的——tools 需要构造底层对象传给 `core/ops`。但应确保**所有核心逻辑都走** **`core/ops`**：

| 工具                        | 当前导入                                                    | 改为                                   |
| ------------------------- | ------------------------------------------------------- | ------------------------------------ |
| `embed_chunks_tool`       | `core/ops.embed.embed_chunks` + `Embedder`              | 保持（构造 Embedder 传给 core/ops 是正确的）     |
| `index_chunks_tool`       | `core/ops.index.index_chunks` + `Embedder`              | 保持，但 `collection_name` 改为必传（Step 1a） |
| `delete_and_reindex_tool` | `core/ops.index.delete_source_and_reindex` + `Embedder` | 保持，但 `collection_name` 改为必传（Step 1a） |
| `get_index_info`          | 直接 `VectorIndexer`                                      | 保持（这是查询操作，core/ops 没有对应函数）           |

### Step 5：删除死代码 `core/ops/query.py`

* 将 `src/core/ops/query.py` 移入 `.trashbin/`

* 将 `tests/test_core_ops/test_query.py` 移入 `.trashbin/`

* 更新 `src/core/ops/__init__.py`，移除 `query_rag` 导出

### Step 6：验证

1. `pixi run ruff-check` 无错误
2. `pixi run test-unit` 全绿
3. `pixi run test` 全绿
4. 确认所有生产代码中，核心逻辑（parse/chunk/embed/index）都走 `core/ops`

***

## 执行顺序与依赖

```
Step 1 (修复 core/ops 自身问题) ────────┐
                                       ↓
Step 2 (分块迁移到 core/ops)  ────────┤  依赖 Step 1b（indexer 参数）
                                       │
Step 3 (嵌入+索引迁移到 core/ops) ────┤  依赖 Step 1a/1b
                                       │
Step 4 (清理 Agent tools 混用) ───────┤  依赖 Step 1a
                                       │
Step 5 (删除 query.py 死代码) ────────┤  独立
                                       ↓
Step 6 (验证) ────────────────────────┘  依赖全部完成
```

Step 1 → Step 2/3/4 可并行 → Step 5 随时 → Step 6 最后

***

## 风险与缓解

| 风险                                             | 概率 | 影响 | 缓解                                       |
| ---------------------------------------------- | -- | -- | ---------------------------------------- |
| `chunk_parsed()` 与批量函数的 chunk 输出格式不一致          | 中  | 高  | 逐字段对比输出格式，确保 metadata 完整性；编写对比测试         |
| `index_chunks(indexer=...)` 复用 indexer 时生命周期管理 | 低  | 高  | 明确约定：传入 indexer 时调用方负责关闭；不传时 core/ops 负责 |
| `process_parsed_files_*` 重构后 JSONL 输出格式变化      | 中  | 中  | 保留原有的 chunk\_id 生成逻辑和 headings 提取逻辑      |
| `collection_name` 改为必填导致现有调用方报错                | 低  | 中  | 全局搜索所有调用点，逐一补全                           |

***

## 预期效果

| 指标                   | 清理前                          | 清理后              |
| -------------------- | ---------------------------- | ---------------- |
| 解析路径                 | 实验系统 ✅ 已走 core/ops           | 不变               |
| 分块路径                 | 实验系统绕过 core/ops ❌            | 实验系统走 core/ops ✅ |
| 嵌入路径                 | 实验系统绕过 core/ops ❌            | 实验系统走 core/ops ✅ |
| 索引路径                 | 实验系统绕过 core/ops ❌            | 实验系统走 core/ops ✅ |
| core/ops 对 Agent 的依赖 | 存在（index.py 引用 agent.config） | 消除               |
| 死代码 query\_rag       | 存在                           | 删除               |
| **改一处用两处**           | ❌ 不保证                        | ✅ 保证             |

