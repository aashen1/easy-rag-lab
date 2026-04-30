# Web UI 侧边栏控件生效 Spec

## Why

Streamlit Web UI 侧边栏的 4 个控件（检索策略、Top-K、Reranker、查询改写）是"假按钮"——它们只写入 `st.session_state`，从未传入 `pipeline.query()`，Pipeline 始终走 `config.yaml` 默认值。这不仅是功能缺陷，更暴露了 Pipeline 缺少运行时配置覆盖能力的架构短板——将来的 Web UI 配置编辑器、CLI `--config-overrides` 参数、实验系统集成都需要这个能力。

## What Changes

- 将 `deep_merge()` 从 `experiment.py` 提取到 `utils.py`，使其成为 Pipeline 和 Web UI 可复用的公共工具
- 给 `RAGPipeline.query()` 新增 `config_overrides` 参数，支持运行时覆盖任意配置项
- 给 Pipeline 新增懒加载机制（BM25 索引、Reranker 模型、QueryRewriter），按需初始化组件
- 给 `Retriever`、`HybridRetriever`、策略类新增 `top_k` 参数，支持动态调整检索数量
- 修改 `qa_demo.py`，将侧边栏控件值构建为 `config_overrides` 传入 `pipeline.query()`
- 在侧边栏新增查询改写策略选择器（HyDE / Multi-Query）

## Impact

- Affected code: `src/pipeline.py`、`src/utils.py`、`src/experiment.py`、`src/retriever.py`、`src/hybrid_retriever.py`、`src/retrieval_strategies.py`、`src/app_pages/qa_demo.py`
- Affected tests: `tests/test_pipeline.py`、`tests/test_retriever.py`、`tests/test_hybrid_retriever.py`
- **不影响**：CLI（`main.py`）、实验系统（`eval/runner/core.py`）——所有新增参数默认值为 `None`，不传走原逻辑

## ADDED Requirements

### Requirement: UI-01 — deep_merge 提取为公共工具

系统 SHALL 将 `src/experiment.py` 中的 `deep_merge()` 函数移至 `src/utils.py`，`experiment.py` 改为从 `utils` 导入。函数行为不变。

#### Scenario: deep_merge 在 utils.py 中定义
- **WHEN** 查看 `src/utils.py`
- **THEN** 存在 `deep_merge(base, override)` 函数，签名和行为与原 `experiment.py` 中完全一致

#### Scenario: experiment.py 无重复定义
- **WHEN** 查看 `src/experiment.py`
- **THEN** `deep_merge` 通过 `from src.utils import deep_merge` 导入，无本地定义

#### Scenario: 向后兼容
- **WHEN** 运行 `pixi run pytest tests/test_experiment.py -x`
- **THEN** 全部通过

### Requirement: UI-02 — Retriever 支持动态 top_k

系统 SHALL 给 `Retriever.retrieve()` 和 `HybridRetriever.retrieve()` 新增可选 `top_k` 参数。传入时覆盖实例属性，不传入时使用 `self.top_k`。

#### Scenario: Retriever 动态 top_k
- **WHEN** 调用 `retriever.retrieve(query, top_k=8)`
- **THEN** 返回最多 8 个结果，`self.top_k` 不被修改

#### Scenario: 默认 top_k
- **WHEN** 调用 `retriever.retrieve(query)` 不传 top_k
- **THEN** 使用 `self.top_k`，行为与改动前完全一致

#### Scenario: HybridRetriever 动态 top_k
- **WHEN** 调用 `hybrid_retriever.retrieve(query, top_k=3)`
- **THEN** 返回最多 3 个融合结果

### Requirement: UI-03 — 策略类转发 top_k

系统 SHALL 修改 `retrieval_strategies.py` 中的三个策略类，将 `retrieve(query, top_k)` 的 `top_k` 参数转发给底层 Retriever。

#### Scenario: VectorRetrievalStrategy 转发 top_k
- **WHEN** 调用 `VectorRetrievalStrategy.retrieve(query, top_k=7)`
- **THEN** 底层 `Retriever.retrieve(query, top_k=7)` 被调用

#### Scenario: BM25RetrievalStrategy 转发 top_k
- **WHEN** 调用 `BM25RetrievalStrategy.retrieve(query, top_k=6)`
- **THEN** 底层 `BM25Retriever.retrieve(query, top_k=6)` 被调用

#### Scenario: HybridRetrievalStrategy 转发 top_k
- **WHEN** 调用 `HybridRetrievalStrategy.retrieve(query, top_k=4)`
- **THEN** 底层 `HybridRetriever.retrieve(query, top_k=4)` 被调用

### Requirement: UI-04 — Pipeline 懒加载机制

系统 SHALL 给 `RAGPipeline` 新增三个懒加载方法和一个 chunks_dir 存储属性：

1. `_ensure_bm25_index()` — 如果 BM25 索引未构建，从 `_chunks_dir` 下的 JSONL 文件构建
2. `_ensure_reranker()` — 如果 Reranker 模型未加载，加载交叉编码器模型
3. `_ensure_query_rewriter(strategy)` — 如果 QueryRewriter 未初始化，用指定策略初始化

