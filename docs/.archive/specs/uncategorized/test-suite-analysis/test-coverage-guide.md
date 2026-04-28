# 项目测试体系指南

> Date: 2026-04-17
> 适用范围：ash-easy-rag 测试套件

---

## 一、测试覆盖状态总览

### 1.1 模块覆盖矩阵

| 源模块 | 测试文件 | 测试数 | 覆盖层级 | Marker |
|--------|---------|--------|---------|--------|
| `eval/metrics.py` | `test_metrics.py` | 17 | 单元测试 | `unit` |
| `src/retriever.py` | `test_retriever.py` | 5 | 单元测试 | `unit` |
| `src/generator.py` | `test_generator.py` | 7 | 单元测试 | `unit` |
| `src/indexer.py` | `test_indexer.py` | 10 | 单元测试 | `unit` |
| `src/pipeline.py` | `test_pipeline.py` | 5 | 单元测试 | `unit` |
| `src/utils.py` | `test_utils.py` | 10 | 单元测试 | `unit` |
| `src/embedder.py` | `test_embedder.py` | 12 | 单元测试 | `unit` |
| `src/parser.py` | `test_parser.py` | 12 | 单元测试 | — |
| `src/chunker.py` | `test_chunker.py` | 15 | 单元测试 | — |
| `src/meal.py` | `test_meal.py` | 28 | 单元测试 | — |
| `src/sampler.py` | `test_sampler.py` | 18 | 单元测试 | — |
| `src/test_generator.py` | `test_test_generator.py` | 13 | 单元测试 | — |
| `src/experiment.py` | `test_experiment.py` | 30+ | 单元测试 | `unit`（部分） |
| `eval/experiment_reporter.py` | `test_experiment_reporter.py` | 25+ | 单元测试 | `unit`（部分） |
| `eval/run_eval.py` | `test_run_eval.py` | 11 | 单元测试 | `unit` |
| `eval/run_experiment.py` | `test_run_experiment.py` | 15 | 单元测试 | — |
| 多模块集成 | `test_e2e_experiment.py` | 7 | 组件集成 | `unit` |
| 黄金数据集 | `test_regression.py` | 6 | 回归测试 | `unit` + `integration` |
| Token 追踪 | `test_token_tracker.py` | 24 | 单元测试 | — |

**总计：356 passed, 2 skipped**

### 1.2 核心 RAG 链路覆盖

```
PDF 解析 → 分块 → Embedding → 向量索引 → 检索 → LLM 生成
   │         │        │           │          │        │
 parser   chunker  embedder    indexer   retriever  generator
   ✅       ✅       ✅          ✅         ✅         ✅
```

所有 6 个核心 RAG 模块均有完整测试覆盖，包括正常路径和错误路径。

### 1.3 评测指标模块覆盖

```
Hit Rate ──── test_metrics.py::TestCalculateHitRate (6 tests)
MRR     ──── test_metrics.py::TestCalculateMRR (5 tests)
NDCG    ──── test_metrics.py::TestCalculateNDCG (6 tests)
```

评测指标是整个实验系统的信任基础，已实现零 mock 的纯函数测试。

---

## 二、测试分层体系

### 2.1 三层测试架构

```
┌─────────────────────────────────────────────────────┐
│  Layer 3: Integration Tests（集成测试）               │
│  触及外部系统：Qdrant、LLM API、真实 PDF              │
│  Marker: @pytest.mark.integration                   │
│  数量：2（当前为 skip 占位）                          │
│  运行：需运行环境 + API key                          │
├─────────────────────────────────────────────────────┤
│  Layer 2: Component Integration（组件集成测试）        │
│  多组件协作，mock 外部依赖                            │
│  代表：test_e2e_experiment.py, test_pipeline.py      │
│  Marker: @pytest.mark.unit                          │
│  数量：~12                                          │
├─────────────────────────────────────────────────────┤
│  Layer 1: Unit Tests（单元测试）                      │
│  单一模块，mock 所有依赖                             │
│  代表：test_metrics.py, test_retriever.py 等         │
│  Marker: @pytest.mark.unit                          │
│  数量：~340                                         │
└─────────────────────────────────────────────────────┘
```

### 2.2 各层适用性说明

