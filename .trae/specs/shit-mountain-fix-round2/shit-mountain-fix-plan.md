# 屎山修复计划

> 基于 2026-04-29 屎山复审报告，综合评分从 3/10 降至 2/10，但仍有 12 个问题待修复。
> 本计划按优先级排序，每个步骤包含具体的修改范围、操作细节和验收标准。

---

## 修复总览

| # | 优先级 | 问题 | 预估改动量 | 涉及文件数 |
|---|--------|------|-----------|-----------|
| 1 | P0 | `ExperimentResult` 同名冲突 | 小 | 4 |
| 2 | P0 | `test_generation/generator.py` 进一步拆分 | 大 | ~10 |
| 3 | P0 | `experiment_reporter.py` 拆分 | 大 | ~8 |
| 4 | P1 | `meal/manager.py` 抽取模板方法 | 中 | 2 |
| 5 | P1 | `BuiltinEvaluator` LSP 修复 | 中 | 4 |
| 6 | P1 | `test_generation/` 内部 DRY | 中 | 5 |
| 7 | P2 | `test_set_manager.py` 清洗策略独立 | 中 | 3 |
| 8 | P2 | `DEFAULT_EVAL_CONFIG` 统一 | 小 | 3 |
| 9 | P3 | `_` 前缀规范化 | 小 | 2 |
| 10 | P3 | `cache.py` 返回值修复 | 小 | 1 |
| 11 | P3 | `manager.py` 内部 `import json` | 小 | 1 |

---

## 步骤 1：`ExperimentResult` 同名冲突（P0）

### 问题

`src/experiment.py` 和 `eval/experiment_reporter.py` 各自定义了 `ExperimentResult`，字段完全不同、语义完全不同。当前没有文件同时导入两者，但命名冲突是维护风险。

### 修改方案

将 `eval/experiment_reporter.py` 中的 `ExperimentResult` 重命名为 `ReportExperimentResult`。

### 具体操作

1. **`eval/experiment_reporter.py`**：
   - L61：`class ExperimentResult` → `class ReportExperimentResult`
   - L79：`from_dict` 返回类型注解 `"ExperimentResult"` → `"ReportExperimentResult"`
   - L354, L1121, L1135, L1146, L1152, L1165, L1192, L1219, L1296, L1371, L1434, L1598, L1612, L1684：所有 `result: ExperimentResult` 参数类型 → `result: ReportExperimentResult`

2. **`tests/test_experiment_reporter.py`**：
   - L8：`from eval.experiment_reporter import ... ExperimentResult ...` → `... ReportExperimentResult ...`
   - L47, L103, L117, L134, L215, L699, L888：所有 `ExperimentResult` 引用 → `ReportExperimentResult`

3. **`tests/test_e2e_experiment.py`**：
   - L897：`from eval.experiment_reporter import ExperimentResult` → `... ReportExperimentResult`
   - L921：`ExperimentResult.from_dict(...)` → `ReportExperimentResult.from_dict(...)`

4. **`src/test_generator.py`**（旧入口 re-export）：
   - 检查是否导出了 `ExperimentResult`，如有则同步更新

### 验收标准

- `grep -r "ExperimentResult" src/ eval/ tests/` 只返回 `src/experiment.py` 中的定义和引用
- `pixi run pytest tests/test_experiment_reporter.py tests/test_e2e_experiment.py -x` 通过

---

## 步骤 2：`test_generation/generator.py` 进一步拆分（P0）

### 问题

`generator.py` 3617 行、66 个方法，仍是全项目最大的单文件。包含 25 个薄包装方法、文档加载逻辑、分段逻辑、LLM 调用逻辑等可独立模块。

### 修改方案

拆分为 4 个新子模块 + 瘦身后的 generator.py：

```
src/test_generation/
  generator.py          ← 保留核心编排逻辑（~1200 行）
  document_loader.py    ← 新建：文档加载逻辑（~400 行）
  segment_builder.py    ← 新建：文档分段逻辑（~450 行）
  llm_caller.py         ← 新建：LLM 调用与响应解析（~350 行）
  models.py             ← 已有：增加 domain_keywords / PROPER_NOUN_SUFFIXES 常量
  prompts.py            ← 已有：不变
  chunk_locator.py      ← 已有：删除 deprecated 函数
  validators.py         ← 已有：不变
```

