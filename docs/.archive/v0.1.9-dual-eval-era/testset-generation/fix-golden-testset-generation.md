# Plan: 修复 Golden Testset 生成脚本 — 数据源无关的健壮设计

## 设计原则

**核心目标**：不管用户放进来什么数据源、按什么目录组织，都能做到不偏不倚、均匀抽样。

**四条原则**：

1. **不假设目录结构** — 不硬编码年份、公司、行业等分类逻辑，目录可能是按年/按公司/按行业/平铺的任意结构
2. **用内容而非路径做决策** — 文档间关系（如摘要⊆年报）通过内容重叠度检测，而非路径模式匹配
3. **保留 round-robin，修好它的前提** — round-robin 的均匀分散逻辑是对的，翻车是因为 name 碰撞和排序偏置
4. **渐进式分配** — 问题分配策略随 Q/N 比值平滑过渡：文档多问题少→均等，文档少问题多→按内容量比例

***

## 问题回顾

| # | 问题          | 根因                     | 修复思路                    |
| - | ----------- | ---------------------- | ----------------------- |
| 1 | 答案数值 10x 错误 | Prompt 无换算规则 + 验证无数值校验 | Prompt 加规则 + 数值交叉校验     |
| 2 | 文档覆盖偏斜      | 文档名碰撞 + 排序偏置           | 唯一 ID + shuffle + 渐进式分配 |
| 3 | 内容重复文档双倍出题  | 无内容重叠检测                | 内容重叠检测 + 去重池            |

### Round-robin 分析

**引入目的**：将问题类型标签均匀铺到文档上，保证每个文档拿到多样化类型，避免某文档全是 single\_fact。

**翻车原因**（round-robin 本身没错，是它的两个前提坏了）：

1. **前提1 坏了**：`doc_names` 中 9 个公司共享 `"2023年年度报告"` 这个 name → round-robin 把 9 个位置的类型都累积到同一个 dict key 下
2. **前提2 坏了**：主循环按 sorted 文件路径遍历，年报排在研报前面 → 150 题额度在年报就用完了

**修法**：保留 round-robin 的均匀分散逻辑，修好两个前提 + 改用渐进式分配算法。

### 渐进式分配策略

**问题**：硬编码 `max_per_doc=3` 在文档少问题多时成为瓶颈，又对 20 页周报和 300 页年报一视同仁。

**解法**：用幂次加权 `weight = L^p`，其中 `p = max(0, (r-1)/r)`，`r = Q/N`（总题数/文档数）。

**渐进性**：

* `r ≈ 1`（每文档约 1 题）→ `p ≈ 0` → `L^0 = 1` → 均等分配

* `r >> 1`（每文档很多题）→ `p → 1` → `L^1 = L` → 按内容量比例分配

* 中间值平滑过渡，无突变点

**验算**：

| 场景           | r = Q/N | p    | 效果                   |
| ------------ | ------- | ---- | -------------------- |
| 300 文档 150 题 | 0.5     | 0    | 均等，随机选 150 个文档各出 1 题 |
| 150 文档 150 题 | 1       | 0    | 均等，每文档恰好 1 题         |
| 75 文档 150 题  | 2       | 0.5  | L^0.5 = √L，温和分化      |
| 30 文档 150 题  | 5       | 0.8  | 强分化，大文档明显多分          |
| 3 文档 150 题   | 50      | 0.98 | 近乎 L¹，几乎按比例          |

***

## Step 1: 修好 round-robin 的前提 + 渐进式分配（问题 2 & 3）

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

### 1.2 修复排序偏置 — 主循环前 shuffle 文档列表

当前 `load_documents()` 返回 `sorted(rglob(...))` 的结果，年报路径字母序在研报前面。
在主循环开始前 shuffle 文档列表，打破排序偏置：

```python
import random
random.shuffle(primary_docs)
```

### 1.3 重写 `distribute_across_documents()` — 渐进式幂次加权分配

替换原来的 round-robin + 无上限逻辑，改为幂次加权分配：

