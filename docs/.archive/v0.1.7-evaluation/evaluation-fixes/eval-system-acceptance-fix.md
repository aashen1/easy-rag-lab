# 评测系统验收与修复计划

## 问题总览

基于对上次对话（分析RAG实验指标优化）所做的修复进行验收，发现以下问题需要修复：

***

## 问题〇：上次修复的整体评价

### 已完成的修复（质量合格）

1. **NDCG Bug 修复** ✅ — 去重逻辑正确，钳位到 \[0,1] 范围，符合业界标准
2. **Context Precision / Context Recall 新增** ✅ — 分别对齐 DeepEval 和 RAGAS 的实现方式
3. **指标集成到评测流程** ✅ — run\_eval.py 和 run\_experiment.py 已支持

### 存在的问题

1. **filter\_valid\_questions 设计方向错误** — 详见问题一
2. **filter\_valid\_questions 实际未集成** — 虽然代码写了，但 run\_eval.py 和 run\_experiment.py 都没有调用它，等于是个摆设
3. **config\_snapshot 信息不完整** — 详见问题三
4. **通用配置与实验配置杂糅** — 详见问题二

***

## 问题一：filter\_valid\_questions 方向错误 → 从源头修复问题生成

### 深度调研结论

经过对问题生成流程的完整追踪，发现：

1. **正常问题类型（single\_fact/multi\_fact/reasoning/comparative）**：

   * `_load_full_documents()` 通过 `meal_config.pdf_files` 过滤文档，只加载属于 meal 的文档

   * 生成问题时 `source_files = [source_path]`，source\_path 来自已加载的文档

   * **结论**：正常问题类型的 source\_files 一定属于 meal，不存在"生成的问题不在 meal 中"的问题

2. **irrelevant 类型（无关问题，5%占比）**：

   * 这类问题**故意**与文档主题无关，测试系统的拒答能力

   * **当前 Bug**：`source_files` 仍然被设为 `[source_path]`（生成该问题的文档路径）

   * **后果**：评测时检查该文档是否在检索结果中，但由于问题无关，检索器不会返回该文档 → hit\_rate=0，**错误地拉低了整体指标**

   * **正确做法**：`source_files` 应为空列表，表示"不期望检索到任何相关文档"

3. **missing 类型（缺失知识点，10%占比）**：

   * 这类问题询问文档中没有的信息，测试系统处理"不知道"的能力

   * source\_files 保留为 `[source_path]` 是合理的（文档主题相关，检索器可能正确返回该文档）

   * 但需要在评测时标记 `expect_no_answer = True`，以便生成指标正确评估"拒答"行为

### 修复方案

**核心思路**：不是"过滤无效问题"，而是"让问题生成时就正确设置 source\_files"

1. **删除** `validate_question()`、`filter_valid_questions()` 函数和 `QuestionValidity` 数据类

2. **修改** **`generate_document_based_questions()`**：

   * 对 `irrelevant` 类型问题：设置 `source_files = []`，添加 `expect_retrieval = False` 标记

   * 对 `missing` 类型问题：保留 `source_files = [source_path]`，添加 `expect_no_answer = True` 标记

   * 对其他类型：保持 `source_files = [source_path]` 不变

3. **修改** **`evaluate_test_set()`**：

   * 对 `expect_retrieval = False` 的问题：跳过检索指标计算（hit\_rate/mrr/ndcg 不适用）

   * 对 `expect_no_answer = True` 的问题：检索指标正常计算，但生成指标需要特殊处理（faithfulness 应检查是否正确拒答）

   * 在聚合指标时，区分"适用检索指标的问题数"和"总问题数"

4. **删除对应的测试用例** `test_metrics.py` 中的 `TestValidateQuestion` 和 `TestFilterValidQuestions`

5. **新增测试**：验证 irrelevant 问题的 source\_files 为空，missing 问题的 expect\_no\_answer 标记

### 涉及文件

* `eval/metrics.py` — 删除 validate\_question, filter\_valid\_questions, QuestionValidity

* `src/test_generator.py` — 修改 source\_files 设置逻辑，添加标记字段

* `eval/run_experiment.py` — 修改 evaluate\_test\_set 和 compute\_aggregate\_metrics 处理特殊标记

* `tests/test_metrics.py` — 删除相关测试

* `tests/test_test_generator.py` — 新增测试

***

## 问题二：通用配置与实验配置杂糅 → 重构 config.yaml 为最小基线

### 现状分析

* `config.yaml` 中 `retrieval.method: "vector"` 但同时包含了 `bm25`、`hybrid`、`reranker`、`query_rewrite` 等高级功能的配置

* `reranker.enabled: false` 和 `query_rewrite.enabled: false` 虽然默认关闭，但参数都写在那里

* **核心问题**：实验配置（`exp_configs/`）中的 `config_overrides` 只能覆盖，不能"删除"通用配置中已有的字段

