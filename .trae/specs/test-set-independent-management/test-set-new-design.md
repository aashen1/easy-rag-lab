# TestSet 独立管理设计方案

## 背景与目标

当前 `exp_configs` 中，`meal` 已是独立、可持久化管理的数据源抽样实体。`test_sets` 则完全由程序自动管理——查找同规格缓存或按 `策略_数量` 命名自动生成，用户无法手动指定。

本次重构目标：**将 test set 提升为与 meal 对等的独立可管理实体**，支持在配置中按名称引用，同时最大限度向下兼容旧配置。

***

## 数据模型

### Test Set 元数据结构

每个 test set 在持久化存储中携带以下元数据：

```yaml
metadata:
  name: "golden_test"             # 测试集名称
  meal_id: "baseline_v2"          # 创建/最后更新时所属 meal 的标识符
  created_at: "2024-01-15T10:00Z"
  updated_at: "2024-01-20T14:30Z"

  generation:                      # 存在则表示为机器生成的测试集
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

  user_defined: false              # true 表示用户定义的测试集
  invalid_policy: null             # 仅当 user_defined: true 时有效（见后文）

  audit_log:                       # 变更记录，只追加不修改
    - event: "trimmed"
      from_meal: "baseline_v1"
      to_meal: "baseline_v2"
      removed_count: 3
      timestamp: "2024-01-20T14:30Z"
    - event: "full_regeneration"   # 特殊标记：用户定义集被完全重新生成
      timestamp: "..."

  suppress_warnings: false         # 用户主动确认后设为 true，停止 audit 相关 warning
```

### 有效性（Valid）判定

**测试集 valid 的唯一条件**：测试集中所有问题引用的数据源，在当前 meal 的抽样中均存在。

`meal_id` 是元数据中的 provenance 字段，用于快速判断：

* 若 `meal_id` 与当前 meal 一致 → 跳过逐条数据源检查，直接视为 valid

* 若 `meal_id` 不一致 → 执行逐条数据源检查

  * 全部存在 → 视为 valid（同时将 `meal_id` 更新为当前 meal）

  * 存在缺失 → invalid，进入清洗流程

***

## 实验配置格式（新版）

### 新格式

```yaml
test_sets:
  - name: "golden_test"           # 测试集名称（新增核心字段）
    on_missing: "auto"            # 找不到时的处理策略（可选，默认 auto）
    generation:                   # 找不到时的生成策略（可选）
      strategy: "document"
      num_questions: 20
      seed: 100
      type_distribution:
        single_fact: 0.30
        multi_fact: 0.25
        ...
```

### 旧格式兼容

旧格式（无 `name` 字段）继续受支持，行为与当前版本一致，但触发 deprecation 提示：

```yaml
# 旧格式（仍可运行）
test_sets:
  - strategy: "document"
    num_questions: 10
```

检测到旧格式时，程序正常执行，并输出以下 warning：

```
[DEPRECATED] test_sets 使用了旧版配置格式。实验将正常运行，但请考虑迁移至新格式：
  test_sets:
    - name: "<自定义名称>"
      on_missing: "auto"
      generation:
        strategy: "document"
        num_questions: 10
```

***

## `on_missing` 参数

控制按名称查找测试集时"找不到任何有效或可清洗的测试集"的兜底行为。

| 值            | 含义                          |
| ------------ | --------------------------- |
| `auto`（默认）   | 优先使用/清洗现有数据集，失败则自动生成        |
| `clean_only` | 允许清洗现有 invalid 数据集，但不进行自动生成 |
| `strict`     | 仅接受 valid 数据集，不进行清洗或生成      |

### `auto` 模式完整流程

```
按名称查找测试集
├── 找到 valid 测试集 → 直接使用
├── 找到 invalid 测试集 → 执行自动清洗（见下文）
│   ├── 清洗成功 → 使用清洗后的测试集
│   └── 清洗失败（用户定义集拒绝修改）→ ERROR，终止实验
└── 未找到任何同名测试集
    ├── 配置中有 generation 参数 → 按参数生成，以指定 name 命名
    └── 无 generation 参数 → 生成 10 个 document 级别问题，以指定 name 命名
        └── [INFO] 提示用户发生了默认生成行为，建议明确配置 generation 参数
```

### `clean_only` 模式完整流程

```
按名称查找测试集
├── 找到 valid 测试集 → 直接使用
├── 找到 invalid 测试集 → 执行自动清洗
│   ├── 清洗成功 → 使用清洗后的测试集
│   └── 清洗失败 → ERROR，终止实验
└── 未找到任何同名测试集 → ERROR，终止实验
    └── [ERROR] 找不到名为 "<name>" 的测试集，且当前模式不允许自动生成。
              请先创建该测试集，或将 on_missing 改为 "auto"。
```

### `strict` 模式完整流程

```
按名称查找测试集
├── 找到 valid 测试集 → 直接使用
├── 找到 invalid 测试集 → ERROR，终止实验
│   └── [ERROR] 测试集 "<name>" 存在但对当前 meal 无效（部分数据源缺失），
              且当前模式不允许自动清洗。请手动更新测试集或更换 meal。
└── 未找到任何同名测试集 → ERROR，终止实验
```

