# 代码质量与规范合规性审查

审查日期：2026-04-18
审查范围：src/, eval/, main.py, interactive.py, tests/

> **状态标注版** — 标注日期：2026-04-18。各节标题前的状态标签含义：✅ 已修复 = 代码中已修复；📋 已安排 = 计划后续处理；❌ 已弃用 = 已拒绝，不会实施。

---

## 审查结论

**整体评价：不合格。** 项目自身制定了严格的开发规范，但实际代码存在大量违规。最严重的问题是 4 个入口文件中残留的调试钩子代码。

---

## 1. ✅ 已修复 — 调试钩子代码残留（严重）

> 已经revert了

### 问题

以下 4 个文件的头部（第 1-38 行）包含完全相同的调试代码：

- `main.py:1-38`
- `interactive.py:1-38`
- `eval/run_eval.py:1-38`
- `eval/run_experiment.py:1-38`

### 代码内容

```python
_DEBUG_LOG_FILE = "output_dir_debug.log"

def _log_hook(message: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    log_line = f"[{timestamp}] {message}"
    print(log_line)
    with open(_DEBUG_LOG_FILE, "a", encoding="utf-8") as f:
        f.write(log_line + "\n")

_original_mkdir = os.mkdir
_original_makedirs = os.makedirs

def _debug_mkdir(path, *args, **kwargs):
    if "output_dir" in str(path).lower():
        _log_hook("=" * 50)
        _log_hook(f"[HOOK] 检测到创建目录: {path}")
        _log_hook("调用堆栈:")
        for line in traceback.format_stack()[:-1]:
            _log_hook(line.strip())
        _log_hook("=" * 50)
    return _original_mkdir(path, *args, **kwargs)

def _debug_makedirs(path, *args, **kwargs):
    if "output_dir" in str(path).lower():
        _log_hook("=" * 50)
        _log_hook(f"[HOOK] 检测到递归创建目录: {path}")
        _log_hook("调用堆栈:")
        for line in traceback.format_stack()[:-1]:
            _log_hook(line.strip())
        _log_hook("=" * 50)
    return _original_makedirs(path, *args, **kwargs)

os.mkdir = _debug_mkdir
os.makedirs = _debug_makedirs
```

### 违规点

| 违规项 | 说明 | 严重程度 |
|--------|------|----------|
| Monkey-patching `os.mkdir`/`os.makedirs` | 替换系统函数，影响所有依赖库的行为 | 严重 |
| 使用 `print()` | 违反"使用 loguru，禁止使用 print"规范 | 中等 |
| 硬编码日志文件名 | `output_dir_debug.log` 写在代码中 | 中等 |
| 四个文件完全重复 | 违反 DRY 原则 | 低 |
| 调试代码未清理 | TODO.md 中标注"修好了"但代码未移除 | 严重 |

### 修复建议

删除 4 个文件中第 1-38 行的全部调试钩子代码。同时删除根目录下的 `output_dir_debug.log` 文件。

---

## 2. 📋 已安排 — print() 调用违规（严重）

> revert掉以后不知道还剩没剩，需要核实

### 统计

约 93 处 `print()` 调用分布在以下文件中：

| 文件 | 数量 | 性质 |
|------|------|------|
| `main.py` | ~50 处 | CLI 输出 + 调试钩子 |
| `interactive.py` | ~12 处 | CLI 输出 + 调试钩子 |
| `eval/run_experiment.py` | ~16 处 | CLI 输出 + 调试钩子 |
| `eval/run_eval.py` | ~10 处 | CLI 输出 + 调试钩子 |
| `src/pipeline.py` | 4 处 | `__main__` 块中的脚本输出 |
| `src/utils.py` | 1 处 | loguru console sink |

### 分类分析

**A. 调试钩子中的 print（应删除）**

4 个文件中 `_log_hook` 函数内的 `print(log_line)`，随调试代码一起删除即可。

**B. CLI 面向用户的输出（可保留，但需标注）**