### 具体操作

#### 2a. 提取常量到 `models.py`

在 `models.py` 中新增：

```python
DOMAIN_KEYWORDS = [
    "增长", "下降", "上升", "减少", "增加",
    "收入", "利润", "营收", "市值", "占比",
    "规模", "产量", "销量", "价格", "成本",
    "投资", "融资", "估值", "盈利", "亏损",
    "负债", "资产", "现金流", "毛利率", "净利率",
    "ROE", "ROA",
]

PROPER_NOUN_SUFFIXES = [
    "股份", "集团", "公司", "行业", "市场",
    "技术", "产品", "业务", "报告", "年度",
]

PROPER_NOUN_PATTERN = (
    r"[\u4e00-\u9fff]{2,8}(?:"
    + "|".join(PROPER_NOUN_SUFFIXES)
    + ")"
)
```

然后修改 `generator.py`、`chunk_locator.py`、`validators.py` 中的三处重复定义，统一引用 `models.py` 的常量。

- **generator.py L569-572, L575-601**：删除内联的 `proper_nouns` 和 `domain_keywords`，改为 `from src.test_generation.models import DOMAIN_KEYWORDS, PROPER_NOUN_PATTERN`
- **chunk_locator.py L486-489, L492-520, L440-458**：同上
- **validators.py L274-277, L278**：同上

#### 2b. 新建 `document_loader.py`

从 `generator.py` 提取以下方法为独立函数：

| 原方法 | 新函数名 |
|--------|---------|
| `_resolve_parsed_dir` | `resolve_parsed_dir` |
| `_resolve_chunks_dir` | `resolve_chunks_dir` |
| `_load_meal_chunks` | `load_meal_chunks` |
| `_load_document_chunks` | `load_document_chunks` |
| `_load_document_pages` | `load_document_pages` |
| `_load_full_documents` | `load_full_documents` |
| `_load_pages_json_documents` | `load_pages_json_documents` |
| `_load_md_documents` | `load_md_documents` |

这些方法不依赖 `self` 状态（或只依赖 `self.config`，可改为参数传入），适合提取为纯函数。

#### 2c. 新建 `segment_builder.py`

从 `generator.py` 提取以下方法为独立函数：

| 原方法 | 新函数名 |
|--------|---------|
| `_segment_document` | `segment_document` |
| `_build_segments_from_pages` | `build_segments_from_pages` |
| `_compact_segments` | `compact_segments` |
| `_select_segments_for_question_type` | `select_segments_for_question_type` |
| `_select_candidate_segments` | `select_candidate_segments` |
| `_select_diverse_segments` | `select_diverse_segments` |
| `_parse_segment_selection` | `parse_segment_selection` |
| `_validate_segment_relevance` | `validate_segment_relevance` |
| `_extract_segment_keywords` | `extract_segment_keywords` |

#### 2d. 新建 `llm_caller.py`

从 `generator.py` 提取以下方法为独立函数：

| 原方法 | 新函数名 |
|--------|---------|
| `_generate_question_with_llm` | `generate_question_with_llm` |
| `_parse_llm_response` | `parse_llm_response` |
| `_generate_question_with_evidence` | `generate_question_with_evidence` |
| `_parse_evidence_question_response` | `parse_evidence_question_response` |
| `_generate_single_document_question` | `generate_single_document_question` |
| `_parse_document_question_response` | `parse_document_question_response` |
| `_generate_missing_question` | `generate_missing_question` |
| `_generate_irrelevant_question` | `generate_irrelevant_question` |

同时提取通用的 JSON 解析逻辑为 `parse_json_response(response, required_fields, defaults)` 函数，消除三个 `_parse_*_response` 方法的重复。

#### 2e. 删除薄包装方法

在 `generator.py` 中删除 25 个薄包装方法，将所有调用点改为直接使用子模块函数。

