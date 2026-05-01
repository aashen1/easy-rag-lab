# 测试集管理操作指南

<!-- status: deprecated -->

> ⚠️ **本指南已废弃**。请参阅新版统一指南：[测试集系统完整指南](test-system.md)。
>
> `pixi run testset <子命令>` 替代了本文档中描述的大部分操作。


> 完成日期：2026-04-20
> 版本：v0.1.8

## 概述

本次重构将 TestSet 提升为与 Meal 对等的独立可管理实体，支持按名称引用、有效性判定、自动清洗和审计追踪。

## 核心功能

### 1. TestSetManager 独立管理类

新增 [`src/test_set_manager.py`](../../src/test_set_manager.py) 模块，包含：

**TestSetMetadata dataclass**
- `name`: 测试集名称
- `meal_id`: 创建/最后更新时所属 meal 的标识符
- `created_at`, `updated_at`: 时间戳
- `generation`: 生成配置（strategy, num_questions, type_distribution 等）
- `user_defined`: 是否为人工定义的测试集
- `invalid_policy`: 用户定义集的有效性策略（immutable / trim / regenerate）
- `audit_log`: 只追加的变更记录
- `suppress_warnings`: 是否抑制审计警告

**TestSetManager 类**
- `find_by_name()`: 按名称查找测试集
- `save_test_set()`, `load_test_set()`: 持久化操作
- `list_test_sets()`: 列出 meal 下所有测试集
- `validate_test_set()`: 有效性判定（meal_id 快速路径 + 逐条数据源检查）
- `resolve_test_set()`: 按 on_missing 模式路由解析
- `_clean_machine_test_set()`: 机器生成集自动清洗
- `_clean_user_test_set()`: 用户定义集清洗（根据 invalid_policy）
- `_create_archive_backup()`: Archive 备份机制

### 2. 有效性（Valid）判定

测试集 valid 的唯一条件：**测试集中所有问题引用的数据源，在当前 meal 的抽样中均存在**。

判定逻辑：
1. 若 `meal_id` 与当前 meal 一致 → 跳过检查，直接 valid
2. 若 `meal_id` 不一致 → 逐条检查数据源
   - 全部存在 → valid，同时更新 `meal_id`
   - 存在缺失 → invalid，进入清洗流程

### 3. on_missing 参数

控制按名称查找失败时的兜底行为：

| 值 | 含义 |
|----|------|
| `auto`（默认） | 优先使用/清洗现有数据集，失败则自动生成 |
| `clean_only` | 允许清洗现有 invalid 数据集，但不进行自动生成 |
| `strict` | 仅接受 valid 数据集，不进行清洗或生成 |

### 4. 自动清洗流程

**机器生成集（user_defined: false）**
1. 删除所有失效问题
2. 按 generation 配置补充生成新问题
3. 更新 `meal_id` 和 `audit_log`
4. Generation 参数冲突时以**实验配置**为准

**用户定义集（user_defined: true）**

由 `invalid_policy` 决定：

- **immutable**: 仅更新 meal_id，存在失效问题时 ERROR
- **trim**: 备份 → 删减 → audit_log → warning
- **regenerate**: 备份 → 删减 → 补充生成 → audit_log（generation 参数以**数据集元数据**为准）

### 5. Archive 备份机制

清洗用户定义集前备份原数据集：
```
<original_name>.archive.<ISO8601_timestamp>.json
# 示例：golden_test.archive.20240120T143022Z.json
```

Archive 文件不参与按名称查找逻辑。

### 6. Audit Log 追踪

变更记录格式：
```json
{
  "event": "cleaned",
  "from_meal": "baseline_v1",
  "to_meal": "baseline_v2",
  "removed_count": 3,
  "added_count": 3,
  "timestamp": "2026-04-20T14:30:22"
}
```

## 配置格式

### 新版格式

```yaml
test_sets:
  - name: "golden_test"           # 测试集名称（核心字段）
    on_missing: "auto"            # 可选：auto / clean_only / strict
    generation:                   # 生成配置
      strategy: "document"
      num_questions: 20
      seed: 100
      type_distribution:
        single_fact: 0.30
        multi_fact: 0.25
        reasoning: 0.15
        comparative: 0.15
        missing: 0.10
        irrelevant: 0.05
```

### 旧版格式（向后兼容）

```yaml
test_sets:
  - strategy: "document"
    num_questions: 10
```

旧格式仍可运行，但触发 deprecation warning。

## 测试集 JSON 结构

### 新结构

