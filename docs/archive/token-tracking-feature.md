# Token 统计功能实现计划

## 目标

为 RAG 系统增加完整的 LLM Token 消耗追踪功能，覆盖所有 LLM 调用场景，提供细粒度的 Token 消耗明细和成本估算能力。

## 现状分析

### LLM 调用点（3 处）

| 调用场景 | 文件 | 函数 | 当前状态 |
|----------|------|------|---------|
| RAG 问答 | `src/generator.py` | `Generator.generate()` | 忽略 `message.usage` |
| 测试集生成 | `src/test_generator.py` | `_generate_question_with_llm()` | 间接调用 Generator，无追踪 |
| 实验报告 | `eval/experiment_reporter.py` | `ExperimentReporter._call_llm()` | 忽略 `message.usage` |

### 关键发现

- Anthropic SDK 的 `messages.create()` 返回 `message.usage.input_tokens` / `message.usage.output_tokens`，当前完全未使用
- 项目已有 `tiktoken` 依赖（用于 chunker 分块），可用于 Token 估算
- `Generator.generate()` 返回 `str`，需扩展返回信息
- `pipeline.query()` 返回 `Dict[str, Any]`，可自然扩展

## 实现方案

### 核心设计原则

1. **双源统计**：API 返回的 `usage` 作为权威总量，tiktoken 估算作为细粒度拆分（system_prompt / contexts / query）
2. **累加器模式**：`TokenTracker` 作为共享累加器，贯穿整个实验流程
3. **向后兼容**：`Generator.generate()` 仍返回 `str`，额外通过属性和 tracker 暴露 Token 信息
4. **零侵入可选**：不传 tracker 则不追踪，现有代码无需修改即可运行

### Step 1: 创建 Token 数据模型和追踪器 (`src/token_tracker.py`)

新建文件，包含以下核心类：

```python
@dataclass
class TokenUsage:
    """单次 LLM 调用的 Token 用量"""
    input_tokens: int = 0
    output_tokens: int = 0
    
    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

@dataclass
class DetailedTokenUsage(TokenUsage):
    """带细粒度拆分的 Token 用量（input 侧拆分）"""
    system_prompt_tokens: int = 0   # 系统提示词
    contexts_tokens: int = 0        # 检索到的参考 chunk
    query_tokens: int = 0           # 用户问题部分
    # output 无法从 API 拆分，只有总量

@dataclass
class TokenRecord:
    """单次 LLM 调用的完整记录"""
    category: str           # "rag_qa" | "test_generation" | "report_generation"
    model_name: str
    usage: DetailedTokenUsage
    timestamp: str
    metadata: Dict[str, Any]  # question_id, variant_name 等

class TokenTracker:
    """Token 用量累加器"""
    def __init__(self):
        self._records: List[TokenRecord] = []
    
    def record(self, category, model_name, usage, **metadata) -> None: ...
    def get_summary_by_category(self) -> Dict[str, TokenUsage]: ...
    def get_total(self) -> TokenUsage: ...
    def get_detailed_table(self) -> str: ...     # 格式化为可读表格
    def estimate_cost(self, cost_config) -> Dict[str, float]: ...  # 成本估算
    def to_dict(self) -> Dict[str, Any]: ...     # 序列化为 JSON
    def merge(self, other: "TokenTracker") -> None: ...  # 合并多个 tracker
```

**tiktoken 拆分逻辑**：在 `Generator.generate()` 中，发送 API 请求前，用 tiktoken 分别计算 system_prompt、contexts 文本、query 文本的 token 数，与 API 返回的 `input_tokens` 做比例校正（因为 tiktoken 的编码与 Anthropic 内部编码不完全一致），确保拆分之和等于 API 返回的总量。

### Step 2: 修改 `Generator` (`src/generator.py`)

改动点：

1. `__init__()` 增加可选参数 `token_tracker: Optional[TokenTracker] = None`
2. `generate()` 中：
   - API 调用前：用 tiktoken 估算 system_prompt / contexts / query 各部分的 token 数
   - API 调用后：从 `message.usage` 获取权威的 `input_tokens` / `output_tokens`
   - 按比例校正 tiktoken 估算值，使拆分之和 = API 返回的 `input_tokens`
   - 如果有 tracker，调用 `tracker.record()` 记录
   - 将详细用量存入 `self.last_token_usage: Optional[DetailedTokenUsage]`
3. `generate()` 返回值不变，仍为 `str`（向后兼容）

### Step 3: 修改 `ExperimentReporter` (`eval/experiment_reporter.py`)

改动点：

1. `__init__()` 增加可选参数 `token_tracker: Optional[TokenTracker] = None`
2. `_call_llm()` 中：
   - API 调用后：从 `message.usage` 获取 token 用量
   - 此场景无 system_prompt 和 contexts，全部 input 归为 query
   - 如果有 tracker，调用 `tracker.record(category="report_generation", ...)`

### Step 4: 修改 `RAGPipeline` (`src/pipeline.py`)

改动点：

1. `__init__()` 中创建 `self.token_tracker = TokenTracker()`，传入 `Generator`
2. `query()` 返回值中增加 `token_usage` 字段（当前调用的详细用量）
3. 暴露 `self.token_tracker` 供外部访问累计数据

### Step 5: 修改实验运行器 (`eval/run_experiment.py`)

