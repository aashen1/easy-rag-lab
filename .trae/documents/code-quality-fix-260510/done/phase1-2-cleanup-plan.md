# 代码质量修复计划 - Phase 1 & Phase 2 收尾

> 创建日期：2026-05-10 | 目标：完成 Phase 1 验证 + Phase 2 拆分 God 函数 + 更新进度统计

***

## 任务概览

| 类别                | 任务数   | 预计耗时       |
| ----------------- | ----- | ---------- |
| Phase 1 最终验证      | 1     | \~5分钟      |
| Phase 2 拆分 God 函数 | 7     | \~33小时     |
| 更新进度统计            | 1     | \~5分钟      |
| **总计**            | **9** | **\~33小时** |

***

## 第一步：Phase 1 最终验证

### 任务 1.1：运行完整验证

**操作**：

1. 运行 `pixi run lint` 确保代码风格合规
2. 运行 `pixi run test` 确保全部测试通过
3. 运行 `pixi run ruff-check` 确认无静态检查问题

**验收标准**：三项检查全部通过

**预计耗时**：5分钟

***

## 第二步：Phase 2 拆分 God 函数

### 任务 2.1：拆分 `run_experiment()` God 函数

**文件**：`eval/runner/core.py`
**当前行数**：约 690 行

**步骤**：

1. 分析 `run_experiment()` 函数职责（识别 8 种职责）
2. 提取 `_load_and_validate_config()` 函数
3. 提取 `_create_experiment_directory()` 函数
4. 提取 `_initialize_profiler()` 函数
5. 提取 `_prepare_evaluation_assets()` 函数
6. 提取 `_run_variant_evaluation()` 函数
7. 提取 `_generate_and_save_report()` 函数
8. 提取 `_save_token_and_profiling_data()` 函数
9. 重构主函数为编排函数（< 50 行）
10. 运行测试验证

**验收标准**：主函数 < 50 行，所有测试通过

**预计耗时**：\~10小时

***

### 任务 2.2：拆分 `compute_aggregate_metrics()` God 函数

**文件**：`eval/runner/metrics.py`
**当前行数**：约 226 行

**步骤**：

1. 分析函数职责（识别 9 种聚合逻辑）
2. 提取 `_compute_document_metrics()` 函数
3. 提取 `_compute_generation_metrics()` 函数
4. 提取 `_compute_chunk_metrics()` 函数
5. 提取 `_compute_dedup_metrics()` 函数
6. 提取 `_compute_diversity_metrics()` 函数
7. 提取 `_compute_hallucination_metrics()` 函数
8. 提取 `_compute_question_type_metrics()` 函数
9. 提取 `_compute_llm_retrieval_metrics()` 函数
10. 重构主函数为编排函数（< 30 行）
11. 运行测试验证

**验收标准**：主函数 < 30 行，所有测试通过

**预计耗时**：\~11小时

***

### 任务 2.3：拆分 `evaluate_single()` God Method

**文件**：`eval/evaluators/builtin_evaluator.py`
**当前行数**：约 200 行

**步骤**：

1. 分析 if-chain 结构，识别所有 metric 判断分支
2. 创建 metric 注册表（`dict[str, Callable]`）
3. 将每个 metric 分支提取为独立函数
4. 重构主函数使用注册表（< 20 行）
5. 运行测试验证

**验收标准**：函数 < 20 行，所有测试通过

**预计耗时**：\~6小时

***

### 任务 2.4：拆分 `src/test_generation/generator.py` (1563行)

**文件**：`src/test_generation/generator.py`

**步骤**：

1. 分析 `TestSetGenerator` 职责边界（识别 10+ 种职责）
2. 提取 `QuestionGenerator` 类（核心问题生成逻辑）
3. 提取 `TestSetOrchestrator` 类（编排逻辑）
4. 消除 `generate_hybrid_questions` 和 `generate_golden_testset` 重复代码
5. 更新所有调用点
6. 运行测试验证

**验收标准**：文件拆分为多个职责单一的类，所有测试通过

**预计耗时**：\~10小时

