# 测试套件重构：对分析文档的回复

> Date: 2026-04-17
> 回复对象：`test-suite-analysis.md`

---

## 概述

本文档是对 `test-suite-analysis.md` 所提问题的逐项回复。重构工作严格遵循分析文档的诊断和优先级建议，按 Phase 1 → Phase 2 → Phase 3 的顺序执行，并额外引入了黄金测试集（Golden Test Suite）作为回归测试基础设施。

**核心成果：**
- 测试总数：356 passed, 2 skipped
- 源模块测试覆盖率：从 8/14 (57%) 提升至 14/14 (100%)
- 核心 RAG 模块测试覆盖率：从 2/6 (33%) 提升至 6/6 (100%)
- 全局 `sys.modules` mock 已移除
- 重复 mock 设置代码从 ~150 行降至 ~30 行
- 私有方法测试从 ~20 个降至 ~5 个
- argparse 标准库测试已全部移除

---

## 一、关键缺失模块（Section 2）的解决策略

### 1.1 `eval/metrics.py` — CRITICAL ✅ 已解决

**分析文档诊断：** Hit Rate / MRR / NDCG 计算函数零测试覆盖，实验结果可信度无法保障。

**解决策略：** 创建 `tests/test_metrics.py`，采用纯函数测试模式（零 mock 依赖），覆盖所有边界条件和数学正确性。

| 测试类 | 测试方法 | 覆盖场景 |
|--------|---------|---------|
| `TestCalculateHitRate` | `test_full_hit` | 完全命中 → 返回 1.0 |
| | `test_partial_hit` | 部分命中 → 返回 2/3 |
| | `test_no_hit` | 无命中 → 返回 0.0 |
| | `test_empty_expected` | 空 expected → 返回 0.0 |
| | `test_empty_retrieved` | 空 retrieved → 返回 0.0 |
| | `test_duplicate_sources` | 重复 source 去重 → 返回 2/3 |
| `TestCalculateMRR` | `test_first_position_hit` | 第一位命中 → 返回 1.0 |
| | `test_last_position_hit` | 末位命中 → 返回 1/3 |
| | `test_no_hit` | 无命中 → 返回 0.0 |
| | `test_empty_expected` | 空 expected → 返回 0.0 |
| | `test_multiple_expected` | 多个 expected → 返回首位命中排名的倒数 |
| `TestCalculateNDCG` | `test_perfect_ranking` | 完美排序 → 返回 1.0 |
| | `test_reverse_ranking` | 逆序排序 → 返回 (0, 1) |
| | `test_partial_ranking` | 部分排序 → 手动计算 DCG/ideal_DCG 验证 |
| | `test_k_truncation` | k 参数截断 → k=2 时返回 0.0，k=5 时 > 0 |
| | `test_empty_expected` | 空 expected → 返回 0.0 |
| | `test_single_document_ideal` | 单文档 ideal DCG → 验证 DCG/ideal_DCG 比值 |

**关键设计决策：**

1. **手动计算验证**：`test_partial_ranking` 和 `test_single_document_ideal` 不依赖源码实现，而是独立计算 DCG 和 ideal DCG 的数学期望值，用 `pytest.approx` 比较。这确保了即使源码重构，只要数学正确，测试就不会误报。

2. **边界条件全覆盖**：三个函数的空列表输入行为（源码统一返回 0.0）均被显式测试，防止未来修改引入回归。

3. **重复 source 行为验证**：`test_duplicate_sources` 验证了 `calculate_hit_rate` 使用 `set()` 去重的行为，与源码实现一致。

### 1.2 `src/retriever.py` — HIGH ✅ 已解决

**分析文档诊断：** Retriever 无测试，输入校验、结果转换、Qdrant 不可用时的错误处理均未覆盖。

**解决策略：** 创建 `tests/test_retriever.py`，使用 conftest 共享 fixture（`mock_embedder`、`mock_qdrant_client`），覆盖完整检索流程和异常路径。

