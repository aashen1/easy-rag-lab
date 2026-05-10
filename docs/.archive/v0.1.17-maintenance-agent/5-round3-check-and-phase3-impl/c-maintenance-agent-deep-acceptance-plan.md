# 维修工 Agent 深度验收计划

> 日期：2026-05-05
> 角色：软件验收人员
> 目标：对 AI 生成的 maintenance-agent 功能进行深度验收，挑出需求走样、风格漂移、隐藏 bug

---

## 一、验收方法论

作为验收人员，我的思路是**从四个维度交叉审查**，而不是简单地逐条对照 checklist：

| 维度 | 关注点 | 方法 |
|------|--------|------|
| **需求忠实度** | 实现是否偏离了用户原始需求？Spec 是否被正确理解？ | 原始需求 → Spec → 代码 三层对照 |
| **代码正确性** | 代码是否真的能跑？有没有隐藏 bug？ | 逐文件代码审查 + 边界条件推演 |
| **风格一致性** | 是否遵循项目既有规范？AI 是否引入了不协调的代码风格？ | 与项目既有代码对比 |
| **架构合理性** | 设计决策是否合理？有没有过度工程或欠工程？ | 架构审查 + 设计决策溯源 |

---

## 二、已发现的问题清单（按严重度排序）

### 🔴 P0 — 必须修复的 Bug / 严重偏差

#### P0-1: `create_meal_manual()` 的 `creation_mode` 未写入 manifest

- **文件**: `src/meal/manager.py` L635
- **问题**: `meal_config.creation_mode = "manual"` 在 `_build_pipeline()` 返回后才设置，但 `_build_pipeline()` 内部已将 MealConfig 序列化写入 manifest.json。manifest 中 `creation_mode` 仍然是 `"random"`
- **影响**: 手动创建的 meal 加载后 `creation_mode` 为 `"random"`，该字段完全失效，无法区分手动/随机 meal
- **验证方式**: 创建一个手动 meal → 读取其 manifest.json → 检查 `creation_mode` 字段

#### P0-2: CLI 每轮对话丢失非 messages 状态

- **文件**: `src/agent/cli.py` L77-87
- **问题**: 每次用户输入都创建全新的 state dict，`execution_log`、`stage_history`、`auto_review` 等非 messages 字段不跨轮次保持
- **影响**: 用户开启 `auto_review` 后，下一轮输入时状态被重置；`stage_history` 永远只有当前轮的工具名，无法实现真正的"回退感知"
- **验证方式**: 启动 agent → 执行一个工具 → 检查下一轮 state 中 stage_history 是否保留

#### P0-3: 经验自动保存逻辑保存的是"空壳经验"

- **文件**: `src/agent/graph.py` L270-292
- **问题**: 只要执行了 `parse_pdf_tool` 或 `chunk_parsed_tool` 就自动保存经验，但保存的经验中 `best_parser`、`best_chunk_strategy`、`best_chunk_size` 全是 `None`，只有 `tools_used` 和 `reason` 有值
- **影响**: 这些"空壳经验"被注入后续 prompt，占用上下文窗口但不提供有用信息，反而可能误导 LLM
- **验证方式**: 执行一次 parse → 检查保存的经验结构

### 🟡 P1 — 应该修复的功能缺陷 / 规范违反

#### P1-1: `MaintenanceState` 类型注解无效

- **文件**: `src/agent/state.py`
- **问题**: 继承 `dict` 而非使用 `TypedDict`，类体中的属性注解只是类级别类型提示，不会创建实例属性，也不做类型检查
- **影响**: IDE 无法提供类型提示，mypy 无法检查，测试中创建 state 需手动传入全部 9 个字段
- **对比**: LangGraph 官方推荐 `TypedDict`

#### P1-2: `approval_node` 无单元测试

- **文件**: `src/agent/graph.py` L140-210
- **问题**: 这是安全关键节点（高风险操作审批），但完全没有测试
- **影响**: 之前验收已发现拒绝操作后崩溃的 bug（3a-bugfix 报告），说明此节点容易出问题

#### P1-3: `_route_after_approval` 无单元测试

- **文件**: `src/agent/graph.py` L212-230
- **问题**: 路由逻辑未覆盖测试
- **影响**: 与 P1-2 同理，关键路径缺乏保障

#### P1-4: config.yaml 中 `agent.defaults.collection_name` 与 meal 系统冲突

- **文件**: `config.yaml` L377
- **问题**: meal 系统使用 `generate_collection_name()` 生成带 `m_` 前缀的集合名，agent 默认使用硬编码 `"financial_reports"`，可能导致 agent 操作不属于任何 meal 的集合
- **影响**: 数据一致性风险

