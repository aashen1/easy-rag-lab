# Profiling 系统修复方案

## 问题诊断

基于首次 `baseline_1kpage` 实验运行结果，发现以下 5 个关键问题：

### 问题 1：S1 覆盖范围严重膨胀
- **现状**：`prepare_meal()` 在 meal 不存在时包含 PDF 解析 + 分块 + 索引构建
- **结果**：S1 耗时 427s（含 S2+S3+S4 的工作），S2 仅 0.002s
- **根因**：`meal_manager.create_meal()` 内部一次性完成了解析→分块→索引构建

### 问题 2：S3/S4 完全缺失
- **现状**：`prepare_index_for_variant()` 中的 `build_index_from_chunks()` 未被 profiler 包裹
- **结果**：embedding 和索引构建时间被"吞掉"，无法单独统计
- **根因**：索引构建发生在 `run_variant_evaluation()` 内部，在 S6 开始之前

### 问题 3：S6/S7 计时划分错误
- **现状**：S6 包含检索+生成+评估全部时间，S7 仅含 `compute_aggregate_metrics()`
- **结果**：S6=158.82s（实际含检索+生成），S7≈0s
- **根因**：`evaluate_test_set()` → `_collect_rag_samples()` → `pipeline.query()` 把检索和生成打包在一起

### 问题 4：Token 统计全为 0
- **现状**：所有环节 token 统计为 0
- **根因**：profiler 绑定的是 `experiment_tracker`，但实际记录 token 的是各阶段独立的 tracker（`test_generation_tracker`、`variant_tracker`），不是同一个对象

### 问题 5：图表中文字体缺失
- **现状**：matplotlib 默认 DejaVu Sans 不支持 CJK 字符
- **结果**：饼图/柱状图中中文标签显示为方框

---

## 修复方案

### 修复 1：重构 S1-S4 的计时策略

**核心思路**：不再按"函数调用"划分阶段，改为按"操作类型"划分阶段。

**方案**：在 `pipeline.query()` 内部添加 profiler 埋点，将检索和生成分开计时。在 `run_variant_evaluation()` 中为索引构建添加 profiler 包裹。

**具体改动**：

#### 1.1 `eval/run_experiment.py` - 重构主流程阶段划分

当前：
```
S1 = prepare_meal()          # 含解析+分块+索引构建
S2 = prepare_variant_chunks() # 仅分块
S5 = prepare_test_sets()
S6 = evaluate_test_set()     # 含检索+生成+评估
S7 = compute_aggregate_metrics()
S8 = 报告整合
```

改为：
```
S1 = prepare_meal() 中的 PDF 解析部分
S2 = prepare_meal() + prepare_variant_chunks() 中的分块部分
S3 = prepare_index_for_variant() 中的 embedding 部分
S4 = prepare_index_for_variant() 中的索引构建部分
S5 = prepare_test_sets()
S6 = pipeline.query() 中的检索部分
S7 = pipeline.query() 中的生成部分
S8 = 报告整合
```

**关键改动**：将 S1 从 `prepare_meal()` 整体包裹改为只包裹解析部分，S2 包含 meal 创建中的分块 + variant chunks，S3/S4 在 `run_variant_evaluation()` 中包裹。

但 `prepare_meal()` 内部逻辑不可拆分（`create_meal()` 是一个原子操作），所以采用**子阶段标记**方案：

- S1 仍然包裹 `prepare_meal()`，但内部通过 meal 的 stats 区分解析和分块
- 在 `run_variant_evaluation()` 中，S3/S4 包裹 `prepare_index_for_variant()`
- S6/S7 通过在 `pipeline.query()` 内部添加 profiler 埋点来拆分

#### 1.2 `src/pipeline.py` - 在 query() 内部添加 S6/S7 埋点

在 `query()` 方法中，检索前后和生成前后添加 profiler 计时：

```python
def query(self, question, ...):
    # ... 前置处理 ...

    if self.profiler:
        self.profiler.begin_stage("S6")
    results = self.retriever.retrieve(retrieval_query)
    if self.profiler:
        self.profiler.end_stage()

    # ... 上下文处理 ...

    if self.profiler:
        self.profiler.begin_stage("S7")
    answer = self.generator.generate(question, contexts, ...)
    if self.profiler:
        self.profiler.end_stage()
```

