# Golden Testset 生成操作指南

<!-- status: active -->

> 创建日期：2026-04-25
> 版本：v0.1.9
> 关联脚本: [`scripts/generate_golden_testset.py`](../../scripts/generate_golden_testset.py)
> 关联审核: [`scripts/review_golden_testset.py`](../../scripts/review_golden_testset.py)

## 概述

本文档描述如何使用 LLM 辅助脚本生成 Golden Testset 初版，以及后续人工精修的工作流。

核心思路：**脚本生成初版 → 审计报告定位问题 → 人工精修 → 迭代**。脚本负责保证覆盖面和结构性质量，人工负责答案准确性和题目深度。

## 前置条件

1. **PDF 已解析**：`data/parsed/` 目录下有 `.pages.json` 或 `.md` 文件
2. **API Key 已配置**：`.env` 中有 LLM API Key（参见 `.env.example`）
3. **config.yaml 已配置**：`llm_presets` 下有所需的模型配置

## 第一步：小规模试跑

正式生成前，先用 5 题验证流程通畅：

```bash
pixi run python scripts/generate_golden_testset.py \
  --num-questions 5 \
  --seed 42 \
  --output data/golden_testset/golden_test_small.json
```

检查输出文件是否正常生成，题目格式是否正确。

## 第二步：正式生成

```bash
pixi run python scripts/generate_golden_testset.py \
  --num-questions 150 \
  --seed 42
```

### 参数说明

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--num-questions` | 150 | 生成题目总数 |
| `--seed` | None | 随机种子，设相同值可复现文档分配结果 |
| `--llm-preset` | default | 使用的 LLM 预设名称（对应 config.yaml） |
| `--output` | data/golden_testset/golden_150.json | 输出路径 |
| `--parsed-dir` | data/parsed | 解析后文档目录 |
| `--chunks-dir` | data/chunks | Chunks 目录 |

### 生成流程

```
load_documents()
    ↓
detect_content_overlaps()    ← 检测摘要⊆年报等包含关系
    ↓
build_primary_pool()         ← 排除 supplementary 文档
    ↓
shuffle(primary_docs)        ← 打乱顺序，打破排序偏置
    ↓
distribute_across_documents() ← 渐进式幂次加权分配
    ↓
for each doc + type:
    generate_single_question()  ← LLM 生成
    validate_answer_numerical_accuracy()  ← 10x 数值校验 + 自动修正
    verify_excerpt_in_document()  ← excerpt 原文验证
    ↓
补充不足题目（如有）
    ↓
输出 JSON
```

### 渐进式分配策略

问题分配采用幂次加权算法，根据题目/文档比自动调节分化程度：

- `weight = L^p`，其中 `p = max(0, (r-1)/r)`，`r = 总题数/文档数`
- `r ≈ 1`（文档多问题少）→ 均等分配
- `r >> 1`（文档少问题多）→ 按内容量比例分配
- 过渡平滑，无突变点

| 场景 | r | p | 效果 |
|------|---|---|------|
| 300 文档 150 题 | 0.5 | 0 | 随机选 150 个文档各出 1 题 |
| 150 文档 150 题 | 1 | 0 | 每文档恰好 1 题 |
| 75 文档 150 题 | 2 | 0.5 | 温和分化 |
| 30 文档 150 题 | 5 | 0.8 | 强分化，大文档多出题 |

## 第三步：审计

生成后立即运行审计，定位结构性问题：

```bash
pixi run python scripts/review_golden_testset.py --audit
```

### 审计报告维度

| 维度 | 检查内容 |
|------|---------|
| 文档分布 | 每个文档的题目数，标记占比 >15% 的偏斜文档 |
| 数值校验 | 检测 10x 单位换算错误（元→亿元） |
| 内容重复 | 不同文档但 key_entities 高度重叠的题目对 |
| 文档集中度 | 同一文档同一类型 >2 题的情况 |
| 难度分布 | easy/medium/hard 比例 |
| Excerpt 验证率 | 已验证/未验证比例 |
| 模板模式 | "X年Y的Z是多少？"等重复句式 |

### 审计报告示例

```
================================================================================
  Golden Test Set Audit Report
  File: data/golden_testset/golden_150.json
  Total Questions: 150
