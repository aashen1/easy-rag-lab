# Phase 3 实施计划：治本（P2-P3 架构问题）

> 创建日期：2026-05-11 | 目标：完成 Phase 3 中相对独立、风险可控的任务

---

## 一、任务选择原则

### 1.1 选择标准

- ✅ **相对独立**：不依赖其他未完成的 Phase 3 任务
- ✅ **风险可控**：修改影响范围明确，易于验证
- ✅ **收益明确**：能显著改善代码质量
- ✅ **时间合理**：单次会话可完成

### 1.2 排除的任务

- ❌ **重构 `ExperimentConfigSchema`**（3.1.1）：影响范围大，需要充分测试
- ❌ **修复 `extra = "allow"` 泛滥**（3.1.2）：可能破坏现有配置兼容性
- ❌ **重构 `LLMEvaluatorConfig`**（3.1.3）：需要更新大量访问点
- ❌ **统一 dataclass/Pydantic 使用策略**（3.3）：涉及多个核心文件
- ❌ **拆分 `build_index()` 方法**（3.4.3）：复杂度高，影响核心流程

---

## 二、任务清单

### 任务组 1：移除过度设计（预计 7.25 小时）

#### 1.1 删除 `ExperimentReporter` 无用委托方法

**文件**: `eval/reporter/__init__.py:118-173`

**当前问题**:
- 6 个 static 方法，每个都是一行委托
- 完全没有存在的必要，调用方应直接使用 `formatters.py` 中的函数

**实施步骤**:

1. **分析 6 个 static 方法的调用点**
   - 搜索每个方法的调用：`_get_generation_metric`, `_get_all_generation_metrics`, `_get_retrieval_metric`, `_get_all_retrieval_metrics`, `_get_chunk_metric`, `_get_all_chunk_metrics`
   - 记录所有调用位置
   - 验收标准：完成调用点清单

2. **更新调用点直接使用 `formatters.py` 函数**
   - 替换委托调用为直接调用
   - 例如：`ExperimentReporter._get_generation_metric(...)` → `get_generation_metric(...)`
   - 验收标准：所有调用点已更新

3. **删除 6 个 static 方法**
   - 删除第 118-173 行
   - 验收标准：方法已删除，测试通过

**预计耗时**: 2.25 小时

---

#### 1.2 删除 `eval/metrics/utils.py` 不必要的间接层

**文件**: `eval/metrics/utils.py`

**当前问题**:
- `create_llm_client()` 只是 `src.utils.create_llm_client` 的薄包装
- 增加了不必要的间接层

**实施步骤**:

1. **分析 `create_llm_client()` 的调用点**
   - 搜索 `from eval.metrics.utils import create_llm_client`
   - 搜索 `eval.metrics.utils.create_llm_client`
   - 验收标准：完成调用点清单

2. **更新调用点直接使用 `src.utils.create_llm_client`**
   - 替换导入语句
   - 替换函数调用
   - 验收标准：所有调用点已更新

3. **删除 `create_llm_client()` 包装函数**
   - 删除薄包装
   - 验收标准：函数已删除，测试通过

**预计耗时**: 1.75 小时

---

#### 1.3 删除 `eval/experiment_reporter.py` 纯转发模块

**文件**: `eval/experiment_reporter.py`

**当前问题**:
- 17 行文件，只是从 `eval.reporter` 重新导出符号
- 兼容性垫片，如无旧依赖方可移除

**实施步骤**:

1. **分析重新导出的符号**
   - 列出所有导出的符号
   - 验收标准：完成符号清单

2. **搜索所有导入点**
   - 搜索 `from eval.experiment_reporter import`
   - 搜索 `import eval.experiment_reporter`
   - 验收标准：完成导入点清单

3. **更新导入点直接使用 `eval.reporter`**
   - 替换导入路径
   - 验收标准：所有导入点已更新

4. **删除 `experiment_reporter.py` 文件**
   - 移入 `.trashbin/`
   - 验收标准：文件已删除，测试通过

**预计耗时**: 2 小时

---

#### 1.4 移除 `src/issue/migrate.py` 到 scripts/

**文件**: `src/issue/migrate.py`

**当前问题**:
- 630 行一次性迁移工具
- 从 `backlog.md` 迁移到 issue 文件是一次性操作
- 不应长期驻留在生产代码中

**实施步骤**:

