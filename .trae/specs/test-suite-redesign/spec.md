# Test Suite Redesign Spec

## Why

当前测试体系存在三类核心问题：(1) 关键模块（`eval/metrics.py`、`src/retriever.py`、`src/generator.py`、`src/indexer.py`）零测试覆盖，实验结果的可信度无法保障；(2) 已有测试存在大量过度工程（重复 mock 设置、测试私有方法、测试标准库行为），维护成本高而实际价值低；(3) 缺乏分层测试策略，所有测试都是同质的 mock 单元测试，无法区分快速反馈与真实验证。

## What Changes

### 新增测试文件

- **`tests/test_metrics.py`** — 为 `eval/metrics.py` 的三个纯函数（`calculate_hit_rate`、`calculate_mrr`、`calculate_ndcg`）添加完整测试，覆盖边界条件和数学正确性
- **`tests/test_retriever.py`** — 为 `src/retriever.py` 添加测试，Mock indexer + embedder，验证输入校验、结果转换、错误处理
- **`tests/test_generator.py`** — 为 `src/generator.py` 添加测试，Mock Anthropic client，验证输入校验、Prompt 构建、API 错误处理
- **`tests/test_indexer.py`** — 为 `src/indexer.py` 添加测试，Mock QdrantClient，验证集合创建、chunk 索引、source_filter、错误处理
- **`tests/test_pipeline.py`** — 为 `src/pipeline.py` 添加测试，Mock 全部依赖组件，验证初始化、query 流程、use_meal 切换
- **`tests/test_utils.py`** — 为 `src/utils.py` 添加测试，验证配置加载、环境变量解析、目录创建

### 重构已有测试

- **`tests/conftest.py`** — 移除全局 `sys.modules["transformers"]` mock，改为按需 fixture
- **`tests/test_embedder.py`** — 提取 Embedder mock fixture，消除 ~150 行重复 mock 设置
- **`tests/test_experiment_reporter.py`** — 将 8 个私有方法测试合并为 2-3 个公共 API 测试
- **`tests/test_run_eval.py`** — 移除 3 个 argparse 标准库测试
- **`tests/test_e2e_experiment.py`** — 移除与 `test_experiment.py` / `test_experiment_reporter.py` 重复的测试，精简 fixture
- **`tests/test_experiment.py`** — 合并 12 个分散的验证测试为 2-3 个综合测试

### 基础设施改进

- **`pytest.ini`** — 新增 `unit` marker，修正 `integration` marker 的语义定义
- **`tests/conftest.py`** — 新增共享 fixture（Embedder mock、QdrantClient mock、Anthropic client mock、临时项目目录）
- **Marker 规范** — `integration` 仅用于触及外部系统的测试，`slow` 仅用于 >5s 的测试，从 mock 测试中移除 `integration` marker

### 黄金测试集（Golden Test Suite）

黄金测试集是一个专用的 Meal + 实验配置组合，用于回归测试 RAG 系统的核心检索和生成能力。

#### Meal 规模设计

- **名称**: `golden_test`
- **采样策略**: `ratio: 0.03`（约 3% 的 PDF 文件，从 ~120 个 PDF 中采样约 3-4 个）
- **固定 seed**: `42`（确保可复现）
- **预期规模**: 约 3-4 个 PDF、150-250 页、300-500 个 chunks
- **设计理由**:
  - 预处理链路（PDF 解析 → 分块 → Embedding → Qdrant 索引）在首次运行后会被 Meal 的 artifact cache 缓存，后续测试无需重复
  - 3-4 个 PDF 足以覆盖年报和研报两种文档类型，确保检索测试有足够多样性
  - 300-500 chunks 的索引构建在 GPU 环境下约 30-60 秒，CPU 下约 2-3 分钟，可接受

#### 实验配置设计

- **配置文件**: `exp_configs/golden_test.yaml`
- **问题策略与数量**:
  - `factual`: 5 个问题（基础事实提取，验证单 chunk 检索能力）
  - `boundary`: 3 个问题（跨 chunk 边界，验证相邻 chunk 检索能力）
  - `multi_hop`: 2 个问题（多跳推理，验证跨 chunk 综合检索能力）
  - **总计 10 个问题**
- **设计理由**:
  - 问题生成需要 LLM API 调用，10 个问题约消耗 ~5K input + ~2K output tokens（使用 LongCat-Flash-Lite），成本 < $0.01
  - 10 个问题的评测运行（含检索 + 生成）约消耗 ~10K input + ~5K output tokens，成本 < $0.02
  - 总 API 开销极低，但足以区分 factual/boundary/multi_hop 三种检索难度
  - 问题数量不会导致测试运行时间过长（10 个问题约 1-2 分钟）

