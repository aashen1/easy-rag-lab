# 维修工 Agent 修复计划

> 状态: Plan | 日期: 2026-05-09
> 依据: 原设计稿 + 审查结果 + 用户反馈

---

## 一、修复优先级总览

根据审查结果和用户反馈,修复任务分为以下优先级:

### P0 (必须修复,影响核心功能)
1. ✅ **P0-2**: delete_source 累计删除硬拦截 (C12)
2. ✅ **P0-3**: Streamlit interrupt 处理优化 (C10)

### P1 (应该修复,影响用户体验)
1. ✅ **P1-1**: 简化轻量/全量双模式 (C6) - 用户建议用两个工具替代
2. ✅ **P1-2**: Streamlit 报告展示/下载区域 (C10)
3. ✅ **P1-3**: Phase C 迁移 (架构一致性) - 工作量小,本次包含

### P2 (建议改进,提升质量)
1. ✅ **P2-1**: 白名单硬拦截机制 (C12) - 用户选择硬拦截
2. ⏸️ **P2-2**: 测试覆盖率提升 - 后续迭代
3. ⏸️ **P2-3**: 文档完善 - 后续迭代

### 延后任务
1. ⏸️ **P0-1**: 经验存储持久化 - 用户要求"下次再做"

---

## 二、修复任务详细设计

### 任务 1: delete_source 累计删除硬拦截 (P0-2)

**问题**: 当前 `delete_source` 操作仅触发 interrupt 警告,无硬拦截机制,存在误操作风险。

**解决方案**:
1. 在 `MaintenanceState` 新增 `delete_count: int` 字段
2. 在 `tool_node` 中 `delete_source` 执行后递增 `delete_count`
3. 当 `delete_count >= 3` 时硬拦截(直接返回错误 ToolMessage)
4. 在 `prompt.py` 增加累计删除警告说明

**涉及文件**:
- `src/agent/state.py` - 新增 `delete_count` 字段
- `src/agent/graph.py` - 在 `tool_node` 中增加计数和硬拦截逻辑
- `src/agent/prompts/prompt.py` - 增加累计删除警告

**测试**:
- 单元测试: `test_delete_count_hard_block()`
- 集成测试: 连续删除 3 个 source,验证第 3 次被硬拦截

**预计工作量**: 3 小时

---

### 任务 2: Streamlit interrupt 处理优化 (P0-3)

**问题**: Streamlit 的 rerun 模式下,interrupt 状态可能无法正确恢复,导致审批流程不稳定。

**解决方案**:
1. 利用 SqliteSaver 持久化 interrupt 状态
2. 页面刷新后,从 checkpointer 恢复 interrupt 上下文
3. 增加 interrupt 状态的 UI 提示(醒目的警告框)
4. 手动测试验证

**涉及文件**:
- `src/app_pages/maintenance.py` - 增加 interrupt 状态恢复逻辑
- `src/agent/graph.py` - 确保 interrupt 状态正确保存到 checkpointer

**测试**:
- 手动测试: 触发 interrupt,刷新页面,验证状态恢复
- 手动测试: 审批后继续执行,验证流程正确

**预计工作量**: 6 小时

---

### 任务 3: 简化轻量/全量双模式 (P1-1)

**问题**: 原设计稿中的"轻量/全量双模式"定义不清晰,用户建议简化。

**用户建议**: 用两个工具替代两个模式:
- 工具 1: 处理单个 PDF (现有工具已支持)
- 工具 2: 调用实验链路处理一个 Meal (需要新增)

**解决方案**:
1. 不实现"轻量/全量双模式"的显式切换机制
2. 新增 `process_meal` 工具,调用实验系统的批量处理链路
3. Agent 根据用户指令自主选择工具:
   - 用户说"处理这个 PDF" → 调用 `parse_pdf` + `chunk_parsed` 等单文件工具
   - 用户说"处理这个 Meal" → 调用 `process_meal` 批量工具
