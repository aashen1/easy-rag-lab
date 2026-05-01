# 冒烟测试修复报告

**日期**: 2026-04-30
**任务**: 运行 `pixi run exp exp_pack_260430/00_smoke_all_variants` 冒烟测试并修复问题
**状态**: ✅ 已完成

---

## 问题概览

在运行冒烟测试过程中，共发现并修复了 **4 个问题**：

| # | 问题 | 严重程度 | 影响范围 |
|---|------|---------|---------|
| 1 | MetricResolver 无法过滤不可用后端 | 高 | 所有使用 `backend_priority` 的实验 |
| 2 | BuiltinEvaluator 属性名错误 | 高 | 所有使用 builtin 评测的实验 |
| 3 | Qdrant 客户端关闭后无法重用 | 高 | 使用 indexer 缓存的实验 |
| 4 | Qdrant 存储目录并发冲突 | 高 | 所有实验变体切换 |

---

## 问题 1: MetricResolver 无法过滤不可用后端

### 问题现象

```
ERROR | eval.runner.core:run_variant_evaluation:316 - Failed to evaluate variant 'rerank_top5':
Backend(s) ['ragas'] in backend_priority not found in evaluators. Available: ['builtin']
```

### 根因分析

配置文件 `00_smoke_all_variants.yaml` 中设置了：

```yaml
evaluation:
  backends: ["builtin"]
  backend_priority: ["builtin", "ragas"]
```

但实际只有 `builtin` 后端可用。`MetricResolver.__init__` 在检测到 `backend_priority` 中有不可用的后端时，直接抛出 `ValueError`，导致整个变体评测失败。

### 修复方案

修改 `eval/metrics/metric_resolver.py`，将严格报错改为警告并过滤：

```python
# 修复前
if missing:
    raise ValueError(
        f"Backend(s) {missing} in backend_priority not found "
        f"in evaluators. Available: {list(evaluators.keys())}"
    )
self.backend_priority = backend_priority

# 修复后
if missing:
    logger.warning(
        f"Backend(s) {missing} in backend_priority not found "
        f"in evaluators. Available: {list(evaluators.keys())}. "
        f"Filtering to available backends only."
    )
self.backend_priority = [b for b in backend_priority if b in evaluators]
if not self.backend_priority:
    raise ValueError(
        f"No valid backends in backend_priority. "
        f"Requested: {backend_priority}, Available: {list(evaluators.keys())}"
    )
```

### 设计考量

- **优雅降级**: 当部分后端不可用时，自动过滤到可用后端，而不是直接失败
- **用户可见性**: 通过警告日志让用户知道后端被过滤
- **安全边界**: 如果所有后端都不可用，仍然报错

---

## 问题 2: BuiltinEvaluator 属性名错误

### 问题现象

```
ERROR | eval.runner.core:run_variant_evaluation:321 - Failed to evaluate variant 'overlap_32':
'BuiltinEvaluator' object has no attribute '_config'
```

### 根因分析

`BuiltinEvaluator.evaluate_batch()` 方法中使用了 `self._config`：

```python
max_workers = self._config.get("evaluation", {}).get(
    "builtin_concurrent_workers", 3
)
```

但父类 `BaseEvaluator.__init__` 保存的是 `self.config`（无下划线）：

```python
class BaseEvaluator(ABC):
    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}
```

### 修复方案

修改 `eval/evaluators/builtin_evaluator.py`，统一使用 `self.config`：

```python
# 修复前
max_workers = self._config.get("evaluation", {}).get(...)

# 修复后
max_workers = self.config.get("evaluation", {}).get(...)
```

---

## 问题 3: Qdrant 客户端关闭后无法重用

### 问题现象

```
ERROR | src.retriever:retrieve:101 - Failed to retrieve results:
QdrantLocal instance is closed. Please create a new instance.
```

### 根因分析

实验框架使用 `indexer_cache` 缓存 `VectorIndexer` 实例，以便相同 chunker 配置的变体可以重用索引。但问题是：

1. 变体 A 创建 indexer 并放入缓存
2. 变体 A 完成后调用 `pipeline.close()` 关闭了 indexer
3. 变体 B 尝试重用缓存的 indexer，但客户端已关闭

### 修复方案

#### 3.1 添加状态跟踪和重开方法

修改 `src/indexer.py`，添加 `is_closed()` 和 `reopen()` 方法：

