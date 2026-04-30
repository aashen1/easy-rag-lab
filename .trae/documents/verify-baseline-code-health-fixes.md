# verify-baseline 代码健康修复计划

> 本计划针对 `verify-baseline` 分支已实现代码的审查发现，不是功能规划。
> 审查发现 6 个需修复问题 + 2 个可选改进，以下给出每个 Fix 的具体代码改动方案。

***

## Fix-1 🔴 死代码：`builtin_concurrent_workers` 未生效

### 问题

`evaluate_with_builtin()` 逐个调用 `evaluator.evaluate_single()`，是纯串行循环。
`BuiltinEvaluator.evaluate_batch()` 已实现 ThreadPoolExecutor 并发，但无调用方。
config.yaml 的 `builtin_concurrent_workers: 3` 形同虚设。

### 具体改动

**文件：`eval/runner/evaluation.py`**

将 `evaluate_with_builtin()` 的 for 循环替换为调用 `evaluator.evaluate_batch()`，然后在 batch 结果上做后处理（拆分 retrieval 指标为 doc/chunk/dedup 三组、构建 result dict、打日志）。

改动前（第 598-695 行）的核心逻辑：

```python
results = []
for sample in samples:
    # ... 构建 EvaluationSample ...
    eval_result = evaluator.evaluate_single(EvaluationSample(...))
    # ... 拆分 metrics，构建 result dict ...
    results.append(result)
return results
```

改动后：

```python
def evaluate_with_builtin(
    samples, evaluator, llm_config=None, retrieval_metrics=None, generation_metrics=None,
):
    # 1. 分离 error samples 和 valid samples
    error_results = []
    valid_samples_data = []
    for sample in samples:
        if "error" in sample:
            error_results.append({...})  # 保持原逻辑
        else:
            expected_answer = sample.get("ground_truth_excerpt")
            if not expected_answer and sample.get("expect_retrieval", True):
                expected_answer = sample.get("expected_answer")
            valid_samples_data.append((sample, EvaluationSample(
                question_id=sample["question_id"],
                question=sample["question"],
                answer=sample["answer"],
                contexts=sample.get("contexts", []),
                expected_sources=sample.get("expected_sources"),
                expected_answer=expected_answer,
                llm_config=llm_config,
                retrieval_metrics=retrieval_metrics,
                generation_metrics=generation_metrics,
                chunk_ids=sample.get("chunk_ids"),
                expected_chunks=sample.get("expected_chunks"),
                equivalence_groups=sample.get("equivalence_groups"),
                expect_retrieval=sample.get("expect_retrieval", True),
                expect_no_answer=sample.get("expect_no_answer", False),
                retrieved_sources=sample.get("retrieved_sources", []),
                question_type=sample.get("question_type"),
            )))

    # 2. 调用 evaluate_batch（内部已有并发逻辑）
    eval_samples = [es for _, es in valid_samples_data]
    batch_results = evaluator.evaluate_batch(
        samples=eval_samples,
        llm_config=llm_config,
        retrieval_metrics=retrieval_metrics,
        generation_metrics=generation_metrics,
    )

    # 3. 对 batch 结果做后处理（拆分 metrics、构建 result dict、打日志）
    valid_results = []
    for (sample, _), eval_result in zip(valid_samples_data, batch_results):
        result = _format_eval_result(sample, eval_result)  # 抽取公共后处理逻辑
        valid_results.append(result)

    # 4. 合并 error 和 valid 结果，保持原始顺序
    return _merge_results_in_order(samples, error_results, valid_results)
```

关键点：

* `evaluate_batch()` 内部已根据 `has_gen_metrics` 决定是否启用 ThreadPoolExecutor

* `evaluate_batch()` 从 `self._config["evaluation"]["builtin_concurrent_workers"]` 读取并发度

* 后处理逻辑（拆分 doc/chunk/dedup metrics、构建 result dict、打日志）抽取为 `_format_eval_result()` 辅助函数

* error sample 不进 batch，直接构造 error result

### 测试

* 在 `tests/test_speed_optimization.py` 中添加测试：mock BuiltinEvaluator，验证 `evaluate_batch` 被调用而非 `evaluate_single`

* 验证返回结果格式与原串行路径一致

***

## Fix-2 🔴 TokenTracker 线程安全

### 问题

并发查询时多线程共享同一 `TokenTracker`，`_records.append()` 无锁保护。

### 具体改动

**文件：`src/token_tracker.py`**

1. `__init__` 中添加锁：

```python
def __init__(self) -> None:
    self._records: list[TokenRecord] = []
    self._lock = threading.Lock()
```

1. `record()` 加锁：

```python
def record(self, category, model_name, usage, **metadata):
    rec = TokenRecord(...)
    with self._lock:
        self._records.append(rec)
```

1. `merge()` 加锁：

```python
def merge(self, other):
    with self._lock:
        self._records.extend(other._records)
```

1. 文件顶部添加 `import threading`

2. 只读方法（`get_total`、`get_summary_by_category` 等）不加锁——它们只在所有写入完成后被调用，不存在并发读写。

### 测试

