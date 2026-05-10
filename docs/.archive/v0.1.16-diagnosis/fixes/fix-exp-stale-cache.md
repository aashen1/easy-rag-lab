# 修复实验系统缓存配置不匹配问题

## 问题诊断

用户修改了 `config.yaml` 中的 PDF 解析配置（`table_enhancer: null` → `pdfplumber`），但运行 `pixi run exp smoke_chunking_5q` 仍然命中旧缓存。

### 根因分析

实验系统有 **三个独立的缓存层**，每一层都有配置不匹配的漏洞：

| 缓存层           | 位置                                                   | 问题                                                       |
| ------------- | ---------------------------------------------------- | -------------------------------------------------------- |
| **Meal 准备层**  | `prepare_meal()` preparation.py:86                   | 只检查 `meal_exists(name)`，不检查 `config_hashes` 是否匹配当前配置     |
| **Chunk 准备层** | `prepare_variant_chunks()` preparation.py:449-452    | `parser_hash` 从旧 `meal_config` 取，不从当前 `merged_config` 计算 |
| **Index 准备层** | `prepare_index_for_variant()` preparation.py:498-502 | 同上，`parser_hash` 和 `embedding_hash` 都从旧 `meal_config` 取  |

**具体流程**：

1. `smoke_chunking_5q.yaml` 指定 `data.meal: "all_meal"`
2. `prepare_meal()` 发现 `all_meal` 存在 → 直接加载（不检查配置是否过时）
3. 旧 `all_meal` 的 `config_hashes.parser = "f2f96875"`（旧链路）
4. 当前配置的 `parser_hash = "42186176"`（新链路，含 pdfplumber）
5. `prepare_variant_chunks()` 和 `prepare_index_for_variant()` 用旧 `parser_hash` 查找 `parsed_f2f96875/` → 命中旧缓存
6. 向量索引的 `collection_name` 也基于旧 `parser_hash` → 命中旧索引

**结果**：整条链路都复用了旧配置的产物，pdfplumber 表格增强从未执行。

### 上一轮修复的局限

上一轮修复了 `find_full_dataset_meal()` 加入 `require_config_match`，但这只影响 `get_or_create_full_meal()` 路径。实验系统走的是 `prepare_meal()` → `meal_exists()` → `load_meal()` 路径，**完全不经过** **`find_full_dataset_meal()`**。

## 设计原则（用户确认）

> 优先级最高的始终是保证全局 `config.yaml` 的配置生效。当用户修改了全局配置（如 PDF 解析链路），系统应该查找是否有与当前配置完全一致的解析结果。如果没有（比如现有缓存是用旧链路解析的），就应该用新链路重新解析。用户既然修改了全局配置，说明他认为这才是他需要的解析结果。如果用户想用旧链路，他应该在全局或实验配置里显式覆盖。

## 修复方案

### 核心思路

**在** **`prepare_meal()`** **中加入配置匹配检查**：当 meal 已存在时，比较其 `config_hashes` 与当前系统配置的 `config_hashes`。如果不匹配，在 meals 目录内备份旧 meal（副本命名为 `{meal_name}_backup_{timestamp}`），然后在原位置用新配置覆盖重建。

### 修改清单

#### 1. `eval/runner/preparation.py` — `prepare_meal()` 加入配置匹配检查

**位置**：preparation.py:86-110

**当前逻辑**：

```python
if meal_manager.meal_exists(meal_name):
    meal_config = meal_manager.load_meal(meal_name)
    # ... 直接返回，不检查配置
```

**修改为**：

```python
if meal_manager.meal_exists(meal_name):
    meal_config = meal_manager.load_meal(meal_name)

    # 检查 meal 的 config_hashes 是否与当前系统配置匹配
    _, current_hashes = meal_manager._build_config_snapshot_and_hashes()
    if meal_config.config_hashes != current_hashes:
        logger.warning(
            f"Meal '{meal_name}' has stale config_hashes. "
            f"Stored: {meal_config.config_hashes}, Current: {current_hashes}. "
            f"Backing up and recreating with current configuration."
        )
        # 在 meals 目录内备份旧 meal
        meal_dir = meal_manager.get_meal_dir(meal_name)
        meals_dir = meal_dir.parent
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"{meal_name}_backup_{timestamp}"
        backup_path = meals_dir / backup_name
        shutil.copytree(str(meal_dir), str(backup_path))
        logger.info(f"Backed up stale meal to: {backup_path}")
        # 继续走创建逻辑（create_meal 会覆盖原位置）
    else:
        # 配置匹配，正常加载
        status, issues = meal_manager.check_meal_status(meal_name)
        # ... 原有返回逻辑
        return { ... }
```