#### 黄金数据集生成与审核流程

1. **自动生成**: 使用 `TestSetGenerator` 基于 `golden_test` meal 自动生成初始问题集
2. **AI 评估**: 对生成的问题进行质量评估（问题是否明确、答案是否可从 chunk 直接得出、difficulty 标注是否合理），输出评估文档
3. **人工审核**: 评估文档供用户最终审核和手动调整
4. **固化**: 审核通过后的问题集作为 `tests/fixtures/golden_qa.json` 固化到仓库

#### 黄金数据集格式

```json
[
  {
    "id": "golden_001",
    "category": "factual",
    "question": "...",
    "expected_sources": ["source_file.md"],
    "expected_keywords": ["关键词1", "关键词2"],
    "description": "验证基础事实提取能力"
  }
]
```

#### 回归测试实现

- **`tests/test_regression.py`** — 参数化回归测试驱动器
  - Mock LLM 生成环节（只测检索链路），验证 expected_sources 命中率
  - 真实 LLM 调用时（integration 标记），验证 expected_keywords 覆盖率

## Impact

- Affected code: `tests/` 目录下全部 12 个文件 + `pytest.ini` + `conftest.py`
- 新增文件: 6 个测试文件 + 1 个 fixture 数据文件 + 1 个实验配置文件 + 1 个评估文档
- 新增 Meal: `golden_test`（3-4 个 PDF，约 150-250 页）
- 预计净效果: 测试行数从 ~5,878 降至 ~4,500（消除冗余后仍新增关键覆盖）
- 源模块测试覆盖率: 从 8/14 (57%) 提升至 14/14 (100%)
- 核心 RAG 模块测试覆盖率: 从 2/6 (33%) 提升至 6/6 (100%)

---

## ADDED Requirements

### Requirement: Metrics Module Test Coverage

系统 SHALL 为 `eval/metrics.py` 中的所有计算函数提供完整测试覆盖。

#### Scenario: Hit Rate 计算正确性
- **WHEN** 调用 `calculate_hit_rate` 传入完全匹配的 retrieved 和 expected 列表
- **THEN** 返回 1.0

#### Scenario: Hit Rate 空列表边界
- **WHEN** 调用 `calculate_hit_rate` 传入空 expected 列表
- **THEN** 返回 0.0

#### Scenario: MRR 第一位命中
- **WHEN** 调用 `calculate_mrr` 且 expected source 出现在 retrieved 列表第一位
- **THEN** 返回 1.0

#### Scenario: MRR 无命中
- **WHEN** 调用 `calculate_mrr` 且 expected source 不在 retrieved 列表中
- **THEN** 返回 0.0

#### Scenario: NDCG 完美排序
- **WHEN** 调用 `calculate_ndcg` 且 retrieved 列表完美排序
- **THEN** 返回 1.0

#### Scenario: NDCG k 参数截断
- **WHEN** 调用 `calculate_ndcg` 且 k 小于 retrieved 列表长度
- **THEN** 只考虑前 k 个结果计算

### Requirement: Retriever Module Test Coverage

系统 SHALL 为 `src/retriever.py` 的 `Retriever.retrieve()` 方法提供测试覆盖。

#### Scenario: 成功检索
- **WHEN** 调用 `retrieve` 传入有效 query 字符串
- **THEN** 返回包含 chunk_id、text、metadata、score 的字典列表

#### Scenario: 空 query 校验
- **WHEN** 调用 `retrieve` 传入空字符串或非字符串
- **THEN** 抛出 ValueError

#### Scenario: Qdrant 不可用
- **WHEN** indexer.client.query_points 抛出异常
- **THEN** 异常被捕获并重新抛出，包含有意义的错误信息

### Requirement: Generator Module Test Coverage

系统 SHALL 为 `src/generator.py` 的 `Generator` 类提供测试覆盖。

#### Scenario: 成功生成回答
- **WHEN** 调用 `generate` 传入有效 query 和 contexts
- **THEN** 返回 LLM 生成的文本

#### Scenario: 空 query 校验
- **WHEN** 调用 `generate` 传入空字符串或非字符串
- **THEN** 抛出 ValueError

#### Scenario: 空 contexts 警告
- **WHEN** 调用 `generate` 传入空 contexts 列表
- **THEN** 不抛出异常，但记录 warning 日志

#### Scenario: API 调用失败
- **WHEN** Anthropic client.messages.create 抛出异常
- **THEN** 异常被捕获并重新抛出