| 测试方法 | 覆盖场景 |
|---------|---------|
| `test_retrieve_success` | 成功检索 → 验证返回结构（chunk_id, text, metadata, score） |
| `test_retrieve_empty_query` | 空字符串 → 抛出 `ValueError` |
| `test_retrieve_non_string_query` | 非字符串输入 → 抛出 `ValueError` |
| `test_retrieve_qdrant_error` | Qdrant 异常 → 捕获并重抛 `Exception("Failed to retrieve results")` |
| `test_retrieve_result_payload_extraction` | 多结果 payload 提取 → 验证转换逻辑 |

**Mock 策略：**
- `mock_embedder`：来自 conftest，预配置 `embedding_dim=1024`，`embed_query` 返回随机 1024 维向量
- `mock_qdrant_client`：来自 conftest，预配置 `query_points` 返回值
- `_make_mock_indexer`：本地辅助方法，将 mock_qdrant_client 包装为 indexer 对象

### 1.3 `src/generator.py` — HIGH ✅ 已解决

**分析文档诊断：** Generator 无测试，输入校验、Prompt 构建、API 错误处理、客户端初始化失败均未覆盖。

**解决策略：** 创建 `tests/test_generator.py`，使用 `@patch("src.generator.Anthropic")` mock 客户端初始化，覆盖生成流程、输入校验、错误处理和 token 追踪。

| 测试方法 | 覆盖场景 |
|---------|---------|
| `test_generate_success` | 成功生成 → 验证返回文本和 API 调用 |
| `test_generate_empty_query` | 空字符串 → 抛出 `ValueError` |
| `test_generate_non_string_query` | 非字符串 → 抛出 `ValueError` |
| `test_generate_empty_contexts_warning` | 空 contexts → 不抛异常，记录 warning |
| `test_generate_api_error` | API 异常 → 重抛 `Exception("Failed to generate answer")` |
| `test_generate_custom_system_prompt` | 自定义 prompt → 传递到 API 调用 |
| `test_generate_token_tracker_records` | TokenTracker 集成 → 验证记录的 category、model_name、token 用量 |

**超出规格的覆盖：** `test_generate_token_tracker_records` 验证了 Generator 与 TokenTracker 的集成行为，这是分析文档未提及但实际价值很高的测试。

### 1.4 `src/indexer.py` — HIGH ✅ 已解决

**分析文档诊断：** VectorIndexer 无测试，集合创建、chunk 索引、source_filter、辅助方法均未覆盖。

**解决策略：** 创建 `tests/test_indexer.py`，使用 `@patch("src.indexer.QdrantClient")` mock 客户端，覆盖集合管理全生命周期和索引流程。

| 测试方法 | 覆盖场景 |
|---------|---------|
| `test_create_collection_new` | 新建集合 → 验证 VectorParams 配置 |
| `test_create_collection_exists_no_recreate` | 集合已存在 + recreate=False → 不删除不创建 |
| `test_create_collection_exists_recreate` | 集合已存在 + recreate=True → 先删后建 |
| `test_index_chunks_success` | 成功索引 → 验证 upsert 调用 |
| `test_index_chunks_empty` | 空 chunks → 不调用 upsert |
| `test_index_chunks_length_mismatch` | 长度不匹配 → 抛出 `ValueError` |
| `test_build_index_dir_not_exists` | 目录不存在 → 抛出 `FileNotFoundError` |
| `test_build_index_source_filter` | source_filter → 只加载匹配的 JSONL 文件 |
| `test_get_collection_info` | 获取集合信息 → 返回 points_count 和 status |
| `test_delete_collection` | 删除集合 → 调用 delete_collection |
| `test_close` | 关闭客户端 → 调用 close |

**关键设计决策：** `test_build_index_source_filter` 使用 `temp_project_dir` fixture 创建真实的 JSONL 文件，验证了文件系统层面的过滤逻辑，而非仅 mock 文件读取。这比纯 mock 测试更可靠。

