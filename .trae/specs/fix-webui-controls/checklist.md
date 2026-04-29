# Web UI 侧边栏控件生效验收清单

## Phase 1: 基础设施

- [x] `src/utils.py` 中存在 `deep_merge(base, override)` 函数
- [x] `src/experiment.py` 中无本地 `deep_merge` 定义，通过 `from src.utils import deep_merge` 导入
- [x] `pixi run pytest tests/test_experiment.py -x` 通过

## Phase 2: 底层组件动态 top_k

- [x] `src/retriever.py` 的 `retrieve()` 方法接受 `top_k: int | None = None` 参数
- [x] `src/hybrid_retriever.py` 的 `retrieve()` 方法接受 `top_k: int | None = None` 参数
- [x] `src/retrieval_strategies.py` 三个策略类的 `retrieve()` 方法将 `top_k` 转发给底层 Retriever
- [x] 传入 `top_k` 时覆盖实例属性，不传入时使用 `self.top_k`（向后兼容）
- [x] `pixi run pytest tests/test_retriever.py tests/test_hybrid_retriever.py -x` 通过

## Phase 3: Pipeline 懒加载 + config_overrides

- [x] `RAGPipeline` 存在 `self._chunks_dir: Path | None` 属性
- [x] `_setup_retrievers()` 始终创建 `BM25Retriever` 实例
- [x] `_ensure_bm25_index()` 方法存在，未索引时从 `_chunks_dir` 构建
- [x] `_ensure_reranker()` 方法存在，未加载时加载模型
- [x] `_ensure_query_rewriter(strategy)` 方法存在，未初始化时初始化
- [x] `query()` 方法接受 `config_overrides: dict[str, Any] | None = None` 参数
- [x] `config_overrides=None` 时走原逻辑（向后兼容）
- [x] `config_overrides` 非 None 时，用 `deep_merge` 计算有效配置并据此选择策略
- [x] `_chunks_dir` 不可用时抛出 `RetrievalError` 并附带清晰错误信息
- [x] `pixi run pytest tests/test_pipeline.py -x` 通过

## Phase 4: Web UI 接入

- [x] `qa_demo.py` 中 `pipeline.query(question)` 改为 `pipeline.query(question, config_overrides=config_overrides)`
- [x] `config_overrides` 从 `st.session_state` 的控件值构建
- [x] 侧边栏"检索策略"下拉框的值生效（切换到 hybrid 时使用混合检索）
- [x] 侧边栏"Top-K"滑块的值生效（滑到 3 时返回最多 3 个结果）
- [x] 侧边栏"启用 Reranker"复选框生效（勾选时执行重排序）
- [x] 侧边栏"启用查询改写"复选框生效（勾选时执行查询改写）
- [x] 勾选"启用查询改写"后出现策略下拉框（HyDE / Multi-Query）
- [x] 策略下拉框的值生效
- [x] BM25 索引不可用时 UI 显示友好错误提示，不崩溃
- [x] Reranker 加载失败时 UI 显示友好错误提示，不崩溃

## Phase 5: 测试 + 全量验证

- [x] `tests/test_pipeline.py` 中存在 `config_overrides` 相关测试
- [x] 测试覆盖：检索策略覆盖、top_k 覆盖、Reranker 启用、查询改写启用、向后兼容
- [x] `pixi run pytest tests/ -x` 全量测试通过
- [x] `pixi run lint` 全局通过

## 全局验收

- [x] CLI（`main.py`）无需任何修改，功能不受影响
- [x] 实验系统（`eval/runner/core.py`）无需任何修改，功能不受影响
- [x] 侧边栏 4 个控件全部生效，不再是"假按钮"
- [x] 新增的 `config_overrides` 机制为将来的 Web UI 配置编辑器、CLI `--config-overrides` 参数预留了扩展路径
