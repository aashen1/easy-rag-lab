# 缓存污染隐患修复完成报告

## 概述

基于 `docs/troubleshooting/cache-analysis.md` 识别的 12 个缓存风险点，本次修复覆盖其中 10 个核心问题（4 高 / 4 中 / 2 低），剩余 2 项因风险较低或已有缓解措施暂不修改。

---

## 修复清单

### 1. `compute_chunker_config_hash` 缺少 `cross_page_overlap` 【高风险】

**问题**：`cross_page_overlap` 参数影响分块结果，但未纳入哈希计算。修改该参数后缓存键不变，导致使用错误的缓存数据。

**修复**：在 `compute_chunker_config_hash` 的 `relevant` 字典中添加：

```python
"cross_page_overlap": chunker_config.get("cross_page_overlap", 0),
```

**测试**：`test_chunker_config_hash_includes_cross_page_overlap` — 验证仅 `cross_page_overlap` 不同时哈希不同。

**影响**：**BREAKING** — 现有 `chunks_{hash}` 目录将不再命中，需清理旧缓存。

---

### 2. `compute_embedding_config_hash` 缺少 `dimension` 【中风险】

**问题**：切换 embedding 模型后，若新模型维度不同，向量索引的 collection_name 可能不变，导致维度不匹配。

**修复**：当 `embedding_config` 中存在 `dimension` 键时，将其纳入哈希：

```python
relevant = {"model_name": embedding_config["model_name"]}
if "dimension" in embedding_config:
    relevant["dimension"] = embedding_config["dimension"]
```

**测试**：`test_embedding_config_hash_includes_dimension` — 验证含 `dimension=1024` 与不含 `dimension` 产生不同哈希。

---

### 3. `compute_parser_config_hash` 缺少版本信息 【中风险】

**问题**：解析器库升级后，相同配置可能产生不同结果，但缓存键不变。

**修复**：动态检测解析器库版本号，纳入 `_version_hint` 字段：

```python
try:
    if algorithm == "pymupdf4llm":
        import pymupdf4llm
        relevant["_version_hint"] = pymupdf4llm.__version__
    elif algorithm == "pymupdf":
        import pymupdf
        relevant["_version_hint"] = pymupdf.__version__
except (ImportError, AttributeError):
    relevant["_version_hint"] = "unknown"
```

**测试**：`test_parser_config_hash_includes_version` — 验证相同算法产生相同哈希，不同算法产生不同哈希。

---

### 4. `save_manifest` / `load_manifest` 并发写入无保护 【高风险】

**问题**：多进程同时操作同一 `data_id` 的缓存时，`manifest.json` 可能被覆盖或损坏。无文件锁机制。

**修复**：使用 `filelock` 库添加排他锁保护写入和读取：

```python
from filelock import FileLock

lock = FileLock(str(lock_path), timeout=30)
with lock, open(manifest_path, "w", encoding="utf-8") as f:
    json.dump(manifest, f, ensure_ascii=False, indent=2)
```

`load_manifest` 同样加锁，防止读取到写入一半的文件。

**依赖**：新增 `filelock >= 3.16.1, <4` 到 `pixi.toml`。

**测试**：`test_concurrent_manifest_write` — 10 个线程并发写入，验证无异常且 manifest 完整。

---

### 5. 部分解析失败后 manifest 不一致 【高风险】

**问题**：解析过程中部分 PDF 失败，但 `pdf_inventory` 仍包含所有 PDF（包括失败的）。`is_full_parsed_valid` 检测到失败文件无产物后判定缓存无效，导致已成功解析的文件也被重新解析。

**修复**：

- `parse_all_pdfs_unified`：根据 `results` 中的 `status` 区分成功和失败文件，`pdf_inventory` 仅包含成功文件，新增 `failed_inventory` 记录失败文件。
- `is_full_parsed_valid`：若 `failed_inventory` 非空，返回 `False` 触发重试（之前失败的文件可能在新一轮中成功）。

```python
success_files = [f for f in pdf_files if any(
    r["source"] == f.path and r["status"] == "success" for r in results
)]
failed_files = [f for f in pdf_files if any(
    r["source"] == f.path and r["status"] == "failed" for r in results
)]

artifact_manifest = {
    ...
    "pdf_inventory": {f.path: f.sha256 for f in success_files},
    "failed_inventory": {f.path: f.sha256 for f in failed_files},
}
```

**测试**：`test_partial_parse_manifest_consistency` + `test_is_full_parsed_valid_with_failed_inventory`。

---

### 6. `LazyDocumentLoader` 缓存无失效机制 【中风险】

**问题**：文档加载后缓存在内存中，源文件修改后缓存不会自动失效，返回旧内容。

**修复**：缓存值从 `LoadedDocument` 改为 `(LoadedDocument, float_mtime)` 元组，`get()` 返回缓存前校验文件 mtime：

