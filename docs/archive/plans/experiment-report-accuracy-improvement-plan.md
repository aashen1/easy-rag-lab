# 实验报告准确性改进计划

## 问题总结

基于对实验报告 `exp_20260421_215222_baseline_5kpage_ragas_and_builtin` 的分析，发现以下影响结论准确性的问题：

| 优先级 | 问题 | 影响 |
|--------|------|------|
| P0 | source_chunks 过多导致检索指标虚高 | Hit Rate/MRR/NDCG 全部 100%，无法区分检索策略差异 |
| P0 | 特殊问题（缺失/无关）的 LLM retrieval 指标计算错误 | context_precision/context_recall 在不应计算时仍产生值 |
| P1 | answer_correctness 为 NaN | 该指标完全失效 |
| P1 | 样本量仅 10 题 | 统计意义不足 |
| P2 | Ragas 配置不一致 | 降低可复现性 |

---

## 改进计划

### 阶段一：代码修复（我执行）

#### 1.1 收紧 source_chunks 生成逻辑

**文件**: `src/test_generator.py`

**修改内容**:
- 修改 `_locate_answer_chunks` 方法，移除或减少相邻 chunk 扩展
- 增加匹配严格度，只保留真正包含答案关键信息的 chunk

**具体改动**:
```python
# 当前逻辑：adjacent_tolerance=1，会扩展相邻 chunk
# 改为：adjacent_tolerance=0，不扩展

# 同时提高匹配阈值：
# - term_threshold: 2 -> 3 (需要更多关键词匹配)
# - overlap_threshold: 0.5 -> 0.7 (需要更高的句子重叠度)
```

#### 1.2 修复特殊问题的 LLM retrieval 指标计算

**文件**: `eval/run_eval.py`

**修改内容**:
- 在计算 `context_precision` 和 `context_recall` 前，检查 `expect_retrieval` 标志
- 如果 `expect_retrieval=False`，跳过 LLM retrieval 指标计算

**具体改动**:
```python
# 在第 174-209 行的 llm_retrieval 计算逻辑中
# 添加 expect_retrieval 检查
if llm_retrieval_metrics_config and llm_config and contexts:
    if not expect_retrieval:  # 新增检查
        logger.info(f"Skipping LLM retrieval metrics for test case {test_case['id']} (expect_retrieval=False)")
    else:
        # 原有的 context_precision 和 context_recall 计算逻辑
```

#### 1.3 修复 Ragas 配置合并问题

**文件**: `eval/run_experiment.py` (或相关配置合并逻辑)

**修改内容**:
- 确保实验配置中的 `backends` 正确传递到 Ragas evaluator
- 当 `backends` 包含 `ragas` 时，自动设置 `ragas.enabled=True`

---

### 阶段二：重新生成测试集（我执行）

修改代码后，需要重新生成测试集以应用新的 source_chunks 逻辑：

```bash
# 删除旧测试集
rm -rf data/meals/m_5kpage/test_sets/doc_n10.json

# 重新生成测试集（使用相同配置）
pixi run python main.py --generate-test-set 5kpage --strategy document --num-questions 10
```

---

### 阶段三：需要用户准备的改进

#### 3.1 增加问题数量

**当前**: 10 题
**建议**: 30-50 题

**操作方式**:
```yaml
# 在实验配置中修改
test_sets:
  - name: doc_n50
    on_missing: auto
    generation:
      strategy: document
      num_questions: 50  # 从 10 改为 50
```

#### 3.2 精修问题集（可选但推荐）

如果需要更高质量的测试集，用户可以：
1. 导出当前测试集
2. 人工审核每个问题的：
   - 问题表述是否清晰
   - 答案是否准确
   - source_files 是否正确
3. 重新导入精修后的测试集

---

## 执行顺序

```
[我执行] 1. 修改 _locate_answer_chunks 方法，收紧 source_chunks
[我执行] 2. 修改 run_eval.py，修复特殊问题的指标计算
[我执行] 3. 检查 Ragas 配置合并逻辑
[我执行] 4. 重新生成测试集
[我执行] 5. 重新运行实验
[用户决定] 6. 是否增加问题数量到 30-50 题？
```

---

## 预期效果

修复后：
- Hit Rate/MRR/NDCG 将反映真实的检索能力，而非虚高的 100%
- 特殊问题（缺失/无关）将正确地不计算检索指标
- 实验结论将具有更高的可信度

---

## 待用户确认

1. **问题数量**: 是否将问题数量从 10 增加到 30-50？
2. **精修问题集**: 是否需要人工审核问题质量？