4. 在 prompt 中明确告知 Agent 两种工具的使用场景

**涉及文件**:
- `src/agent/tools.py` - 新增 `process_meal` 工具
- `src/agent/prompts/prompt.py` - 增加工具使用场景说明
- `src/agent/graph.py` - 增加 `process_meal` 工具节点

**测试**:
- 单元测试: `test_process_meal_tool_exists()`
- 集成测试: Agent 根据用户指令选择正确的工具

**预计工作量**: 4 小时

---

### 任务 4: Streamlit 报告展示/下载区域 (P1-2)

**问题**: Streamlit UI 缺少报告展示/下载区域,用户无法查看维修报告和对比报告。

**解决方案**:
1. 在主区域增加报告展示区域(Markdown 渲染)
2. 增加下载按钮(.md 文件)
3. 报告类型:
   - 维修报告 (`generate_maintenance_report_tool`)
   - 对比报告 (`generate_comparison_report_tool`)

**涉及文件**:
- `src/app_pages/maintenance.py` - 增加报告展示/下载 UI

**测试**:
- 手动测试: 生成报告,验证展示和下载功能

**预计工作量**: 3 小时

---

### 任务 5: Phase C 迁移 (P1-3)

**问题**: 实验系统的 `process_parsed_files()` 和 `process_parsed_files_page_aware()` 还没有迁移到共享单元,存在两套并行代码。

**现状**:
- ✅ `parse_all_pdfs_unified()` 已经调用共享单元 `parse_pdf()`
- ❌ `process_parsed_files()` 和 `process_parsed_files_page_aware()` 还没有迁移

**解决方案**:
1. 修改 `process_parsed_files()` 内部调用 `chunk_parsed()` 共享单元
2. 修改 `process_parsed_files_page_aware()` 内部调用 `chunk_parsed()` 共享单元
3. 确保行为一致性(输入输出格式不变)
4. 运行全量测试确认无回归

**涉及文件**:
- `src/chunker.py` - 修改 `process_parsed_files()` 和 `process_parsed_files_page_aware()`
- `src/core/ops/chunk.py` - 确保 `chunk_parsed()` 接口完整

**测试**:
- 运行现有测试: `tests/test_chunker.py`, `tests/test_pipeline.py`
- 运行全量测试: `pixi run test`

**预计工作量**: 4 小时

---

### 任务 6: 白名单硬拦截机制 (P2-1)

**问题**: 当前白名单为"软拦截"(触发 interrupt),LLM 可能通过组合合法工具绕过。

**解决方案**:
1. 定义 `FORBIDDEN_OPERATIONS` 集合(硬拦截):
   - `DROP` 相关操作
   - `DELETE` 全量操作
   - 其他危险操作
2. 在 `tool_node` 中检查并直接拒绝,不触发 interrupt
3. 返回错误 ToolMessage,告知用户操作被禁止

**涉及文件**:
- `src/agent/graph.py` - 增加硬拦截检查逻辑
- `src/agent/prompts/prompt.py` - 增加禁止操作说明

**测试**:
- 单元测试: `test_forbidden_operations_hard_block()`
- 集成测试: 尝试执行禁止操作,验证被硬拦截

**预计工作量**: 3 小时

---

## 三、实施计划

### Sprint 1: P0 问题修复 (预计 9 小时)

**目标**: 修复核心功能缺陷

**任务清单**:
1. ✅ 任务 1: delete_source 累计删除硬拦截 (3 小时)
2. ✅ 任务 2: Streamlit interrupt 处理优化 (6 小时)

**验收标准**:
- 连续删除 3 个 source 时,第 3 次被硬拦截
- Streamlit interrupt 状态在页面刷新后正确恢复
- 手动测试通过

---

### Sprint 2: P1 功能增强 (预计 11 小时)

**目标**: 提升用户体验和架构一致性

