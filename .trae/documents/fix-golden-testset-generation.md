# Plan: 修复 Golden Testset 生成脚本 — 数据源无关的健壮设计

## 设计原则

**核心目标**：不管用户放进来什么数据源、按什么目录组织，都能做到不偏不倚、均匀抽样。

**三条原则**：

1. **不假设目录结构** — 不硬编码年份、公司、行业等分类逻辑，目录可能是按年/按公司/按行业/平铺的任意结构
2. **用内容而非路径做决策** — 文档间关系（如摘要⊆年报）通过内容重叠度检测，而非路径模式匹配
3. **均匀随机抽样** — 像用户随机点开一个文档出题一样，每个文档被选中的概率相等

***

## 问题回顾

| # | 问题          | 根因                     | 修复思路                |
| - | ----------- | ---------------------- | ------------------- |
| 1 | 答案数值 10x 错误 | Prompt 无换算规则 + 验证无数值校验 | Prompt 加规则 + 数值交叉校验 |
| 2 | 文档覆盖偏斜      | 文档名碰撞 + 排序偏置           | 唯一 ID + 内容去重 + 随机抽样 |
| 3 | 内容重复文档双倍出题  | 无内容重叠检测                | 内容重叠检测 + 去重池        |

***

## Step 1: 文档身份与去重（问题 2 & 3 的根本修复）

### 1.1 修复文档名碰撞 — 用 source\_path 作唯一 ID

当前 `name` 用文件 stem（如 `"2023年年度报告"`），9 个公司共享同名。
改为 **`source_path`（相对路径）作为唯一标识**，`name` 仅用于展示。

```python
# Before: name = "2023年年度报告"  ← 碰撞
# After:  doc_id = "annual_reports/2023/万科A/2023年年度报告.pages.json"  ← 唯一
#         name  = "2023年年度报告"  ← 仅展示用
```

`_load_pages_json()` 和 `load_documents()` 返回的 dict 增加 `doc_id` 字段，
`distribute_across_documents()` 和主循环全部改用 `doc_id` 作 key。

### 1.2 新增内容重叠检测 — `detect_content_overlaps()`

**不依赖路径模式**，纯基于内容判断文档间关系：

```python
def detect_content_overlaps(documents: list[dict], threshold: float = 0.8) -> list[tuple[str, str, float]]:
    """检测文档间内容重叠。

    对每对文档，计算较短文档内容在较长文档中的覆盖率。
    如果覆盖率超过 threshold，标记为重叠对。

    Returns:
        列表，每项为 (supplementary_doc_id, primary_doc_id, overlap_ratio)
    """
```

算法：

1. 对所有文档对，取较短文本的若干采样片段（如取前 500 字、中间 500 字、末尾 500 字）
2. 检查这些片段是否出现在较长文本中
3. 命中率 > threshold → 标记较短文档为 supplementary

**为什么用采样而非全文比较**：全文比较 O(n²) 太慢。采样 3 段 × 每段 500 字 ≈ 1500 字的子串查找，足够判断包含关系（摘要一定是年报的子集，且包含首尾关键段落）。

### 1.3 构建主文档池 — 排除 supplementary 文档

```python
def build_primary_pool(documents: list[dict], overlaps: list[tuple]) -> list[dict]:
    """构建主文档池，排除被包含的 supplementary 文档。

    如果文档 A 被标记为 B 的 supplementary，则 A 不进入主池。
    如果 A 同时被 B 和 C 标记为 supplementary，只保留 B（较长的那个）。
    """
```

### 1.4 重写 `distribute_across_documents()` — 随机均匀分配

**核心改动**：不再按文档在列表中的位置 round-robin，而是随机打乱后均匀分配。

```python
def distribute_across_documents(
    type_counts: dict[str, int],
    documents: list[dict[str, str]],
    max_per_doc: int = 3,
    seed: int | None = None,
) -> dict[str, list[str]]:
    """将问题类型均匀分配到文档，每文档最多 max_per_doc 个类型。

    1. 随机打乱文档列表
    2. 随机打乱问题类型列表
    3. 轮流分配：每个文档依次拿一个类型，直到类型用完
    4. 每个文档不超过 max_per_doc 个类型
    """
```

关键参数：

* `max_per_doc=3`：每个文档最多出 3 题，防止大文档吃掉所有名额

* `seed`：可复现的随机种子

**效果**：不管目录结构如何，每个文档被选中的概率相等。150 题 ÷ 每文档最多 3 题 = 至少需要 50 个不同文档，自然保证了覆盖面。

### 1.5 主循环改造 — 从主文档池生成

```python
# 伪代码
primary_docs = build_primary_pool(documents, overlaps)
doc_plans = distribute_across_documents(type_counts, primary_docs, max_per_doc=3)

for doc_data in primary_docs:  # 遍历主池（已随机打乱）
    doc_id = doc_data["doc_id"]
    assigned_types = doc_plans.get(doc_id, [])
    ...
```

***

## Step 2: 修复 10x 数值错误（问题 1）

