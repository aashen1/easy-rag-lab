# 维修工 Agent 验收计划

> 日期：2026-05-04
> 分支：`agent-maintainer`
> 基于：implementation-report.md + spec.md + tasks.md + checklist.md + 实际代码审查

---

## 一、做了哪些可用的东西？（直白总结）

### 1.1 共享操作层 `src/core/ops/`（6 个子模块）

这是一组"薄包装"函数，把 RAG 管线各环节封装成独立可调用的纯函数：

| 函数 | 干什么 |
|------|--------|
| `parse_pdf()` | 解析 PDF，支持选择解析器+增强器组合 |
| `enhance_page()` | 对单页做表格增强（1-indexed） |
| `enhance_table()` | 对单页的单个表格做增强（1-indexed） |
| `chunk_parsed()` | 按策略分块（fixed/page_aware/semantic），预留了父子块接口 |
| `embed_chunks()` | 对 chunks 列表生成嵌入向量 |
| `index_chunks()` | 创建 collection → 嵌入 → 索引 |
| `delete_source_and_reindex()` | 按源删除旧向量 → 嵌入新块 → 增量 upsert |
| `query_rag()` | 执行 RAG 查询 |
| `evaluate_single()` | 评估回答质量（Phase A：仅用 Jaccard 词重叠，不用 LLM） |

### 1.2 现有模块扩展

| 模块 | 新增了什么 |
|------|-----------|
| `PdfPlumberEnhancer` | `enhance_page()` 单页增强 + `enhance_table()` 单表格增强 |
| `ParserRegistry` | `get_enhancer()` 获取增强器实例 |
| `VectorIndexer` | `delete_by_source()` 按 source 删向量 + `upsert_chunks()` 增量插入 |
| `MealConfig` | `creation_mode` 字段（"random" / "manual"） |
| `MealManager` | `create_meal_manual()` 手动创建 meal |
| `ArtifactCache` | `update_manifest_entry()` 增量更新 manifest |
| `llm_client.py` | `create_langchain_anthropic_client()` LangChain 客户端工厂 |

### 1.3 维修工 Agent `src/agent/`（5 个文件）

| 文件 | 干什么 |
|------|--------|
| `state.py` | 定义状态模型（消息、当前 meal、诊断结果、审批状态等） |
| `tools.py` | 11 个 @tool：8 个安全工具 + 3 个高风险工具 |
| `prompt.py` | 系统提示词（诊断→分析→修复三阶段工作流） |
| `graph.py` | LangGraph StateGraph：agent→approval→tools 循环 |
| `cli.py` | 交互式 CLI，`pixi run agent` 启动 |

**安全机制**：3 个高风险工具（rebuild_index、delete_source、update_meal）执行前会通过 `interrupt()` 暂停，等待用户确认。

### 1.4 依赖和入口

- 新增依赖：`langgraph`、`langchain-core`、`langchain-anthropic`
- CLI 入口：`pixi run agent`

---

## 二、验收思路：怎么确认做的是成功的、没 bug？

### 2.1 第一层：自动化测试（当前状态）

**现有测试**：`tests/test_agent.py` 共 22 个测试，覆盖：
- ✅ State 创建和字段访问
- ✅ HIGH_RISK_TOOLS 集合成员
- ✅ 11 个 @tool 存在性（名字+描述）
- ✅ Graph 构建、编译、checkpointer
- ✅ should_continue 路由
- ✅ 未知工具处理
- ✅ 系统提示词内容

**缺失测试**（tasks.md 明确列出但未实现）：
- ❌ `tests/test_core_ops/` 目录完全不存在
- ❌ 共享单元层 6 个子模块的单元测试（parse/chunk/embed/index/query/evaluate）
- ❌ `create_langchain_anthropic_client()` 单元测试
- ❌ `PdfPlumberEnhancer` 新方法的单元测试
- ❌ `VectorIndexer` 新方法的单元测试
- ❌ `MealManager.create_meal_manual()` 单元测试
- ❌ `ArtifactCache.update_manifest_entry()` 单元测试

### 2.2 第二层：集成/功能验证（需要手动或半自动）

| 验证项 | 方法 | 预期结果 |
|--------|------|---------|
| `pixi run test` 全量通过 | 运行命令 | 2013+ tests passed, 0 failed |
| `pixi run lint` 通过 | 运行命令 | 无错误 |
| `pixi run agent` 能启动 | 运行命令 | 显示"🔧 RAG 维修工 Agent 已启动" |
| Agent 能响应简单问题 | 输入"列出所有 meal" | 返回 meal 列表或"Error listing meals"（无数据时） |
| 高风险操作触发审批 | 触发 rebuild_index | 显示"⚠️ 高风险操作需要确认" |
| 审批拒绝后不执行 | 输入 n | 返回"用户拒绝了操作" |
| 审批通过后执行 | 输入 y | 执行操作并返回结果 |
| 退出命令 | 输入 quit/exit | 正常退出 |

