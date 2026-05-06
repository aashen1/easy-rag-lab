# 瘦身计划书：ash-easy-rag 架构精简

> 目标：让项目从"大而全"变成"小而精"，面试 15 分钟能讲透
> 原则：不动 Issue 系统；保留 Agent（加分项）；保留 Meal 核心（实验系统依赖）

***

## 阶段总览

| 阶段 | 主题                | 预估改动量                                     | 可独立执行 |
| -- | ----------------- | ----------------------------------------- | ----- |
| P0 | 双重接口清理            | 删 \~400 行 + 改 \~30 处导入                    | ✅     |
| P1 | CLI 统一            | 重写 main.py + 删 testset\_cli + 改 pixi.toml | ✅     |
| P2 | Pydantic 配置验证精简   | 897→\~150 行                               | ✅     |
| P3 | Meal 系统瘦身         | 2565→\~1200 行                             | ✅     |
| P4 | Strategy 模式简化     | 删 \~200 行 + 改 pipeline.py                 | ✅     |
| P5 | ParserRegistry 简化 | 385→\~60 行                                | ✅     |
| P6 | 杂项清理              | 散落各处的小问题                                  | ✅     |

每个阶段独立可执行，互不依赖，可以跨对话分批完成。

***

## P0：双重接口清理

### 问题

`src/core/ops/` 是为 Agent 设计的函数式门面层，`src/` 根目录是底层实现。但迁移未完成，导致：

* Agent tools 全部用 `core/ops`

* Pipeline 全部用 `src/` 根模块

* Meal 混合使用两者

* `core/ops/query.py` 的 `query_rag()` 是死代码（无生产调用者）

### 方案：统一到 `src/` 根模块，删除 `core/ops/`

理由：`core/ops` 是薄封装层，功能完全依赖底层实现。统一后减少一层间接调用，代码更直观。

### 具体步骤

#### P0-1：删除 `core/ops/query.py`（死代码）

* 文件：`src/core/ops/query.py`

* 操作：移入 `.trashbin/`

* 影响：仅测试文件 `tests/test_core_ops/test_query.py` 引用，同步移入 `.trashbin/`

* 更新 `src/core/ops/__init__.py`，移除 `query_rag` 导出

#### P0-2：将 Agent tools 的导入从 `core/ops` 改为 `src/` 根模块

需要修改 `src/agent/tools.py` 中的以下导入：

| 当前导入                                                                     | 改为                                                                        |
| ------------------------------------------------------------------------ | ------------------------------------------------------------------------- |
| `from src.core.ops.parse import parse_pdf`                               | `from src.parsers.registry import get_parser` + 调用方式调整                    |
| `from src.core.ops.parse import enhance_page, enhance_table`             | `from src.parsers.pdfplumber_enhancer import PdfPlumberEnhancer` + 调用方式调整 |
| `from src.core.ops.chunk import chunk_parsed`                            | `from src.chunker import chunk_text, chunk_text_page_aware` + 调用方式调整      |
| `from src.core.ops.embed import embed_chunks`                            | `from src.embedder import Embedder` + 直接调用                                |
| `from src.core.ops.index import index_chunks, delete_source_and_reindex` | `from src.indexer import VectorIndexer` + 直接调用                            |
| `from src.core.ops.evaluate import evaluate_single`                      | `from eval.evaluators.builtin_evaluator import BuiltinEvaluator` 或保留为独立函数 |

**注意**：`core/ops` 的函数签名与底层模块不同（例如 `parse_pdf` 接收文件路径，而 `get_parser` 返回 parser 实例），需要逐一适配调用方式。这是 P0 中最复杂的部分。

#### P0-3：将 Meal manager 的 `core/ops` 导入改为 `src/` 根模块

* 文件：`src/meal/manager.py` L1474

* 当前：`from src.core.ops.parse import parse_pdf`

* 改为：`from src.parsers.registry import get_parser` 或直接调用 `src.parser` 的函数

#### P0-4：删除整个 `src/core/ops/` 目录

* 确认所有生产代码不再引用后，将 `src/core/ops/` 移入 `.trashbin/`

* 同步移入 `.trashbin/`：`tests/test_core_ops/` 整个目录

