# Tasks

- [x] Task 1: 修复 `compute_chunker_config_hash` —— 将 `cross_page_overlap` 纳入哈希计算
  - [x] SubTask 1.1: 在 `compute_chunker_config_hash` 的 `relevant` 字典中添加 `cross_page_overlap` 字段
  - [x] SubTask 1.2: 编写测试 `test_chunker_config_hash_includes_cross_page_overlap`：验证仅 `cross_page_overlap` 不同时哈希不同
  - [x] SubTask 1.3: 运行 `pixi run lint` 确保代码格式正确

- [x] Task 2: 修复 `compute_embedding_config_hash` —— 将 `dimension` 纳入哈希计算
  - [x] SubTask 2.1: 在 `compute_embedding_config_hash` 的 `relevant` 字典中添加 `dimension` 字段（如配置中存在）
  - [x] SubTask 2.2: 编写测试 `test_embedding_config_hash_includes_dimension`：验证仅 `dimension` 不同时哈希不同
  - [x] SubTask 2.3: 运行 `pixi run lint` 确保代码格式正确

- [x] Task 3: 修复 `compute_parser_config_hash` —— 将解析器版本信息纳入哈希计算
  - [x] SubTask 3.1: 在 `compute_parser_config_hash` 中获取解析器库版本号（如 pymupdf4llm 版本），纳入 `relevant` 字典的 `_version_hint` 字段
  - [x] SubTask 3.2: 编写测试 `test_parser_config_hash_includes_version`：验证版本号变化时哈希不同
  - [x] SubTask 3.3: 运行 `pixi run lint` 确保代码格式正确

- [x] Task 4: 修复 `save_manifest` 并发安全 —— 添加文件锁保护
  - [x] SubTask 4.1: 在 `save_manifest` 中使用 `filelock` 库添加文件锁
  - [x] SubTask 4.2: 在 `load_manifest` 中添加锁保护，防止读取正在写入的文件
  - [x] SubTask 4.3: 编写测试 `test_concurrent_manifest_write`：验证多线程写入 manifest 不损坏
  - [x] SubTask 4.4: 运行 `pixi run lint` 确保代码格式正确

- [x] Task 5: 修复部分解析失败后 manifest 不一致
  - [x] SubTask 5.1: 修改 `parse_all_pdfs_unified`，将 `pdf_inventory` 仅包含成功解析的文件，新增 `failed_inventory` 记录失败文件
  - [x] SubTask 5.2: 修改 `is_full_parsed_valid`，对 `failed_inventory` 中的文件触发重试
  - [x] SubTask 5.3: 编写测试 `test_partial_parse_manifest_consistency`：验证部分失败时 manifest 只含成功文件
  - [x] SubTask 5.4: 运行 `pixi run lint` 确保代码格式正确

- [x] Task 6: 修复 `LazyDocumentLoader` 缓存失效校验
  - [x] SubTask 6.1: 在 `_cache` 中存储 `(LoadedDocument, float_mtime)` 元组
  - [x] SubTask 6.2: 在 `get` 方法中，返回缓存前校验文件 mtime，若变化则重新加载
  - [x] SubTask 6.3: 编写测试 `test_cache_invalidation_on_source_change`：验证文件修改后缓存自动失效
  - [x] SubTask 6.4: 运行 `pixi run lint` 确保代码格式正确

- [x] Task 7: 修复 `LazyDocumentLoader` 缓存无大小限制 —— 添加 LRU 淘汰
  - [x] SubTask 7.1: 将 `_cache` 从 `dict` 改为 `OrderedDict`，实现 LRU 淘汰
  - [x] SubTask 7.2: 添加 `max_cache_size` 参数（默认 128），在 `get` 中淘汰最久未访问的条目
  - [x] SubTask 7.3: 编写测试 `test_lru_eviction`：验证缓存超过上限时淘汰最久未访问的文档
  - [x] SubTask 7.4: 运行 `pixi run lint` 确保代码格式正确

- [x] Task 8: 修复 `TestSetGenerator._doc_truncate_cache` 哈希不稳定
  - [x] SubTask 8.1: 将 `str(hash(document_content[:1000]))` 替换为 `hashlib.sha256(document_content[:1000].encode()).hexdigest()[:16]`
  - [x] SubTask 8.2: 编写测试 `test_doc_truncate_cache_key_stability`：验证相同内容在不同调用中产生相同缓存键
  - [x] SubTask 8.3: 运行 `pixi run lint` 确保代码格式正确

- [x] Task 9: 增加 `data_id` 短 ID 长度
  - [x] SubTask 9.1: 将 `get_artifact_group_dir` 中 `data_id[:12]` 改为 `data_id[:16]`
  - [x] SubTask 9.2: 编写测试 `test_short_id_length`：验证目录名使用 16 位短 ID
  - [x] SubTask 9.3: 运行 `pixi run lint` 确保代码格式正确

- [x] Task 10: 为 `parsed_exists` / `chunks_exist` 添加 SHA-256 校验
  - [x] SubTask 10.1: 修改 `parsed_exists`，接受可选 `manifest` 参数，若提供则校验源文件 SHA-256
  - [x] SubTask 10.2: 修改 `chunks_exist`，接受可选 `manifest` 参数，若提供则校验源文件 SHA-256
  - [x] SubTask 10.3: 编写测试 `test_parsed_exists_sha_validation`：验证源文件变化后 `parsed_exists` 返回 False
  - [x] SubTask 10.4: 运行 `pixi run lint` 确保代码格式正确

# Task Dependencies

- [Task 6] 和 [Task 7] 都修改 `LazyDocumentLoader`，需串行执行（先 Task 6 再 Task 7）
- [Task 5] 修改 `parse_all_pdfs_unified` 和 `is_full_parsed_valid`，与 Task 4（manifest 文件锁）有轻微关联，建议先完成 Task 4
- 其余 Task 互相独立，可并行执行
