# Code Review 建议清单

> Date: 2026-04-17
> 来源：测试套件重新设计的 Code Review
>
> **状态标注版** — 2026-04-18 附加各建议当前状态。标签说明：✅ 已修复 | 📋 已安排（建议 spec 模式） | ❌ 已弃用

---

## 建议总览

| # | 状态 | 优先级 | 类别 | 建议 | 所在文件 |
|---|------|--------|------|------|---------|
| 1 | ✅ 已修复 | 🟡 中 | 代码重复 | 删除本地 `temp_project_dir` fixture，使用 conftest 的 | test_e2e_experiment.py |
| 2 | 📋 已安排 | 🟡 中 | 测试质量 | 避免访问 TokenTracker 私有属性 `_records` | test_generator.py |
| 3 | ✅ 已修复 | 🟡 中 | 警告清理 | 修复 PytestCollectionWarning | eval/experiment_reporter.py |
| 4 | 📋 已安排 | 🟢 低 | 覆盖缺口 | 添加 MRR 对 retrieved_sources 重复项的测试 | test_metrics.py |
| 5 | 📋 已安排 | 🟢 低 | 覆盖缺口 | 添加 `get_collection_info` 异常返回 None 的测试 | test_indexer.py |
| 6 | 📋 已安排 | 🟢 低 | 覆盖缺口 | 添加 `build_index` JSONL 加载失败优雅降级的测试 | test_indexer.py |
| 7 | 📋 已安排 | 🟢 低 | 覆盖缺口 | 添加 `get_llm_config` API key 缺失抛异常的测试 | test_utils.py |
| 8 | 📋 已安排 | 🟢 低 | 覆盖缺口 | 添加 `retrieve` 返回值 payload 默认值的测试 | test_retriever.py |
| 9 | 📋 已安排 | 🟢 低 | 代码优化 | 提取 Pipeline 测试的 7 层 @patch 为辅助函数 | test_pipeline.py |
| 10 | ✅ 已修复 | 🟢 低 | 确定性 | mock_embedder fixture 使用固定向量替代随机向量 | conftest.py |
| 11 | 📋 已安排 | 🟢 低 | 规范一致性 | 为旧测试补齐 `@pytest.mark.unit` marker | 多个文件 |

---

## 🟡 中等优先级建议

### 建议 1：✅ 已修复 — 删除 test_e2e_experiment.py 本地 fixture 重复

**解决的问题：** 代码重复（DRY 原则违反）

**现状：** `test_e2e_experiment.py` 第 10-39 行定义了本地 `temp_project_dir` fixture，与 `conftest.py` 第 54-69 行的同名 fixture 功能完全相同。pytest 的 fixture 解析规则会让本地 fixture 覆盖 conftest 的，功能不受影响，但造成代码重复。

**建议修改：** 删除 `test_e2e_experiment.py` 中的本地 `temp_project_dir` fixture，直接使用 conftest 的共享 fixture。

**影响范围：** 仅 `test_e2e_experiment.py`，无功能影响。

**修改示例：**
```python
# 删除 test_e2e_experiment.py 第 10-39 行的本地 fixture
# conftest.py 中的 fixture 会自动生效
```

---

### 建议 2：📋 已安排 — 避免访问 TokenTracker 私有属性

**解决的问题：** 测试与实现细节耦合（测试脆弱性）

**现状：** `test_generator.py` 第 79 行 `tracker._records[0]` 直接访问了 `TokenTracker` 的私有属性 `_records`。如果 `TokenTracker` 的内部实现变化（如改用 `defaultdict` 或调整属性名），这个测试会脆断。

**建议修改：** 通过公共 API 验证 token 记录行为。

**修改示例：**
```python
# 修改前
assert tracker.record_count == 1
record = tracker._records[0]
assert record.category == "rag_qa"

# 修改后
assert tracker.record_count == 1
records = tracker.get_records_by_category("rag_qa")
assert len(records) == 1
assert records[0].category == "rag_qa"
assert records[0].model_name == "LongCat-Flash-Lite"
```

**前提条件：** 需确认 `TokenTracker.get_records_by_category()` 方法存在且返回完整记录。

---

### 建议 3：✅ 已修复 — 修复 PytestCollectionWarning

**解决的问题：** 测试运行警告

**现状：** 每次运行 pytest 都会产生以下警告：
```
PytestCollectionWarning: cannot collect test class 'TestCaseResult' because it has a __init__ constructor
```
原因是 `eval/experiment_reporter.py` 中的 `TestCaseResult` dataclass 名字以 `Test` 开头，pytest 误以为是测试类。

**建议修改（二选一）：**

