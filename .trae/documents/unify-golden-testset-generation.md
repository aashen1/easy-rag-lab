# Plan: 统一测试集生成链路 — 收编 Golden 到 TestSetGenerator

## 目标

将 `scripts/generate_golden_testset.py` 中的独立生成逻辑收编到 `src/test_generator.py` 的 `TestSetGenerator` 中，实现统一的测试集生成入口。Golden 脚本退化为薄 CLI 壳。

## 原则

- **好用的留下**：Golden 独有的有价值设计迁入内部链路
- **不好用的抛掉**：Golden 自搞一套的文档加载、chunk 定位、prompt 体系，统一用内部链路已有的
- **全量 meal 替代 data/parsed**：Golden 不再直接读 `data/parsed/`，改为找到全量 PDF 对应的 meal

---

## Golden 独有功能分类

逐项分析 Golden 相对于内部链路的独有设计，分为两类：

### A 类：内部链路也应该这么做 → 直接并入，所有策略受益

| # | 功能 | 理由 |
|---|------|------|
| A1 | **adversarial 问题类型** | 对抗性问题是评估 RAG 系统边界能力的重要类型，任何测试集都可能需要。加入 QUESTION_TYPES，默认分布 0%（不强制使用），但用户可通过 type_distribution 配置启用 |
| A2 | **数值精度校验 `validate_answer_numerical_accuracy()`** | 检测元→亿元 10 倍换算错误。这是金融 QA 的通用痛点，任何策略生成的测试集都可能出这种错。应作为 `_validate_numerical_accuracy()` 并入，在所有策略的生成后自动执行 |
| A3 | **Prompt 中的数值换算规则** | GOLDEN_PROMPT 中明确写了"元÷1e8=亿元"的正确/错误示例。这个规则对金融场景的任何问题生成都有效，应融入 EVIDENCE_AWARE_PROMPT |
| A4 | **excerpt 验证 `verify_excerpt_in_document()`** | 验证 LLM 输出的 ground_truth_excerpt 确实存在于文档原文中。当前内部链路的 `_validate_evidence()` 只验证 quote 在 segment 中，不验证 excerpt 在完整文档中。这是额外的质量保障层，所有策略都应启用 |
| A5 | **`excerpt_verified` 和 `numerical_auto_corrected` 质量标记** | 作为质量指标写入问题元数据，对所有策略都有诊断价值。应纳入 `_calculate_hybrid_quality_metrics()` 的指标计算 |

### B 类：只有 golden 需要的 → 作为 golden 条件分支，仅 golden 时激活

| # | 功能 | 理由 |
|---|------|------|
| B1 | **文档去重 `detect_content_overlaps()` + `build_primary_pool()`** | Golden 从全量文档池生成，可能存在年报摘要 vs 完整年报的重叠。普通策略绑定 meal，文档已由 meal 定义，无需去重。仅在 golden 策略下激活 |
| B2 | **`FAILURE_MODES` / `target_failure_mode`** | 每种问题类型对应的 RAG 失败模式描述（如"基础检索失败""幻觉控制失败"）。这是 golden 集用于定向评估的标注，普通测试集不需要。仅在 golden 策略下写入问题元数据 |
| B3 | **审计元数据 `reviewed` / `review_notes` / `author`** | Golden 集需要人工审核流程（reviewed=False → 审核后改为 True）。普通测试集是机器生成的，不需要审核标记。仅在 golden 策略下写入 |
| B4 | **`user_defined=True`, `invalid_policy="immutable"`** | Golden 集作为项目级资产，不应被自动清洗修改。普通测试集是机器生成的，可以被清洗/补充。仅在 golden 策略下设置 |
| B5 | **全量 meal 查找** | Golden 需要找到包含所有 PDF 的 meal 来获取文档。普通策略直接用传入的 meal_name。仅在 golden 策略下执行 |

### 抛掉不保留的

| # | 功能 | 理由 |
|---|------|------|
| X1 | **GOLDEN_PROMPT** | 统一使用 EVIDENCE_AWARE_PROMPT + 类型 supplement，数值规则融入 A3 |
| X2 | **`locate_source_chunks()`** | 统一使用 `_locate_chunks_by_quote()`，已有更完善的模糊匹配 |
| X3 | **`parse_question_response()`** | 统一使用 `_parse_evidence_question_response()` |
| X4 | **`extract_excerpt_core()` / `extract_key_terms_from_excerpt()`** | 仅服务于 X2，随 X2 一起废弃 |
| X5 | **直接读 `data/parsed/` / `data/chunks/`** | 统一通过 meal 的 artifacts 获取 |

---

## Step 1: 在 MealManager 中新增 `find_full_dataset_meal()` 方法 [B5]

**文件**: `src/meal.py`

当前项目中没有"从全量 data_id 反查 meal"的现成方法。需要新增：