* 更新 `src/core/__init__.py`（如果存在）

#### P0-5：验证

* `pixi run ruff-check` 无错误

* `pixi run test-unit` 全绿

* `pixi run test` 全绿

***

## P1：CLI 统一

### 问题

当前 4 个 CLI 入口使用 3 种不同框架，用户需要记住多个命令：

| 入口            | 框架              | 调用方式                    |
| ------------- | --------------- | ----------------------- |
| main.py       | argparse        | `python main.py --flag` |
| issue/cli.py  | Click           | `pixi run issue`        |
| agent/cli.py  | argparse + REPL | `pixi run agent`        |
| testset\_cli/ | argparse        | `pixi run testset`      |

### 方案：统一为 Click 单入口 `rag`

目标命令结构：

```
pixi run rag query "什么是ROE?"              # 单次查询
pixi run rag query --interactive             # 交互式问答
pixi run rag query --meal my_meal            # 指定 meal
pixi run rag build-index                     # 构建索引
pixi run rag build-index --rebuild           # 重建索引
pixi run rag build-index --sample-count 5    # 采样构建

pixi run rag meal list                       # 列出 meal
pixi run rag meal create [NAME]              # 创建 meal
pixi run rag meal info NAME                  # 查看 meal 详情
pixi run rag meal delete NAME                # 删除 meal
pixi run rag meal rename OLD NEW             # 重命名 meal
pixi run rag meal copy SRC DST               # 复制 meal
pixi run rag meal repair NAME                # 修复 meal
pixi run rag meal merge M1 M2 ...            # 合并 meal
pixi run rag meal extend NAME --add-pdfs ... # 扩展 meal

pixi run rag testset generate --meal NAME    # 生成测试集
pixi run rag testset generate --strategy hybrid --num 20
pixi run rag testset migrate                 # 迁移旧格式
pixi run rag testset enrich --input FILE     # 丰富测试集
pixi run rag testset review --input FILE     # 审查测试集
pixi run rag testset approve --input FILE    # 批准测试集
pixi run rag testset compose merge --sources A B
pixi run rag testset compose filter --input FILE
pixi run rag testset compose incremental --base FILE

pixi run rag issue create --type bug --title "描述"
pixi run rag issue list
pixi run rag issue show ID
pixi run rag issue start ID
pixi run rag issue done ID
pixi run rag issue ...                       # 其余 issue 子命令原样保留

pixi run rag agent                           # 启动维修工 Agent
pixi run rag agent --full                    # 全量模式
pixi run rag agent --session-id xxx          # 恢复会话

pixi run rag experiment --config xxx         # 运行实验
pixi run rag parser-bench --config xxx       # 解析器基准测试
```

### 具体步骤

#### P1-1：创建 `src/cli/` 包结构

```
src/cli/
├── __init__.py          # 入口点 main() 函数
├── root.py              # 根命令组 @click.group()
├── query.py             # query 子命令组
├── build.py             # build-index 子命令
├── meal.py              # meal 子命令组
├── testset.py           # testset 子命令组
├── issue.py             # issue 子命令组（委托给 src/issue/cli.py）
├── agent_cmd.py         # agent 子命令（委托给 src/agent/cli.py）
└── experiment.py        # experiment / parser-bench 子命令
```

#### P1-2：迁移 main.py 功能到 src/cli/

按子命令拆分 main.py 的 1212 行：

| main.py 中的功能                                                                                                                                               | 目标文件              | 预估行数    |
| ---------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------- | ------- |
| `--query` / `--interactive`                                                                                                                                | `query.py`        | \~80 行  |
| `--build-index` / `--rebuild` / 采样参数                                                                                                                       | `build.py`        | \~60 行  |
| `--create-meal` / `--list-meals` / `--meal-info` / `--delete-meal` / `--rename-meal` / `--copy-meal` / `--repair-meal` / `--merge-meals` / `--extend-meal` | `meal.py`         | \~200 行 |
| `--generate-test-set` / `--merge-test-sets`                                                                                                                | `testset.py` 的一部分 | \~60 行  |
| `--history-list` / `--history-show` / `--history-save`                                                                                                     | `query.py` 的子命令   | \~80 行  |
| `--llm-report-only`                                                                                                                                        | `experiment.py`   | \~20 行  |
| 辅助函数 (`_build_sampling_config`, `_resolve_meal_name`, `_print_query_result`)                                                                               | `utils.py` 或各自文件  | \~50 行  |

