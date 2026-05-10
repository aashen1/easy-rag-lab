# 代码质量修复计划 - Phase 1 & Phase 2

> 创建日期：2026-05-10 | 目标：完成 Phase 1 剩余任务和 Phase 2 核心任务

---

## 当前状态分析

### Phase 1 已完成
- ✅ 删除假测试 (`test_run_experiment.py:1130-1132`)
- ✅ 删除未使用的装饰器 (`error_handler.py`)
- ✅ 删除未使用的静态方法 (`_compute_config_hash`)
- ✅ 修复拼写错误 (`pymupdf4llllm` → `pymupdf4llm`)

### Phase 1 待完成
- ❌ 替换 `print()` 为 `logger` (`eval/runner/core.py`)

### Phase 2 已完成
- ✅ 消除 token tracker 重建逻辑重复
- ✅ 提取 `ExperimentManager._update_manifest()` 辅助方法

### Phase 2 待完成
- ❌ 拆分 God 文件与 God 函数（7个大文件）
- ❌ 消除重复代码（10个重复点）

---

## 执行计划

### 第一步：完成 Phase 1 剩余任务

#### 任务 1.1：替换 `print()` 为 `logger`
**文件**: `eval/runner/core.py`

**步骤**:
1. 搜索 `eval/runner/core.py` 中所有 `print()` 调用
2. 确认 `loguru` 已导入
3. 替换 `list_experiments()` 中的 `print()` 为 `logger.info()`
4. 替换 `show_experiment_info()` 中的 `print()` 为 `logger.info()`
5. 运行测试验证功能正常

**验收标准**: 无 `print()` 调用，日志输出正常

---

### 第二步：Phase 2 核心任务 - 消除重复代码

#### 任务 2.1：消除 serial/concurrent 采样逻辑重复
**文件**: `eval/runner/evaluation.py`

**步骤**:
1. 读取 `eval/runner/evaluation.py` 分析重复代码
2. 识别 `_collect_rag_samples_serial()` 和 `_query_single_question()` 的重复部分
3. 提取 `_build_sample()` 函数封装 sample 构建逻辑
4. 重构两个函数使用新函数
5. 运行测试验证

**验收标准**: 无重复代码，功能验证通过

---

#### 任务 2.2：消除 RAGAS evaluator ref/no-ref 分支重复
**文件**: `eval/evaluators/ragas_evaluator.py`

**步骤**:
1. 读取 `eval/evaluators/ragas_evaluator.py` 第 551-649 行
2. 分析两个分支的重复逻辑
3. 提取 `_run_ragas_evaluation()` 函数
4. 重构两个分支使用新函数
5. 运行测试验证

**验收标准**: 无重复代码，功能验证通过

---

#### 任务 2.3：消除 LLM 调用 + JSON 解析重复模式
**文件**: `eval/metrics/llm_retrieval.py`, `eval/metrics/generation.py`

**步骤**:
1. 读取两个文件分析重复模式
2. 提取 `_llm_judge()` 辅助函数到 `eval/metrics/utils.py`
3. 重构所有调用点使用新函数
4. 运行测试验证

**验收标准**: 无重复代码，功能验证通过

---

#### 任务 2.4：消除 chunk 匹配逻辑重复
**文件**: `eval/metrics/chunk.py`

**步骤**:
1. 读取 `eval/metrics/chunk.py` 分析三个函数
2. 提取 `_match_chunks()` 函数
3. 重构三个函数使用新函数
4. 运行测试验证

**验收标准**: 无重复代码，功能验证通过

---

#### 任务 2.5：消除推荐逻辑重复
**文件**: `eval/reporter/template_single.py`, `eval/reporter/template_variant.py`

**步骤**:
1. 读取两个文件分析推荐逻辑
2. 提取 `_generate_recommendation()` 函数到 `eval/reporter/utils.py`
3. 重构两个文件使用新函数
4. 运行测试验证

**验收标准**: 无重复代码，功能验证通过

---

#### 任务 2.6：消除 `_resolve_db_path` 函数重复
**文件**: `src/agent/checkpoint.py`, `src/agent/session_manager.py`

**步骤**:
1. 创建 `src/agent/db_utils.py` 模块
2. 移动 `_resolve_db_path` 到新模块
3. 更新两个文件的导入
4. 运行测试验证

**验收标准**: 无重复函数，功能验证通过

---

#### 任务 2.7：消除 Reporter save 方法重复
**文件**: `src/agent/reporters/comparison_report.py`, `src/agent/reporters/maintenance_report.py`