| 层级 | 适用场景 | Mock 策略 | 运行速度 | 反馈价值 |
|------|---------|----------|---------|---------|
| **单元测试** | 验证单一函数/方法的行为 | Mock 所有外部依赖 | 极快（<1s/test） | 定位精确，失败时立即知道哪个函数出错 |
| **组件集成** | 验证多组件协作的正确性 | Mock 外部系统（Qdrant、LLM API），保留内部组件交互 | 快（<2s/test） | 验证组件间接口契约，发现集成问题 |
| **集成测试** | 验证真实环境下的端到端行为 | 不 mock，使用真实服务 | 慢（>10s/test） | 最高置信度，但维护成本高 |

### 2.3 测试选择策略

```
新功能开发 → 先写单元测试（Layer 1）
接口变更   → 补充组件集成测试（Layer 2）
版本发布   → 运行集成测试（Layer 3）
日常开发   → 运行单元测试 + 组件集成测试
```

---

## 三、如何运行测试

### 3.1 基础命令

```bash
# 运行全部测试
pixi run pytest tests/ -v

# 运行全部测试（简洁输出）
pixi run pytest tests/ -q

# 运行单个测试文件
pixi run pytest tests/test_metrics.py -v

# 运行单个测试类
pixi run pytest tests/test_metrics.py::TestCalculateHitRate -v

# 运行单个测试方法
pixi run pytest tests/test_metrics.py::TestCalculateHitRate::test_full_hit -v
```

### 3.2 按 Marker 过滤

```bash
# 仅运行单元测试（快速反馈，日常开发推荐）
pixi run pytest tests/ -m "unit" -v

# 排除集成测试（CI 环境推荐，无需 API key）
pixi run pytest tests/ -m "not integration" -v

# 仅运行集成测试（需运行环境 + API key）
pixi run pytest tests/ -m "integration" -v

# 运行慢速测试
pixi run pytest tests/ -m "slow" -v
```

### 3.3 按模块过滤

```bash
# 仅运行核心 RAG 模块测试
pixi run pytest tests/test_metrics.py tests/test_retriever.py tests/test_generator.py tests/test_indexer.py tests/test_pipeline.py tests/test_embedder.py -v

# 仅运行评测相关测试
pixi run pytest tests/test_metrics.py tests/test_experiment.py tests/test_experiment_reporter.py -v

# 仅运行回归测试
pixi run pytest tests/test_regression.py -v
```

### 3.4 调试与诊断

```bash
# 失败时显示完整 traceback
pixi run pytest tests/test_metrics.py -v --tb=long

# 失败时进入 pdb 调试器
pixi run pytest tests/test_metrics.py -v --pdb

# 显示测试中 print 输出
pixi run pytest tests/test_metrics.py -v -s

# 遇到第一个失败就停止
pixi run pytest tests/ -x -v

# 只运行上次失败的测试
pixi run pytest tests/ --lf -v
```

### 3.5 覆盖率报告

```bash
# 生成覆盖率报告（需安装 pytest-cov）
pixi run pytest tests/ --cov=src --cov=eval --cov-report=term-missing -v

# 生成 HTML 覆盖率报告
pixi run pytest tests/ --cov=src --cov=eval --cov-report=html -v
```

---

## 四、测试指标含义

### 4.1 测试运行指标

| 指标 | 含义 | 健康标准 |
|------|------|---------|
| **passed** | 测试通过数 | 应占总数 95%+ |
| **failed** | 测试失败数 | 应为 0 |
| **skipped** | 跳过数（`pytest.skip`） | 应仅限需运行环境的集成测试 |
| **deselected** | 因 marker 过滤未选中的测试 | 正常，取决于过滤条件 |
| **warnings** | pytest 警告 | 应为 0（当前有 1 个 CollectionWarning 待修复） |

### 4.2 RAG 评测指标（被测试验证的指标）

这些指标由 `eval/metrics.py` 计算，其正确性由 `test_metrics.py` 验证。

#### Hit Rate（命中率）

**含义：** 检索结果中包含正确文档的比例。

**计算方式：**
```
Hit Rate = |retrieved ∩ expected| / |expected|
```

**取值范围：** [0, 1]
- 1.0 = 所有期望文档都被检索到
- 0.0 = 没有任何期望文档被检索到