#### P1-3：迁移 testset\_cli 功能到 src/cli/testset.py

将 `src/testset_cli/` 的 6 个子命令（generate/migrate/enrich/review/approve/compose）合并到 `src/cli/testset.py`。

* `testset_cli/__init__.py` 的 `build_parser()` 逻辑转为 Click 子命令

* `testset_cli/generate.py` 的 `run_generate()` 转为 Click 命令

* 其余同理

#### P1-4：将 issue/cli.py 委托到 src/cli/issue.py

不重写 issue CLI，而是创建一个薄委托层：

```python
# src/cli/issue.py
@click.group()
def issue():
    """Issue management commands."""
    pass

# 将 src/issue/cli.py 的所有命令注册到这个组下
# 方案：直接 import src.issue.cli 的命令并添加到 issue 组
```

或者更简单：直接在 `src/cli/root.py` 中注册 `src.issue.cli.cli` 作为子命令。

#### P1-5：将 agent/cli.py 委托到 src/cli/agent\_cmd.py

```python
# src/cli/agent_cmd.py
@click.command()
@click.option("--session-id", ...)
@click.option("--pdf", ...)
@click.option("--full", is_flag=True)
def agent(session_id, pdf, full):
    """Start the maintenance agent."""
    from src.agent.cli import run_agent
    run_agent(session_id=session_id, pdf_path=pdf, full_mode=full)
```

#### P1-6：更新 pixi.toml 任务

| 当前任务           | 改为                                                              |
| -------------- | --------------------------------------------------------------- |
| `interactive`  | `python -m src.cli rag query --interactive`                     |
| `issue`        | `python -m src.cli rag issue`                                   |
| `testset`      | `python -m src.cli rag testset`                                 |
| `agent`        | `python -m src.cli rag agent`                                   |
| `exp`          | `python -m src.cli rag experiment --config {{ config }}.yaml`   |
| `parser-bench` | `python -m src.cli rag parser-bench --config {{ config }}.yaml` |

新增：

* `rag` 任务：`python -m src.cli` （通用入口）

#### P1-7：将旧入口移入 .trashbin/

* `main.py` → `.trashbin/`

* `src/testset_cli/` → `.trashbin/`

#### P1-8：验证

* `pixi run rag query "test"` 能正常查询

* `pixi run rag meal list` 能列出 meal

* `pixi run rag issue list` 能列出 issue

* `pixi run rag agent` 能启动 agent

* `pixi run rag testset generate --help` 显示帮助

* `pixi run test-unit` 全绿

***

## P2：Pydantic 配置验证精简

### 问题

* 39 个 Pydantic 类、167 个字段、897 行代码

* 全部设 `extra = "allow"`，类型安全被削弱

* 验证后立即 `model_dump()` 转回 dict，Pydantic 的类型提示优势完全未利用

* 真正有意义的验证只有 3 个跨字段验证器 + 约 30 个范围/枚举约束

### 方案：替换为精简的验证函数

保留所有有价值的验证逻辑（范围约束、枚举约束、跨字段验证），但用 \~150 行的验证函数替代 897 行的 Pydantic 模型。

### 具体步骤

#### P2-1：编写新验证函数 `src/config_validator.py`（\~150 行）

```python
def validate_config(config: dict) -> dict:
    """Validate config dict. Returns config on success, raises ValueError on failure."""

    # 1. 范围约束（约 40 行）
    _check_ranges(config, {
        ("chunker",): {"chunk_size": (1, None), "chunk_overlap": (0, None), ...},
        ("retrieval",): {"top_k": (1, None), "score_threshold": (0, 1), ...},
        ...
    })

    # 2. 枚举约束（约 20 行）
    _check_enums(config, {
        ("parser", "primary"): ["pymupdf4llm", "fitz"],
        ("chunker", "strategy"): ["fixed", "semantic"],
        ...
    })

    # 3. 跨字段验证（约 15 行）
    _check_cross_fields(config)

    return config
```