同时：
- 新增 `self._chunks_dir: Path | None` 属性，在 `__init__`、`build_index`、`use_meal` 中赋值
- 修改 `_setup_retrievers()` 始终创建 `BM25Retriever` 实例（但不建索引），使懒加载成为可能

#### Scenario: BM25 懒加载
- **WHEN** Pipeline 初始化时 config 为 `method: "vector"`，后通过 `config_overrides` 切换为 `method: "hybrid"`
- **THEN** 首次查询时自动构建 BM25 索引，后续查询复用已建索引

#### Scenario: Reranker 懒加载
- **WHEN** Pipeline 初始化时 config 为 `reranker.enabled: false`，后通过 `config_overrides` 启用
- **THEN** 首次查询时加载 Reranker 模型，后续查询复用已加载模型

#### Scenario: QueryRewriter 懒加载
- **WHEN** Pipeline 初始化时 config 为 `query_rewrite.enabled: false`，后通过 `config_overrides` 启用
- **THEN** 首次查询时初始化 QueryRewriter，后续查询复用

#### Scenario: chunks_dir 不可用时的优雅降级
- **WHEN** `_chunks_dir` 为 None 或路径不存在，且用户请求 BM25/hybrid 检索
- **THEN** 抛出 `RetrievalError` 并附带清晰错误信息，不崩溃

### Requirement: UI-05 — Pipeline.query() 支持 config_overrides

系统 SHALL 给 `RAGPipeline.query()` 新增 `config_overrides: dict[str, Any] | None = None` 参数。

当 `config_overrides` 不为 None 时：
1. 用 `deep_merge(self.config, config_overrides)` 计算有效配置
2. 从有效配置中读取 `retrieval.method`、`retrieval.top_k`、`retrieval.reranker.enabled`、`retrieval.query_rewrite.enabled`
3. 根据有效配置选择检索策略、决定是否懒加载组件、决定是否重排序、决定是否改写查询

当 `config_overrides` 为 None 时，走原逻辑（向后兼容）。

#### Scenario: 覆盖检索策略
- **WHEN** 调用 `pipeline.query(question, config_overrides={"retrieval": {"method": "hybrid"}})`
- **THEN** 使用混合检索策略，BM25 索引按需懒加载

#### Scenario: 覆盖 top_k
- **WHEN** 调用 `pipeline.query(question, config_overrides={"retrieval": {"top_k": 8}})`
- **THEN** 检索返回最多 8 个结果

#### Scenario: 启用 Reranker
- **WHEN** 调用 `pipeline.query(question, config_overrides={"retrieval": {"reranker": {"enabled": true}}})`
- **THEN** 对检索结果执行重排序

#### Scenario: 启用查询改写
- **WHEN** 调用 `pipeline.query(question, config_overrides={"retrieval": {"query_rewrite": {"enabled": true, "strategy": "hyde"}}})`
- **THEN** 先用 HyDE 策略改写查询，再检索

#### Scenario: 向后兼容
- **WHEN** 调用 `pipeline.query(question)` 不传 config_overrides
- **THEN** 行为与改动前完全一致

### Requirement: UI-06 — 侧边栏控件传入 Pipeline

系统 SHALL 修改 `qa_demo.py`，将侧边栏控件值构建为 `config_overrides` 字典并传入 `pipeline.query()`。

具体改动：
1. 将 `pipeline.query(question)` 改为 `pipeline.query(question, config_overrides=config_overrides)`
2. `config_overrides` 从 `st.session_state` 的控件值构建
3. 懒加载失败时在 UI 显示友好错误提示（st.error），不崩溃

#### Scenario: 检索策略切换生效
- **WHEN** 用户在侧边栏选择"hybrid"并发送问题
- **THEN** 返回混合检索的结果（与纯向量检索不同）

#### Scenario: Top-K 调整生效
- **WHEN** 用户在侧边栏将 Top-K 滑到 3 并发送问题
- **THEN** 返回最多 3 个检索结果

#### Scenario: Reranker 启用生效
- **WHEN** 用户勾选"启用 Reranker"并发送问题
- **THEN** 检索结果经过重排序

#### Scenario: 查询改写启用生效
- **WHEN** 用户勾选"启用查询改写"并发送问题
- **THEN** 查询先被改写再检索

#### Scenario: BM25 索引不可用的友好提示
- **WHEN** 用户选择 BM25/hybrid 但 chunks 目录不存在
- **THEN** UI 显示错误提示"BM25 索引不可用：找不到 chunks 数据目录"，不崩溃

### Requirement: UI-07 — 查询改写策略选择器

系统 SHALL 在侧边栏"启用查询改写"复选框被勾选时，显示下拉框让用户选择改写策略（HyDE / Multi-Query）。

#### Scenario: 策略选择器显示
- **WHEN** 用户勾选"启用查询改写"
- **THEN** 下方出现下拉框，选项为"HyDE（假设性文档）"和"Multi-Query（多查询）"

#### Scenario: 策略选择器隐藏
- **WHEN** 用户取消勾选"启用查询改写"
- **THEN** 策略选择下拉框消失

#### Scenario: 策略选择生效
- **WHEN** 用户选择"Multi-Query"并发送问题
- **THEN** 使用 Multi-Query 策略改写查询

## MODIFIED Requirements

无。所有改动保持行为不变（`config_overrides=None` 时走原逻辑）。

## REMOVED Requirements

无。
