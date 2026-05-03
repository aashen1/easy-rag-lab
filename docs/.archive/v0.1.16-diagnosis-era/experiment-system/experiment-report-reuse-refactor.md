# 实验报告复用功能重构计划

## 背景分析

当前系统已有以下复用相关机制：

* **断点续跑（Resume）**：通过 `ResumeConfig` + `manifest.json` 的 `completed_variants` / `variant_config_hashes` 实现增量执行

* **实验复现（Reproduce）**：从已有实验目录加载配置快照，重新运行完整实验

* **配置哈希验证**：`compute_variant_config_hash()` 判断变体配置是否变更

但当前机制存在不足：

1. Resume 只能在**同一目录**内增补变体，无法跨实验复用
2. Reproduce 是完整重跑，不是报告内容的迁移复用
3. 没有实验配置指纹识别，无法自动判断两个实验是否"实质相同"
4. 没有报告级别的增量更新和版本回溯能力

## 设计方案

### 一、核心数据模型

#### 1.1 ReportReuseConfig（复用配置）

```python
@dataclass
class ReportReuseConfig:
    mode: Literal["in_place", "copy_migrate", "none"] = "none"
    target_dir: str | None = None           # in-place 模式的目标目录
    source_dir: str | None = None           # copy_migrate 模式的来源目录
    backup_before_append: bool = True        # in-place 专用：增补前是否创建完整快照备份
    fingerprint_keys: list[str] = field(default_factory=lambda: [
        "data.meal", "chunker", "embedding", "retrieval.method",
        "retrieval.top_k", "retrieval.reranker", "retrieval.query_rewrite",
    ])
```

> **注意**：`backup_before_append` 仅适用于 in-place 模式。copy-migrate 模式本质是复制到新目录，原实验不受影响，无需备份。

#### 1.2 ExperimentFingerprint（实验配置指纹）

```python
@dataclass
class ExperimentFingerprint:
    meal_name: str
    chunker_config_hash: str
    embedding_config_hash: str
    retrieval_method: str
    retrieval_top_k: int
    reranker_enabled: bool
    query_rewrite_enabled: bool
    test_set_strategy: str
    test_set_count: int

    def to_dict(self) -> dict[str, Any]: ...
    def matches(self, other: "ExperimentFingerprint") -> bool: ...
```

#### 1.3 Manifest 扩展字段

在 `manifest.json` 中增加：

```json
{
  "reuse_mode": "in_place",
  "reuse_target_dir": "data/exp_reports/exp_20260501_120000",
  "reuse_history": [
    {
      "timestamp": "2026-05-01T12:00:00",
      "action": "append_variant",
      "variant": "new_reranker",
      "backup_snapshot": "exp_20260501_120000_backup/20260501_120000"
    }
  ],
  "fingerprint": { ... }
}
```

### 二、In-Place 模式实现

#### 2.1 配置驱动

在 `config.yaml` 的 `experiments` 节增加：

```yaml
experiments:
  dir: "data/exp_reports"
  configs_dir: "exp_configs"
  reuse:
    mode: "none"               # none / in_place / copy_migrate
    target_dir: null           # in-place 目标目录
    backup_before_append: true  # in-place 专用：增补前创建完整快照备份
```

在实验配置 YAML 中增加：

```yaml
reuse:
  mode: "in_place"
  target_dir: "data/exp_reports/exp_20260501_120000"
  backup_before_append: true   # 仅 in-place 模式生效；copy_migrate 模式忽略此字段
```

#### 2.2 核心流程

1. **识别阶段**：加载实验配置时，检查 `reuse.mode == "in_place"` 且 `reuse.target_dir` 非空
2. **验证阶段**：验证目标目录存在且包含有效 manifest.json
3. **备份阶段**（可选）：若 `backup_before_append=true`，将目标实验目录的**完整快照**复制到同级备份目录
4. **指纹比对**：计算目标实验的指纹，与新配置指纹比对，记录匹配/差异
5. **增量执行**：

   * 仅执行目标实验中不存在的变体（新变体）

   * 已存在且配置哈希匹配的变体直接复用结果

   * 已存在但配置哈希变更的变体需用户确认是否覆盖
6. **报告更新**：将新变体结果追加到已有报告，重新生成对比报告
7. **历史记录**：在 manifest 的 `reuse_history` 中记录本次操作

#### 2.3 增量更新算法

```python
def compute_incremental_updates(
    target_dir: Path,
    new_variants: list[dict],
    exp_manager: ExperimentManager,
) -> tuple[list[dict], list[dict], list[dict]]:
    """计算增量更新计划。

    Returns:
        (to_run, to_reuse, to_confirm) — 需要运行的、可直接复用的、需用户确认的变体
    """
```

#### 2.4 备份机制（In-Place 模式专用）

**设计理念**：启用备份意味着用户打算在目标目录反复增补、反复调试，因此每次运行前需要对当时的完整状态做快照，以便版本回溯。

**目录结构**：备份目录与实验目录同级，以 `_backup` 后缀命名：

