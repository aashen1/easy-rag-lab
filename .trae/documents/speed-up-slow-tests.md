# Speed Up Slow Tests — 优化计划

## 目标

将 `pixi run test` 中的最慢测试耗时从 \~30s（累加 top-10）降到 \~5s 以内，整体 `pixi run test` 耗时从 37.5s 降到约 12-15s。

## 根因总结

| 测试                                                            | 耗时     | 根因                                                                                                                  |
| ------------------------------------------------------------- | ------ | ------------------------------------------------------------------------------------------------------------------- |
| `test_supplement_skips_duplicate_question`                    | 12.30s | `supplement.py` 中 `or Path()` 兜底导致 `locate_answer_chunks` 收到项目根目录，每轮循环做全项目 `rglob("*.jsonl")` 扫描                    |
| `test_supplement_adds_deficit_questions`                      | 3.86s  | 同上                                                                                                                  |
| `test_supplement_allows_different_questions`                  | 3.33s  | 同上                                                                                                                  |
| `test_locate_returns_empty_when_no_chunks_dir`                | 1.88s  | 测试直接传入 `Path()`，`locate_answer_chunks` 对项目根做全项目扫描                                                                   |
| `test_evaluate_single_context_precision_error_handling`       | 2.63s  | `BuiltinEvaluator` 模块级导入链触发 `eval.metrics.generation` → `from anthropic import Anthropic`（顶层导入），anthropic SDK 初始化耗时 |
| `test_evaluate_single_context_precision_recall`               | 2.52s  | 同上                                                                                                                  |
| `test_contexts_used_for_context_precision_recall_not_sources` | 2.45s  | 同上                                                                                                                  |
| `test_build_index`                                            | 1.03s  | BM25Retriever 初始化 + jieba 分词器初始化，5 个 retrieve 测试各自重复 build\_index                                                   |

### 根因链路详解

**慢根因 A —** **`Path()`** **兜底触发全项目扫描**：

```
supplement.py:143-145  (三处相同模式)
  resolved_dir = chunks_dir or resolve_chunks_dir(config, meal_config) or Path()
  → 当 MagicMock 没有 config_hashes 时，resolve_chunks_dir 返回 None
  → or Path() 兜底为项目根目录
  → locate_answer_chunks(chunks_dir=Path()) 
  → chunk_locator.py:455  chunks_dir.rglob("*.jsonl")  ← 全项目递归扫描
```

关键：`chunk_locator.py:448` 的守卫 `if not chunks_dir or not chunks_dir.exists()` 对 `Path()` 无效——`Path()` 是 truthy 且 `Path().exists()` 为 True。

**慢根因 B —** **`anthropic`** **SDK 过早导入**：

```
test_evaluators.py
  → builtin_evaluator.py (line 12)
    → eval.metrics.__init__ (line 14)
      → eval.metrics.generation (line 13)
        → from anthropic import Anthropic (line 5) ← 顶层导入，模块加载即触发
```

注意：`RagasEvaluator` 的所有 ragas/torch 依赖已经是延迟导入（在方法内部 import），不是慢根因。慢根因是 `BuiltinEvaluator` 的导入链触发了 `anthropic`。

***

## Step 1: 修复 supplement 测试中的 `Path()` 问题

**文件**: `tests/test_test_generator.py`

### 1.1 `TestSupplementDocumentBasedQuestions::test_supplement_adds_deficit_questions`（\~3.86s → \~0.2s）

**改动**: patch `resolve_chunks_dir` 返回一个不存在的临时路径，阻止 `or Path()` 兜底到项目根目录。

**具体操作**:

* 该测试已有 patch `resolve_parsed_dir`，再增加：

  ```python
  patch("src.test_generation.supplement.resolve_chunks_dir", return_value=tmp_path / "no_chunks"),
  ```

  > ⚠️ **关键：patch target 必须是** **`src.test_generation.supplement.resolve_chunks_dir`，不是** **`src.test_generation.document_loader.resolve_chunks_dir`！**
  >
  > 原因：`supplement.py` 通过 `from src.test_generation.document_loader import resolve_chunks_dir` 导入，这会在 `supplement` 模块的命名空间创建本地绑定。`patch("...document_loader.resolve_chunks_dir")` 只替换源模块属性，不会影响已绑定的本地名称。必须 patch 使用方模块的属性才能生效。

* `meal_config.config_hashes = {"chunker": ""}` 可加可不加——空字符串是 falsy，`resolve_chunks_dir` 仍返回 None，真正起修复作用的是 patch 本身。如果加，建议用非空 hash 值如 `{"chunker": "testhash"}` 以保持语义一致性，但这不影响性能修复。