**适用场景：** 衡量检索系统的"召回能力"——能否找到相关文档。

#### MRR（Mean Reciprocal Rank，平均倒数排名）

**含义：** 第一个正确文档出现位置的倒数的平均值。

**计算方式：**
```
MRR = 1 / rank_of_first_relevant_doc
```

**取值范围：** [0, 1]
- 1.0 = 第一个检索结果就是正确文档
- 1/3 = 正确文档出现在第 3 位

**适用场景：** 衡量检索系统的"排序质量"——正确文档排得越靠前越好。

#### NDCG（Normalized Discounted Cumulative Gain，归一化折损累积增益）

**含义：** 考虑排序位置的信息检索质量指标，对排在前面的正确文档给予更高权重。

**计算方式：**
```
DCG = Σ (1 / log2(rank + 1))  for relevant docs in retrieved[:k]
IDCG = Σ (1 / log2(rank + 1))  for all relevant docs (ideal order)
NDCG = DCG / IDCG
```

**取值范围：** [0, 1]
- 1.0 = 完美排序
- 0.0 = 无相关文档或完全逆序

**参数 k：** 截断位置，只考虑前 k 个检索结果。默认 k=5。

**适用场景：** 综合衡量检索系统的排序质量，比 MRR 更全面（考虑多个相关文档的位置）。

### 4.3 测试质量指标

| 指标 | 当前值 | 目标 | 说明 |
|------|--------|------|------|
| 源模块覆盖率 | 14/14 (100%) | 100% | 所有 src/ 和 eval/ 模块均有对应测试 |
| 核心 RAG 覆盖率 | 6/6 (100%) | 100% | RAG 链路 6 个核心模块全覆盖 |
| 重复 mock 行数 | ~30 | <50 | mock 设置代码去重效果 |
| 私有方法测试数 | ~5 | <10 | 测试行为而非实现 |
| 标准库测试数 | 0 | 0 | 不测试 Python 自身功能 |
| 零测试纯函数模块 | 0 | 0 | 所有纯函数模块均有测试 |

---

## 五、共享 Fixture 速查

| Fixture | 位置 | 返回值 | 使用场景 |
|---------|------|--------|---------|
| `mock_embedder` | conftest.py | MagicMock，dim=1024 | 需要 Embedder 的测试 |
| `mock_qdrant_client` | conftest.py | MagicMock，预配置集合信息 | 需要 QdrantClient 的测试 |
| `mock_anthropic_client` | conftest.py | MagicMock，预配置消息和 token 用量 | 需要 Anthropic client 的测试 |
| `temp_project_dir` | conftest.py | Path，自动清理 | 需要文件系统操作的测试 |
| `embedder_setup` | test_embedder.py | SimpleNamespace（mock_model, embedder 等） | Embedder 内部行为测试 |
| `sample_result` | test_experiment_reporter.py | ExperimentResult | Reporter 输出测试 |
| `sample_variant_results` | test_experiment_reporter.py | List[dict] | 多 variant 对比测试 |

---

## 六、Marker 使用规范

### 6.1 何时使用哪个 Marker

| Marker | 使用条件 | 示例 |
|--------|---------|------|
| `@pytest.mark.unit` | 纯单元测试，无外部依赖 | `test_metrics.py` 的所有测试 |
| `@pytest.mark.integration` | 触及外部系统（Qdrant、LLM API、真实 PDF） | `test_regression.py::test_golden_qa_full_pipeline` |
| `@pytest.mark.slow` | 执行时间 >5s | 目前无测试使用 |

### 6.2 常见错误

| 错误 | 正确做法 |
|------|---------|
| Mock 测试标记 `integration` | Mock 测试标记 `unit` 或不标记 |
| 所有测试都不加 marker | 新增测试应标记 `unit` |
| `integration` 用于"看起来像集成的 mock 测试" | `integration` 仅用于真正触及外部系统的测试 |

### 6.3 当前 Marker 分布

```
unit:        168 tests (47%)
integration:   2 tests (1%, 均为 skip 占位)
无 marker:   186 tests (52%, 主要是重构前的旧测试)
```

> 注：重构前的旧测试未添加 `unit` marker，不影响功能，但建议逐步补齐。