```python
def find_full_dataset_meal(self) -> MealConfig | None:
    """Find the meal that contains all PDFs in raw_dir.

    Computes the full data_id from raw_dir, then searches all meals
    for one with a matching data_id.

    Returns:
        MealConfig if found, None otherwise.
    """
    cache = ArtifactCache(
        Path(self.config.get("artifacts", {}).get("dir", "data/artifacts")),
        Path(self.config.get("parser", {}).get("input_dir", "data/raw")),
    )
    try:
        full_data_id = cache._compute_full_data_id()
    except ValueError:
        return None

    equivalents = self.find_equivalent_meals(full_data_id)
    return equivalents[0] if equivalents else None
```

**测试**: 在 `tests/test_meal.py` 中新增 `TestFindFullDatasetMeal` 测试类。

**同时验证 BUG-026 修复**: 确认 `ArtifactCache.is_full_parsed_valid()` 在 `pipeline.py` 修复后能正确命中缓存。

---

## Step 2: A 类功能并入内部链路（所有策略受益）

### 2a: 新增 `adversarial` 问题类型 [A1]

**文件**: `src/test_generator.py`

- 在 `QUESTION_TYPES` 中添加 `"adversarial": "对抗性问题"`
- 在 `TYPE_DISTRIBUTION` 中添加 `"adversarial": 0.00`（默认不启用，用户可配置）
- 新增 `EVIDENCE_ADVERSARIAL_SUPPLEMENT` 常量（从 Golden 的 `ADVERSARIAL_INSTRUCTION` 适配，融入 evidence 体系）
- 在 `EVIDENCE_QUESTION_TYPE_SUPPLEMENTS` 中注册 `adversarial`
- 在 `_select_segments_for_question_type()` 中添加 adversarial 选段逻辑（选 1-2 个 segment）
- 在 `_generate_hybrid_question()` 中添加 adversarial 特殊处理

### 2b: 新增 `_validate_numerical_accuracy()` 方法 [A2]

**文件**: `src/test_generator.py`

从 Golden 的 `validate_answer_numerical_accuracy()` 迁入，适配为实例方法。在 `_generate_hybrid_question()` 的生成后自动调用，检测并自动修正 10 倍换算错误。所有策略均受益。

### 2c: 数值换算规则融入 Prompt [A3]

**文件**: `src/test_generator.py`

在 `EVIDENCE_AWARE_PROMPT` 的"生成要求"部分追加数值换算规则段落（从 GOLDEN_PROMPT 提取）：

```
重要数值规则：
- 文档中的财务数据通常以"元"为单位（如 12,162,684,368.86）
- 答案中请换算为"亿元"：÷100,000,000（即去掉8位数字）
- 正确示例：12,162,684,368.86元 = 121.63亿元
- 错误示例：12,162,684,368.86元 ≠ 1216.3亿元（多了10倍）
- 如果原文已用"亿元"为单位，则直接引用，不要再次换算
```

### 2d: 新增 `_verify_excerpt_in_document()` 方法 [A4]

**文件**: `src/test_generator.py`

从 Golden 的 `verify_excerpt_in_document()` 迁入。在 `_generate_hybrid_question()` 中，对非 irrelevant 类型的问题，在 evidence 验证通过后追加 excerpt 验证。所有策略均受益。

### 2e: 质量标记纳入指标 [A5]

**文件**: `src/test_generator.py`

- 在问题元数据中写入 `excerpt_verified` 和 `numerical_auto_corrected` 标记
- 在 `_calculate_hybrid_quality_metrics()` 中新增 `excerpt_verified_rate` 和 `numerical_correction_rate` 指标

---

## Step 3: B 类功能作为 golden 条件分支

### 3a: 文档去重 [B1]

**文件**: `src/test_generator.py`

从 Golden 迁入 `_detect_content_overlaps()` 和 `_build_primary_pool()` 作为实例方法。仅在 `generate_golden_testset()` 中调用，普通策略不调用。

### 3b: FAILURE_MODES 和 target_failure_mode [B2]

**文件**: `src/test_generator.py`

- 新增 `FAILURE_MODES` 类常量
- 在 `generate_golden_testset()` 中，对每个生成的问题写入 `target_failure_mode`

### 3c: 审计元数据 [B3]

**文件**: `src/test_generator.py`

在 `generate_golden_testset()` 中，对每个问题写入 `reviewed=False`、`review_notes=""`、`author="llm_assisted"`。

### 3d: 生命周期标记 [B4]

**文件**: `src/test_generator.py`

在 `generate_golden_testset()` 中，设置 `user_defined=True`、`invalid_policy="immutable"`。

---

## Step 4: 新增 `generate_golden_testset()` 方法

**文件**: `src/test_generator.py`

```python
def generate_golden_testset(
    self,
    num_questions: int = 150,
    name: str = "golden_150",
    llm_preset: str = "default",
    token_tracker: Any | None = None,
    type_distribution: dict[str, float] | None = None,
    seed: int | None = None,
) -> dict[str, Any]:
```

