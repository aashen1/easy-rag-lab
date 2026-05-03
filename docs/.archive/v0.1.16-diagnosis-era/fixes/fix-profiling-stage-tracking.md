# Profiling 阶段追踪修复计划

## 问题诊断

### 当前问题

| 阶段 | 名称     | 预期内容      | 实际内容                              | 问题            |
| -- | ------ | --------- | --------------------------------- | ------------- |
| S1 | PDF解析  | PDF解析     | PDF解析 + 分块 + **Embedding** + 索引构建 | 范围膨胀          |
| S2 | 文档分块   | 文档分块      | 检查/复用已有 chunks                    | 无实际分块         |
| S3 | 向量嵌入生成 | Embedding | 检查/复用已有索引                         | 无实际 embedding |
| S4 | 向量索引构建 | 索引构建      | 未追踪                               | 缺失            |

### 根因分析

1. `prepare_meal()` 内部的 `_build_pipeline()` 调用了 `build_index_from_chunks()`，包含 embedding + 索引构建
2. profiler 没有传递到 `prepare_meal()` 内部，无法追踪子阶段
3. S1 外层包裹了整个 `prepare_meal()`，导致所有子步骤时间被归入 "PDF解析"

### 时间线证据

```
07:54:41 - PDF 解析开始 (S1 开始)
09:15:48 - Loading embedding model (S1 内部，被隐藏)
09:15:54 - Embedding 45077 texts (S1 内部，被隐藏)
09:42:49 - Embedding 完成 (~27分钟被隐藏)
09:45:35 - Indexing 完成
09:45:43 - Meal created (S1 结束)
```

***

## 修复方案

### 核心思路

**传递 profiler 到** **`prepare_meal()`** **内部，在** **`_build_pipeline()`** **中正确追踪每个子阶段。**

### 阶段定义（修复后）

| 阶段 | 名称     | 追踪位置                       | 内容           |
| -- | ------ | -------------------------- | ------------ |
| S1 | PDF解析  | `_build_pipeline()`        | PDF 解析       |
| S2 | 文档分块   | `_build_pipeline()`        | 文档分块         |
| S3 | 向量嵌入生成 | `_build_pipeline()`        | Embedding 生成 |
| S4 | 向量索引构建 | `_build_pipeline()`        | Qdrant 索引构建  |
| S5 | 测试集生成  | `run_experiment()`         | 测试集生成        |
| S6 | 检索匹配   | `pipeline.query()`         | 向量检索         |
| S7 | 答案生成   | `pipeline.query()`         | LLM 生成       |
| S8 | 报告整合   | `run_experiment()`         | 报告整合         |
| S9 | 评估计算   | `run_variant_evaluation()` | 评估指标计算       |

***

## 实施步骤

### Step 1: 修改 `eval/runner/preparation.py`

**修改** **`prepare_meal()`** **函数签名，接受** **`profiler`** **参数：**

```python
def prepare_meal(
    system_config: dict[str, Any],
    exp_config: ExperimentConfig,
    skip_preprocessing: bool = False,
    force_meal: bool = False,
    force_parse: bool = False,
    force_chunk: bool = False,
    profiler: Any | None = None,  # 新增
) -> dict[str, Any]:
```

**传递 profiler 到** **`MealManager`：**

```python
meal_manager = MealManager(system_config, profiler=profiler)
```

### Step 2: 修改 `src/meal/manager.py`

**修改** **`MealManager.__init__()`** **接受** **`profiler`** **参数：**

```python
def __init__(
    self,
    config: dict[str, Any],
    profiler: Any | None = None,
):
    self.profiler = profiler
    # ... 其他初始化
```

**修改** **`create_meal()`** **传递 profiler 到** **`_build_pipeline()`：**

```python
def create_meal(..., profiler: Any | None = None) -> MealConfig:
    # ...
    meal_config = self._build_pipeline(
        ...,
        profiler=profiler or self.profiler,
    )
```

**修改** **`_build_pipeline()`** **添加 profiler 追踪：**

```python
def _build_pipeline(
    self,
    ...,
    profiler: Any | None = None,
) -> MealConfig:
    # S1: PDF 解析
    if profiler:
        profiler.begin_stage("S1")
    if not reuse_parsed and pdfs_to_parse:
        self._parse_pdfs_with_registry(parser_config, pdfs_to_parse, parsed_dir)
    if profiler:
        profiler.end_stage()

    # S2: 文档分块
    if profiler:
        profiler.begin_stage("S2")
    build_chunks_if_needed(
        parsed_dir,
        chunks_dir,
        chunker_config,
        model_name=embedding_config.get("model_name"),
        force=force_chunk,
    )
    if profiler:
        profiler.end_stage()

    # S3+S4: 向量嵌入生成 + 索引构建
    if profiler:
        profiler.begin_stage("S3")
    build_index_from_chunks(
        chunks_dir=chunks_dir,
        embedding_config=embedding_config,
        vector_store_config=self.config.get("vector_store", {}),
        collection_name=collection_name,
        profiler=profiler,  # 传递 profiler 以便内部分 S3/S4
    )
```

