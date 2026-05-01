# 测试集兼容性契约

> 本文档定义测试集数据结构的**不可变更约定**。所有对测试集元数据或问题结构的修改，必须遵守此契约，确保评估管线不断裂。

## 一、顶层结构

测试集 JSON 文件顶层必须支持两种格式（通过 `_migrate_test_set` 自动转换）：

```python
# 新格式
{
    "metadata": {...},       # 见 §二
    "quality_metrics": {...},
    "questions": [...]       # 见 §三
}

# 旧格式（加载时自动迁移）
{
    "name": "...",
    "meal_data_id": "...",
    "meal_name": "...",
    "strategy": "...",
    "created_at": "...",
    "generation_config": {...},
    "quality_metrics": {...},
    "questions": [...]
}
```

## 二、Metadata 级字段契约

| 字段名 | 类型 | 消费者 | 可变更 | 备注 |
|--------|------|--------|--------|------|
| `name` | `str` | core.py:679, evaluation.py:158 | **不可删除/重命名** | 新旧格式均以此为测试集标识 |
| `meal_id` | `str` | core.py:685, cleaner.py(多处) | **不可删除/重命名** | cleaner 用它判断是否需要清洗 |
| `created_at` | `str` | core.py:682 | **不可删除/重命名** | 快照保存 |
| `updated_at` | `str` | cleaner.py(多处) | **不可删除/重命名** | cleaner 更新此字段 |
| `generation` | `dict\|None` | core.py:676, cleaner.py:197, experiment_reuse.py:270-280 | **不可删除/重命名** | cleaner 的 regenerate 策略依赖此字段存在性 |
| `generation.strategy` | `str` | core.py:680, experiment_reuse.py:273 | **不可删除/重命名** | 快照 + 实验指纹 |
| `generation.num_questions` | `int` | experiment_reuse.py:277 | **不可删除/重命名** | 实验指纹 |
| `user_defined` | `bool` | cleaner.py(间接) | **可新增替代字段，但必须保留读取兼容** | 被 `quality_status` 替代 |
| `invalid_policy` | `str\|None` | cleaner.py:279 | **不可删除/重命名** | 决定清洗策略 (immutable/trim/regenerate) |
| `audit_log` | `list[dict]` | cleaner.py(多处) | **不可删除/重命名** | 记录变更历史 |
| `suppress_warnings` | `bool` | cleaner.py:414 | **不可删除/重命名** | 抑制审计警告 |
| `composition` | `dict` | merge 逻辑 | 可扩展 | 组合溯源 |

### 新增字段约束

以下字段为 Phase 1 新增，**消费者不应假定它们存在**，所有读取必须带默认值：

| 字段名 | 默认值 | 备注 |
|--------|--------|------|
| `quality_status` | `"draft"` | 质量管线状态机 |
| `review_progress` | `{}` | 审核进度统计 |
| `portable` | `False` | 可移植性标记 |
| `data_coverage` | `"partial"` | 数据覆盖范围 |

## 三、Question 级字段契约

每个 question dict 的**不可变更字段**（评估管线直接读取）：

| 字段名 | 类型 | 读取位置 | 不可变更 |
|--------|------|----------|----------|
| `id` | `str` | evaluation.py:272 | 不可删除/重命名 |
| `question` | `str` | evaluation.py:273 | 不可删除/重命名 |
| `answer` | `str` | evaluation.py:298,326 | 不可删除/重命名 |
| `source_files` | `list[str]` | evaluation.py:297,325 | 不可删除/重命名 |
| `ground_truth_excerpt` | `str` | evaluation.py:299,327 | 不可删除/重命名 |
| `source_chunks` | `list[str]` | evaluation.py:302,330 | 不可删除/重命名 |
| `question_type` | `str` | evaluation.py:304,332 | 不可删除/重命名 |
| `category` | `str` | evaluation.py:307,337 | 不可删除/重命名 |
| `difficulty` | `str` | evaluation.py:308 | 不可删除/重命名 |
| `expect_retrieval` | `bool` | evaluation.py:310,333 | 不可删除/重命名 |
| `expect_no_answer` | `bool` | evaluation.py:311,334 | 不可删除/重命名 |
| `metadata.review_status` | `str` | evaluation.py:163, cleaner.py:50 | 不可删除/重命名 |

**规则**：以上 12 个顶级字段 + 1 个嵌套字段 (`metadata.review_status`) 是评估管线的硬依赖，**名称和语义均不可变更**。可以新增字段，但不能删除或重命名现有字段。

## 四、resolve_test_set 契约

`TestSetManager.resolve_test_set()` 返回值必须满足：

1. 顶层包含 `"metadata"` 和 `"questions"` 两个 key
2. `"metadata"` 是 dict，包含 `"name"`, `"meal_id"`, `"generation"`, `"created_at"`, `"user_defined"`, `"invalid_policy"` 等字段
3. `"questions"` 是 `list[dict]`，每个元素包含 §三 的所有字段

## 五、旧格式兼容

`_migrate_test_set()` 负责将旧格式（无 `"metadata"` 包装）转换为新格式。转换规则：

```python
# 旧格式字段 → 新格式 metadata 字段
"name" → metadata["name"]
"meal_data_id" → metadata["meal_id"]
"created_at" → metadata["created_at"]
"generation_config" → metadata["generation"]
```

旧格式的 `user_defined` 默认为 `False`，`invalid_policy` 默认为 `None`。

## 六、冒烟测试维护

`tests/test_eval_pipeline_compat.py` 验证 resolve_test_set → collect_rag_samples 全链路。任何对上述契约字段的修改，必须保证此测试通过。