### 1.5 `src/pipeline.py` — MEDIUM ✅ 已解决

**分析文档诊断：** RAGPipeline 无测试，初始化、query 流程、use_meal 切换均未覆盖。

**解决策略：** 创建 `tests/test_pipeline.py`，使用 7 层 `@patch` 完整隔离所有依赖组件，验证编排逻辑。

| 测试方法 | 覆盖场景 |
|---------|---------|
| `test_init_without_meal` | 无 meal 初始化 → 验证各组件初始化参数 |
| `test_init_with_meal` | 有 meal 初始化 → 使用 meal 的 collection_name |
| `test_query_full_flow` | 完整 query 流程 → 验证 retriever→generator 调用链和返回结构 |
| `test_query_invalid_input` | 无效输入 → 抛出 `ValueError` |
| `test_use_meal_switch` | meal 切换 → indexer 和 retriever 使用新 collection |

**Mock 策略：** Pipeline 是编排层，其测试重点不是各组件的内部行为（已有独立测试覆盖），而是组件间的协作关系。因此采用全 mock 策略，只验证调用顺序和参数传递。

### 1.6 `src/utils.py` — MEDIUM ✅ 已解决

**分析文档诊断：** 工具函数无测试，配置加载、环境变量解析、目录创建均未覆盖。

**解决策略：** 创建 `tests/test_utils.py`，使用 `@patch("src.utils.os.getenv")` mock 环境变量，使用 `tmp_path` fixture 处理文件系统操作。

| 测试类 | 测试方法 | 覆盖场景 |
|--------|---------|---------|
| `TestLoadConfig` | `test_load_valid_config` | 有效 YAML → 返回解析后的字典 |
| | `test_load_config_file_not_found` | 文件不存在 → 抛出 `FileNotFoundError` |
| | `test_load_config_invalid_yaml` | 无效 YAML → 抛出 `yaml.YAMLError` |
| `TestGetLlmConfig` | `test_default_preset` | 默认 preset → 使用 LLM_MODEL_ID 等环境变量 |
| | `test_named_preset` | 命名 preset → 使用自定义环境变量 |
| | `test_preset_not_found_fallback` | preset 不存在 → 回退到 default |
| | `test_env_var_resolution` | 环境变量解析 → base_url 追加 "/anthropic" |
| `TestGetEnvVar` | `test_existing_var` | 变量存在 → 返回值 |
| | `test_missing_var_with_default` | 变量缺失 + 默认值 → 返回默认值 |
| | `test_required_var_missing` | 必需变量缺失 → 抛出 `ValueError` |
| `TestEnsureDir` | `test_create_new_dir` | 新建目录 → 创建成功 |
| | `test_existing_dir` | 已存在目录 → 不报错 |
| | `test_nested_dir` | 嵌套目录 → 递归创建 |

---

## 二、过度工程（Section 3）的解决策略

### 2.1 `test_embedder.py` Mock 去重 ✅ 已解决

**分析文档诊断：** 每个测试方法重复 10-15 行相同的 mock 设置代码，约 150 行纯重复。

**解决策略：** 提取本地 `embedder_setup` fixture，使用 `SimpleNamespace` 封装所有 mock 对象。

**重构前（每个测试重复）：**
```python
@patch("src.embedder.AutoTokenizer")
@patch("src.embedder.AutoModel")
@patch("src.embedder.torch.cuda.is_available")
def test_XXX(self, mock_cuda_available, mock_auto_model, mock_auto_tokenizer):
    mock_cuda_available.return_value = True
    mock_model = MagicMock()
    mock_model.config.hidden_size = 1024
    mock_model.to.return_value = mock_model
    mock_model.half.return_value = mock_model
    mock_auto_model.from_pretrained.return_value = mock_model
    mock_auto_tokenizer.from_pretrained.return_value = MagicMock()
    # ... actual test (2-3 lines)
```