#### P1-5: `query.py` 共享单元缺少异常处理

- **文件**: `src/core/ops/query.py`
- **问题**: 31 行代码只是 `pipeline.query(question)` 透传，无 try/except，违反项目规范"所有 IO 操作必须有 try/except"
- **对比**: `parse.py` 已在 Phase 2 补全了 try/except，`query.py` 遗漏

#### P1-6: `enhance_page()` / `enhance_table()` 单页操作却遍历全 PDF

- **文件**: `src/parsers/pdfplumber_enhancer.py` L163-235
- **问题**: 调用 `_extract_all_tables(pdf_path, page_number)` 时，内部仍遍历所有页面。对于大 PDF，只增强一页却要遍历全部
- **影响**: 性能浪费，大 PDF（100+ 页）场景明显

#### P1-7: `TestCLIReviewCommand` 是空壳测试

- **文件**: `tests/test_agent.py` L933-938
- **问题**: 两个测试方法只有 `assert True`，完全没有测试逻辑
- **影响**: `:review on/off` 功能无测试保障

#### P1-8: `search_experiences()` 是死代码

- **文件**: `src/agent/memory/experience_store.py`
- **问题**: graph.py 中只用了 `get_all_experiences`，`search_experiences` 方法从未被调用
- **影响**: 死代码增加维护负担

#### P1-9: `evaluate_single()` 的 Jaccard 指标对中文不友好

- **文件**: `src/core/ops/evaluate.py`
- **问题**: `_word_overlap` 按空格分词，中文句子会被当作一个整体 token
- **影响**: 评测指标对中文内容完全失真，Agent 基于失真指标做决策可能误判

#### P1-10: `get_agent_default()` 每次调用都读配置文件

- **文件**: `src/agent/config.py`
- **问题**: 无缓存，`chunk_parsed_tool` 一次调用读 3 次配置文件
- **影响**: 不必要的 IO 开销

### 🟢 P2 — 建议改进 / 风格漂移

#### P2-1: `tools.py` 874 行单文件过长

- **文件**: `src/agent/tools.py`
- **问题**: 19 个 tool + 辅助函数挤在一个文件中，远超项目其他模块的文件长度
- **对比**: 项目既有模块通常 200-400 行
- **建议**: 拆分为 `parse_tools.py`, `index_tools.py`, `meal_tools.py`, `issue_tools.py`

#### P2-2: 大量延迟导入说明模块结构有问题

- **文件**: `src/agent/tools.py`
- **问题**: 至少 20+ 处 `from src.xxx import yyy` 散布在函数体内，为避免循环依赖
- **影响**: 代码可读性差，IDE 无法正确解析依赖

#### P2-3: `_backup_to_trashbin` 用 copy 而非 move

- **文件**: `src/agent/tools.py` L48
- **问题**: 使用 `shutil.copytree` / `shutil.copy2`，但项目规范要求"移入 `.trashbin/`"而非复制
- **影响**: 备份后原始文件仍存在，不是真正的"安全删除"

#### P2-4: `_backup_to_trashbin` 缺少 docstring

- **文件**: `src/agent/tools.py` L48
- **问题**: 违反项目规范"公共函数须包含功能描述"

#### P2-5: 经验系统缺少淘汰机制

- **文件**: `src/agent/memory/experience_store.py`
- **问题**: 经验只增不减，长时间运行后 namespace 下积累大量经验，全部注入 prompt 会超出上下文窗口

#### P2-6: `_infer_pdf_type` 过于简单

- **文件**: `src/agent/graph.py` L81-87
- **问题**: 仅通过"年报"/"研报"关键词判断，无法覆盖英文文件名或无特征文件名

#### P2-7: `SYSTEM_PROMPT` 全局变量多余

- **文件**: `src/agent/prompt.py` L89
- **问题**: 模块加载时调用 `build_system_prompt()`，此时 stage_history 和 experiences 始终为 None。实际 graph 中用动态调用，全局变量只在测试中使用

#### P2-8: `creation_mode` 缺少值约束

- **文件**: `src/meal/models.py` L38
- **问题**: 自由字符串而非 `Literal["random", "manual"]`，可能导致拼写错误

#### P2-9: `upsert_chunks()` 幂等性缺失未在 docstring 中说明

- **文件**: `src/indexer.py` L301-371
- **问题**: 每次调用生成新 UUID，相同数据多次 upsert 会产生重复点，但 docstring 未说明调用方需先 delete

#### P2-10: `update_manifest_entry()` 回滚逻辑实际无效