具体来说，将：
```python
self._validate_numerical_accuracy(question_data)
```
改为：
```python
from src.test_generation.validators import validate_numerical_accuracy
validate_numerical_accuracy(question_data)
```

注意：需要同时清理 `generator.py` 顶部约 70 行的 `import ... as _xxx_standalone` 别名导入。

#### 2f. 提取验证后处理方法

将 `generate_hybrid_questions` 和 `generate_golden_testset` 中重复的验证代码块提取为 `_post_process_question` 方法：

```python
def _post_process_question(
    self,
    qa: dict,
    doc_content: str,
    seen_questions: set,
    *,
    check_answer_consistency: bool = False,
    golden_metadata: dict | None = None,
) -> bool:
```

返回 `True` 表示问题通过验证并已加入 `seen_questions`，`False` 表示问题被过滤。

#### 2g. 更新 `__init__.py` 和 `test_generator.py`

- `__init__.py`：导出新增的子模块公共 API
- `test_generator.py`：更新 re-export 列表

#### 2h. 删除 `chunk_locator.py` 中的 deprecated 函数

删除以下已标记 deprecated 的函数（约 250 行）：
- `texts_overlap` (L125)
- `map_segments_to_chunks` (L165)
- `locate_chunks_by_quote` (L277)
- `locate_multi_hop_chunks` (L364)
- `locate_answer_chunks` (L576)

先全局搜索确认无调用点，再删除。

### 验收标准

- `generator.py` 行数 ≤ 1500
- 无薄包装方法（`_validate_numerical_accuracy` 等委托调用全部消除）
- `domain_keywords` / `PROPER_NOUN_PATTERN` 只在 `models.py` 中定义一次
- `parse_json_response` 通用方法替代三个 `_parse_*_response` 的重复逻辑
- `_post_process_question` 替代 4 处验证代码块
- `pixi run pytest tests/test_test_generator.py tests/test_generator.py -x` 通过
- `pixi run lint` 通过

---

## 步骤 3：`experiment_reporter.py` 拆分（P0）

### 问题

`experiment_reporter.py` 1779 行，`ExperimentReporter` 类约 1594 行、35 个方法，承担了 6 个独立职责。

### 修改方案

拆分为 `eval/reporter/` 包：

```
eval/reporter/
  __init__.py            ← 统一导出
  models.py              ← TestCaseResult, VariantResult, ReportExperimentResult
  template_single.py     ← 单变体模板报告生成
  template_variant.py    ← 多变体对比模板报告生成
  llm_reporter.py        ← LLM 增强报告 + 客户端管理
  formatters.py          ← _dict_to_yaml_lines, _generate_tech_summary, metric 辅助
```

### 具体操作

#### 3a. 新建 `eval/reporter/models.py`

提取以下数据类：
- `TestCaseResult`（原 L19-34）
- `VariantResult`（原 L36-59）
- `ReportExperimentResult`（原 L61-119，使用步骤 1 的新名称）

#### 3b. 新建 `eval/reporter/formatters.py`

提取以下工具方法：
- `_dict_to_yaml_lines`
- `_generate_tech_summary`
- `_get_generation_metric`
- 指标描述/解读的共享逻辑（消除 `_generate_conclusion_section` 和 `_generate_variant_recommendations_section` 中的重复阈值判断）

#### 3c. 新建 `eval/reporter/template_single.py`

提取单变体模板报告生成逻辑：
- `_generate_template_report`
- `_generate_header`
- `_generate_overview_section`
- `_generate_data_section`
- `_generate_config_section`
- `_generate_test_set_section`
- `_generate_results_section`
- `_generate_comparison_table`
- `_generate_conclusion_section`
- `_generate_assets_section`

封装为 `TemplateSingleReporter` 类或独立函数集合。

#### 3d. 新建 `eval/reporter/template_variant.py`

提取多变体对比模板报告生成逻辑：
- `_generate_variant_comparison_template`
- `_generate_variant_comparison_table_section`
- `_generate_best_variant_section`
- `_generate_variant_details_section`
- `_generate_variant_recommendations_section`