### 1.2 `TestQuestionDeduplication::test_supplement_skips_duplicate_question`（\~12.30s → \~0.3s）

**改动**: 同上，patch `resolve_chunks_dir`。

**具体操作**:

* 在当前 `with (patch(...), ...)` 块中增加：

  ```python
  patch("src.test_generation.supplement.resolve_chunks_dir", return_value=tmp_path / "no_chunks"),
  ```

  > 同样，patch target 必须是 `src.test_generation.supplement.resolve_chunks_dir`。

### 1.3 `TestQuestionDeduplication::test_supplement_allows_different_questions`（\~3.33s → \~0.2s）

**改动**: 同上。

**具体操作**:

* 在 patch 块中增加：

  ```python
  patch("src.test_generation.supplement.resolve_chunks_dir", return_value=tmp_path / "no_chunks"),
  ```

***

## Step 2: 修复 `test_locate_returns_empty_when_no_chunks_dir`

**文件**: `tests/test_test_generator.py`

**测试**: `TestLocateAnswerChunks::test_locate_returns_empty_when_no_chunks_dir`

* 当前传入 `chunks_dir=Path()`（项目根目录）

* 改为传入 `chunks_dir=tmp_path / "nonexistent_chunks_dir"`（不存在的临时目录）

**具体操作**:

* 将方法签名改为 `def test_locate_returns_empty_when_no_chunks_dir(self, tmp_path):`

* 将 `chunks_dir=Path()` 改为 `chunks_dir=tmp_path / "nonexistent_chunks_dir"`

***

## Step 3: 延迟导入 `anthropic`（在 `eval/metrics/__init__.py` 层面）

**文件**: `eval/metrics/__init__.py`

**改动**: 将 `from eval.metrics.generation import ...` 从模块顶层导入改为延迟导入，避免 `anthropic` SDK 在 `BuiltinEvaluator` 被导入时触发加载。

**根因分析**: 三个 context\_precision 测试慢的原因不是 `RagasEvaluator`（其 ragas/torch 依赖已是延迟导入），而是 `BuiltinEvaluator` 的导入链：

```
builtin_evaluator.py → eval.metrics.__init__ → eval.metrics.generation → from anthropic import Anthropic
```

`anthropic` 在 `generation.py` 顶层被导入，而 `eval/metrics/__init__.py` 顶层 `from eval.metrics.generation import ...` 会在任何 `eval.metrics` 被导入时触发。

**具体操作**:

* 在 `eval/metrics/__init__.py` 中，将 `from eval.metrics.generation import (...)` 改为 `__getattr__` 延迟导入模式：

  ```python
  _GENERATION_EXPORTS = [
      "calculate_answer_relevancy",
      "calculate_faithfulness",
      "calculate_hallucination_rate",
      "extract_statements",
      "parse_relevancy_response",
      "verify_statements",
  ]

  def __getattr__(name):
      if name in _GENERATION_EXPORTS:
          from eval.metrics.generation import (
              calculate_answer_relevancy,
              calculate_faithfulness,
              calculate_hallucination_rate,
              extract_statements,
              parse_relevancy_response,
              verify_statements,
          )
          globals()[name] = locals()[name]
          return locals()[name]
      raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
  ```

* `__all__` 列表保持不变，确保 `from eval.metrics import calculate_faithfulness` 仍然可用。

* 其他子模块（`chunk`、`dedup`、`fpr`、`llm_retrieval`、`retrieval`、`utils`）的顶层导入保持不变，它们不触发重量级依赖。

**替代方案**: 如果觉得 `__getattr__` 模式不够直观，也可以只修改 `generation.py` 本身（见 Step 3B），但 `__init__.py` 层面的延迟导入更彻底——即使未来有其他模块间接导入 `eval.metrics`，也不会触发 `anthropic`。

### Step 3B（可选）: 同时在 `generation.py` 内部也做延迟导入

**文件**: `eval/metrics/generation.py`

**改动**: 将 `from anthropic import Anthropic` 从模块顶部移入实际使用它的函数内部。

**具体操作**:

* 在文件顶部添加 `from __future__ import annotations`（**必须**，否则 `extract_statements` 和 `verify_statements` 函数签名中的 `client: Anthropic` 类型注解会在模块加载时求值，导致 `NameError`）

* 删除第 5 行的 `from anthropic import Anthropic`

* 在 `extract_statements` 函数内部添加 `from anthropic import Anthropic`

* 在 `verify_statements` 函数内部添加 `from anthropic import Anthropic`