**流程**：
1. 通过 `MealManager.find_full_dataset_meal()` 找到全量 PDF 对应的 meal [B5]
2. 若找不到，抛出明确错误（提示用户先创建全量 meal）
3. 从该 meal 的 artifacts 中加载文档和 chunks（复用 `_load_full_documents()` 和 `_load_document_chunks()`）
4. 调用 `_detect_content_overlaps()` + `_build_primary_pool()` 过滤补充文档 [B1]
5. 使用 golden 类型分布（含 adversarial 10%），调用 `_calculate_question_distribution()` + `_distribute_questions_across_docs()`
6. 主循环：对每个文档的每个类型调用 `_generate_hybrid_question()`（复用已有逻辑，自动享受 A2/A4 的增强）
7. 生成后追加 golden 专属步骤：
   - 写入 `target_failure_mode` [B2]
   - 写入审计元数据 `reviewed`/`review_notes`/`author` [B3]
8. 补充循环（复用已有逻辑）
9. 计算质量指标 + 构建 TestSetMetadata（`user_defined=True`, `invalid_policy="immutable"` [B4]）
10. 通过 `TestSetManager` 保存到 `data/golden_testset/`

**关键设计决策**：
- 复用 `_generate_hybrid_question()` 而非 Golden 的 `generate_single_question()`，因为前者已有完善的 evidence 验证和 chunk 定位
- Golden 的 `GOLDEN_PROMPT` 不保留 [X1]，统一使用 `EVIDENCE_AWARE_PROMPT` + adversarial supplement
- Golden 的 `locate_source_chunks()` 不保留 [X2]，统一使用 `_locate_chunks_by_quote()`

---

## Step 5: 更新 TestSetManager 的 golden 路径

**文件**: `src/test_set_manager.py`

当前 `resolve_test_set()` 中 `golden: true` 直接调用 `load_golden_testset()` 加载固定文件。保持加载路径不变。

新增：当 `golden: true` 且文件不存在时，调用 `generator.generate_golden_testset()` 自动生成（而非直接报错）。

---

## Step 6: 更新 CLI 入口

**文件**: `main.py`

在 `--generate-test-set` 的 `--strategy` 选项中新增 `golden`。

**文件**: `scripts/generate_golden_testset.py`

退化为薄 CLI 壳，仅做参数解析 + 调用 `TestSetGenerator.generate_golden_testset()`。

---

## Step 7: 迁移测试

**文件**: `tests/test_golden_testset.py`

当前测试从 `scripts.generate_golden_testset` 导入函数。迁移后改为从 `src.test_generator` 导入：

| 原测试类 | 迁移目标 |
|----------|----------|
| `TestGoldenSchema` | → 测试 `TestSetGenerator.QUESTION_TYPES` 含 adversarial |
| `TestDistributeAcrossDocuments` | → 合并到已有的 `_distribute_questions_across_docs()` 测试 |
| `TestDetectContentOverlaps` | → 测试 `TestSetGenerator._detect_content_overlaps()` |
| `TestBuildPrimaryPool` | → 测试 `TestSetGenerator._build_primary_pool()` |
| `TestValidateAnswerNumericalAccuracy` | → 测试 `TestSetGenerator._validate_numerical_accuracy()` |
| `TestParseQuestionResponse` | → 删除 [X3] |
| `TestValidateQuestionQuality` | → 合并到已有的 `_validate_question_quality()` 测试 |
| `TestVerifyExcerptInDocument` | → 测试 `TestSetGenerator._verify_excerpt_in_document()` |
| `TestLocateSourceChunks` | → 删除 [X2] |
| `TestTestSetManagerGolden` | → 保留，测试 `TestSetManager.load_golden_testset()` |
| `TestAuditTestset` | → 保留，测试 `review_golden_testset.py` |

**文件**: `tests/test_test_generator.py`

新增 `TestGenerateGoldenTestset` 测试类，覆盖 golden 策略的完整流程（mock LLM）。

---

## Step 8: 清理

- **删除** Golden 脚本中的独立生成逻辑（`generate_golden_testset()` 主函数、`generate_single_question()`、`parse_question_response()`、`locate_source_chunks()`、`extract_excerpt_core()`、`extract_key_terms_from_excerpt()` 等）[X1-X5]
- **保留** `scripts/review_golden_testset.py`（交互式审计工具，不属于生成链路）
- **保留** `scripts/reset_review_status.py`（审计辅助工具）
- **保留** `scripts/generate_golden_testset.py` 作为薄 CLI 壳
- 更新 `CLAUDE.md` 中的版本状态

---

## 执行顺序

1. Step 1: `MealManager.find_full_dataset_meal()` + 测试 + 验证 BUG-026
2. Step 2a: adversarial 类型支持 [A1] + 测试
3. Step 2b-2e: 数值校验 [A2] / 数值 prompt [A3] / excerpt 验证 [A4] / 质量标记 [A5] + 测试
4. Step 3a-3d: 文档去重 [B1] / FAILURE_MODES [B2] / 审计元数据 [B3] / 生命周期标记 [B4] + 测试
5. Step 4: `generate_golden_testset()` 主方法 + 测试
6. Step 5: `TestSetManager` golden 路径更新 + 测试
7. Step 6: CLI 入口更新
8. Step 7: 测试迁移
9. Step 8: 清理

每步完成后立即提交，遵循 atomic commit 规范。
