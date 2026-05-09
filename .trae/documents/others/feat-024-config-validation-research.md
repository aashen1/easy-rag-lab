# FEAT-20260428-024 调研报告：配置验证系统

## Issue 概要

| 字段       | 内容                                                                                 |
| -------- | ---------------------------------------------------------------------------------- |
| **ID**   | FEAT-20260428-024-wt1                                                              |
| **标题**   | 配置验证系统（Pydantic 模型验证 + 必填项校验 + 范围校验）                                               |
| **状态**   | todo                                                                               |
| **优先级**  | medium                                                                             |
| **核心诉求** | 为 `config.yaml` 加载流程引入 Pydantic 模型验证，解决当前无验证导致的拼写错误静默通过、类型错误运行时暴露、缺少必填项时错误信息不明确等问题 |

***

## 现状调研

### 1. 当前配置加载机制

主配置加载函数位于 [src/utils.py:19-55](file:///b:/project/ash-easy-rag/src/utils.py#L19-L55)：

```python
def load_config(config_path: str = "config.yaml") -> dict[str, Any]:
    # yaml.safe_load() 直接返回 dict，无任何结构验证
    # 有缓存机制（_config_cache）
    # 有 data_dir 路径重写（_resolve_data_paths）
    # 返回类型：dict[str, Any]，完全无类型约束
```

**关键问题**：

* `yaml.safe_load()` 返回原始 `dict`，无 schema 约束

* 字段缺失 → 消费端用 `.get()` 带默认值或直接 `[]` 访问，行为不一致

* 类型错误 → 运行时才暴露，错误信息不友好

* 值域越界 → 无任何检查

### 2. Pydantic 已是项目依赖

[pixi.toml:102](file:///b:/project/ash-easy-rag/pixi.toml#L102) 已声明：

```toml
pydantic = ">=2.13.3, <3"     # Data validation
```

**无需新增依赖**，这是 Issue 描述中的担忧之一，现已消除。

### 3. 项目中已有 Pydantic 使用先例

| 模块       | 文件                                                                                      | 用法                                                                 |
| -------- | --------------------------------------------------------------------------------------- | ------------------------------------------------------------------ |
| Issue 系统 | [src/issue/models.py](file:///b:/project/ash-easy-rag/src/issue/models.py)              | `IssueConfig`、`Issue` 等模型，使用 `BaseModel`、`Field`、`field_validator` |
| 实验配置     | [src/experiment\_schemas.py](file:///b:/project/ash-easy-rag/src/experiment_schemas.py) | `ExperimentConfigSchema`，使用 `model_validator` 进行丰富验证               |

### 4. config.yaml 结构（387 行，20 个顶层字段）

| 顶层键               | 类型                    | 关键验证需求                                                             |
| ----------------- | --------------------- | ------------------------------------------------------------------ |
| `active_mode`     | str                   | 需是 `llm_presets` 中已有的 key                                          |
| `data_dir`        | str                   | 路径合法性                                                              |
| `llm_presets`     | dict\[str, LLMPreset] | 每个 preset 需 model\_name/temperature/max\_tokens/api\_key/base\_url |
| `parser`          | ParserConfig          | primary 需在合法值内；嵌套子配置                                               |
| `chunker`         | ChunkerConfig         | chunk\_size > 0, overlap < chunk\_size, strategy 合法值               |
| `embedding`       | EmbeddingConfig       | model\_name 必填, batch\_size > 0                                    |
| `vector_store`    | VectorStoreConfig     | type 合法值, distance 合法值                                             |
| `retrieval`       | RetrievalConfig       | method 合法值, top\_k > 0, 嵌套 bm25/hybrid/reranker/query\_rewrite     |
| `generation`      | GenerationConfig      | max\_context\_tokens > 0                                           |
| `experiments`     | ExperimentsConfig     | 嵌套 profiling/reuse                                                 |
| `meals`           | MealsConfig           | dir/collection\_prefix/default\_name                               |
| `artifacts`       | ArtifactsConfig       | dir                                                                |
| `llm_evaluator`   | LLMEvaluatorConfig    | 嵌套各指标 temperature/max\_tokens                                      |
| `evaluation`      | EvaluationConfig      | backends 合法值, metrics\_preset 合法值                                  |
| `llm_retry`       | LLMRetryConfig        | max\_retries >= 0, delays > 0                                      |
| `test_generation` | TestGenerationConfig  | 嵌套 hybrid/document\_level                                          |
| `token_cost`      | TokenCostConfig       | 价格非负                                                               |
| `query_history`   | QueryHistoryConfig    | max\_entries > 0                                                   |
| `logging`         | LoggingConfig         | level 合法值                                                          |
| `agent`           | AgentConfig           | 嵌套 checkpoint/defaults                                             |

### 5. 调用 `load_config()` 的位置（影响范围）

**核心模块**：`pipeline.py`、`app.py`、`indexer.py`、`interactive_qa.py`
**Agent 模块**：`tools.py`（10+ 处）、`graph.py`、`config.py`、`reporters/`
**UI 模块**：`app_pages/qa_demo.py`
**CLI 模块**：`artifact_cli.py`、`case_collector.py`
**测试文件**：大量 patch `src.utils.load_config`

### 6. 现有验证分散度

各模块各自做运行时校验（如 `sampler.py` 的 `ConfigurationError`、`embedder.py` 的配置校验、`query_rewriter.py` 的 strategy 合法性等），无统一入口。

***

## 可行性评估

| 维度       | 评估                                                       |
| -------- | -------------------------------------------------------- |
| **依赖**   | ✅ pydantic 已安装，无需新增                                      |
| **先例**   | ✅ 项目内已有两处 Pydantic 模型使用                                  |
| **向后兼容** | ⚠️ 需确保所有字段有默认值，`load_config()` 返回类型变更影响面广                |
| **工作量**  | 中等 — 20 个顶层字段需建模，但大部分是简单类型+范围校验                          |
| **风险**   | ⚠️ `load_config()` 返回类型从 `dict` 变为 Pydantic 模型会破坏所有消费端代码 |

***

## 实施计划

### 策略选择：渐进式引入，保持向后兼容

**核心原则**：`load_config()` 继续返回 `dict[str, Any]`，Pydantic 验证作为中间层，验证通过后转回 dict。这样所有消费端代码零改动。

### 步骤

#### Step 1: 创建 Pydantic 配置模型文件 `src/config_schema.py`

定义嵌套 Pydantic 模型，对应 config.yaml 层级：

* `LLMPresetConfig` — model\_name, temperature (0-2), max\_tokens (>0), api\_key, base\_url

* `ParserPymupdf4llmConfig` — header/footer/page\_separators 等 bool 字段

* `ParserFitzConfig` — header\_filter/footer\_filter 等 + noise\_patterns list

* `ParserPdfplumberConfig` — strategy/table\_settings/quality\_filter/replace\_policy

* `ParserConfig` — input\_dir, primary (Literal), table\_enhancer (Literal), pymupdf4llm, fitz, pdfplumber

* `ChunkerSemanticConfig` — similarity\_threshold (0-1), breakpoint\_percentile, min\_chunk\_size (>0)

* `ChunkerConfig` — strategy (Literal), encoding (Literal), chunk\_size (>0), chunk\_overlap (>=0, \<chunk\_size), cross\_page\_overlap (>=0), semantic

* `EmbeddingConfig` — model\_name, device, batch\_size (>0), query\_instruction

* `VectorStoreConfig` — type (Literal), collection\_name, persist\_dir, distance (Literal)

* `BM25Config` — k1 (>0), b (0-1)

* `HybridConfig` — fusion (Literal), rrf\_k (>0), vector\_weight (0-1), bm25\_weight (0-1)

* `RerankerConfig` — enabled, model\_name, device, top\_n (>0)

* `QueryRewriteConfig` — enabled, strategy (Literal), num\_queries (>0)

* `RetrievalConfig` — method (Literal), top\_k (>0), score\_threshold (0-1), bm25, hybrid, reranker, query\_rewrite

* `GenerationConfig` — system\_prompt, max\_context\_tokens (>0)

* `ProfilingConfig` — enabled, monitor\_interval (>0), generate\_charts

* `ReuseConfig` — mode (Literal), backup\_before\_append

* `ExperimentsConfig` — dir, configs\_dir, profiling, reuse

* `MealsConfig` — dir, collection\_prefix, default\_name

* `ArtifactsConfig` — dir

* `LLMEvaluatorSubConfig` — temperature (0-2), max\_tokens (>0)

* `LLMEvaluatorConfig` — model\_name, base\_url, 各指标子配置

* `EvaluationConfig` — backends (list\[Literal]), resolution\_strategy (Literal), backend\_priority, metrics\_preset (Literal), ragas, concurrent\_queries (>0), builtin\_concurrent\_workers (>0)

* `LLMRetryConfig` — max\_retries (>=0), base\_delay (>0), max\_delay (>0)

* `TestGenerationHybridConfig` — enabled, segment\_size (>0), compact\_segment\_max\_chars (>0), 等

* `TestGenerationDocumentLevelConfig` — enabled, default\_num\_questions (>0), type\_distribution, quality\_control

* `TestGenerationConfig` — default\_strategy (Literal), default\_num\_questions (>0), max\_retries (>=0), hybrid, document\_level

* `TokenCostModelConfig` — input\_price\_per\_1k (>=0), output\_price\_per\_1k (>=0), conversion\_factor (>0)

* `TokenCostConfig` — models: dict\[str, TokenCostModelConfig]

* `QueryHistoryConfig` — max\_entries (>0), dir

* `LoggingConfig` — level (Literal), format, log\_dir, rotation, retention

* `AgentDefaultsConfig` — parser\_name, enhancer\_name, chunk\_size (>0), chunk\_overlap (>=0), 等

* `AgentConfig` — checkpoint, trashbin\_dir, maintenance\_reports\_dir, subprocess\_timeout (>0), defaults

* `AppConfig` — 顶层模型，包含所有上述字段

**验证规则**：

* `chunk_overlap < chunk_size`（跨字段校验，用 `model_validator`）

* `active_mode` 必须是 `llm_presets` 中已有的 key（跨字段校验）

* `bm25_weight + vector_weight ≈ 1.0`（可选，warning 级别）

* 所有字段都有默认值，确保向后兼容

#### Step 2: 修改 `load_config()` 集成验证

在 [src/utils.py](file:///b:/project/ash-easy-rag/src/utils.py) 的 `load_config()` 中：

```python
from src.config_schema import AppConfig

def load_config(config_path: str = "config.yaml") -> dict[str, Any]:
    # ... 现有逻辑：yaml.safe_load + data_dir 路径重写 ...
    
    # 新增：Pydantic 验证
    try:
        validated = AppConfig(**config)
        config = validated.model_dump()
    except ValidationError as e:
        logger.error(f"Configuration validation failed:\n{e}")
        raise ConfigurationError(f"Invalid configuration: {e}") from e
    
    # ... 现有逻辑：缓存 + 返回 ...
```

**关键**：验证后用 `model_dump()` 转回 `dict`，返回类型不变，所有消费端零改动。

#### Step 3: 编写测试 `tests/test_config_schema.py`

* 测试正常配置加载通过验证

* 测试缺失必填字段时抛出 `ConfigurationError`

* 测试类型错误（如 chunk\_size 写成字符串）

* 测试范围校验（如 chunk\_size <= 0, overlap >= chunk\_size）

* 测试枚举值校验（如 strategy 不在合法值内）

* 测试跨字段校验（如 active\_mode 指向不存在的 preset）

* 测试默认值填充

* 测试向后兼容性（现有 config.yaml 不报错）

#### Step 4: 运行现有测试确保无回归

运行 `pixi run test` 确保所有现有测试通过。

#### Step 5: 提交

按 Conventional Commits 规范提交。

***

## 风险与注意事项

1. **返回类型兼容性**：`model_dump()` 返回的 dict 与 `yaml.safe_load()` 返回的 dict 可能有细微差异（如 None vs 缺失字段），需仔细测试
2. **缓存机制**：当前 `_config_cache` 缓存的是原始 dict，验证后的 dict 也应缓存
3. **实验配置覆盖**：`deep_merge()` 合并实验配置后产生的 dict 也应通过验证，但这是后续优化
4. **config.yaml 注释**：Pydantic 验证不涉及 YAML 注释，不影响用户体验
5. **性能**：Pydantic 验证开销极小（毫秒级），且有缓存机制，不影响性能