* **结果**：做"加与不加重排序"的对比实验时，需要在 variant 中显式设置 `reranker.enabled: false`，这很反直觉——基线应该默认什么高级功能都不开

### 修复方案

1. **重构** **`config.yaml`**：将默认配置设为最小基线

   * `retrieval.method: "vector"` ✅ 已是

   * `retrieval.reranker.enabled: false` ✅ 已是

   * `retrieval.query_rewrite.enabled: false` ✅ 已是

   * **关键变更**：在 `config.yaml` 中增加注释说明"这是最小基线配置，高级功能通过实验配置的 config\_overrides 开启"

   * **实际影响**：当前 config.yaml 的默认值已经是关闭高级功能的，所以功能上没有问题。问题在于**认知上的混淆**——用户看到 config.yaml 中有 bm25/hybrid/reranker/query\_rewrite 的参数，会误以为这些功能默认开启

2. **在实验报告中增加"技术选型摘要"**：在报告的配置部分，用简洁的表格或列表明确列出该实验使用了哪些技术：

   ```
   技术选型:
   - 检索方式: vector (纯向量)
   - 重排序: 未启用
   - 查询改写: 未启用
   - 混合检索: 未启用
   ```

3. **更新实验配置模板**：在 `_complete.yaml` 和其他模板中增加注释，说明 config\_overrides 的用法

### 涉及文件

* `config.yaml` — 增加注释说明最小基线原则

* `eval/experiment_reporter.py` — 增加技术选型摘要

* `exp_configs/templates/_complete.yaml` — 增加注释

***

## 问题三：config\_snapshot 信息不完整 → 保存完整合并配置

### 现状分析

* **实验级 config\_snapshot.yaml**（保存到实验目录根）：只包含 `data`、`evaluation`、`llm`、`test_sets`，完全没有技术选型信息

* **变体级 config\_snapshot**（保存在 `results/<variant>.json` 中）：包含 `merged` 字段，但只有 `chunker`、`embedding`、`retrieval` 三个段落

* **缺失信息**：

  * `parser` 配置（PDF 解析参数）

  * `vector_store` 配置（向量存储类型、距离度量等）

  * `llm_presets` 配置（使用的 LLM 模型信息）

  * `active_mode` 配置

  * `retrieval` 中虽然有，但报告渲染时嵌套字典显示为 Python dict 字符串，不直观

### 修复方案

1. **实验级 config\_snapshot.yaml**：保存完整的合并后配置（merged\_config），而不仅仅是实验配置的子集

   * 包含所有段落：parser, chunker, embedding, vector\_store, retrieval, llm\_presets, active\_mode, experiments, meals, artifacts, test\_generation, token\_cost, logging

   * 但**排除敏感信息**：llm\_presets 中的 api\_key 字段需要脱敏（替换为 "\*\*\*"）

2. **变体级 config\_snapshot**：同样保存完整的 merged\_config，增加 `parser`、`vector_store` 等缺失段落

3. **报告渲染优化**：

   * 改进 YAML 格式渲染，支持任意深度嵌套

   * 增加技术选型摘要（与问题二联动）

### 涉及文件

* `eval/run_experiment.py` — 修改 config\_snapshot 的构建逻辑

* `eval/experiment_reporter.py` — 改进配置渲染，增加技术选型摘要

***

## 实施步骤

### Step 1: 删除 filter\_valid\_questions 相关代码

* 删除 `eval/metrics.py` 中的 `QuestionValidity`、`validate_question()`、`filter_valid_questions()`

* 删除 `tests/test_metrics.py` 中对应的测试类

* 运行测试确认无回归

### Step 2: 修复问题生成的 source\_files 设置

* 修改 `src/test_generator.py`：

  * `irrelevant` 类型：`source_files = []`，添加 `expect_retrieval = False`

  * `missing` 类型：保留 `source_files`，添加 `expect_no_answer = True`

* 修改 `eval/run_experiment.py` 的 `evaluate_test_set()`：

  * 跳过 `expect_retrieval = False` 问题的检索指标

  * 对 `expect_no_answer = True` 问题的生成指标做特殊处理

* 修改 `compute_aggregate_metrics()` 区分适用/不适用检索指标的问题

* 新增测试验证

### Step 3: 重构 config\_snapshot 为完整配置

* 修改 `eval/run_experiment.py` 中实验级和变体级的 config\_snapshot 构建逻辑

* 保存完整的 merged\_config，脱敏 api\_key

* 确保 config\_snapshot.yaml 包含所有技术选型信息

### Step 4: 增加技术选型摘要到实验报告

* 在 `eval/experiment_reporter.py` 中增加技术选型摘要生成逻辑

* 改进配置渲染，支持任意深度嵌套的 YAML 格式

### Step 5: 更新 config.yaml 注释和模板

* 在 `config.yaml` 中增加最小基线原则的注释

* 更新实验配置模板的注释

### Step 6: 运行完整测试并提交

* 运行 pytest 确认所有测试通过

* 逐步骤提交