### Step 3: 修改 `src/meal/builders.py`

**修改** **`build_index_from_chunks()`** **接受** **`profiler`** **参数：**

```python
def build_index_from_chunks(
    chunks_dir: Path,
    embedding_config: dict[str, Any],
    vector_store_config: dict[str, Any],
    collection_name: str,
    profiler: Any | None = None,  # 新增
) -> VectorIndexer:
    # S3: Embedding 生成
    if profiler:
        profiler.begin_stage("S3")
    embedder = Embedder(...)
    embeddings = embedder.embed_texts(texts, batch_size=batch_size)
    if profiler:
        profiler.end_stage()

    # S4: 索引构建
    if profiler:
        profiler.begin_stage("S4")
    indexer = VectorIndexer(...)
    indexer.create_collection(...)
    indexer.index_chunks(...)
    if profiler:
        profiler.end_stage()
```

### Step 4: 修改 `eval/runner/core.py`

**修改** **`run_experiment()`** **中的 S1/S2 包裹逻辑：**

```python
# 移除外层 S1/S2 包裹，改为传递 profiler 到 prepare_meal
logger.info("Step 1: Preparing meal...")
meal_info = prepare_meal(
    system_config,
    exp_config,
    skip_preprocessing,
    force_meal=force_meal,
    force_parse=force_parsed,
    force_chunk=force_chunk,
    profiler=profiler,  # 传递 profiler
)

# S2 已在 prepare_meal 内部追踪，移除外层包裹
logger.info("Step 2: Preparing variant chunks...")
for i, variant in enumerate(exp_config.variants, 1):
    # ... variant chunks 准备（通常缓存命中，无需追踪）
```

### Step 5: 修改 `eval/runner/core.py` 中的 `run_variant_evaluation()`

**移除 S3 的外层包裹（已在 prepare\_meal 内部追踪）：**

```python
# 移除 S3 外层包裹
# if profiler:
#     profiler.begin_stage("S3")
indexer = prepare_index_for_variant(...)
# if profiler:
#     profiler.end_stage()
```

### Step 6: 更新测试

**修改** **`tests/test_speed_optimization.py`** **中的相关测试：**

确保测试覆盖新的 profiler 传递逻辑。

***

## 文件修改清单

| 文件                           | 修改内容                                                        |
| ---------------------------- | ----------------------------------------------------------- |
| `eval/runner/preparation.py` | `prepare_meal()` 接受 `profiler` 参数                           |
| `src/meal/manager.py`        | `MealManager` 接受 `profiler` 参数，`_build_pipeline()` 追踪 S1-S4 |
| `src/meal/builders.py`       | `build_index_from_chunks()` 接受 `profiler` 参数，追踪 S3/S4       |
| `eval/runner/core.py`        | `run_experiment()` 传递 profiler，移除 S1/S2 外层包裹                |
| `eval/runner/core.py`        | `run_variant_evaluation()` 移除 S3 外层包裹                       |

***

## 预期结果

修复后的 profiling 报告应呈现：

| 环节        | 预期耗时占比   | 说明                |
| --------- | -------- | ----------------- |
| S1 PDF解析  | \~60-70% | 纯解析时间             |
| S2 文档分块   | <1%      | fixed chunking 极快 |
| S3 向量嵌入   | \~10-15% | GPU 加速            |
| S4 向量索引构建 | \~2-5%   | Qdrant 构建         |
| S5 测试集生成  | \~5-10%  | LLM API 调用        |
| S6 检索匹配   | \~3-5%   | 向量检索极快            |
| S7 答案生成   | \~5-10%  | LLM API 调用        |
| S8 报告整合   | <1%      | 纯计算               |
| S9 评估计算   | \~20-30% | 评估指标计算            |

***

## 验证步骤

1. 运行 `pixi run exp baseline/baseline_all_golden_0501` 验证所有阶段计时正确
2. 检查 profiling 报告中 S1-S4 全部有数据
3. 确认 S3 显示正确的 embedding 时间（\~27 分钟）
4. 确认 S1 仅显示 PDF 解析时间
