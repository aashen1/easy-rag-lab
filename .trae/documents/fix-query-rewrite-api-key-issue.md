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

---

## 方案讨论与评价

### 方案A：延迟初始化/配置热更新

**核心思想**：允许配置改变后，重新初始化依赖配置的组件。

**评价**：
- **短期价值**：对修复当前bug来说是"杀鸡用牛刀"
- **长期价值**：如果实现完整的配置热更新，对实验批量运行、生产环境动态调整都有价值
- **风险**：需要解决状态一致性、资源释放、事务性等问题，不是简单加一个reload方法能解决的
- **结论**：**暂不采用**，但值得未来系统性讨论。详见专题文档 `config-hot-swap-architecture.md`

### 方案B：临时配置文件

**核心思想**：把合并后的配置写入临时文件，让 `RAGPipeline` 从文件加载。

**评价**：
- **优点**：不需要改 `RAGPipeline` 的接口
- **缺点**：
  - 运行时开销（每次都要写文件、读文件）
  - 需要管理临时文件生命周期
  - 潜在问题：文件残留、路径冲突、Windows文件锁
  - 违反"最短路径"原则（配置已在内存，非要写文件再读）
- **结论**：**不采用**，是"快速修复"但会留下技术债务

### 方案C：统一配置参数（采用）

**核心思想**：修改 `RAGPipeline` 的接口，统一配置参数，支持字符串（文件路径）或字典。

**评价**：
- **优点**：
  - 最直接解决问题，无额外开销
  - 接口语义清晰（`config` 参数支持多种形态）
  - 向后兼容（不传参数时用默认值）
  - 承认现实：配置可能来自不同地方（文件、内存）
- **缺点**：需要修改 `RAGPipeline` 的接口
- **结论**：**采用**

---

## 最终方案：改进版方案C

### 接口设计

将 `config_path` 和 `config_dict` 合并为一个统一的 `config` 参数：

```python
def __init__(
    self,
    config: str | dict | None = None,  # 统一参数：文件路径或字典
    llm_preset: str | None = None,
    meal_name: str | None = None,
    token_tracker: TokenTracker | None = None,
    profiler: PipelineProfiler | None = None,
):
    if config is None:
        config = "config.yaml"
    
    if isinstance(config, str):
        self.config = load_config(config)
    else:
        self.config = config
    
    self.llm_preset = llm_preset  # 存储为实例变量
    # ... 其余初始化代码
```

### 调用方式变更

```python
# 实验运行器
pipeline = RAGPipeline(
    config=merged_config,  # 直接传入字典
    llm_preset=llm_preset,
    meal_name=meal_name,
    token_tracker=variant_tracker,
    profiler=profiler,
)

# 现有代码（向后兼容）
pipeline = RAGPipeline()  # 使用默认 config.yaml
pipeline = RAGPipeline(config="custom_config.yaml")  # 使用指定文件
```

---

## 实施步骤

### 1. 修改 `src/pipeline.py`

- [ ] 修改 `__init__()` 签名，将 `config_path` 改为 `config`
- [ ] 修改配置加载逻辑，支持字符串或字典
- [ ] 将 `llm_preset` 存储为实例变量 `self.llm_preset`
- [ ] 确保 `_setup_retrievers()` 中的 `get_llm_config()` 使用 `self.llm_preset`

### 2. 修改 `eval/runner/core.py`

- [ ] 修改 `run_variant()` 函数，使用 `config=merged_config`
- [ ] 移除 `pipeline.config = merged_config` 这行代码

### 3. 更新测试

- [ ] 添加测试用例验证 `config` 参数接受字典
- [ ] 添加测试用例验证 `config` 参数接受文件路径
- [ ] 确保现有测试不被破坏

### 4. 验证修复

- [ ] 重新运行失败的3个变体（hyde、multi_query_3、combo_full）
- [ ] 确认API认证成功
- [ ] 确认其他变体不受影响

---

## 风险评估

| 风险类型 | 说明 | 缓解措施 |
|----------|------|----------|
| 接口变更 | 修改 `RAGPipeline` 的签名 | 使用默认参数保持向后兼容 |
| 调用方改动 | 需要修改实验运行器 | 改动量小，仅一行代码 |
| 测试覆盖 | 需要确保所有场景都有测试 | 添加新的测试用例 |

---

## 预期结果

修复后：
1. hyde、multi_query_3、combo_full 三个变体能够正常运行
2. 不再出现API认证失败错误
3. 现有代码继续正常工作（向后兼容）
