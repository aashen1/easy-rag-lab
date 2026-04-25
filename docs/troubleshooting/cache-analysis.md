# RAG 链路缓存机制隐患调研报告

> 任务量比较大，需要用spec模式，换用最强模型来做。

## 概述

本文档对 `ash-easy-rag` 项目中 RAG 链路的缓存机制进行深度调研，识别潜在的缓存命中失败和缓存污染风险点，并提出改进建议。

---

## 1. 缓存机制全景图

项目中存在 **6 类缓存机制**，分布在 RAG 链路的不同环节：

| 缓存类型 | 位置 | 生命周期 | 缓存介质 | 主要用途 |
|---------|------|---------|---------|---------|
| ArtifactCache | `src/meal.py` | 持久化 | 文件系统 | 解析/分块产物缓存 |
| LazyDocumentLoader._cache | `src/document_loader.py` | 进程内 | 内存 | 文档内容懒加载缓存 |
| Embedder._tokenizer_cache | `src/embedder.py` | 进程内 | 内存 | Tokenizer 复用 |
| _bge_encoder_cache | `src/chunker.py` | 进程内 | 内存 | BGE Encoder 复用 |
| TestSetGenerator._doc_truncate_cache | `src/test_generator.py` | 实例内 | 内存 | 文档截断结果缓存 |
| Qdrant Vector Index | `src/indexer.py` | 持久化 | 文件系统 | 向量索引存储 |

---

## 2. 各缓存机制详细分析

### 2.1 ArtifactCache（核心缓存系统）

