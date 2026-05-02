# 并发优化计划：充分利用 API 并发能力加速实验

## 背景分析

项目已有**三层并发机制**，默认值可能偏保守：

| 并发层        | 配置路径                                    | 当前默认值 | 机制                                 | 控制范围        |
| ---------- | --------------------------------------- | ----- | ---------------------------------- | ----------- |
| 问题查询       | `evaluation.concurrent_queries`         | 5     | `ThreadPoolExecutor` + pipeline 克隆 | RAG 问答并发数   |
| Builtin 评估 | `evaluation.builtin_concurrent_workers` | 8     | `ThreadPoolExecutor`               | 生成指标计算并发数   |
| RAGAS 评估   | `ragas.run_config.max_workers`          | 5     | RAGAS 框架内部 `RunConfig`             | RAGAS 评测并发数 |

**串行瓶颈**：测试集生成（`src/test_generation/generator.py`）完全串行，无并发支持。

**现有压力测试脚本问题**：`scripts/stress_test_concurrency.py` 发送的是裸 API 调用（无上下文、无检索），与真实 exp 流量的 token 消耗模式差异大，测出来的极限不靠谱。需要重写。

***

## 执行步骤

### Step 1：跑一次小实验，观察 API 调用日志

* 复用 `exp_configs/smoke_tests/` 下的配置，或创建一个 5-10 题的冒烟配置

* 运行 `pixi run exp <name>`，观察日志中 API 调用的时序和耗时

* 确认三层并发是否实际生效，日志中是否有并发请求的迹象

* **目的**：建立对当前串行/并发行为的直观认识

### Step 2：重写压力测试脚本，走真实 exp 并发路径

**核心思路**：不再发裸 API 请求，而是通过真实 exp 系统的并发路径来测压，使 token 消耗模式与实际实验一致。

**新脚本** `scripts/stress_test_concurrency_v2.py`，分两阶段：

#### Phase 1 — Query 阶段（模拟 `collect_rag_samples_concurrent`）

* 加载真实 Meal + 向量索引，构建 `RAGPipeline`

* 准备 5-10 个真实问题（从已有 test\_set 加载，或硬编码几个金融研报问题）

* 对不同 `concurrent_queries` 值（如 1, 3, 5, 8, 10, 15, 20, 30），调用 `_collect_rag_samples_concurrent()`

* 每轮记录：wall time、每题延迟、429 错误数、token 消耗

* 二分搜索找到不触发 429 的最大安全并发数

#### Phase 2 — Evaluation 阶段（模拟 `BuiltinEvaluator.evaluate_batch`）

* 用 Phase 1 产出的 samples 作为输入

* 对不同 `builtin_concurrent_workers` 值，调用 `BuiltinEvaluator.evaluate_batch()`

* 每轮记录：wall time、每题延迟、429 错误数、token 消耗

* 二分搜索找到不触发 429 的最大安全并发数

**与旧脚本的区别**：

* Phase 1 走的是 `pipeline.query()` → 检索 + 生成，prompt 包含完整 RAG 上下文（与真实实验一致）

* Phase 2 走的是 `BuiltinEvaluator.evaluate_single()` → faithfulness/answer\_relevancy 计算，prompt 包含完整上下文和回答（与真实实验一致）

* token 消耗模式与真实实验高度一致，测出的并发极限更可靠

**脚本接口**：

```bash
pixi run python scripts/stress_test_concurrency_v2.py \
  --meal <meal_name> \
  --questions 10 \
  --hi 30 \
  --lo 1
```

### Step 3：为 API 调用添加 429 指数退避

当前代码对 429 没有自动重试，高并发下偶发 429 会导致样本丢失。需要在所有 LLM API 调用点添加指数退避。

**实现方案**：创建一个通用的 API 调用包装函数，统一处理 429 重试。

#### 3.1 创建 `src/llm_retry.py`

```python
def call_with_retry(
    fn: Callable,
    *args,
    max_retries: int = 5,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    **kwargs,
) -> Any:
    """带指数退避的 API 调用包装。

    检测 429 / rate_limit / overloaded 错误，自动重试。
    延迟公式：min(base_delay * 2^attempt + jitter, max_delay)
    """
```

* 识别 429 / `rate_limit_error` / `overloaded_error` 等可重试错误

* 指数退避 + 随机抖动（jitter），避免雷群效应

* 非速率限制错误直接抛出，不重试

* 每次重试记录日志（含等待时间、剩余重试次数）

#### 3.2 在关键 API 调用点接入重试

需要修改的文件和调用点：