**重构后（每个测试仅覆盖差异）：**
```python
@pytest.fixture
def embedder_setup():
    with patch("src.embedder.AutoTokenizer") as mock_auto_tokenizer, \
         patch("src.embedder.AutoModel") as mock_auto_model, \
         patch("src.embedder.torch.cuda.is_available") as mock_cuda_available:
        # ... 公共 mock 设置（15 行，只出现一次）
        yield SimpleNamespace(mock_model=mock_model, embedder=embedder, ...)

def test_embedder_init_success(self, embedder_setup):
    assert embedder_setup.embedder.model_name == "test-model"  # 1 行

def test_embedder_init_cuda_fallback_to_cpu(self, embedder_setup):
    embedder_setup.mock_cuda_available.return_value = False  # 仅覆盖差异
    embedder = Embedder(model_name="test-model", device="cuda")
    assert embedder.device == "cpu"
```

**设计决策：** 选择本地 fixture 而非 conftest 全局 fixture，原因是 Embedder 初始化需要 `@patch` 控制 `AutoModel`/`AutoTokenizer` 的导入行为，这种生命周期管理不适合放在 conftest 中。

### 2.2 `test_experiment_reporter.py` 私有方法测试替换 ✅ 已解决

**分析文档诊断：** 8 个私有 `_generate_*_section` 方法测试，测试实现细节而非行为。

**解决策略：** 替换为公共 API 测试，验证 `generate_markdown_report()` 和 `generate_variant_comparison_report()` 的输出内容。

| 原测试（私有方法） | 新测试（公共 API） |
|-------------------|-------------------|
| `test_generate_overview_section` | `test_generate_markdown_report_contains_all_sections` |
| `test_generate_data_section` | ↑ 合并 |
| `test_generate_config_section` | ↑ 合并 |
| `test_generate_test_set_section` | ↑ 合并 |
| `test_generate_results_section` | ↑ 合并 |
| `test_generate_comparison_table` | ↑ 合并 |
| `test_generate_conclusion_section` | ↑ 合并 |
| `test_generate_assets_section` | ↑ 合并 |
| — | `test_generate_markdown_report_reflects_data`（新增） |
| — | `test_generate_markdown_report_saves_file`（新增） |
| — | `test_generate_variant_comparison_report_contains_all_sections` |
| — | `test_generate_variant_comparison_report`（完整输出验证） |

**核心改变：** 从"验证每个 section 方法返回了什么"变为"验证完整报告包含了什么"。如果报告格式变更（section 重命名、合并），只要输出内容正确，测试就不会失败。

### 2.3 `test_e2e_experiment.py` 去重 ✅ 已解决

**分析文档诊断：** 1,402 行文件标记为 E2E 但全部使用 mock，与 `test_experiment.py` 和 `test_experiment_reporter.py` 大量重复。

**解决策略：**
1. 移除与 `test_experiment.py` 重复的 ExperimentManager CRUD 测试
2. 移除与 `test_experiment_reporter.py` 重复的报告生成测试
3. 仅保留真正独特的场景：资产验证（含 PDF hash 校验）、实验对比、复现验证
4. 移除所有 `@pytest.mark.integration` 标记（因为全部是 mock 测试）

**精简效果：**
- 行数：1,402 → ~549（减少 61%）
- 测试数：15 → 7
- Fixture：8 个精简为 5 个（移除了多数测试不需要的目录结构）

### 2.4 `test_run_eval.py` argparse 测试移除 ✅ 已解决

**分析文档诊断：** 3 个测试仅验证 `argparse.ArgumentParser` 的参数解析行为，测试的是 Python 标准库。

**解决策略：** 直接删除这 3 个测试。保留有项目逻辑价值的测试（实验配置加载、variant 合并、向后兼容）。

### 2.5 `test_experiment.py` 验证测试合并 ✅ 已解决

