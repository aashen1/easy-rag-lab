# 配置热更新架构设计

## 背景

在排查查询改写API认证失败问题时，我们发现了 `RAGPipeline` 的一个设计缺陷：配置在初始化后才被设置，导致依赖配置的组件（如 `QueryRewriter`）使用了错误的配置。

代码注释中提到了"配置热更新"：
```python
def _setup_retrievers(self) -> None:
    """Set up retrievers based on the current retrieval config.

    Called during initialization and when the config is hot-swapped during experiments.
    """
```

但实际上，**热更新并未正确实现**。本文档探讨如果要实现完整的配置热更新，需要解决哪些问题。

---

## 当前状态

### 已有设计

1. `_setup_retrievers()` 方法被设计为可重复调用
2. 注释中明确提到"热更新"场景
3. 但没有实现配置变更时的自动触发机制

### 已知问题

1. **配置设置时机错误**：`pipeline.config = merged_config` 在初始化之后执行
2. **组件状态不一致**：部分组件使用旧配置，部分使用新配置
3. **无状态管理**：没有追踪哪些组件需要重置

---

## 热更新的真实价值

### 场景1：实验批量运行

```
运行变体A → 切换配置 → 运行变体B → 切换配置 → 运行变体C
```

**当前做法**：每个变体创建新的 `RAGPipeline` 实例

**热更新的潜在收益**：
- 减少重复初始化开销（Embedder、Indexer等可复用）
- 更快的实验迭代速度

### 场景2：生产环境动态调整

```
检测到API限流 → 自动切换到备用模型
检测到用户量增加 → 动态调整并发数
检测到成本超支 → 切换到更便宜的模型
```

**热更新的潜在收益**：
- 无需重启服务
- 更灵活的运维能力

### 场景3：A/B测试

```
用户A组 → 使用配置A
用户B组 → 使用配置B
```

**热更新的潜在收益**：
- 同一服务实例支持多配置
- 简化A/B测试部署

---

## 热更新的技术挑战

### 1. 状态一致性问题

**问题描述**：当配置变更时，多个组件可能处于不同状态。

**示例**：
```
配置变更前：
- QueryRewriter 使用 model_A
- Generator 使用 model_A
- Embedder 使用 embedding_model_A

配置变更后（只重置了部分组件）：
- QueryRewriter 使用 model_B  ← 已重置
- Generator 使用 model_A      ← 忘记重置
- Embedder 使用 embedding_model_A  ← 不需要重置
```

**结果**：系统行为不一致，难以调试。

### 2. 资源释放问题

**问题描述**：旧配置创建的资源（连接池、缓存、模型实例）如何释放？

**示例**：
```python
# 旧配置创建了LLM客户端
self.llm_client = LLMClient(api_key="key_A")

# 配置变更后，需要释放旧客户端
# 但如果有其他地方持有引用怎么办？
```

### 3. 事务性问题

**问题描述**：如果重置到一半失败了，是回滚还是继续？

**示例**：
```python
def reload_config(self, new_config):
    # 步骤1：重置 QueryRewriter
    self.query_rewriter = create_query_rewriter(new_config)  # 成功

    # 步骤2：重置 Generator
    self.generator = create_generator(new_config)  # 失败！

    # 现在怎么办？系统处于不一致状态
```

### 4. 副作用问题

**问题描述**：用户代码可能持有旧组件的引用。

**示例**：
```python
# 用户代码
rewriter = pipeline.query_rewriter
rewriter.rewrite("some query")  # 使用的是旧实例

# 配置变更后
pipeline.reload_config(new_config)

# 用户代码继续使用旧的 rewriter
rewriter.rewrite("some query")  # 还是旧配置！
```

---

## 可能的解决方案

### 方案1：组件注册表 + 依赖追踪

```python
class RAGPipeline:
    def __init__(self):
        self._config_dependent_components = []
        self._register_component("query_rewriter", self._create_query_rewriter)
        self._register_component("generator", self._create_generator)

    def _register_component(self, name, factory):
        """注册依赖配置的组件"""
        self._config_dependent_components.append((name, factory))

    def reload_config(self, new_config):
        """重置所有依赖配置的组件"""
        old_components = {}
        try:
            for name, factory in self._config_dependent_components:
                old_components[name] = getattr(self, name)
                setattr(self, name, factory(new_config))
        except Exception as e:
            # 回滚
            for name, old in old_components.items():
                setattr(self, name, old)
            raise
```

**优点**：显式追踪，不易遗漏
**缺点**：需要修改所有组件的创建逻辑

### 方案2：配置代理模式

```python
class ConfigProxy:
    """配置代理，监听配置变更"""
    def __init__(self, config):
        self._config = config
        self._listeners = []

    def add_listener(self, callback):
        self._listeners.append(callback)

    def update(self, new_config):
        old_config = self._config
        self._config = new_config
        for callback in self._listeners:
            callback(old_config, new_config)

class QueryRewriter:
    def __init__(self, config_proxy):
        self._config_proxy = config_proxy
        config_proxy.add_listener(self._on_config_change)

    def _on_config_change(self, old_config, new_config):
        # 自动响应配置变更
        self._reinitialize(new_config)
```

**优点**：自动响应，无需手动管理
**缺点**：增加复杂度，调试困难

### 方案3：不可变设计

```python
class RAGPipeline:
    """不可变Pipeline，配置变更时创建新实例"""

    def with_config(self, new_config) -> "RAGPipeline":
        """创建使用新配置的Pipeline实例"""
        new_pipeline = RAGPipeline.__new__(RAGPipeline)
        new_pipeline.config = new_config
        # 复用可共享的组件
        new_pipeline.embedder = self.embedder
        new_pipeline.indexer = self.indexer
        # 重新创建依赖配置的组件
        new_pipeline._setup_retrievers()
        new_pipeline._setup_generator()
        return new_pipeline
```

**优点**：无状态一致性问题，线程安全
**缺点**：每次变更都创建新实例，可能有性能开销

---

## 推荐的演进路径

### 短期（当前修复）

采用方案C（统一配置参数），解决当前的bug，不引入热更新机制。

### 中期（v0.2.x）

如果实验系统需要更快的迭代速度，可以考虑：
1. 实现 `with_config()` 方法，支持创建新配置的Pipeline实例
2. 复用可共享的组件（Embedder、Indexer）
3. 保持不可变设计，避免状态一致性问题

### 长期（v0.3+）

如果生产环境需要动态调整能力，可以考虑：
1. 引入配置代理模式
2. 实现组件级别的配置监听
3. 添加健康检查和自动恢复机制

---

## 相关Issue

- [FEAT-XXX: 配置热更新架构设计](.issues/active/FEAT-XXX.md)

---

## 参考资料

- [Python State Machine Pattern](https://refactoring.guru/design-patterns/state)
- [Configuration Management Best Practices](https://12factor.net/config)
- [Hot Reload in Production Systems](https://blog.cloudflare.com/hot-reload-in-production/)