**任务清单**:
1. ✅ 任务 3: 简化轻量/全量双模式 (4 小时)
2. ✅ 任务 4: Streamlit 报告展示/下载区域 (3 小时)
3. ✅ 任务 5: Phase C 迁移 (4 小时)

**验收标准**:
- Agent 能根据用户指令选择正确的工具(单文件 vs 批量)
- Streamlit UI 能展示和下载报告
- 实验系统迁移到共享单元,全量测试通过

---

### Sprint 3: P2 质量提升 (预计 3 小时)

**目标**: 提升代码质量

**任务清单**:
1. ✅ 任务 6: 白名单硬拦截机制 (3 小时)

**验收标准**:
- 禁止操作被硬拦截,不触发 interrupt
- 单元测试和集成测试通过

---

## 四、总工作量评估

| Sprint | 任务数 | 预计工作量 | 风险等级 |
|--------|--------|------------|----------|
| Sprint 1 | 2 | 9 小时 | 中等 (Streamlit interrupt 处理) |
| Sprint 2 | 3 | 11 小时 | 低 (功能增强) |
| Sprint 3 | 1 | 3 小时 | 低 (硬拦截逻辑简单) |
| **总计** | **6** | **23 小时** | **中等** |

**建议**: 分 3 个 Sprint 完成,每个 Sprint 1-2 天。

---

## 五、风险评估

### 高风险项
1. ⚠️ **Streamlit interrupt 处理优化**: 涉及架构调整,可能引入新问题
   - 缓解措施: 充分手动测试,保留回退方案

### 中风险项
1. ⚠️ **Phase C 迁移**: 可能影响实验系统现有功能
   - 缓解措施: 运行全量测试,确保无回归

### 低风险项
1. ✅ **delete_source 累计删除硬拦截**: 逻辑简单,风险低
2. ✅ **白名单硬拦截**: 逻辑简单,风险低
3. ✅ **简化轻量/全量双模式**: 新增工具,不影响现有功能
4. ✅ **Streamlit 报告展示**: 纯 UI 增强,风险低

---

## 六、验收标准

### 功能验收
1. ✅ delete_source 累计删除 3 次后被硬拦截
2. ✅ Streamlit interrupt 状态在页面刷新后正确恢复
3. ✅ Agent 能根据用户指令选择正确的工具(单文件 vs 批量)
4. ✅ Streamlit UI 能展示和下载报告
5. ✅ 实验系统迁移到共享单元,全量测试通过
6. ✅ 禁止操作被硬拦截

### 质量验收
1. ✅ 所有新增代码有单元测试覆盖
2. ✅ 全量测试通过 (`pixi run test`)
3. ✅ Lint 检查通过 (`pixi run lint`)

---

## 七、后续迭代计划

### 下一版本 (v0.2.x)
1. ⏸️ 经验存储持久化 (P0-1)
2. ⏸️ 测试覆盖率提升 (P2-2)
3. ⏸️ 文档完善 (P2-3)

### 未来版本
1. 探索更智能的经验检索方式(语义搜索)
2. 优化 LLM 决策质量(提示词工程)
3. 支持更多解析器和分块策略

---

## 八、总结

本修复计划共包含 6 个任务,预计总工作量 23 小时,分 3 个 Sprint 完成。

**核心修复**:
1. delete_source 累计删除硬拦截
2. Streamlit interrupt 处理优化

**功能增强**:
1. 简化轻量/全量双模式(用两个工具替代)
2. Streamlit 报告展示/下载
3. Phase C 迁移(实验系统迁移到共享单元)

**质量提升**:
1. 白名单硬拦截机制

**延后任务**:
1. 经验存储持久化(用户要求"下次再做")

**风险控制**:
- 高风险项(Streamlit interrupt)充分测试
- 中风险项(Phase C 迁移)运行全量测试
- 低风险项快速完成

**验收标准**:
- 功能验收: 6 项核心功能全部通过
- 质量验收: 单元测试 + 全量测试 + Lint 检查全部通过