封装为 `TemplateVariantReporter` 类或独立函数集合。

#### 3e. 新建 `eval/reporter/llm_reporter.py`

提取 LLM 增强报告逻辑：
- `_generate_llm_report`
- `_build_llm_prompt`
- `_call_llm`
- `_init_llm_client`
- `_format_llm_report`
- `_build_variant_comparison_llm_prompt`
- `_format_variant_comparison_llm_report`

封装为 `LLMReporter` 类。

#### 3f. 新建 `eval/reporter/__init__.py`

统一导出公共 API：
- `ReportExperimentResult`
- `ExperimentReporter`（重构为 Facade，委托给子模块）

#### 3g. 更新 `eval/experiment_reporter.py`

改为从 `eval.reporter` 导入并 re-export，保持向后兼容。或直接删除（如果无外部直接导入）。

#### 3h. 更新测试文件

- `tests/test_experiment_reporter.py`：更新 import 路径
- `tests/test_e2e_experiment.py`：更新 import 路径

### 验收标准

- 每个子模块行数 ≤ 500
- `eval/experiment_reporter.py` 缩减为 re-export 入口（≤ 30 行）或删除
- `pixi run pytest tests/test_experiment_reporter.py tests/test_e2e_experiment.py -x` 通过
- `pixi run lint` 通过

---

## 步骤 4：`meal/manager.py` 抽取模板方法（P1）

### 问题

`create_meal`、`merge_meals`、`extend_meal`、`repair_meal` 四个方法共享 7 个完全重复的步骤（哈希计算、配置提取、缓存目录创建、解析、分块、索引、manifest 保存），合计约 150-200 行重复代码。

### 修改方案

抽取 `_build_pipeline` 私有方法，封装共享的"解析→分块→索引→统计→artifact_manifest→等价组→MealConfig→目录创建→manifest保存"流程。

### 具体操作

#### 4a. 新增 `_build_pipeline` 方法

```python
def _build_pipeline(
    self,
    *,
    meal_files: list[MealFile],
    config_snapshot: dict,
    config_hashes: dict,
    data_id: str,
    index_key: str,
    collection_name: str,
    pdfs_to_parse: list[Path],
    parsed_dir: Path,
    chunks_dir: Path,
    reuse_parsed: bool = False,
    source_parsed_dir: Path | None = None,
    source_chunks_dir: Path | None = None,
    composition: dict | None = None,
    sampling_config: dict | None = None,
) -> MealConfig:
```

此方法封装以下共享步骤：
1. 提取 parser/chunker/embedding 配置
2. 缓存目录创建
3. 解析 PDF（支持复用已有解析结果）
4. 构建分块
5. 构建向量索引
6. 统计 chunks 数量
7. 构建 & 保存 artifact_manifest
8. 推断等价组
9. 构建 MealConfig 对象
10. 创建 meal 目录 + test_sets 子目录
11. 保存 manifest.json

#### 4b. 重构四个方法

- `create_meal`：保留采样逻辑（A1-A3），调用 `_build_pipeline`
- `merge_meals`：保留合并逻辑（B1-B4），调用 `_build_pipeline`
- `extend_meal`：保留扩展逻辑（C1-C5, C9），调用 `_build_pipeline`
- `repair_meal`：保留替换逻辑（D1-D4），调用 `_build_pipeline`

#### 4c. 修复 `import json` 问题

将 `manager.py:1380` 的方法内部 `import json` 移至文件顶部（注意：文件顶部 L4 已有 `import json`，L1380 的导入是冗余的，直接删除即可）。

### 验收标准

- `manager.py` 行数减少 150+ 行
- 四个方法中不再有重复的"解析→分块→索引→manifest"流程
- `pixi run pytest tests/test_meal.py -x` 通过
- `pixi run lint` 通过

---

## 步骤 5：`BuiltinEvaluator` LSP 修复（P1）

### 问题

`BuiltinEvaluator.evaluate_single` 在基类签名基础上额外增加了 8 个参数，违反里氏替换原则。`RagasEvaluator.evaluate_batch` 签名也缺少 `retrieval_metrics` 参数。

