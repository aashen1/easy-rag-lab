# 修复计划：Streamlit 侧边栏控件"造假"问题

## 问题直白解释

```
Streamlit 进程启动
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
       ├─ 选了"hybrid"检索 ── 写入 st.session_state
       ├─ 勾了"启用 Reranker" ── 写入 st.session_state
       │
       └─ pipeline.query(question)  ← 完全没传任何参数！
            └─ 走的还是 config.yaml 默认值
```

## 对现有 CLI 功能的影响评估

**影响为零。** 所有改动都是纯增量式的：

1. `query()` 新增的参数全部有默认值 `None`，不传就走原逻辑
2. 懒加载方法是新增的，不影响已有代码路径
3. CLI（`main.py`）不需要任何修改
4. 实验系统（`eval/runner/core.py`）不需要任何修改

## 架构思考：双端对齐的基石

### 现状：三种"覆盖配置"的模式，各干各的

| 模式                              | 使用者            | 实现方式                                      | 问题                      |
| ------------------------------- | -------------- | ----------------------------------------- | ----------------------- |
| LLM Preset 选择器                  | CLI / Pipeline | `get_llm_config(config, preset_name)`     | 只覆盖 LLM，不覆盖其他           |
| deep\_merge + config\_overrides | 实验系统           | `merge_config()` + 暴力替换 `pipeline.config` | Pipeline 不原生支持，靠外部 hack |
| 侧边栏控件                           | Web UI         | 写入 `st.session_state` 但不传入 Pipeline       | **完全是假的**               |

### 目标：统一为一种模式

**`config_overrides`** **作为 Pipeline 的原生能力**，CLI 和 Web UI 都是这种模式的使用者：

```
config.yaml（基线默认）
  │
  ├─ CLI 用户 ── 通过命令行参数构建 config_overrides
  │    pixi run interactive --config-overrides '{"retrieval": {"method": "hybrid"}}'
  │
  ├─ Web UI 用户 ── 通过侧边栏控件构建 config_overrides
  │    pipeline.query(question, config_overrides={...})
  │
  └─ 实验系统 ── 通过 variant.config_overrides 构建（已有，可逐步迁移）
       merge_config() → pipeline.query(question, config_overrides=merged_overrides)
```

### 为什么选 `config_overrides` 而不是单独的参数？

| 方案                                                           | 现在（4 个控件） | 将来（完整配置编辑）        |
| ------------------------------------------------------------ | --------- | ----------------- |
| 单独参数 `query(question, retrieval_method=..., top_k=..., ...)` | 还行        | 每加一个配置项就加一个参数，爆炸  |
| `config_overrides` 字典                                        | 稍多几行代码    | 天然支持任意配置项，和实验系统一致 |

**选** **`config_overrides`**，因为：

1. 和实验系统的 `variant.config_overrides` 是同一个概念，心智模型统一
2. 将来做 Web UI 配置编辑器时，直接把表单值转成 `config_overrides` 字典就行
3. 不需要为每个配置项加一个函数参数

### 懒加载策略

不是启动时把所有组件都加载（太慢太费内存），而是**按需加载**：

| 组件            | 加载时机              | 首次耗时        | 内存占用    |
| ------------- | ----------------- | ----------- | ------- |
| BM25 索引       | 用户选 bm25/hybrid 时 | 几秒\~几十秒     | 中（内存索引） |
| Reranker 模型   | 用户勾"启用 Reranker"时 | 10-30 秒     | \~1GB   |
| QueryRewriter | 用户勾"启用查询改写"时      | <1 秒（调 API） | 极小      |

加载一次后缓存，后续查询不再重复加载。

## 实施步骤

### 第 1 步：把 `deep_merge` 提取到 `utils.py`

**文件**：`src/utils.py`、`src/experiment.py`

现在 `deep_merge()` 定义在 `experiment.py` 里，Web UI 和 Pipeline 不方便用。把它移到 `utils.py`，`experiment.py` 改为从 `utils` 导入。

这是纯重构，不影响任何功能。

### 第 2 步：让 Retriever 支持动态 top\_k

**文件**：`src/retriever.py`

`retrieve(query)` → `retrieve(query, top_k=None)`，传了就用传的，没传用 `self.top_k`。

### 第 3 步：让 HybridRetriever 支持动态 top\_k

**文件**：`src/hybrid_retriever.py`

同上。

### 第 4 步：修复策略类，把 top\_k 传下去

**文件**：`src/retrieval_strategies.py`

