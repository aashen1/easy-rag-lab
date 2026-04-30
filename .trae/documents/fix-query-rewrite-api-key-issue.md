# 修复查询改写API认证失败问题

## 问题分析

### 现象
3个变体（hyde、multi_query_3、combo_full）因API认证失败而无法运行：
```
Error code: 401 - {'error': {'code': 'invalid_api_key', 'message': 'missing_api_key', 'type': 'authentication_error'}}
```

### 根本原因

在 `eval/runner/core.py` 的 `run_variant()` 函数中：

```python
pipeline = RAGPipeline(
    config_path=None,
    llm_preset=llm_preset,
    meal_name=meal_name,
    token_tracker=variant_tracker,
    profiler=profiler,
)
pipeline.config = merged_config  # 问题：配置在初始化后才设置
```

**问题流程**：
1. `RAGPipeline.__init__()` 被调用时，`config_path=None`，所以加载默认的 `config.yaml`
2. 在初始化过程中，`_setup_retrievers()` 被调用
3. `_setup_retrievers()` 中创建 `QueryRewriter` 时调用 `get_llm_config(self.config)`
4. **关键问题**：此时 `self.config` 是默认配置，而不是实验的 `merged_config`
5. 实验配置中的 `llm_preset` 参数也没有被传递给 `_setup_retrievers()` 中的 `get_llm_config()` 调用
6. 然后才执行 `pipeline.config = merged_config`，但为时已晚

**结果**：`QueryRewriter` 使用了错误的LLM配置，导致API认证失败。

## 修复方案

### 方案A：修改 RAGPipeline 支持延迟初始化（推荐）

修改 `RAGPipeline` 的初始化流程，支持在设置 `config` 属性后重新初始化相关组件。

**优点**：
- 保持现有的实验运行器代码不变
- 更灵活，支持配置热更新

**缺点**：
- 需要修改 `RAGPipeline` 的内部逻辑

### 方案B：修改实验运行器，在创建Pipeline前合并配置

修改 `eval/runner/core.py`，在创建 `RAGPipeline` 之前就完成配置合并，并保存到临时文件。

**优点**：
- 不需要修改 `RAGPipeline` 的逻辑
- 更符合"配置优先"的设计原则

**缺点**：
- 需要创建临时配置文件
- 可能影响其他使用 `RAGPipeline` 的代码

### 方案C：修改 RAGPipeline 支持直接传入配置字典

为 `RAGPipeline.__init__()` 添加一个 `config_dict` 参数，允许直接传入配置字典。

**优点**：
- 最干净的解决方案
- 避免临时文件
- 明确的配置来源

**缺点**：
- 需要修改 `RAGPipeline` 的接口

## 推荐方案：方案C

修改 `RAGPipeline.__init__()` 添加 `config_dict` 参数：

```python
def __init__(
    self,
    config_path: str = "config.yaml",
    config_dict: dict[str, Any] | None = None,  # 新增参数
    llm_preset: str | None = None,
    meal_name: str | None = None,
    token_tracker: TokenTracker | None = None,
    profiler: PipelineProfiler | None = None,
):
    if config_dict is not None:
        self.config = config_dict
    else:
        self.config = load_config(config_path)
    # ... 其余初始化代码
```

然后修改实验运行器：

```python
pipeline = RAGPipeline(
    config_dict=merged_config,  # 直接传入合并后的配置
    llm_preset=llm_preset,
    meal_name=meal_name,
    token_tracker=variant_tracker,
    profiler=profiler,
)
```

## 实施步骤

1. **修改 `src/pipeline.py`**
   - 为 `RAGPipeline.__init__()` 添加 `config_dict` 参数
   - 修改配置加载逻辑，优先使用 `config_dict`
   - 确保 `_setup_retrievers()` 中的 `get_llm_config()` 调用使用正确的 `llm_preset`

2. **修改 `eval/runner/core.py`**
   - 修改 `run_variant()` 函数，使用 `config_dict` 参数传入合并后的配置
   - 移除 `pipeline.config = merged_config` 这行代码

3. **修改 `_setup_retrievers()` 方法**
   - 确保 `get_llm_config()` 调用时传递正确的 `llm_preset`
   - 需要将 `llm_preset` 存储为实例变量

4. **更新测试**
   - 添加测试用例验证 `config_dict` 参数的功能
   - 确保现有测试不被破坏

5. **验证修复**
   - 重新运行失败的3个变体
   - 确认API认证成功

## 风险评估

- **影响范围**：`RAGPipeline` 是核心组件，修改需谨慎
- **向后兼容**：`config_dict` 参数是可选的，不影响现有代码
- **测试覆盖**：需要确保所有使用 `RAGPipeline` 的场景都有测试覆盖

## 预期结果

修复后，hyde、multi_query_3、combo_full 三个变体应该能够正常运行，不再出现API认证失败错误。
