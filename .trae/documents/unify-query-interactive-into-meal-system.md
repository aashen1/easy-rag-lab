# 计划：统一单轮问答入口到 Meal/Artifact 系统

## 目标

让 `main.py --query` 和 `main.py --interactive` 在**不指定 `--meal`** 时，自动接入 Meal/Artifact 系统，消除独立于 RAG 体系之外的解析链路。

## 现状问题

| 路径 | 现状 | 问题 |
|------|------|------|
| `--query`（无 `--meal`） | `RAGPipeline(meal_name=None)` → `indexer=None` | 直接报错，无法工作 |
| `--interactive`（无 `--meal`） | 同上 | 同上 |
| `--build-index` | `pipeline.build_index()` 用了 ArtifactCache，但**不创建 Meal** | 产物存入 artifacts 但无人追踪，后续 `--query` 仍连不上 |

## 设计思路

引入 **"默认全量 Meal"** 概念：

- 当用户不指定 `--meal` 时，自动查找或创建一个包含 `data/raw/` 下所有 PDF 的 Meal
- 默认 Meal 名称为 `"all"`（可通过 `config.yaml` 的 `meals.default_name` 配置）
- `--build-index` 也走 Meal 系统，创建/更新默认全量 Meal
- 解析/分块/索引全部通过 ArtifactCache 管理，零独立链路

## 实现步骤

### Step 1：在 `MealManager` 中添加 `get_or_create_full_meal()` 方法

**文件**：`src/meal/manager.py`

新增方法：

```python
DEFAULT_MEAL_NAME = "all"

def get_or_create_full_meal(
    self,
    name: str | None = None,
    force_parse: bool = False,
    force_chunk: bool = False,
    profiler: Any | None = None,
) -> MealConfig:
```

逻辑：
1. 确定目标 meal 名称：`name` 参数 > `config["meals"]["default_name"]` > `"all"`
2. 先调用 `find_full_dataset_meal()` 查找已有全量 Meal
3. 如果找到且名称匹配 → 直接返回
4. 如果找到但名称不同 → 也直接返回（data_id 匹配即可，名称不重要）
5. 如果没找到 → 调用 `create_meal(name=name, sampling_config=SamplingConfig(mode="ratio", value=1.0), force_parse=force_parse, force_chunk=force_chunk, profiler=profiler)` 自动创建
6. 返回 MealConfig

### Step 2：在 `config.yaml` 中添加默认 Meal 名称配置

**文件**：`config.yaml`

在 `meals` 节下添加：

```yaml
meals:
  dir: "data/meals"
  collection_prefix: "m_"
  default_name: "all"        # 新增：--query/--interactive 无 --meal 时自动使用的 Meal 名称
```

### Step 3：重构 `main.py` 的 `--query` / `--interactive` / `--build-index` 路径

**文件**：`main.py`

核心改动：提取一个 `_resolve_meal_name()` 辅助函数，统一处理 Meal 解析逻辑。

```python
def _resolve_meal_name(meal_manager: MealManager, args: argparse.Namespace) -> str | None:
    """Resolve the meal name to use for query/interactive/build-index.

    Priority:
      1. Explicit --meal argument
      2. Auto-resolve to the default full-dataset meal (get_or_create_full_meal)

    Returns:
        Meal name string, or None if no meal can be resolved.
    """
    if args.meal:
        return args.meal

    try:
        meal = meal_manager.get_or_create_full_meal()
        logger.info(f"No --meal specified, auto-resolved to meal '{meal.name}'")
        return meal.name
    except Exception as e:
        logger.error(f"Failed to auto-resolve default meal: {e}")
        return None
```

然后重构主逻辑（第 243-278 行区域）：

**Before**（当前代码）：
```python
if args.build_index or args.rebuild:
    sampling_config = _build_sampling_config(args)
    pipeline = RAGPipeline(config=args.config, llm_preset=args.llm_preset)
    pipeline.build_index(...)

if args.meal:
    pipeline = RAGPipeline(..., meal_name=args.meal)
    ...
elif args.interactive:
    pipeline = RAGPipeline(...)   # indexer=None，会报错
    _interactive_qa(pipeline)
elif args.query:
    pipeline = RAGPipeline(...)   # indexer=None，会报错
    result = pipeline.query(args.query)
```

