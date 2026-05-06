# P0 双重接口清理计划书：消灭 `core/ops` 双路径技术债

> 目标：彻底消除 `src/core/ops/` 间接层，统一到 `src/` 根模块，实现单一调用链路
> 基准文档：`architecture-slim-plan.md` P0 + `maintenance-agent` 系列 spec
> 生成日期：2026-05-06

***

## 问题全景

### 现状：两条并行链路

```
Agent tools ──→ core/ops ──→ src/ 底层模块（parsers, chunker, embedder, indexer）
实验系统 ─────────────────→ src/ 底层模块（直接调用，绕过 core/ops）
Meal 系统 ──→ core/ops（仅 parse）+ src/ 底层模块（chunk, embed, index 直接调用）
```

### 核心矛盾

1. **`core/ops`** **只封装了"单文件/单步"操作**，但实验系统需要批量操作（`process_parsed_files`、`build_index`），粒度不匹配导致实验系统无法迁移
2. **`core/ops`** **是薄封装层**，功能完全依赖底层实现，增加了一层间接调用却未带来抽象价值
3. **Agent tools 混用两条路径**：parse/chunk/embed/index 走 `core/ops`，但 Embedder/VectorIndexer 实例自己构造
4. **`query_rag`** **是死代码**：无任何生产调用者
5. **`evaluate_single`** **仅被 Agent 使用**：实验系统有自己的评估逻辑

### 目标：单一链路

```
Agent tools ──→ src/ 根模块（parsers.registry, chunker, embedder, indexer, eval_helpers）
实验系统 ──→ src/ 根模块（同上）
Meal 系统 ──→ src/ 根模块（同上）
```

***

## 策略：有用逻辑归位，薄封装内联，死代码删除

`core/ops` 中有三类函数：

| 类型        | 函数                                                                                           | 处理方式            |
| --------- | -------------------------------------------------------------------------------------------- | --------------- |
| **有实际逻辑** | `parse_pdf`, `chunk_parsed`, `evaluate_single`                                               | 移入对应的 `src/` 模块 |
| **薄封装**   | `enhance_page`, `enhance_table`, `embed_chunks`, `index_chunks`, `delete_source_and_reindex` | 内联到 Agent tools |
| **死代码**   | `query_rag`                                                                                  | 删除              |

***

## 具体步骤

### Step 1：将 `parse_pdf()` 移入 `ParserRegistry`

**原因**：`parse_pdf()` 包含有用逻辑——根据 `enhancer_name` 是否存在，选择 `get_composite()` 或 `get()` 路径。这不是薄封装，而是有价值的便利方法。最自然的归属是 `ParserRegistry`，因为它已经提供 `get()` 和 `get_composite()`。

**操作**：

1. 在 `src/parsers/registry.py` 的 `ParserRegistry` 类中新增 `@classmethod parse_pdf()`，逻辑从 `src/core/ops/parse.py` 的 `parse_pdf()` 搬入，包括：

   * 路径存在性校验

   * `enhancer_name` 分发逻辑

   * 日志记录
2. 更新 `src/parser.py` 两处调用：

   * L184: `from src.core.ops.parse import parse_pdf` → `from src.parsers.registry import ParserRegistry` + `ParserRegistry.parse_pdf(...)`

   * L388: 同上
3. 更新 `src/meal/manager.py` L1474：

   * `from src.core.ops.parse import parse_pdf` → `from src.parsers.registry import ParserRegistry` + `ParserRegistry.parse_pdf(...)`
4. 更新 `src/agent/tools.py` L188/280：

   * `from src.core.ops.parse import parse_pdf` → `from src.parsers.registry import ParserRegistry` + `ParserRegistry.parse_pdf(...)`
5. 迁移 `tests/test_core_ops/test_parse.py` 中 `parse_pdf` 相关测试到 `tests/test_parsers_base.py`（或新建 `tests/test_parsers_registry_parse.py`），改为测试 `ParserRegistry.parse_pdf()`

### Step 2：将 `chunk_parsed()` 移入 `src/chunker.py`

**原因**：`chunk_parsed()` 包含策略分发逻辑（fixed/page\_aware/semantic）和元数据合并，是有价值的便利函数。自然归属是 `src/chunker.py`。

