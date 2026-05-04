# 维修工 Agent 全面验收计划

> 日期：2026-05-05
> 范围：Phase 0 ~ Phase 3 全量验收 + 打扫卫生
> 黄金基准：`0-initial-plans/maintenance-agent-research-plan.md` + `0-initial-plans/maintenance-agent-checklist.md`

---

## 一、验收策略

### 我来做的（自动化可验证）

1. **运行测试基线**：`pixi run test` + `pixi run lint`，确认当前状态
2. **逐 Phase 对照 checklist 验证代码实现**：读取源码，逐条核对 checklist 中的 ✅/⚠️/❌ 项
3. **修复可自动验证的 bug**：空壳经验、缓存问题、代码质量问题
4. **补充缺失测试**：CLI review 空壳测试等
5. **代码质量审查**：try/except 覆盖、loguru 使用、硬编码配置值

### 需要用户做的（体验/判断类）

1. **Streamlit 页面实际体验**：interrupt 处理是否可用、对话是否流畅
2. **Agent 决策质量**：LLM 是否真的能自主选择合适的工具
3. **维修报告可读性**：生成的 Markdown 报告是否对人有价值
4. **轻量/全量模式需求确认**：是否真的需要显式切换

---

## 二、验收步骤（按 Phase 增序）

### Step 1: 基线确认

- [ ] `pixi run test` 全量通过
- [ ] `pixi run lint` 通过
- [ ] 记录测试数量基线

### Step 2: Phase 0 验收 — 共享单元层 + 基础设施

对照 checklist 0-3 ~ 0-10，验证：

- [ ] `src/core/ops/` 6 个共享单元函数存在且可调用
- [ ] `parse_pdf()` / `enhance_page()` / `enhance_table()` 有 try/except + loguru
- [ ] `chunk_parsed()` 支持 fixed/page_aware/semantic 三种策略
- [ ] `embed_chunks()` / `index_chunks()` / `delete_source_and_reindex()` 正确包装
- [ ] `query_rag()` 包装 RAGPipeline.query()
- [ ] `evaluate_single()` 实现基础指标
- [ ] `VectorIndexer.delete_by_source()` / `upsert_chunks()` / `scroll_by_source()` 已实现
- [ ] `ArtifactCache.update_manifest_entry()` 原子性更新
- [ ] `MealConfig.creation_mode` 字段 + `create_meal_manual()`
- [ ] `PdfPlumberEnhancer.enhance_page()` / `enhance_table()` 单页/单表格增强
- [ ] `ParserRegistry.get_enhancer()` 方法
- [ ] Anthropic 认证适配 `create_langchain_anthropic_client()`
- [ ] `config.yaml` agent 配置段
- [ ] `src/agent/config.py` 配置加载

### Step 3: Phase 1 验收 — Agent MVP

对照 checklist 0-6，验证：

- [ ] `MaintenanceState` TypedDict 定义完整（messages, current_meal, current_source, diagnosis, pending_action, approved, execution_log, stage_history, auto_review, locked_tool, locked_tool_args）
- [ ] `agent_node` 调用 LLM with tools bound
- [ ] `approval_node` 检查 HIGH_RISK_TOOLS + interrupt
- [ ] `tool_node` 执行 tool_calls + 更新 stage_history + 保存经验
- [ ] 条件边路由 `should_continue()` / `_route_after_approval()` 正确
- [ ] 系统提示词 `build_system_prompt()` 动态构建
- [ ] 8 安全工具 + 3 高风险工具（Phase 1 原始）存在
- [ ] CLI 入口 `pixi run agent` 可启动

### Step 4: Phase 2 验收 — 扩展能力

对照 checklist 0-1.2 ~ 0-1.12 及 Phase 2 spec，验证：

- [ ] 全链路 @tool 共 20 个（8 原始 + 9 新增 + 2 报告 + 1 锁定相关）
- [ ] `stage_history` 回退感知：tool_node 更新 + 提示词注入
- [ ] `auto_review` 人工干预增强：CLI `:review on/off`
- [ ] `ExperienceStore` 经验积累：save/search/get_all
- [ ] Issue 系统集成：create/list/close 3 个 @tool
- [ ] 安全备份机制：写操作前备份到 `.trashbin/`
- [ ] `FORBIDDEN_OPERATIONS` 硬拦截 + `HIGH_RISK_TOOLS` 软拦截
- [ ] LLM 客户端 `lru_cache` 缓存

### Step 5: Phase 3 验收 — UI + 报告 + 生产化

对照 Phase 3 plan T1-T8，验证：

- [ ] T1: `SqliteSaver` 持久化 — `src/agent/checkpoint.py` + CLI `--session-id` / `--pdf`
- [ ] T2: 维修报告 `MaintenanceReporter` + 对比报告 `ComparisonReporter`
- [ ] T3: CLI 指令 — `:parse` / `:back` / `:compare` / `:report` / `:history` / `:status`
- [ ] T4: 工具链锁定 — `locked_tool` / `locked_tool_args` + agent_node 跳过 LLM
- [ ] T6: Streamlit 维修工页面 — `src/app_pages/maintenance.py` + `app.py` Tab 注册
- [ ] T7: 系统提示词优化 — 示例/约束/错误处理指导
- [ ] T8: Phase C 迁移 — `parse_all_pdfs_unified()` 是否调用 `parse_pdf()` 共享单元

### Step 6: 已知问题复查

对照 Phase 3 acceptance plan 中的勘误 1-17，验证已修复项：

- [ ] 勘误 10: 空壳经验自动保存 — 是否已从 tool_call args 提取实际参数
- [ ] 勘误 11: ComparisonReporter 推荐逻辑 — 是否支持 lower-is-better 指标
- [ ] 勘误 14: locked_tool 冗余 prompt — 是否已移除
- [ ] 勘误 15: CLI review 空壳测试 — 是否已补充实际测试
- [ ] 勘误 16: config 读取缓存 — `get_agent_config()` 是否有 `lru_cache`
- [ ] 勘误 17: `_get_tool_names` 清缓存 — 是否已移除 `cache_clear()`

### Step 7: 代码质量深度审查

- [ ] 所有 @tool 包含 try/except + loguru 日志
- [ ] 所有 IO 操作有异常处理
- [ ] 无硬编码配置值（应从 config.yaml 读取）
- [ ] VectorIndexer 实例使用 try/finally 确保 close()
- [ ] 无 `print` 语句（应使用 loguru）
- [ ] 公共函数有 docstring

### Step 8: 修复可自动验证的问题

根据验收发现，修复以下类型的问题：
- 空壳测试补充
- 缺失 try/except
- 硬编码配置值
- 缓存问题
- 代码规范问题

### Step 9: 用户验收项交接

将以下需要人工判断的项目整理成清单，交给用户：
- Streamlit 页面实际操作体验
- Agent 决策质量（给一个 PDF，看 Agent 是否能正确诊断）
- 维修报告可读性
- 轻量/全量模式是否需要
- 白名单硬拦截是否需要加强

---

## 三、验收产出

1. **验收报告**：记录每个 checklist 项的实际验证结果
2. **Bug 修复**：可自动验证的问题直接修复并提交
3. **用户验收清单**：需要人工判断的项目列表
4. **更新 checklist**：将验证结果同步到 `0-initial-plans/maintenance-agent-checklist.md`
