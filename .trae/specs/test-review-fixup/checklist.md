# Test Review Fixup Checklist

## 建议 2：避免访问 TokenTracker 私有属性

- [x] `test_generator.py` 中不再有 `tracker._records` 的直接访问
- [x] 改用 `tracker.get_records_by_category()` 公共 API
- [x] 测试验证的断言内容与修改前等价（category、model_name、usage、metadata）

## 建议 4：MRR 对 retrieved_sources 重复项的测试

- [x] `test_metrics.py` 的 `TestCalculateMRR` 中新增 `test_duplicate_in_retrieved` 测试
- [x] 测试覆盖 `retrieved = ["doc1", "doc1", "doc2"]`, `expected = ["doc1"]` 场景
- [x] 断言结果为 `1.0`

## 建议 5：get_collection_info 异常路径测试

- [x] `test_indexer.py` 新增 `test_get_collection_info_error` 测试
- [x] mock `QdrantClient.get_collection` 抛出异常
- [x] 断言 `get_collection_info()` 返回 `None`

## 建议 6：build_index JSONL 加载失败优雅降级测试

- [x] `test_indexer.py` 新增 `test_build_index_corrupted_jsonl` 测试
- [x] 创建损坏的 JSONL 文件和有效的 JSONL 文件
- [x] 断言损坏文件被跳过，有效文件的 chunks 被正常处理

## 建议 7：get_llm_config API key 缺失测试

- [x] `test_utils.py` 新增 `test_api_key_missing_raises_error` 测试
- [x] mock `os.getenv` 使 `LLM_API_KEY` 缺失
- [x] 断言抛出 `ValueError`，消息匹配 "Required environment variable"

## 建议 8：retrieve payload 默认值测试

- [x] `test_retriever.py` 新增 `test_retrieve_missing_payload_fields` 测试
- [x] mock 检索结果 payload 为空字典
- [x] 断言返回结果中 `chunk_id == ""`, `text == ""`, `metadata == {}`

## 文档状态同步

- [x] `test-review-suggestions.md` 中建议 2、4、5、6、7、8 状态更新为 ✅ 已修复
- [x] `test-review-suggestions.md` 中建议 9 状态更新为 ❌ 已弃用，注明"过度修复，风格偏好不值得引入额外复杂度"
- [x] `test-review-suggestions.md` 中建议 11 状态更新为 ❌ 已弃用，注明"过度修复，原文档建议逐步补齐无需专门安排"
- [x] 建议总览表格状态列已同步更新

## 全量验证

- [x] `pixi run pytest tests/ -v` 全部通过（397 passed, 2 skipped; 1 pre-existing integration failure unrelated to changes）
