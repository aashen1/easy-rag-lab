# 实验报告指标问题修复计划

## 问题概述

实验报告 `exp_20260424_232234_baseline_evaluation` 中存在以下指标问题：

| 优先级 | 问题                | 类型      | 说明                                          |
| --- | ----------------- | ------- | ------------------------------------------- |
| P0  | FPR = 1.0 被错误解读   | 指标语义错误  | LLM 报告把 FPR=1.0 说成"所有检索到的文档都被确认为相关"，实际是最差表现 |
| P1  | Chunk-level 指标未报告 | 数据结构不匹配 | 原始数据存在 chunk-level 指标，但报告中显示 N/A            |

## 修复任务

### 任务 1: 修复 FPR 指标语义解读

**问题**：LLM 生成的报告中，FPR = 1.0 被错误解读为"所有检索到的文档都被确认为相关"。

**正确语义**：

* FPR (False Positive Rate) = 检索到的无关文档数 / top-k

* FPR = 1.0 表示"系统面对无关问题时，100% 的 top-k 槽位都被无关结果填充"——是**最差**表现

* FPR = 0.0 表示"系统正确地没有返回任何结果"——是**最佳**表现

**修复方案**：在 `LLM_REPORT_PROMPT_TEMPLATE` 中添加 FPR 指标的明确说明。

**修改文件**：`eval/experiment_reporter.py`

**修改内容**：

```python
# 在 LLM_REPORT_PROMPT_TEMPLATE 中添加 FPR 指标说明
"""
- **False Positive Rate (FPR)**: 仅对无关问题计算。衡量系统面对无关问题时"有多安静"。
  - FPR = 0.0 表示系统正确地没有返回任何结果（最佳）
  - FPR = 1.0 表示系统返回了满额的无关结果（最差）
  - FPR > 0.3 应视为警告，表明系统无法有效拒绝无关问题
"""
```

### 任务 2: 修复 Chunk-level 指标数据获取

**问题**：原始 JSON 数据中 chunk-level 指标存储在 `chunk_level_metrics` 子对象中：

```json
"retrieval_metrics": {
  "avg_hit_rate": 0.9474,
  "chunk_level_metrics": {
    "avg_hit_rate": 0.8333,
    "avg_mrr": 0.5833,
    "avg_ndcg": 0.4261
  }
}
```

但报告代码使用 `metrics.get("avg_chunk_hit_rate")` 获取，导致返回 `None`。

**修复方案**：修改数据获取逻辑，从正确的路径读取 chunk-level 指标。

**修改文件**：`eval/experiment_reporter.py`

**修改内容**：

1. 在 `_generate_variant_comparison_table_section` 方法中修复 chunk 指标获取
2. 在 `_generate_best_variant_section` 方法中修复 chunk 指标获取
3. 在 `_generate_variant_recommendations_section` 方法中修复 chunk 指标获取

**修改示例**：

```python
# 修改前
chunk_hr = metrics.get("avg_chunk_hit_rate")

# 修改后
chunk_metrics = metrics.get("chunk_level_metrics", {})
chunk_hr = chunk_metrics.get("avg_hit_rate") if chunk_metrics else None
```

### 任务 3: 更新 inbox 文档状态

**问题**：`docs/inbox/一个关于FPR的bug，及两种修复方案.md` 中描述的 `missing` 类型 `expect_retrieval` bug 已经被修复（代码中已设为 `True`）。

**修复方案**：将该文档移动到 `docs/inbox-processed/` 并在 `docs/inbox-log.md` 中记录处理结果。

## 实施步骤

1. 修改 `eval/experiment_reporter.py`：

   * 更新 `LLM_REPORT_PROMPT_TEMPLATE` 添加 FPR 指标说明

   * 修复 `_generate_variant_comparison_table_section` 中的 chunk 指标获取

   * 修复 `_generate_best_variant_section` 中的 chunk 指标获取

   * 修复 `_generate_variant_recommendations_section` 中的 chunk 指标获取

2. 更新项目文档：

   * 移动 `docs/inbox/一个关于FPR的bug，及两种修复方案.md` 到 `docs/inbox-processed/`

   * 更新 `docs/inbox-log.md`

3. 运行 lint 检查

4. 提交代码

## 预期结果

修复后：

1. LLM 生成的报告将正确解读 FPR 指标，FPR > 0.3 会触发警告
2. Chunk-level 指标将正确显示在报告中（Hit Rate: 0.8333, MRR: 0.5833, NDCG: 0.4261）
3. 文档系统保持整洁