### 修改方案

引入 `EvaluationSample` dataclass 封装评测样本的所有字段，统一 `evaluate_single` 和 `evaluate_batch` 的签名。

### 具体操作

#### 5a. 在 `eval/evaluators/base.py` 中新增 `EvaluationSample`

```python
@dataclass
class EvaluationSample:
    question_id: str
    question: str
    answer: str
    contexts: list[str]
    expected_sources: list[str] | None = None
    expected_answer: str | None = None
    llm_config: dict[str, str] | None = None
    retrieval_metrics: list[str] | None = None
    generation_metrics: list[str] | None = None
    chunk_ids: list[str] | None = None
    expected_chunks: list[str] | None = None
    equivalence_groups: dict[str, list[str]] | None = None
    expect_retrieval: bool = True
    expect_no_answer: bool = False
    retrieved_sources: list[str] | None = None
    question_type: str | None = None
```

#### 5b. 修改基类签名

```python
@abstractmethod
def evaluate_single(self, sample: EvaluationSample) -> EvaluationResult:
    ...

def evaluate_batch(
    self,
    samples: list[EvaluationSample],
    llm_config: dict[str, str] | None = None,
    retrieval_metrics: list[str] | None = None,
    generation_metrics: list[str] | None = None,
) -> list[EvaluationResult]:
    ...
```

`evaluate_batch` 的默认实现从 `EvaluationSample` 中提取字段，调用 `evaluate_single`。

#### 5c. 修改 `BuiltinEvaluator.evaluate_single`

```python
def evaluate_single(self, sample: EvaluationSample) -> EvaluationResult:
    # 从 sample 中提取所有字段
    ...
```

#### 5d. 修改 `RagasEvaluator.evaluate_single` 和 `evaluate_batch`

同样改为接收 `EvaluationSample`。

#### 5e. 更新所有调用点

搜索所有调用 `evaluate_single` 和 `evaluate_batch` 的地方，改为构造 `EvaluationSample` 对象传入。

主要调用点：
- `eval/runner/evaluation.py` 中的 `_evaluate_with_builtin` 和 `_evaluate_with_ragas`
- `tests/test_evaluators.py`

### 验收标准

- `BuiltinEvaluator.evaluate_single` 签名与基类一致（只接收 `EvaluationSample`）
- `RagasEvaluator.evaluate_batch` 签名与基类一致
- `pixi run pytest tests/test_evaluators.py -x` 通过
- `pixi run lint` 通过

---

## 步骤 6：`test_generation/` 内部 DRY（P1）

### 问题

- 25 个薄包装方法（~250 行）
- `domain_keywords` 重复 3 处
- `proper_nouns` 正则重复 3 处
- 三个 `_parse_*_response` 方法重复
- 4 处验证代码块重复（~266 行）

### 修改方案

此步骤与步骤 2 合并执行。在步骤 2 的拆分过程中同步处理所有 DRY 问题。

### 具体操作

已在步骤 2 中详细描述：
- 2a：常量统一到 `models.py`
- 2d：提取 `parse_json_response` 通用方法
- 2e：删除薄包装方法
- 2f：提取 `_post_process_question` 方法

### 验收标准

- 无薄包装方法
- `domain_keywords` / `PROPER_NOUN_PATTERN` 只定义一次
- `parse_json_response` 替代三个重复的 parse 方法
- `_post_process_question` 替代 4 处验证代码块

---

## 步骤 7：`test_set_manager.py` 清洗策略独立（P2）

### 问题

`TestSetManager` 1277 行，其中 `_clean_immutable_policy`、`_clean_trim_policy`、`_clean_regenerate_policy` 合计约 400+ 行，逻辑复杂且彼此独立。

### 修改方案

抽取 `TestSetCleaner` 类，使用策略模式封装三种清洗策略。

### 具体操作

#### 7a. 新建 `src/test_set_cleaner.py`

```python
class TestSetCleaner:
    def clean_immutable(self, test_set, ...) -> cleaned_test_set: ...
    def clean_trim(self, test_set, ...) -> cleaned_test_set: ...
    def clean_regenerate(self, test_set, ...) -> cleaned_test_set: ...
```

