# RAG 测试集生成系统全面审查与优化计划

## 一、系统现状总结

### 1.1 架构概览

当前系统采用 **双链路策略**：

* **Default 链路**（hybrid/document 策略）：针对特定 meal 生成测试集，20 题规模，用于日常实验

* **Golden 链路**：全量数据 + 文档去重 + adversarial 类型 + 审核元数据，150 题规模，用于项目级基准

核心文件：[test\_generator.py](file:///b:/project/ash-easy-rag/src/test_generator.py)（4186 行）、[test\_set\_manager.py](file:///b:/project/ash-easy-rag/src/test_set_manager.py)（1214 行）、[run\_experiment.py](file:///b:/project/ash-easy-rag/eval/run_experiment.py)（2985 行）

### 1.2 关键问题发现

| 问题类别        | 严重程度 | 描述                                                                                                             |
| ----------- | ---- | -------------------------------------------------------------------------------------------------------------- |
| 指标冗余        | 高    | Builtin 与 RAGAS 4 个重叠指标（faithfulness/answer\_relevancy/context\_precision/context\_recall），双后端同时启用时 token 成本翻倍 |
| 审核漏洞        | 高    | rejected 题目仍参与评测，review\_status 在评测管线中完全不被检查                                                                   |
| Token 浪费    | 高    | multi\_hop 类型 4 个候选段 × 8000 字符 = \~12,800 tokens/题，占测试集生成 token 的 80%+                                         |
| 审核效率        | 中    | 150 题逐题交互审核，无批量操作、无审计联动、无自动预筛选                                                                                 |
| 链路冗余        | 中    | Golden 与 Default 共享 90% 代码逻辑，仅类型分布/去重/元数据不同                                                                    |
| 评测 Token 盲区 | 中    | Builtin evaluator 的 LLM 调用未纳入 TokenTracker                                                                     |

***

## 二、优化方案详细设计

### 2.1 系统逻辑与指标优化

#### 2.1.1 指标体系精简（剔除冗余指标）

**现状**：Builtin 和 RAGAS 有 4 个重叠指标，同时启用时 token 成本翻倍且评分不一致。

**方案**：建立 **指标分层策略**，而非简单删除：

| 层级                | 指标                                                                                        | 后端      | LLM 需求 | 适用场景   |
| ----------------- | ----------------------------------------------------------------------------------------- | ------- | ------ | ------ |
| **核心层**（每次必算）     | hit\_rate, mrr, ndcg, recall\@3/5/10, faithfulness, answer\_relevancy                     | builtin | 是（2 个） | 日常实验   |
| **扩展层**（按需启用）     | chunk\_hit\_rate/mrr/ndcg, dedup\_hit\_rate/mrr/ndcg, context\_precision, context\_recall | builtin | 是（2 个） | 深度诊断   |
| **RAGAS 层**（对标验证） | faithfulness, answer\_relevancy, answer\_correctness, semantic\_similarity                | ragas   | 是（4 个） | 版本发布对标 |
| **诊断层**（专项分析）     | fpr, retrieval\_diversity, hallucination\_rate                                            | builtin | 否      | 问题排查   |

**具体操作**：

1. 在 `config.yaml` 中新增 `evaluation.metrics_tier` 配置项（core/extended/full），默认 `core`
2. `core`：仅计算核心层指标（hit\_rate/mrr/ndcg/recall + faithfulness/answer\_relevancy）
3. `extended`：核心层 + chunk/dedup/context\_precision/context\_recall
4. `full`：全部指标 + RAGAS 对标
5. 修改 `BuiltinEvaluator.evaluate_single()` 根据 tier 跳过非必要指标
6. 修改 `run_experiment.py` 根据 tier 决定是否启用 RAGAS 后端

**预估收益**：

* core tier 相比 full：评测 LLM 调用从 \~11 次/题降至 \~3 次/题（-73%）

* 日常实验不再默认跑 context\_precision/context\_recall（每题 \~8 次 LLM 调用）

#### 2.1.2 Token 消耗优化

**优化项 A：减少 multi\_hop 候选段数量**

* `multi_hop_candidate_count` 从 4 降至 3

* 预估节省：multi\_hop 类型输入 token -25%

* 实施：修改 `config.yaml` 一行配置

* 风险：低，LLM 通常只引用 2-3 个片段

**优化项 B：segment\_size 自适应**

* single\_fact/missing/adversarial：segment\_size=6000（-25%）

* multi\_fact/reasoning/comparative：segment\_size=8000（保持不变）

* 实施：修改 `_select_segments_for_question_type()` 中的 segment\_size 参数

* 风险：中，需验证小 segment 是否影响 evidence 验证通过率

**优化项 C：EVIDENCE\_AWARE\_PROMPT 精简**

* 压缩类型说明（与 EVIDENCE\_QUESTION\_TYPE\_SUPPLEMENTS 去重）

* 精简数值规则（200 字符 → 80 字符）

* 压缩 JSON schema 示例

* 预估节省：固定部分 -30%（\~500 → \~350 tokens）

* 风险：低，纯文本优化不影响逻辑

**优化项 D：预验证机制减少无效重试**

* 在调用 LLM 前，检查 segments 是否包含足够的关键词/数字（`_extract_segment_keywords` 已存在）

* 对 irrelevant 类型，跳过 segment 加载（当前已实现，但可加日志确认）

* 对 evidence 验证失败的重试，先尝试修复 JSON 格式再重试

* 预估节省：减少 30-50% 的无效重试

**优化项 E：评测 LLM 调用纳入 TokenTracker**

* BuiltinEvaluator 的 faithfulness/answer\_relevancy/context\_precision/context\_recall 调用目前未追踪

* 将 TokenTracker 传入 BuiltinEvaluator，记录评测阶段的 token 消耗

* 收益：可观测性提升，而非直接节省 token

**总体预估**：综合 A+B+C+D，测试集生成 token 消耗可降低 **30-40%**。

#### 2.1.3 生成质量提升方案

**方案 1：LLM 自评过滤**

* 在 `_generate_question_with_evidence()` 后增加一步 LLM 自评

* 让 LLM 对生成的问题打分（清晰度/可回答性/证据充分性），低于阈值自动重试

* 预估增加 1 次 LLM 调用/题（\~500 tokens），但可减少人工审核拒绝率

**方案 2：问题多样性增强**

* 在 `_distribute_questions_across_docs()` 后增加跨文档去重检查

* 检测语义相似的问题（embedding 余弦相似度 > 0.9），替换重复题

* 避免不同文档生成相同模式的问题

**方案 3：数值校验扩展**

* 当前仅检测 10x 换算错误，扩展到：

  * 百分比与绝对值的一致性检查

  * 年份/日期的合理性检查

  * 数值与单位的一致性检查

***

### 2.2 人工审核流程优化

#### 2.2.1 紧急修复：rejected 题目过滤

**现状**：评测管线不检查 `review_status`，rejected 题目仍参与评测。

**方案**：

1. 在 `TestSetManager.resolve_test_set()` 中，加载 Golden 测试集后过滤 `review_status == "rejected"` 的题目
2. 在 `run_eval.py` 的 `run_evaluation()` 中增加同样的过滤逻辑（防御性编程）
3. 过滤后记录日志：`logger.info(f"Filtered {n_rejected} rejected questions from golden testset")`

#### 2.2.2 审核流程分层：先机器筛选，再人工精审

**核心思路**：将 150 题的审核工作量从"全部人工"降至"仅审核机器标记的可疑题"。

**分层策略**：

| 层级        | 筛选条件                                             | 预估题量      | 处理方式                                 |
| --------- | ------------------------------------------------ | --------- | ------------------------------------ |
| **自动通过**  | excerpt\_verified=True + 数值校验通过 + 非模板化 + 审计报告无异常 | \~60-80 题 | 自动标记 `review_status="auto_approved"` |
| **需人工审核** | excerpt\_verified=False 或 数值问题 或 模板化 或 审计报告异常    | \~40-60 题 | 人工逐题审核                               |
| **自动拒绝**  | 空答案/空问题/格式严重错误                                   | \~0-5 题   | 自动标记 `review_status="auto_rejected"` |

**自动通过的判定规则**：

1. `excerpt_verified == True`
2. `numerical_auto_corrected` 不存在或为 False（无自动修正记录）
3. 审计报告中"模板模式"未命中该题
4. 审计报告中"内容重复"未命中该题
5. 审计报告中"文档集中度"未命中该题
6. 问题长度在合理范围（15-200 字符）
7. 答案长度在合理范围（10-500 字符）

**实施步骤**：

1. 在 `review_golden_testset.py` 中新增 `--auto-approve` 模式
2. 实现上述判定规则，对通过所有检查的题目自动标记 `auto_approved`
3. 人工审核时默认只展示非 auto\_approved 的题目（可通过 `--include-auto-approved` 查看全部）
4. 在评测管线中，`auto_approved` 与 `approved` 等价

**预估收益**：人工审核工作量从 150 题降至 40-60 题（**-60%**）。

#### 2.2.3 审核工具增强

**增强 1：审计报告与审核联动**

* 在 `display_question()` 中展示审计标记（如"⚠️ 数值精度问题"、"⚠️ 与 golden\_042 可能重复"）

* 让审核员优先关注有问题的题目

**增强 2：批量操作**

* 新增 `--batch-approve` 模式：对通过审计检查的题目自动标记为 approved

* 新增 `--batch-reject` 模式：对指定条件的题目批量拒绝

**增强 3：审核进度持久化**

* 在测试集 `metadata` 中记录 `last_reviewed_index`

* 下次启动时自动从该位置继续

**增强 4：needs\_revision 状态激活**

* Edit 操作完成后自动将 `review_status` 设为 `"needs_revision"`

* 审核循环中 needs\_revision 与 pending 一样需要再次审核

**增强 5：审核者身份记录**

* 新增 `--reviewer` CLI 参数

* 在审核元数据中记录 `reviewer` 字段

***

### 2.3 双链路策略专题研究

#### 2.3.1 双链路必要性分析

**当前差异点**：

| 维度   | Default        | Golden          | 差异本质      |
| ---- | -------------- | --------------- | --------- |
| 数据范围 | 指定 meal        | 全量 meal         | **配置差异**  |
| 类型分布 | adversarial=0% | adversarial=10% | **配置差异**  |
| 文档去重 | 无              | 有               | **功能开关**  |
| 元数据  | 基础             | 审核相关            | **元数据扩展** |
| 生命周期 | 随 meal 变化      | 项目级资产           | **存储策略**  |

**结论**：两条链路的 **核心生成逻辑完全相同**（都走 `generate_hybrid_questions()`），差异仅在配置参数和后处理步骤。Golden 链路的"额外功能"（去重、审核元数据、adversarial 类型）本质上都是 Default 链路的 **可选增强**，而非独立能力。

#### 2.3.2 Golden 测试集定位评估

**当前定位**："标定系统基本性能"的项目级基准测试集。

**评估**：

* ✅ 合理性：全量数据 + adversarial 类型 + 人工审核 = 高质量基准

* ✅ 不可替代性：Default 测试集随 meal 变化，无法作为跨版本对比的稳定基准

* ⚠️ 问题：Golden 测试集的"标定"能力受限于 LLM 生成质量，未经人工审核的 Golden 题目不一定比 Default 更可靠

* ⚠️ 问题：Golden 自动生成（`resolve_test_set` 中不存在时自动生成）破坏了"项目级资产"的稳定性

**建议**：

1. 保留 Golden 测试集作为项目级基准的定位
2. 移除自动生成逻辑（Golden 应该是预生成 + 人工审核的稳定资产，不应自动生成）
3. 在实验配置中增加 `golden_require_reviewed: true` 选项，确保只有审核通过的 Golden 题目参与评测

#### 2.3.3 Golden 额外指标设计审查

**Golden 专属的 FAILURE\_MODES**：

| 类型           | 目标失败模式 | 评估                                |
| ------------ | ------ | --------------------------------- |
| single\_fact | 基础检索失败 | ✅ 有效，直接对应 hit\_rate               |
| multi\_fact  | 多跳检索失败 | ✅ 有效，对应 recall\@k                 |
| reasoning    | 推理能力不足 | ⚠️ 部分有效，当前指标无法直接衡量"推理能力"          |
| comparative  | 对比分析失败 | ⚠️ 部分有效，同上                        |
| missing      | 拒答能力不足 | ✅ 有效，对应 FPR + faithfulness        |
| irrelevant   | 幻觉控制失败 | ✅ 有效，对应 FPR + hallucination\_rate |
| adversarial  | 边界场景翻车 | ⚠️ 部分有效，当前指标无法区分"边界场景失败"和"普通失败"   |

**建议**：

1. `target_failure_mode` 作为元数据保留（有助于人工分析），但不作为评测指标
2. 新增 `failure_mode_coverage` 聚合指标：统计各失败模式是否被"触发"（即该类型问题的指标低于阈值）
3. reasoning/comparative 的"推理能力"评估，可考虑新增 `reasoning_accuracy` 指标（LLM 判断答案是否需要推理、推理是否正确）

#### 2.3.4 双链路融合方案

**方案：统一为"质量等级"策略**

将 Golden/Default 双链路融合为单一生成链路，通过 `quality_level` 参数控制输出质量：

```yaml
test_generation:
  quality_levels:
    quick:       # 原 Default，日常实验用
      num_questions: 20
      type_distribution: {single_fact: 0.30, multi_fact: 0.25, reasoning: 0.15, comparative: 0.15, missing: 0.10, irrelevant: 0.05, adversarial: 0.00}
      enable_dedup: false
      enable_review_metadata: false
      storage: "meal_scoped"        # data/meals/<meal>/test_sets/

    standard:    # 原 Default 增强，重要实验用
      num_questions: 50
      type_distribution: {single_fact: 0.20, multi_fact: 0.20, reasoning: 0.17, comparative: 0.17, missing: 0.13, irrelevant: 0.07, adversarial: 0.06}
      enable_dedup: true
      enable_review_metadata: true
      storage: "meal_scoped"

    golden:      # 原 Golden，项目级基准
      num_questions: 150
      type_distribution: {single_fact: 0.17, multi_fact: 0.20, reasoning: 0.17, comparative: 0.17, missing: 0.13, irrelevant: 0.07, adversarial: 0.10}
      enable_dedup: true
      enable_review_metadata: true
      storage: "project_scoped"      # data/golden_testset/
      require_full_dataset: true
      invalid_policy: "immutable"
```

**融合后的统一入口**：

```python
def generate_test_set(self, meal_name, quality_level="quick", **kwargs):
    config = self.quality_levels[quality_level]
    # 统一走 generate_hybrid_questions()
    # 根据 config 启用/禁用去重、审核元数据等
```

**融合收益**：

1. 消除 `generate_golden_testset()` 与 `generate_hybrid_questions()` 的代码重复
2. 新增 `standard` 质量等级填补 quick(20题) 和 golden(150题) 之间的空白
3. 配置驱动而非硬编码，用户可自定义质量等级
4. 实验配置简化：`quality_level: golden` 替代 `golden: true`

**融合风险**：

1. 需要仔细处理 `require_full_dataset` 逻辑（Golden 需要全量 meal）
2. 需要保持向后兼容（`golden: true` 配置仍需支持）
3. `storage` 差异需要统一管理

**实施建议**：分两阶段

* **阶段 1**（v0.2.0）：将 Golden 的差异点提取为配置参数，`generate_golden_testset()` 内部改为调用统一方法 + 配置覆盖

* **阶段 2**（v0.2.1）：引入 `quality_level` 概念，重构 CLI 和实验配置

***

## 三、实施步骤与优先级

### Phase 1：紧急修复与低成本优化（预估 2-3 天）

| 步骤  | 任务                               | 涉及文件                                | 优先级 |
| --- | -------------------------------- | ----------------------------------- | --- |
| 1.1 | 修复 rejected 题目未过滤 BUG            | test\_set\_manager.py, run\_eval.py | P0  |
| 1.2 | multi\_hop\_candidate\_count 4→3 | config.yaml                         | P0  |
| 1.3 | EVIDENCE\_AWARE\_PROMPT 精简       | test\_generator.py                  | P1  |
| 1.4 | needs\_revision 状态激活             | review\_golden\_testset.py          | P1  |
| 1.5 | 审核进度持久化                          | review\_golden\_testset.py          | P1  |

### Phase 2：指标体系优化（预估 3-4 天）

| 步骤  | 任务                       | 涉及文件                                     | 优先级 |
| --- | ------------------------ | ---------------------------------------- | --- |
| 2.1 | 设计 metrics\_tier 配置      | config.yaml                              | P1  |
| 2.2 | BuiltinEvaluator 支持 tier | builtin\_evaluator.py                    | P1  |
| 2.3 | run\_experiment 支持 tier  | run\_experiment.py                       | P1  |
| 2.4 | 评测 LLM 调用纳入 TokenTracker | builtin\_evaluator.py, token\_tracker.py | P2  |
| 2.5 | segment\_size 自适应        | test\_generator.py                       | P2  |

### Phase 3：审核流程优化（预估 3-4 天）

| 步骤  | 任务                 | 涉及文件                       | 优先级 |
| --- | ------------------ | -------------------------- | --- |
| 3.1 | 实现 auto-approve 机制 | review\_golden\_testset.py | P1  |
| 3.2 | 审计报告与审核联动          | review\_golden\_testset.py | P2  |
| 3.3 | 批量操作支持             | review\_golden\_testset.py | P2  |
| 3.4 | 审核者身份记录            | review\_golden\_testset.py | P3  |

### Phase 4：双链路融合（预估 4-5 天）

| 步骤  | 任务                                       | 涉及文件                                     | 优先级 |
| --- | ---------------------------------------- | ---------------------------------------- | --- |
| 4.1 | Golden 差异点提取为配置参数                        | test\_generator.py, config.yaml          | P2  |
| 4.2 | generate\_golden\_testset 重构为统一方法 + 配置覆盖 | test\_generator.py                       | P2  |
| 4.3 | 移除 Golden 自动生成逻辑                         | test\_set\_manager.py                    | P2  |
| 4.4 | 引入 quality\_level 概念                     | test\_generator.py, config.yaml, main.py | P3  |
| 4.5 | 实验配置向后兼容                                 | run\_experiment.py                       | P3  |

### Phase 5：生成质量提升（预估 3-4 天）

| 步骤  | 任务                    | 涉及文件               | 优先级 |
| --- | --------------------- | ------------------ | --- |
| 5.1 | LLM 自评过滤              | test\_generator.py | P2  |
| 5.2 | 问题多样性增强（embedding 去重） | test\_generator.py | P3  |
| 5.3 | 数值校验扩展                | test\_generator.py | P3  |
| 5.4 | 预验证机制减少无效重试           | test\_generator.py | P2  |

***

## 四、预期收益汇总

| 维度                      | 当前            | 优化后                 | 改善幅度         |
| ----------------------- | ------------- | ------------------- | ------------ |
| 测试集生成 token/题           | \~8,000 input | \~5,000-5,500 input | **-30\~35%** |
| 评测 LLM 调用/题（core tier）  | \~11 次        | \~3 次               | **-73%**     |
| 人工审核工作量（150 题）          | 150 题         | 40-60 题             | **-60%**     |
| 代码重复（Golden vs Default） | 独立方法          | 统一方法 + 配置           | **-200 行**   |
| 指标可观测性                  | 评测 LLM 调用不可见  | 全链路追踪               | 质的飞跃         |
| rejected 题目污染           | 存在            | 已修复                 | BUG 消除       |

***

## 五、风险与缓解

| 风险                                | 概率 | 影响 | 缓解措施                               |
| --------------------------------- | -- | -- | ---------------------------------- |
| segment\_size 缩减影响 evidence 验证通过率 | 中  | 中  | 先 A/B 测试对比通过率，再决定是否全量切换            |
| auto-approve 误放过低质量题              | 低  | 高  | 保守判定规则 + 人工抽检 10% auto\_approved 题 |
| 双链路融合破坏现有实验配置                     | 低  | 高  | 向后兼容层 + 渐进式迁移                      |
| metrics\_tier 导致历史数据不可比           | 中  | 中  | 保留 full tier 作为选项，版本发布时用 full 对标   |