`main.py` 中的 `_print_query_result()`、`_interactive_qa()`、`_handle_meal_info()` 等函数使用 print 输出查询结果、交互提示等。这些是面向终端用户的输出，使用 print 有一定合理性（与日志区分）。

**C. loguru sink 中的 print（合理但可优化）**

`src/utils.py:37`：

```python
logger.add(sink=lambda msg: print(msg, end=""), ...)
```

这是 loguru 的 console sink 配置，print 在此处是 loguru 内部机制的一部分。可改用 `sys.stdout.write` 或 loguru 自带的 `sys.stderr` sink。

### 修复建议

1. 删除调试钩子中的 print（随调试代码一起）
2. CLI 输出的 print 可保留，但建议在文件头部注释说明：`# CLI 面向用户的输出使用 print，与日志输出区分`
3. `src/utils.py` 中的 print 改为 `sys.stdout.write`

---

## 3. 📋 已安排 — 公共函数缺少 docstring（中等）

### 统计

`src/` 目录下约 50+ 个公共函数/方法缺少 docstring：

#### parser.py

| 行号 | 函数 | 有类型标注 | 有 docstring |
|------|------|-----------|-------------|
| 10 | `parse_pdf` | 有 | 无 |
| 34 | `parse_all_pdfs` | 有 | 无 |

#### chunker.py

| 行号 | 函数 | 有类型标注 | 有 docstring |
|------|------|-----------|-------------|
| 11 | `chunk_text` | 有 | 无 |
| 78 | `process_parsed_files` | 有 | 无 |

#### utils.py

| 行号 | 函数 | 有类型标注 | 有 docstring |
|------|------|-----------|-------------|
| 12 | `load_config` | 有 | 无 |
| 21 | `setup_logger` | 有 | 无 |
| 55 | `get_llm_config` | 有 | 无 |
| 91 | `get_env_var` | 有 | 无 |
| 105 | `ensure_dir` | 有 | 无 |

#### meal.py

| 行号 | 函数/方法 | 有 docstring |
|------|-----------|-------------|
| 77 | `compute_file_sha256` | 无 |
| 88 | `compute_data_id` | 无 |
| 94 | `compute_parser_config_hash` | 无 |
| 99 | `compute_chunker_config_hash` | 无 |
| 110 | `compute_embedding_config_hash` | 无 |
| 115 | `compute_index_key` | 无 |
| 126 | `generate_collection_name` | 无 |
| 130 | `validate_meal_name` | 无 |
| 137 | `generate_timestamp_name` | 无 |
| MealConfig | `to_dict` / `from_dict` | 无 |
| ArtifactCache | 所有方法 | 无 |
| MealManager | `create_meal` / `load_meal` / `find_equivalent_meals` / `list_meals` / `delete_meal` / `rename_meal` / `copy_meal` / `check_meal_status` / `repair_meal` / `meal_exists` / `get_meal_dir` | 无 |

#### indexer.py

| 类 | 方法 | 有 docstring |
|-----|------|-------------|
| VectorIndexer | `__init__` / `create_collection` / `index_chunks` / `build_index` / `get_collection_info` / `delete_collection` / `close` | 无 |

#### embedder.py

| 类 | 方法 | 有 docstring |
|-----|------|-------------|
| Embedder | `__init__` / `_encode_batch` / `embed_texts` / `embed_query` / `get_embedding_dimension` | 无 |

#### retriever.py

| 类 | 方法 | 有 docstring |
|-----|------|-------------|
| Retriever | `__init__` / `retrieve` | 无 |

#### pipeline.py

| 类 | 方法 | 有 docstring |
|-----|------|-------------|
| RAGPipeline | `__init__` / `build_index` / `use_meal` / `query` | 无 |

#### test_generator.py

| 类 | 方法 | 有 docstring |
|-----|------|-------------|
| TestSetGenerator | `__init__` / `generate_test_set` / 所有私有方法 | 无 |

### 修复建议

按优先级补全 docstring：
1. 先补全 `pipeline.py`、`generator.py`、`retriever.py`（核心链路）
2. 再补全 `meal.py`、`experiment.py`（数据管理）
3. 最后补全工具函数