#### Scenario: 自定义 system prompt
- **WHEN** 调用 `generate` 时传入自定义 system_prompt
- **THEN** 该 prompt 被传递给 API 调用而非使用默认值

### Requirement: Indexer Module Test Coverage

系统 SHALL 为 `src/indexer.py` 的 `VectorIndexer` 类提供测试覆盖。

#### Scenario: 创建新集合
- **WHEN** 调用 `create_collection` 且集合不存在
- **THEN** 创建集合并使用正确的向量维度和距离度量

#### Scenario: 集合已存在且不重建
- **WHEN** 调用 `create_collection` 且集合已存在、recreate=False
- **THEN** 跳过创建，不删除已有集合

#### Scenario: 集合已存在且重建
- **WHEN** 调用 `create_collection` 且 recreate=True
- **THEN** 先删除旧集合再创建新集合

#### Scenario: chunks 和 embeddings 长度不匹配
- **WHEN** 调用 `index_chunks` 时 chunks 和 embeddings 长度不同
- **THEN** 抛出 ValueError

#### Scenario: 空 chunks
- **WHEN** 调用 `index_chunks` 时 chunks 为空
- **THEN** 不抛出异常，直接返回

#### Scenario: source_filter 过滤
- **WHEN** 调用 `build_index` 时传入 source_filter
- **THEN** 只加载匹配 filter 的 JSONL 文件

### Requirement: Pipeline Module Test Coverage

系统 SHALL 为 `src/pipeline.py` 的 `RAGPipeline` 类提供测试覆盖。

#### Scenario: 初始化
- **WHEN** 创建 RAGPipeline 实例
- **THEN** 正确初始化 embedder、indexer、retriever、generator

#### Scenario: 使用 meal 初始化
- **WHEN** 创建 RAGPipeline 时传入 meal_name
- **THEN** 使用 meal 对应的 collection_name

#### Scenario: query 完整流程
- **WHEN** 调用 `query` 传入有效问题
- **THEN** 依次调用 retriever.retrieve 和 generator.generate，返回包含 answer 和 contexts 的字典

#### Scenario: use_meal 切换
- **WHEN** 调用 `use_meal` 切换到新 meal
- **THEN** indexer 和 retriever 使用新 meal 的 collection

### Requirement: Utils Module Test Coverage

系统 SHALL 为 `src/utils.py` 的工具函数提供测试覆盖。

#### Scenario: 加载有效配置
- **WHEN** 调用 `load_config` 传入有效 YAML 文件路径
- **THEN** 返回解析后的字典

#### Scenario: 配置文件不存在
- **WHEN** 调用 `load_config` 传入不存在的文件路径
- **THEN** 抛出 FileNotFoundError

#### Scenario: LLM preset 回退
- **WHEN** 调用 `get_llm_config` 时指定的 preset 不存在
- **THEN** 回退到 default preset 并记录 warning

#### Scenario: 必需环境变量缺失
- **WHEN** 调用 `get_env_var` 时 required=True 且变量未设置
- **THEN** 抛出 ValueError

### Requirement: Shared Test Fixtures

系统 SHALL 在 `tests/conftest.py` 中提供可复用的共享 fixture。

#### Scenario: Embedder mock fixture
- **WHEN** 测试需要 Embedder 实例
- **THEN** 使用 `mock_embedder` fixture，返回预配置的 Embedder mock，embedding 维度为 1024

#### Scenario: QdrantClient mock fixture
- **WHEN** 测试需要 QdrantClient 实例
- **THEN** 使用 `mock_qdrant_client` fixture，返回预配置的 QdrantClient mock

#### Scenario: 临时项目目录 fixture
- **WHEN** 测试需要文件系统操作
- **THEN** 使用 `temp_project_dir` fixture，自动创建和清理临时目录结构

### Requirement: Golden Test Suite

系统 SHALL 提供基于专用 Meal 和实验配置的黄金测试集，用于 RAG 系统回归测试。

#### Scenario: 黄金 Meal 创建
- **WHEN** 运行 Meal 创建命令，使用 `ratio: 0.03`、`seed: 42` 采样
- **THEN** 生成名为 `golden_test` 的 Meal，包含 3-4 个 PDF、150-250 页、300-500 个 chunks

#### Scenario: 黄金实验配置
- **WHEN** 查看 `exp_configs/golden_test.yaml`
- **THEN** 包含 3 个 test_sets：factual(5)、boundary(3)、multi_hop(2)，总计 10 个问题

