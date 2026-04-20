# TestSet 独立管理 Spec

## Why

当前 `test_sets` 完全由程序自动管理——按 `策略_数量` 命名自动生成，用户无法手动指定名称，也无法跨 meal 复用或持久化管理测试集。`meal` 已是独立可管理实体，`test_sets` 应提升为与 meal 对等的独立实体，支持按名称引用、有效性判定、自动清洗和审计追踪。

## What Changes

- **新增 TestSetManager 类**：独立管理测试集的 CRUD、有效性判定、清洗和归档，类似 MealManager 对 meal 的管理
- **新增测试集元数据结构**：每个测试集携带 `metadata`（name、meal_id、generation、user_defined、invalid_policy、audit_log、suppress_warnings）
- **新增 `name` 字段解析**：实验配置中 test_sets 支持按名称引用，区分新旧格式，旧格式触发 deprecation warning
- **新增 `on_missing` 参数**：三种模式（auto / clean_only / strict）控制按名称查找失败时的兜底行为
- **新增自动清洗流程**：机器生成集和用户定义集分别有不同的清洗策略
- **新增 archive 备份机制**：清洗用户定义集前备份原数据集
- **新增 audit_log 追踪**：记录测试集变更历史
- **修改 ExperimentConfig.validate()**：适配新格式校验
- **修改 prepare_test_sets()**：使用 TestSetManager 进行按名称查找和清洗
- **修改 run_eval.py 测试集加载**：支持按名称查找
- **更新实验配置模板**：展示新格式用法

## Impact

- Affected specs: 实验系统、评测系统
- Affected code:
  - `src/test_set_manager.py`（新增）- TestSetManager 核心类
  - `src/test_generator.py` - 生成时写入 metadata，文件名改为按 name 命名
  - `src/experiment.py` - ExperimentConfig 适配新格式校验
  - `eval/run_experiment.py` - prepare_test_sets() 重构为使用 TestSetManager
  - `eval/run_eval.py` - 测试集加载适配
  - `main.py` - CLI 适配
  - `exp_configs/templates/` - 模板更新
  - `tests/test_test_set_manager.py`（新增）- TestSetManager 测试
  - `tests/test_experiment.py` - 适配新格式测试
  - `tests/test_test_generator.py` - 适配 metadata 测试

## ADDED Requirements

### Requirement: TestSetManager 独立管理类

系统应提供 `TestSetManager` 类，作为测试集生命周期的统一管理入口，负责按名称查找、有效性判定、清洗、归档和 CRUD 操作。

#### Scenario: 按名称查找测试集

- **WHEN** 调用 `TestSetManager.find_by_name(meal_name, test_set_name)`
- **THEN** 在 `data/meals/{meal_name}/test_sets/` 目录下查找文件名为 `{test_set_name}.json` 的测试集

#### Scenario: 创建新测试集

- **WHEN** 生成新的测试集
- **THEN** 以指定的 `name` 命名保存为 `{name}.json`，并写入完整 metadata

#### Scenario: 列出 meal 下所有测试集

- **WHEN** 调用 `TestSetManager.list_test_sets(meal_name)`
- **THEN** 返回该 meal 目录下所有测试集的名称和 metadata 摘要

### Requirement: 测试集元数据结构

每个测试集 JSON 文件应包含 `metadata` 字段，携带以下信息：

```yaml
metadata:
  name: "golden_test"
  meal_id: "baseline_v2"
  created_at: "2024-01-15T10:00Z"
  updated_at: "2024-01-20T14:30Z"
  generation:
    strategy: "document"
    num_questions: 20
    seed: 100
    type_distribution: { ... }
  user_defined: false
  invalid_policy: null
  audit_log: []
  suppress_warnings: false
```

#### Scenario: 机器生成测试集的 metadata

- **WHEN** 通过 TestSetGenerator 生成测试集
- **THEN** metadata 中 `user_defined` 为 `false`，`generation` 包含完整生成参数，`meal_id` 为当前 meal 的 data_id

#### Scenario: 用户定义测试集的 metadata

- **WHEN** 用户手动创建测试集
- **THEN** metadata 中 `user_defined` 为 `true`，`invalid_policy` 为 `immutable` / `trim` / `regenerate` 之一

### Requirement: 有效性（Valid）判定

测试集 valid 的唯一条件：测试集中所有问题引用的数据源，在当前 meal 的抽样中均存在。

#### Scenario: meal_id 一致时快速判定

- **WHEN** 测试集 metadata 中的 `meal_id` 与当前 meal 的 data_id 一致
- **THEN** 跳过逐条数据源检查，直接视为 valid

