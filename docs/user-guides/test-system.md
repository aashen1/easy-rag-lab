# 测试集系统完整指南

<!-- status: active -->

> 创建日期：2026-05-02
> 最后更新：2026-05-02
> 版本：v0.1.16
> 统一 CLI：`pixi run testset <子命令>`

---

## 一、测试集到底是什么

在 RAG 系统中，测试集就是一组「问题 + 标准答案 + 原文出处」的集合。它的作用只有一个：**衡量你的 RAG 系统回答质量好不好**。

打个比方：考试要先出好卷子才能打分。测试集就是你的卷子，RAG 系统就是考生，评测指标就是分数。

一个题目长这样：

```json
{
  "id": "q001",
  "question": "工商银行2024年不良贷款率是多少？",
  "question_type": "单知识点查询",
  "difficulty": "easy",
  "source_files": ["reports/icbc_2024_annual.pdf"],
  "source_chunks": ["chunk_关于资产质量的一段原文"],
  "answer": "工商银行2024年不良贷款率为1.36%。",
  "ground_truth_excerpt": "报告显示，截至报告期末，本行不良贷款率为1.36%。",
  "metadata": {
    "review_status": "approved"
  }
}
```

核心字段：

| 字段 | 什么意思 |
|------|---------|
| `question` | 要问 RAG 系统的问题 |
| `answer` | 标准答案，用来跟 RAG 的回答做对比 |
| `ground_truth_excerpt` | 原文片段，证明答案确实来自文档 |
| `source_files` | 答案来自哪个 PDF |
| `source_chunks` | 答案来自 PDF 的哪个分段 |
| `review_status` | 这道题审过没有：`approved` / `rejected` / `pending` |

---

## 二、为什么要统一

以前测试集有两套概念：「普通测试集」和「黄金测试集」。它们本质上是同一个东西，区别只在于：

- 黄金测试集 = 审过的 + 用全量 PDF 生成的 → 可以跨项目复用
- 普通测试集 = 没审过的 + 用部分 PDF 生成的 → 只在当前数据集内用

这两套东西分散在不同目录、不同命令、不同文档里，维护起来很累。

**统一之后**：所有测试集都是同一类东西，区别只在于两个属性：

| 属性 | 值 | 含义 |
|------|----|------|
| `quality_status` | `draft` → `ai_reviewed` → `human_reviewed` → `approved` | 这道题走过哪些审核阶段 |
| `data_coverage` | `full` / `partial` | 题目覆盖了全部 PDF 还是部分 PDF |

一条规则就够了：**审核通过 + 覆盖全量 PDF = 可以跨项目复用**。不需要再叫什么"黄金"。

---

## 三、一个命令搞定一切

所有测试集操作都在统一的 CLI 下：

```bash
pixi run testset <子命令>
```

可用子命令：

```
generate   机器生成新题目
enrich     AI 预审，自动打分分级
review     人工逐题审核
approve    定稿，标记为审核通过
compose    组合复用（合并、筛选、增量追加）
migrate    把旧的 golden_testset 目录迁移到新目录
```

想看每个命令的详细参数，直接加 `--help`：

```bash
pixi run testset enrich --help
pixi run testset review --help
```

---

## 四、完整工作流：从生成到复用

### 4.1 流程总览

```
生成 ──→ AI预审 ──→ 人工审核 ──→ 定稿 ──→ 组合复用 ──→ 评测
draft     ai_reviewed  human_reviewed  approved   composed
```

每一步都会在 JSON 文件的 `metadata.quality_status` 里留下记录，你能随时知道这份测试集处于哪个阶段。

---

### 4.2 第一步：生成

从 PDF 中自动出题。

```bash
# 生成 30 道 hybrid 策略的题
pixi run testset generate --meal my_meal --strategy hybrid --num 30

# 生成 150 道全量数据集题（覆盖所有 PDF）
pixi run testset generate --meal full_dataset --strategy hybrid --num 150
```

生成出来的测试集放在 `data/<meal_name>/test_sets/` 下，`quality_status` 为 `draft`。

生成策略和题目类型详见 [question-generation.md](question-generation.md)。

---

### 4.3 第二步：AI 预审

把生成的题扔给 LLM 看一眼，自动评分、分级。

