# 冒烟测试计划：实验结果复用与增量实验功能

## 1. 测试目标

对 `pixi run exp` 的结果复用与增量实验功能进行全面摸底，发现潜在 bug，提出修复方案。

## 2. 功能范围

### 2.1 核心功能点

| 功能 | 实现位置 | 说明 |
|------|---------|------|
| **Variant 级别 Resume** | `eval/runner/core.py:run_experiment()` | 跳过已完成的 variant |
| **Config Hash 验证** | `src/meal/hashes.py:compute_variant_config_hash()` | 验证配置一致性 |
| **Question 级别 Checkpoint** | `eval/runner/evaluation.py:collect_rag_samples()` | 问题级断点保存/恢复 |
| **Indexer Cache** | `eval/runner/core.py:run_variant_evaluation()` | 索引跨 variant 复用 |
| **Manifest 管理** | `src/experiment.py:ExperimentManager` | 实验状态持久化 |

### 2.2 CLI 参数

- `--resume <exp_dir>`: 从已有实验目录恢复
- `--force-rerun`: 强制重跑所有 variant
- `--force-variant <name>`: 选择性重跑指定 variant

## 3. 测试用例设计

### 3.1 Variant 级别 Resume 测试

#### TC-VR-01: 基本恢复 - 跳过已完成 variant
**步骤**:
1. 创建包含 2 个 variant 的实验配置
2. 运行实验，等待完成
3. 使用 `--resume` 再次运行同一配置

**预期**: 两个 variant 都被跳过，直接复用已有结果

**潜在 Bug**:
- [ ] manifest.json 中 `completed_variants` 未正确更新
- [ ] 结果文件路径不匹配（sanitize_name 问题）

#### TC-VR-02: 增量添加 variant
**步骤**:
1. 运行包含 variant_a 的实验
2. 修改配置，添加 variant_b
3. 使用 `--resume` 运行

**预期**: variant_a 复用，variant_b 新跑

**潜在 Bug**:
- [ ] 新 variant 添加后，旧 variant 的 hash 验证失败
- [ ] indexer_cache 状态不一致

#### TC-VR-03: Config Hash 验证 - 配置变更检测
**步骤**:
1. 运行包含 variant_a 的实验（chunk_size=512）
2. 修改配置，将 chunk_size 改为 256
3. 使用 `--resume` 运行

**预期**: 检测到 hash 变化，自动重跑 variant_a

**潜在 Bug**:
- [ ] hash 计算不包含关键配置项
- [ ] hash 比较逻辑错误（字符串 vs 对象）
- [ ] invalidate 后 manifest 未正确更新

#### TC-VR-04: Config Hash 验证 - 系统配置变更
**步骤**:
1. 运行实验
2. 修改 `config.yaml` 中的全局配置（如 embedding model）
3. 使用 `--resume` 运行

**预期**: 所有 variant 的 hash 都变化，全部重跑

**潜在 Bug**:
- [ ] sanitize_config 遗漏敏感字段
- [ ] 系统配置变更未触发 hash 变化

#### TC-VR-05: --force-variant 选择性重跑
**步骤**:
1. 运行包含 variant_a, variant_b 的实验
2. 使用 `--resume --force-variant variant_a` 运行

**预期**: 只重跑 variant_a，variant_b 复用

**潜在 Bug**:
- [ ] force-variant 后 variant_a 的旧结果文件未清理
- [ ] indexer_cache 使用了旧的索引

#### TC-VR-06: --force-rerun 全部重跑
**步骤**:
1. 运行实验
2. 使用 `--resume --force-rerun` 运行

**预期**: 忽略所有 checkpoint，全部重跑

**潜在 Bug**:
- [ ] manifest 中的 completed_variants 未清空
- [ ] 旧结果文件未覆盖（追加而非替换）

### 3.2 Question 级别 Checkpoint 测试

#### TC-QC-01: 问题级断点保存
**步骤**:
1. 运行实验，在执行过程中 Ctrl+C 中断
2. 使用 `--resume` 恢复

**预期**: 从中断的问题继续，已完成的跳过

**潜在 Bug**:
- [ ] checkpoint 文件损坏（写入中断）
- [ ] checkpoint 文件名冲突（variant name sanitize 问题）
- [ ] 并发模式下 checkpoint 顺序错乱

#### TC-QC-02: 并发模式下的 Checkpoint
**步骤**:
1. 配置 `concurrent_queries: 2`
2. 运行实验并中断
3. 恢复运行

