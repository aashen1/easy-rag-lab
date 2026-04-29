# Tasks

## Phase 1: 基础设施（无功能影响，纯重构）

- [x] Task 1: UI-01 — deep_merge 提取到 utils.py
  - [x] 1.1: 在 `src/utils.py` 中新增 `deep_merge(base, override)` 函数，从 `src/experiment.py` 复制实现
  - [x] 1.2: 修改 `src/experiment.py`，删除本地 `deep_merge` 定义，改为 `from src.utils import deep_merge`
  - [x] 1.3: 运行 `pixi run pytest tests/test_experiment.py -x` 确认测试通过
  - [x] 1.4: 运行 `pixi run lint` 确认无问题
  - [x] 1.5: 提交

## Phase 2: 底层组件支持动态 top_k

- [x] Task 2: UI-02 — Retriever 支持动态 top_k
  - [x] 2.1: 修改 `src/retriever.py` 的 `retrieve()` 方法，新增 `top_k: int | None = None` 参数，传入时覆盖 `self.top_k`
  - [x] 2.2: 修改 `src/hybrid_retriever.py` 的 `retrieve()` 方法，新增 `top_k: int | None = None` 参数，传入时覆盖 `self.top_k`
  - [x] 2.3: 运行 `pixi run pytest tests/test_retriever.py tests/test_hybrid_retriever.py -x` 确认测试通过
  - [x] 2.4: 运行 `pixi run lint` 确认无问题
  - [x] 2.5: 提交

- [x] Task 3: UI-03 — 策略类转发 top_k
  - [x] 3.1: 修改 `src/retrieval_strategies.py` 中 `VectorRetrievalStrategy.retrieve()`，将 `top_k` 参数转发给底层 `Retriever.retrieve()`
  - [x] 3.2: 修改 `BM25RetrievalStrategy.retrieve()`，将 `top_k` 参数转发给底层 `BM25Retriever.retrieve()`
  - [x] 3.3: 修改 `HybridRetrievalStrategy.retrieve()`，将 `top_k` 参数转发给底层 `HybridRetriever.retrieve()`
  - [x] 3.4: 运行 `pixi run pytest tests/test_retriever.py tests/test_bm25_retriever.py tests/test_hybrid_retriever.py -x` 确认测试通过
  - [x] 3.5: 运行 `pixi run lint` 确认无问题
  - [x] 3.6: 提交

## Phase 3: Pipeline 懒加载 + config_overrides（核心改动）

- [x] Task 4: UI-04 — Pipeline 懒加载机制
  - [x] 4.1: 在 `RAGPipeline.__init__()` 中新增 `self._chunks_dir: Path | None` 属性，从 meal_config 或 artifact cache 指针解析
  - [x] 4.2: 在 `build_index()` 末尾赋值 `self._chunks_dir`
  - [x] 4.3: 在 `use_meal()` 中赋值 `self._chunks_dir`
  - [x] 4.4: 修改 `_setup_retrievers()`，始终创建 `BM25Retriever` 实例（不建索引），使懒加载成为可能
  - [x] 4.5: 新增 `_ensure_bm25_index()` 方法：检查 `self.bm25_retriever.is_indexed()`，未索引则从 `self._chunks_dir` 构建
  - [x] 4.6: 新增 `_ensure_reranker()` 方法：检查 `self.reranker is None`，为 None 则加载模型
  - [x] 4.7: 新增 `_ensure_query_rewriter(strategy)` 方法：检查 `self.query_rewriter is None` 或策略不匹配，不匹配则重新初始化
  - [x] 4.8: 运行 `pixi run pytest tests/test_pipeline.py -x` 确认测试通过
  - [x] 4.9: 运行 `pixi run lint` 确认无问题
  - [x] 4.10: 提交

- [x] Task 5: UI-05 — Pipeline.query() 支持 config_overrides
  - [x] 5.1: 给 `query()` 新增 `config_overrides: dict[str, Any] | None = None` 参数
  - [x] 5.2: 当 `config_overrides` 不为 None 时，用 `deep_merge(self.config, config_overrides)` 计算有效配置
  - [x] 5.3: 从有效配置读取 `retrieval.method`，据此选择检索策略（调用 `_ensure_bm25_index()` 懒加载）
  - [x] 5.4: 从有效配置读取 `retrieval.top_k`，传给检索策略
  - [x] 5.5: 从有效配置读取 `retrieval.reranker.enabled`，为 True 时调用 `_ensure_reranker()` 并执行重排序
  - [x] 5.6: 从有效配置读取 `retrieval.query_rewrite.enabled` 和 `strategy`，为 True 时调用 `_ensure_query_rewriter()` 并执行改写
  - [x] 5.7: 当 `config_overrides` 为 None 时，走原逻辑（向后兼容）
  - [x] 5.8: 运行 `pixi run pytest tests/test_pipeline.py -x` 确认测试通过
  - [x] 5.9: 运行 `pixi run lint` 确认无问题
  - [x] 5.10: 提交

## Phase 4: Web UI 接入

- [x] Task 6: UI-06 — 侧边栏控件传入 Pipeline
  - [x] 6.1: 在 `qa_demo.py` 中构建 `config_overrides` 字典，从 `st.session_state` 读取控件值
  - [x] 6.2: 将 `pipeline.query(question)` 改为 `pipeline.query(question, config_overrides=config_overrides)`
  - [x] 6.3: 添加 try/except 包裹，捕获 `RetrievalError` 等异常，用 `st.error()` 显示友好提示
  - [x] 6.4: 运行 `pixi run lint` 确认无问题
  - [x] 6.5: 提交

- [x] Task 7: UI-07 — 查询改写策略选择器
  - [x] 7.1: 在侧边栏"启用查询改写"复选框下方，条件显示策略下拉框（HyDE / Multi-Query）
  - [x] 7.2: 将策略选择值纳入 `config_overrides` 的 `retrieval.query_rewrite.strategy` 字段
  - [x] 7.3: 运行 `pixi run lint` 确认无问题
  - [x] 7.4: 提交

## Phase 5: 测试补充 + 全量验证

- [x] Task 8: 补充测试
  - [x] 8.1: 在 `tests/test_pipeline.py` 中新增 `test_query_with_config_overrides_retrieval_method` 测试
  - [x] 8.2: 新增 `test_query_with_config_overrides_top_k` 测试
  - [x] 8.3: 新增 `test_query_with_config_overrides_reranker` 测试
  - [x] 8.4: 新增 `test_query_with_config_overrides_query_rewrite` 测试
  - [x] 8.5: 新增 `test_query_without_config_overrides_backward_compat` 测试
  - [x] 8.6: 运行 `pixi run pytest tests/ -x` 确认全量测试通过
  - [x] 8.7: 运行 `pixi run lint` 确认无问题
  - [x] 8.8: 提交

# Task Dependencies

- Task 2 和 Task 3 互相依赖（策略类需要 Retriever 先支持 top_k）
- Task 4 依赖 Task 1（懒加载需要 `deep_merge` 在 utils 中）
- Task 5 依赖 Task 3 和 Task 4（config_overrides 需要策略类转发 top_k 和懒加载机制）
- Task 6 依赖 Task 5（UI 需要 query() 支持 config_overrides）
- Task 7 依赖 Task 6（策略选择器是 UI 的一部分）
- Task 8 依赖 Task 5（测试需要 config_overrides 功能就绪）
- Task 1 独立，可最先执行