**分析文档诊断：** `TestExperimentConfig` 有 12 个分散的验证测试，测试数据类样板代码。

**解决策略：** 合并为 2 个综合测试。

| 原测试（12 个） | 新测试（2 个） |
|----------------|---------------|
| `test_empty_name` | `test_invalid_config_catches_all_errors`（一次断言 6 个错误） |
| `test_empty_description` | ↑ 合并 |
| `test_missing_meal` | ↑ 合并 |
| `test_empty_test_sets` | ↑ 合并 |
| `test_missing_strategy` | `test_invalid_config_partial_errors`（细粒度验证） |
| `test_missing_num_questions` | ↑ 合并 |
| `test_empty_variants` | ↑ 合并 |
| `test_missing_variant_name` | ↑ 合并 |
| `test_missing_metrics` | ↑ 合并 |
| ... | |

**设计决策：** 保留 `test_invalid_config_partial_errors` 作为细粒度验证，确保部分错误不会导致其他错误被遗漏。这比单纯合并为 1 个测试更安全。

---

## 三、基础设施问题（Section 4）的解决策略

### 3.1 `conftest.py` 全局 Mock 清理 ✅ 已解决

**分析文档诊断：** `sys.modules["transformers"] = MagicMock()` 在模块级别全局 mock transformers，影响所有测试。

**解决策略：**
1. 完全删除 `sys.modules["transformers"]` 全局 mock
2. 在 `test_embedder.py` 中使用本地 `@patch` 装饰器进行局部 mock
3. 在 conftest.py 中新增 4 个共享 fixture，供多个测试文件复用

| Fixture | 用途 | 使用者 |
|---------|------|--------|
| `mock_embedder` | 预配置的 Embedder mock（dim=1024） | test_retriever.py, test_pipeline.py |
| `mock_qdrant_client` | 预配置的 QdrantClient mock | test_retriever.py, test_indexer.py |
| `mock_anthropic_client` | 预配置的 Anthropic client mock | test_generator.py |
| `temp_project_dir` | 临时项目目录（自动清理） | test_indexer.py, test_e2e_experiment.py |

### 3.2 Marker 使用规范 ✅ 已解决

**分析文档诊断：** `integration` marker 被滥用在 mock 测试上，`slow` marker 未使用，无 `unit` marker。

**解决策略：**
1. `pytest.ini` 新增 `unit` marker 定义
2. 所有新增测试文件标记 `@pytest.mark.unit`
3. `integration` marker 仅用于触及外部系统的测试（目前仅 `test_regression.py::test_golden_qa_full_pipeline`）
4. 从 `test_e2e_experiment.py` 移除所有 `@pytest.mark.integration` 标记

**Marker 语义定义：**

| Marker | 语义 | 使用条件 |
|--------|------|---------|
| `unit` | 纯单元测试 | 无外部依赖（Qdrant、LLM API、真实 PDF） |
| `integration` | 集成测试 | 触及外部系统 |
| `slow` | 慢速测试 | 执行时间 >5s（目前无测试使用） |

### 3.3 测试隔离 ✅ 已解决

**分析文档诊断：** 测试通过全局 `sys.modules` 操纵共享状态，无隔离策略。

**解决策略：**
1. 移除全局 `sys.modules` mock，消除隐式共享状态
2. 所有 mock 通过 `@patch` 装饰器或 fixture 限定作用域
3. `temp_project_dir` fixture 使用 `tempfile.TemporaryDirectory` + `yield`，测试结束后自动清理
4. 每个测试可独立运行，无执行顺序依赖

---

## 四、缺失测试模式（Section 5）的解决策略

### 4.1 核心模块错误路径测试 ✅ 已解决

