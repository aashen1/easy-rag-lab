# 修复：全量解析结果复用失效（page_chunks 模式）

## 问题根因

用户已经跑过全量 PDF 解析，但创建抽样实验集时仍然重新解析 PDF。经排查，发现 **3 个 Bug**，全部与 `page_chunks=True` 模式相关（当前 config.yaml 中 `page_chunks: true`）。

### Bug #1（致命）：`is_full_parsed_valid` 不识别 `.pages.json` 文件

**位置**：[cache.py:379-382](file:///b:/project/w1-easy-rag/src/meal/cache.py#L379-L382)

```python
if rel_path.endswith(".pages.json"):          # ← 死代码！pdf_inventory 的 key 永远是 .pdf 结尾
    parsed_file = parsed_dir / Path(rel_path).with_suffix(".pages.json")
else:
    parsed_file = parsed_dir / Path(rel_path).with_suffix(".md")  # ← 永远走这里
```

`pdf_inventory` 的 key 是 PDF 相对路径（如 `annual_reports/report.pdf`），永远以 `.pdf` 结尾，所以 `rel_path.endswith(".pages.json")` 永远为 False。当 `page_chunks=True` 时，实际输出是 `.pages.json` 文件，但验证逻辑却去找 `.md` 文件 → 找不到 → 返回 False → 跳过全量复用 → 重新解析。

### Bug #2（致命）：`parsed_exists` 只扫描 `.md` 文件

**位置**：[cache.py:183](file:///b:/project/w1-easy-rag/src/meal/cache.py#L183)

```python
existing = set(p.name for p in parsed_dir.rglob("*.md"))  # ← 只找 .md
```

当 `page_chunks=True` 时，解析产物是 `.pages.json`，但此方法只扫描 `.md` 文件 → 永远找不到 → 返回 False。这是第二层缓存检查，同样失效。

### Bug #3（中等）：`_reuse_full_parsed` 不追踪缺失文件

**位置**：[manager.py:1287-1291](file:///b:/project/w1-easy-rag/src/meal/manager.py#L1287-L1291)

```python
if not src.exists():
    logger.warning(f"Full parsed file not found: {src}, will parse separately")
    continue  # ← 仅打日志，未将缺失文件加入 pdfs_to_parse
```

调用方在 line 408 已将 `pdfs_to_parse = []`，缺失的文件不会被补解析，导致 meal 不完整。

---

## 修复方案

### Step 1：修复 `is_full_parsed_valid` — 增加 `use_page_chunks` 参数

**文件**：`src/meal/cache.py`

- 给 `is_full_parsed_valid(parser_hash)` 增加 `use_page_chunks: bool = False` 参数
- 根据参数决定查找 `.md` 还是 `.pages.json`：
  ```python
  suffix = ".pages.json" if use_page_chunks else ".md"
  parsed_file = parsed_dir / Path(rel_path).with_suffix(suffix)
  ```
- 删除无用的 `rel_path.endswith(".pages.json")` 分支

### Step 2：修复 `parsed_exists` — 增加 `use_page_chunks` 参数

**文件**：`src/meal/cache.py`

- 给 `parsed_exists(data_id, expected_files, parser_hash, manifest)` 增加 `use_page_chunks: bool = False` 参数
- 修改扫描逻辑：
  ```python
  ext = "*.pages.json" if use_page_chunks else "*.md"
  existing = set(p.name for p in parsed_dir.rglob(ext))
  ```

### Step 3：修复 `create_meal` 中的调用 — 传入 `use_page_chunks`

**文件**：`src/meal/manager.py`

- 在 `create_meal` 中调用 `is_full_parsed_valid` 和 `parsed_exists` 时，传入 `use_page_chunks` 参数
- 具体位置：
  - line 394: `self.cache.is_full_parsed_valid(parser_hash, use_page_chunks=use_page_chunks)`
  - line 409-410: `self.cache.parsed_exists(data_id, expected_md_names, parser_hash, use_page_chunks=use_page_chunks)`

### Step 4：修复 `_reuse_full_parsed` — 返回缺失文件列表

**文件**：`src/meal/manager.py`

- 修改 `_reuse_full_parsed` 返回值，从 `None` 改为返回缺失的 `MealFile` 列表
- 在 `create_meal` 中使用返回值，将缺失文件加入 `pdfs_to_parse`：
  ```python
  missing_files = self._reuse_full_parsed(...)
  if missing_files:
      pdfs_to_parse = [self.raw_dir / f.path for f in missing_files]
      logger.warning(f"Will parse {len(pdfs_to_parse)} missing files separately")
  ```

### Step 5：同步修复 `parse_all_pdfs_unified` 中的 `is_full_parsed_valid` 调用

**文件**：`src/parser.py`

- line 125: `cache.is_full_parsed_valid(parser_hash)` 也需要传入 `use_page_chunks`

### Step 6：更新测试

**文件**：`tests/test_meal.py`

- 为 `is_full_parsed_valid` 添加 `page_chunks=True` 场景的测试
- 为 `parsed_exists` 添加 `page_chunks=True` 场景的测试
- 为 `_reuse_full_parsed` 添加缺失文件追踪的测试
- 修改现有测试以适配新参数签名

---

## 影响范围

| 文件 | 改动类型 | 风险 |
|------|---------|------|
| `src/meal/cache.py` | 方法签名扩展（新增可选参数，默认值保持向后兼容） | 低 |
| `src/meal/manager.py` | 调用点传参 + `_reuse_full_parsed` 返回值变更 | 中 |
| `src/parser.py` | 调用点传参 | 低 |
| `tests/test_meal.py` | 新增测试 + 适配签名变更 | 低 |

所有新增参数都有默认值 `False`，保持向后兼容。`_reuse_full_parsed` 返回值从 `None` 变为 `list[MealFile]`，需确认所有调用点。