#### Scenario: meal_id 不一致但数据源完整

- **WHEN** 测试集 metadata 中的 `meal_id` 与当前 meal 不一致
- **AND** 逐条检查所有问题的数据源均存在于当前 meal
- **THEN** 视为 valid，同时将 `meal_id` 更新为当前 meal 的 data_id

#### Scenario: meal_id 不一致且存在缺失数据源

- **WHEN** 测试集 metadata 中的 `meal_id` 与当前 meal 不一致
- **AND** 存在问题引用了当前 meal 中不存在的数据源
- **THEN** 视为 invalid，进入清洗流程

### Requirement: 新版实验配置格式

实验配置中 test_sets 支持新版格式，包含 `name`、`on_missing`、`generation` 字段。

#### Scenario: 新格式配置

- **WHEN** 实验配置中 test_sets 项包含 `name` 字段
- **THEN** 按新格式解析，使用 `name` 按名称查找测试集，`on_missing` 控制兜底行为

```yaml
test_sets:
  - name: "golden_test"
    on_missing: "auto"
    generation:
      strategy: "document"
      num_questions: 20
      seed: 100
      type_distribution: { ... }
```

#### Scenario: 旧格式兼容

- **WHEN** 实验配置中 test_sets 项不包含 `name` 字段
- **THEN** 按旧格式处理（行为与当前版本一致），同时输出 deprecation warning

### Requirement: on_missing 参数

控制按名称查找测试集时"找不到任何有效或可清洗的测试集"的兜底行为。

#### Scenario: on_missing 为 auto（默认）

- **WHEN** `on_missing` 为 `auto`
- **THEN** 优先使用/清洗现有数据集，失败则自动生成

完整流程：
1. 找到 valid 测试集 → 直接使用
2. 找到 invalid 测试集 → 执行自动清洗
   - 清洗成功 → 使用清洗后的测试集
   - 清洗失败（用户定义集拒绝修改）→ ERROR，终止实验
3. 未找到任何同名测试集
   - 配置中有 generation 参数 → 按参数生成，以指定 name 命名
   - 无 generation 参数 → 生成 10 个 document 级别问题，以指定 name 命名，并输出 INFO 提示

#### Scenario: on_missing 为 clean_only

- **WHEN** `on_missing` 为 `clean_only`
- **THEN** 允许清洗现有 invalid 数据集，但不进行自动生成

完整流程：
1. 找到 valid 测试集 → 直接使用
2. 找到 invalid 测试集 → 执行自动清洗
   - 清洗成功 → 使用清洗后的测试集
   - 清洗失败 → ERROR，终止实验
3. 未找到任何同名测试集 → ERROR，终止实验

#### Scenario: on_missing 为 strict

- **WHEN** `on_missing` 为 `strict`
- **THEN** 仅接受 valid 数据集，不进行清洗或生成

完整流程：
1. 找到 valid 测试集 → 直接使用
2. 找到 invalid 测试集 → ERROR，终止实验
3. 未找到任何同名测试集 → ERROR，终止实验

### Requirement: 机器生成测试集的自动清洗

当机器生成的测试集（`user_defined: false`）为 invalid 时，执行自动清洗。

#### Scenario: 清洗流程

- **WHEN** 机器生成的测试集存在失效问题
- **THEN** 执行以下步骤：
  1. 标记引用了当前 meal 中不存在的数据源的问题
  2. 删除所有失效问题
  3. 按原 generation 配置补充生成新问题至原始数量
  4. 将 `meal_id` 更新为当前 meal
  5. 向 `audit_log` 写入变更记录

#### Scenario: generation 参数冲突（机器生成集）

- **WHEN** 实验配置中的 `generation` 参数与数据集元数据中的 `generation` 参数不一致
- **THEN** 以实验配置为准，并在 `audit_log` 中记录参数变更

### Requirement: 用户定义测试集的清洗策略

用户定义的测试集（`user_defined: true`）的清洗行为由数据集自身元数据中的 `invalid_policy` 决定，优先级高于实验配置中的 `on_missing`。

#### Scenario: invalid_policy 为 immutable

- **WHEN** 用户定义集的 `invalid_policy` 为 `immutable`
- **AND** 所有问题均有效（仅 meal 归属变化）
- **THEN** 更新 `meal_id`，视为清洗成功

- **WHEN** 用户定义集的 `invalid_policy` 为 `immutable`
- **AND** 存在任意失效问题
- **THEN** 拒绝修改，ERROR 终止实验

#### Scenario: invalid_policy 为 trim