将 `TestSetManager` 中的三个 `_clean_*_policy` 方法和相关的 `_should_warn_about_cleaning`、`_filter_rejected_questions` 方法移入此类。

#### 7b. 修改 `TestSetManager`

- 删除移出的方法
- 在 `validate_test_set` 中委托给 `TestSetCleaner`
- `resolve_test_set` 方法如果过长（176 行），也考虑拆分

### 验收标准

- `test_set_manager.py` 行数 ≤ 900
- `test_set_cleaner.py` 行数 ≤ 500
- `pixi run pytest tests/test_test_set_manager.py -x` 通过
- `pixi run lint` 通过

---

## 步骤 8：`DEFAULT_EVAL_CONFIG` 统一（P2）

### 问题

`eval/metrics/generation.py` 和 `eval/metrics/llm_retrieval.py` 各自定义了几乎相同的 `DEFAULT_EVAL_CONFIG` 和 `_get_eval_config`。

### 修改方案

将公共部分提取到 `eval/metrics/utils.py`。

### 具体操作

#### 8a. 在 `eval/metrics/utils.py` 中新增

```python
DEFAULT_EVAL_BASE_CONFIG = {
    "model_name": "LongCat-Flash-Lite",
    "base_url": "https://api.longcat.chat/anthropic",
}

def get_eval_config(user_config: dict | None, default_config: dict) -> dict:
    if user_config is None:
        return default_config
    merged = {**default_config, **user_config}
    merged.setdefault("model_name", DEFAULT_EVAL_BASE_CONFIG["model_name"])
    merged.setdefault("base_url", DEFAULT_EVAL_BASE_CONFIG["base_url"])
    return merged
```

#### 8b. 修改 `generation.py` 和 `llm_retrieval.py`

- 删除各自的 `DEFAULT_EVAL_CONFIG` 和 `_get_eval_config`
- 从 `utils.py` 导入 `DEFAULT_EVAL_BASE_CONFIG` 和 `get_eval_config`
- 各自只保留差异部分的子配置（`extract_statements`、`verify_statements` 等）

### 验收标准

- `model_name` 和 `base_url` 只在 `utils.py` 中定义一次
- `generation.py` 和 `llm_retrieval.py` 不再有 `_get_eval_config` 函数
- `pixi run pytest tests/test_metrics.py tests/test_metric_resolver.py -x` 通过

---

## 步骤 9：`_` 前缀规范化（P3）

### 问题

`eval/runner/__init__.py` 导出了 11 个 `_` 前缀函数；`eval/metrics/__init__.py` 导入了 8 个 `_` 前缀函数。

### 修改方案

对被跨模块使用的 `_` 前缀函数，去掉下划线；对仅内部使用的，从 `__all__` 中移除。

### 具体操作

#### 9a. `eval/runner/` 中被跨模块使用的函数

以下函数被 `eval/runner/evaluation.py` 或 `core.py` 直接导入使用，应去掉 `_` 前缀：

| 原名 | 新名 |
|------|------|
| `_build_legacy_resolver` | `build_legacy_resolver` |
| `_merge_result` | `merge_result` |
| `_namespace_result` | `namespace_result` |
| `_collect_rag_samples` | `collect_rag_samples` |
| `_create_evaluators` | `create_evaluators` |
| `_evaluate_with_builtin` | `evaluate_with_builtin` |
| `_evaluate_with_ragas` | `evaluate_with_ragas` |
| `_build_comparison_data` | `build_comparison_data` |
| `_extract_category_metrics` | `extract_category_metrics` |
| `_generate_comparison_report` | `generate_comparison_report` |
| `_print_comparison_table` | `print_comparison_table` |
| `_prepare_legacy_test_set` | `prepare_legacy_test_set` |

需要同步修改：
- 函数定义处（各子模块文件）
- `__init__.py` 的导入和 `__all__`
- 所有调用点

#### 9b. `eval/metrics/` 中的 `_` 前缀函数