1. **确认迁移已完成**
   - 检查是否还有未迁移的 backlog
   - 检查是否有其他代码依赖此文件
   - 验收标准：确认迁移完成，无依赖

2. **移动文件到 `scripts/` 目录**
   - 从 `src/issue/` 移动到 `scripts/`
   - 更新文件名（如需要）
   - 验收标准：文件已移动

3. **更新导入路径（如有）**
   - 搜索并更新所有导入
   - 验收标准：无导入错误

**预计耗时**: 1.25 小时

---

### 任务组 2：修复架构问题（预计 3.5 小时）

#### 2.1 修复 `ExperimentFingerprint` 字段不一致

**文件**: `src/experiment_reuse.py`

**当前问题**:
- `matches()` 只检查 5 个字段
- `diff()` 检查 9 个字段
- `compute_hash()` 又用全部 9 个字段
- 三者的字段集合不一致，容易引发混淆

**实施步骤**:

1. **分析三个方法的字段使用情况**
   - 列出 `matches()` 使用的字段
   - 列出 `diff()` 使用的字段
   - 列出 `compute_hash()` 使用的字段
   - 验收标准：完成字段对比文档

2. **决定统一的字段集合**
   - 确定哪些字段应该用于比较
   - 文档化决策理由
   - 验收标准：决策文档完成

3. **更新三个方法使用一致的字段集合**
   - 修改 `matches()` 方法
   - 修改 `diff()` 方法（如需要）
   - 修改 `compute_hash()` 方法（如需要）
   - 验收标准：三个方法使用一致的字段集合

4. **更新单元测试**
   - 添加测试验证字段一致性
   - 验收标准：测试通过

**预计耗时**: 2 小时

---

#### 2.2 消除 `use_meal()` 中重复的配置读取

**文件**: `src/pipeline.py:615-626, 189-199`

**当前问题**:
- `use_meal()` 方法中 `HybridRetriever` 的配置读取（615-626 行）
- 与 `_setup_retrievers()` 中的（189-199 行）完全重复
- 都是逐层 `.get()` 取值

**实施步骤**:

1. **分析两处重复的配置读取逻辑**
   - 对比 615-626 行和 189-199 行
   - 识别完全相同的代码
   - 验收标准：完成重复分析文档

2. **提取 `_get_hybrid_retriever_config()` 函数**
   - 封装逐层 `.get()` 取值逻辑
   - 返回配置字典或配置对象
   - 验收标准：函数提取完成，单元测试通过

3. **重构两处使用新函数**
   - 更新 `use_meal()` (615-626行)
   - 更新 `_setup_retrievers()` (189-199行)
   - 验收标准：无重复代码，功能验证通过

**预计耗时**: 1.5 小时

---

### 任务组 3：类型安全改进（预计 3 小时）

#### 3.1 为裸 `dict` 字段定义 Pydantic 模型

**文件**: `src/config_schema.py`

**当前问题**:
- `EvaluationRagasConfig.run_config: dict` - 放弃验证
- `TestGenerationConfig.validation: dict` - 放弃验证
- `AgentConfig.checkpoint: dict` - 放弃验证

**实施步骤**:

1. **定义 `RunConfigConfig` 模型**
   - 字段: `max_workers: int`, `timeout: int`, `max_retries: int`
   - 添加合理的默认值
   - 验收标准：模型定义完成

2. **更新 `EvaluationRagasConfig.run_config` 类型**
   - 从 `dict` 改为 `RunConfigConfig`
   - 验收标准：类型更新完成，测试通过

3. **定义 `ValidationConfig` 模型**
   - 字段: `check_proper_nouns: bool`
   - 验收标准：模型定义完成

4. **更新 `TestGenerationConfig.validation` 类型**
   - 从 `dict` 改为 `ValidationConfig`
   - 验收标准：类型更新完成，测试通过

5. **定义 `CheckpointConfig` 模型**
   - 字段: `db_path: str`
   - 验收标准：模型定义完成

6. **更新 `AgentConfig.checkpoint` 类型**
   - 从 `dict` 改为 `CheckpointConfig`
   - 验收标准：类型更新完成，测试通过

**预计耗时**: 3 小时

---

## 三、实施顺序

### 3.1 推荐顺序