```bash
pixi run testset enrich --input data/my_meal/test_sets/hybrid_n30.json

# 自动通过 A 级题目（省人工）
pixi run testset enrich --input data/my_meal/test_sets/hybrid_n30.json --auto-approve-tier-a
```

AI 预审会给每道题打一个 tier：

| Tier | 含义 | 建议 |
|------|------|------|
| **A** | 质量好，答案准确，原文支撑充分 | 可直接自动通过 |
| **B** | 基本可用，有小瑕疵 | 人工扫一眼 |
| **C** | 有问题，可能需要改或删 | 人工重点审 |

加上 `--auto-approve-tier-a` 后，A 级题直接标记为 `auto_approved`，剩下 B/C 级才需要人工审。

---

### 4.4 第三步：人工审核

逐题看，逐题决定。

```bash
# 审核所有题
pixi run testset review --input data/my_meal/test_sets/hybrid_n30.json

# 只审尚未审核的题（跳过已 approved/rejected/auto_approved 的题）
pixi run testset review --input data/my_meal/test_sets/hybrid_n60.json --only-new

# 从第 15 题开始（断点续审）
pixi run testset review --input data/my_meal/test_sets/hybrid_n30.json --start-from 15

# 标记审核人
pixi run testset review --input data/my_meal/test_sets/hybrid_n30.json --reviewer "张三"
```

审核界面会显示：
- 问题内容和类型
- 原文片段
- AI 给的评分和意见
- 相关 chunk 上下文（如果配置了 PDF viewer）

操作选项：

```
[a]pprove  通过，标记为 approved
[r]eject   拒绝，标记为 rejected
[e]dit     编辑题目内容后再通过
[s]kip     跳过不处理
[q]uit     退出（自动保存进度）
```

进度会**每 5 题自动保存一次**，不用担心中断。审核完成后 `quality_status` 自动变为 `human_reviewed`。

---

### 4.5 第四步：定稿

审核完了，正式定稿。

```bash
pixi run testset approve --input data/my_meal/test_sets/hybrid_n30.json
```

这一步会：
1. 把 `quality_status` 设为 `approved`
2. 如果 `data_coverage == "full"`（覆盖了全量 PDF），自动把文件复制到 `data/test_sets/` 目录，标记为 `portable`
3. 记录审计日志

**注意**：一个测试集能不能变成 portable（可跨项目复用），取决于它是否覆盖了全部 PDF。用部分数据集生成的测试集即使审核通过了，也只能在原项目内使用。

---

### 4.6 第五步：组合复用

这是整个系统最实用的功能：**不想重新生成 60 题，只想在上次 30 题的基础上追加 30 题**。

```bash
# 增量追加：在已有 30 题基础上，加上一个新生成的 30 题文件
pixi run testset compose incremental \
  --base data/my_meal/test_sets/hybrid_n30_reviewed.json \
  --supplement-file data/my_meal/test_sets/hybrid_n30_new.json \
  --name hybrid_n60 \
  --meal my_meal

# 多源合并：把两个不同 meal 的测试集合在一起
pixi run testset compose merge \
  --sources meal_a:hybrid_n20 meal_b:document_n15 \
  --name combined_n35 \
  --meal target_meal

# 条件筛选：从 150 题里抽出所有单知识点 + 已通过的题
pixi run testset compose filter \
  --input data/test_sets/financial_reviewed.json \
  --name single_fact_approved \
  --question-type 单知识点查询 \
  --review-status approved \
  --limit 50
```

组合时会自动：
- **去重**：相同或相似的问题只保留一份
- **保留审核状态**：旧题维持 `approved`，新题标记 `draft`
- **记录溯源**：metadata 里会写清楚这份测试集是怎么拼出来的

---

## 五、存储布局

```
data/
├── test_sets/                              ← 可跨项目复用的测试集
│   └── financial_reviewed_2026.json
│
├── golden_testset/                          ← 旧目录，保留兼容
│   └── golden_150.json
│
├── <meal_name>/
│   └── test_sets/                           ← 该项目专属的测试集
│       ├── hybrid_n30.json                  ← draft
│       ├── hybrid_n30.json                  ← human_reviewed
│       └── *.archive.*.json                 ← 备份
```

测试集文件放在哪里取决于它的状态：
- **`data/<meal>/test_sets/`**：还在打磨中的测试集
- **`data/test_sets/`**：审核通过 + 覆盖全量 PDF 的测试集，可以给任意项目用

