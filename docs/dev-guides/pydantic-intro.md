# Pydantic 入门：配置验证的守护神

## 一句话概括

**Pydantic 是一个 Python 库，它让你用 Python 类来定义"数据长什么样"，然后自动帮你检查传入的数据是否符合这个样子——不符合就报错，告诉你哪里错了、该怎么改。**

---

## 为什么需要它？先看一个场景

假设我们的 `config.yaml` 里有这么一段：

```yaml
chunker:
  chunk_size: 512
  chunk_overlap: 64
```

当前项目加载配置的方式是这样的（简化版）：

```python
config = yaml.safe_load("config.yaml")
chunk_size = config["chunker"]["chunk_size"]
overlap = config["chunker"]["chunk_overlap"]
```

看起来没问题？但如果有人手滑把 `chunk_size` 写成了字符串：

```yaml
chunker:
  chunk_size: "512"      # 多打了个引号
  chunk_overlap: -10      # 负数？？
```

**会发生什么？**

- `yaml.safe_load()` 照单全收，不报任何错
- 程序继续往下跑，直到某个地方用 `chunk_size` 做数学运算时才崩溃
- 报错信息可能是 `TypeError: '>' not supported between instances of 'str' and 'int'`
- 你得顺着调用栈往上找，才发现是配置写错了

这就是**"没有验证"的代价**：错误在配置文件里埋下，却在八竿子打不着的地方爆炸，报错信息还让人一头雾水。

---

## Pydantic 怎么解决这个问题？

Pydantic 的思路很简单：**先定义规矩，再收数据**。

### 第一步：用 Python 类定义"规矩"

```python
from pydantic import BaseModel, Field

class ChunkerConfig(BaseModel):
    chunk_size: int = Field(gt=0, description="切块大小，必须大于 0")
    chunk_overlap: int = Field(ge=0, description="切块重叠，不能为负")
```

这段代码的意思是：

- `chunk_size` 必须是 `int` 类型，而且必须大于 0（`gt=0` = greater than 0）
- `chunk_overlap` 必须是 `int` 类型，而且必须大于等于 0（`ge=0` = greater than or equal to 0）

### 第二步：把数据扔进去，让它检查

```python
config = ChunkerConfig(chunk_size="512", chunk_overlap=-10)
```

Pydantic 会立刻报错：

```
ValidationError: 2 validation errors for ChunkerConfig
chunk_overlap
  Input should be greater than or equal to 0 [input_value=-10, input_type=int]
```

注意两件事：

1. **`chunk_size="512"` 没有报错**——Pydantic 足够聪明，它发现 `"512"` 可以安全地转成整数，就自动帮你转了。这叫"类型强制转换"（coercion），是 Pydantic 的贴心设计。
2. **`chunk_overlap=-10` 报错了**——负数不满足 `ge=0` 的约束，而且报错信息非常明确：哪个字段、什么问题、实际值是什么。

### 对比一下

| | 没有 Pydantic | 有 Pydantic |
|---|---|---|
| 类型错误 | 运行时随机崩溃 | 加载时立刻报错 |
| 范围越界 | 静默通过，结果不可预测 | 加载时立刻报错 |
| 报错信息 | `TypeError: '>' not supported...` | `chunk_overlap: Input should be greater than or equal to 0` |
| 错误定位 | 需要顺着调用栈找 | 直接告诉你哪个配置字段有问题 |

---

## Pydantic 核心概念速览

### 1. BaseModel——所有模型的基类

继承 `BaseModel` 的类就是一个"数据模型"。它定义了数据有哪些字段、每个字段什么类型。

```python
from pydantic import BaseModel

class User(BaseModel):
    name: str
    age: int
    email: str | None = None   # 可选字段，默认 None
```

使用时：

```python
user = User(name="Alice", age=30)
print(user.name)   # "Alice"
print(user.email)  # None（自动填充了默认值）
```

### 2. Field——给字段加约束

`Field` 是给字段附加规则的工具：

```python
from pydantic import BaseModel, Field

class ChunkerConfig(BaseModel):
    chunk_size: int = Field(gt=0, description="切块大小")
    chunk_overlap: int = Field(ge=0, description="切块重叠")
    strategy: str = Field(default="fixed", description="切块策略")
```

常用的约束参数：

| 参数 | 含义 | 示例 |
|---|---|---|
| `gt` | 大于 | `gt=0` → 必须 > 0 |
| `ge` | 大于等于 | `ge=0` → 必须 ≥ 0 |
| `lt` | 小于 | `lt=1` → 必须 < 1 |
| `le` | 小于等于 | `le=100` → 必须 ≤ 100 |
| `default` | 默认值 | `default="fixed"` |
| `description` | 字段描述 | 用于生成文档和报错信息 |

### 3. Literal——限制只能取几个值

当你想让某个字段只能从几个固定选项中选一个时：

