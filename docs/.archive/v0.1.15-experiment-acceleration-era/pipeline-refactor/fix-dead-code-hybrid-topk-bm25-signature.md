# 修复计划：死代码 / Hybrid top\_k 缺失 / BM25 签名不一致

## 问题分析

### 问题 1：`_get_retrieval_strategy()` 死代码

* **位置**：[pipeline.py:716](file:///b:/project/ash-easy-rag/src/pipeline.py#L716)

* **现状**：`query()` 在 L573-589 已内联创建了 `retrieval_strategy`，不再调用 `_get_retrieval_strategy()`

* **确认**：全局搜索 `_get_retrieval_strategy` 仅在定义处出现，无任何调用点

* **方案**：直接删除该方法

### 问题 2：`HybridRetriever.retrieve()` 向量侧未传 top\_k

* **位置**：[hybrid\_retriever.py:99](file:///b:/project/ash-easy-rag/src/hybrid_retriever.py#L99)

* **现状**：

  ```python
  fetch_k = effective_top_k * 3
  vector_results = self.vector_retriever.retrieve(query)          # ← 未传 top_k
  bm25_results = self.bm25_retriever.retrieve(query, top_k=fetch_k)  # ← 传了
  ```

* **影响**：当 `config_overrides.top_k > self.top_k` 时，向量侧只返回 `self.top_k`（默认 5）个候选，而 BM25 侧返回 `fetch_k` 个，导致融合时向量侧候选不足，影响召回质量

* **方案**：改为 `self.vector_retriever.retrieve(query, top_k=fetch_k)`

### 问题 3：`BM25Retriever.retrieve()` 签名不一致

* **位置**：[bm25\_retriever.py:204](file:///b:/project/ash-easy-rag/src/bm25_retriever.py#L204)

* **现状**：

  | 类                 | 签名                                           |
  | ----------------- | -------------------------------------------- |
  | `Retriever`       | `retrieve(query, top_k: int \| None = None)` |
  | `HybridRetriever` | `retrieve(query, top_k: int \| None = None)` |
  | `BM25Retriever`   | `retrieve(query, top_k: int = 5)` ← 不一致      |

* **影响**：签名风格不统一；且 BM25Retriever 没有 `self.top_k` 实例属性，无法像其他两个类一样 fallback 到实例默认值

* **方案**：

  1. 给 `BM25Retriever.__init__` 增加 `top_k: int = 5` 参数，存储为 `self.top_k`
  2. 将 `retrieve` 签名改为 `top_k: int | None = None`
  3. 在 `retrieve` 内部增加 `effective_top_k = top_k if top_k is not None else self.top_k`，后续使用 `effective_top_k`
  4. 更新 docstring

## 实施步骤

### Step 1：删除 `_get_retrieval_strategy()` 死代码

* 编辑 `src/pipeline.py`，删除 L716-726 的 `_get_retrieval_strategy` 方法

* 检查 `RetrievalStrategy` 相关 import 是否仍被 `query()` 中内联代码使用（L24-26），若是则保留

### Step 2：修复 `HybridRetriever.retrieve()` 向量侧 top\_k

* 编辑 `src/hybrid_retriever.py:99`

* 将 `self.vector_retriever.retrieve(query)` 改为 `self.vector_retriever.retrieve(query, top_k=fetch_k)`

### Step 3：统一 `BM25Retriever.retrieve()` 签名

* 编辑 `src/bm25_retriever.py`：

  1. `__init__` 增加 `top_k: int = 5` 参数，赋值 `self.top_k = top_k`
  2. `retrieve` 签名从 `top_k: int = 5` 改为 `top_k: int | None = None`
  3. 方法体开头增加 `effective_top_k = top_k if top_k is not None else self.top_k`
  4. 将 `scored_docs[:top_k]` 改为 `scored_docs[:effective_top_k]`
  5. 更新 docstring

### Step 4：运行 lint 检查

* 执行 `pixi run lint` 确保代码格式和规范通过

### Step 5：提交

* 按 atomic commit 规范，每个修复独立提交

## 影响范围

| 文件                        | 变更类型  | 风险             |
| ------------------------- | ----- | -------------- |
| `src/pipeline.py`         | 删除死代码 | 低 — 无调用点       |
| `src/hybrid_retriever.py` | 传参修复  | 低 — 仅补全缺失参数    |
| `src/bm25_retriever.py`   | 签名统一  | 中 — 需确认所有调用方兼容 |

调用方兼容性确认：

* `BM25RetrievalStrategy.retrieve()` 传入 `top_k=top_k`（int），兼容 `int | None`

* `HybridRetriever.retrieve()` 传入 `top_k=fetch_k`（int），兼容 `int | None`

* 其他直接调用 `bm25_retriever.retrieve()` 的地方需确认
