# Meal 扩充与测试集组合功能 Spec

## Why

当前 Meal 系统只支持创建全新的 meal，用户无法在已有 meal 基础上扩充数据集。当用户需要增加 PDF 文件时，必须重新创建整个 meal，导致：

1. 已有的测试集无法复用，需要重新生成问题
2. 解析/分块缓存虽然可以命中，但缺少明确的组合追踪
3. 实验对比时难以追溯数据来源

## What Changes

* 新增 `MealManager.merge_meals()` 方法：支持多个 meal 合并创建新 meal

* 新增 `MealManager.extend_meal()` 方法：支持在已有 meal 基础上添加新 PDF

* 新增 `TestSetManager.merge_test_sets()` 方法：支持合并多个 meal 的测试集

* MealConfig 新增 `composition` 字段：记录 meal 的组合来源和历史

* TestSetMetadata 新增 `composition` 字段：记录测试集的组合来源

## Impact

* Affected specs: Meal 系统、TestSetManager 系统

* Affected code:

  * `src/meal.py` - 新增 merge\_meals/extend\_meal 方法

  * `src/test_set_manager.py` - 新增 merge\_test\_sets 方法

  * `main.py` - 新增 CLI 命令支持

  * `tests/test_meal.py` - 新增测试

  * `tests/test_test_set_manager.py` - 新增测试

## ADDED Requirements

### Requirement: Meal 组合功能

系统 SHALL 支持将多个已有 meal 合并为新的 meal，并追踪组合来源。

#### Scenario: 合并两个 meal 创建新 meal

* **GIVEN** 存在 meal A（包含 PDF 文件列表 PA）和 meal B（包含 PDF 文件列表 PB）

* **WHEN** 用户执行 `merge_meals([A, B], name="C")`

* **THEN** 系统 SHALL 创建新 meal C，其 PDF 文件列表为 PA ∪ PB（去重）

* **AND** meal C 的 `composition` 字段记录来源为 `[{"meal": "A", "pdf_count": N}, {"meal": "B", "pdf_count": M}]`

* **AND** 系统 SHALL 复用已有的解析/分块缓存，仅处理新增的 PDF

#### Scenario: 合并时处理重复 PDF

* **GIVEN** meal A 和 meal B 包含部分相同的 PDF 文件

* **WHEN** 用户合并 A 和 B

* **THEN** 系统 SHALL 自动去重，确保每个 PDF 只出现一次

* **AND** 系统 SHALL 在 composition 中记录去重信息

### Requirement: Meal 扩充功能

系统 SHALL 支持在已有 meal 基础上添加新的 PDF 文件，创建新的 meal。

#### Scenario: 扩充 meal 添加新 PDF

* **GIVEN** 存在 meal A（包含 10 个 PDF）

* **WHEN** 用户执行 `extend_meal(A, new_pdfs=["new1.pdf", "new2.pdf"], name="B")`

* **THEN** 系统 SHALL 创建新 meal B，包含原有 10 个 PDF + 新增 2 个 PDF

* **AND** meal B 的 `composition` 字段记录 `{"base_meal": "A", "added_files": ["new1.pdf", "new2.pdf"]}`

* **AND** 系统 SHALL 复用 meal A 的解析/分块缓存，仅处理新增的 2 个 PDF

#### Scenario: 扩充时检测重复 PDF

* **GIVEN** 用户尝试添加已存在于 meal 中的 PDF

* **WHEN** 执行扩充操作

* **THEN** 系统 SHALL 发出警告，跳过重复文件

* **AND** 在 composition 中记录跳过的文件

### Requirement: 测试集组合功能

系统 SHALL 支持合并多个 meal 的测试集，减少重复生成问题的工作量。

#### Scenario: 合并测试集

* **GIVEN** meal A 有测试集 TA（10 个问题），meal B 有测试集 TB（10 个问题）

* **WHEN** 用户创建 meal C = A ∪ B，并请求组合测试集

* **THEN** 系统 SHALL 创建测试集 TC，包含 TA 和 TB 的所有问题

* **AND** TC 的 `composition` 字段记录来源为 `[{"meal": "A", "test_set": "TA"}, {"meal": "B", "test_set": "TB"}]`

* **AND** 系统 SHALL 重新分配问题 ID，确保唯一性

#### Scenario: 测试集问题去重

* **GIVEN** TA 和 TB 包含部分相同的问题（基于问题文本相似度）

* **WHEN** 合并测试集

* **THEN** 系统 SHALL 检测并标记重复问题

* **AND** 默认保留第一个出现的问题，跳过重复项

* **AND** 在 audit\_log 中记录去重信息

#### Scenario: 测试集有效性验证

* **GIVEN** 合并后的测试集 TC 关联到 meal C

* **WHEN** 验证 TC 的有效性

* **THEN** 系统 SHALL 检查每个问题的 source\_files 是否在 meal C 的 PDF 列表中

* **AND** 移除无效问题（source\_files 不在 meal C 中）

### Requirement: CLI 支持

系统 SHALL 提供 CLI 命令支持 meal 组合和扩充操作。

#### Scenario: CLI 合并 meal

* **WHEN** 用户执行 `pixi run python main.py --merge-meals A B --name C`

* **THEN** 系统 SHALL 创建 meal C 为 A 和 B 的合并

* **AND** 输出合并结果摘要

#### Scenario: CLI 扩充 meal

* **WHEN** 用户执行 `pixi run python main.py --extend-meal A --add-pdfs path/to/new.pdf --name B`

* **THEN** 系统 SHALL 创建 meal B 为 A 的扩充

* **AND** 输出扩充结果摘要

#### Scenario: CLI 合并测试集

* **WHEN** 用户执行 `pixi run python main.py --merge-test-sets A:TA B:TB --meal C --name TC`

* **THEN** 系统 SHALL 创建测试集 TC 为 TA 和 TB 的合并

* **AND** 输出合并结果摘要

### Requirement: 元数据追踪

系统 SHALL 在 meal 和测试集的元数据中完整记录组合历史。

#### Scenario: Meal composition 元数据

* **WHEN** 创建组合 meal

* **THEN** MealConfig.composition SHALL 包含：

  * `type`: "merged" | "extended" | "original"

  * `sources`: 来源 meal 列表（对于 merged 类型）

  * `base_meal`: 基础 meal 名称（对于 extended 类型）

  * `added_files`: 新增文件列表（对于 extended 类型）

  * `dedup_info`: 去重信息（如有）

  * `created_at`: 组合时间

#### Scenario: TestSet composition 元数据

* **WHEN** 创建组合测试集

* **THEN** TestSetMetadata.composition SHALL 包含：

  * `type`: "merged" | "generated" | "user\_defined"

  * `sources`: 来源测试集列表

  * `dedup_count`: 去重的问题数量

  * `original_count`: 原始问题总数

  * `final_count`: 最终问题数量

## MODIFIED Requirements

### Requirement: MealConfig 数据结构

MealConfig 数据结构 SHALL 新增 `composition` 字段以支持组合追踪。

原有字段保持不变，新增：

```python
@dataclass
class MealConfig:
    # ... 现有字段 ...
    composition: dict[str, Any] = field(default_factory=dict)
```

### Requirement: TestSetMetadata 数据结构

TestSetMetadata 数据结构 SHALL 新增 `composition` 字段以支持组合追踪。

原有字段保持不变，新增：

```python
@dataclass
class TestSetMetadata:
    # ... 现有字段 ...
    composition: dict[str, Any] = field(default_factory=dict)
```