```python
from typing import Literal
from pydantic import BaseModel

class ParserConfig(BaseModel):
    primary: Literal["pymupdf4llm", "fitz"]  # 只能二选一
```

如果传入 `primary: "abc"`，立刻报错：

```
Input should be 'pymupdf4llm' or 'fitz'
```

这比在代码里写 `if primary not in ["pymupdf4llm", "fitz"]: raise ValueError(...)` 优雅多了。

### 4. 嵌套模型——配置的层级结构

配置文件是有层级的，Pydantic 用嵌套模型来表达：

```python
class SemanticConfig(BaseModel):
    similarity_threshold: float = Field(default=0.5, ge=0, le=1)

class ChunkerConfig(BaseModel):
    chunk_size: int = Field(gt=0)
    chunk_overlap: int = Field(ge=0)
    strategy: Literal["fixed", "semantic"] = "fixed"
    semantic: SemanticConfig = SemanticConfig()  # 嵌套
```

对应 YAML：

```yaml
chunker:
  chunk_size: 512
  chunk_overlap: 64
  strategy: "semantic"
  semantic:
    similarity_threshold: 0.7
```

### 5. model_validator——跨字段校验

有些规则涉及多个字段之间的关系，比如"overlap 必须小于 chunk_size"：

```python
from pydantic import BaseModel, Field, model_validator

class ChunkerConfig(BaseModel):
    chunk_size: int = Field(gt=0)
    chunk_overlap: int = Field(ge=0)

    @model_validator(mode="after")
    def check_overlap_less_than_size(self):
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError(
                f"chunk_overlap ({self.chunk_overlap}) must be less than "
                f"chunk_size ({self.chunk_size})"
            )
        return self
```

这种校验用普通的 `Field` 约束做不到，因为需要同时读两个字段的值。`model_validator` 就是干这个的。

### 6. field_validator——单字段自定义校验

如果某个字段的校验逻辑比较复杂，可以用 `field_validator`：

```python
from pydantic import BaseModel, field_validator

class LLMPresetConfig(BaseModel):
    model_name: str
    temperature: float = Field(default=0.0, ge=0, le=2)

    @field_validator("model_name")
    @classmethod
    def model_name_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("model_name cannot be empty or whitespace")
        return v
```

### 7. model_dump()——把模型转回字典

验证通过后，可以用 `model_dump()` 把 Pydantic 模型转回普通的 `dict`：

```python
config = ChunkerConfig(chunk_size=512, chunk_overlap=64)
plain_dict = config.model_dump()
# {'chunk_size': 512, 'chunk_overlap': 64, 'strategy': 'fixed', ...}
```

这个功能非常关键——它意味着我们可以在验证后转回 `dict`，让下游代码完全不用改。

---

## 对本项目的好处

### 1. 配置错误在启动时暴露，而不是运行时

当前项目的 `load_config()` 用 `yaml.safe_load()` 直接返回 `dict`，没有任何验证。拼写错误、类型错误、范围越界都会静默通过，直到运行到某个具体功能时才爆炸。

引入 Pydantic 后，配置在加载的瞬间就会被全面检查。如果 `chunk_size` 写成了负数，你在启动程序的第一秒就能看到清晰的报错，而不是在跑了 10 分钟索引之后才崩溃。

### 2. 报错信息从"天书"变成"人话"

没有验证时，配置错误导致的报错可能是这样的：

```
TypeError: '>' not supported between instances of 'str' and 'int'
  File "src/chunker.py", line 45, in split_text
```

有了 Pydantic，报错变成：

```
ValidationError: 1 validation error for AppConfig
chunker.chunk_size
  Input should be a valid integer [input_value="abc", input_type=str]
```

一眼就能看出：`chunker.chunk_size` 这个字段应该是整数，但你写了字符串 `"abc"`。

### 3. 消除分散在各处的重复校验

当前项目中，各模块各自做运行时校验：

- `sampler.py` 有自己的 `ConfigurationError`
- `embedder.py` 有配置校验逻辑
- `query_rewriter.py` 检查 strategy 合法性
- `chunker.py` 检查 chunk_size 和 overlap 的关系

这些校验逻辑分散在十几个文件里，风格不统一，而且容易遗漏。Pydantic 把所有校验集中到一个地方——`config_schema.py`，一处定义，全局生效。

### 4. 配置即文档

Pydantic 模型本身就是配置的"活文档"。每个字段有类型、有约束、有描述：

```python
class ChunkerConfig(BaseModel):
    chunk_size: int = Field(gt=0, description="切块大小（字符数），必须大于 0")
    chunk_overlap: int = Field(ge=0, description="相邻切块重叠字符数")
    strategy: Literal["fixed", "semantic"] = Field(
        default="fixed", description="切块策略：fixed=固定长度, semantic=语义分割"
    )
```

比在 YAML 里写注释更可靠——因为这段代码**既是文档，又是运行时校验**，永远不会和实际逻辑脱节。

