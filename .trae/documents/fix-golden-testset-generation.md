# Plan: 修复 Golden Testset 生成脚本的三大系统性缺陷

## 问题回顾

| # | 问题 | 根因 | 影响 |
|---|------|------|------|
| 1 | 答案数值 10x 错误 | Prompt 无换算规则 + 验证无数值校验 | 答案不可信 |
| 2 | 0% 研报覆盖 | 文档名碰撞 + 排序偏置 + 无配额控制 | 覆盖面极窄 |
| 3 | 年报/摘要重复出题 | 同名碰撞 + 无内容去重 | 有效题量虚高 |

## 修改范围

- `scripts/generate_golden_testset.py` — 主要修改目标
- `tests/test_golden_testset.py` — 补充对应测试
- `scripts/review_golden_testset.py` — 增加审计报告功能

---

## Step 1: 修复文档名碰撞 + 排序偏置 + 配额控制（问题 2 & 3）

### 1.1 修复 `_load_pages_json()` — 文档名加入公司/年份前缀

当前 `name` 仅用文件 stem（如 `"2023年年度报告"`），9 个公司共享同名。
改为从 `source_path` 中提取公司目录名作为前缀，生成唯一 name：

```
annual_reports/2023/万科A/2023年年度报告.pages.json
→ name = "万科A/2023年年度报告"
```

同理 `load_documents()` 中的 `.md` 文件也做相同处理。

### 1.2 新增 `distribute_across_documents()` 配额控制

当前 round-robin 无配额，年报排前面就吃光所有名额。改为：

1. 将文档按类别分组：`annual_reports_2023`、`annual_reports_2024`、`annual_reports_2025`、`research_reports`
2. 按配额比例分配题目数（默认：年报 60%、研报 40%）
3. 年报内部再按年份分配（2023:2024:2025 = 2:2:1）
4. 每组内 round-robin 分配类型
5. 同一公司的"年报+摘要"视为一个文档组，只从完整年报出题（摘要跳过），除非该公司只有摘要

### 1.3 新增 `classify_documents()` 函数

从 `source_path` 解析文档类别：
- `annual_reports/2023/` → category=`annual_2023`
- `annual_reports/2024/` → category=`annual_2024`
- `annual_reports/2025/` → category=`annual_2025`
- `research_reports/` → category=`research`

同时标记文档是否为摘要（`is_summary=True`），用于后续去重。

### 1.4 新增 `deduplicate_document_groups()` 函数

检测同一公司的年报+摘要对，标记摘要为 `supplementary=True`。
分配题目时优先用完整年报，摘要仅在该公司无完整年报时使用。

---

## Step 2: 修复 10x 数值错误（问题 1）

### 2.1 修改 `GOLDEN_PROMPT` — 增加单位换算指令

在 prompt 的输出格式说明中增加：

```
重要：文档中的财务数据以"元"为单位（如 12,162,684,368.86），
请在答案中换算为"亿元"（÷100,000,000），并确保换算正确。
示例：12,162,684,368.86元 = 121.63亿元（不是1216.3亿元）
```

### 2.2 新增 `validate_answer_numerical_accuracy()` 函数

交叉验证 answer 中的数值与 ground_truth_excerpt 中的原始数字：

1. 从 excerpt 中提取所有 8 位以上的逗号分隔数字（如 `12,162,684,368.86`）
2. 将其换算为亿元
3. 从 answer 中提取所有 `XX亿` 格式的数字
4. 检查 answer 中的数字是否与 excerpt 换算后的数字一致（允许 ±5% 误差）
5. 如果发现 10x 偏差，自动修正 answer 中的数字并记录 warning

### 2.3 在 `validate_question_quality()` 中集成数值校验

在现有校验之后，调用 `validate_answer_numerical_accuracy()`。
如果检测到 10x 错误，自动修正而非拒绝（因为 LLM 生成的其他内容可能很好）。

---

## Step 3: 增强审核工具（review_golden_testset.py）

### 3.1 新增 `audit_testset()` 函数

生成测试集审计报告，输出以下统计：

1. **文档分布**：按类别（年报/研报）、年份、公司统计题目数
2. **数值校验**：标记所有疑似 10x 错误的题目
3. **结构重复**：标记同一公司年报+摘要的重复题对
4. **类型-文档交叉**：标记同一文档同类型超过 2 题的情况
5. **难度分布**：统计 easy/medium/hard 比例
6. **excerpt 验证率**：统计已验证/未验证比例

### 3.2 新增 `--audit` CLI 参数

```bash
pixi run python scripts/review_golden_testset.py --audit
```

仅输出审计报告，不进入交互审核模式。

---

## Step 4: 补充测试

### 4.1 文档名唯一性测试

- 测试 `_load_pages_json()` 生成的 name 包含公司前缀
- 测试同名文件（不同公司）生成不同 name
- 测试 `classify_documents()` 正确分类

### 4.2 配额分配测试

- 测试 `distribute_across_documents()` 按配额分配
- 测试研报获得非零配额
- 测试年报/摘要去重逻辑

### 4.3 数值校验测试

- 测试 `validate_answer_numerical_accuracy()` 检测 10x 错误
- 测试自动修正功能
- 测试正常数值不被误判

### 4.4 审计报告测试

- 测试 `audit_testset()` 输出格式
- 测试各类异常检测

---

## 文件变更清单

| 操作 | 文件 | 说明 |
|------|------|------|
| 修改 | `scripts/generate_golden_testset.py` | 修复三大缺陷 |
| 修改 | `scripts/review_golden_testset.py` | 增加 audit 功能 |
| 修改 | `tests/test_golden_testset.py` | 补充测试 |

## 不做的事

- **不重新生成 golden_150.json**：脚本修复后，由用户决定何时重新生成
- **不修改 src/test_set_manager.py**：golden 加载逻辑无需改动
- **不修改 eval/ 下的评测管线**：评测管线消费 golden set 的方式不变