```
data/exp_reports/
  exp_20260501_120000/              # 实验目录（活数据）
  exp_20260501_120000_backup/       # 同级备份根目录
    20260501_120000/                # 第 1 次增补前的完整快照
      manifest.json
      config_snapshot.yaml
      meal_snapshot.json
      experiment_report.md
      experiment_report_llm.md
      results/
        baseline.json
        hybrid.json
      test_sets/
        hybrid.json
      profiling/
        ...
    20260502_140000/                # 第 2 次增补前的完整快照
      manifest.json
      ...
    20260503_093000/                # 第 3 次增补前的完整快照
      ...
```

**备份内容**：目标实验目录的**完整递归复制**，包括：
- `manifest.json`、`config_snapshot.yaml`、`meal_snapshot.json`
- `experiment_report.md`、`experiment_report_llm.md`（如存在）
- `results/` 目录下所有变体结果
- `test_sets/` 目录下所有测试集快照
- `profiling/` 目录（如存在）
- `token_summary.json`、`token_summary.txt`（如存在）
- `experiment.log`（如存在）

**快照命名**：使用当前时间戳 `YYYYMMDD_HHMMSS`，与实验 ID 的时间戳格式一致。

**恢复方式**：将备份快照目录中的所有文件复制回实验目录，覆盖当前文件。提供 CLI 命令：
```
pixi run python eval/run_experiment.py --restore-backup exp_20260501_120000 --snapshot 20260502_140000
```

**与 copy-migrate 的区别**：copy-migrate 是将实验复制到**新目录**，原实验不受影响，天然安全，因此不需要备份机制。

### 三、Copy-Migrate 模式实现

#### 3.1 指纹识别算法

```python
def compute_experiment_fingerprint(
    config_snapshot: dict[str, Any],
    manifest: dict[str, Any],
) -> ExperimentFingerprint:
    """从配置快照和 manifest 计算实验指纹。"""
```

指纹匹配规则：

* `meal_name` 必须相同（数据源一致）

* `chunker_config_hash` 必须相同（分块策略一致）

* `embedding_config_hash` 必须相同（向量化一致）

* `retrieval_method` 必须相同（检索方法一致）

* `test_set_strategy` 必须相同（评测策略一致）

* `retrieval_top_k`、`reranker_enabled`、`query_rewrite_enabled` 作为参考指标（不强制匹配）

#### 3.2 核心流程

1. **来源识别**：用户指定来源实验目录，或系统扫描所有实验目录通过指纹匹配
2. **指纹比对**：计算来源实验指纹与当前实验指纹，判断实质是否相同
3. **复制迁移**：

   * 复制来源实验的完整目录结构到新实验目录

   * 复制所有变体结果文件

   * 复制测试集快照、meal 快照

   * 复制报告文件
4. **标识更新**：

   * 生成新的 experiment\_id（带新时间戳）

   * 更新 manifest 中的 experiment\_id、created\_at

   * 在 manifest 中记录 `migrated_from` 字段

   * 更新 config\_snapshot 中的变体列表
5. **增量执行**：对新配置中来源实验不包含的变体，执行评测并追加结果

#### 3.3 迁移完整性保证

* 校验源目录所有必需文件存在（manifest.json、config\_snapshot.yaml、results/\*.json）

* 迁移后验证目标目录文件完整性

* 记录迁移操作日志

### 四、冲突检测与用户交互

#### 4.1 冲突场景

| 场景                    | 处理方式              |
| --------------------- | ----------------- |
| 目标目录不存在               | 报错退出              |
| 目标目录无有效 manifest      | 报错退出              |
| 新变体与已有变体同名但配置不同       | 提示用户确认（覆盖/跳过/重命名） |
| 新变体与已有变体同名且配置相同       | 自动跳过（复用）          |
| copy-migrate 源实验指纹不匹配 | 警告但允许继续           |
| 备份快照时间戳冲突             | 自动追加序号后缀          |

#### 4.2 CLI 交互

```
# In-place 模式：向已有实验目录增补变体
pixi run python eval/run_experiment.py --config exp.yaml --reuse in-place --target-dir data/exp_reports/exp_20260501_120000

# In-place 模式（禁用备份）
pixi run python eval/run_experiment.py --config exp.yaml --reuse in-place --target-dir data/exp_reports/exp_20260501_120000 --no-backup

# Copy-migrate 模式：从已有实验复制迁移
pixi run python eval/run_experiment.py --config exp.yaml --reuse copy-migrate --source-dir data/exp_reports/exp_20260501_120000

# 恢复备份快照
pixi run python eval/run_experiment.py --restore-backup exp_20260501_120000 --snapshot 20260502_140000

# 列出可用备份快照
pixi run python eval/run_experiment.py --list-backups exp_20260501_120000
```

新增 CLI 参数：

* `--reuse {in-place,copy-migrate}` — 复用模式选择

* `--target-dir PATH` — in-place 目标目录

* `--source-dir PATH` — copy-migrate 来源目录