改动点：

1. `run_experiment()` 中创建顶层 `TokenTracker`
2. `run_variant_evaluation()` 中：
   - 将 tracker 传入 `RAGPipeline`
   - 评测完成后，从 pipeline 获取 tracker 快照，存入 variant_result
   - 重置 pipeline 的 tracker（每个 variant 独立统计）
3. `evaluate_test_set()` 中：每条问题的 result 增加单题 token 用量
4. `prepare_test_sets()` 中：追踪测试集生成阶段的 token 消耗
5. 报告生成阶段：将 tracker 传入 `ExperimentReporter`
6. 实验结束后：
   - 将总 token 统计写入实验结果 JSON
   - 在 CLI 输出中打印 Token 消耗汇总表
   - 写入实验报告 markdown

### Step 6: 添加配置项 (`config.yaml`)

在 `config.yaml` 中增加 `token_cost` 配置段：

```yaml
token_cost:
  # 各模型的折算系数和单价（每 1K token）
  # conversion_factor: 相对于基准模型的折算系数，用于跨模型成本对比
  models:
    LongCat-Flash-Lite:
      input_price_per_1k: 0.001
      output_price_per_1k: 0.002
      conversion_factor: 1.0
    claude-3-opus-20240229:
      input_price_per_1k: 0.015
      output_price_per_1k: 0.075
      conversion_factor: 15.0
    claude-3-5-sonnet-20241022:
      input_price_per_1k: 0.003
      output_price_per_1k: 0.015
      conversion_factor: 3.0
    claude-3-haiku-20240307:
      input_price_per_1k: 0.00025
      output_price_per_1k: 0.00125
      conversion_factor: 0.25
```

### Step 7: 修改入口脚本

#### `main.py` 和 `interactive.py`

- 单次查询后打印本次 Token 消耗
- 交互模式退出时打印累计 Token 消耗

### Step 8: 编写测试 (`tests/test_token_tracker.py`)

测试内容：
- `TokenUsage` / `DetailedTokenUsage` 数据模型
- `TokenTracker` 的记录、聚合、合并功能
- tiktoken 拆分 + 比例校正逻辑
- 成本估算逻辑
- `Generator` 的 token 追踪集成
- 序列化/反序列化

## 输出示例

### 实验结束后的 CLI 输出

```
============================================================
TOKEN USAGE SUMMARY
============================================================
Category             | Input Tokens | Output Tokens | Total Tokens
------------------------------------------------------------
RAG Q&A              |     125,430 |      42,180 |     167,610
Test Generation      |      38,200 |      12,600 |      50,800
Report Generation    |       5,200 |       2,800 |       8,000
------------------------------------------------------------
TOTAL                |     168,830 |      57,580 |     226,410

Detailed Breakdown (RAG Q&A):
  System Prompt      |      28,500 |           - |      28,500
  Contexts (chunks)  |      82,300 |           - |      82,300
  Query              |      14,630 |           - |      14,630

Estimated Cost (model: LongCat-Flash-Lite):
  Input:  $0.169  |  Output: $0.115  |  Total: $0.284
============================================================
```

### 实验结果 JSON 中的 token_usage 字段

```json
{
  "variant_name": "baseline",
  "token_usage": {
    "total": {"input_tokens": 168830, "output_tokens": 57580, "total_tokens": 226410},
    "by_category": {
      "rag_qa": {"input_tokens": 125430, "output_tokens": 42180},
      "test_generation": {"input_tokens": 38200, "output_tokens": 12600},
      "report_generation": {"input_tokens": 5200, "output_tokens": 2800}
    },
    "detailed_breakdown": {
      "rag_qa": {
        "system_prompt_tokens": 28500,
        "contexts_tokens": 82300,
        "query_tokens": 14630
      }
    },
    "estimated_cost": {
      "input_cost": 0.169,
      "output_cost": 0.115,
      "total_cost": 0.284,
      "model": "LongCat-Flash-Lite"
    }
  }
}
```

## 文件变更清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `src/token_tracker.py` | 新建 | Token 数据模型 + Tracker 累加器 |
| `src/generator.py` | 修改 | 接入 tracker，提取 usage，tiktoken 拆分 |
| `src/pipeline.py` | 修改 | 创建 tracker，传入 generator，query 返回增加 token_usage |
| `eval/experiment_reporter.py` | 修改 | 接入 tracker，追踪报告生成 token |
| `eval/run_experiment.py` | 修改 | 顶层 tracker 管理，结果集成，CLI 输出 |
| `config.yaml` | 修改 | 增加 token_cost 配置段 |
| `main.py` | 修改 | 单次/交互查询后显示 token 消耗 |
| `interactive.py` | 修改 | 退出时显示累计 token 消耗 |
| `tests/test_token_tracker.py` | 新建 | 单元测试 |

## 实施顺序

1. `src/token_tracker.py` — 数据模型和核心逻辑
2. `tests/test_token_tracker.py` — TDD：先写测试
3. `src/generator.py` — 接入追踪
4. `src/pipeline.py` — 串联 tracker
5. `eval/experiment_reporter.py` — 报告生成追踪
6. `eval/run_experiment.py` — 实验流程集成
7. `config.yaml` — 成本配置
8. `main.py` + `interactive.py` — 入口脚本
9. 运行测试验证
