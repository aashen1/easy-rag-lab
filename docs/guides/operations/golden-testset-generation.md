# Golden Testset 生成操作指南

<!-- status: active -->

> 创建日期：2026-04-25
> 最后更新：2026-04-26
> 版本：v0.1.8
> 核心模块: [`src/test_generator.py`](../../src/test_generator.py) → `TestSetGenerator.generate_golden_testset()`
> CLI 入口: [`scripts/generate_golden_testset.py`](../../scripts/generate_golden_testset.py)
> 审核工具: [`scripts/review_golden_testset.py`](../../scripts/review_golden_testset.py)

## 概述

本文档描述如何使用统一的 TestSetGenerator 生成 Golden Testset，以及后续人工精修的工作流。

核心思路：**脚本生成初版 → 审计报告定位问题 → 人工精修 → 迭代**。脚本负责保证覆盖面和结构性质量，人工负责答案准确性和题目深度。

> **v0.1.11 变更**：Golden 生成逻辑已收编入 `TestSetGenerator.generate_golden_testset()`，不再使用独立的 `scripts/generate_golden_testset.py` 中的生成逻辑。该脚本现为薄 CLI 壳，仅做参数解析后委托给 TestSetGenerator。所有问题生成策略（hybrid/document/golden）共享同一套核心逻辑。

## 前置条件

1. **全量 meal 已创建**：需要有一个包含所有 PDF 的 meal（sampling=1.0）。Golden 生成通过 `MealManager.find_full_dataset_meal()` 自动查找
2. **API Key 已配置**：`.env` 中有 LLM API Key（参见 `.env.example`）
3. **config.yaml 已配置**：`llm_presets` 下有所需的模型配置

## 第一步：小规模试跑

正式生成前，先用 5 题验证流程通畅：

```bash
pixi run python scripts/generate_golden_testset.py \
  --num-questions 5 \
  --seed 42 \
  --name golden_test_small
```

或通过主 CLI：

```bash
pixi run python main.py \
  --generate-test-set golden \
  --strategy golden \
  --num-questions 5 \
  --seed 42
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
| `--name` | golden_150 | 测试集名称 |
| `--seed` | None | 随机种子，设相同值可复现 |
| `--llm-preset` | default | 使用的 LLM 预设名称（对应 config.yaml） |

### 生成流程

```
MealManager.find_full_dataset_meal()  ← 自动查找全量 PDF meal
    ↓
_load_full_documents() + _load_document_chunks()  ← 从 meal artifacts 加载
    ↓
_detect_content_overlaps()    ← 检测摘要⊆年报等包含关系
    ↓
_build_primary_pool()         ← 排除 supplementary 文档
    ↓
_calculate_question_distribution()  ← 按 GOLDEN_TYPE_DISTRIBUTION 分配
    ↓
_distribute_questions_across_docs() ← 轮询分配到各文档
    ↓
for each doc + type:
    _generate_hybrid_question()  ← 复用内部链路核心逻辑
    _validate_numerical_accuracy()  ← 10x 数值校验 + 自动修正
    _verify_excerpt_in_document()  ← excerpt 原文验证
    附加 golden 元数据（target_failure_mode, reviewed, author）
    ↓
补充不足题目（如有）
    ↓
保存到 data/golden_testset/{name}.json
```

### Golden 类型分布

| 类型 | 占比 | 说明 |
|------|------|------|
| single_fact | 17% | 单知识点查询 |
| multi_fact | 20% | 多知识点综合 |
| reasoning | 17% | 推理型问题 |
| comparative | 17% | 对比分析 |
| missing | 13% | 缺失知识点 |
| irrelevant | 7% | 无关问题 |
| adversarial | 10% | 对抗性问题（边界场景） |

### 与普通策略的差异

| 维度 | 普通策略（hybrid/document） | Golden 策略 |
|------|---------------------------|-------------|
| 文档来源 | 绑定指定 meal | 自动查找全量 PDF meal |
| 文档去重 | 不执行 | 执行内容重叠检测 |
| adversarial 类型 | 默认 0%（可配置） | 10% |
| 审计元数据 | 无 | reviewed/author/target_failure_mode |
| 生命周期 | user_defined=False | user_defined=True, invalid_policy="immutable" |
| 保存位置 | data/meals/{meal}/test_sets/ | data/golden_testset/ |

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

## 第五步：恢复状态

如果要撤销某次精修，可以使用重置脚本：

```bash
pixi run python scripts/reset_review_status.py data/golden_testset/golden_150.json
```

## 常见问题

### Q: 生成时报"No full-dataset meal found"怎么办？

需要先创建一个包含所有 PDF 的 meal：

```bash
pixi run python main.py --create-meal golden_full --sampling 1.0
```

### Q: 生成时 API 报错怎么办？

脚本会自动跳过失败的题目并记录日志。生成结束后会尝试补充不足的题目。如果最终题目数仍不够，可提高 `--num-questions` 的值（如设为 160 以留出余量）。

### Q: 如何保留旧版本？

用 `--name` 指定新名称：

```bash
pixi run python scripts/generate_golden_testset.py \
  --num-questions 150 --seed 42 \
  --name golden_150_v2
```

### Q: 如何只对特定文档出题？

目前不支持文档过滤。建议创建一个只包含目标文档的 meal，然后使用 `--strategy hybrid` 生成。

## 设计决策记录

| 决策 | 选择 | 理由 |
|------|------|------|
| 生成逻辑归属 | 收编入 TestSetGenerator | 消除重复代码，统一维护入口 |
| 文档唯一标识 | source_path（相对路径） | 文件 stem 会碰撞（9 个公司共享"2023年年度报告"） |
| 内容去重 | 3 段采样子串匹配 | 不依赖路径模式，纯内容判断 |
| 数值校验 | answer vs excerpt 交叉验证 | LLM 系统性 10x 错误需脚本兜底 |
| adversarial 类型 | 默认 0%，golden 10% | 普通策略可选启用，golden 必须包含 |
| 全量 meal 查找 | data_id 反查 | 替代直接读 data/parsed/，与 meal 体系一致 |

## 相关文档

- [Golden Testset 审核工具指南](golden-test-review.md) — 交互式审核、AI预审、PDF定位
- [TestSet 管理系统](test-set-management.md) — 测试集生命周期管理
- [评测指标详解](evaluation-metrics.md) — 各指标的含义和计算方式
- [问题生成指南](question-generation.md) — 文档级问题生成策略