方案 A：在 `TestCaseResult` 类上添加标记（推荐，改动最小）
```python
@dataclass
class TestCaseResult:
    __test__ = False  # 告知 pytest 这不是测试类
    ...
```

方案 B：在 `pytest.ini` 中配置收集规则
```ini
[pytest]
collect_ignore_glob = ["eval/*"]
python_classes = !TestCaseResult
```

**推荐方案 A**，因为更精确且不影响其他类的收集。

---

## 🟢 低优先级建议

### 建议 4：📋 已安排 — 添加 MRR 对 retrieved_sources 重复项的测试

**解决的问题：** 隐含行为未显式验证

**现状：** 源码 `calculate_mrr` 对 `expected_sources` 转 `set` 去重，但对 `retrieved_sources` 保留原始顺序。如果 `retrieved_sources` 中有重复项（如 `["doc1", "doc1", "doc2"]`），第一个匹配位置的 rank 会被正确计算，但这是一个隐含行为。

**建议新增测试：**
```python
def test_duplicate_in_retrieved(self):
    retrieved = ["doc1", "doc1", "doc2"]
    expected = ["doc1"]
    assert calculate_mrr(retrieved, expected) == 1.0
```

**价值：** 显式文档化 `calculate_mrr` 对重复 retrieved source 的处理行为，防止未来修改引入回归。

---

### 建议 5：📋 已安排 — 添加 `get_collection_info` 异常路径测试

**解决的问题：** 异常路径覆盖缺口

**现状：** 源码 `VectorIndexer.get_collection_info()` 在异常时返回 `None`（第 196-198 行），但当前测试只验证了成功路径。

**建议新增测试：**
```python
@patch("src.indexer.QdrantClient")
def test_get_collection_info_error(self, mock_qdrant_class, mock_qdrant_client, temp_project_dir):
    mock_qdrant_class.return_value = mock_qdrant_client
    mock_qdrant_client.get_collection.side_effect = Exception("Collection not found")
    indexer = VectorIndexer(persist_dir=str(temp_project_dir / "data" / "vector_store"))
    info = indexer.get_collection_info()
    assert info is None
```

---

### 建议 6：📋 已安排 — 添加 `build_index` JSONL 加载失败优雅降级测试

**解决的问题：** 优雅降级行为未验证

**现状：** 源码 `VectorIndexer.build_index()` 在 JSONL 文件加载失败时会 log error 并 continue（第 162-172 行），但当前测试未覆盖此行为。

**建议新增测试：**
```python
@patch("src.indexer.QdrantClient")
def test_build_index_corrupted_jsonl(self, mock_qdrant_class, mock_qdrant_client, temp_project_dir):
    mock_qdrant_class.return_value = mock_qdrant_client
    chunks_dir = temp_project_dir / "data" / "chunks"
    bad_file = chunks_dir / "corrupted.jsonl"
    with open(bad_file, "w", encoding="utf-8") as f:
        f.write("not valid json\n")
    good_file = chunks_dir / "valid.jsonl"
    with open(good_file, "w", encoding="utf-8") as f:
        f.write(json.dumps({"chunk_id": "c1", "text": "valid", "metadata": {}}) + "\n")
    mock_embedder_inst = MagicMock()
    mock_embedder_inst.get_embedding_dimension.return_value = 1024
    mock_embedder_inst.embed_texts.return_value = np.random.randn(1, 1024).astype(np.float32)
    indexer.build_index(chunks_dir=str(chunks_dir), embedder=mock_embedder_inst)
    mock_embedder_inst.embed_texts.assert_called_once()
    texts_arg = mock_embedder_inst.embed_texts.call_args[0][0]
    assert len(texts_arg) == 1
    assert texts_arg[0] == "valid"
```

---

### 建议 7：📋 已安排 — 添加 `get_llm_config` API key 缺失测试

**解决的问题：** 关键错误路径未验证

**现状：** 源码 `get_llm_config()` 中，当 API key 环境变量未设置时，会调用 `get_env_var("LLM_API_KEY", required=True)` 抛出 `ValueError`。但当前所有测试都 mock 了 `os.getenv` 返回有效值。

**建议新增测试：**
```python
@patch("src.utils.os.getenv")
def test_api_key_missing_raises_error(self, mock_getenv):
    mock_getenv.side_effect = lambda key, default=None: {
        "LLM_MODEL_ID": "test-model",
        "LLM_BASE_URL": "https://api.test.com/",
    }.get(key, default)
    config = {"llm_presets": {"default": {"temperature": 0.5, "max_tokens": 2048}}}
    with pytest.raises(ValueError, match="Required environment variable"):
        get_llm_config(config)
```