**预期**: 已完成的问题正确恢复，顺序正确

**潜在 Bug**:
- [ ] 并发写入 checkpoint 导致数据丢失
- [ ] results_dict 顺序与问题顺序不一致
- [ ] _on_future_done 回调中的竞态条件

#### TC-QC-03: 模型变更检测
**步骤**:
1. 使用 gpt-4 运行实验并中断
2. 修改配置使用 gpt-3.5-turbo
3. 恢复运行

**预期**: 输出警告，但允许继续（或按配置决定行为）

**潜在 Bug**:
- [ ] 模型变更未检测
- [ ] 检测到变更但未输出警告
- [ ] 检测逻辑在错误的阶段执行

#### TC-QC-04: Checkpoint 清理
**步骤**:
1. 运行实验完成所有问题
2. 检查 checkpoint 目录

**预期**: checkpoint 文件被清理

**潜在 Bug**:
- [ ] checkpoint 文件残留
- [ ] 清理失败但未报错

### 3.3 Indexer Cache 测试

#### TC-IC-01: 相同 Chunker Config 复用
**步骤**:
1. 创建包含 2 个 variant 的实验，使用相同的 chunk_size
2. 运行实验

**预期**: 第二个 variant 复用第一个的索引

**潜在 Bug**:
- [ ] 索引未正确复用
- [ ] 复用时 indexer 状态不正确（is_closed 检查）
- [ ] chunker_hash 计算不包含所有相关参数

#### TC-IC-02: 不同 Chunker Config 重建
**步骤**:
1. 创建包含 2 个 variant 的实验，使用不同的 chunk_size
2. 运行实验

**预期**: 每个 variant 创建独立索引

**潜在 Bug**:
- [ ] 旧索引未关闭导致资源泄漏
- [ ] 新索引覆盖旧索引

#### TC-IC-03: Resume 时的 Indexer Cache
**步骤**:
1. 运行包含 variant_a 的实验
2. 添加 variant_b（相同 chunker config）
3. Resume

**预期**: variant_b 复用 variant_a 的索引

**潜在 Bug**:
- [ ] indexer_cache 在 resume 时未正确初始化
- [ ] 缓存的 indexer 已关闭无法重用

### 3.4 边界情况和错误处理

#### TC-ERR-01: Manifest 损坏
**步骤**:
1. 运行实验
2. 手动损坏 manifest.json（删除部分内容）
3. Resume

**预期**: 输出错误信息，优雅降级

**潜在 Bug**:
- [ ] JSON 解析错误未捕获
- [ ] 损坏的 manifest 导致程序崩溃

#### TC-ERR-02: Checkpoint 文件损坏
**步骤**:
1. 运行实验并中断
2. 手动损坏 checkpoint 文件
3. Resume

**预期**: 检测到损坏，从头开始该 variant

**潜在 Bug**:
- [ ] 损坏的 JSON 导致程序崩溃
- [ ] 损坏的数据被加载导致后续错误

#### TC-ERR-03: 结果文件丢失
**步骤**:
1. 运行实验完成
2. 删除某个 variant 的结果文件
3. Resume

**预期**: 检测到文件丢失，重跑该 variant

**潜在 Bug**:
- [ ] 文件丢失未检测，导致结果不完整
- [ ] load_variant_result 返回 None 但未正确处理

#### TC-ERR-04: 空 Test Set
**步骤**:
1. 创建包含 0 个问题的 test set
2. 运行实验

**预期**: 优雅处理，不崩溃

**潜在 Bug**:
- [ ] 除零错误（avg_time_per_question）
- [ ] 空列表导致后续逻辑错误

#### TC-ERR-05: Variant 名称特殊字符
**步骤**:
1. 创建 variant 名称包含特殊字符（如 "Chunk-512/Overlap:0"）
2. 运行实验

**预期**: 正确 sanitize，文件名安全

**潜在 Bug**:
- [ ] sanitize_name 逻辑不完整
- [ ] 不同位置使用不同的 sanitize 逻辑

### 3.5 集成测试

#### TC-INT-01: 完整增量工作流
**步骤**:
1. 创建实验配置，包含 variant_a
2. 运行实验
3. 添加 variant_b，resume
4. 修改 variant_a 配置，resume
5. 添加 variant_c，resume

**预期**: 每步都正确处理