***

## 自动清洗流程

### 机器生成的测试集（`user_defined: false`）

1. 检查所有问题，标记引用了当前 meal 中不存在的数据源的问题
2. 删除所有失效问题
3. 按原 `generation` 配置（如果实验配置中也定义了 `generation`，以**实验配置为准**）补充生成新问题，直到总数恢复至原始数量
4. 将 `meal_id` 更新为当前 meal
5. 向 `audit_log` 写入此次变更记录

**冲突处理**：若实验配置中的 `generation` 参数与数据集元数据中的 `generation` 参数不一致，以实验配置为准，并在 `audit_log` 中记录参数变更。

### 用户定义的测试集（`user_defined: true`）

行为由数据集自身元数据中的 `invalid_policy` 决定，**优先级高于实验配置中的** **`on_missing`**。

#### `invalid_policy: immutable`（严格一致性）

适用场景：用于严谨对比实验的精调数据集，任何问题变动都影响结论可靠性。

* 若所有问题均有效（仅 meal 归属变化）→ 更新 `meal_id`，视为清洗成功

* 若存在任意失效问题 → 拒绝修改，**ERROR 终止实验**

  ```
  [ERROR] 测试集 "<name>" 为 immutable 用户定义集，存在 N 个问题在当前 meal 中        数据源缺失，且该数据集不允许任何问题变动。        请检查 meal 配置，或手动更新测试集。
  ```

#### `invalid_policy: trim`（允许删减，不允许补充）

适用场景：探索性实验，可接受"能用多少用多少"。

* 备份原数据集为 `<name>.archive.<timestamp>`

* 删除所有失效问题，以剩余合法问题作为新测试集

* 向 `audit_log` 写入 `trimmed` 记录（包含 `from_meal`、`to_meal`、`removed_count`）

* 更新 `meal_id`

* 若删除后问题数为 0 → **ERROR 终止实验**，不对数据集做任何修改

  ```
  [ERROR] 测试集 "<name>" 在自动清洗后无任何剩余问题。        请检查 meal 配置与测试集内容是否匹配。
  ```

* 清洗成功后，每次使用该测试集时输出 warning（直到用户将 `suppress_warnings` 设为 `true`）：

  ```
  [WARNING] 测试集 "<name>" 曾在 <timestamp> 的清洗中删除了 N 个问题（<from_meal> → <to_meal>）。          如果这是预期行为，请在测试集元数据中设置 suppress_warnings: true。
  ```

#### `invalid_policy: regenerate`（允许删减和补充）

适用场景：更看重问题数量达标，愿意接受机器补充生成。

* 备份原数据集为 `<name>.archive.<timestamp>`

* 删除所有失效问题

* 按数据集元数据中的 `generation` 配置（若实验配置中同时有 `generation`，以**数据集元数据为准**，与机器生成集的冲突处理相反）补充生成新问题至原始数量

* 更新 `meal_id`，向 `audit_log` 写入记录

* 若清洗后问题数为 0（即所有问题均被替换）→ 清洗仍可继续，但向 `audit_log` 写入 `full_regeneration` 特殊标记，之后每次使用时输出 warning：

  ```
  [WARNING] 测试集 "<name>" 在 <timestamp> 的清洗中所有原始问题均失效并被重新生成，          当前数据集与原始版本已无共同问题。          原始版本已备份为 "<name>.archive.<timestamp>"。          如果这是预期行为，请设置 suppress_warnings: true。
  ```

* `invalid_policy: regenerate` 的数据集必须在自身元数据中配置 `generation` 参数（否则视为配置错误，报 ERROR）

***

## Archive 命名规范

```
<original_name>.archive.<ISO8601_timestamp>
# 示例：golden_test.archive.20240120T143022Z
```

Archive 文件不参与任何按名称的查找逻辑（名称格式不匹配），仅用于数据恢复。

***

## 冲突优先级总结

| 数据集类型                       | `generation` 参数冲突时 | `invalid_policy` 与 `on_missing` 冲突时 |
| --------------------------- | ------------------ | ----------------------------------- |
| 机器生成（`user_defined: false`） | 实验配置优先             | 实验配置优先                              |
| 用户定义（`user_defined: true`）  | 数据集元数据优先           | 数据集元数据优先                            |

***

## 实现检查清单

* [ ] 新增 `name` 字段解析，区分新旧配置格式，旧格式触发 deprecation warning

* [ ] 实现按 `meal_id` 的快速 valid 判定与逐条数据源检查的 fallback

* [ ] 实现三种 `on_missing` 模式的路由逻辑

* [ ] 实现机器生成测试集的自动清洗（含实验配置优先的冲突处理）

* [ ] 实现三种 `invalid_policy` 的用户定义测试集清洗逻辑

* [ ] 实现 archive 备份机制

* [ ] 实现 `audit_log` 的追加写入与 `suppress_warnings` 读取

* [ ] 实现 `on_missing: auto` 在无测试集时的默认生成兜底逻辑