**位置**: [src/meal.py:395-655](file:///b:/project/ash-easy-rag/src/meal.py#L395-L655)

**缓存键设计**:
- `data_id`: 基于 PDF 文件 SHA-256 哈希组合计算
- `parser_hash`: 解析器配置哈希（取前 8 位）
- `chunker_hash`: 分块器配置哈希（取前 8 位）

**目录结构**:
```
data/artifacts/
└── {data_id[:12]}/           # 短 ID 目录
    ├── manifest.json         # 元数据清单
    ├── parsed_{parser_hash}/ # 解析产物
    └── chunks_{chunker_hash}/# 分块产物
```

**缓存验证逻辑**:
```python
# src/parser.py:122-128
cache_valid = (
    manifest is not None
    and "pdf_inventory" in manifest
    and cache.is_full_parsed_valid(parser_hash)
)
```

---

### 2.2 LazyDocumentLoader._cache（文档懒加载缓存）

**位置**: [src/document_loader.py:272-427](file:///b:/project/ash-easy-rag/src/document_loader.py#L272-L427)

**特点**:
- 按需加载文档内容
- 加载后缓存在 `_cache` 字典中
- 提供 `clear_cache()` 方法手动清理

---

### 2.3 Embedder._tokenizer_cache（Tokenizer 缓存）

**位置**: [src/embedder.py:13](file:///b:/project/ash-easy-rag/src/embedder.py#L13)

**特点**:
- 类级别静态变量 `dict[str, Any]`
- 在 `__init__` 时注册，在 `get_tokenizer()` 时复用
- **跨实例共享**

---

### 2.4 _bge_encoder_cache（BGE Encoder 缓存）

**位置**: [src/chunker.py:81](file:///b:/project/ash-easy-rag/src/chunker.py#L81)

**特点**:
- 模块级别全局变量
- 按模型名缓存 `BGETokenizerEncoder` 实例

---

### 2.5 TestSetGenerator._doc_truncate_cache（文档截断缓存）

**位置**: [src/test_generator.py:253](file:///b:/project/ash-easy-rag/src/test_generator.py#L253)

**特点**:
- 实例级别缓存
- 使用文档内容前 1000 字符的哈希作为键
- 缓存截断后的文档内容

---

### 2.6 Qdrant Vector Index（向量索引）

**位置**: [src/indexer.py](file:///b:/project/ash-easy-rag/src/indexer.py)

**特点**:
- 使用 Qdrant 本地模式持久化
- `collection_name` 作为索引标识
- 通过 `persist_dir` 指定存储路径

---

## 3. 缓存命中失败风险点

### 3.1 【高风险】data_id 碰撞风险

**问题描述**:
`data_id` 仅取 SHA-256 哈希的前 12 个字符作为目录名，存在碰撞风险。

**代码位置**: [src/meal.py:452-454](file:///b:/project/ash-easy-rag/src/meal.py#L452-L454)

```python
def get_artifact_group_dir(self, data_id: str) -> Path:
    short_id = data_id[:12]  # 只取前12位
    return self.artifacts_dir / short_id
```

**风险分析**:
- SHA-256 前 12 位（48 bits）的碰撞概率约为 2^-24（约 1600 万分之一）
- 当项目规模扩大，PDF 文件数量增加时，碰撞风险上升
- 碰撞会导致不同数据集的缓存被错误覆盖

**影响**: 缓存污染、数据错误

---

### 3.2 【高风险】config_hash 不完整导致缓存误用

**问题描述**:
`compute_chunker_config_hash` 未包含所有影响分块结果的参数。

**代码位置**: [src/meal.py:155-187](file:///b:/project/ash-easy-rag/src/meal.py#L155-L187)

```python
def compute_chunker_config_hash(chunker_config: dict) -> str:
    relevant = {
        "strategy": chunker_config.get("strategy", "fixed"),
        "chunk_size": chunker_config["chunk_size"],
        "overlap": overlap,
        "encoding": chunker_config.get("encoding", "cl100k_base"),
    }
    # 缺少: cross_page_overlap
```

**风险分析**:
- `cross_page_overlap` 参数未被纳入哈希计算
- 修改 `cross_page_overlap` 后，缓存键不变，但分块结果不同
- 导致使用错误的缓存数据

**影响**: 缓存命中失败（实际应该失效但未失效）

---

### 3.3 【中风险】parser_options 部分参数未纳入哈希

**问题描述**:
`compute_parser_config_hash` 只包含 `algorithm` 和 `options`，但某些解析器内部状态可能影响结果。

**代码位置**: [src/meal.py:138-152](file:///b:/project/ash-easy-rag/src/meal.py#L138-L152)

**风险分析**:
- 解析器版本升级后，相同配置可能产生不同结果
- OCR 语言设置等参数变化未被检测

---

### 3.4 【中风险】LazyDocumentLoader 缓存无失效机制

**问题描述**:
文档加载后缓存在内存中，但源文件修改后缓存不会自动失效。

**代码位置**: [src/document_loader.py:334-372](file:///b:/project/ash-easy-rag/src/document_loader.py#L334-L372)

```python
def get(self, doc_name: str) -> LoadedDocument:
    if doc_name in self._cache:
        return self._cache[doc_name]  # 直接返回缓存，无校验
```

**风险分析**:
- 长时间运行的进程中，文档内容可能已更新
- 缓存返回的是旧内容，导致数据不一致

---

### 3.5 【中风险】embedding model_name 变化未触发索引重建

**问题描述**:
切换 embedding 模型后，向量索引的 collection_name 可能不变，导致向量维度不匹配。

**代码位置**: [src/meal.py:190-200](file:///b:/project/ash-easy-rag/src/meal.py#L190-L200)

```python
def compute_embedding_config_hash(embedding_config: dict) -> str:
    relevant = {"model_name": embedding_config["model_name"]}
    # 只包含 model_name，不包含 device、batch_size 等
```

**风险分析**:
- `index_key` 包含 embedding hash，但 Qdrant collection 的向量维度是固定的
- 如果新模型的 embedding 维度不同，会导致运行时错误

---

### 3.6 【低风险】TestSetGenerator._doc_truncate_cache 哈希键不稳定

**问题描述**:
使用文档内容前 1000 字符的 `hash()` 作为键，但 Python 的 `hash()` 在不同进程中不稳定。

**代码位置**: [src/test_generator.py:1377-1382](file:///b:/project/ash-easy-rag/src/test_generator.py#L1377-L1382)

```python
doc_key = str(hash(document_content[:1000]))
if doc_key in self._doc_truncate_cache:
    truncated_doc = self._doc_truncate_cache[doc_key]
```

**风险分析**:
- Python 的 `hash()` 函数在不同进程间可能返回不同值
- 跨进程场景下缓存无法命中

---

## 4. 缓存污染风险点

### 4.1 【高风险】部分解析失败导致缓存不完整

**问题描述**:
解析过程中部分 PDF 失败，但已解析的文件会被缓存，manifest 中的 `pdf_inventory` 与实际文件不一致。

**代码位置**: [src/parser.py:158-227](file:///b:/project/ash-easy-rag/src/parser.py#L158-L227)

```python
for meal_file in pdf_files:
    try:
        # 解析逻辑...
    except Exception as e:
        logger.error(f"Failed to parse {meal_file.path}: {str(e)}")
        # 失败后继续处理下一个文件

# 最后仍然保存 manifest
cache.save_manifest(data_id, artifact_manifest)
```

**风险分析**:
- manifest 记录了所有 PDF 的 SHA-256，但实际只生成了部分 .md 文件
- 下次运行时，`is_full_parsed_valid()` 会检测到文件缺失，但中间状态可能被误用

---

### 4.2 【高风险】并发写入导致 manifest 损坏

**问题描述**:
多个进程同时操作同一 `data_id` 的缓存时，manifest.json 可能被覆盖或损坏。

**代码位置**: [src/meal.py:544-560](file:///b:/project/ash-easy-rag/src/meal.py#L544-L560)

```python
def save_manifest(self, data_id: str, manifest: dict[str, Any]) -> None:
    # 无文件锁保护
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
```

**风险分析**:
- 无文件锁机制
- 并发场景下 manifest 可能损坏或数据丢失

---

### 4.3 【中风险】LazyDocumentLoader 缓存无大小限制

**问题描述**:
内存缓存无上限，大量文档加载后可能导致内存溢出。

**代码位置**: [src/document_loader.py:302](file:///b:/project/ash-easy-rag/src/document_loader.py#L302)

```python
self._cache: dict[str, LoadedDocument] = {}  # 无大小限制
```

**风险分析**:
- 处理大量文档时，内存占用持续增长
- 无 LRU 淘汰机制

---

### 4.4 【中风险】Embedder._tokenizer_cache 类级别共享

**问题描述**:
tokenizer 缓存是类级别静态变量，跨实例共享，可能导致意外行为。

**代码位置**: [src/embedder.py:13](file:///b:/project/ash-easy-rag/src/embedder.py#L13)

```python
class Embedder:
    _tokenizer_cache: dict[str, Any] = {}  # 类级别共享
```

**风险分析**:
- 不同 Embedder 实例共享同一 tokenizer
- 如果 tokenizer 状态被修改，会影响所有实例
- 单元测试中需要手动清理 `Embedder._tokenizer_cache.clear()`

---

### 4.5 【低风险】Qdrant collection 共享风险

**问题描述**:
多个 meal 可能共享同一个 Qdrant collection（当 `index_key` 相同时），删除一个 meal 可能影响其他 meal。

**代码位置**: [src/meal.py:1027-1066](file:///b:/project/ash-easy-rag/src/meal.py#L1027-L1066)

```python
def delete_meal(self, name: str) -> None:
    shared = self._is_collection_shared(
        meal_config.collection_name, exclude_name=name
    )
    if not shared:
        indexer.delete_collection()  # 只有非共享时才删除
```

**风险分析**:
- 已有共享检测机制，但依赖 `_is_collection_shared()` 的正确实现
- 如果检测逻辑有误，可能误删共享 collection

---

## 5. 缓存一致性风险点

### 5.1 【高风险】源文件修改后缓存未失效

**问题描述**:
PDF 源文件被修改（内容变化但路径不变），缓存的解析产物不会自动失效。

**缓解措施**:
项目已实现 SHA-256 校验机制：

**代码位置**: [src/meal.py:612-654](file:///b:/project/ash-easy-rag/src/meal.py#L612-L654)

```python
def is_full_parsed_valid(self, parser_hash: str) -> bool:
    for rel_path, expected_sha in pdf_inventory.items():
        if compute_file_sha256(pdf_path) != expected_sha:
            return False  # SHA 变化则缓存失效
```

**残留风险**:
- 仅在 `is_full_parsed_valid()` 中校验
- `parsed_exists()` 和 `chunks_exist()` 方法不校验 SHA

---

### 5.2 【中风险】配置热更新后缓存不一致

**问题描述**:
运行时修改配置（如 chunk_size），缓存的分块结果与新配置不匹配。

**缓解措施**:
配置变化会改变 `chunker_hash`，从而使用新的缓存目录。

**残留风险**:
- 旧缓存目录不会被自动清理
- 磁盘空间持续增长

---

## 6. 改进建议

### 6.1 短期改进（低风险）

| 问题 | 建议 | 优先级 |
|-----|------|-------|
| config_hash 不完整 | 将 `cross_page_overlap` 纳入 `compute_chunker_config_hash` | P0 |
| hash() 不稳定 | 使用 `hashlib.sha256()` 替代 `hash()` | P1 |
| 内存缓存无上限 | 为 `LazyDocumentLoader._cache` 添加 LRU 淘汰机制 | P2 |

### 6.2 中期改进（中风险）

| 问题 | 建议 | 优先级 |
|-----|------|-------|
| 并发写入 | 为 `save_manifest()` 添加文件锁（如 `fcntl.flock` 或 `portalocker`） | P1 |
| 缓存清理 | 实现缓存清理工具，删除无主的 artifacts 目录 | P2 |
| 缓存监控 | 添加缓存命中率统计和日志 | P2 |

### 6.3 长期改进（架构级）

| 问题 | 建议 | 优先级 |
|-----|------|-------|
| data_id 碰撞 | 增加短 ID 长度至 16 位，或使用完整哈希 | P2 |
| 缓存版本化 | 在 manifest 中添加缓存格式版本号，便于迁移 | P3 |
| 分布式缓存 | 考虑使用 Redis 等分布式缓存替代文件系统缓存 | P3 |

---

## 7. 测试覆盖建议

当前测试覆盖情况：

| 缓存机制 | 单元测试 | 集成测试 | 缺失场景 |
|---------|---------|---------|---------|
| ArtifactCache | ✅ `test_meal.py::TestArtifactCache` | ✅ | 并发写入测试 |
| LazyDocumentLoader | ✅ `test_document_loader.py` | 部分 | 缓存失效测试 |
| Embedder._tokenizer_cache | ✅ `test_embedder.py::TestGetTokenizer` | - | 跨实例共享测试 |
| _bge_encoder_cache | ❌ | - | 需要添加 |
| TestSetGenerator._doc_truncate_cache | ❌ | - | 需要添加 |
| Qdrant Vector Index | ✅ `test_indexer.py` | ✅ | collection 共享测试 |

**建议添加的测试用例**:
1. `test_config_hash_includes_cross_page_overlap`: 验证配置哈希完整性
2. `test_concurrent_manifest_write`: 验证并发写入安全性
3. `test_tokenizer_cache_cross_instance`: 验证 tokenizer 缓存共享行为
4. `test_cache_invalidation_on_source_change`: 验证源文件修改后缓存失效

---

## 8. 总结

### 风险等级分布

| 风险等级 | 数量 | 主要问题 |
|---------|------|---------|
| 高风险 | 4 | data_id 碰撞、config_hash 不完整、部分解析失败、并发写入 |
| 中风险 | 6 | parser_options 不完整、内存缓存无上限、tokenizer 共享等 |
| 低风险 | 2 | hash() 不稳定、collection 共享 |

### 核心结论

1. **缓存键设计基本合理**：使用 SHA-256 哈希作为缓存键，结合配置哈希实现细粒度缓存控制。

2. **主要隐患集中在边界条件**：
   - 配置参数未完全纳入哈希计算
   - 并发场景缺乏保护机制
   - 内存缓存缺乏淘汰策略

3. **已有的安全机制**：
   - SHA-256 校验防止源文件变化后缓存误用
   - `_is_collection_shared()` 防止误删共享 collection
   - `force_parse` 和 `rebuild` 参数支持强制重建

4. **优先修复项**：
   - 将 `cross_page_overlap` 纳入 `chunker_hash` 计算（可能导致当前缓存失效，需清理）
   - 为 manifest 写入添加文件锁
   - 添加缓存清理工具

---

*文档生成时间: 2026-04-26*
*分析范围: ash-easy-rag v0.1.8*
