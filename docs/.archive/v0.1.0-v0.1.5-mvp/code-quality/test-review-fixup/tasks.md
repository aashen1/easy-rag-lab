# Tasks

- [x] Task 1: 修复建议 2 — 替换 `test_generator.py` 中对 `tracker._records` 私有属性的访问
  - [x] SubTask 1.1: 将 `tracker._records[0]` 替换为 `tracker.get_records_by_category("rag_qa")[0]`
  - [x] SubTask 1.2: 验证测试通过
  - [x] SubTask 1.3: git commit（msg: `fix(test): use public API instead of private _records in test_generator`）

- [x] Task 2: 修复建议 4 — 在 `test_metrics.py` 新增 MRR 对 retrieved_sources 重复项的测试
  - [x] SubTask 2.1: 在 `TestCalculateMRR` 中新增 `test_duplicate_in_retrieved` 方法
  - [x] SubTask 2.2: 验证测试通过
  - [x] SubTask 2.3: git commit（msg: `test(metrics): add test for MRR with duplicate retrieved sources`）

- [x] Task 3: 修复建议 5 — 在 `test_indexer.py` 新增 `get_collection_info` 异常返回 None 的测试
  - [x] SubTask 3.1: 新增 `test_get_collection_info_error` 测试方法
  - [x] SubTask 3.2: 验证测试通过
  - [x] SubTask 3.3: git commit（msg: `test(indexer): add test for get_collection_info error path`）

- [x] Task 4: 修复建议 6 — 在 `test_indexer.py` 新增 `build_index` JSONL 加载失败优雅降级的测试
  - [x] SubTask 4.1: 新增 `test_build_index_corrupted_jsonl` 测试方法
  - [x] SubTask 4.2: 验证测试通过
  - [x] SubTask 4.3: git commit（msg: `test(indexer): add test for build_index corrupted JSONL graceful degradation`）

- [x] Task 5: 修复建议 7 — 在 `test_utils.py` 新增 `get_llm_config` API key 缺失抛异常的测试
  - [x] SubTask 5.1: 新增 `test_api_key_missing_raises_error` 测试方法
  - [x] SubTask 5.2: 验证测试通过
  - [x] SubTask 5.3: git commit（msg: `test(utils): add test for get_llm_config missing API key error`）

- [x] Task 6: 修复建议 8 — 在 `test_retriever.py` 新增 `retrieve` 返回值 payload 默认值的测试
  - [x] SubTask 6.1: 新增 `test_retrieve_missing_payload_fields` 测试方法
  - [x] SubTask 6.2: 验证测试通过
  - [x] SubTask 6.3: git commit（msg: `test(retriever): add test for retrieve payload default values`）

- [x] Task 7: 更新 `test-review-suggestions.md` 文档状态
  - [x] SubTask 7.1: 将建议 2、4、5、6、7、8 的状态更新为 ✅ 已修复
  - [x] SubTask 7.2: 将建议 9、11 的状态更新为 ❌ 已弃用，并注明弃用理由
  - [x] SubTask 7.3: 更新建议总览表格中的状态列
  - [x] SubTask 7.4: git commit（msg: `docs: update test-review-suggestions status to reflect fixes and rejections`）

- [x] Task 8: 全量测试运行验证
  - [x] SubTask 8.1: 运行 `pixi run pytest tests/ -v` 确保所有测试通过（397 passed, 2 skipped, 1 pre-existing integration failure）

# Task Dependencies

- Task 1-6 之间无依赖，可并行执行
- Task 7 依赖 Task 1-6 全部完成（需要知道实际修复结果）
- Task 8 依赖 Task 1-6 全部完成