**注意**：此任务风险较高，涉及大量调用点，建议优先完成 2.1-2.3 后再处理

***

### 任务 2.5：拆分 `src/app_pages/maintenance.py` (1160行)

**文件**：`src/app_pages/maintenance.py`

**步骤**：

1. 分析 `render_maintenance()` 职责（识别 15+ 个 session state 变量）
2. 提取 `_initialize_session_state()` 函数
3. 提取 `_render_sidebar()` 函数
4. 提取 `_render_chat_messages()` 函数
5. 提取 `_handle_interruption()` 函数
6. 提取 `_scan_experiences()` 函数
7. 提取 `_download_report()` 函数
8. 提取 `_render_agent_graph()` 函数
9. 重构主函数为编排函数（< 100 行）
10. 运行测试验证

**验收标准**：主函数 < 100 行，所有测试通过

**预计耗时**：\~10小时

***

### 任务 2.6：拆分 `src/agent/tools.py` (1033行)

**文件**：`src/agent/tools.py`

**步骤**：

1. 分析重复模式（识别 20+ 个 `@tool` 函数的共同模式）
2. 创建 `tool_with_error_handling` 装饰器
3. 创建 `json_response` 辅助函数
4. 创建 `get_config()` 辅助函数
5. 重构所有 tool 函数使用新辅助工具
6. 运行测试验证

**验收标准**：代码行数减少 30%+，所有测试通过

**预计耗时**：\~8小时

***

### 任务 2.7：拆分 `src/agent/cli.py` 的 `run_agent()` (330+行)

**文件**：`src/agent/cli.py`

**步骤**：

1. 分析 `run_agent()` 职责
2. 提取 `_parse_cli_args()` 函数
3. 提取 `_initialize_database()` 函数
4. 提取 `_manage_session()` 函数
5. 提取 `_interactive_loop()` 函数
6. 提取 `_dispatch_cli_command()` 函数
7. 重构主函数为编排函数（< 50 行）
8. 运行测试验证

**验收标准**：主函数 < 50 行，所有测试通过

**预计耗时**：\~7小时

***

## 第三步：更新进度统计

### 任务 3.1：更新 `code-quality-fix-progress.md` 底部统计

**操作**：

1. 更新 Phase 1 进度统计：

   * 开始日期：2026-05-10

   * 完成日期：2026-05-10

   * 完成任务：15/15

   * 完成百分比：100%

2. 更新 Phase 2 进度统计（消除重复代码部分）：

   * 开始日期：2026-05-10

   * 完成任务：根据实际完成情况更新

3. 添加 Phase 1 Step 7 验证条目到进度报告

**验收标准**：统计数字与实际完成情况一致

**预计耗时**：5分钟

***

## 执行策略

### 优先级排序

1. **P0 - 必须先做**：Phase 1 最终验证（确保之前的工作没有破坏任何东西）
2. **P1 - 高价值低风险**：拆分 `run_experiment()`、`compute_aggregate_metrics()`、`evaluate_single()`
3. **P2 - 高价值中风险**：拆分 `generator.py`、`maintenance.py`、`tools.py`、`cli.py`
4. **P3 - 收尾**：更新进度统计

### 风险控制

1. **每个子任务完成后立即提交**（遵循 atomic commit 规则）
2. **每完成一个 God 函数拆分后运行完整测试**
3. **如遇测试失败，立即回滚并分析原因**
4. **对于复杂的拆分（如 generator.py），先分析职责边界再动手**

### 验收标准

* 每个子任务完成后运行 `pixi run test-unit` 验证

* 所有任务完成后运行 `pixi run test` 完整验证

* 运行 `pixi run lint` 确保代码质量

***

## 成功标准

* [x] Phase 1 最终验证通过

* [x] 至少完成 3 个 God 函数拆分（`run_experiment`、`compute_aggregate_metrics`、`evaluate_single`）

* [x] 完成 7 个 God 函数拆分（全部完成）

* [x] 所有测试通过

* [x] Lint 检查通过

* [x] 进度统计已更新

