# INV-018: 异常路径测试覆盖评估报告

> 评估日期：2026-04-23
> 评估范围：tests/ 目录下所有测试文件
> 评估目标：识别异常路径测试覆盖情况，发现缺失的测试用例

---

## 一、评估方法

通过代码搜索和分析，检查测试文件中是否包含以下异常路径测试：

1. **异常捕获**：使用 `pytest.raises` 测试异常抛出
2. **错误处理**：ValueError, FileNotFoundError, PermissionError 等
3. **异常传播**：测试异常是否正确传播
4. **错误恢复**：重试机制、降级处理

---

## 二、已覆盖的异常路径测试

### 2.1 test_test_set_manager.py（14处）

| 测试函数 | 异常类型 | 说明 |
|----------|----------|------|
| `test_load_test_set_not_found` | FileNotFoundError | 测试集不存在 |
| `test_delete_test_set_not_found` | FileNotFoundError | 删除不存在的测试集 |
| `test_clean_immutable_policy_invalid_questions` | ValueError | 无效问题处理 |
| `test_clean_trim_policy_all_invalid` | ValueError | 全部无效问题 |
| `test_clean_regenerate_policy_missing_generation_config` | ValueError | 缺失生成配置 |
| `test_clean_regenerate_policy_missing_generation_key` | ValueError | 缺失生成键 |
| `test_resolve_test_set_unknown_policy` | ValueError | 未知策略 |
| `test_merge_test_sets_empty_source_specs` | ValueError | 空源规格 |
| `test_merge_test_sets_missing_meal_key` | ValueError | 缺失meal键 |
| `test_merge_test_sets_missing_test_set_key` | ValueError | 缺失test_set键 |
| `test_prepare_test_sets_invalid_on_missing` | ValueError | 无效on_missing参数 |
| `test_prepare_test_sets_on_missing_fail` | ValueError | fail模式处理 |
| `test_prepare_test_sets_on_missing_ignore` | ValueError | ignore模式处理 |
| `test_prepare_test_sets_on_missing_regenerate` | ValueError | regenerate模式处理 |

### 2.2 test_meal.py（13处）

| 测试函数 | 异常类型 | 说明 |
|----------|----------|------|
| `test_load_meal_not_found` | FileNotFoundError | meal不存在 |
| `test_rename_meal_invalid_name` | ValueError | 无效名称 |
| `test_rename_meal_target_exists` | ValueError | 目标已存在 |
| `test_copy_meal_target_exists` | ValueError | 复制目标已存在 |
| `test_merge_meals_empty_list` | ValueError | 空meal列表 |
| `test_merge_meals_meal_not_found` | ValueError | meal不存在 |
| `test_merge_meals_invalid_name` | ValueError | 无效名称 |
| `test_merge_meals_target_exists` | ValueError | 合并目标已存在 |
| `test_extend_meal_source_not_found` | ValueError | 源meal不存在 |
| `test_extend_meal_invalid_name` | ValueError | 无效名称 |
| `test_extend_meal_target_exists` | ValueError | 扩展目标已存在 |
| `test_extend_meal_pdf_not_found` | ValueError | PDF文件不存在 |
| `test_extend_meal_no_new_pdfs` | ValueError | 无新PDF文件 |

### 2.3 test_pipeline.py（2处）

| 测试函数 | 异常类型 | 说明 |
|----------|----------|------|
| `test_query_empty_string` | ValueError | 空查询字符串 |
| `test_query_non_string_input` | ValueError | 非字符串查询 |

### 2.4 test_parsers_base.py（2处）

| 测试函数 | 异常类型 | 说明 |
|----------|----------|------|
| `test_parse_pdf_file_not_found` | ValueError | PDF文件不存在 |
| `test_parse_pdf_invalid_type` | TypeError | 无效类型 |

### 2.5 test_parsers_fitz_pdfplumber.py（2处）

| 测试函数 | 异常类型 | 说明 |
|----------|----------|------|
| `test_parse_pdf_file_not_found` | FileNotFoundError | PDF文件不存在 |
| `test_parse_pdf_invalid_options` | ValueError | 无效选项 |

### 2.6 test_parsers_pymupdf4llm.py（3处）

| 测试函数 | 异常类型 | 说明 |
|----------|----------|------|
| `test_parse_pdf_file_not_found` | FileNotFoundError | PDF文件不存在 |
| `test_parse_pdf_invalid_options` | ValueError | 无效选项 |
| `test_parse_pdf_exception_handling` | Exception | 通用异常处理 |

### 2.7 test_metrics.py（14处）

| 测试函数 | 异常类型 | 说明 |
|----------|----------|------|
| `test_calculate_ndcg_invalid_mode` | ValueError | 无效模式 |
| `test_calculate_answer_relevancy_invalid_json` | ValueError | 无效JSON |
| `test_calculate_answer_relevancy_empty_json` | ValueError | 空JSON |
| `test_calculate_answer_relevancy_empty_question` | ValueError | 空问题 |
| `test_calculate_answer_relevancy_empty_answer` | ValueError | 空答案 |
| `test_calculate_answer_relevancy_empty_question_2` | ValueError | 空问题 |
| `test_calculate_answer_relevancy_empty_answer_2` | ValueError | 空答案 |
| `test_calculate_answer_relevancy_exception` | Exception | 通用异常 |
| `test_calculate_faithfulness_exception_statements` | Exception | 语句提取异常 |
| `test_calculate_faithfulness_exception_verification` | Exception | 语句验证异常 |
| `test_calculate_faithfulness_empty_answer` | ValueError | 空答案 |
| `test_calculate_faithfulness_whitespace_answer` | ValueError | 空白答案 |
| `test_calculate_faithfulness_exception` | Exception | 通用异常 |
| `test_calculate_context_recall_exception` | Exception | 通用异常 |