**注意**：S6/S7 在多问题场景下会被多次 begin/end，需要修改 `PipelineProfiler` 支持累加模式。

### 修复 2：PipelineProfiler 支持累加模式

当前 `begin_stage()/end_stage()` 每次会覆盖同一 stage_id 的数据。需要改为累加模式：

```python
def end_stage(self) -> StageMetrics:
    # 如果该 stage_id 已存在，累加而非覆盖
    if stage_id in self._stages:
        existing = self._stages[stage_id]
        existing.duration_seconds += duration
        existing.input_tokens += input_tokens
        existing.output_tokens += output_tokens
        # CPU/内存取峰值
        existing.cpu_percent_peak = max(existing.cpu_percent_peak, cpu_peak)
        existing.memory_mb_peak = max(existing.memory_mb_peak, mem_peak)
        # CPU/内存平均值重新计算
        ...
    else:
        self._stages[stage_id] = metrics
```

### 修复 3：Token 统计修复

**方案**：不再依赖 `set_token_tracker()` 绑定单一 tracker，改为在每个阶段结束时，由调用方主动传入该阶段的 token 使用量。

在 `StageMetrics` 中添加 `add_token_usage()` 方法：

```python
def add_token_usage(self, input_tokens: int, output_tokens: int):
    self.input_tokens += input_tokens
    self.output_tokens += output_tokens
```

在 `run_experiment.py` 中，各阶段结束后主动报告 token：

```python
# S5 结束后
if profiler:
    profiler.get_stage_metrics("S5").add_token_usage(
        test_generation_tracker.get_total_input(),
        test_generation_tracker.get_total_output(),
    )

# S6/S7 结束后（在 pipeline.query 内部已通过 profiler 累加）
# variant_tracker 的 token 在 run_variant_evaluation 结束后汇总
```

### 修复 4：图表中文字体

在 `visualize_profiler.py` 中添加中文字体支持：

```python
import matplotlib
matplotlib.use('Agg')

# 尝试设置中文字体
try:
    matplotlib.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'Arial Unicode MS']
    matplotlib.rcParams['axes.unicode_minus'] = False
except Exception:
    pass
```

---

## 实施步骤

### Step 1：修改 `eval/pipeline_profiler.py`
- `StageMetrics` 添加 `add_token_usage()` 方法和累加支持
- `PipelineProfiler.end_stage()` 支持累加模式（同一 stage_id 多次 begin/end 时累加）
- `PipelineProfiler` 添加 `report_stage_tokens()` 方法，供外部主动报告 token

### Step 2：修改 `src/pipeline.py`
- `query()` 方法内添加 S6/S7 的 profiler 埋点
- `build_index()` 方法内添加 S3/S4 的 profiler 埋点（已有 S3，需确认 S4）

### Step 3：修改 `eval/run_experiment.py`
- 重构 S1 包裹范围：S1 仅含 `prepare_meal()`，但通过 meal stats 区分子阶段
- 在 `run_variant_evaluation()` 中为 `prepare_index_for_variant()` 添加 S3/S4 包裹
- 移除 S6/S7 的外层包裹（改由 pipeline.query 内部处理）
- 各阶段结束后主动报告 token 使用量

### Step 4：修改 `eval/visualize_profiler.py`
- 添加中文字体支持

### Step 5：运行验证
- 运行 `pixi run exp baseline/baseline_1kpage` 验证所有阶段计时正确
- 检查 profiling 报告中 S1-S8 全部有数据
- 检查 token 统计不为 0
- 检查图表中文正常显示

---

## 预期结果

修复后的 profiling 报告应呈现：

| 环节 | 预期耗时占比 | 说明 |
|------|-------------|------|
| S1 PDF解析 | ~60-70% | 纯解析时间 |
| S2 文档分块 | <1% | fixed chunking 极快 |
| S3 向量嵌入 | ~10-15% | GPU 加速 |
| S4 索引构建 | ~2-5% | Qdrant 构建 |
| S5 测试集生成 | ~5-10% | LLM API 调用 |
| S6 检索匹配 | ~3-5% | 向量检索极快 |
| S7 答案生成 | ~5-10% | LLM API 调用 |
| S8 报告整合 | <1% | 纯计算 |

Token 统计应正确反映各环节消耗。