---

## 4. 📋 已安排 — 公共函数缺少类型标注（中等）

| 文件 | 行号 | 函数 | 问题 |
|------|------|------|------|
| main.py | 219 | `_build_sampling_config` | 返回类型标注为 `object`，应为 `Optional[SamplingConfig]` |
| main.py | 239 | `_handle_meal_info` | 无返回类型标注 |
| main.py | 293 | `_handle_list_meals` | 无返回类型标注 |
| main.py | 344 | `_handle_delete_meal` | 无返回类型标注 |
| main.py | 352 | `_handle_rename_meal` | 无返回类型标注 |
| main.py | 362 | `_handle_copy_meal` | 无返回类型标注 |
| main.py | 372 | `_handle_create_meal` | 无返回类型标注 |
| main.py | 400 | `_handle_repair_meal` | 无返回类型标注 |
| main.py | 482 | `_handle_generate_test_set` | 参数 `config` 类型为 `dict`，应为 `Dict[str, Any]` |
| main.py | 507 | `_print_query_result` | 参数 `result` 类型为 `dict`，应为 `Dict[str, Any]` |
| main.py | 534 | `_interactive_qa` | 无返回类型标注 |
| pipeline.py | 156 | `use_meal` | 无返回类型标注 |
| test_generator.py | 167 | `_load_meal_chunks` | 参数 `meal_config` 无类型标注 |
| test_generator.py | 286 | `_generate_question_with_llm` | 参数 `generator` 无类型标注 |
| embedder.py | 48 | `_encode_batch` | 无返回类型标注 |
| retriever.py | 17 | `Retriever.__init__` | 无返回类型标注 |

---

## 5. 📋 已安排 — IO 操作缺少 try/except（严重）

项目规范要求"所有 IO 操作必须有 try/except，捕获异常后记录日志并优雅降级"，但以下位置未做异常处理：

### src/meal.py

| 行号 | 函数 | 操作 | 缺少 try/except |
|------|------|------|-----------------|
| 79 | `compute_file_sha256` | 文件读取 | 是 |
| 270 | `ArtifactCache.save_manifest` | 文件写入 | 是 |
| 277 | `ArtifactCache.load_manifest` | 文件读取 | 是 |
| 496 | `MealManager.create_meal` | manifest 写入 | 是 |
| 600 | `MealManager.rename_meal` | manifest 写入 | 是 |
| 636 | `MealManager.copy_meal` | manifest 写入 | 是 |
| 836 | `MealManager.repair_meal` | manifest 写入 | 是 |

注：`MealManager.load_meal`（第 521 行）的文件读取已在 try/except 中，合规。

---

## 6. 📋 已安排 — 代码风格问题（低）

### 重复导入

| 文件 | 行号 | 问题 |
|------|------|------|
| `eval/run_eval.py` | 3, 40 | `from datetime import datetime` 重复导入 |
| `eval/run_experiment.py` | 3, 46 | `from datetime import datetime` 重复导入 |

### 函数内部导入

| 文件 | 行号 | 导入内容 |
|------|------|----------|
| `eval/run_experiment.py` | 507 | `import yaml` |
| `eval/run_experiment.py` | 578 | `import json` |
| `eval/run_experiment.py` | 660 | `import json` |
| `eval/run_experiment.py` | 734 | `import json` |
| `eval/run_experiment.py` | 775 | `import json` |
| `eval/run_experiment.py` | 861 | `from src.token_tracker import DetailedTokenUsage, TokenRecord` |

### 尾随空格

`src/chunker.py` 第 68 行末尾有多余空格。

---

## 7. ✅ 已修复 — 合规项

| 检查项 | 状态 |
|--------|------|
| 无 TODO/FIXME/HACK/XXX 标记 | ✅ |
| 无大段注释掉的代码 | ✅ |
| `eval/metrics.py` 所有公共函数有 docstring 和类型标注 | ✅ |