### 5. 向后兼容——不需要改任何下游代码

这是最关键的一点。引入 Pydantic 不意味着要把 `load_config()` 的返回类型从 `dict` 改成 Pydantic 模型。我们的策略是：

```
YAML 文件 → yaml.safe_load() → dict → Pydantic 验证 → model_dump() → dict
```

验证通过后转回 `dict` 返回，所有消费 `load_config()` 的代码零改动。Pydantic 只是一个"安检门"——数据经过检查后，还是原来的样子。

### 6. 不需要新增依赖

项目已经在 `pixi.toml` 中声明了 `pydantic = ">=2.13.3, <3"`，而且项目中已有两处使用：

- [src/issue/models.py](src/issue/models.py)——Issue 系统的数据模型，使用了 `BaseModel`、`Field`、`field_validator`
- [src/experiment_schemas.py](src/experiment_schemas.py)——实验配置验证，使用了 `model_validator`

所以引入 Pydantic 做配置验证，不是在引入一个陌生的新工具，而是在把项目已经在用的工具用得更彻底。

---

## 一个完整的例子：从 YAML 到验证

假设 `config.yaml` 中有这样一段：

```yaml
chunker:
  chunk_size: 512
  chunk_overlap: 64
  strategy: "fixed"
```

对应的 Pydantic 模型：

```python
from typing import Literal
from pydantic import BaseModel, Field, model_validator

class ChunkerConfig(BaseModel):
    chunk_size: int = Field(gt=0, description="切块大小")
    chunk_overlap: int = Field(ge=0, description="切块重叠")
    strategy: Literal["fixed", "semantic"] = Field(default="fixed")

    @model_validator(mode="after")
    def overlap_less_than_size(self):
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap must be less than chunk_size")
        return self
```

在 `load_config()` 中集成：

```python
def load_config(config_path: str = "config.yaml") -> dict[str, Any]:
    with open(config_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    # Pydantic 验证（新增）
    validated = AppConfig(**config)    # 如果有问题，这里就报错
    config = validated.model_dump()    # 转回 dict，下游无感

    return config
```

如果有人把配置写错了：

```yaml
chunker:
  chunk_size: 0          # 不大于 0
  chunk_overlap: 999     # 大于 chunk_size
  strategy: "magic"      # 不在合法值内
```

程序启动时立刻报错：

```
ValidationError: 3 validation errors for AppConfig
chunker.chunk_size
  Input should be greater than 0 [input_value=0]
chunker.strategy
  Input should be 'fixed' or 'semantic' [input_value=magic]
chunker
  Value error, chunk_overlap must be less than chunk_size
```

三个问题，一目了然。

---

## 常见疑问

### Q: Pydantic 会让程序变慢吗？

不会。验证只在配置加载时执行一次（而且有缓存），耗时在毫秒级。相比之下，RAG 管线的一次查询可能要几秒到几十秒，验证的开销完全可以忽略。

### Q: 如果我想让某个字段可选怎么办？

给默认值就行：

```python
class MyConfig(BaseModel):
    required_field: str                    # 必填，不传就报错
    optional_field: str = "default_value"  # 可选，不传就用默认值
    maybe_none: str | None = None          # 可选，可以是 None
```

### Q: Pydantic v1 和 v2 有什么区别？

项目用的是 Pydantic v2（`>=2.13.3`）。v2 是 v1 的重大升级，核心 API 变化包括：

| v1 | v2 | 说明 |
|---|---|---|
| `.dict()` | `.model_dump()` | 导出为字典 |
| `@validator` | `@field_validator` | 字段验证器 |
| `@root_validator` | `@model_validator` | 模型级验证器 |
| `class Config:` | `model_config = {...}` | 模型配置 |

网上很多教程还在用 v1 语法，请注意区分。本项目全部使用 v2 语法。

### Q: 和 JSON Schema 有什么关系？

Pydantic 模型可以一键导出 JSON Schema：

```python
print(ChunkerConfig.model_json_schema())
```

这意味着未来如果要做配置的 IDE 自动补全、Web 表单校验等，都有现成的基础。

---

## 总结

| 维度 | 没有 Pydantic | 有 Pydantic |
|---|---|---|
| 错误发现时机 | 运行时（随机崩溃） | 加载时（立刻报错） |
| 报错信息 | 晦涩的 Python 异常 | 精确到字段的人话 |
| 校验代码位置 | 分散在十几个文件 | 集中在一个 schema 文件 |
| 配置文档 | YAML 注释（容易过时） | 代码即文档（永远同步） |
| 下游代码改动 | — | 零改动（验证后转回 dict） |
| 新增依赖 | — | 无（项目已有） |

一句话：**Pydantic 是配置文件的安检门——数据经过它检查后才能进入系统，有问题在门口就拦住，不让错误悄悄溜进去。**
