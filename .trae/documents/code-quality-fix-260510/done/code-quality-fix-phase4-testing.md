# 代码质量修复计划 - Phase 4 测试质量改进

> 创建日期：2026-05-10 | 目标：删除框架测试 + 重构测试使用 parametrize

---

## 任务概述

基于 `code-quality-fix-progress.md`，Phase 1 和 Phase 2 已完成。本计划聚焦于 **Phase 4: 测试质量改进** 的前两个子任务：

1. **删除框架测试** - 删除测试 Python 标准库/语言本身行为的测试
2. **重构测试使用 parametrize** - 将复制粘贴测试合并为参数化测试

---

## 任务 1: 删除框架测试

### 1.1 目标测试清单

根据审计报告，以下测试验证的是 Python 标准库/语言本身的行为，而非项目逻辑：

| 文件 | 测试类/函数 | 原因 |
|------|------------|------|
| `tests/test_agent.py` | `TestLLMClientCaching` | 测试 `functools.lru_cache` 的缓存行为 |
| `tests/test_agent.py` | `TestMaintenanceStateNewFields` | 测试 TypedDict 能否存储新字段 |
| `tests/test_agent.py` | `TestMaintenanceState` | 测试 Python TypedDict 的赋值和取值行为 |
| `tests/test_experiment.py` | `test_to_dict` | 测试 dict 的赋值行为 |
| `tests/test_meal.py` | `test_to_dict` | 测试 dataclass 的序列化行为 |
| `tests/test_run_experiment.py` | `test_result_merging_builtin_and_ragas` | 测试 `dict.update()` 的行为 |
| `tests/test_evaluators.py` | `TestEvaluationResult` | 测试 dataclass 的创建和 `to_dict` |

### 1.2 执行步骤

1. **读取每个测试文件**，定位目标测试类/函数
2. **验证测试内容**，确认确实是框架测试
3. **删除测试类/函数**
4. **运行测试验证**，确保删除后测试仍然通过
5. **提交变更**

### 1.3 验收标准

- [ ] 所有框架测试已删除
- [ ] `pixi run test` 通过
- [ ] `pixi run lint` 通过

---

## 任务 2: 重构测试使用 parametrize

### 2.1 目标测试清单

根据审计报告，以下测试是复制粘贴模式，应使用 `@pytest.mark.parametrize` 重构：

| 文件 | 测试类 | 测试数 | 模式 |
|------|--------|--------|------|
| `tests/test_metrics.py` | `TestNormalizeSource` | 16 | 输入路径 → 断言归一化结果 |
| `tests/test_agent.py` | `TestToolFunctions` + `TestNewTools` | 15 | `.name` 断言 |
| `tests/test_agent.py` | `TestBuildSystemPrompt` | 6 | 字符串包含测试 |
| `tests/test_agent.py` | `TestCLICommands` | 8 | 命令存在性测试 |
| `tests/test_chunker.py` | `TestChunkTextChineseRoundtrip` | 7 | roundtrip 测试 |
| `tests/test_evaluators.py` | `TestRagasEvaluatorConfigReading` | 4 | 配置读取测试 |

### 2.2 执行步骤

对每个测试类：

1. **读取测试文件**，分析所有测试方法的模式
2. **提取测试数据**，创建参数化数据列表
3. **创建参数化测试函数**，使用 `@pytest.mark.parametrize`
4. **删除原测试方法**
5. **运行测试验证**，确保参数化测试通过
6. **提交变更**

### 2.3 验收标准

- [ ] 所有目标测试类已重构为参数化测试
- [ ] 测试数量显著减少（预计减少 50%+）
- [ ] `pixi run test` 通过
- [ ] `pixi run lint` 通过

---

## 执行顺序

### Step 1: 删除框架测试（预计 1.5 小时）

1. 删除 `tests/test_agent.py` 中的框架测试类
2. 删除 `tests/test_experiment.py` 中的框架测试
3. 删除 `tests/test_meal.py` 中的框架测试
4. 删除 `tests/test_run_experiment.py` 中的框架测试
5. 删除 `tests/test_evaluators.py` 中的框架测试类
6. 运行测试验证

### Step 2: 重构参数化测试（预计 4.5 小时）

1. 重构 `tests/test_metrics.py` 的 `TestNormalizeSource` (16→1)
2. 重构 `tests/test_agent.py` 的 `TestToolFunctions` + `TestNewTools` (15→1)
3. 重构 `tests/test_agent.py` 的 `TestBuildSystemPrompt` (6→1)
4. 重构 `tests/test_agent.py` 的 `TestCLICommands` (8→1)
5. 重构 `tests/test_chunker.py` 的 `TestChunkTextChineseRoundtrip` (7→1)
6. 重构 `tests/test_evaluators.py` 的 `TestRagasEvaluatorConfigReading` (4→1)
7. 运行测试验证

### Step 3: 最终验证

1. 运行 `pixi run test` 确保所有测试通过
2. 运行 `pixi run lint` 确保代码质量
3. 更新进度报告

---

## 风险评估

### 低风险

- **删除框架测试**：这些测试不验证项目逻辑，删除不会影响覆盖率
- **参数化重构**：只是改变测试组织方式，不改变测试逻辑

### 缓解措施

- 每次删除/重构后立即运行测试验证
- 使用 git 提交记录每次变更，便于回滚
- 保持测试的断言逻辑不变，只改变组织方式

---

## 预期成果

### 定量成果

- 删除框架测试：7 个测试类/函数
- 参数化重构：56 个测试方法 → 6 个参数化测试方法
- 测试代码行数减少：预计减少 200+ 行

### 定性成果

- 测试更聚焦于项目逻辑
- 测试代码更简洁、更易维护
- 测试运行更快（参数化测试可并行）

---

## 时间估算

| 任务 | 预计耗时 |
|------|---------|
| 删除框架测试 | 1.5 小时 |
| 参数化重构 | 4.5 小时 |
| 测试验证与提交 | 0.5 小时 |
| **总计** | **6.5 小时** |

---

## 备注

- 本计划聚焦于低风险、高收益的测试质量改进
- 如时间充裕，可继续推进 Phase 3 的架构问题修复
- 每个子任务完成后立即提交，遵循原子提交原则