---

## 六、从旧系统迁移

如果你的项目里有 `data/golden_testset/` 目录，跑一条命令搞定：

```bash
# 先预览会迁移哪些文件
pixi run testset migrate --dry-run

# 正式迁移
pixi run testset migrate
```

迁移后，旧的 `load_golden_testset()` 调用会自动先查新目录、再回退旧目录，不会断。

---

## 七、常见场景速查

### 场景 A：我想从零建一套测试集

```bash
# 1. 机器生成
pixi run testset generate --meal banking --strategy hybrid --num 30

# 2. AI 预审
pixi run testset enrich \
  --input data/banking/test_sets/hybrid_n30.json \
  --auto-approve-tier-a

# 3. 人工审核
pixi run testset review --input data/banking/test_sets/hybrid_n30.json

# 4. 定稿
pixi run testset approve --input data/banking/test_sets/hybrid_n30.json
```

### 场景 B：上次审了 30 题，这次想加到 60 题

```bash
# 1. 另外生成 30 道新题
pixi run testset generate --meal banking --strategy hybrid --num 30 --name hyrbid_n30_batch2

# 2. 跟上次审好的 30 题合并
pixi run testset compose incremental \
  --base data/banking/test_sets/hybrid_n30.json \
  --supplement-file data/banking/test_sets/draft/hybrid_n30_batch2.json \
  --name hybrid_n60 \
  --meal banking

# 3. 只审新增的 30 题
pixi run testset review --input data/banking/test_sets/hybrid_n60.json --only-new

# 4. 定稿
pixi run testset approve --input data/banking/test_sets/hybrid_n60.json
```

### 场景 C：我想把两个项目的测试集合成一个

```bash
pixi run testset compose merge \
  --sources banking:hybrid_n30 insurance:hybrid_n20 \
  --name finance_combined_n50 \
  --meal finance_joint
```

### 场景 D：我想从大测试集里抽一个子集做快速实验

```bash
# 只要单知识点 + 已通过的题，最多 20 道
pixi run testset compose filter \
  --input data/test_sets/financial_reviewed.json \
  --name quick_test_20 \
  --question-type 单知识点查询 \
  --review-status approved \
  --limit 20
```

---

## 八、看懂测试集的 JSON

打开一个测试集文件，你会看到三个顶层部分：

```json
{
  "metadata": {
    "name": "hybrid_n30",
    "meal_id": "abc123",
    "quality_status": "human_reviewed",
    "review_progress": {
      "total": 30,
      "approved": 25,
      "rejected": 2,
      "pending": 3
    },
    "data_coverage": "partial",
    "portable": false,
    "composition": {
      "type": "incremental",
      "base": {"name": "hybrid_n20", "num_questions": 20},
      "supplement": {"num_generated": 10},
      "duplicates_removed": 0
    }
  },
  "quality_metrics": {},
  "questions": [...]
}
```

关键字段解释：

| 字段 | 看什么 |
|------|--------|
| `quality_status` | 测试集当前在哪个阶段 |
| `review_progress` | 多少题过了、多少题拒了、多少还没审 |
| `data_coverage` | `full` 就是覆盖了全部 PDF，`partial` 就是只覆盖了部分 |
| `portable` | `true` 就是可以跨项目用 |
| `composition` | 如果非空，说明这个测试集是通过 compose 拼出来的，这里记录了来源 |

每道题里的 `metadata.review_status` 才是单题级别的审核状态。

---

## 九、和评测系统的对接

测试集最终要喂给评测管线。评测系统会自动读取 `review_status`，**评测时只使用 `approved` 和 `auto_approved` 的题**，`rejected` 的题会被跳过。

所以在实验配置里引用测试集时，你不需要手动筛选，系统会帮你处理：

```yaml
test_sets:
  - name: banking_review
    golden: true
```

---

## 十、相关文档

| 文档 | 内容 |
|------|------|
| [question-generation.md](question-generation.md) | 题目生成的策略和类型详解 |
| [compatibility contract](../dev-guides/test-set-compatibility.md) | 元数据字段兼容性契约（开发者看） |
| [golden-test-review.md](golden-test-review.md) | 旧版审核工具指南（逐步废弃中） |
| [golden-testset-generation.md](golden-testset-generation.md) | 旧版 golden 生成指南（逐步废弃中） |
