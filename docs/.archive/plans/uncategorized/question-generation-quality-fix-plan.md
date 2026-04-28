# 问题生成质量深度修复计划

## 问题概述

当前问题生成功能存在以下核心问题导致分数虚假、问答质量不高：

1. **Segment-Chunk 粒度不匹配**：问题生成时使用 8000 字符的 segment，检索时使用 512 token 的 chunk，粒度相差 10 倍
2. **Ground Truth 无验证**：expected\_answer 由 LLM 生成，可能包含幻觉，但被当作正确答案
3. **Evidence 验证不足**：只要求 15 字符的引用，且不验证答案正确性
4. **问题类型分布不合理**：adversarial 占比 0%，缺少边界场景测试

## 修复策略

采用**三阶段渐进式修复**：

* **Phase 1（快速修复）**：调整参数、增强验证，立即见效

* **Phase 2（机制改进）**：改进生成流程、增加验证步骤

* **Phase 3（架构优化）**：解决根本问题，建立长期机制

***

## Phase 1：快速修复（预计 2-3 小时）

### 1.1 调整问题类型分布

**目标**：增加边界场景测试，提高问题多样性

**修改文件**：`src/test_generator.py`

**具体步骤**：

1. 修改 `TYPE_DISTRIBUTION` 常量（行 443-451）：

   ```python
   TYPE_DISTRIBUTION = {
       "single_fact": 0.25,    # 从 0.30 降低
       "multi_fact": 0.20,     # 从 0.25 降低
       "reasoning": 0.15,      # 保持不变
       "comparative": 0.15,    # 保持不变
       "missing": 0.10,        # 保持不变
       "irrelevant": 0.05,     # 保持不变
       "adversarial": 0.10,    # 从 0.00 提升到 10%
   }
   ```

2. 同步修改 `GOLDEN_TYPE_DISTRIBUTION`（行 455-463）：

   ```python
   GOLDEN_TYPE_DISTRIBUTION = {
       "single_fact": 0.15,    # 从 0.17 降低
       "multi_fact": 0.18,     # 从 0.20 降低
       "reasoning": 0.15,      # 从 0.17 降低
       "comparative": 0.15,    # 保持不变
       "missing": 0.12,        # 从 0.13 降低
       "irrelevant": 0.05,     # 从 0.07 降低
       "adversarial": 0.20,    # 从 0.10 提升到 20%
   }
   ```

**验证方式**：

* 运行测试：`pixi run pytest tests/test_test_generator.py -v`

* 检查生成的测试集类型分布是否符合预期

### 1.2 强化 Evidence 验证

**目标**：提高引用质量，减少幻觉

**修改文件**：`src/test_generator.py`

**具体步骤**：

1. 增加 `MIN_QUOTE_LENGTH` 常量（行 4453）：

   ```python
   MIN_QUOTE_LENGTH = 30  # 从 15 提升到 30
   ```

2. 在 `_validate_evidence()` 方法中增加答案一致性检查（行 4455 附近）：

   * 新增方法 `_validate_answer_evidence_consistency()`

   * 检查 expected\_answer 中的关键信息是否在 evidence 中

   * 数值、日期、专有名词必须能在 quote 中找到

3. 修改 `_validate_evidence()` 调用逻辑：

   ```python
   # 在验证 evidence 后，额外验证答案一致性
   if validation["valid"]:
       consistency = self._validate_answer_evidence_consistency(qa)
       if not consistency["valid"]:
           logger.warning(f"Answer-evidence inconsistency: {consistency['reason']}")
           validation["valid"] = False
   ```

**验证方式**：

* 生成测试集，检查 `excerpt_verified_rate` 指标

* 手动抽查 10-20 个问题，验证引用质量

### 1.3 添加数值一致性检查

**目标**：确保答案中的数值与原文一致

**修改文件**：`src/test_generator.py`

**具体步骤**：

1. 增强 `_validate_numerical_accuracy()` 方法（行 2582）：

   * 当前只检测 10 倍换算错误

   * 增加检测：答案中的数值是否在 ground\_truth\_excerpt 中出现

   * 增加检测：单位是否一致（元/亿元/万元）

2. 新增数值提取和验证逻辑：

   ```python
   def _extract_numbers_from_text(self, text: str) -> list[dict]:
       """提取文本中的数值和单位"""
       # 使用正则提取：数字 + 单位
       # 返回 [(数值, 单位, 原文片段)]

   def _validate_number_consistency(self, answer: str, excerpt: str) -> dict:
       """验证答案中的数值是否在原文中出现"""
       answer_numbers = self._extract_numbers_from_text(answer)
       excerpt_numbers = self._extract_numbers_from_text(excerpt)
       # 检查每个答案数值是否在原文数值中（允许单位换算）
   ```

**验证方式**：

* 运行测试：`pixi run pytest tests/test_test_generator.py::TestNumericalValidation -v`

* 检查 `numerical_correction_rate` 指标

***

