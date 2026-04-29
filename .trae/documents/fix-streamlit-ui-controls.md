# 修复计划：Streamlit 侧边栏控件"造假"问题

## 问题直白解释

你观察到的现象完全正确，这确实是"层级错误"。让我画个图说清楚：

```
Streamlit 进程启动
  │
  ├─ 读取环境变量（API KEY 等）── 只读一次，进程不重启就不刷新
  │
  ├─ @st.cache_resource 缓存了 Pipeline 实例
  │    │
  │    ├─ 读取 config.yaml ── 只读一次，决定初始化哪些组件
  │    │
  │    ├─ config.yaml 说 retrieval.method = "vector"
  │    │    → 只创建 VectorRetriever，不创建 BM25Retriever
  │    │
  │    ├─ config.yaml 说 reranker.enabled = false
  │    │    → 不加载 Reranker 模型（~1GB）
  │    │
  │    └─ config.yaml 说 query_rewrite.enabled = false
  │         → 不初始化 QueryRewriter
  │
  └─ 用户在侧边栏操作
       │
       ├─ 选了"hybrid"检索 ── 写入 st.session_state.retrieval_method
       ├─ 勾了"启用 Reranker" ── 写入 st.session_state.use_reranker
       ├─ 勾了"启用查询改写" ── 写入 st.session_state.use_query_rewrite
       │
       └─ 点击发送问题
            │
            └─ pipeline.query(question)  ← 完全没传任何侧边栏参数！
                 │
                 └─ 走的还是 config.yaml 的默认值
                      → 纯向量检索，没 Reranker，没查询改写
```

**所以你之前发现的环境变量问题也是同一个根因**：Pipeline 在启动时一次性读取配置，之后就不变了。Streamlit 的 Rerun 只是重新执行脚本，不会重启进程，所以环境变量和 Pipeline 缓存都不会刷新。

## 修复思路

**核心想法：不在启动时决定一切，而是在每次查询时按需决定。**

具体来说：

1. **给** **`query()`** **方法加"覆盖参数"**：用户在 UI 上选了什么，就传什么给 `query()`
2. **用"懒加载"代替"启动时全量加载"**：用户勾了 Reranker，才去加载模型；没勾就不加载
3. **Pipeline 实例仍然缓存**：不重建 Pipeline，只是让它在每次查询时能动态选择策略

修复后的流程：

```
用户点击发送问题
  │
  └─ pipeline.query(
       question,
       retrieval_method="hybrid",    ← 从 UI 传入
       top_k=8,                      ← 从 UI 传入
       use_reranker=True,            ← 从 UI 传入
       use_query_rewrite=True,       ← 从 UI 传入
     )
       │
       ├─ 检测到 retrieval_method="hybrid"
       │    → BM25 索引还没建？那就现在建（懒加载）
       │    → 用 HybridRetriever 检索
       │
       ├─ 检测到 use_reranker=True
       │    → Reranker 模型还没加载？那就现在加载（懒加载，首次约 10-30 秒）
       │    → 对检索结果做重排序
       │
       └─ 检测到 use_query_rewrite=True
            → QueryRewriter 还没初始化？那就现在初始化（调 LLM API，很快）
            → 先改写查询再检索
```

## 4 个控件的难度评估

| 控件       | 难度      | 说明                                      |
| -------- | ------- | --------------------------------------- |
| Top-K    | ⭐ 很简单   | 直接传参，改一行代码                              |
| 检索策略     | ⭐⭐⭐ 中等  | 需要懒加载 BM25 索引（从 JSONL 文件构建，几秒到几十秒）      |
| 查询改写     | ⭐⭐ 中等   | 需要懒初始化 QueryRewriter（调 LLM API，不需要本地模型） |
| Reranker | ⭐⭐⭐⭐ 较难 | 需要懒加载 \~1GB 交叉编码器模型（首次启用慢 10-30 秒，之后正常） |

**四个都能做，不需要删任何一个。**

## 实施步骤

### 第 1 步：让 Retriever 支持动态 top\_k

**文件**：`src/retriever.py`

现在 `retrieve(query)` 写死了用 `self.top_k`。改成可以传参覆盖：

```python
def retrieve(self, query: str, top_k: int | None = None) -> list[dict]:
    effective_top_k = top_k if top_k is not None else self.top_k
    # 用 effective_top_k 去检索
```

