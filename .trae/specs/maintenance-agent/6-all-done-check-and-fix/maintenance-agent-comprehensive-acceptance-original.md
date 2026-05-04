# 维修工 Agent 全面验收计划

> 日期：2026-05-05
> 范围：Phase 0 ~ Phase 3 全量验收 + 打扫卫生 + 设计缺陷修复
> 黄金基准：`0-initial-plans/maintenance-agent-research-plan.md` + `0-initial-plans/maintenance-agent-checklist.md`
> 补充输入：`maintenance-agent-issue-fix-plan.md`（另一对话的设计缺陷分析）

---

## 一、验收策略

### 我来做的（自动化可验证）

1. **运行测试基线**：`pixi run test` + `pixi run lint`，确认当前状态
2. **逐 Phase 对照 checklist 验证代码实现**：读取源码，逐条核对
3. **修复设计缺陷**（来自另一对话的 issue fix plan）：
   - P0-1: 连续 delete_source 无限制 → 加 delete_count 计数器
   - P0-2: 阶段守卫缺失 → 加 DIAGNOSIS_TOOLS/REPAIR_TOOLS 守卫
   - P0-3: 报告工具依赖 LLM 传参 → 改为从 checkpointer 读 state
   - P1-1: 轻量/全量双模式 → 加 mode 字段 + prompt 注入 + CLI/Streamlit 切换
   - P1-2: Phase C 迁移 → parse_all_pdfs_unified() 走 parse_pdf() 共享单元
4. **补充缺失测试**：CLI review 空壳测试等
5. **代码质量审查**：try/except 覆盖、loguru 使用、硬编码配置值

### 需要用户做的（体验/判断类）

1. **Streamlit 页面实际体验**：interrupt 处理是否可用、对话是否流畅
2. **Agent 决策质量**：LLM 是否真的能自主选择合适的工具
3. **维修报告可读性**：生成的 Markdown 报告是否对人有价值
4. **P1-3 TypedDict 迁移**：是否值得冒风险做（需要 spike 验证 LangGraph 兼容性）
5. **P1-4 Streamlit interrupt 修复**：是否需要现在修（涉及架构重构）
6. **P1-5 经验持久化**：是否需要 SQLite 持久化（当前 InMemoryStore 重启丢失）

---

## 二、验收 + 修复步骤

### Step 1: 基线确认

- [ ] `pixi run test` 全量通过
- [ ] `pixi run lint` 通过
- [ ] 记录测试数量基线

### Step 2: Phase 0~3 逐条验证（只读）

对照 checklist 0-3 ~ 0-10 + Phase 1~3 spec，逐条验证代码实现。
此步骤只做验证，不做修改，产出验证报告。

### Step 3: 已知问题复查（勘误 1-17）

验证 Phase 3 acceptance plan 中声称已修复的勘误项是否确实修复。

### Step 4: 修复 P0-1 — 连续 delete_source 安全策略

- [ ] `state.py` 新增 `delete_count: int` 字段
- [ ] `graph.py` tool_node 中 delete_source 执行后递增 delete_count
- [ ] `delete_count >= 3` 时自动 interrupt 展示累计警告
- [ ] `prompt.py` 增加连续删除警告说明
- [ ] `cli.py` / `maintenance.py` 同步 delete_count
- [ ] 新增测试

### Step 5: 修复 P0-2 — 阶段守卫

- [ ] `graph.py` tool_node 中定义 DIAGNOSIS_TOOLS / REPAIR_TOOLS 集合
- [ ] 未调用任何诊断工具时，修复工具调用被拒绝
- [ ] 拒绝消息引导 LLM 先进行诊断
- [ ] 新增测试

### Step 6: 修复 P0-3 — 报告工具从 checkpointer 读 state

- [ ] `tools.py` 报告工具签名改为接收 thread_id
- [ ] 内部通过 checkpointer 获取完整 state
- [ ] `reporters/maintenance_report.py` 改为接收 MaintenanceState
- [ ] `graph.py` tool_node 注入 thread_id
- [ ] `prompt.py` 更新报告工具说明
- [ ] 更新测试

### Step 7: 修复 P1-1 — 轻量/全量双模式

- [ ] `state.py` 新增 `mode: str` 字段
- [ ] `prompt.py` build_system_prompt 根据 mode 注入不同指导
- [ ] `cli.py` 新增 `--full` 参数 + `:mode` 指令
- [ ] `maintenance.py` 侧边栏模式切换
- [ ] `config.yaml` 新增 mode 默认值
- [ ] 新增测试

### Step 8: 修复 P1-2 — Phase C 迁移

- [ ] 验证 parse_pdf() 与 ParserRegistry.get() 行为一致性
- [ ] 修改 parse_all_pdfs_unified() 调用 parse_pdf() 共享单元
- [ ] 运行全量测试确认无回归

### Step 9: 代码质量深度审查 + 小修小补

- [ ] 所有 @tool 包含 try/except + loguru 日志
- [ ] 所有 IO 操作有异常处理
- [ ] 无硬编码配置值
- [ ] VectorIndexer 实例使用 try/finally
- [ ] 无 print 语句
- [ ] P2-1: execution_log 增加时间戳
- [ ] P2-2: SqliteSaver 启用 WAL 模式
- [ ] P1-6: 移除 _agent_store 全局变量

### Step 10: 回归验证

- [ ] `pixi run test` 全量通过
- [ ] `pixi run lint` 通过

### Step 11: 用户验收项交接

整理需要人工判断的项目清单交给用户。

---

## 三、验收产出

1. **验证报告**：每个 checklist 项的实际验证结果
2. **Bug 修复**：P0-1 ~ P1-2 + P2-x 的代码修复和提交
3. **用户验收清单**：需要人工判断的项目列表
4. **更新 checklist**：同步验证结果