```json
{
  "metadata": {
    "name": "golden_test",
    "meal_id": "abc123...",
    "created_at": "2026-04-20T10:00:00",
    "updated_at": "2026-04-20T14:30:00",
    "generation": {
      "strategy": "document",
      "num_questions": 20,
      "type_distribution": { ... }
    },
    "user_defined": false,
    "invalid_policy": null,
    "audit_log": [],
    "suppress_warnings": false
  },
  "quality_metrics": { ... },
  "questions": [ ... ]
}
```

### 旧结构（自动迁移）

```json
{
  "name": "document_level_n20",
  "meal_data_id": "abc123...",
  "meal_name": "my_meal",
  "strategy": "document",
  "created_at": "2026-04-20T10:00:00",
  "generation_config": { ... },
  "quality_metrics": { ... },
  "questions": [ ... ]
}
```

旧格式测试集在加载时自动迁移为新结构。

## 文件变更

### 新增文件

- [`src/test_set_manager.py`](../../src/test_set_manager.py) - TestSetManager 核心类
- [`tests/test_test_set_manager.py`](../../tests/test_test_set_manager.py) - TestSetManager 测试

### 修改文件

- [`src/test_generator.py`](../../src/test_generator.py) - 输出新 metadata 结构
- [`src/experiment.py`](../../src/experiment.py) - 新格式校验
- [`eval/run_experiment.py`](../../eval/run_experiment.py) - 重构为使用 TestSetManager
- [`eval/run_eval.py`](../../eval/run_eval.py) - 支持按名称查找（已废弃，请使用 `run_experiment.py`）
- [`main.py`](../../main.py) - CLI 支持 --name 参数
- [`exp_configs/templates/_minimal.yaml`](../../exp_configs/templates/_minimal.yaml) - 新格式示例
- [`exp_configs/templates/_complete.yaml`](../../exp_configs/templates/_complete.yaml) - 新格式完整示例

## 测试结果

全量 **831 个测试** 全部通过，无回归。

关键测试覆盖：
- TestSetMetadata 序列化/反序列化
- TestSetManager CRUD 操作
- 有效性判定（meal_id 快速路径、逐条检查）
- on_missing 三种模式路由
- 机器生成集清洗
- 用户定义集三种 invalid_policy 清洗
- Archive 备份机制
- 旧格式向后兼容

## 使用示例

### 生成测试集

```bash
# 使用新格式（指定名称）
pixi run python main.py --generate-test-set my_meal --name golden_test --strategy document --num-questions 20

# 使用默认名称（旧格式兼容）
pixi run python main.py --generate-test-set my_meal --strategy document --num-questions 10
```

### 实验配置

```yaml
name: "my_experiment"
description: "使用自定义测试集"

data:
  meal: "my_meal"

test_sets:
  - name: "golden_test"
    on_missing: "auto"
    generation:
      strategy: "document"
      num_questions: 20

variants:
  - name: "baseline"
    config_overrides: {}

evaluation:
  llm_preset: "default"
  metrics_preset: "core"
  resolution_strategy: "priority_fallback"
  backend_priority: ["builtin", "ragas"]
```

### 合并测试集

当通过合并 meal 创建新 meal 时，可以合并已有测试集：

```bash
# 合并多个测试集
pixi run python main.py --merge-test-sets A:TA B:TB --meal C --name TC
```

| 参数 | 说明 |
|------|------|
| `--merge-test-sets SPEC [SPEC...]` | 测试集规格列表（格式：`meal:test_set`） |
| `--meal MEAL` | 目标 meal 名称 |
| `--name NAME` | 新测试集名称（可选） |

**合并行为**：
- 问题自动去重（基于问题文本完全匹配）
- 验证问题的 `source_files` 是否在目标 meal 中
- 移除无效问题
- 重新分配问题 ID
- 在 `composition` 和 `audit_log` 中记录合并信息

## 经验教训

1. **向后兼容至关重要**：旧格式测试集和配置必须能正常加载，通过 `_migrate_test_set()` 实现自动迁移
2. **有效性判定需要快速路径**：通过 meal_id 比对避免不必要的逐条检查
3. **用户定义集需要特殊处理**：immutable/trim/regenerate 三种策略满足不同场景需求
4. **Audit Log 是调试利器**：记录所有变更历史，便于追踪问题
5. **Archive 备份防止数据丢失**：清洗前备份，支持手动恢复

## 相关文档

- [Meal 系统指南](meal-system.md)
- [实验系统指南](experiment-system.md)
