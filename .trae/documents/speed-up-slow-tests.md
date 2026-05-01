# Speed Up Slow Tests — 优化计划

## 目标

将 `pixi run test` 中的最慢测试耗时从 ~30s（累加 top-10）降到 ~5s 以内，整体 `pixi run test` 耗时从 37.5s 降到约 12-15s。

## 根因总结

| 测试 | 耗时 | 根因 |
|------|------|------|
| `test_supplement_skips_duplicate_question` | 12.30s | `locate_answer_chunks` 被传入 `Path()`（项目根目录），每轮循环做全项目 `rglob("*.jsonl")` 扫描 |
| `test_supplement_adds_deficit_questions` | 3.86s | 同上 |
| `test_supplement_allows_different_questions` | 3.33s | 同上 |
| `test_locate_returns_empty_when_no_chunks_dir` | 1.88s | `Path()` 传入 `locate_answer_chunks`，全项目扫描 |
| `test_evaluate_single_context_precision_error_handling` | 2.63s | 模块级 import `anthropic` + `RagasEvaluator` 触发 worker 进程内重导入 |
| `test_evaluate_single_context_precision_recall` | 2.52s | 同上 |
| `test_contexts_used_for_context_precision_recall_not_sources` | 2.45s | 同上 |
| `test_build_index` | 1.03s | BM25Retriever 初始化 + jieba 分词器初始化 |

---

## Step 1: 修复 supplement 测试中的 `Path()` 问题

**文件**: `tests/test_test_generator.py`

### 1.1 `TestSupplementDocumentBasedQuestions::test_supplement_adds_deficit_questions`（~3.86s → ~0.2s）

**改动**: 给 `meal_config` mock 对象添加 `config_hashes` 属性，让 `resolve_chunks_dir` 返回 `None`（而不是返回 `None` 后 fallback 到 `Path()`）。

同时 patch `resolve_chunks_dir` 为返回 `tmp_path / "nonexistent_chunks"`，确保不会扫描到项目根目录。

**具体操作**:
- 找到 `meal_config = MagicMock()` 处，添加：
  ```python
  meal_config.config_hashes = {"chunker": ""}
  ```
- 该测试已有 patch `resolve_parsed_dir`，再增加：
  ```python
  patch("src.test_generation.document_loader.resolve_chunks_dir", return_value=tmp_path / "no_chunks"),
  ```
  （注意：`resolve_chunks_dir` 在 `supplement.py` 中是通过 `from src.test_generation.document_loader import resolve_chunks_dir` 导入的，所以 patch target 应是 `src.test_generation.document_loader.resolve_chunks_dir`）

### 1.2 `TestQuestionDeduplication::test_supplement_skips_duplicate_question`（~12.30s → ~0.3s）

**改动**: 同上，添加 `config_hashes` 和 patch `resolve_chunks_dir`。

**具体操作**:
- 找到 `meal_config = MagicMock()` 处，添加 `meal_config.config_hashes = {"chunker": ""}`
- 在当前 `with (patch(...), ...)` 块中增加：
  ```python
  patch("src.test_generation.document_loader.resolve_chunks_dir", return_value=tmp_path / "no_chunks"),
  ```

### 1.3 `TestQuestionDeduplication::test_supplement_allows_different_questions`（~3.33s → ~0.2s）

**改动**: 同上。

**具体操作**:
- 找到 `meal_config = MagicMock()` 处，添加 `meal_config.config_hashes = {"chunker": ""}`
- 在 patch 块中增加 `resolve_chunks_dir` 的 patch

---

## Step 2: 修复 `test_locate_returns_empty_when_no_chunks_dir`

**文件**: `tests/test_test_generator.py`

**测试**: `TestLocateAnswerChunks::test_locate_returns_empty_when_no_chunks_dir`
- 当前传入 `chunks_dir=Path()`（项目根目录）
- 改为传入 `chunks_dir=tmp_path / "nonexistent_chunks_dir"`（不存在的临时目录）

**具体操作**:
- 将方法签名改为 `def test_locate_returns_empty_when_no_chunks_dir(self, tmp_path):`
- 将 `chunks_dir=Path()` 改为 `chunks_dir=tmp_path / "nonexistent_chunks_dir"`

---

## Step 3: 延迟导入 `RagasEvaluator`

**文件**: `tests/test_evaluators.py`

**改动**: 将顶层的 `from eval.evaluators.ragas_evaluator import RagasEvaluator` 移除，改为在使用处延迟导入。

**具体操作**:
- 删除第 13 行的 `from eval.evaluators.ragas_evaluator import RagasEvaluator`
- 找到 `class TestRagasEvaluator` 类，在 `setup_method` 或第一个测试方法中添加：
  ```python
  from eval.evaluators.ragas_evaluator import RagasEvaluator
  ```
- 或者直接在 `TestRagasEvaluator` 类中的每个使用 `RagasEvaluator` 的方法内部 import

---

## Step 4: 延迟导入 `Anthropic`

**文件**: `eval/metrics/generation.py`

**改动**: 将 `from anthropic import Anthropic` 从模块顶部移入实际使用它的函数内部。

**具体操作**:
- 删除第 5 行的 `from anthropic import Anthropic`
- 找到实际使用 `Anthropic` 的函数（如 `extract_statements`、`verify_statements`、`calculate_faithfulness` 等），在函数内部添加 `from anthropic import Anthropic`
- 如果 `Anthropic` 在多处使用，可以创建一个获取 client 的内部辅助函数，在其中做延迟导入

---

## Step 5: 复用 BM25Retriever 实例

**文件**: `tests/test_bm25_retriever.py`

**改动**: 用 `@pytest.fixture(scope="class")` 缓存已构建好索引的 `BM25Retriever` 实例。

**当前问题**: `test_build_index` 花费 1.03s，主要来自 jieba 分词初始化 + BM25 索引构建。

**具体操作**:
- 添加 class 级别的 fixture:
  ```python
  @pytest.fixture(scope="class")
  def indexed_retriever(self):
      retriever = BM25Retriever()
      retriever.build_index(self._make_test_chunks())
      return retriever
  ```
- `test_build_index` 保持独立（验证 build_index 本身）
- 其他需要已索引 retriever 的测试（`test_retrieve_*` 系列）使用 `indexed_retriever` fixture

---

## Step 6: 验证

每步完成后运行 `pixi run test` 确认耗时下降。

### 预期结果

| 优化后测试 | 预期耗时 |
|-----------|---------|
| `test_supplement_skips_duplicate_question` | < 0.5s |
| `test_supplement_adds_deficit_questions` | < 0.3s |
| `test_supplement_allows_different_questions` | < 0.3s |
| `test_locate_returns_empty_when_no_chunks_dir` | < 0.1s |
| `test_evaluate_single_context_precision_*` × 3 | < 1s (each) |
| `test_build_index` | < 0.5s |

**整体 `pixi run test` 总耗时**: 从 37.5s 降到 **12-15s**。

---

## 执行顺序

1. **Step 2** — 最简单，1 行改动，立即见效
2. **Step 1** — 3 个测试，核心修复
3. **Step 5** — BM25 fixture 复用
4. **Step 3** — 延迟导入 RagasEvaluator
5. **Step 4** — 延迟导入 Anthropic（可能影响面较大，需仔细检查）

每完成一步，运行 `pixi run test` 验证，然后按 auto-commit-enforcer 规范立即提交。