**操作**：

1. 在 `src/chunker.py` 中新增 `chunk_parsed()` 函数，逻辑从 `src/core/ops/chunk.py` 搬入
2. 更新 `src/agent/tools.py` L279：

   * `from src.core.ops.chunk import chunk_parsed` → `from src.chunker import chunk_parsed`
3. 迁移 `tests/test_core_ops/test_chunk.py` 中 `chunk_parsed` 相关测试到 `tests/test_chunker.py`

### Step 3：将 `evaluate_single()` 移入 `src/eval_helpers.py`（新文件）

**原因**：`evaluate_single()` 有自己的实现（字符 bigram 重叠度计算），不是薄封装。它仅被 Agent tools 使用，但作为独立函数放在 `src/` 下是合理的。

**操作**：

1. 创建 `src/eval_helpers.py`，将 `src/core/ops/evaluate.py` 全部内容搬入（包括 `_char_bigrams` 和 `_word_overlap` 辅助函数）
2. 更新 `src/agent/tools.py` L319：

   * `from src.core.ops.evaluate import evaluate_single` → `from src.eval_helpers import evaluate_single`
3. 迁移 `tests/test_core_ops/test_evaluate.py` 到 `tests/test_eval_helpers.py`，改为测试 `src.eval_helpers.evaluate_single`

### Step 4：内联薄封装到 Agent tools

**原因**：以下函数是极薄的封装，内联后代码更直观，减少间接调用。

#### 4a. 内联 `enhance_page()` / `enhance_table()`

当前 `core/ops/parse.py` 的 `enhance_page()` 逻辑：

```python
enhancer = ParserRegistry.get_enhancer(enhancer_name, enhancer_options)
result = enhancer.enhance_page(str(pdf_path), page_number, existing_text)
```

**操作**：在 `src/agent/tools.py` 的 `enhance_page_tool` 和 `enhance_table_tool` 中：

* `from src.core.ops.parse import enhance_page` → `from src.parsers.registry import ParserRegistry`

* 调用改为 `ParserRegistry.get_enhancer(enhancer_name).enhance_page(...)`

#### 4b. 内联 `embed_chunks()`

当前 `core/ops/embed.py` 的 `embed_chunks()` 逻辑：

```python
texts = [chunk["text"] for chunk in chunks]
embeddings = embedder.embed_texts(texts, batch_size=batch_size)
return embeddings.tolist()
```

**操作**：在 `src/agent/tools.py` 的 `embed_chunks_tool` 中：

* 删除 `from src.core.ops.embed import embed_chunks`

* 直接调用 `embedder.embed_texts(texts, batch_size=batch_size).tolist()`

#### 4c. 内联 `index_chunks()`

当前 `core/ops/index.py` 的 `index_chunks()` 逻辑：

```python
indexer = VectorIndexer(collection_name=collection_name)
texts = [chunk["text"] for chunk in chunks]
embeddings = embedder.embed_texts(texts, batch_size=batch_size)
vector_size = embedder.get_embedding_dimension()
indexer.create_collection(vector_size=vector_size, recreate=False)
indexer.index_chunks(chunks, embeddings, batch_size=100)
indexer.close()
```

**操作**：在 `src/agent/tools.py` 的 `index_chunks_tool` 中：

* 删除 `from src.core.ops.index import index_chunks`

* 直接使用 `VectorIndexer` + `Embedder` 完成索引构建

#### 4d. 内联 `delete_source_and_reindex()`

当前 `core/ops/index.py` 的 `delete_source_and_reindex()` 逻辑：

```python
indexer = VectorIndexer(collection_name=collection_name)
indexer.delete_by_source(source)
texts = [chunk["text"] for chunk in new_chunks]
embeddings = embedder.embed_texts(texts, batch_size=32)
vector_size = embedder.get_embedding_dimension()
indexer.upsert_chunks(new_chunks, embeddings)
indexer.close()
```

**操作**：在 `src/agent/tools.py` 的 `delete_and_reindex_tool` 中：

* 删除 `from src.core.ops.index import delete_source_and_reindex`