#### TC-INT-02: 多 Test Set 场景
**步骤**:
1. 创建包含 2 个 test set 的实验
2. 运行并中断
3. Resume

**预期**: 两个 test set 的进度都正确恢复

## 4. 已知/潜在 Bug 分析

### 4.1 代码审查发现的问题

#### BUG-01: indexer_cache 在 resume 时可能泄漏资源
**位置**: `eval/runner/core.py:163-177`

**问题**: 当从缓存获取 indexer 时，如果 `indexer.is_closed()` 为 True，会关闭所有缓存的 indexer 然后重新打开当前这个。但如果有多个 indexer 都关闭了，只重新打开一个，其他的可能丢失。

```python
if indexer.is_closed():
    for cached_indexer in indexer_cache.values():
        if not cached_indexer.is_closed():
            cached_indexer.close()
    indexer.reopen()
```

**影响**: 资源泄漏，后续 variant 可能无法复用缓存

**修复建议**: 检查所有缓存的 indexer 状态，必要时重建

#### BUG-02: 并发模式下 checkpoint 保存可能丢失数据
**位置**: `eval/runner/evaluation.py:535-552`

**问题**: `_on_future_done` 回调中，`results_dict` 和 `_save_question_checkpoint` 都在锁内执行，但 `sorted_samples` 的构建依赖 `results_dict` 的所有 key。如果有新的结果在排序过程中添加，可能导致顺序不一致。

**影响**: checkpoint 中的问题顺序可能与实际不一致

**修复建议**: 使用更严格的同步机制，或在保存前获取 results_dict 的快照

#### BUG-03: compute_variant_config_hash 可能不包含所有影响结果的配置
**位置**: `src/meal/hashes.py:142-178`

**问题**: hash 只包含 `variant_overrides`, `merged`, `data`, `test_sets`, `evaluation`，但未包含：
- `force_overwrite` 设置
- `llm` preset 配置
- 系统级的 `token_cost` 等可能影响行为的配置

**影响**: 配置变更但 hash 不变，导致错误复用旧结果

**修复建议**: 扩展 hash 计算范围，或明确文档说明哪些配置变更需要手动重跑

#### BUG-04: sanitize_config 可能遗漏敏感信息
**位置**: `eval/runner/asset_verifier.py:sanitize_config()`

**问题**: 需要检查该函数是否正确移除了所有敏感字段（API key、密码等）

**影响**: 敏感信息泄露到 config_snapshot.yaml

**修复建议**: 审查并测试 sanitize_config 的输出

#### BUG-05: variant 完成后 checkpoint 清理可能失败但被忽略
**位置**: `eval/runner/core.py:331-340`

**问题**: checkpoint 清理失败时只记录日志，不抛出异常

```python
try:
    checkpoint_file.unlink()
    logger.info(f"Cleaned up checkpoint for variant '{variant_name}'")
except OSError:
    pass
```

**影响**: checkpoint 文件残留，可能影响后续运行

**修复建议**: 记录警告而非静默忽略，或在下次运行时检查并清理

#### BUG-06: Question 级别 checkpoint 的 model_name 可能为空
**位置**: `eval/runner/evaluation.py:56-92`

**问题**: `_save_question_checkpoint` 接受 `model_name` 参数，但在调用时可能传入空字符串

**影响**: 模型变更检测失效

**修复建议**: 确保调用时传入正确的 model_name

#### BUG-07: force-variant 后旧结果文件可能残留
**位置**: `eval/runner/core.py:575-587`

**问题**: `invalidate_variant` 只更新 manifest，不删除结果文件

**影响**: 旧结果文件残留，可能造成混淆

**修复建议**: 在 invalidate 时同时删除对应的结果文件

### 4.2 测试中需要验证的问题

1. **Hash 碰撞**: 短 hash（12 字符）是否存在碰撞风险
2. **时区问题**: 时间戳使用本地时间还是 UTC
3. **并发安全**: 多线程/多进程场景下的数据一致性
4. **大实验**: 大量 variant 或大量问题时的性能和稳定性

## 5. 测试执行计划

### 5.1 准备工作

1. 创建测试用的实验配置文件
2. 准备测试数据（小型 PDF 文档）
3. 配置测试用的 LLM preset（使用便宜的模型）

### 5.2 执行顺序