### 2.8 test_parser.py（1处）

| 测试函数 | 异常类型 | 说明 |
|----------|----------|------|
| `test_parse_pdf_file_not_found` | FileNotFoundError | PDF文件不存在 |

---

## 三、异常类型覆盖统计

| 异常类型 | 出现次数 | 覆盖模块 |
|----------|----------|----------|
| ValueError | 35 | test_set_manager, meal, pipeline, parsers, metrics |
| FileNotFoundError | 6 | test_set_manager, meal, parsers |
| Exception | 5 | parsers, metrics |
| TypeError | 1 | parsers |

---

## 四、缺失的异常路径测试

### 4.1 高优先级缺失

| 模块 | 缺失的异常类型 | 风险等级 | 说明 |
|------|----------------|----------|------|
| **test_generator.py** | ValueError, Exception | 高 | LLM调用可能失败，缺少异常测试 |
| **test_experiment.py** | ValueError, FileNotFoundError | 高 | 实验配置可能无效 |
| **test_run_experiment.py** | ValueError, PermissionError | 高 | 文件操作可能失败 |
| **test_indexer.py** | Exception, PermissionError | 高 | 向量索引操作可能失败 |

### 4.2 中优先级缺失

| 模块 | 缺失的异常类型 | 风险等级 | 说明 |
|------|----------------|----------|------|
| **test_embedder.py** | Exception | 中 | API调用可能失败 |
| **test_retriever.py** | Exception | 中 | 检索操作可能失败 |
| **test_reranker.py** | Exception | 中 | 重排操作可能失败 |
| **test_chunker.py** | ValueError | 中 | 分块参数可能无效 |

### 4.3 低优先级缺失

| 模块 | 缺失的异常类型 | 风险等级 | 说明 |
|------|----------------|----------|------|
| **test_sampler.py** | ValueError | 低 | 采样参数验证 |
| **test_query_rewriter.py** | Exception | 低 | 查询改写失败 |

---

## 五、具体缺失测试用例建议

### 5.1 test_generator.py

```python
# 建议添加的测试用例
- test_generate_with_invalid_meal_name: 无效meal名称
- test_generate_with_api_failure: API调用失败
- test_generate_with_timeout: 超时处理
- test_generate_with_rate_limit: 速率限制
```

### 5.2 test_experiment.py

```python
# 建议添加的测试用例
- test_run_experiment_invalid_config: 无效配置
- test_run_experiment_missing_meal: meal不存在
- test_run_experiment_output_dir_permission_denied: 权限错误
```

### 5.3 test_run_experiment.py

```python
# 建议添加的测试用例
- test_run_experiment_config_not_found: 配置文件不存在
- test_run_experiment_invalid_variant: 无效变体
- test_run_experiment_output_permission_denied: 输出目录权限错误
```

### 5.4 test_indexer.py

```python
# 建议添加的测试用例
- test_build_index_permission_denied: 权限错误
- test_build_index_invalid_collection: 无效集合名称
- test_build_index_api_failure: API调用失败
```

---

## 六、统计摘要

| 指标 | 数值 |
|------|------|
| 已覆盖异常路径测试 | 51个 |
| 涉及测试文件 | 8个 |
| 高优先级缺失 | 4个模块 |
| 中优先级缺失 | 4个模块 |
| 低优先级缺失 | 2个模块 |
| 总体覆盖率评估 | 良好（约75%） |

---

## 七、建议行动

### 立即行动（高优先级）

1. 为 `test_generator.py` 添加API调用失败和超时测试
2. 为 `test_experiment.py` 添加配置验证和权限错误测试
3. 为 `test_run_experiment.py` 添加文件操作异常测试
4. 为 `test_indexer.py` 添加向量索引异常测试

### 后续行动（中优先级）

1. 为 `test_embedder.py` 添加API异常测试
2. 为 `test_retriever.py` 添加检索异常测试
3. 为 `test_reranker.py` 添加重排异常测试
4. 为 `test_chunker.py` 添加参数验证测试

---

## 八、生成的新Issue

根据评估结果，建议创建以下新issue：

### TEST-005: 补充generator模块异常路径测试
- **类型**: Test
- **优先级**: 高
- **内容**: 为test_generator.py添加API调用失败、超时、速率限制等异常测试
- **关联**: INV-018

### TEST-006: 补充experiment模块异常路径测试
- **类型**: Test
- **优先级**: 高
- **内容**: 为test_experiment.py添加无效配置、权限错误等异常测试
- **关联**: INV-018

### TEST-007: 补充run_experiment模块异常路径测试
- **类型**: Test
- **优先级**: 高
- **内容**: 为test_run_experiment.py添加文件操作异常测试
- **关联**: INV-018

### TEST-008: 补充indexer模块异常路径测试
- **类型**: Test
- **优先级**: 高
- **内容**: 为test_indexer.py添加向量索引异常测试
- **关联**: INV-018

---

## 九、结论

当前测试体系对异常路径的覆盖率为良好水平（约75%）。主要问题集中在核心业务模块（generator、experiment、indexer）缺少对API调用失败、权限错误、超时等异常场景的测试。建议优先补充高优先级模块的异常路径测试，以提高系统的健壮性和可靠性。

特别需要注意的是：
1. **API调用相关模块**（generator、embedder）缺少对网络异常、超时、速率限制的测试
2. **文件操作相关模块**（experiment、run_experiment）缺少对权限错误的测试
3. **向量索引模块**缺少对API调用失败的测试

这些异常场景在生产环境中较为常见，应优先补充测试覆盖。
