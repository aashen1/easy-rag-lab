# 修复查询改写API认证失败问题

## 问题分析

### 现象
3个变体（hyde、multi_query_3、combo_full）因API认证失败而无法运行：
```
Error code: 401 - {'error': {'code': 'invalid_api_key', 'message': 'missing_api_key', 'type': 'authentication_error'}}
```

### 根本原因

经过深入排查，发现存在**两个独立的问题**：

#### 问题1：配置传递时机错误

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

#### 问题2：QueryRewriter 未使用标准认证模式

在 `src/query_rewriter.py` 中：

```python
# 错误的方式
self._client = Anthropic(
    api_key=self.llm_api_key, base_url=self.llm_base_url
)
```

项目的 API 代理要求将 API key 放在 `Authorization: Bearer` header 中，而不是默认的 `x-api-key` header。`QueryRewriter` 没有使用项目的标准认证模式，导致 API 调用失败。

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

## 最终方案

### 修复1：统一配置参数

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

### 修复2：QueryRewriter 使用标准认证模式

```python
# 修改前
self._client = Anthropic(
    api_key=self.llm_api_key, base_url=self.llm_base_url
)

# 修改后
from src.llm_client import create_anthropic_client

self._client = create_anthropic_client(
    api_key=self.llm_api_key,
    base_url=self.llm_base_url,
)
```

---

## 实施结果

### 已完成的修改

- [x] 修改 `RAGPipeline.__init__()` 签名，将 `config_path` 改为 `config`
- [x] 修改配置加载逻辑，支持字符串或字典
- [x] 将 `llm_preset` 存储为实例变量 `self.llm_preset`
- [x] 确保 `_setup_retrievers()` 中的 `get_llm_config()` 使用 `self.llm_preset`
- [x] 修改 `eval/runner/core.py`，使用 `config=merged_config`
- [x] 修改 `QueryRewriter` 使用标准认证模式
- [x] 运行测试确保现有功能不受影响
- [x] 验证修复：重新运行失败的3个变体

### 验证结果

实验 `exp_20260430_185054_verify_fix` 结果：

```
- Total Variants: 3
- Successful Variants: 3
- Failed Variants: 0
```

| Variant | Hit Rate | Faithfulness | Relevancy |
|---------|----------|--------------|-----------|
| hyde | 1.0 | 0.98 | 0.94 |
| multi_query_3 | 1.0 | 0.78 | 0.92 |
| combo_full | 1.0 | 0.98 | 0.96 |

**修复成功！**

---

## 提交记录

1. `fix: pass merged config to RAGPipeline at initialization`
   - 修改 `RAGPipeline.__init__()` 签名
   - 修改配置加载逻辑
   - 修改实验运行器

2. `fix: use standard auth pattern in QueryRewriter`
   - 导入 `create_anthropic_client`
   - 替换直接的 `Anthropic()` 实例化

---

## 相关文档

- [配置热更新架构设计](config-hot-swap-architecture.md)
- Issue: [RF-20260430-001-w0: 配置热更新架构设计](../.issues/active/RF-20260430-001-w0-配置热更新架构设计.md)