- **文件**: `src/meal/cache.py` L348-350
- **问题**: 回滚的是局部变量 manifest dict，方法返回后即丢失，不是真正的回滚

---

## 三、需求走样分析

### 走样 1: Spec 设计了多节点架构，实际实现为 ReAct 单节点

- **Spec 规划**: `parse_node`, `chunk_node`, `embed_node` 等独立节点 + `Command(goto=...)` 跳转
- **实际实现**: 所有工具在 `tool_node` 统一执行，agent_node 每次重新决策
- **偏差理由**: Phase 2 plan 中有明确的设计决策记录，认为 ReAct 模式下不需要 Command(goto=...)
- **验收判断**: **可接受的架构简化**，但应在 Spec 中更新，避免后续开发者按旧 Spec 理解

### 走样 2: Spec 要求"白名单硬拦截"，实际仅靠 interrupt + 提示词

- **Spec 要求**: "系统 SHALL 维护一个危险操作白名单，禁止删除整个 Qdrant collection"
- **实际实现**: `FORBIDDEN_OPERATIONS` 集合 + `HIGH_RISK_TOOLS` + interrupt 审批
- **偏差程度**: 中等。LLM 仍可通过组合合法工具达到类似效果（如先 delete_source 逐个删除）
- **验收判断**: **部分可接受**，但应在 Spec 中明确标注"软拦截"而非"硬拦截"

### 走样 3: Spec 要求"轻量/全量双模式"，实际未实现

- **Spec 要求**: `--full` 参数切换模式
- **实际实现**: 无模式切换
- **偏差程度**: 高。这是 C6 核心能力需求
- **验收判断**: **不可接受**，至少应实现 CLI 参数

### 走样 4: Spec 要求"维修报告 + 对比报告"，实际未实现

- **Spec 要求**: 维修报告保存到 `data/maintenance_reports/`
- **实际实现**: 无报告生成
- **偏差程度**: 高。这是 C9 核心能力需求
- **验收判断**: Phase 3 范围，当前验收可暂缓，但 Spec 应标注未实现

### 走样 5: Spec 要求"Streamlit 维修工页面"，实际未实现

- **Spec 要求**: Web UI 优先
- **实际实现**: 仅 CLI
- **偏差程度**: 高。这是 C10 核心能力需求
- **验收判断**: Phase 3 范围，当前验收可暂缓

---

## 四、风格漂移分析

### 漂移 1: `MaintenanceState` 继承 `dict` 而非 `TypedDict`

- **项目既有风格**: 使用 `dataclass` 或 `TypedDict` 定义数据结构（如 `MealConfig`, `ParseResult`）
- **Agent 引入风格**: 继承 `dict` + 类级别类型注解
- **影响**: 与项目风格不一致，类型注解无效

### 漂移 2: 全局可变状态 `_agent_store`

- **项目既有风格**: 避免全局可变状态，使用依赖注入或工厂函数
- **Agent 引入风格**: 模块级全局变量 + `global` 修改
- **影响**: 测试困难（需手动恢复原始值），线程不安全

### 漂移 3: Issue 工具使用 subprocess 调用 CLI

- **项目既有风格**: Python 模块间直接调用 API
- **Agent 引入风格**: `subprocess.run(["pixi", "run", "issue", ...])`
- **影响**: 低效、脆弱（CLI 输出格式变化即失败）、难以测试

### 漂移 4: 备份机制用 copy 而非 move

- **项目既有风格**: `.trashbin/` 规则明确要求"移入"（mv），不是复制
- **Agent 引入风格**: `shutil.copytree` / `shutil.copy2`
- **影响**: 与项目规范不一致

---

## 五、验收执行步骤

> **⚠️ 并行开发约束**：Phase 3 正在另一个 worktree 中实现，涉及以下文件：
> - `src/agent/cli.py`, `src/agent/graph.py`, `src/agent/state.py`, `src/agent/prompt.py`, `src/agent/config.py`, `config.yaml`, `src/app.py`, `src/parser.py`
> - 新建 `src/agent/checkpoint.py`, `src/agent/reporters/`, `src/app_pages/maintenance.py` 等
>
> **本验收只修改不与 Phase 3 冲突的文件**，冲突文件的问题记录为"待 Phase 3 合并后修复"。

### Step 1: 自动化基线确认（只读）
- `pixi run test` 全量通过
- `pixi run lint` 通过

### Step 2: P0 Bug 验证与修复