* 直接使用 `VectorIndexer` + `Embedder` 完成删除+重建索引

### Step 5：删除 `core/ops/query.py`（死代码）

**操作**：

1. 将 `src/core/ops/query.py` 移入 `.trashbin/`
2. 将 `tests/test_core_ops/test_query.py` 移入 `.trashbin/`
3. 更新 `src/core/ops/__init__.py`，移除 `query_rag` 导出

### Step 6：删除整个 `src/core/ops/` 目录

**前提**：Step 1-5 全部完成后，确认无生产代码引用 `src/core.ops`。

**操作**：

1. 将 `src/core/ops/` 整个目录移入 `.trashbin/`
2. 将 `tests/test_core_ops/` 整个目录移入 `.trashbin/`
3. 清空 `src/core/__init__.py`（已经是空文件，确认即可）
4. 全局搜索确认无残留引用：`grep -r "from src.core.ops" src/ tests/` 和 `grep -r "import src.core.ops" src/ tests/`

### Step 7：迁移扩展测试到对应模块

`tests/test_core_ops/` 中除了 ops 函数测试外，还有底层模块扩展的测试：

| 测试文件                           | 测试内容                        | 迁移目标                                                 |
| ------------------------------ | --------------------------- | ---------------------------------------------------- |
| `test_enhancer_extensions.py`  | PdfPlumberEnhancer 单页/单表格增强 | `tests/test_parsers_pdfplumber_enhancer.py` 或合并到现有测试 |
| `test_indexer_extensions.py`   | VectorIndexer 增量操作          | `tests/test_indexer.py`（追加）                          |
| `test_cache_extensions.py`     | ArtifactCache 增量更新          | `tests/test_meal_cache.py`（追加）                       |
| `test_meal_extensions.py`      | Meal 手动模式                   | `tests/test_meal.py`（追加）                             |
| `test_llm_client_langchain.py` | LangChain Anthropic 客户端     | `tests/test_llm_client.py`（追加）                       |

**注意**：这些测试测试的是底层模块的新增功能，不是 `core/ops` 本身。迁移时需更新导入路径。

### Step 8：验证

1. `pixi run ruff-check` 无错误
2. `pixi run test-unit` 全绿
3. `pixi run test` 全绿
4. 全局搜索确认无 `core.ops` 残留引用

***

## 执行顺序与依赖

```
Step 1 (parse_pdf → ParserRegistry) ─┐
Step 2 (chunk_parsed → chunker)     ─┤
Step 3 (evaluate_single → eval_helpers) ─┤  可并行
Step 4 (内联薄封装到 tools)          ─┤
Step 5 (删除 query.py 死代码)        ─┘
                ↓
Step 6 (删除 core/ops 目录) ← 依赖 Step 1-5 全部完成
                ↓
Step 7 (迁移扩展测试) ← 依赖 Step 6
                ↓
Step 8 (验证) ← 依赖 Step 7
```

***

## 风险与缓解

| 风险                                                                 | 概率 | 影响 | 缓解                      |
| ------------------------------------------------------------------ | -- | -- | ----------------------- |
| `ParserRegistry.parse_pdf()` 与原 `core/ops.parse.parse_pdf()` 行为不一致 | 低  | 高  | 逐行对比逻辑，保留所有原逻辑包括日志和异常处理 |
| Agent tools 内联后代码量增大                                               | 中  | 低  | 添加清晰的注释分段，保持可读性         |
| 扩展测试迁移后导入路径错误                                                      | 低  | 中  | 逐文件验证测试可运行              |
| 遗漏 `core.ops` 引用                                                   | 低  | 高  | Step 6/8 全局搜索确认         |

***

## 预期效果

| 指标                         | 清理前                     | 清理后          |
| -------------------------- | ----------------------- | ------------ |
| `src/core/ops/` 文件数        | 7                       | 0（删除）        |
| `tests/test_core_ops/` 文件数 | 12                      | 0（迁移/删除）     |
| 间接调用层数                     | Agent → core/ops → src/ | Agent → src/ |
| 双路径问题                      | 存在                      | 消除           |
| 死代码 (`query_rag`)          | 存在                      | 删除           |