### 2.1 修改 `GOLDEN_PROMPT` — 增加单位换算指令

在 prompt 的输出格式说明中增加：

```
重要数值规则：
- 文档中的财务数据通常以"元"为单位（如 12,162,684,368.86）
- 答案中请换算为"亿元"：÷100,000,000（即去掉8位数字）
- 正确示例：12,162,684,368.86元 = 121.63亿元
- 错误示例：12,162,684,368.86元 ≠ 1216.3亿元（多了10倍）
- 如果原文已用"亿元"为单位，则直接引用，不要再次换算
```

### 2.2 新增 `validate_answer_numerical_accuracy()` 函数

交叉验证 answer 中的数值与 ground\_truth\_excerpt 中的原始数字：

```python
def validate_answer_numerical_accuracy(
    question_data: dict,
) -> tuple[bool, dict | None]:
    """校验答案中的数值与 excerpt 中的原始数字是否一致。

    检测 10x 单位换算错误：excerpt 中以元为单位的大数字，
    answer 中换算为亿元时是否正确。

    Returns:
        (is_valid, correction) — is_valid 为 True 表示数值正确；
        correction 为 None 或包含修正信息的字典。
    """
```

算法：

1. 从 excerpt 中提取所有 8 位以上的逗号分隔数字（如 `12,162,684,368.86`）
2. 将其换算为亿元（÷10⁸）
3. 从 answer 中提取所有 `XX亿` / `XX.X亿` 格式的数字
4. 对每对 (excerpt\_num\_亿, answer\_num\_亿)：

   * 如果 |answer / excerpt| ≈ 10（9.5\~10.5），标记为 10x 错误

   * 如果 |answer / excerpt| ≈ 0.1，也是 10x 错误（反方向）

   * 如果 |answer - excerpt| / excerpt < 0.05，数值一致 ✓
5. 返回校验结果 + 修正建议

### 2.3 在生成流程中集成数值校验

在 `generate_single_question()` 返回结果后、加入 questions 列表前，调用数值校验：

* 如果检测到 10x 错误 → 自动修正 answer 中的数字，记录 warning

* 如果检测到其他数值偏差 → 标记 `metadata.needs_manual_review = True`，仍加入列表

***

## Step 3: 增强审核工具（review\_golden\_testset.py）

### 3.1 新增 `audit_testset()` 函数

生成测试集审计报告，**不假设任何目录结构**，纯基于数据本身统计：

1. **文档分布**：按 source\_file 统计题目数，标记占比 >15% 的文档
2. **数值校验**：对所有含数字的题目运行 `validate_answer_numerical_accuracy()`
3. **内容重复**：检测不同 source\_file 但 key\_entities 高度重叠的题目对
4. **单文档过度集中**：标记同一 source\_file 同类型 >2 题的情况
5. **难度分布**：统计 easy/medium/hard 比例
6. **excerpt 验证率**：统计已验证/未验证比例
7. **问题模式重复**：检测"X年Y的Z是多少？"等模板化问题

### 3.2 新增 `--audit` CLI 参数

```bash
pixi run python scripts/review_golden_testset.py --audit
pixi run python scripts/review_golden_testset.py --audit --input data/golden_testset/golden_150.json
```

仅输出审计报告，不进入交互审核模式。

***

## Step 4: 补充测试

### 4.1 文档唯一性测试

* 测试 `doc_id` 使用 source\_path，同名文件（不同路径）生成不同 doc\_id

* 测试 `detect_content_overlaps()` 检测摘要⊆年报

* 测试 `detect_content_overlaps()` 对无重叠文档返回空列表

* 测试 `build_primary_pool()` 排除 supplementary 文档

### 4.2 均匀分配测试

* 测试 `distribute_across_documents()` 每文档不超过 max\_per\_doc

* 测试随机种子可复现

* 测试文档数少于类型数时的行为

* 测试所有文档都被分配到（无遗漏）

### 4.3 数值校验测试

* 测试 `validate_answer_numerical_accuracy()` 检测 10x 错误

* 测试正确数值不被误判

* 测试 excerpt 无大数字时不报错

* 测试 answer 中无"亿"单位时不报错

### 4.4 审计报告测试

* 测试 `audit_testset()` 输出结构

* 测试各类异常检测

***

## 文件变更清单

| 操作 | 文件                                   | 说明          |
| -- | ------------------------------------ | ----------- |
| 修改 | `scripts/generate_golden_testset.py` | 修复三大缺陷      |
| 修改 | `scripts/review_golden_testset.py`   | 增加 audit 功能 |
| 修改 | `tests/test_golden_testset.py`       | 补充测试        |

## 不做的事

* **不重新生成 golden\_150.json**：脚本修复后，由用户决定何时重新生成

* **不修改 src/test\_set\_manager.py**：golden 加载逻辑无需改动

* **不修改 eval/ 下的评测管线**：评测管线消费 golden set 的方式不变

* **不硬编码任何目录结构假设**：年份、公司、行业等分类逻辑全部从代码中移除