**注意**：`create_meal()` 要求 meal 不存在才能创建（会抛 `MealError`），所以备份后需要先删除原 meal 目录，再调用 `create_meal()`。或者直接在原 meal 目录上覆盖 manifest 和重建索引。

#### 2. `eval/runner/preparation.py` — `prepare_variant_chunks()` 使用当前配置的 parser\_hash

**位置**：preparation.py:449-452

**当前逻辑**：

```python
parsed_dir = cache.get_parsed_dir(
    meal_config.data_id,
    parser_hash=meal_config.config_hashes.get("parser"),
)
```

**修改为**：

```python
from src.meal.hashes import compute_parser_config_hash

parser_section = _build_parser_section(merged_config)
current_parser_hash = compute_parser_config_hash(parser_section)
parsed_dir = cache.get_parsed_dir(
    meal_config.data_id,
    parser_hash=current_parser_hash,
)
```

#### 3. `eval/runner/preparation.py` — `prepare_index_for_variant()` 使用当前配置的 hashes

**位置**：preparation.py:498-502

**当前逻辑**：

```python
config_hashes = {
    "parser": meal_config.config_hashes.get("parser", ""),
    "chunker": chunker_hash,
    "embedding": meal_config.config_hashes.get("embedding", ""),
}
```

**修改为**：

```python
from src.meal.hashes import compute_parser_config_hash, compute_embedding_config_hash

parser_section = _build_parser_section(merged_config)
current_parser_hash = compute_parser_config_hash(parser_section)
current_embedding_hash = compute_embedding_config_hash(
    merged_config.get("embedding", {})
)

config_hashes = {
    "parser": current_parser_hash,
    "chunker": chunker_hash,
    "embedding": current_embedding_hash,
}
```

#### 4. 提取公共辅助函数 `_build_parser_section()`

`_build_parser_section(merged_config)` 将 `merged_config["parser"]` 转换为 `compute_parser_config_hash()` 需要的格式，复用 `MealManager._build_config_snapshot_and_hashes()` 中的逻辑。

**位置**：preparation.py 新增辅助函数

```python
def _build_parser_section(parser_config: dict) -> dict:
    if "primary" in parser_config:
        return {
            "primary": parser_config.get("primary", "pymupdf4llm"),
            "enhancer": parser_config.get("table_enhancer"),
            "primary_config": parser_config.get(
                parser_config.get("primary", "pymupdf4llm"), {}
            ),
            "enhancer_config": parser_config.get(
                parser_config.get("table_enhancer", ""), {}
            ),
        }
    algorithm = parser_config.get("algorithm", "pymupdf4llm")
    return {
        "algorithm": algorithm,
        "options": parser_config.get(algorithm, {}),
    }
```

#### 5. 测试更新

* 新增测试：`test_prepare_meal_stale_config_recreates` — 验证配置不匹配时自动重建 meal

* 新增测试：`test_prepare_variant_chunks_uses_current_parser_hash` — 验证使用当前配置的 parser\_hash

* 新增测试：`test_prepare_index_uses_current_config_hashes` — 验证使用当前配置的所有 hashes

### 不修改的部分

* `MealManager.find_full_dataset_meal()` — 上一轮已修复，保持不变

* `MealManager._build_config_snapshot_and_hashes()` — 已有正确逻辑，保持不变

* `compute_parser_config_hash()` — hash 计算逻辑正确，保持不变

* 实验配置 YAML — 不需要修改，用户无需显式声明 parser 配置

### 风险评估

* **低风险**：修改集中在 `prepare_meal()` 的缓存判断逻辑，不影响核心解析/分块/索引逻辑

* **向后兼容**：配置匹配时行为不变；配置不匹配时自动重建，用户无需手动操作

* **数据安全**：旧 meal 在 meals 目录内备份为 `{name}_backup_{timestamp}`，用户可随时恢复