**第一批（低风险，快速见效）**:
1. 任务 1.2：删除 `eval/metrics/utils.py` 不必要的间接层
2. 任务 1.3：删除 `eval/experiment_reporter.py` 纯转发模块
3. 任务 1.4：移除 `src/issue/migrate.py` 到 scripts/

**第二批（中等风险，需要仔细测试）**:
4. 任务 1.1：删除 `ExperimentReporter` 无用委托方法
5. 任务 2.2：消除 `use_meal()` 中重复的配置读取
6. 任务 3.1：为裸 `dict` 字段定义 Pydantic 模型

**第三批（需要决策）**:
7. 任务 2.1：修复 `ExperimentFingerprint` 字段不一致

### 3.2 并行执行可能性

- 任务 1.2、1.3、1.4 可以并行执行（无依赖关系）
- 任务 2.2 和 3.1 可以并行执行（修改不同文件）
- 任务 1.1 和 2.1 需要单独执行（涉及决策）

---

## 四、验收标准

### 4.1 每个 task 的验收标准

- ✅ 代码修改完成
- ✅ 单元测试通过
- ✅ Lint 检查通过
- ✅ 无功能回归

### 4.2 整体验收标准

- ✅ 所有测试通过 (`pixi run test-all`)
- ✅ Lint 检查通过 (`pixi run lint`)
- ✅ 代码行数减少（移除过度设计部分）
- ✅ 类型安全性提升（Pydantic 模型改进）
- ✅ 无重复代码（配置读取逻辑）

---

## 五、风险与缓解措施

### 5.1 风险识别

| 风险 | 影响 | 概率 | 缓解措施 |
|------|------|------|---------|
| 删除转发模块破坏兼容性 | 高 | 中 | 充分搜索所有导入点 |
| Pydantic 模型变更破坏配置加载 | 高 | 低 | 保留默认值，测试配置加载 |
| 字段不一致修复影响实验复用 | 中 | 低 | 添加单元测试验证行为 |
| 移动 migrate.py 破坏现有流程 | 低 | 低 | 确认迁移已完成 |

### 5.2 回滚策略

- 每个 task 完成后立即提交
- 如发现问题，可快速回滚到上一个提交
- 保留 `.trashbin/` 中的删除文件

---

## 六、时间估算

| 任务组 | 任务数 | 预计耗时 |
|--------|--------|---------|
| 任务组 1：移除过度设计 | 4 | 7.25 小时 |
| 任务组 2：修复架构问题 | 2 | 3.5 小时 |
| 任务组 3：类型安全改进 | 1 | 3 小时 |
| **总计** | **7** | **13.75 小时** |

---

## 七、成功标准

### 7.1 代码质量改进

- ✅ 删除 3 个不必要的间接层/转发模块
- ✅ 移动 1 个一次性工具到合适位置
- ✅ 消除 1 处重复代码
- ✅ 为 3 个裸 `dict` 字段添加类型安全
- ✅ 修复 1 个字段不一致问题

### 7.2 测试覆盖

- ✅ 所有现有测试通过
- ✅ 新增类型验证测试
- ✅ 新增字段一致性测试

### 7.3 文档更新

- ✅ 更新相关代码注释
- ✅ 记录架构决策

---

## 八、后续任务

完成本次计划后，Phase 3 剩余任务：

1. **重构 `ExperimentConfigSchema`**（3.1.1）- 6 小时
2. **修复 `extra = "allow"` 泛滥**（3.1.2）- 4.25 小时
3. **重构 `LLMEvaluatorConfig`**（3.1.3）- 3 小时
4. **统一 dataclass/Pydantic 使用策略**（3.3）- 7 小时
5. **拆分 `build_index()` 方法**（3.4.3）- 9 小时

**剩余任务预计耗时**: 约 29.25 小时

---

## 九、执行检查清单

### 9.1 执行前检查

- [ ] 确认当前分支状态干净
- [ ] 确认测试环境可用
- [ ] 备份重要配置文件

### 9.2 执行中检查

- [ ] 每个 task 完成后运行测试
- [ ] 每个 task 完成后运行 lint
- [ ] 每个 task 完成后提交代码

### 9.3 执行后检查

- [ ] 运行全量测试 `pixi run test-all`
- [ ] 运行 lint 检查 `pixi run lint`
- [ ] 更新进度报告
- [ ] 更新相关文档

---

**计划创建完成，等待用户确认后开始执行。**
