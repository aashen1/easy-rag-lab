# 统一解析链路计划

## 背景

当前存在两套独立的解析系统：
1. **旧链路**：`python -m src.parser` → 输出到 `data/parsed/`
2. **新链路**：Meal 创建流程 → 输出到 `data/artifacts/<data_id>/parsed_<parser_hash>/`

问题：
- 两套系统不互通，预解析结果无法复用
- 用户希望支持全量运行（不抽样），同时废弃旧链路

## 设计方案

### 核心思路：引入"全局 Meal"概念

将"全量数据集"视为一种特殊的 Meal：
- 名称：`_global`（或用户自定义）
- 特点：包含所有 PDF，无需抽样配置
- data_id：基于所有 PDF 的 SHA256 组合计算

### 目录结构变化

```
data/
├── artifacts/                    # 统一的 Artifact 存储
│   ├── <data_id_1>/             # 全局 Meal 的 data_id
│   │   ├── parsed_<hash>/       # 解析结果
│   │   ├── chunks_<hash>/       # 切块结果
│   │   └── manifest.json        # 元数据
│   └── <data_id_2>/             # 其他抽样 Meal
│       └── ...
├── meals/                        # Meal 配置目录
│   ├── _global/                  # 全局 Meal
│   │   └── manifest.json
│   └── meal_xxx/                 # 抽样 Meal
│       └── manifest.json
└── parsed/                       # [废弃] 不再使用
```

## 实施步骤

### Step 1: 新增 `create_global_meal` 方法

**文件**: `src/meal.py`

在 `MealManager` 类中添加：

```python
def create_global_meal(
    self,
    name: str = "_global",
    force_parse: bool = False,
) -> MealConfig:
    """Create a meal containing all PDFs in the raw directory.

    This is equivalent to create_meal with sample_ratio=1.0,
    but with a clearer semantic for "full corpus" usage.
    """
    from src.sampler import SamplingConfig
    return self.create_meal(
        name=name,
        sampling_config=SamplingConfig(mode="ratio", value=1.0),
        force_parse=force_parse,
    )
```

### Step 2: 修改 `main.py` 入口

**文件**: `main.py`

新增命令行参数：

```python
meal_group.add_argument(
    "--create-global-meal",
    nargs="?",
    const="_global",
    default=None,
    help="Create a global meal with all PDFs (default name: _global)"
)
```

处理逻辑：

```python
if args.create_global_meal is not None:
    meal = meal_manager.create_global_meal(
        name=args.create_global_meal if args.create_global_meal != "_global" else None,
        force_parse=args.force_parse,
    )
    # ...
```

### Step 3: 废弃 `python -m src.parser`

**文件**: `src/parser.py`

修改 `if __name__ == "__main__"` 部分：

```python
if __name__ == "__main__":
    import warnings
    warnings.warn(
        "Direct invocation of src.parser is deprecated. "
        "Use 'python main.py --create-global-meal' instead.",
        DeprecationWarning,
        stacklevel=2
    )
    # 保留旧逻辑以兼容，但输出警告
    # ...
```

### Step 4: 更新文档

**文件**: `docs/guides/operations/pdf-parsing.md`

更新操作指南，说明新的预解析方式：

```markdown
## 预解析所有 PDF

推荐方式（创建全局 Meal）：
```bash
python main.py --create-global-meal
```

这会：
1. 解析所有 PDF 到 artifacts 系统
2. 创建名为 `_global` 的 Meal
3. 后续创建抽样 Meal 时自动复用解析结果
```

### Step 5: 更新 `RAGPipeline.build_index`

**文件**: `src/pipeline.py`

修改 `build_index` 方法，使其能够复用 Artifact 系统：

```python
def build_index(self, rebuild=False, force_parse=False, sampling_config=None):
    if sampling_config is None:
        # 无抽样时，检查是否存在全局 Meal
        # 如果存在，复用其解析结果
        # 否则，创建全局 Meal
        ...
```

### Step 6: 添加测试

**文件**: `tests/test_meal.py`

新增测试用例：

```python
def test_create_global_meal(meal_manager):
    """Test creating a global meal with all PDFs."""
    meal = meal_manager.create_global_meal()
    assert meal.name == "_global"
    # 验证包含所有 PDF
    # 验证可以复用解析结果
```

## 风险与缓解

| 风险 | 缓解措施 |
|------|----------|
| 全量 PDF 的 data_id 计算耗时 | 使用增量计算，或缓存文件列表 |
| 旧用户习惯 `python -m src.parser` | 保留兼容性警告，文档明确迁移路径 |
| `_global` 名称冲突 | 允许用户自定义名称 |

## 验收标准

1. `python main.py --create-global-meal` 能创建包含所有 PDF 的 Meal
2. 后续创建抽样 Meal 时，能复用全局 Meal 的解析结果（cache hit）
3. `python -m src.parser` 输出废弃警告但仍能工作
4. 文档已更新