### 第 2 步：让 HybridRetriever 也支持动态 top\_k

**文件**：`src/hybrid_retriever.py`

同上，加 `top_k` 参数。

### 第 3 步：修复策略类，把 top\_k 传下去

**文件**：`src/retrieval_strategies.py`

现在的 `VectorRetrievalStrategy.retrieve()` 收到了 `top_k` 参数但完全忽略了！修一下，让它传给底层 Retriever。

### 第 4 步：给 Pipeline 加懒加载方法

**文件**：`src/pipeline.py`

加三个方法：

* `_ensure_bm25_index()` — 如果 BM25 索引没建，就从 chunks 文件建一个

* `_ensure_reranker()` — 如果 Reranker 模型没加载，就加载

* `_ensure_query_rewriter()` — 如果 QueryRewriter 没初始化，就初始化

同时存一个 `self._chunks_dir`，这样懒加载 BM25 时知道去哪找 chunks 文件。

### 第 5 步：修改 `_setup_retrievers()`，始终创建 BM25Retriever 实例

**文件**：`src/pipeline.py`

现在只有 config 说用 bm25/hybrid 时才创建 BM25Retriever。改成**始终创建实例**（但不建索引），这样用户切换到 bm25/hybrid 时可以懒加载索引。

### 第 6 步：给 `query()` 加覆盖参数

**文件**：`src/pipeline.py`

新签名：

```python
def query(
    self,
    question: str,
    return_contexts: bool = True,
    retrieval_method: str | None = None,   # 新增
    top_k: int | None = None,              # 新增
    use_reranker: bool | None = None,      # 新增
    use_query_rewrite: bool | None = None, # 新增
) -> dict[str, Any]:
```

逻辑：

* 传了 `retrieval_method` → 用它选策略，需要 BM25 就懒加载

* 传了 `top_k` → 传给检索策略

* 传了 `use_reranker=True` → 懒加载 Reranker 并重排序

* 传了 `use_query_rewrite=True` → 懒加载 QueryRewriter 并改写查询

* 都没传 → 走 config.yaml 默认值（向后兼容）

### 第 7 步：修改 qa\_demo.py，把 UI 值传进去

**文件**：`src/app_pages/qa_demo.py`

把 `pipeline.query(question)` 改成：

```python
result = pipeline.query(
    question,
    retrieval_method=st.session_state.retrieval_method,
    top_k=st.session_state.top_k,
    use_reranker=st.session_state.use_reranker,
    use_query_rewrite=st.session_state.use_query_rewrite,
)
```

加上错误处理：BM25 索引建不了、Reranker 加载失败等，给用户看友好的提示。

### 第 8 步：查询改写加策略选择器

**文件**：`src/app_pages/qa_demo.py`

勾了"启用查询改写"后，显示一个下拉框选策略（HyDE / Multi-Query）。

### 第 9 步：更新测试

**文件**：`tests/test_pipeline.py`

给 `query()` 的覆盖参数加测试。

### 第 10 步：跑 lint 和测试

```bash
pixi run lint
pixi run test
```

## 关键设计决策

1. **懒加载优于启动时全量加载**：不提前加载 Reranker 模型或建 BM25 索引。用户启用时才加载，首次查询慢一点，但启动快。

2. **覆盖参数优于改配置**：不改 `self.config`，而是把 UI 值作为参数传给 `query()`。这样 Pipeline 对 UI 设置是无状态的。

3. **优雅降级**：BM25 索引建不了（找不到 chunks 文件），给用户看清晰的错误提示，不崩溃。

4. **chunks\_dir 存储**：在 `__init__()`（从 meal\_config 算）、`build_index()`、`use_meal()` 三个地方存 `_chunks_dir`，懒加载 BM25 时用。

## 需要修改的文件

1. `src/retriever.py` — `retrieve()` 加 `top_k` 参数
2. `src/hybrid_retriever.py` — `retrieve()` 加 `top_k` 参数
3. `src/retrieval_strategies.py` — 把 `top_k` 传给底层 Retriever
4. `src/pipeline.py` — 加懒加载方法、`query()` 加覆盖参数、始终创建 BM25Retriever
5. `src/app_pages/qa_demo.py` — 传 UI 值、加策略选择器、错误处理
6. `tests/test_pipeline.py` — 加覆盖参数测试