```python
def distribute_across_documents(
    type_counts: dict[str, int],
    documents: list[dict],
    min_per_doc: int = 1,
    max_per_doc: int | None = None,
    seed: int | None = None,
) -> dict[str, list[str]]:
    """按内容量幂次加权分配问题类型。

    权重 = L^p，其中 p = max(0, (r-1)/r)，r = 总题数/文档数。
    r≈1 时 p≈0（均等分配），r>>1 时 p→1（按比例分配）。
    渐进性：r 从 1 到 ∞，分化程度平滑增强，无突变。

    Args:
        type_counts: 问题类型到数量的映射
        documents: 文档列表，每个需含 doc_id 和 content 字段
        min_per_doc: 每文档最少分配题数（默认 1，确保不遗漏）
        max_per_doc: 每文档最多分配题数（默认 None，不设上限；可设为安全阀）
        seed: 随机种子，可复现

    Returns:
        doc_id → 问题类型列表的映射
    """
```

算法步骤：

1. 计算 `r = Q / N`，`p = max(0, (r-1)/r)`
2. 如果 `r < 1`（文档比问题多）：随机选 Q 个文档，各出 1 题
3. 如果 `r >= 1`：计算每个文档权重 `L_i^p / Σ L_j^p`，按权重分配题数
4. 取整 + 最低保障 `min_per_doc` + 可选 `max_per_doc` + 调整总和
5. 为每个文档的问题槽位，round-robin 填入不同类型（保证类型多样化）

**辅助函数** **`round_allocations()`**：

* 处理取整后的总和偏差（因 min\_per\_doc 和四舍五入）

* 优先从大文档扣减（如果总和偏大）或加给大文档（如果总和偏小）

### 1.4 新增内容重叠检测 — `detect_content_overlaps()`

**不依赖路径模式**，纯基于内容判断文档间关系：

```python
def detect_content_overlaps(
    documents: list[dict], threshold: float = 0.8,
) -> list[tuple[str, str, float]]:
    """检测文档间内容重叠。

    对每对文档，取较短文档的采样片段，检查是否出现在较长文档中。
    如果命中率超过 threshold，标记较短文档为 supplementary。

    算法：
    1. 取较短文本的 3 段采样（前 500 字、中间 500 字、末尾 500 字）
    2. 去空白后做子串匹配
    3. 命中率 > threshold → 标记为 supplementary

    为什么用采样：全文 O(n²) 太慢，3×500 字子串查找足够判断包含关系。

    Returns:
        列表，每项为 (supplementary_doc_id, primary_doc_id, overlap_ratio)
    """
```

### 1.5 构建主文档池 — 排除 supplementary 文档

```python
def build_primary_pool(
    documents: list[dict], overlaps: list[tuple],
) -> list[dict]:
    """构建主文档池，排除被包含的 supplementary 文档。

    如果文档 A 被标记为 B 的 supplementary，则 A 不进入主池。
    如果 A 同时被 B 和 C 标记为 supplementary，只保留 B（较长的那个）。
    """
```

### 1.6 主循环改造

```python
overlaps = detect_content_overlaps(documents)
primary_docs = build_primary_pool(documents, overlaps)
random.shuffle(primary_docs)
doc_plans = distribute_across_documents(type_counts, primary_docs)

for doc_data in primary_docs:
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

### 4.2 渐进式分配测试

* 测试 r < 1 时（文档多问题少）：均等分配，每文档最多 1 题

* 测试 r = 1 时：每文档恰好 1 题

* 测试 r = 2 时（p=0.5）：温和分化，大文档略多

* 测试 r = 5 时（p=0.8）：强分化，大文档明显多分

* 测试 min\_per\_doc 最低保障生效

* 测试 max\_per\_doc 安全阀生效（可选）

* 测试 round-robin 保证类型均匀分散（不出现某文档全是同一类型）

* 测试随机种子可复现

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

* **不扔掉 round-robin**：保留其类型均匀分散逻辑，只修好它依赖的前提

* **不硬编码 max\_per\_doc**：改为渐进式幂次加权分配，max\_per\_doc 仅作可选安全阀