1. 先执行基本功能测试（TC-VR-01 ~ TC-VR-06）
2. 再执行问题级 checkpoint 测试（TC-QC-01 ~ TC-QC-04）
3. 然后执行 Indexer Cache 测试（TC-IC-01 ~ TC-IC-03）
4. 接着执行错误处理测试（TC-ERR-01 ~ TC-ERR-05）
5. 最后执行集成测试（TC-INT-01 ~ TC-INT-02）

### 5.3 测试脚本

创建自动化测试脚本，每个测试用例：
1. 准备环境
2. 执行操作
3. 验证结果
4. 清理环境

## 6. 修复优先级

| 优先级 | Bug ID | 说明 |
|--------|--------|------|
| P0 | BUG-03 | Hash 计算不完整，可能导致错误复用结果 |
| P0 | BUG-07 | force-variant 后旧结果残留 |
| P1 | BUG-01 | Indexer cache 资源泄漏 |
| P1 | BUG-02 | 并发 checkpoint 数据不一致风险 |
| P1 | BUG-06 | 模型变更检测失效 |
| P2 | BUG-04 | 敏感信息泄露风险 |
| P2 | BUG-05 | Checkpoint 清理失败被忽略 |

## 7. 复用配置方案对比

### 7.1 当前实现

当前 `pixi run exp` 是一个 pixi task 语法糖：

```toml
[tasks._run-exp]
args = ["config"]
cmd = "python eval/run_experiment.py --config {{ config }}"

[tasks.exp]
args = ["name"]
depends-on = [
  { task = "_run-exp", args = [
    "exp_configs/{{ name if '.yaml' in name else name + '.yaml' }}"
  ]}
]
```

使用方式：`pixi run exp baseline` → 运行 `exp_configs/baseline.yaml`

### 7.2 方案A：CLI 参数

继续使用 CLI 参数传递复用设置。

**实现方式**：

```toml
[tasks.exp]
args = ["name"]
cmd = """
python eval/run_experiment.py --config exp_configs/{{ name if '.yaml' in name else name + '.yaml' }} {{ extra_args }}
"""
```

**使用方式**：
```bash
# 普通运行
pixi run exp baseline

# Resume（需要用 -- 分隔）
pixi run exp baseline -- --resume data/exp_reports/exp_001

# 强制重跑指定 variant
pixi run exp baseline -- --resume data/exp_reports/exp_001 --force-variant variant_a
```

**优点**：
- ✅ 灵活，可以临时决定
- ✅ 不需要修改 YAML 文件
- ✅ 符合传统 CLI 工具习惯

**缺点**：
- ❌ 命令行复杂，用户需要记住多个参数
- ❌ pixi task 的 `--` 分隔符不够直观
- ❌ 路径输入繁琐（如 `data/exp_reports/exp_20260501_120000_my_experiment`）
- ❌ 无法版本控制复用决策

### 7.3 方案B：YAML 配置

在 exp_configs YAML 文件中声明复用设置。

**实现方式**：

```yaml
name: "my_experiment"
description: "实验描述"

# 新增：复用配置
resume:
  from: "data/exp_reports/exp_20260501_120000_my_experiment"  # 可选：从哪个实验恢复
  force_rerun: false          # 是否强制重跑所有 variant
  force_variants: []          # 选择性重跑的 variant 列表
  # 或者更简洁的写法：
  # force_variants: ["variant_a", "variant_b"]

# 其他配置保持不变
data:
  meal: "my_meal"
# ...
```

**使用方式**：
```bash
# 所有设置都在 YAML 中，命令行保持简洁
pixi run exp baseline

# 临时覆盖（可选，通过环境变量）
RESUME_FROM=exp_001 pixi run exp baseline
```

**优点**：
- ✅ 配置集中，一目了然
- ✅ 命令行简洁：`pixi run exp baseline`
- ✅ 可版本控制，记录每次实验的复用决策
- ✅ 符合 "配置即代码" 理念
- ✅ 便于复现：看到 YAML 就知道用了哪些设置
- ✅ IDE 友好，可以有 schema 提示

**缺点**：
- ❌ 每次修改需要编辑文件
- ❌ 不够灵活，无法临时调整
- ❌ 需要修改 `ExperimentConfig` 类和验证逻辑

### 7.4 方案对比总结