- **WHEN** 用户定义集的 `invalid_policy` 为 `trim`
- **THEN** 执行以下步骤：
  1. 备份原数据集为 `<name>.archive.<ISO8601_timestamp>`
  2. 删除所有失效问题
  3. 向 `audit_log` 写入 `trimmed` 记录
  4. 更新 `meal_id`
  5. 若删除后问题数为 0 → ERROR 终止实验，不对数据集做任何修改
  6. 清洗成功后，每次使用时输出 warning（直到 `suppress_warnings` 设为 `true`）

#### Scenario: invalid_policy 为 regenerate

- **WHEN** 用户定义集的 `invalid_policy` 为 `regenerate`
- **THEN** 执行以下步骤：
  1. 备份原数据集为 `<name>.archive.<ISO8601_timestamp>`
  2. 删除所有失效问题
  3. 按数据集元数据中的 `generation` 配置补充生成新问题至原始数量
  4. 更新 `meal_id`，向 `audit_log` 写入记录
  5. 若清洗后问题数为 0 → 清洗仍可继续，但写入 `full_regeneration` 特殊标记，之后每次使用时输出 warning

- **WHEN** 用户定义集的 `invalid_policy` 为 `regenerate` 但元数据中无 `generation` 参数
- **THEN** 视为配置错误，报 ERROR

#### Scenario: generation 参数冲突（用户定义集）

- **WHEN** 用户定义集的 `invalid_policy` 为 `regenerate`
- **AND** 实验配置中同时有 `generation` 参数
- **THEN** 以数据集元数据为准（与机器生成集的冲突处理相反）

### Requirement: Archive 备份机制

清洗用户定义测试集前，备份原数据集。

#### Scenario: 备份命名

- **WHEN** 对用户定义集执行 trim 或 regenerate 清洗
- **THEN** 原数据集备份为 `<original_name>.archive.<ISO8601_timestamp>`

#### Scenario: Archive 不参与查找

- **WHEN** 按名称查找测试集
- **THEN** Archive 文件不参与任何按名称的查找逻辑

### Requirement: Audit Log 追踪

测试集变更时追加写入 audit_log。

#### Scenario: 追加写入

- **WHEN** 测试集发生变更（清洗、参数变更等）
- **THEN** 向 `audit_log` 追加一条记录，包含 event、from_meal、to_meal、removed_count、timestamp 等信息

#### Scenario: suppress_warnings

- **WHEN** 测试集 metadata 中 `suppress_warnings` 为 `true`
- **THEN** 不再输出 audit 相关的 warning

- **WHEN** `suppress_warnings` 为 `false`（默认）
- **THEN** 每次使用清洗过的测试集时输出 warning

## MODIFIED Requirements

### Requirement: ExperimentConfig.validate()

实验配置校验需适配新的 test_sets 格式。

#### 原行为

- test_sets 中每项必须包含 `strategy` 和 `num_questions` 字段

#### 新行为

- 新格式（含 `name` 字段）：`generation` 中应包含 `strategy` 和 `num_questions`
- 旧格式（无 `name` 字段）：保持原校验逻辑，触发 deprecation warning
- `on_missing` 值须为 `auto` / `clean_only` / `strict` 之一

### Requirement: prepare_test_sets()

测试集准备流程需重构为使用 TestSetManager。

#### 原行为

- 按 `策略_数量` 命名查找或生成测试集

#### 新行为

- 新格式：按 `name` 查找，根据 `on_missing` 模式路由
- 旧格式：保持原行为，触发 deprecation warning

### Requirement: 测试集文件命名

#### 原行为

- 文件名按 `document_level_n{num_questions}` 或 `auto_{strategy}_n{num_questions}` 命名

#### 新行为

- 新格式：文件名按 `{name}.json` 命名
- 旧格式：保持原命名方式

### Requirement: 测试集 JSON 结构

#### 原结构

```json
{
  "name": "document_level_n20",
  "meal_data_id": "...",
  "meal_name": "...",
  "strategy": "document",
  "created_at": "...",
  "generation_config": { ... },
  "quality_metrics": { ... },
  "questions": [ ... ]
}
```

#### 新结构

```json
{
  "metadata": {
    "name": "golden_test",
    "meal_id": "...",
    "created_at": "...",
    "updated_at": "...",
    "generation": { ... },
    "user_defined": false,
    "invalid_policy": null,
    "audit_log": [],
    "suppress_warnings": false
  },
  "quality_metrics": { ... },
  "questions": [ ... ]
}
```

## REMOVED Requirements

无移除的需求。旧格式保持兼容，仅标记为 deprecated。