**After**（重构后）：
```python
# 统一解析 meal_name：显式指定 或 自动获取全量 meal
resolved_meal = _resolve_meal_name(meal_manager, args) if (args.query or args.interactive or args.build_index or args.rebuild) else None

if args.build_index or args.rebuild:
    if resolved_meal:
        # 走 Meal 系统重建
        _handle_rebuild_meal(meal_manager, resolved_meal, args)
    else:
        # fallback：无 PDF 可用，报错退出
        logger.error("No PDFs found and no meal available. Cannot build index.")
        sys.exit(1)

if resolved_meal:
    pipeline = RAGPipeline(config=args.config, llm_preset=args.llm_preset, meal_name=resolved_meal)
    status, issues = meal_manager.check_meal_status(resolved_meal)
    if status != MealStatus.AVAILABLE:
        logger.warning(...)

    if args.query:
        result = pipeline.query(args.query)
        _print_query_result(result)
    elif args.interactive:
        _interactive_qa(pipeline, resolved_meal)
elif args.query or args.interactive:
    # 不应该到达这里（_resolve_meal_name 失败时），但做兜底
    logger.error("No meal available. Please create one first with --create-meal.")
    sys.exit(1)
```

### Step 4：添加 `_handle_rebuild_meal()` 辅助函数

**文件**：`main.py`

处理 `--build-index` / `--rebuild` 通过 Meal 系统执行：

```python
def _handle_rebuild_meal(meal_manager: MealManager, meal_name: str, args: argparse.Namespace) -> None:
    """Rebuild a meal's index through the meal system.

    If --rebuild is specified, deletes and recreates the meal.
    Otherwise, ensures the meal exists and is up-to-date.
    """
    if args.rebuild and meal_manager.meal_exists(meal_name):
        logger.info(f"Rebuilding meal '{meal_name}' from scratch...")
        meal_manager.delete_meal(meal_name)

    if not meal_manager.meal_exists(meal_name):
        meal_manager.get_or_create_full_meal(
            name=meal_name,
            force_parse=args.force_parse,
        )
    else:
        logger.info(f"Meal '{meal_name}' already exists, index is ready")
```

### Step 5：更新 `_interactive_qa()` 的提示信息

**文件**：`main.py`

当自动解析到默认 meal 时，提示信息应明确告知用户：

```python
if meal_name:
    print(f"\n🤖 RAG 问答系统已启动（meal: {meal_name}）")
else:
    print("\n🤖 RAG 问答系统已启动")
```

这部分已有，无需修改。但需要确保 `meal_name` 参数在自动解析场景下也能正确传入。

### Step 6：更新 `--build-index` 的帮助提示

**文件**：`main.py`

更新 `_interactive_qa` 中的提示文字：

```python
# Before
print("⚠️  数据库为空，请先构建索引：pixi run python main.py --build-index")
# After
print("⚠️  数据库为空，请先构建索引：pixi run python main.py --build-index --meal <name>")
```

### Step 7：编写测试

**文件**：`tests/test_meal.py`

新增测试用例：

1. `test_get_or_create_full_meal_creates_new`：无全量 meal 时自动创建
2. `test_get_or_create_full_meal_returns_existing`：已有全量 meal 时直接返回
3. `test_get_or_create_full_meal_uses_config_name`：使用 config 中的 default_name
4. `test_get_or_create_full_meal_no_pdfs`：raw_dir 无 PDF 时抛出异常

### Step 8：运行 lint 和测试

```bash
pixi run lint
pixi run test
```

## 变更文件清单

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `src/meal/manager.py` | 修改 | 添加 `DEFAULT_MEAL_NAME` 常量和 `get_or_create_full_meal()` 方法 |
| `config.yaml` | 修改 | meals 节添加 `default_name: "all"` |
| `main.py` | 修改 | 重构 `--query`/`--interactive`/`--build-index` 路径，添加 `_resolve_meal_name()` 和 `_handle_rebuild_meal()` |
| `tests/test_meal.py` | 修改 | 添加 `get_or_create_full_meal` 测试用例 |

## 风险与注意事项

1. **向后兼容**：`--build-index` 的行为从"独立建索引"变为"通过 Meal 系统建索引"。已有用户若习惯用 `--build-index` + `--query`（不带 `--meal`），新版本会自动创建名为 "all" 的 meal 并使用它，体验更顺畅
2. **首次运行耗时**：首次 `--query` 不带 `--meal` 时，若没有全量 meal，会自动触发全量解析+分块+索引，耗时较长。应通过日志明确提示用户
3. **`--build-index` 的 `--sample-*` 参数**：带采样参数的 `--build-index` 不应走全量 meal 路径，应保持原有行为（采样建索引后不创建 meal，或提示用户用 `--create-meal`）
