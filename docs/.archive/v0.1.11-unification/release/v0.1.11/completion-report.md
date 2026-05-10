# v0.1.11 完成报告：链路统一

> 日期：2026-04-26
> 版本：v0.1.11
> 主题：Golden 独立生成链路收编入 TestSetGenerator

---

## 一、解决了什么问题

### 核心问题：两套并行的测试集生成链路

项目存在两套独立的问题生成链路：

| 维度 | 实验系统内部 | Golden 脚本 |
|------|-------------|-------------|
| 位置 | `src/test_generator.py` | `scripts/generate_golden_testset.py` |
| 文档加载 | 通过 MealManager | 直接读 `data/parsed/` |
| Prompt | EVIDENCE_AWARE_PROMPT | GOLDEN_PROMPT |
| 问题类型 | 6 种 | 7 种（多 adversarial） |
| Chunk 定位 | _locate_chunks_by_quote() | locate_source_chunks() |
| 数值校验 | 无 | validate_answer_numerical_accuracy() |
| Excerpt 验证 | 无 | verify_excerpt_in_document() |

这导致：
1. **代码重复**：文档分段、问题分配、LLM 调用、响应解析等逻辑各实现一遍
2. **维护割裂**：修改问题生成方式需要改两处，容易遗漏
3. **路径依赖**：Golden 直接读 `data/parsed/`（已弃用路径），绕过 meal 体系
4. **质量不均**：Golden 有数值校验和 excerpt 验证，内部链路没有

### 次要问题

- **RF-020**：全量测试路径重构（data/parsed→artifacts）
- **FEAT-031**：golden_qa.json 重做与回归测试更新

---

## 二、如何解决

### 设计原则

将 Golden 独有功能分为三类：

**A 类：内部链路也应该这么做 → 所有策略受益**

| # | 功能 | 实现方式 |
|---|------|---------|
| A1 | adversarial 问题类型 | 加入 QUESTION_TYPES，默认分布 0% |
| A2 | 数值精度校验 | _validate_numerical_accuracy()，所有策略自动执行 |
| A3 | 数值换算规则 | 融入 EVIDENCE_AWARE_PROMPT |
| A4 | excerpt 验证 | _verify_excerpt_in_document()，所有策略自动执行 |
| A5 | 质量标记 | excerpt_verified_rate / numerical_correction_rate |

**B 类：只有 golden 需要 → 条件分支，仅 golden 时激活**

| # | 功能 | 实现方式 |
|---|------|---------|
| B1 | 文档去重 | _detect_content_overlaps() + _build_primary_pool() |
| B2 | FAILURE_MODES | target_failure_mode 元数据 |
| B3 | 审计元数据 | reviewed / review_notes / author |
| B4 | 生命周期标记 | user_defined=True, invalid_policy="immutable" |
| B5 | 全量 meal 查找 | MealManager.find_full_dataset_meal() |

**X 类：抛掉不保留**

| # | 功能 | 理由 |
|---|------|------|
| X1 | GOLDEN_PROMPT | 统一用 EVIDENCE_AWARE_PROMPT |
| X2 | locate_source_chunks() | 统一用 _locate_chunks_by_quote() |
| X3 | parse_question_response() | 统一用 _parse_evidence_question_response() |
| X4 | extract_excerpt_core/extract_key_terms | 仅服务于 X2 |
| X5 | 直接读 data/parsed/ | 统一通过 meal artifacts 获取 |

### 实现步骤（8 个 atomic commits）

1. **Step 1**：新增 `MealManager.find_full_dataset_meal()` — 通过全量 data_id 反查 meal
2. **Step 2a**：新增 adversarial 问题类型 [A1]
3. **Step 2b-2e**：新增数值校验 [A2]、prompt 规则 [A3]、excerpt 验证 [A4]、质量标记 [A5]
4. **Step 3**：新增文档去重 [B1]、FAILURE_MODES [B2]、审计元数据 [B3]、生命周期标记 [B4]
5. **Step 4**：新增 `generate_golden_testset()` 主方法
6. **Step 5**：更新 TestSetManager golden 路径（自动生成）
7. **Step 6**：CLI 入口更新（main.py 新增 golden 策略，golden 脚本退化为薄壳）
8. **Step 7-8**：测试迁移 + 清理

---

## 三、如何判定确实修好了

### 1. 全量测试通过

```
1377 passed, 10 skipped, 2 deselected
```

2 个 deselected 是预先存在的失败（与本次修改无关），10 个 skipped 是条件跳过。

### 2. Golden 脚本已精简

- 修改前：1242 行独立生成逻辑
- 修改后：62 行薄 CLI 壳（仅参数解析 + 委托 TestSetGenerator）
- 净删除：1180 行

### 3. 无残留导入

```bash
grep -r "from scripts.generate_golden_testset import" --include="*.py"
# 无结果
```

所有原来从 `scripts.generate_golden_testset` 导入的代码已改为从 `src.test_generator` 导入。

### 4. 新增功能可验证

| 功能 | 验证方法 |
|------|---------|
| adversarial 类型 | `TestSetGenerator.QUESTION_TYPES` 含 "adversarial" |
| 数值校验 | `_validate_numerical_accuracy()` 检测 10x 错误并自动修正 |
| excerpt 验证 | `_verify_excerpt_in_document()` 模糊匹配验证 |
| 文档去重 | `_detect_content_overlaps()` 检测重叠文档 |
| 全量 meal 查找 | `find_full_dataset_meal()` 通过 data_id 反查 |
| Golden 自动生成 | `resolve_test_set(golden=True)` 文件不存在时自动生成 |
| CLI golden 策略 | `--strategy golden` 可用 |

### 5. Lint 通过

```
pixi run lint
# All checks passed!
```

---

## 四、变更文件清单

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `src/test_generator.py` | 修改 | +300 行：adversarial、数值校验、excerpt 验证、文档去重、generate_golden_testset() |
| `src/meal.py` | 修改 | +25 行：find_full_dataset_meal() |
| `src/test_set_manager.py` | 修改 | +8 行：golden 自动生成路径 |
| `scripts/generate_golden_testset.py` | 重写 | 1242→62 行：薄 CLI 壳 |
| `scripts/review_golden_testset.py` | 修改 | 导入改为 TestSetGenerator |
| `main.py` | 修改 | 新增 golden 策略选项 |
| `tests/test_test_generator.py` | 修改 | +130 行：A2/A4/B1 测试 |
| `tests/test_golden_testset.py` | 重写 | 775→443 行：导入改为 TestSetGenerator |
| `tests/test_meal.py` | 修改 | +30 行：find_full_dataset_meal 测试 |

---

## 五、后续注意事项

1. **旧版 golden_150.json 兼容性**：现有 golden 测试集文件格式不变，可继续使用
2. **data/parsed/ 路径**：Golden 不再依赖此路径，但其他代码可能仍在使用，暂不删除
3. **FEAT-039 交互式审查脚本**：review_golden_testset.py 保持独立，不属于生成链路
4. **预先存在的测试失败**：`test_source_files_set_in_generated_questions` 和 `test_supplemental_loop_fills_gap` 在修改前就已失败，非本次引入