#### P2-2：修改 `src/utils.py` 的 `load_config()`

```python
# 当前：
from src.config_schema import AppConfig
validated = AppConfig(**config)
config = validated.model_dump()

# 改为：
from src.config_validator import validate_config
config = validate_config(config)
```

#### P2-3：将 `src/config_schema.py` 移入 `.trashbin/`

#### P2-4：更新测试

* 将 `tests/test_config_schema.py` 改为测试 `validate_config()` 函数

* 保留所有有价值的测试用例（范围越界、枚举非法、跨字段冲突）

* 删除仅测试 Pydantic 特性的用例（如 `test_extra_fields_allowed`）

#### P2-5：验证

* `pixi run test-unit` 全绿

* 故意写一个非法 config.yaml，确认 `validate_config()` 能报错

***

## P3：Meal 系统瘦身

### 问题

* MealManager 是 1582 行的上帝类，22 个方法

* 6 个无人调用的 CRUD 方法占 565 行（rename/copy/merge/extend/repair/delete）

* Pointer 机制几乎未使用

* 全量模式快捷方法仅内部使用

### 方案：保留核心，删除无人调用的方法

### 具体步骤

#### P3-1：从 MealManager 中删除无人调用的方法

以下方法**无 Python 代码从外部调用**（可能仅 CLI 使用，但 CLI 统一后这些命令也会保留，只是入口变了）：

| 方法                          | 行数(估) | 决策                                           |
| --------------------------- | ----- | -------------------------------------------- |
| `rename_meal()`             | \~45  | **保留**（CLI 需要）                               |
| `copy_meal()`               | \~60  | **保留**（CLI 需要）                               |
| `merge_meals()`             | \~135 | **保留**（CLI 需要）                               |
| `extend_meal()`             | \~145 | **保留**（CLI 需要）                               |
| `repair_meal()`             | \~140 | **保留**（CLI 需要）                               |
| `delete_meal()`             | \~40  | **保留**（CLI 需要）                               |
| `create_meal_manual()`      | \~140 | **合并到** **`create_meal`**（增加 `pdf_files` 参数） |
| `find_equivalent_meals()`   | \~15  | **删除**（仅被 `find_full_dataset_meal` 调用）       |
| `find_full_dataset_meal()`  | \~60  | **保留**（test\_generation 依赖）                  |
| `get_or_create_full_meal()` | \~60  | **保留**（UI 依赖）                                |

**修正**：经过重新审视，CLI 统一后这些命令仍然需要保留。真正的瘦身来自：

#### P3-2：合并 `create_meal_manual` 到 `create_meal`

`create_meal_manual` 与 `create_meal` 的区别仅在于 PDF 来源（手动指定 vs 采样）。在 `create_meal` 中增加一个可选参数 `pdf_files: list[str] | None = None`，当提供时跳过采样逻辑。

预计减少 \~100 行。

#### P3-3：简化 ArtifactCache 的 Pointer 机制

* `save_pointer()` 仅在 `pipeline.build_index` 无采样模式下调用一次

* `resolve_pointer()` 完全无外部消费者

* 删除 `resolve_pointer()` 和 `pointers_dir` 属性

* 保留 `save_pointer()` 但标记为内部方法

预计减少 \~30 行。

#### P3-4：内联全量模式快捷方法

将 `get_full_parsed_dir`、`save_full_manifest`、`load_full_manifest`、`is_full_parsed_valid` 内联到调用点（仅在 `MealManager.create_meal` 内部使用）。

预计减少 \~50 行。

#### P3-5：删除 `_infer_equivalence_groups` 及相关字段

`equivalence_groups` 字段无代码读取使用，删除：

* `MealConfig.equivalence_groups` 字段

* `utils.py` 中的 `_infer_equivalence_groups()` 函数

* `MealManager` 中设置 `equivalence_groups` 的逻辑

预计减少 \~40 行。

#### P3-6：验证

* `pixi run test-unit` 全绿

* `pixi run rag meal list` 正常

* `pixi run rag build-index` 正常

* 实验系统 `pixi run exp smoke_quick` 正常

***

## P4：Strategy 模式简化

### 问题