#### Scenario: 黄金数据集自动生成
- **WHEN** 运行实验配置生成问题集
- **THEN** 使用 `TestSetGenerator` 基于 `golden_test` meal 自动生成 10 个问题

#### Scenario: 问题质量评估
- **WHEN** 自动生成完成后
- **THEN** 输出评估文档至 `tests/fixtures/golden_qa_review.md`，包含每个问题的质量评价和优化建议

#### Scenario: 黄金数据集格式
- **WHEN** 查看 `tests/fixtures/golden_qa.json`
- **THEN** 每条记录包含 id、category、question、expected_sources、expected_keywords、description 字段

#### Scenario: 参数化回归测试（Mock LLM）
- **WHEN** 运行 `pytest tests/test_regression.py`
- **THEN** 对黄金数据集中的每条问题执行检索（Mock LLM 生成），验证 expected_sources 命中率

#### Scenario: 参数化回归测试（真实 LLM）
- **WHEN** 运行 `pytest tests/test_regression.py -m integration`
- **THEN** 对黄金数据集中的每条问题执行完整 RAG 链路，验证 expected_keywords 覆盖率

#### Scenario: 新增功能时扩展
- **WHEN** 新功能上线
- **THEN** 只需向 golden_qa.json 添加新条目，无需编写新的测试函数

### Requirement: Test Marker 规范

系统 SHALL 遵循明确的测试 marker 使用规范。

#### Scenario: integration marker 语义
- **WHEN** 测试触及外部系统（Qdrant、LLM API、真实 PDF 文件）
- **THEN** 标记为 `@pytest.mark.integration`

#### Scenario: slow marker 语义
- **WHEN** 测试执行时间 >5 秒
- **THEN** 标记为 `@pytest.mark.slow`

#### Scenario: unit marker
- **WHEN** 测试为纯单元测试（无外部依赖）
- **THEN** 标记为 `@pytest.mark.unit`

#### Scenario: mock 测试不标记 integration
- **WHEN** 测试使用 mock 替代外部依赖
- **THEN** 不标记 `@pytest.mark.integration`

---

## MODIFIED Requirements

### Requirement: conftest.py 全局 Mock 清理

原 `conftest.py` 在模块级别通过 `sys.modules["transformers"] = MagicMock()` 全局 mock transformers 库。此行为 SHALL 被移除，改为在 `test_embedder.py` 中使用 `@patch` 装饰器或 fixture 进行局部 mock。

**变更原因**: 全局 mock 影响所有测试、隐藏依赖关系、可能导致微妙问题。

### Requirement: test_embedder.py Mock 去重

原 `test_embedder.py` 中每个测试方法重复 10-15 行相同的 mock 设置代码。此重复 SHALL 被消除，改为使用 `conftest.py` 中的 `mock_embedder` fixture。

### Requirement: test_experiment_reporter.py 测试公共 API

原 `test_experiment_reporter.py` 测试 8 个私有 `_generate_*_section` 方法。此行为 SHALL 被替换为测试公共 API `generate_markdown_report()` 和 `generate_variant_comparison_report()` 的输出是否包含预期内容。

### Requirement: test_e2e_experiment.py 去重

原 `test_e2e_experiment.py` (1,400 行) 中大量测试与 `test_experiment.py` 和 `test_experiment_reporter.py` 重复。重复测试 SHALL 被移除，仅保留真正独特的集成场景。

### Requirement: test_run_eval.py 移除 argparse 测试

原 `test_run_eval.py` 中 3 个测试仅验证 `argparse.ArgumentParser` 的参数解析行为。这些测试 SHALL 被移除，因为它们测试的是 Python 标准库而非项目逻辑。

### Requirement: test_experiment.py 合并验证测试

原 `test_experiment.py` 中 `TestExperimentConfig` 有 12 个分散的验证测试。这些 SHALL 被合并为 2-3 个综合测试（有效配置、含多个错误的无效配置、序列化往返）。

---

## REMOVED Requirements

### Requirement: 全局 transformers mock

**Reason**: 隐式依赖、影响范围不可控、与测试隔离原则冲突
**Migration**: 在 `test_embedder.py` 中使用 `@patch` 或 fixture 局部 mock

### Requirement: argparse 标准库测试

**Reason**: 测试 Python 标准库行为，不验证项目逻辑，维护成本无收益
**Migration**: 直接删除，无需替代

### Requirement: 私有方法级别的 Reporter 测试

**Reason**: 测试实现细节而非行为，报告格式变更会导致大量测试失败
**Migration**: 改为测试公共 API 的输出内容