`VectorRetrievalStrategy.retrieve()` 现在收到了 `top_k` 但完全忽略了。修一下。

### 第 5 步：给 Pipeline 加懒加载方法

**文件**：`src/pipeline.py`

三个方法：

* `_ensure_bm25_index()` — 从 chunks 文件建 BM25 索引（如果还没建）

* `_ensure_reranker()` — 加载 Reranker 模型（如果还没加载）

* `_ensure_query_rewriter(strategy)` — 初始化 QueryRewriter（如果还没初始化）

同时：

* 存 `self._chunks_dir: Path | None`（在 `__init__`、`build_index`、`use_meal` 三个地方赋值）

* 始终创建 `BM25Retriever` 实例（在 `_setup_retrievers` 里），但不建索引

### 第 6 步：给 `query()` 加 `config_overrides` 参数

**文件**：`src/pipeline.py`

```python
def query(
    self,
    question: str,
    return_contexts: bool = True,
    config_overrides: dict[str, Any] | None = None,  # 新增
) -> dict[str, Any]:
```

逻辑：

1. 如果 `config_overrides` 不为 None，用 `deep_merge(self.config, config_overrides)` 算出有效配置
2. 从有效配置中读取 `retrieval.method`、`retrieval.top_k`、`retrieval.reranker.enabled`、`retrieval.query_rewrite.enabled`
3. 根据这些值选择策略、懒加载组件
4. 如果 `config_overrides` 为 None，走原逻辑（向后兼容）

### 第 7 步：修改 qa\_demo.py，构建 config\_overrides 并传入

**文件**：`src/app_pages/qa_demo.py`

```python
config_overrides = {
    "retrieval": {
        "method": st.session_state.retrieval_method,
        "top_k": st.session_state.top_k,
        "reranker": {"enabled": st.session_state.use_reranker},
        "query_rewrite": {
            "enabled": st.session_state.use_query_rewrite,
            "strategy": st.session_state.query_rewrite_strategy,
        },
    }
}
result = pipeline.query(question, config_overrides=config_overrides)
```

加上错误处理和友好提示。

### 第 8 步：查询改写加策略选择器

**文件**：`src/app_pages/qa_demo.py`

勾了"启用查询改写"后，显示下拉框选 HyDE / Multi-Query。

### 第 9 步：更新测试

**文件**：`tests/test_pipeline.py`

给 `query()` 的 `config_overrides` 参数加测试。

### 第 10 步：跑 lint 和测试

```bash
pixi run lint
pixi run test
```

## 关键设计决策

1. **`config_overrides`** **优于单独参数**：和实验系统一致，可扩展，将来做配置编辑器时天然适配。

2. **懒加载优于启动时全量加载**：用户启用某功能时才加载，首次查询慢但启动快。

3. **`deep_merge`** **提取到 utils**：让 Pipeline、Web UI、CLI 都能用，不依赖 experiment 模块。

4. **向后兼容**：`config_overrides=None` 时走原逻辑，CLI 和实验系统零影响。

5. **优雅降级**：BM25 索引建不了（找不到 chunks），给用户看清晰提示，不崩溃。

## 将来扩展路径（本次不做，但架构不阻碍）

* **CLI 加** **`--config-overrides`** **参数**：`pixi run interactive --config-overrides '{"retrieval": {"method": "hybrid"}}'`

* **Web UI 配置编辑器**：表单 → `config_overrides` 字典 → `pipeline.query()`

* **实验系统集成**：实验运行器从"暴力替换 pipeline.config"改为"传 config\_overrides 给 query()"

* **LLM 预设切换**：Web UI 下拉框选 preset → `config_overrides = {"active_mode": "sonnet"}`

## 需要修改的文件

1. `src/utils.py` — 从 experiment.py 移入 `deep_merge()`
2. `src/experiment.py` — 改为从 utils 导入 `deep_merge`
3. `src/retriever.py` — `retrieve()` 加 `top_k` 参数
4. `src/hybrid_retriever.py` — `retrieve()` 加 `top_k` 参数
5. `src/retrieval_strategies.py` — 把 `top_k` 传给底层 Retriever
6. `src/pipeline.py` — 加懒加载方法、`query()` 加 `config_overrides`、始终创建 BM25Retriever
7. `src/app_pages/qa_demo.py` — 构建 config\_overrides 并传入、加策略选择器、错误处理
8. `tests/test_pipeline.py` — 加 config\_overrides 测试