* 多线程并发写入测试：启动 N 个线程各 record 100 次，断言最终 record\_count == N \* 100

***

## Fix-3 🔴 断点续跑缺少 CLI 入口

### 问题

每次运行都创建新时间戳目录，旧目录的断点数据无法被读取。CLI 没有 `--resume` 参数。

### 具体改动

**文件：`eval/run_experiment.py`**

添加 `--resume` 参数：

```python
parser.add_argument(
    "--resume",
    type=str,
    metavar="EXP_DIR",
    help="Resume an interrupted experiment from an existing experiment directory",
)
```

main() 中：

```python
elif args.config:
    result = run_experiment(
        config_path=args.config,
        ...
        resume_dir=args.resume,  # 新增
    )
```

**文件：`eval/runner/core.py`**

修改 `run_experiment()` 签名，添加 `resume_dir` 参数：

```python
def run_experiment(
    config_path, skip_preprocessing=False, use_llm_report=False,
    system_config_path="config.yaml", force_rerun=False,
    resume_dir: str | None = None,  # 新增
) -> dict[str, Any]:
```

核心逻辑改动：

```python
if resume_dir:
    exp_dir = Path(resume_dir)
    if not (exp_dir / "manifest.json").exists():
        raise ConfigurationError(f"Not a valid experiment directory: {resume_dir}")
    logger.info(f"Resuming experiment from: {exp_dir}")
else:
    exp_dir = exp_manager.create_experiment_dir(exp_config)
```

当 resume 时：

* 跳过 `save_snapshots()`（已存在）

* 从 manifest 读取 completed\_variants

* 在 manifest 中追加 `resumed_at` 时间戳和 `resume_count` 计数

**文件：`src/experiment.py`**

`ExperimentManager` 添加方法：

```python
def mark_resumed(self, exp_dir: Path) -> None:
    """Record that the experiment was resumed in the manifest."""
    # 读取 manifest，追加 resumed_at 时间戳，递增 resume_count
```

### 测试

* 测试 resume 时跳过已完成变体

* 测试 resume 时 manifest 中有 `resumed_at` 记录

* 测试无效 resume\_dir 抛异常

* 测试 resume + force\_rerun 组合（force\_rerun 应清空 completed\_variants 但仍在原目录运行）

***

## Fix-4 🟡 Checkpoint 写入非原子

### 问题

`_save_question_checkpoint()` 直接 `open("w")` + `json.dump()`，写到一半崩了留下半个 JSON。

### 具体改动

**文件：`eval/runner/evaluation.py`**

修改 `_save_question_checkpoint()`：

```python
import os

def _save_question_checkpoint(checkpoint_path, variant_name, experiment_name,
                              samples, total_questions, model_name=""):
    checkpoint_data = { ... }  # 不变
    tmp_path = checkpoint_path.with_suffix(".json.tmp")
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(checkpoint_data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, checkpoint_path)  # 原子重命名
    except OSError as e:
        logger.warning(f"Failed to save question checkpoint: {str(e)}")
        with contextlib.suppress(OSError):
            tmp_path.unlink()  # 清理临时文件
```

### 测试

* 现有测试应继续通过（行为不变）

* 可选：测试 tmp 文件存在但 replace 未执行时，旧 checkpoint 仍可读

***

## Fix-5 🟡 `deepcopy(pipeline)` 又贵又脆

### 问题

`copy.deepcopy(pipeline)` 复制了所有重量级对象（embedder、Qdrant 客户端），然后又覆盖 indexer 和 token\_tracker。

### 具体改动

**文件：`src/pipeline.py`**

添加 `clone_for_concurrency()` 方法：

```python
def clone_for_concurrency(self) -> "RAGPipeline":
    """Create a lightweight clone for concurrent query execution.

    Shares the indexer (Qdrant client, thread-safe for reads) and
    embedder (stateless inference). Creates new instances of components
    that hold per-call state (generator, reranker, query_rewriter).

    Returns:
        A new RAGPipeline instance suitable for use in a separate thread.
    """
    clone = RAGPipeline.__new__(RAGPipeline)
    clone.config = self.config
    clone.meal_name = self.meal_name
    clone.meal_config = self.meal_config
    clone._chunks_dir = self._chunks_dir

    # 共享：indexer（Qdrant 读操作线程安全）和 embedder（无状态推理）
    clone.indexer = self.indexer
    clone.embedder = self.embedder

    # 共享：token_tracker（Fix-2 加锁后线程安全）
    clone.token_tracker = self.token_tracker

    # 共享：profiler（只读使用）
    clone.profiler = self.profiler

    # 新建：generator（持有 last_token_usage 等每调用状态）
    llm_config = get_llm_config(self.config, "default")
    clone.generator = Generator(
        model_name=llm_config["model_name"],
        api_key=llm_config["api_key"],
        base_url=llm_config["base_url"],
        temperature=llm_config["temperature"],
        max_tokens=llm_config["max_tokens"],
        token_tracker=clone.token_tracker,
        system_prompt=self.config.get("generation", {}).get("system_prompt"),
        max_context_tokens=self.config.get("generation", {}).get("max_context_tokens"),
    )

    # 新建：retriever（持有 indexer + embedder 引用，轻量）
    clone._setup_retrievers()

    # 重置 lazy-init 组件（首次 query 时按需创建）
    clone.reranker = None
    clone.query_rewriter = None

    return clone
```