这些函数未列入 `__all__`，但被导入了。决定：
- 如果是测试中使用的公共 API，去掉 `_` 前缀并加入 `__all__`
- 如果是内部实现，从 `__init__.py` 的导入中移除

### 验收标准

- `__all__` 中无 `_` 前缀函数
- 被跨模块使用的函数无 `_` 前缀
- `pixi run pytest tests/ -x` 通过

---

## 步骤 10：`cache.py` 返回值修复（P3）

### 问题

`src/meal/cache.py` 的 `save_manifest` 方法 docstring 声明返回 `True/False`，但函数签名声明 `-> None`，实际代码 `return True` / `return False`。

### 修改方案

将返回类型注解改为 `-> bool`，与实际行为和 docstring 一致。

### 具体操作

修改 `cache.py` 中 `save_manifest` 方法的签名：`-> None` → `-> bool`。

### 验收标准

- 函数签名、docstring、实际行为三者一致
- `pixi run pytest tests/test_meal.py -x` 通过

---

## 步骤 11：`manager.py` 内部 `import json`（P3）

### 问题

`src/meal/manager.py:1380` 在方法内部 `import json`，但文件顶部 L4 已有 `import json`。

### 修改方案

删除 L1380 的冗余 `import json`。

### 具体操作

删除 `manager.py:1380` 的 `import json` 行。

### 验收标准

- `manager.py` 中无方法内部的 `import json`
- `pixi run pytest tests/test_meal.py -x` 通过

---

## 执行顺序与依赖关系

```
步骤 1 (ExperimentResult 重命名)
  ↓ 无依赖
步骤 10 (cache.py 返回值修复)
  ↓ 无依赖
步骤 11 (manager.py import json)
  ↓ 无依赖
步骤 8 (DEFAULT_EVAL_CONFIG 统一)
  ↓ 无依赖
步骤 4 (meal/manager.py 模板方法) ← 步骤 11 先完成
  ↓ 无依赖
步骤 5 (BuiltinEvaluator LSP 修复)
  ↓ 无依赖
步骤 2 (test_generation/generator.py 拆分 + DRY) ← 包含步骤 6
  ↓ 无依赖
步骤 3 (experiment_reporter.py 拆分) ← 步骤 1 先完成
  ↓ 无依赖
步骤 7 (test_set_manager.py 清洗策略)
  ↓ 无依赖
步骤 9 (_ 前缀规范化) ← 步骤 3, 5 先完成（避免改名冲突）
```

建议执行顺序：1 → 10 → 11 → 8 → 4 → 5 → 2 → 3 → 7 → 9

每个步骤完成后立即运行对应的测试和 lint，确保不引入回归。

---

## 风险与缓解

| 风险 | 缓解措施 |
|------|---------|
| 步骤 2 拆分范围大，可能引入 bug | 每个子步骤完成后立即运行 `tests/test_test_generator.py` |
| 步骤 3 拆分后 `ExperimentReporter` 的 Facade 接口变化 | 保持公共方法签名不变，只改内部实现 |
| 步骤 5 `EvaluationSample` 引入影响所有调用点 | 先改基类和子类，再逐一修改调用点 |
| 步骤 9 大规模重命名可能遗漏 | 使用 `grep` 全局搜索确认所有引用 |
| 拆分过程中 `__init__.py` 导出遗漏 | 每步完成后运行 `pixi run pytest tests/ -x` 全量测试 |

---

## 预期成果

| 指标 | 修复前 | 修复后（预期） |
|------|--------|---------------|
| 最大单文件行数 | 3,617 (generator.py) | ≤ 1,500 |
| God File 数量 | 2 (generator.py, experiment_reporter.py) | 0 |
| 薄包装方法数 | 25 | 0 |
| 常量重复次数 | 6 (domain_keywords×3 + proper_nouns×3) | 0 |
| 验证代码块重复 | 4 处 ~266 行 | 0（提取为 1 个方法） |
| LSP 违反 | 1 (BuiltinEvaluator) | 0 |
| 同名类冲突 | 1 (ExperimentResult) | 0 |
| 综合屎山指数 | 2/10 | **1/10** |