### 2.3 第三层：代码质量审查

| 审查项 | 关注点 |
|--------|--------|
| 错误处理 | 所有 @tool 是否有 try/except？是否用 loguru 记录？ |
| 安全机制 | 高风险操作是否都经过 interrupt？白名单是否完整？ |
| 向后兼容 | MealConfig.creation_mode 默认值是否为 "random"？现有 create_meal() 是否不受影响？ |
| 原子性 | ArtifactCache.update_manifest_entry() 失败时 manifest 是否保持原状？ |
| 资源管理 | VectorIndexer 实例是否正确关闭（close()）？ |
| 导入风格 | 是否使用懒导入避免循环依赖？ |

### 2.4 第四层：Spec 一致性审查

**关键偏差**（需确认是否可接受）：

| Spec 要求 | 实际实现 | 偏差程度 | 建议 |
|-----------|---------|---------|------|
| `create_meal()` 扩展参数 | 新建 `create_meal_manual()` | 低风险 | 报告已说明理由，可接受 |
| `evaluate_single()` 包装 BuiltinEvaluator | LLM-free Jaccard 指标 | 中风险 | Phase A 策略，需确认指标质量 |
| 写操作前自动备份到 `.trashbin/` | 未实现 | **高偏差** | Spec 明确要求，缺失 |
| 危险操作白名单（禁止 DROP 全量） | 仅 HIGH_RISK_TOOLS interrupt | **高偏差** | 无硬拦截，仅靠提示词约束 |
| `src/agent/config.py` 配置模块 | 未创建 | 低风险 | 配置直接在 graph.py 中读取 |
| `config.yaml` agent 配置段 | 未添加 | 低风险 | 可后续补充 |
| 轻量/全量双模式 | 未实现 | 中偏差 | Spec 明确要求 |

---

## 三、Spec/Tasks 规划的任务是否全部完成？

### Phase 0 完成度：功能 ✅ 测试 ❌

| Task | 功能代码 | 单元测试 |
|------|---------|---------|
| 0.1 依赖管理 | ✅ | N/A |
| 0.2 包结构 | ✅ | N/A |
| 0.3 parse_pdf | ✅ | ❌ `tests/test_core_ops/test_parse.py` 未创建 |
| 0.4 chunk_parsed | ✅ | ❌ `tests/test_core_ops/test_chunk.py` 未创建 |
| 0.5 query_rag | ✅ | ❌ `tests/test_core_ops/test_query.py` 未创建 |
| 0.6 evaluate_single | ✅ | ❌ `tests/test_core_ops/test_evaluate.py` 未创建 |
| 0.7 embed + index | ✅ | ❌ `tests/test_core_ops/` 下测试未创建 |
| 0.8 Anthropic 适配 | ✅ | ❌ 单元测试未创建 |
| 0.9 Enhancer 扩展 | ✅ | ❌ 单元测试未创建 |
| 0.10 VectorIndexer 扩展 | ✅ | ❌ 单元测试未创建 |
| 0.11 Meal 手动模式 | ✅ | ❌ 单元测试未创建 |
| 0.12 ArtifactCache 扩展 | ✅ | ❌ 单元测试未创建 |
| 0.13 全量测试 | ✅ | ✅ |

**结论**：Phase 0 的功能代码全部完成，但 **所有共享单元层和模块扩展的单元测试均缺失**。tasks.md 中每个 Task 的"编写单元测试"子项全部未勾选。

### Phase 1 完成度：✅

| Task | 状态 |
|------|------|
| 1.1 包结构 | ✅ |
| 1.2 MaintenanceState | ✅ |
| 1.3 核心 @tool | ✅ |
| 1.4 系统提示词 | ✅ |
| 1.5 agent_node | ✅ |
| 1.6 tool_node | ✅ |
| 1.7 StateGraph + 条件边 | ✅ |
| 1.8 安全机制 | ✅ |
| 1.9 CLI 入口 | ✅ |
| 1.10 Agent 测试 | ✅ 22 个测试 |

**结论**：Phase 1 全部完成。

### Phase 2 完成度：部分