| Bug | 涉及文件 | 是否与 Phase 3 冲突 | 处理策略 |
|-----|---------|-------------------|---------|
| P0-1 `creation_mode` 未写入 manifest | `src/meal/manager.py` | ❌ 不冲突 | ✅ 本轮修复 |
| P0-2 CLI 状态丢失 | `src/agent/cli.py` | ⚠️ 冲突 | 📋 记录，Phase 3 T1(SqliteSaver)+T3(CLI增强) 会重构 cli.py，届时一并修复 |
| P0-3 空壳经验 | `src/agent/graph.py` | ⚠️ 冲突 | 📋 记录，Phase 3 T7(提示词优化) 可能涉及，待合并后修复 |

**本轮实际修复**：仅 P0-1

### Step 3: P1 功能缺陷修复

| 缺陷 | 涉及文件 | 是否与 Phase 3 冲突 | 处理策略 |
|------|---------|-------------------|---------|
| P1-1 `MaintenanceState` 改 TypedDict | `src/agent/state.py` | ⚠️ 冲突（T4 会新增字段） | 📋 记录，待 Phase 3 合并后统一重构 |
| P1-2/P1-3 approval_node 测试 | `tests/test_agent.py` | ⚠️ 可能冲突 | ✅ 新增测试文件 `tests/test_agent_approval.py`，避免修改现有测试 |
| P1-4 `collection_name` 冲突 | `config.yaml`, `src/agent/tools.py` | ⚠️ config.yaml 冲突 | 📋 记录，待 Phase 3 合并后修复 |
| P1-5 `query.py` 异常处理 | `src/core/ops/query.py` | ❌ 不冲突 | ✅ 本轮修复 |
| P1-6 `enhance_page` 性能 | `src/parsers/pdfplumber_enhancer.py` | ❌ 不冲突 | ✅ 本轮评估+修复 |
| P1-7 CLI review 空壳测试 | `tests/test_agent.py` | ⚠️ 可能冲突 | 📋 记录，Phase 3 T3 会重写 CLI |
| P1-8 `search_experiences` 死代码 | `src/agent/memory/experience_store.py` | ❌ 不冲突 | ✅ 本轮标注 |
| P1-9 `evaluate_single` 中文分词 | `src/core/ops/evaluate.py` | ❌ 不冲突 | ✅ 本轮修复 |
| P1-10 `get_agent_default` 缓存 | `src/agent/config.py` | ⚠️ 冲突 | 📋 记录，待 Phase 3 合并后修复 |

**本轮实际修复**：P1-5, P1-6, P1-8, P1-9 + P1-2/P1-3（新建测试文件）

### Step 4: P2 风格改进（本轮不执行）
- 全部推迟到 Phase 3 合并后，避免冲突

### Step 5: Spec 更新（只修改 spec 文件，不冲突）
- 将架构简化决策（ReAct vs 多节点）更新到 Spec
- 标注"软拦截"而非"硬拦截"
- 标注未实现的 Phase 3 功能

### Step 6: 回归验证
- `pixi run test` 全量通过
- `pixi run lint` 通过

---

## 六、本轮修复范围总结

### ✅ 本轮修复（不与 Phase 3 冲突）

| 编号 | 修复项 | 涉及文件 |
|------|--------|---------|
| P0-1 | `creation_mode` 未写入 manifest | `src/meal/manager.py` |
| P1-2/3 | approval_node + route_after_approval 测试 | 新建 `tests/test_agent_approval.py` |
| P1-5 | `query.py` 异常处理 | `src/core/ops/query.py` |
| P1-6 | `enhance_page` 性能优化 | `src/parsers/pdfplumber_enhancer.py` |
| P1-8 | `search_experiences` 死代码标注 | `src/agent/memory/experience_store.py` |
| P1-9 | `evaluate_single` 中文分词 | `src/core/ops/evaluate.py` |

### 📋 记录待 Phase 3 合并后修复

| 编号 | 问题 | 原因 |
|------|------|------|
| P0-2 | CLI 状态丢失 | Phase 3 T1+T3 会重构 cli.py |
| P0-3 | 空壳经验 | Phase 3 T7 会优化 graph.py |
| P1-1 | MaintenanceState 改 TypedDict | Phase 3 T4 会新增字段 |
| P1-4 | collection_name 冲突 | Phase 3 会修改 config.yaml |
| P1-7 | CLI review 空壳测试 | Phase 3 T3 会重写 CLI |
| P1-10 | config 缓存 | Phase 3 会修改 config.py |

---

## 七、验收结论标准

| 条件 | 判定 |
|------|------|
| P0-1 修复 + P1 本轮 4 项修复 + 测试全通过 | ✅ 验收通过（附带待合并后修复清单） |
| P0-1 未修复 | ❌ 验收不通过 |