* `RetrievalStrategy` 的 3 个子类方法体完全相同，纯粹是空壳代理

* `QueryRewriteStrategy` 的分发仍靠 pipeline 中的 if/elif

* `RetrievalResult` 和 `RewrittenQuery` 数据类仅在策略文件内部使用

### 方案：删除 Strategy 类，直接在 pipeline 中调用

### 具体步骤

#### P4-1：删除 `src/retrieval_strategies.py`

* 移入 `.trashbin/`

* 修改 `pipeline.py` 中的检索逻辑：

```python
# 当前：
if effective_method == "bm25" and self.bm25_retriever is not None:
    retrieval_strategy = BM25RetrievalStrategy(self.bm25_retriever)
    result = retrieval_strategy.retrieve(question, top_k=effective_top_k)
    chunks = result.chunks
elif effective_method == "hybrid" and self.bm25_retriever is not None:
    retrieval_strategy = HybridRetrievalStrategy(self.hybrid_retriever)
    result = retrieval_strategy.retrieve(question, top_k=effective_top_k)
    chunks = result.chunks
else:
    retrieval_strategy = VectorRetrievalStrategy(self.retriever)
    result = retrieval_strategy.retrieve(question, top_k=effective_top_k)
    chunks = result.chunks

# 简化为：
if effective_method == "bm25" and self.bm25_retriever is not None:
    chunks = self.bm25_retriever.retrieve(question, top_k=effective_top_k)
elif effective_method == "hybrid" and self.hybrid_retriever is not None:
    chunks = self.hybrid_retriever.retrieve(question, top_k=effective_top_k)
else:
    chunks = self.retriever.retrieve(question, top_k=effective_top_k)
```

#### P4-2：简化 `src/query_rewrite_strategies.py`

保留文件但大幅简化：

```python
def rewrite_query(query: str, rewriter: QueryRewriter | None, strategy: str = "hyde") -> tuple[list[str], bool]:
    """Rewrite query using specified strategy. Returns (queries, is_multi_query)."""
    if rewriter is None:
        return [query], False
    result = rewriter.rewrite(query)
    if strategy == "multi_query":
        return result.queries, True
    return result.queries, False
```

删除 `QueryRewriteStrategy`、`NoRewriteStrategy`、`HyDERewriteStrategy`、`MultiQueryRewriteStrategy`、`RewrittenQuery` 数据类。

#### P4-3：更新 pipeline.py 中的调用

```python
# 当前：
rewrite_strategy = self._get_rewrite_strategy()
rewritten = rewrite_strategy.rewrite(question)
rewritten_queries = rewritten.queries
is_multi = rewritten.is_multi

# 简化为：
rewritten_queries, is_multi = rewrite_query(question, self.query_rewriter, effective_rewrite_strategy)
```

删除 `_get_rewrite_strategy()` 方法。

#### P4-4：更新测试

* 删除 `tests/test_retrieval_strategies.py`（移入 .trashbin/）

* 简化 `tests/test_query_rewrite_strategies.py`

* 在 `tests/test_pipeline.py` 中补充检索和改写的集成测试

#### P4-5：验证

* `pixi run test-unit` 全绿

* `pixi run rag query "test"` 正常

***

## P5：ParserRegistry 简化

### 问题

* 385 行注册表代码服务 2 个 primary parser + 1 个 enhancer

* 3 套几乎相同的 register/lazy\_import 逻辑

* 公开 `register_*` API 从未被外部调用

### 方案：替换为简单的工厂函数

### 具体步骤

#### P5-1：创建简化版 `src/parsers/registry.py`（\~60 行）