| 维度 | 方案A (CLI) | 方案B (YAML) |
|------|------------|--------------|
| **用户体验** | 命令行复杂，需要记住参数 | 命令行简洁，配置集中 |
| **灵活性** | ✅ 高，可临时决定 | ❌ 低，需编辑文件 |
| **可追溯性** | ❌ 无，命令不记录 | ✅ 高，配置可版本控制 |
| **实现成本** | ✅ 低，已有 CLI 参数 | ❌ 中，需修改配置类 |
| **IDE 支持** | ❌ 无 | ✅ 可有 schema 提示 |
| **典型场景** | 临时调试、快速迭代 | 正式实验、团队协作 |

### 7.5 推荐方案

**推荐方案B（YAML 配置）**，理由：

1. **用户友好**：用户不需要记住复杂的 CLI 参数，只需编辑熟悉的 YAML 文件
2. **可追溯**：复用决策被记录在配置文件中，便于后续审查和复现
3. **一致性**：与实验的其他配置（data、test_sets、variants）保持一致
4. **团队协作**：配置文件可以提交到 git，团队成员可以看到复用设置

**实现建议**：

```yaml
# exp_configs/baseline.yaml
name: "baseline"
description: "基线实验"

# 复用配置（可选，省略则从头开始）
resume:
  # 从哪个实验目录恢复（支持相对路径或绝对路径）
  # 可以是目录名（自动在 data/exp_reports 下查找）或完整路径
  from: "exp_20260501_120000"  # 或 "data/exp_reports/exp_20260501_120000"

  # 是否强制重跑所有 variant（默认 false）
  force_rerun: false

  # 选择性重跑的 variant（默认空）
  force_variants: ["variant_a"]

# 其他配置...
data:
  meal: "my_meal"
# ...
```

**兼容性**：
- 现有的 CLI 参数继续支持，作为 YAML 配置的覆盖
- 优先级：CLI 参数 > YAML 配置 > 默认值

### 7.6 实现细节

如果选择方案B，需要修改：

1. **ExperimentConfig 类** (`src/experiment.py`)：
   - 添加 `resume` 字段
   - 定义 `ResumeConfig` 子类

2. **run_experiment 函数** (`eval/runner/core.py`)：
   - 从 `exp_config.resume` 读取配置
   - CLI 参数作为覆盖

3. **文档更新**：
   - 更新 `docs/user-guides/experiment-system.md`
   - 添加 `resume` 配置的说明

---

## 8. 测试执行结果

### 8.1 测试日期

2026-05-01

### 8.2 测试结果汇总

| 测试用例 | 状态 | 说明 |
|---------|------|------|
| TC-VR-01: 基本恢复 | ✅ 通过 | variant 被正确跳过，耗时从 258s 降到 0.13s |
| TC-VR-02: 增量添加 variant | ✅ 通过 | variant_a 复用，variant_b 新跑 |
| TC-VR-03: 配置变更检测 | ✅ 通过 | 检测到 hash 变化，自动重跑 variant |
| TC-VR-05: force-variant | ✅ 通过 | 强制重跑指定 variant |

### 8.3 发现并修复的 Bug

#### BUG-08: `effective_resume_dir` 未被正确使用
**位置**: `eval/runner/core.py:571`

**问题**: 使用 `resume_dir` 而不是 `effective_resume_dir` 判断是否需要保存 snapshot

**影响**: 使用 YAML 配置 resume 时，snapshot 保存逻辑错误

**修复**: 将 `if not resume_dir:` 改为 `if not effective_resume_dir:`

**状态**: ✅ 已修复

#### BUG-09: 配置变更后 variant 未重新运行
**位置**: `eval/runner/core.py:660-662`

**问题**: 当 hash 不匹配时，代码执行 `continue` 跳过了当前 variant 的评估逻辑

**影响**: 配置变更后 variant 被标记为 invalidate，但实际没有重新运行

**修复**: 重构代码逻辑，只有当 hash 匹配时才加载旧结果并跳过评估

**状态**: ✅ 已修复

### 8.4 实现的新功能

#### 功能: YAML 配置支持 resume 设置

**实现位置**:
- `src/experiment.py`: 新增 `ResumeConfig` 类
- `eval/runner/core.py`: 从 YAML 读取 resume 配置

**配置示例**:
```yaml
resume:
  from: "exp_20260501_122627_resume_test"
  force_rerun: false
  force_variants: ["variant_a"]
```

**状态**: ✅ 已实现

---

## 9. 后续行动

1. **已完成**: 冒烟测试，发现并修复 2 个 Bug
2. **已完成**: 实现 YAML 配置支持 resume 设置
3. **建议**: 添加更多自动化测试用例
4. **建议**: 更新用户文档