* `calculate_faithfulness` 和 `calculate_answer_relevancy` 不直接使用 `Anthropic` 类型（它们通过 `create_llm_client` 获取 client），无需修改

> ⚠️ **必须加** **`from __future__ import annotations`**，否则删除顶层 `from anthropic import Anthropic` 后，函数签名 `client: Anthropic` 会在模块加载时触发 `NameError: name 'Anthropic' is not defined`。`from __future__ import annotations` 让所有注解变成字符串延迟求值，避免此问题。

***

## Step 4: 复用 BM25Retriever 实例

**文件**: `tests/test_bm25_retriever.py`

**改动**: 用 `@pytest.fixture(scope="class")` 缓存已构建好索引的 `BM25Retriever` 实例。

**当前问题**: `test_build_index` 花费 1.03s，主要来自 jieba 分词初始化 + BM25 索引构建。5 个 retrieve 测试各自独立 `build_index`，重复 jieba 初始化开销。

**具体操作**:

* 添加 class 级别的 fixture:

  ```python
  @pytest.fixture(scope="class")
  def indexed_retriever(self):
      retriever = BM25Retriever()
      retriever.build_index(self._make_test_chunks())
      return retriever
  ```

* `test_build_index` 保持独立（验证 build\_index 本身）

* 其他需要已索引 retriever 的测试（`test_retrieve_*` 系列）改为使用 `indexed_retriever` fixture 参数：

  ```python
  def test_retrieve_returns_results(self, indexed_retriever):
      results = indexed_retriever.retrieve("茅台营业收入", top_k=2)
      ...
  ```

* 确认所有使用 fixture 的测试都是只读操作（不修改 retriever 状态），当前代码符合此条件。

***

## Step 5: 验证

每步完成后运行 `pixi run test` 确认耗时下降。

### 预期结果

| 优化后测试                                          | 预期耗时          | 对应步骤   |
| ---------------------------------------------- | ------------- | ------ |
| `test_supplement_skips_duplicate_question`     | < 0.5s        | Step 1 |
| `test_supplement_adds_deficit_questions`       | < 0.3s        | Step 1 |
| `test_supplement_allows_different_questions`   | < 0.3s        | Step 1 |
| `test_locate_returns_empty_when_no_chunks_dir` | < 0.1s        | Step 2 |
| `test_evaluate_single_context_precision_*` × 3 | < 1s (each)   | Step 3 |
| `test_build_index`                             | < 0.5s        | Step 4 |
| `test_retrieve_*` × 5                          | < 0.1s (each) | Step 4 |

**整体** **`pixi run test`** **总耗时**: 从 37.5s 降到 **12-15s**。

***

## 执行顺序

1. **Step 2** — 最简单，1 行改动，立即见效
2. **Step 1** — 3 个测试，核心修复（注意 patch target 必须是 `src.test_generation.supplement.resolve_chunks_dir`）
3. **Step 3** — `eval/metrics/__init__.py` 延迟导入 generation 子模块（可选同时做 Step 3B）
4. **Step 4** — BM25 fixture 复用

每完成一步，运行 `pixi run test` 验证，然后按 auto-commit-enforcer 规范立即提交。

***

## 原计划错误修正记录

| 原计划内容                                                                         | 问题                                                                                         | 修正                                                       |
| ----------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------ | -------------------------------------------------------- |
| Step 1 patch target: `src.test_generation.document_loader.resolve_chunks_dir` | ❌ `supplement.py` 用 `from ... import` 创建了本地绑定，patch 源模块属性不影响已绑定的本地名称                       | ✅ 改为 `src.test_generation.supplement.resolve_chunks_dir` |
| Step 1 添加 `meal_config.config_hashes = {"chunker": ""}`                       | ⚠️ 空字符串是 falsy，`resolve_chunks_dir` 仍返回 None，实际不起作用                                        | ✅ patch 本身才是修复手段；config\_hashes 可加可不加                    |
| Step 3 根因: "模块级 import `anthropic` + `RagasEvaluator`"                        | ❌ `RagasEvaluator` 的 ragas/torch 依赖已是延迟导入，不是慢根因；慢根因是 `BuiltinEvaluator` 的导入链触发 `anthropic` | ✅ 改为在 `eval/metrics/__init__.py` 层面延迟导入 `generation` 子模块 |
| Step 4 删除顶层 `from anthropic import Anthropic`                                 | ⚠️ 遗漏了函数签名 `client: Anthropic` 类型注解会在模块加载时求值，导致 `NameError`                                | ✅ 必须同时添加 `from __future__ import annotations`            |