| Task | 状态 |
|------|------|
| 2.1 高风险 @tool | ✅ |
| 2.2 全链路 @tool | ❌ |
| 2.3 Command(goto=...) | ❌ |
| 2.4 interrupt 增强 | ❌ |
| 2.5 Memory Store | ❌ |
| 2.6 Issue 集成 | ❌ |
| 2.7 StateGraph 更新 | ❌ |
| 2.8 Phase 2 测试 | ❌ |

**结论**：Phase 2 仅完成高风险 @tool（Task 2.1），其余 7 个 Task 均未开始。

### Phase 3 完成度：❌

全部 8 个 Task 均未开始。

---

## 四、未完成项的情况和建议

### 4.1 缺失的单元测试（Phase 0）

**优先级：高**。这些测试是验证共享单元层正确性的基础，没有它们我们无法确认：
- `parse_pdf()` 是否真的能正确调用 ParserRegistry
- `chunk_parsed()` 三种策略是否都能正确分发
- `evaluate_single()` 的 Jaccard 指标计算是否正确
- `create_meal_manual()` 是否真的向后兼容
- `update_manifest_entry()` 失败时是否真的原子回滚

**建议**：验收前必须补充，否则无法确认代码质量。

### 4.2 Spec 中的安全机制缺失

**优先级：高**。Spec 明确要求：
1. 写操作前自动备份到 `.trashbin/` — 完全未实现
2. 危险操作硬拦截（禁止 DROP 全量 collection）— 仅靠提示词约束

**建议**：验收前至少实现备份机制，硬拦截可作为 Phase 2 补充。

### 4.3 Phase 2 未完成项

| Task | 重要性 | 是否阻塞验收 |
|------|--------|-------------|
| 2.2 全链路 @tool | 中 | 不阻塞，但影响 Agent 实用性 |
| 2.3 Command(goto=...) | 中 | 不阻塞 |
| 2.4 interrupt 增强 | 低 | 不阻塞 |
| 2.5 Memory Store | 中 | 不阻塞 |
| 2.6 Issue 集成 | 中 | 不阻塞 |
| 2.7 StateGraph 更新 | 中 | 依赖 2.2-2.6 |
| 2.8 Phase 2 测试 | 高 | 依赖 2.2-2.7 |

### 4.4 Phase 3 未完成项

全部不阻塞当前验收，可在后续迭代完成。

### 4.5 总体建议

**先验收 Phase 0 + Phase 1 + Phase 2.1，再继续实现**。理由：

1. 已完成的功能形成了完整的 MVP 闭环：共享单元 → Agent 工具 → LangGraph 图 → CLI
2. 但缺少单元测试是硬伤，必须先补上才能确认代码质量
3. 安全机制的备份功能缺失是 Spec 明确要求的，应在验收前补上
4. Phase 2 剩余和 Phase 3 是增量功能，不影响 MVP 的正确性

**验收步骤建议**：

```
Step 1: 运行 pixi run test + pixi run lint（确认现有测试无回归）
Step 2: 补充 Phase 0 缺失的单元测试
Step 3: 补充安全机制（写操作前备份到 .trashbin/）
Step 4: 手动验证 pixi run agent 交互流程
Step 5: 代码质量审查（错误处理、资源管理、向后兼容）
Step 6: 确认验收通过后，再开新对话继续 Phase 2 剩余任务
```

---

## 五、验收执行清单

### A. 自动化验证

- [ ] `pixi run test` 全量通过
- [ ] `pixi run lint` 通过
- [ ] 补充 `tests/test_core_ops/` 下所有缺失的单元测试
- [ ] 补充现有模块扩展的单元测试
- [ ] 新测试全部通过

### B. 功能验证

- [ ] `pixi run agent` 能正常启动
- [ ] Agent 能响应简单问题（列出 meal）
- [ ] 高风险操作触发 interrupt 审批
- [ ] 审批拒绝后操作不执行
- [ ] 审批通过后操作执行
- [ ] 退出命令正常工作

### C. 安全验证

- [ ] 写操作前自动备份到 `.trashbin/`（需补充实现）
- [ ] HIGH_RISK_TOOLS 全部经过 interrupt
- [ ] update_meal 白名单字段限制生效

### D. 向后兼容验证

- [ ] `create_meal()` 原有参数行为不变
- [ ] `MealConfig.creation_mode` 默认值为 "random"
- [ ] 现有测试无回归

### E. 代码质量

- [ ] 所有 @tool 有 try/except + loguru 日志
- [ ] VectorIndexer 实例正确 close()
- [ ] ArtifactCache.update_manifest_entry() 失败时原子回滚
- [ ] 无硬编码配置值