* `--no-backup` — 禁用增补前备份（仅 in-place 模式生效）

* `--restore-backup EXP_ID` — 从备份快照恢复实验目录

* `--snapshot TIMESTAMP` — 指定恢复的快照时间戳（配合 --restore-backup 使用）

* `--list-backups EXP_ID` — 列出实验的所有备份快照

### 五、实现步骤

#### Step 1：数据模型层

1. 创建 `src/experiment_reuse.py`，定义 `ReportReuseConfig`、`ExperimentFingerprint` 数据类
2. 扩展 `ResumeConfig` 或新增 `ReuseConfig` 字段到 `ExperimentConfig`
3. 更新 `ExperimentConfigSchema` 验证逻辑

#### Step 2：指纹识别模块

1. 在 `src/experiment_reuse.py` 中实现 `compute_experiment_fingerprint()`
2. 实现 `fingerprint_matches()` 比对逻辑
3. 实现 `scan_matching_experiments()` 扫描匹配实验
4. 编写单元测试

#### Step 3：In-Place 模式核心逻辑

1. 实现 `InPlaceReuseHandler` 类：

   * `validate_target_dir()` — 验证目标目录

   * `create_full_snapshot()` — 创建完整快照备份（递归复制目标目录到同级 `_backup/{timestamp}/`）

   * `restore_snapshot()` — 从指定快照恢复实验目录

   * `list_snapshots()` — 列出所有可用备份快照

   * `compute_incremental_updates()` — 计算增量计划

   * `append_variant_results()` — 追加变体结果

   * `update_report()` — 重新生成报告

   * `record_reuse_history()` — 记录复用历史
2. 编写单元测试

#### Step 4：Copy-Migrate 模式核心逻辑

1. 实现 `CopyMigrateHandler` 类：

   * `validate_source_dir()` — 验证来源目录

   * `copy_experiment()` — 复制完整实验

   * `update_identifiers()` — 更新实验标识

   * `verify_migration()` — 验证迁移完整性

   * `merge_new_variants()` — 合并新变体
2. 编写单元测试

#### Step 5：集成到实验运行流程

1. 修改 `run_experiment()` 函数，在创建实验目录前检查复用配置
2. 修改 `ExperimentManager`，增加复用相关方法
3. 扩展 `manifest.json` 结构，增加 `reuse_mode`、`reuse_history`、`fingerprint` 字段
4. 更新 `save_snapshots()` 和 `_create_manifest()` 方法

#### Step 6：CLI 集成

1. 在 `eval/run_experiment.py` 增加 `--reuse`、`--target-dir`、`--source-dir`、`--no-backup` 参数
2. 实现 CLI 参数到 `ReportReuseConfig` 的映射
3. 实现冲突检测时的交互式确认流程

#### Step 7：配置集成

1. 更新 `config.yaml` 增加 `experiments.reuse` 配置节
2. 更新 `load_config()` 和配置加载逻辑
3. 更新实验配置模板

#### Step 8：日志与错误处理

1. 在所有复用操作中增加 loguru 日志记录
2. 定义 `ReuseError`、`FingerprintMismatchError`、`ConflictDetectedError` 异常类
3. 实现完善的错误反馈机制

#### Step 9：端到端测试

1. 测试 in-place 模式完整流程
2. 测试 copy-migrate 模式完整流程
3. 测试冲突检测与用户交互
4. 测试备份与恢复
5. 测试边界情况（空目录、损坏的 manifest、指纹不匹配等）

### 六、文件变更清单

| 文件                                           | 变更类型 | 说明                           |
| -------------------------------------------- | ---- | ---------------------------- |
| `src/experiment_reuse.py`                    | 新建   | 复用核心逻辑：数据模型、指纹、Handler       |
| `src/experiment.py`                          | 修改   | ExperimentConfig 增加 reuse 字段 |
| `src/experiment_schemas.py`                  | 修改   | 增加复用配置验证                     |
| `src/exceptions.py`                          | 修改   | 增加复用相关异常类                    |
| `eval/runner/core.py`                        | 修改   | run\_experiment() 集成复用逻辑     |
| `eval/run_experiment.py`                     | 修改   | 增加 CLI 参数                    |
| `config.yaml`                                | 修改   | 增加 experiments.reuse 配置节     |
| `tests/test_experiment_reuse.py`             | 新建   | 复用功能单元测试                     |
| `tests/test_experiment_reuse_integration.py` | 新建   | 复用功能集成测试                     |

### 七、设计原则遵循

* **配置驱动**：复用模式、目标目录、备份开关均通过配置管理

* **统一数据模型**：两种模式共享 `ExperimentFingerprint`、`ReportReuseConfig`，manifest 扩展字段一致

* **冲突检测**：所有潜在覆盖操作前检测并提示

* **日志追踪**：所有复用操作记录到 loguru + manifest.reuse\_history

* **错误处理**：自定义异常类 + 明确错误消息

* **向后兼容**：不使用复用功能时，系统行为与当前完全一致