```python
_PARSERS = {
    "pymupdf4llm": ("src.parsers.pymupdf4llm_parser", "PyMuPDF4LLMParser"),
    "fitz": ("src.parsers.fitz_parser", "FitzParser"),
}

_ENHANCERS = {
    "pdfplumber": ("src.parsers.pdfplumber_enhancer", "PdfPlumberEnhancer"),
}

def get_parser(name: str, config: dict) -> BaseParser:
    """Get a parser instance by name."""
    if name not in _PARSERS:
        raise ValueError(f"Unknown parser: {name}. Available: {list(_PARSERS.keys())}")
    module_path, class_name = _PARSERS[name]
    module = importlib.import_module(module_path)
    cls = getattr(module, class_name)
    return cls(config)

def get_enhancer(name: str, config: dict) -> TableEnhancer | None:
    """Get a table enhancer by name. Returns None if name is 'null'."""
    if name == "null" or name is None:
        return None
    if name not in _ENHANCERS:
        raise ValueError(f"Unknown enhancer: {name}. Available: {list(_ENHANCERS.keys())}")
    module_path, class_name = _ENHANCERS[name]
    module = importlib.import_module(module_path)
    cls = getattr(module, class_name)
    return cls(config)

def list_parsers() -> list[str]:
    return list(_PARSERS.keys())

def list_enhancers() -> list[str]:
    return list(_ENHANCERS.keys())
```

#### P5-2：更新所有调用 `ParserRegistry` 的代码

主要调用者：

* `src/parser.py` — `ParserRegistry.get()`, `ParserRegistry.get_composite()`, `ParserRegistry.get_enhancer()`

* `src/agent/tools.py` — `ParserRegistry.get()`

* `src/meal/manager.py` — `ParserRegistry.get()`

替换为新的 `get_parser()` / `get_enhancer()` 函数。

#### P5-3：验证

* `pixi run test-unit` 全绿

* `pixi run rag build-index` 正常

***

## P6：杂项清理

### P6-1：删除 `core/ops/query.py` 的死代码

已在 P0 中覆盖。

### P6-2：简化异常层次

**决策：暂不处理。** 异常层次虽然过度工程，但改动收益不大（仅语义标签），且涉及 179 处 raise，改动面太大。

### P6-3：简化 DocumentLoader ABC

**决策：暂不处理。** 只有 2 个实现，但 LazyDocumentLoader 有实际价值，改动收益不大。

### P6-4：清理 `main.py` 中 `--generate-test-set` 与 `testset generate` 的重复

已在 P1 中覆盖（统一 CLI 后自然消除）。

### P6-5：删除 `core/ops/evaluate.py` 的冗余

`evaluate_single()` 被 Agent tools 调用。如果 P0 中决定删除 `core/ops`，需要将此函数移到合适位置（如 `src/evaluate.py` 或 `eval/` 下）。

**具体方案**：将 `evaluate_single()` 移到 `src/eval_helpers.py`（新文件，\~50 行），Agent tools 从那里导入。

### P6-6：统一 `_parse_pdfs_with_registry` 与 pipeline 的解析逻辑

MealManager 的 `_parse_pdfs_with_registry` 和 pipeline 的 `parse_all_pdfs_unified` 是两套解析路径。

**方案**：让 `_parse_pdfs_with_registry` 调用 `parse_all_pdfs_unified`，消除重复。

***

## 执行顺序建议

推荐按以下顺序执行，每个阶段独立提交：

```
P0（双重接口清理）→ P4（Strategy 简化）→ P5（ParserRegistry 简化）→ P2（Pydantic 精简）→ P3（Meal 瘦身）→ P1（CLI 统一）→ P6（杂项）
```

理由：

* P0 最独立，改动面最小，先做降低后续复杂度

* P4、P5 是独立的模式简化，互不依赖

* P2 精简配置验证，为后续改动减少配置相关代码量

* P3 Meal 瘦身，需要理解 Meal 与实验系统的关系

* P1 CLI 统一最复杂，放后面做，因为前面的精简会让 main.py 更小

* P6 收尾

***

## 预期效果

| 指标                | 当前              | 精简后                | 缩减    |
| ----------------- | --------------- | ------------------ | ----- |
| Python 源文件数       | \~224           | \~200              | -11%  |
| 业务代码行数            | \~30,200        | \~24,000           | -20%  |
| CLI 入口数           | 4               | 2（rag + streamlit） | -50%  |
| 配置验证行数            | 897             | \~150              | -83%  |
| Strategy 模式文件     | 2（\~200 行）      | 0（内联到 pipeline）    | -100% |
| ParserRegistry 行数 | 385             | \~60               | -84%  |
| Meal 系统行数         | \~2,565         | \~2,200            | -14%  |
| 双重接口              | core/ops + src/ | 仅 src/             | 消除    |