| 文件                                       | 调用点                                  | 用途                            |
| ---------------------------------------- | ------------------------------------ | ----------------------------- |
| `src/generator.py:255`                   | `self.client.messages.create()`      | RAG 问答生成                      |
| `src/query_rewriter.py:208`              | `client.messages.create()`           | 查询改写                          |
| `eval/metrics/generation.py:134,221,473` | `client.messages.create()`           | Faithfulness/Answer Relevancy |
| `eval/metrics/llm_retrieval.py:90,255`   | `client.messages.create()`           | Context Precision/Recall      |
| `src/test_generation/llm_caller.py`      | `generator.generate()`               | 测试集生成                         |
| `src/testset_review/ai_reviewer.py:68`   | `self.client.messages.create()`      | AI 评审                         |
| `eval/reporter/llm_reporter.py:153`      | `self._llm_client.messages.create()` | LLM 报告                        |

**接入方式**：将 `client.messages.create(...)` 替换为 `call_with_retry(client.messages.create, ...)`，保持其他参数不变。

**配置化**：在 `config.yaml` 中添加重试配置：

```yaml
llm_retry:
  max_retries: 5
  base_delay: 1.0
  max_delay: 60.0
```

#### 3.3 RAGAS 的 429 处理

RAGAS 通过 `LangchainLLMWrapper(ChatAnthropic)` 调用 API，不直接经过我们的代码。处理方式：

* RAGAS 的 `RunConfig` 已有 `max_retries` 和 `timeout`，但退避策略不可控

* 方案：在 `ChatAnthropic` 初始化时，通过 `max_retries` 参数让 langchain-anthropic 自带重试

* 如果不够，可以在 `LangchainLLMWrapper` 外层再包一层带退避的包装器

### Step 4：运行压力测试，测定 429 极限

* 运行 Step 2 的新脚本

* 记录两阶段结果：

  * **Query 阶段**：最大安全并发数（基于真实 RAG 流量）

  * **Evaluation 阶段**：最大安全并发数（基于真实评测流量）

* 如果 30 并发都没触发 429，逐步调高 `--hi`

### Step 5：更新 config.yaml 默认值

根据 Step 4 的结果，将最优并发数写入 `config.yaml`：

```yaml
evaluation:
  concurrent_queries: <Query阶段safe_max-2>
  builtin_concurrent_workers: <Evaluation阶段safe_max-2>
  ragas:
    run_config:
      max_workers: <Evaluation阶段safe_max-2>
```

安全策略：取 `safe_max - 2` 作为默认值，留出余量。有了 Step 3 的指数退避，即使偶发 429 也能自动恢复，所以余量可以比以前更激进一些。

### Step 6：为测试集生成添加并发支持

测试集生成是唯一完全串行的 LLM 调用环节。当问题量大时（如 50+ 题），是显著瓶颈。

* 新增配置项 `test_generation.concurrent_generation`（默认 1=串行）

* 在 `generate_hybrid_questions()` 中，对每个文档的问题生成使用 `ThreadPoolExecutor` 并发

* 每个 worker 使用独立的 `Generator` 实例

* 复用 `src/llm_retry.py` 的退避机制

### Step 7：验证与回归测试

* 用调整后的配置重新运行 Step 1 的小实验，确认：

  * 并发确实生效（日志中多个问题同时处理）

  * 429 被指数退避自动处理（日志中有重试记录）

  * 结果与串行一致（指标值不变）

* 运行 `pixi run test` 确保无回归

***

## 文件变更清单

| 操作 | 文件                                      | 说明                             |
| -- | --------------------------------------- | ------------------------------ |
| 新建 | `src/llm_retry.py`                      | 通用指数退避重试包装                     |
| 新建 | `scripts/stress_test_concurrency_v2.py` | 基于真实 exp 路径的压力测试               |
| 修改 | `src/generator.py`                      | API 调用接入 `call_with_retry`     |
| 修改 | `src/query_rewriter.py`                 | API 调用接入 `call_with_retry`     |
| 修改 | `eval/metrics/generation.py`            | 3 处 API 调用接入 `call_with_retry` |
| 修改 | `eval/metrics/llm_retrieval.py`         | 2 处 API 调用接入 `call_with_retry` |
| 修改 | `src/test_generation/llm_caller.py`     | API 调用接入 `call_with_retry`     |
| 修改 | `src/testset_review/ai_reviewer.py`     | API 调用接入 `call_with_retry`     |
| 修改 | `eval/reporter/llm_reporter.py`         | API 调用接入 `call_with_retry`     |
| 修改 | `config.yaml`                           | 更新并发默认值 + 添加 `llm_retry` 配置    |
| 修改 | `src/test_generation/generator.py`      | 添加并发生成支持                       |
| 修改 | `eval/evaluators/ragas_evaluator.py`    | RAGAS LLM 客户端添加重试              |

***

## 风险与注意事项

* **API 提供商差异**：不同模型/API 代理的 rate limit 不同，压力测试结果仅适用于当前配置的 API

* **线程安全**：新增并发代码需确保线程安全，复用 pipeline 克隆模式

* **RAGAS 退避**：RAGAS 框架内部的 429 处理不完全可控，可能需要额外包装

* **测试覆盖**：`src/llm_retry.py` 需要编写单元测试（mock 429 响应验证退避行为）