## Phase 2：机制改进（预计 1-2 天）

### 2.1 实现 Chunk-Aware 问题生成

**目标**：让 LLM 在生成问题时看到的上下文与检索时一致

**修改文件**：`src/test_generator.py`

**具体步骤**：

1. 新增配置项 `use_chunk_context`（在 `config.yaml` 中）：

   ```yaml
   test_generation:
     use_chunk_context: true  # 使用 chunk 级别上下文生成问题
     chunk_context_k: 3       # 使用前 3 个 chunk 作为上下文
   ```

2. 新增方法 `_select_chunks_for_question_generation()`：

   * 根据问题类型选择合适数量的 chunk

   * 单知识点：1 个 chunk

   * 多知识点：2-3 个相邻 chunk

   * 推理型：2-3 个相关 chunk

3. 修改 `_generate_hybrid_question()` 方法：

   * 当 `use_chunk_context=True` 时，使用 chunk 而非 segment

   * 确保生成的 evidence 引用来自 chunk 文本

4. 更新 prompt 模板：

   * 修改 `EVIDENCE_AWARE_PROMPT`

   * 明确告知 LLM 只能使用提供的 chunk 内容

   * 强调引用必须逐字一致

**验证方式**：

* 生成测试集，对比 `use_chunk_context=True/False` 的质量差异

* 检查 `source_chunks` 定位成功率

### 2.2 增加答案验证步骤

**目标**：在生成问题后，验证答案的正确性

**修改文件**：`src/test_generator.py`

**具体步骤**：

1. 新增方法 `_verify_generated_answer()`：

   ```python
   def _verify_generated_answer(
       self,
       question: str,
       answer: str,
       evidence: list[dict],
       doc_content: str,
   ) -> dict[str, Any]:
       """验证生成的答案是否可靠"""
       # 1. 检查答案中的关键信息是否在 evidence 中
       # 2. 检查答案是否自相矛盾
       # 3. 检查答案是否过于宽泛或无意义
       return {
           "valid": bool,
           "issues": list[str],
           "confidence": float,  # 0-1
       }
   ```

2. 在问题生成流程中调用验证：

   ```python
   # 在 _generate_hybrid_question() 中
   if qa is not None:
       verification = self._verify_generated_answer(
           qa["question"],
           qa["answer"],
           qa.get("evidence", []),
           doc_content,
       )
       if not verification["valid"]:
           logger.warning(f"Answer verification failed: {verification['issues']}")
           continue  # 重试
       qa["metadata"]["answer_confidence"] = verification["confidence"]
   ```

3. 实现具体的验证规则：

   * **关键信息覆盖**：答案中的实体、数值必须在 evidence 中出现

   * **逻辑一致性**：答案不能自相矛盾（如"增长"和"下降"同时出现）

   * **完整性检查**：答案不能是"文档未提及"、"无法回答"（除非是 missing 类型）

**验证方式**：

* 生成测试集，检查 `answer_confidence` 分布

* 手动审查低 confidence 的问题

### 2.3 改进问题质量评分

**目标**：建立更全面的问题质量评估体系

**修改文件**：`src/test_generator.py`

**具体步骤**：

1. 增强 `_calculate_hybrid_quality_metrics()` 方法（行 2963）：

   * 新增指标：`answer_evidence_consistency_rate`

   * 新增指标：`numerical_accuracy_rate`

   * 新增指标：`chunk_location_success_rate`

2. 新增质量阈值配置：

   ```yaml
   test_generation:
     quality_thresholds:
       min_excerpt_verified_rate: 0.80
       min_answer_confidence: 0.70
       min_chunk_location_rate: 0.60
   ```

3. 实现质量门控：

   * 如果测试集质量低于阈值，发出警告

   * 可选：自动重新生成低质量问题

**验证方式**：

* 生成测试集，检查各项质量指标

* 对比修复前后的指标变化

***

## Phase 3：架构优化（预计 3-5 天）

### 3.1 分离生成模型与评测模型

**目标**：避免自评偏差，提高评测可靠性

**修改文件**：`config.yaml`, `src/test_generator.py`

**具体步骤**：

1. 新增配置项：

   ```yaml
   test_generation:
     generation_model: "LongCat-Flash-Lite"
     verification_model: "claude-3-5-sonnet-20241022"  # 更强的模型验证
   ```

2. 实现双模型流程：

   * 使用 `generation_model` 生成问题

   * 使用 `verification_model` 验证答案正确性

   * 验证失败的问题被拒绝或重新生成

3. 修改评测流程：

   * 使用独立的评测模型（与生成模型不同）

   * 避免同一模型既当运动员又当裁判

**验证方式**：

* 对比单模型 vs 双模型生成的测试集质量

* 检查评测分数的合理性

### 3.2 建立人工审核机制

**目标**：通过人工审核建立高质量黄金测试集

**新增文件**：`scripts/review_testset.py`

**具体步骤**：