**步骤**:
1. 读取两个文件分析 `save()` 方法
2. 创建 `BaseReporter` 基类
3. 重构两个类继承基类
4. 运行测试验证

**验收标准**: 无重复代码，功能验证通过

---

#### 任务 2.8：消除 Agent state 字典构造重复
**文件**: `src/agent/cli.py`, `src/app_pages/maintenance.py`

**步骤**:
1. 搜索两个文件中的 state 字典构造
2. 创建 `build_agent_state()` 辅助函数
3. 重构所有调用点
4. 运行测试验证

**验收标准**: 无重复代码，功能验证通过

---

#### 任务 2.9：消除流式处理逻辑重复
**文件**: `src/app_pages/maintenance.py`

**步骤**:
1. 读取文件分析 `_render_streaming_agent` 和 `_resume_interrupt_streaming`
2. 提取 `_handle_streaming_event()` 函数
3. 重构两个函数使用新函数
4. 运行测试验证

**验收标准**: 无重复代码，功能验证通过

---

### 第三步：Phase 2 高优先级任务 - 拆分 God 函数

#### 任务 2.10：拆分 `run_experiment()` God 函数
**文件**: `eval/runner/core.py`

**步骤**:
1. 分析 `run_experiment()` 函数职责（约 690 行）
2. 提取子函数：
   - `_load_and_validate_config()`
   - `_create_experiment_directory()`
   - `_initialize_profiler()`
   - `_prepare_evaluation_assets()`
   - `_run_variant_evaluation()`
   - `_generate_and_save_report()`
   - `_save_token_and_profiling_data()`
3. 重构主函数为编排函数
4. 运行测试验证

**验收标准**: 主函数 < 50 行，功能验证通过

---

#### 任务 2.11：拆分 `compute_aggregate_metrics()` God 函数
**文件**: `eval/runner/metrics.py`

**步骤**:
1. 分析函数职责（约 226 行）
2. 提取子函数：
   - `_compute_document_metrics()`
   - `_compute_generation_metrics()`
   - `_compute_chunk_metrics()`
   - `_compute_dedup_metrics()`
   - `_compute_diversity_metrics()`
   - `_compute_hallucination_metrics()`
   - `_compute_question_type_metrics()`
   - `_compute_llm_retrieval_metrics()`
3. 重构主函数为编排函数
4. 运行测试验证

**验收标准**: 主函数 < 30 行，功能验证通过

---

#### 任务 2.12：拆分 `evaluate_single()` God Method
**文件**: `eval/evaluators/builtin_evaluator.py`

**步骤**:
1. 分析 if-chain 结构（约 200 行）
2. 创建 metric 注册表
3. 将每个 metric 分支提取为独立函数
4. 重构主函数使用注册表
5. 运行测试验证

**验收标准**: 函数 < 20 行，功能验证通过

---

### 第四步：更新进度报告

完成所有任务后，更新 `code-quality-fix-progress.md`：
- 将完成的任务打钩 `[x]`
- 更新 Phase 1 和 Phase 2 的进度统计
- 记录完成日期

---

## 执行策略

### 优先级排序
1. **Phase 1 剩余任务**（P0）- 必须完成
2. **Phase 2 消除重复代码**（P1）- 高价值，风险低
3. **Phase 2 拆分 God 函数**（P1）- 高价值，风险中等

### 验收标准
- 每个任务完成后立即运行 `pixi run test-unit` 验证
- 所有任务完成后运行 `pixi run test` 完整验证
- 运行 `pixi run lint` 确保代码质量

### 风险控制
- 每个重构步骤后立即提交（遵循 atomic commit 规则）
- 如遇测试失败，立即回滚并分析原因
- 对于复杂的 God 函数拆分，先分析职责边界再动手

---

## 预计工作量

| 任务类型 | 任务数 | 预计耗时 |
|---------|--------|---------|
| Phase 1 剩余 | 1 | ~20分钟 |
| Phase 2 消除重复 | 9 | ~18小时 |
| Phase 2 拆分 God 函数 | 3 | ~15小时 |
| **总计** | **13** | **~33.3小时** |

---

## 成功标准

- ✅ Phase 1 所有任务完成
- ✅ Phase 2 核心重复代码消除
- ✅ Phase 2 至少 3 个 God 函数拆分完成
- ✅ 所有测试通过
- ✅ Lint 检查通过
- ✅ 进度报告已更新
