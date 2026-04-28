# Test Review Suggestions Fixup Spec

## Why

Code Review 建议清单（`test-review-suggestions.md`）中有 8 条 📋 已安排但未修复的建议，需要逐条评估并实施合理的修复，同时维护原文档状态同步更新。

## What Changes

- 修改 `tests/test_generator.py`：将 `tracker._records[0]` 替换为 `tracker.get_records_by_category()` 公共 API 调用
- 修改 `tests/test_metrics.py`：新增 MRR 对 retrieved_sources 重复项的测试
- 修改 `tests/test_indexer.py`：新增 `get_collection_info` 异常返回 None 的测试
- 修改 `tests/test_indexer.py`：新增 `build_index` JSONL 加载失败优雅降级的测试
- 修改 `tests/test_utils.py`：新增 `get_llm_config` API key 缺失抛异常的测试
- 修改 `tests/test_retriever.py`：新增 `retrieve` 返回值 payload 默认值的测试
- 维护 `test-review-suggestions.md`：同步更新每条建议的修复状态

## 不修的建议及理由

### 建议 9：提取 Pipeline 测试的 @patch 辅助函数 — 不修

**理由：过度修复，没必要。** 原文档自身已指出权衡："当前方式虽然重复，但每个测试的依赖关系是显式可见的，调试时更容易理解。fixture 方式更简洁但隐式依赖更多。两种方式各有优劣，建议根据团队偏好选择。" 当前 7 层 `@patch` 虽然视觉上较重，但每个测试的 mock 依赖一目了然，调试时无需跳转到 fixture 定义去理解 mock 行为。提取为 fixture 反而增加了间接性，降低了可调试性。这不属于 bug 或测试质量问题，纯属风格偏好，不值得为此引入额外复杂度。

### 建议 11：为旧测试补齐 `@pytest.mark.unit` marker — 不修

**理由：过度修复，原文档也建议逐步补齐。** 原文档明确指出："此项不影响测试正确性，仅影响 marker 过滤的完整性。可在日常开发中逐步补齐，无需专门安排。" 补 marker 是纯机械操作，不改善测试质量，不修复任何 bug，且涉及多个文件（test_parser.py、test_chunker.py、test_meal.py 等）的批量修改，投入产出比极低。适合在日常开发中顺手补齐，不应作为独立任务执行。

## Impact

- Affected code: `tests/test_generator.py`, `tests/test_metrics.py`, `tests/test_indexer.py`, `tests/test_utils.py`, `tests/test_retriever.py`, `.trae/documents/test-suite/test-review-suggestions.md`
- 无 breaking changes，所有修改均为新增测试或替换测试内部实现方式

## ADDED Requirements

### Requirement: 测试不应访问被测对象的私有属性

测试代码 SHALL 通过公共 API 验证行为，而非直接访问私有属性（以 `_` 开头的属性）。

#### Scenario: TokenTracker 记录验证
- **WHEN** 测试需要验证 `TokenTracker` 的记录内容
- **THEN** 使用 `tracker.get_records_by_category()` 而非 `tracker._records`

### Requirement: MRR 对重复 retrieved_sources 的行为应有显式测试

`calculate_mrr` 对 `retrieved_sources` 中重复项的处理行为 SHALL 通过显式测试用例文档化。

#### Scenario: retrieved_sources 含重复项
- **WHEN** `retrieved_sources = ["doc1", "doc1", "doc2"]` 且 `expected_sources = ["doc1"]`
- **THEN** `calculate_mrr` 返回 `1.0`（第一个匹配位置的 rank）

### Requirement: get_collection_info 异常路径应有测试

`VectorIndexer.get_collection_info()` 在异常时返回 `None` 的行为 SHALL 有对应测试覆盖。

#### Scenario: Qdrant 抛出异常
- **WHEN** `QdrantClient.get_collection()` 抛出异常
- **THEN** `get_collection_info()` 返回 `None`

### Requirement: build_index JSONL 加载失败应有测试

`VectorIndexer.build_index()` 在 JSONL 文件加载失败时优雅降级的行为 SHALL 有对应测试覆盖。

#### Scenario: 损坏的 JSONL 文件被跳过，有效文件正常处理
- **WHEN** chunks 目录中同时存在损坏的 JSONL 文件和有效的 JSONL 文件
- **THEN** 损坏文件被跳过，有效文件的 chunks 被正常索引

### Requirement: get_llm_config API key 缺失应有测试

`get_llm_config()` 在 API key 环境变量未设置时抛出 `ValueError` 的行为 SHALL 有对应测试覆盖。

#### Scenario: LLM_API_KEY 环境变量缺失
- **WHEN** 调用 `get_llm_config()` 时 `LLM_API_KEY` 环境变量未设置
- **THEN** 抛出 `ValueError`，消息包含 "Required environment variable"

### Requirement: retrieve payload 默认值应有测试

`Retriever.retrieve()` 对 payload 缺失字段使用默认值的行为 SHALL 有对应测试覆盖。

#### Scenario: payload 中缺少 chunk_id、text、metadata 字段
- **WHEN** 检索结果的 payload 为空字典 `{}`
- **THEN** 返回结果中 `chunk_id` 为 `""`，`text` 为 `""`，`metadata` 为 `{}`

### Requirement: Code Review 建议文档状态同步

`test-review-suggestions.md` SHALL 始终反映每条建议的最新修复状态。

#### Scenario: 建议被修复后
- **WHEN** 某条建议被实施修复
- **THEN** 文档中该建议的状态更新为 ✅ 已修复，并注明修复方式

#### Scenario: 建议被决定不修
- **WHEN** 某条建议被评估后决定不修
- **THEN** 文档中该建议的状态更新为 ❌ 已弃用，并注明弃用理由
