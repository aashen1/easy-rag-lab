好问题，让我把 FPR 的语义和两种方案的区别讲清楚。

## FPR 是什么

FPR（False Positive Rate）在这个系统里的定义是：**当一个问题不应该检索到任何文档时，系统仍然检索了多少文档的比例**。

具体公式（[fpr.py](file:///b:/project/ash-easy-rag/eval/metrics/fpr.py)）：

```
FPR = len(top_k_results) / k
```

- 系统对无关问题检索了 5 个文档 → FPR = 5/5 = 1.0（全都是误报，最差）
- 系统对无关问题检索了 0 个文档 → FPR = 0/5 = 0.0（正确地什么都没检索，最好）
- 系统对无关问题检索了 2 个文档 → FPR = 2/5 = 0.4

**FPR 衡量的是"检索系统在不该检索时有多安静"**——理想情况下，面对一个与语料库完全无关的问题，系统应该拒绝返回任何结果。

## 两种问题类型的区别

|                         | `irrelevant`（无关问题）         | `missing`（缺失知识点）    |
| ----------------------- | -------------------------------- | -------------------------- |
| 例子                    | "美联储加息对恒瑞医药股价的影响" | "工商银行净息差下降的原因" |
| 文档是否相关            | ❌ 语料库中没有任何相关文档       | ✅ 工商银行年报是相关文档   |
| 期望检索                | 不应该检索到任何文档             | **应该检索到工商银行年报** |
| 期望回答                | 无法回答                         | 无法回答（答案不在文档中） |
| 当前 `expect_retrieval` | False ✅ 正确                     | False ❌ **错误**           |

关键矛盾在 `missing` 类型：**文档应该被检索到，只是答案无法从文档中得出**。但当前代码把 `missing` 和 `irrelevant` 同等对待，都设为 `expect_retrieval=False`。

## 当前 FPR 的问题

以 q019（工商银行净息差）为例：

```
expected_sources: ["工商银行2025年度报告摘要.pages.json"]  ← 有期望文档
expect_retrieval: False  ← 但标记为不期望检索
实际检索结果: ["工商银行2025年度报告摘要", "平安银行...", ...]  ← 检索到了正确文档
FPR = 5/5 = 1.0  ← 被判定为"全部误报"
```

这显然不合理——系统检索到了正确的工商银行年报，却被当成误报。

## 两种修复方案的区别

### 方案 A：从源头修（随 Bug 1 一起）

把 `missing` 类型的 `expect_retrieval` 改为 `True`：

```python
# test_generator.py
elif q_type == "missing":
    qa["source_files"] = [source_path]
    qa["source_chunks"] = []
    qa["expect_no_answer"] = True
    qa["expect_retrieval"] = True   # 改为 True
```

这样 FPR 的计算逻辑完全不用动——`expect_retrieval=True` 的问题不会进入 FPR 分支，FPR 自然只对 `irrelevant` 计算。同时 `missing` 类型会正确计算 hit_rate/MRR（因为文档应该被检索到）。

**优点**：改动最小，语义正确，一处修改解决两个 bug
**缺点**：无

### 方案 B：不动 `expect_retrieval`，改 FPR 计算逻辑

保持 `missing` 的 `expect_retrieval=False`，但让 FPR 计算时考虑 `expected_sources`：

```python
# fpr.py - 对 missing 类型，用 expected_sources 做真正的 FP 判断
if expected_sources:
    # missing 类型：检索到 expected_sources 中的文档不算误报
    true_positives = len(set(top_k) & set(expected_sources))
    false_positives = len(top_k) - true_positives
    return false_positives / k
else:
    # irrelevant 类型：所有检索结果都是误报
    return len(top_k) / k
```

**优点**：不改变 `expect_retrieval` 的语义
**缺点**：
- 改动更大，需要把 `expected_sources` 传入 FPR 计算函数
- `missing` 类型仍然不计算 hit_rate/MRR（因为 `expect_retrieval=False`），这是 Bug 1 的问题
- 本质上是绕过 Bug 1 做局部修补，治标不治本

## 结论

**方案 A 明显更优**。FPR 这个指标的设计初衷就是只对 `irrelevant` 计算的——"系统面对完全无关的问题时，有多安静"。`missing` 类型的问题根本不应该进入 FPR 的计算范围，因为它们有相关文档应该被检索到。

方案 B 看起来给了 `missing` 一个"更合理的 FPR"，但 FPR 对 `missing` 类型本身就没有意义——`missing` 类型应该用 hit_rate/MRR 来衡量检索质量，而不是 FPR。

---

> **处理状态**: ✅ 已修复
> **处理时间**: 2026-04-25
> **修复方案**: 采用方案 A，`missing` 类型的 `expect_retrieval` 已在 `test_generator.py` 中设为 `True`