```python
class VectorIndexer:
    def __init__(self, ...):
        ...
        self._is_closed = False

    def close(self) -> None:
        if hasattr(self, "client") and self.client is not None:
            self.client.close()
            self._is_closed = True

    def is_closed(self) -> bool:
        return self._is_closed

    def reopen(self) -> None:
        if self._is_closed:
            logger.info(f"Reopening Qdrant client for collection: {self.collection_name}")
            self.client = QdrantClient(path=str(self.persist_dir))
            self._is_closed = False
```

#### 3.2 在重用缓存时检查并重开

修改 `eval/runner/core.py`：

```python
indexer = indexer_cache[chunker_hash]
if indexer.is_closed():
    indexer.reopen()
```

---

## 问题 4: Qdrant 存储目录并发冲突

### 问题现象

```
ERROR | src.indexer:__init__:56 - Failed to initialize Qdrant client:
Storage folder data\vector_store is already accessed by another instance of Qdrant client.
If you require concurrent access, use Qdrant server instead.
```

### 根因分析

所有 `VectorIndexer` 实例使用同一个存储目录 `data\vector_store`。Qdrant Local 模式使用文件锁，不支持多个客户端同时访问同一目录。

问题流程：
1. 变体 A 创建 indexer_1（collection_a），客户端打开存储目录
2. 变体 A 完成，indexer_1 保持打开状态（为了缓存）
3. 变体 B 需要不同的 collection_b，尝试创建 indexer_2
4. indexer_2 无法打开存储目录，因为 indexer_1 仍持有文件锁

### 修复方案

#### 4.1 RAGPipeline 不再自动创建 indexer

修改 `src/pipeline.py`，将 `self.indexer` 初始化为 `None`：

```python
# 修复前
self.indexer = VectorIndexer(
    persist_dir=vector_store_config["persist_dir"],
    collection_name=collection_name,
    distance=vector_store_config["distance"],
)

# 修复后
self.indexer: VectorIndexer | None = None
```

#### 4.2 创建新 indexer 前关闭所有缓存的客户端

修改 `eval/runner/core.py`：

```python
if indexer_cache is not None:
    for cached_indexer in indexer_cache.values():
        if not cached_indexer.is_closed():
            cached_indexer.close()
```

#### 4.3 重开缓存 indexer 前关闭其他客户端

```python
indexer = indexer_cache[chunker_hash]
if indexer.is_closed():
    for cached_indexer in indexer_cache.values():
        if not cached_indexer.is_closed():
            cached_indexer.close()
    indexer.reopen()
```

#### 4.4 优化 pipeline.close() 逻辑

```python
if indexer_cache is None:
    pipeline.close()
else:
    pipeline.indexer = None
```

当使用缓存时，不关闭 indexer，保持其打开状态供后续变体使用。

---

## 测试结果

修复后，冒烟测试成功完成：

```
Experiment completed: exp_20260430_122934_smoke_all_variants
Results saved to: data\exp_reports\exp_20260430_122934_smoke_all_variants

TOKEN USAGE SUMMARY
Category               |      Input |     Output |      Total
------------------------------------------------------------------------
rag_qa                 |     66,218 |     11,360 |     77,578
```

20 个变体全部评测完成，无 ERROR 日志（仅有预期的 WARNING）。

---

## 提交记录

本次修复拆分为 4 个独立提交：

1. `fix: MetricResolver gracefully filter unavailable backends`
2. `fix: BuiltinEvaluator use correct config attribute name`
3. `feat: VectorIndexer support reopen closed client`
4. `fix: resolve Qdrant storage directory conflict in experiment runner`

---

## 经验总结

### 1. 资源生命周期管理

在使用缓存共享资源（如 Qdrant 客户端）时，需要明确：
- 资源的所有权归属
- 资源的打开/关闭时机
- 多个使用者之间的协调机制

### 2. 优雅降级 vs 严格校验

对于配置错误，需要权衡：
- **严格校验**：尽早发现问题，但可能过于僵化
- **优雅降级**：提高可用性，但可能隐藏问题

本案例中，`backend_priority` 使用优雅降级更合适，因为用户可能在不同环境中运行（有的有 ragas，有的没有）。

### 3. 属性命名一致性

Python 中 `_attr` 通常表示"受保护"或"内部使用"。在本案例中，父类使用 `config`，子类误用 `_config`，导致属性名不一致。建议：
- 使用类型检查工具（mypy）捕获此类错误
- 代码审查时关注继承关系中的属性命名

### 4. Qdrant Local 的限制

Qdrant Local 模式使用文件锁，不支持并发访问。对于实验场景，解决方案：
- 使用 Qdrant Server 模式
- 在实验框架中管理客户端生命周期（本次采用）
- 为不同 collection 使用不同存储目录（需要更多磁盘空间）