| 模块 | 错误路径 | 测试覆盖 |
|------|---------|---------|
| retriever | Qdrant 不可用 | `test_retrieve_qdrant_error` |
| generator | API 调用失败 | `test_generate_api_error` |
| generator | 空 contexts | `test_generate_empty_contexts_warning` |
| indexer | chunks/embeddings 长度不匹配 | `test_index_chunks_length_mismatch` |
| indexer | 目录不存在 | `test_build_index_dir_not_exists` |
| pipeline | 无效 query | `test_query_invalid_input` |
| utils | 配置文件不存在 | `test_load_config_file_not_found` |
| utils | 无效 YAML | `test_load_config_invalid_yaml` |
| utils | 必需环境变量缺失 | `test_required_var_missing` |

### 4.2 黄金测试集（新增）✅ 框架已建立

分析文档 Section 5.4 提到缺乏回归测试。我们引入了黄金测试集（Golden Test Suite）作为解决方案：

- **`exp_configs/golden_test.yaml`**：专用实验配置，3 个 test_sets（factual:5 + boundary:3 + multi_hop:2）
- **`tests/fixtures/golden_qa.json`**：固化的问题集，每条包含 id/category/question/expected_sources/expected_keywords/description
- **`tests/test_regression.py`**：参数化回归测试驱动器
  - Mock LLM 模式：验证 expected_sources 命中率
  - Integration 模式：验证 expected_keywords 覆盖率（需运行环境）

**设计理念：** 新功能上线时，只需向 `golden_qa.json` 添加新条目，无需编写新的测试函数。

### 4.3 Property-Based Testing ⚠️ 未实现

分析文档 Section 5.2 建议为纯函数添加 property-based testing（如 hypothesis）。这是一个合理的建议，但考虑到当前测试已覆盖所有边界条件，优先级较低，留待后续优化。

---

## 五、改进计划（Section 6）的执行状态

| Phase | # | 行动 | 状态 |
|-------|---|------|------|
| Phase 1 | 1 | 添加 `eval/metrics.py` 测试 | ✅ 完成 |
| Phase 1 | 2 | 添加 `src/retriever.py` 测试 | ✅ 完成 |
| Phase 1 | 3 | 添加 `src/generator.py` 测试 | ✅ 完成 |
| Phase 1 | 4 | 添加 `src/indexer.py` 测试 | ✅ 完成 |
| Phase 1 | 5 | 移除全局 `sys.modules` mock | ✅ 完成 |
| Phase 2 | 6 | 提取 Embedder mock fixture | ✅ 完成 |
| Phase 2 | 7 | 合并 reporter 私有方法测试 | ✅ 完成 |
| Phase 2 | 8 | 移除 argparse 测试 | ✅ 完成 |
| Phase 2 | 9 | 精简 e2e_experiment 测试 | ✅ 完成 |
| Phase 2 | 10 | 合并 experiment 验证测试 | ✅ 完成 |
| Phase 3 | 11 | 添加 `src/pipeline.py` 测试 | ✅ 完成 |
| Phase 3 | 12 | 添加 `src/utils.py` 测试 | ✅ 完成 |
| Phase 3 | 13 | 添加错误路径测试 | ✅ 完成（核心模块） |
| Phase 3 | 14 | 修正 marker 使用 | ✅ 完成 |
| Phase 3 | 15 | 添加 property-based 测试 | ⚠️ 未实现（低优先级） |

---

## 六、与预期效果的对照

| 指标 | 分析文档预期 | 实际结果 |
|------|------------|---------|
| 源模块测试覆盖率 | 14/14 (100%) | ✅ 14/14 (100%) |
| 核心 RAG 模块覆盖率 | 6/6 (100%) | ✅ 6/6 (100%) |
| 重复 mock 设置行数 | ~30 | ✅ ~30 |
| 私有方法测试数 | ~5 | ✅ ~5 |
| 标准库测试数 | 0 | ✅ 0 |
| 纯函数模块零测试 | 0 | ✅ 0 |
| 总测试行数 | ~4,500 | ✅ 约 4,500-5,000（含黄金测试集框架） |

实际结果与分析文档的预期高度一致，验证了分析诊断的准确性和重构策略的有效性。