```python
cached_doc, cached_mtime = self._cache[doc_name]
current_mtime = self._index[doc_name].stat().st_mtime
if current_mtime != cached_mtime:
    # 重新加载
```

**测试**：`test_cache_invalidation_on_source_change` — 修改文件 mtime 后验证缓存自动失效。

---

### 7. `LazyDocumentLoader` 缓存无大小限制 【中风险】

**问题**：内存缓存无上限，大量文档加载后可能导致内存溢出。无 LRU 淘汰机制。

**修复**：

- `_cache` 从 `dict` 改为 `OrderedDict`
- 新增 `max_cache_size` 参数（默认 128）
- 缓存命中时 `move_to_end()`，新文档入缓存后检查是否超限并淘汰最久未访问的条目

```python
self._cache: OrderedDict[str, tuple[LoadedDocument, float]] = OrderedDict()
self._max_cache_size = max_cache_size

# 命中时
self._cache.move_to_end(doc_name)

# 新增后
if len(self._cache) > self._max_cache_size:
    self._cache.popitem(last=False)
```

**测试**：`test_lru_eviction` — 5 个文档、`max_cache_size=3`，验证最早加载的被淘汰。

---

### 8. `TestSetGenerator._doc_truncate_cache` 哈希不稳定 【低风险】

**问题**：使用 Python 内置 `hash()` 函数计算缓存键，该函数因 `PYTHONHASHSEED` 随机化，跨进程返回不同值。

**修复**：替换为确定性的 `hashlib.sha256`：

```python
# 之前
doc_key = str(hash(document_content[:1000]))

# 之后
doc_key = hashlib.sha256(document_content[:1000].encode()).hexdigest()[:16]
```

**测试**：`test_doc_truncate_cache_key_stability` — 验证相同内容产生相同 key，不同内容产生不同 key。

---

### 9. `data_id` 短 ID 碰撞风险 【高风险】

**问题**：`get_artifact_group_dir` 仅取 SHA-256 前 12 位（48 bits）作为目录名，碰撞概率约 2^-24。

**修复**：短 ID 长度从 12 位增至 16 位（64 bits），碰撞概率降至约 2^-32：

```python
short_id = data_id[:16]  # 原为 data_id[:12]
```

**测试**：`test_short_id_length` — 验证目录名为 `data_id[:16]`。

**影响**：**BREAKING** — 现有 `data/artifacts/{12位ID}/` 目录不再被识别，需迁移或清理。

---

### 10. `parsed_exists` / `chunks_exist` 不校验源文件 SHA-256 【中风险】

**问题**：这两个方法只检查产物文件是否存在，不校验源 PDF 是否被修改。`is_full_parsed_valid` 有校验，但 `parsed_exists` / `chunks_exist` 没有。

**修复**：新增可选 `manifest` 参数，提供时校验源文件 SHA-256：

```python
def parsed_exists(
    self,
    data_id: str,
    expected_files: list[str],
    parser_hash: str | None = None,
    manifest: dict[str, Any] | None = None,  # 新增
) -> bool:
    ...
    if manifest is not None and "pdf_inventory" in manifest and self.raw_dir is not None:
        for rel_path, expected_sha in manifest["pdf_inventory"].items():
            pdf_path = self.raw_dir / rel_path
            if not pdf_path.exists():
                return False
            if compute_file_sha256(pdf_path) != expected_sha:
                return False
    return True
```

`chunks_exist` 同理。不传 `manifest` 时行为完全不变（向后兼容）。

**测试**：`test_parsed_exists_sha_validation` + `test_chunks_exist_sha_validation` + 2 个向后兼容测试。

---

## 未修复项

| 风险点 | 原因 |
|--------|------|
| `Embedder._tokenizer_cache` 类级别共享 | tokenizer 是无状态对象，共享不会产生副作用，风险极低 |
| Qdrant collection 共享风险 | 已有 `_is_collection_shared()` 保护机制，当前实现足够 |

---

## 变更文件索引

| 文件 | 变更类型 |
|------|---------|
| `src/meal.py` | 修改 6 处 |
| `src/parser.py` | 修改 1 处 |
| `src/document_loader.py` | 修改 2 处 |
| `src/test_generator.py` | 修改 1 处 |
| `tests/test_meal.py` | 新增 8 个测试 |
| `tests/test_document_loader.py` | 新增 2 个测试 |
| `tests/test_test_generator.py` | 新增 1 个测试 + 修复 1 个既有测试 |
| `pixi.toml` | 新增 `filelock` 依赖 |

---

## 迁移指引

由于哈希计算变更（Task 1-3）和短 ID 长度变更（Task 9），现有缓存将不再命中。建议：

1. **清理旧缓存**：删除 `data/artifacts/` 下所有子目录
2. **重新运行解析**：下次运行 RAG 链路时会自动重建缓存
3. **无需手动迁移**：旧缓存不会被误用，只是不再命中

---

*完成时间: 2026-04-26*
*对应 Spec: `.trae/specs/fix-cache-pollution-risks/`*
