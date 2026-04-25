# 缓存污染隐患修复 Spec

## Why

`docs/troubleshooting/cache-analysis.md` 调研报告识别了 RAG 链路中 6 类缓存机制的 12 个风险点（4 高 / 6 中 / 2 低）。其中 `cross_page_overlap` 未纳入哈希、部分解析失败后 manifest 不一致、并发写入无锁保护等问题，已在生产场景中具备触发条件，可能导致缓存数据被错误复用或覆盖。

## What Changes

- **修复 `compute_chunker_config_hash`**：将 `cross_page_overlap` 纳入哈希计算，确保参数变化时缓存正确失效
- **修复 `compute_embedding_config_hash`**：将 `dimension` 纳入哈希计算，防止向量维度不匹配
- **修复 `compute_parser_config_hash`**：将解析器版本信息纳入哈希计算
- **修复 `save_manifest` 并发安全**：添加文件锁保护，防止并发写入导致 manifest 损坏
- **修复部分解析失败后 manifest 不一致**：仅将成功解析的文件记入 `pdf_inventory`
- **修复 `LazyDocumentLoader` 缓存无失效机制**：加载时校验文件修改时间（mtime），过期自动重新加载
- **修复 `LazyDocumentLoader` 缓存无大小限制**：添加 LRU 淘汰机制（默认上限 128）
- **修复 `TestSetGenerator._doc_truncate_cache` 哈希不稳定**：用 `hashlib.sha256` 替代 `hash()`
- **增加 `data_id` 短 ID 长度**：从 12 位增加到 16 位，降低碰撞概率
- **为 `parsed_exists` / `chunks_exist` 添加 SHA-256 校验**：防止源文件变化后缓存被误用

## Impact

- Affected specs: ArtifactCache 缓存键计算、manifest 持久化、文档加载器、测试生成器
- Affected code: `src/meal.py`、`src/document_loader.py`、`src/test_generator.py`、`src/parser.py`
- **BREAKING**: `compute_chunker_config_hash` 变更后，现有 `chunks_{hash}` 目录将不再命中，需清理旧缓存

## ADDED Requirements

### Requirement: 完整的 chunker 配置哈希

`compute_chunker_config_hash` SHALL 将 `cross_page_overlap` 参数纳入哈希计算，确保该参数变化时缓存键不同。

#### Scenario: cross_page_overlap 变化导致缓存键不同
- **WHEN** 两个 chunker_config 仅 `cross_page_overlap` 不同
- **THEN** `compute_chunker_config_hash` 返回不同的哈希值

### Requirement: 完整的 embedding 配置哈希

`compute_embedding_config_hash` SHALL 将 `dimension` 参数纳入哈希计算，防止向量维度不匹配时缓存被误用。

#### Scenario: dimension 变化导致缓存键不同
- **WHEN** 两个 embedding_config 仅 `dimension` 不同
- **THEN** `compute_embedding_config_hash` 返回不同的哈希值

### Requirement: 完整的 parser 配置哈希

`compute_parser_config_hash` SHALL 将解析器库版本信息纳入哈希计算，防止库升级后缓存被误用。

#### Scenario: 解析器库版本变化导致缓存键不同
- **WHEN** 解析器依赖库版本发生变化
- **THEN** `compute_parser_config_hash` 返回不同的哈希值

### Requirement: manifest 并发写入安全

`ArtifactCache.save_manifest` SHALL 使用文件锁保护写入操作，防止并发写入导致数据损坏。

#### Scenario: 多进程同时写入同一 manifest
- **WHEN** 多个进程同时调用 `save_manifest` 写入同一 `data_id` 的 manifest
- **THEN** 所有写入操作串行执行，manifest 文件内容完整

### Requirement: 部分解析失败后 manifest 一致性

`parse_all_pdfs_unified` SHALL 仅将成功解析的文件记入 `pdf_inventory`，失败文件记入 `failed_inventory`。

#### Scenario: 部分 PDF 解析失败
- **WHEN** 10 个 PDF 中有 2 个解析失败
- **THEN** `pdf_inventory` 仅包含 8 个成功文件的 SHA-256，`failed_inventory` 包含 2 个失败文件路径

### Requirement: LazyDocumentLoader 缓存失效校验

`LazyDocumentLoader.get` SHALL 在返回缓存前校验文件修改时间（mtime），若文件已被修改则重新加载。

#### Scenario: 源文件在缓存后被修改
- **WHEN** 文档已缓存，但磁盘文件 mtime 发生变化
- **THEN** 重新加载文档并更新缓存

### Requirement: LazyDocumentLoader LRU 淘汰

`LazyDocumentLoader._cache` SHALL 使用 LRU 策略淘汰缓存，默认上限 128 个文档。

#### Scenario: 缓存数量超过上限
- **WHEN** 已缓存 128 个文档，加载第 129 个
- **THEN** 最久未访问的文档被淘汰

### Requirement: 稳定的文档截断缓存键

`TestSetGenerator._doc_truncate_cache` SHALL 使用 `hashlib.sha256` 计算缓存键，替代不稳定的 `hash()` 函数。

#### Scenario: 跨进程缓存键一致性
- **WHEN** 不同进程使用相同文档内容计算缓存键
- **THEN** 缓存键相同

### Requirement: 更长的 data_id 短 ID

`ArtifactCache.get_artifact_group_dir` SHALL 使用 `data_id` 前 16 位作为目录名，替代当前的 12 位。

#### Scenario: 短 ID 碰撞概率降低
- **WHEN** 使用 16 位短 ID（64 bits）
- **THEN** 碰撞概率从约 2^-24 降低至约 2^-32

### Requirement: parsed_exists / chunks_exist SHA-256 校验

`ArtifactCache.parsed_exists` 和 `ArtifactCache.chunks_exist` SHALL 在检查文件存在性的同时，校验源文件 SHA-256 是否与 manifest 一致。

#### Scenario: 源文件被修改但缓存目录仍存在
- **WHEN** 源 PDF 文件内容变化，但解析产物目录仍存在
- **THEN** `parsed_exists` 返回 False

## MODIFIED Requirements

### Requirement: ArtifactCache 缓存键计算

`compute_chunker_config_hash` 的 `relevant` 字典 SHALL 包含 `cross_page_overlap` 字段。

`compute_embedding_config_hash` 的 `relevant` 字典 SHALL 包含 `dimension` 字段（如配置中存在）。

`compute_parser_config_hash` 的 `relevant` 字典 SHALL 包含 `_version_hint` 字段（基于解析器库版本计算）。

## REMOVED Requirements

无移除的需求。