================================================================================

--- Document Distribution ---
  Unique source files: 52
  Top 10:
    annual_reports/2023/万科A/2023年年度报告.pages.json: 5 (3.3%)
    ...

--- Numerical Accuracy ---
  Issues found: 0

--- Content Duplication ---
  Potential duplicate groups: 2
    ...
================================================================================
```

## 第四步：人工精修

审计通过后，进入交互式精修：

```bash
pixi run python scripts/review_golden_testset.py
```

### 精修重点清单

| 优先级 | 检查项 | 方法 |
|--------|--------|------|
| P0 | 数值准确性 | 打开原文 PDF，核对 answer 中的数字 |
| P0 | missing 题验证 | 确认信息确实不存在于文档中（而非 LLM 没找到） |
| P1 | adversarial 题纠正 | 确认 answer 正确反驳了问题中的错误前提 |
| P1 | comparative 题质量 | 确认是真正的跨实体对比，而非同公司同比 |
| P2 | reasoning 题深度 | 确认推理链 >1 步，不是简单的"为什么X增长？" |
| P2 | excerpt 完整性 | 补充过短的 excerpt（<50 字），确保可用于 context_precision 评测 |
| P3 | difficulty 标注 | 补充 hard 难度题（当前生成偏向 easy/medium） |

### 交互式操作

```
Question 1/150: golden_001
Q: 万科2023年净利润是多少？
A: 121.63亿元
Type: single_fact | Difficulty: easy

[a]pprove  [r]evise  [j]reject  [s]kip  [q]uit
```

- **approve**：标记 `reviewed=True`，进入下一题
- **revise**：编辑 question/answer/excerpt 等字段
- **reject**：删除该题（最终补充新题）
- **skip**：跳过，留待后续处理

## 第五步：迭代

精修完成后，如需补充被删除的题目：

```bash
# 重新生成（会覆盖），或手动补充后用 --audit 再审
pixi run python scripts/review_golden_testset.py --audit
```

## 常见问题

### Q: 生成时 API 报错怎么办？

脚本会自动跳过失败的题目并记录日志。生成结束后会尝试补充不足的题目。如果最终题目数仍不够，可提高 `--num-questions` 的值（如设为 160 以留出余量）。

### Q: 如何保留旧版本？

用 `--output` 指定新路径：

```bash
pixi run python scripts/generate_golden_testset.py \
  --num-questions 150 --seed 42 \
  --output data/golden_testset/golden_150_v2.json
```

### Q: 文档目录结构不同怎么办？

脚本不假设任何目录结构。文档名碰撞通过 `source_path`（相对路径）解决，文档覆盖通过 shuffle + 渐进式分配保证。无论文档按年/按公司/按行业/平铺组织，都能均匀抽样。

### Q: 如何只对特定文档出题？

目前不支持文档过滤。如需限定范围，可临时将目标文档放入独立目录，用 `--parsed-dir` 指定。

## 设计决策记录

| 决策 | 选择 | 理由 |
|------|------|------|
| 文档唯一标识 | source_path（相对路径） | 文件 stem 会碰撞（9 个公司共享"2023年年度报告"） |
| 分配算法 | 幂次加权 L^p | r≈1 均等，r>>1 按比例，平滑过渡 |
| 内容去重 | 3 段采样子串匹配 | 不依赖路径模式，纯内容判断 |
| 数值校验 | answer vs excerpt 交叉验证 | LLM 系统性 10x 错误需脚本兜底 |
| max_per_doc | 默认不设上限 | 文档少问题多时不应人为限制 |

## 相关文档

- [TestSet 管理系统](test-set-management.md) — 测试集生命周期管理
- [评测指标详解](evaluation-metrics.md) — 各指标的含义和计算方式
- [问题生成指南](question-generation.md) — 文档级问题生成策略