**文件：`eval/runner/evaluation.py`**

替换 `_collect_rag_samples_concurrent()` 中的 deepcopy：

```python
# 改动前
pipelines: list[RAGPipeline] = [pipeline]
for _ in range(concurrent_workers - 1):
    clone = copy.deepcopy(pipeline)
    clone.token_tracker = pipeline.token_tracker
    clone.indexer = pipeline.indexer
    pipelines.append(clone)

# 改动后
pipelines: list[RAGPipeline] = [pipeline]
for _ in range(concurrent_workers - 1):
    pipelines.append(pipeline.clone_for_concurrency())
```

同时移除 `import copy`（如果该文件只有这一处使用）。

### 测试

* 现有并发测试应继续通过

* 添加测试：验证 clone 的 generator 是独立实例（修改 clone.generator 不影响原 pipeline）

* 添加测试：验证 clone 的 indexer 是同一实例（共享）

***

## Fix-6 🟡 `safe_name` 清洗逻辑去重

### 问题

相同字符串清洗代码重复 4 处。

### 具体改动

**文件：`src/utils.py`**

添加函数：

```python
def sanitize_name(name: str) -> str:
    """Sanitize a name for use as a file system path component.

    Converts to lowercase, replaces spaces and hyphens with underscores,
    and removes all characters except alphanumeric and underscore.

    Args:
        name: The raw name string to sanitize.

    Returns:
        A sanitized string safe for use in file paths.
    """
    safe = name.lower().replace(" ", "_").replace("-", "_")
    return "".join(c for c in safe if c.isalnum() or c == "_")
```

**替换 4 处**：

| 文件                          | 行号      | 改动                                        |
| --------------------------- | ------- | ----------------------------------------- |
| `eval/runner/core.py`       | 80-81   | `safe_name = sanitize_name(variant_name)` |
| `eval/runner/core.py`       | 305-306 | `safe_name = sanitize_name(variant_name)` |
| `eval/runner/evaluation.py` | 176-177 | `safe_name = sanitize_name(variant_name)` |
| `src/experiment.py`         | 959-960 | `safe_name = sanitize_name(variant_name)` |

每处添加 `from src.utils import sanitize_name` import。

### 测试

* 添加 `tests/test_utils.py` 中的 `test_sanitize_name` 单元测试

* 运行现有测试确保无回归

***

## Fix-7 🟢 循环内 import 移到顶部

### 具体改动

**文件：`eval/runner/core.py`**

* 第 532-533 行和第 584-585 行的 `from src.token_tracker import DetailedTokenUsage` 移到文件顶部 import 区

***

## Fix-8 🟢 并发路径 checkpoint 粒度改进

### 问题

串行路径每做完一题就保存 checkpoint；并发路径等所有任务完成后才保存。

### 具体改动

**文件：`eval/runner/evaluation.py`**

在 `_collect_rag_samples_concurrent()` 中，将 checkpoint 保存从"全部完成后按序保存"改为"每个 future 完成后立即保存"：

```python
_samples_lock = threading.Lock()
_samples: list[tuple[int, dict]]] = []  # (original_idx, result)

def _on_future_done(future, idx):
    try:
        result = future.result()
    except Exception as e:
        result = {...}  # error result
    if not result.get("_skip"):
        result.pop("_skip", None)
        with _samples_lock:
            _samples.append((idx, result))
            # 按 idx 排序后保存 checkpoint
            sorted_samples = [r for _, r in sorted(_samples)]
            if checkpoint_path is not None:
                _save_question_checkpoint(
                    checkpoint_path, variant_name, experiment_name,
                    sorted_samples, len(questions), model_name=model_name,
                )

for future in as_completed(future_to_idx):
    idx = future_to_idx[future]
    _on_future_done(future, idx)
```

注意：此改动依赖 Fix-4（原子写入），否则并发保存 checkpoint 可能写到一半被另一个线程覆盖。

***

## 执行顺序

```
Fix-6 (safe_name 去重)     ← 最简单，无依赖，热身
  ↓
Fix-7 (循环 import)         ← 最简单，热身
  ↓
Fix-4 (checkpoint 原子写入)  ← 独立，Fix-8 依赖它
  ↓
Fix-2 (TokenTracker 加锁)   ← 独立，Fix-5 依赖它
  ↓
Fix-1 (死代码修复)           ← 需理解 evaluate_batch 接口
  ↓
Fix-5 (deepcopy 替换)       ← 依赖 Fix-2（token_tracker 加锁后才能安全共享）
  ↓
Fix-3 (断点续跑 CLI)        ← 最复杂，涉及多文件
  ↓
Fix-8 (并发 checkpoint)     ← 依赖 Fix-4
```

每个 Fix 完成后：

1. 运行 `pixi run lint` 确保代码格式正确
2. 运行相关 pytest 测试确保无回归
3. 按 commit-rule 原子提交