---

### 建议 8：📋 已安排 — 添加 `retrieve` 返回值 payload 默认值测试

**解决的问题：** 默认值行为未验证

**现状：** 源码 `Retriever.retrieve()` 中，payload 的 `chunk_id` 默认 `""`、`text` 默认 `""`、`metadata` 默认 `{}`（通过 `result.payload.get(key, default)` 实现）。当前测试只验证了 payload 完整的情况。

**建议新增测试：**
```python
def test_retrieve_missing_payload_fields(self, mock_embedder, mock_qdrant_client):
    indexer = self._make_mock_indexer(mock_qdrant_client)
    mock_point = MagicMock()
    mock_point.payload = {}
    mock_point.score = 0.5
    mock_result = MagicMock()
    mock_result.points = [mock_point]
    mock_qdrant_client.query_points.return_value = mock_result
    retriever = Retriever(indexer=indexer, embedder=mock_embedder, top_k=5)
    results = retriever.retrieve("test query")
    assert results[0]["chunk_id"] == ""
    assert results[0]["text"] == ""
    assert results[0]["metadata"] == {}
```

---

### 建议 9：📋 已安排 — 提取 Pipeline 测试的 @patch 辅助函数

**解决的问题：** 视觉复杂度高，代码重复

**现状：** `test_pipeline.py` 的每个测试方法都有 7 层 `@patch` 装饰器和 7 个参数，视觉上较重且重复。

**建议修改：** 提取一个 fixture 或辅助函数来封装 mock 设置。

**修改示例：**
```python
@pytest.fixture
def mock_pipeline_deps():
    with patch("src.pipeline.load_config") as mock_load, \
         patch("src.pipeline.setup_logger") as mock_logger, \
         patch("src.pipeline.get_llm_config") as mock_llm, \
         patch("src.pipeline.Embedder") as mock_embedder, \
         patch("src.pipeline.VectorIndexer") as mock_indexer, \
         patch("src.pipeline.Retriever") as mock_retriever, \
         patch("src.pipeline.Generator") as mock_generator:
        mock_load.return_value = _make_config()
        mock_llm.return_value = _make_llm_config()
        yield SimpleNamespace(
            load_config=mock_load, embedder=mock_embedder,
            indexer=mock_indexer, retriever=mock_retriever,
            generator=mock_generator,
        )

def test_init_without_meal(self, mock_pipeline_deps):
    pipeline = RAGPipeline(config_path="dummy.yaml")
    mock_pipeline_deps.embedder.assert_called_once_with(
        model_name="test-model", device="cpu"
    )
```

**权衡：** 当前方式虽然重复，但每个测试的依赖关系是显式可见的，调试时更容易理解。fixture 方式更简洁但隐式依赖更多。两种方式各有优劣，建议根据团队偏好选择。

---

### 建议 10：✅ 已修复 — mock_embedder fixture 使用固定向量

**解决的问题：** 非确定性测试

**现状：** `conftest.py` 中 `mock_embedder` fixture 使用 `np.random.randn(1024)` 生成返回值，每次调用返回不同向量。对于当前测试无影响（测试不验证向量内容），但如果有未来测试需要确定性结果，可能产生不可复现的失败。

**建议修改：**
```python
@pytest.fixture
def mock_embedder():
    embedder = MagicMock()
    embedder.embedding_dim = 1024
    embedder.get_embedding_dimension.return_value = 1024
    np.random.seed(42)
    embedder.embed_query.return_value = np.random.randn(1024).astype(np.float32)
    embedder.embed_texts.return_value = np.random.randn(3, 1024).astype(np.float32)
    return embedder
```

**权衡：** 使用固定种子可能引入微妙的状态依赖（如果测试顺序变化）。更安全的方式是使用固定数组：
```python
embedder.embed_query.return_value = np.ones(1024, dtype=np.float32)
```

---

### 建议 11：📋 已安排 — 为旧测试补齐 `@pytest.mark.unit` marker

**解决的问题：** Marker 规范一致性

**现状：** 新增的 6 个测试文件全部标记了 `@pytest.mark.unit`，但重构前的旧测试文件（test_parser.py、test_chunker.py、test_meal.py 等）未添加此 marker。当前 168/356 (47%) 的测试标记了 `unit`。

**建议：** 逐步为旧测试补齐 `@pytest.mark.unit` marker，使 `pixi run pytest -m "unit"` 能覆盖所有纯单元测试。

**优先级说明：** 此项不影响测试正确性，仅影响 marker 过滤的完整性。可在日常开发中逐步补齐，无需专门安排。