1. 实现交互式审核脚本：

   ```python
   # scripts/review_testset.py
   # 功能：
   # 1. 加载生成的测试集
   # 2. 逐题展示：问题、答案、原文引用、来源文档
   # 3. 用户打分：1-5 分，或标记为"拒绝"
   # 4. 保存审核结果到 metadata.review_status
   ```

2. 实现审核结果统计：

   * 统计通过率、拒绝率

   * 分析常见问题类型

   * 生成审核报告

3. 建立黄金测试集：

   * 通过审核的问题进入黄金测试集

   * 黄金测试集用于回归测试和模型对比

**验证方式**：

* 审核至少 50 个问题

* 建立包含 30+ 高质量问题的黄金测试集

### 3.3 实现 Ground Truth 标注工具

**目标**：支持人工标注高质量的问答对

**新增文件**：`scripts/annotate_ground_truth.py`

**具体步骤**：

1. 实现标注界面：

   * 展示文档内容

   * 用户选择原文片段作为 ground truth

   * 用户编写问题和答案

   * 系统自动定位 source\_chunks

2. 实现标注数据管理：

   * 保存标注结果到 JSON

   * 支持导入/导出

   * 支持多人协作标注

3. 建立标注规范：

   * 编写标注指南文档

   * 定义各类问题的标注标准

   * 提供标注示例

**验证方式**：

* 标注至少 20 个高质量问答对

* 用于验证自动生成问题的质量

***

## 实施顺序

### Week 1：快速修复 + 验证

* Day 1：Phase 1.1 - 调整问题类型分布

* Day 1：Phase 1.2 - 强化 Evidence 验证

* Day 2：Phase 1.3 - 添加数值一致性检查

* Day 2-3：生成测试集，验证修复效果

### Week 2：机制改进

* Day 1-2：Phase 2.1 - Chunk-Aware 问题生成

* Day 3：Phase 2.2 - 增加答案验证步骤

* Day 4：Phase 2.3 - 改进问题质量评分

* Day 5：集成测试，验证整体效果

### Week 3-4：架构优化（可选）

* Week 3：Phase 3.1 - 分离生成模型与评测模型

* Week 3-4：Phase 3.2 - 建立人工审核机制

* Week 4：Phase 3.3 - 实现 Ground Truth 标注工具

***

## 成功标准

### Phase 1 完成标准

* [ ] adversarial 问题占比达到 10%

* [ ] MIN\_QUOTE\_LENGTH 提升到 30

* [ ] 新增数值一致性验证

* [ ] 测试通过率 > 95%

* [ ] 生成测试集的 `excerpt_verified_rate` > 0.70

### Phase 2 完成标准

* [ ] 实现 chunk-aware 问题生成

* [ ] 答案验证步骤集成到生成流程

* [ ] 质量指标体系完善

* [ ] `chunk_location_success_rate` > 0.60

* [ ] `answer_confidence` 平均值 > 0.75

### Phase 3 完成标准

* [ ] 生成模型与评测模型分离

* [ ] 人工审核流程建立

* [ ] 黄金测试集包含 30+ 高质量问题

* [ ] 标注工具可用

* [ ] 评测分数与人工判断相关性 > 0.80

***

## 风险与缓解

### 风险 1：修改后问题生成失败率上升

**缓解措施**：

* 保留原有逻辑作为 fallback

* 设置合理的重试次数（max\_retries=5）

* 记录失败原因，用于后续优化

### 风险 2：Chunk-Aware 生成导致问题过于简单

**缓解措施**：

* 对比测试：segment-based vs chunk-based

* 调整 chunk 数量（1-3 个）

* 保持问题类型多样性

### 风险 3：双模型增加成本和延迟

**缓解措施**：

* 仅对关键问题类型使用验证模型

* 批量验证，减少 API 调用次数

* 缓存验证结果

### 风险 4：人工审核耗时过长

**缓解措施**：

* 优先审核高价值问题类型

* 使用抽样审核（审核 20-30%）

* 建立审核队列，分批处理

***

## 附录：关键代码位置

| 功能          | 文件                 | 行号        | 说明                                      |
| ----------- | ------------------ | --------- | --------------------------------------- |
| 类型分布        | test\_generator.py | 443-451   | TYPE\_DISTRIBUTION                      |
| Golden 类型分布 | test\_generator.py | 455-463   | GOLDEN\_TYPE\_DISTRIBUTION              |
| Evidence 验证 | test\_generator.py | 4455-4610 | \_validate\_evidence()                  |
| 数值验证        | test\_generator.py | 2582-2666 | \_validate\_numerical\_accuracy()       |
| 问题生成        | test\_generator.py | 2393-2528 | \_generate\_hybrid\_question()          |
| 质量指标        | test\_generator.py | 2963-3043 | \_calculate\_hybrid\_quality\_metrics() |
| Segment 切分  | test\_generator.py | 508-592   | \_segment\_document()                   |
| Chunk 映射    | test\_generator.py | 921-1003  | \_map\_segments\_to\_chunks()           |
