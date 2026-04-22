# RF-002 评估报告：项目结构整理 — 根目录 .py 文件

> **评估编号**：RF-002
> **评估日期**：2026-04-23
> **评估对象**：根目录下 `main.py`（704 行）和 `interactive.py`（79 行）
> **评估目标**：分析两个入口脚本的结构合理性，评估是否需要迁移、合并或保持现状

---

## 1. 依赖关系分析

### 1.1 main.py 的导入和依赖模块

| 导入项 | 来源 | 用途 |
|--------|------|------|
| `argparse` | 标准库 | CLI 参数解析 |
| `sys` | 标准库 | 退出码控制 |
| `Any, Dict` | `typing` | 类型标注 |
| `logger` | `loguru` | 日志记录 |
| `MealManager, MealStatus, validate_meal_name` | `src.meal` | Meal 数据集管理 |
| `RAGPipeline` | `src.pipeline` | RAG 流水线核心 |
| `SamplingConfig` | `src.sampler` | 采样配置 |
| `TestSetManager` | `src.test_set_manager` | 测试集管理 |
| `load_config, setup_logger` | `src.utils` | 配置加载与日志初始化 |

**延迟导入**（函数内部）：
- `src.meal.compute_file_sha256`（`_handle_repair_meal` 内）
- `src.test_generator.TestSetGenerator`（`_handle_generate_test_set` 内）
- `collections.defaultdict`（`_handle_list_meals` 内）

**CLI 参数分组**（共 6 组，约 30 个参数）：

| 参数组 | 参数 | 说明 |
|--------|------|------|
| 基础操作 | `--query`, `--build-index`, `--rebuild`, `--force-parse`, `--config`, `--llm-preset` | 查询与索引构建 |
| 采样控制 | `--sample-count`, `--sample-pages`, `--sample-ratio`, `--seed` | PDF 采样策略 |
| Meal 管理 | `--create-meal`, `--meal`, `--list-meals`, `--meal-info`, `--delete-meal`, `--rename-meal`, `--copy-meal`, `--repair-meal`, `--merge-meals`, `--extend-meal`, `--add-pdfs` | 数据集生命周期管理 |
| 测试集生成 | `--generate-test-set`, `--strategy`, `--num-questions`, `--name` | 测试集生成 |
| 测试集管理 | `--merge-test-sets` | 测试集合并 |
| 交互式问答 | `--meal`（无 `--query` 时触发） | 进入交互 Q&A 模式 |

**内部函数清单**（10 个）：

| 函数 | 行数 | 功能 |
|------|------|------|
| `main()` | 14-230 | 入口函数，参数解析与路由 |
| `_build_sampling_config()` | 232-249 | 构建采样配置 |
| `_handle_meal_info()` | 252-304 | 显示 Meal 详情 |
| `_handle_list_meals()` | 307-356 | 列出所有 Meal |
| `_handle_delete_meal()` | 359-364 | 删除 Meal |
| `_handle_rename_meal()` | 367-374 | 重命名 Meal |
| `_handle_copy_meal()` | 377-384 | 复制 Meal |
| `_handle_create_meal()` | 387-413 | 创建 Meal |
| `_handle_repair_meal()` | 416-496 | 修复 Meal |
| `_handle_generate_test_set()` | 499-529 | 生成测试集 |
| `_print_query_result()` | 532-556 | 格式化打印查询结果 |
| `_interactive_qa()` | 559-596 | **交互式问答循环** |
| `_handle_merge_meals()` | 599-625 | 合并 Meal |
| `_handle_extend_meal()` | 628-650 | 扩展 Meal |
| `_handle_merge_test_sets()` | 653-700 | 合并测试集 |

### 1.2 interactive.py 的导入和依赖模块

| 导入项 | 来源 | 用途 |
|--------|------|------|
| `argparse` | 标准库 | CLI 参数解析 |
| `logger` | `loguru` | 日志记录 |
| `RAGPipeline` | `src.pipeline` | RAG 流水线核心 |
| `load_config, setup_logger` | `src.utils` | 配置加载与日志初始化 |

**CLI 参数**（仅 2 个）：

| 参数 | 说明 |
|------|------|
| `--config` | 配置文件路径（默认 `config.yaml`） |
| `--llm-preset` | LLM 预设名称 |

**内部函数**（2 个）：

| 函数 | 行数 | 功能 |
|------|------|------|
| `interactive_chat()` | 9-56 | 交互式问答循环 |
| `main()` | 59-75 | 入口函数 |

### 1.3 功能重叠分析

两个文件的**核心重叠**在于交互式 Q&A 功能：

| 对比维度 | `main.py` → `_interactive_qa()` | `interactive.py` → `interactive_chat()` |
|----------|--------------------------------|----------------------------------------|
| **触发方式** | `--meal <name>`（无 `--query`） | 直接运行 `interactive.py` |
| **Meal 支持** | ✅ 指定 Meal 名称 | ❌ 无 Meal 概念，使用默认 Pipeline |
| **提示符** | `Q>` | `💬 You:` |
| **退出命令** | `quit` / `exit` / `q` | `quit` / `exit` / `q` |
| **退出消息** | `Exiting.` | `👋 再见！` |
| **Token 统计** | ✅ 退出时显示累计 token | ✅ 退出时显示累计 token |
| **来源显示** | 显示全部来源 + 相关度分数 | 仅显示前 3 个来源 + 相关度 |
| **来源格式** | 原始路径 | 提取文件名（去掉目录前缀） |
| **错误处理** | `logger.error` | `logger.error` + 用户友好中文提示 |
| **界面语言** | 英文 | 中文（含 emoji） |
| **集合信息** | 不显示 | 启动时显示 chunk 数量 |
| **Pipeline 初始化** | 传入 `meal_name` | 不传 `meal_name` |

**关键差异**：

1. **Meal 支持**：`main.py` 的交互模式绑定 Meal 系统，可指定数据集；`interactive.py` 使用默认 Pipeline，无法指定 Meal
2. **用户体验**：`interactive.py` 有更友好的中文界面和 emoji，启动时显示数据库信息；`main.py` 的交互模式更简洁
3. **来源展示**：`interactive.py` 限制来源数量为 3 个并格式化路径，`main.py` 展示全部来源
4. **功能定位**：`interactive.py` 是独立的"快速上手"入口；`main.py` 的 `_interactive_qa` 是 Meal 工作流的一部分

**结论**：`interactive.py` 的功能是 `main.py` 的**子集**，但存在 UI 细节差异（中文/英文、emoji、来源数量限制）。两者并非完全重复，而是面向不同场景的入口。

---

## 2. 迁移方案选项

### 方案 A：移入 `src/cli/` 目录

将 `main.py` 和 `interactive.py` 移入新建的 `src/cli/` 目录，根目录仅保留薄入口脚本或通过 `pixi.toml` 的 `[tasks]` 定义命令别名。

**目录结构示例**：
```
src/cli/
├── __init__.py
├── main.py          # 主 CLI 逻辑
├── interactive.py   # 交互式问答
└── handlers.py      # 各 _handle_* 函数（可选拆分）
```

**优点**：
- 根目录更整洁，符合"源码在 src/ 下"的惯例
- CLI 代码可被其他模块导入复用（如测试中 mock CLI 行为）
- 便于后续拆分 `main.py`（704 行）为多个子模块（handlers、formatters 等）
- 与 `src/` 下其他模块的导入风格一致

**缺点**：
- **破坏性变更最大**：所有 `pixi run python main.py` 命令需改为 `pixi run python src/cli/main.py` 或通过 pixi task 间接调用
- 文档引用更新量巨大（约 70+ 处 `main.py` 引用，涉及 `docs/getting-started.md`、`docs/cli-reference.md`、`docs/guides/meal-system.md` 等核心文档）
- 用户习惯需要改变，现有脚本和工作流全部失效
- `pixi.toml` 中未定义 `main.py` 相关的 task 入口，用户直接 `pixi run python main.py` 是约定俗成的用法
- 增加导入路径复杂度（`src.cli.main` vs 直接 `main`）
- 对于一个学习型 RAG 项目，结构过度工程化

### 方案 B：保持根目录（作为入口脚本）

维持现状，`main.py` 和 `interactive.py` 保留在根目录，作为项目入口脚本。

**优点**：
- **零迁移成本**，无需修改任何代码或文档
- 符合 Python 项目常见惯例（`main.py` 在根目录作为入口是广泛接受的做法）
- 用户习惯不变，所有现有命令和工作流继续有效
- `pixi run python main.py` 路径简短直观
- 对于学习型项目，根目录入口降低了理解门槛

**缺点**：
- 根目录仍有 2 个 .py 文件，结构不够"纯粹"
- `main.py` 已达 704 行，继续增长会导致维护困难
- `interactive.py` 与 `main.py` 的交互 Q&A 功能存在重叠，可能造成用户困惑（该用哪个？）
- 两个入口脚本的关系和定位不够清晰

### 方案 C：合并 `interactive.py` 到 `main.py`

将 `interactive.py` 的功能合并到 `main.py`，删除 `interactive.py`。`main.py` 新增 `--interactive` 参数作为显式入口，同时保留 `--meal <name>`（无 `--query`）时的隐式交互模式。

**合并后 CLI 用法**：
```bash
# 替代原 interactive.py 的用法
pixi run python main.py --interactive
pixi run python main.py --interactive --llm-preset opus

# 原有用法保持不变
pixi run python main.py --meal my_meal          # 进入 Meal 交互模式
pixi run python main.py --meal my_meal --query "问题"  # 单次查询
```

**优点**：
- **消除功能重叠**：统一入口，用户不再困惑于"该用哪个脚本"
- **减少维护负担**：只需维护一套交互式 Q&A 逻辑
- **保留 `interactive.py` 的 UI 优点**：可将中文界面、emoji、来源数量限制等特性作为 `--interactive` 模式的默认行为
- **迁移成本可控**：仅需更新 `interactive.py` 相关的少量文档引用（约 5 处）
- **单一入口更符合 CLI 工具设计原则**：类似 `git` 的子命令模式

**缺点**：
- `main.py` 行数会进一步增加（从 704 行增至约 730 行）
- 需要设计 `--interactive` 与 `--meal` 的交互逻辑（两者组合时的行为需明确定义）
- `interactive.py` 的"无 Meal 快速上手"场景需要在新入口中保留
- 合并后 `main.py` 的职责更重，但可通过内部函数拆分缓解

### 方案 D（补充）：保持根目录 + 内部重构

保持文件在根目录，但对 `main.py` 进行内部重构：将 `_handle_*` 函数和 `_interactive_qa` 提取到 `src/cli/` 模块中，根目录的 `main.py` 变为薄入口脚本。

**目录结构示例**：
```
main.py              # 薄入口（~30行）：解析参数 → 调用 src.cli
interactive.py       # 保留（或合并）
src/cli/
├── __init__.py
├── handlers.py      # 各 _handle_* 函数
├── interactive.py   # 交互式 Q&A 逻辑
└── formatters.py    # _print_query_result 等格式化函数
```

**优点**：
- 根目录入口不变，用户体验零影响
- `main.py` 从 704 行降至约 30 行，大幅提升可读性
- 业务逻辑移入 `src/`，可被测试和复用
- 渐进式重构，风险可控

**缺点**：
- 需要新建 `src/cli/` 模块，增加目录层级
- 需要处理导入路径变更
- 重构工作量中等

---

## 3. 影响范围评估

### 3.1 pixi.toml 入口脚本变更

当前 `pixi.toml` 中**未定义** `main.py` 或 `interactive.py` 的 task 入口。用户通过 `pixi run python main.py` 直接调用。

| 方案 | pixi.toml 变更 |
|------|---------------|
| A | 需新增 task：`qa = "python src/cli/main.py"` 等，或修改所有文档中的命令 |
| B | 无变更 |
| C | 可选：新增 `interactive = "python main.py --interactive"` task，替代原 `interactive.py` |
| D | 无变更（入口脚本路径不变） |

### 3.2 文档引用更新

通过搜索 `docs/` 目录，统计引用情况如下：

| 文件 | `main.py` 引用数 | `interactive.py` 引用数 |
|------|------------------|------------------------|
| `docs/getting-started.md` | 10 | 1 |
| `docs/cli-reference.md` | 17 | 2 |
| `docs/guides/meal-system.md` | 13 | 0 |
| `docs/guides/pdf-parsing.md` | 8 | 0 |
| `docs/guides/test-set-management.md` | 4 | 0 |
| `docs/guides/question-generation.md` | 2 | 0 |
| `docs/guides/token-tracking.md` | 2 | 0 |
| `docs/architecture.md` | 1 | 1 |
| `docs/backlog.md` | 1 | 0 |
| `docs/archive/` 下多个文件 | 若干 | 若干 |
| `exp_configs/README.md` | 3 | 0 |
| **合计（非 archive）** | **~61** | **~4** |

| 方案 | 文档更新量 |
|------|-----------|
| A | 约 65 处（所有 `main.py` 和 `interactive.py` 引用） |
| B | 0 |
| C | 约 4 处（仅 `interactive.py` 相关引用） |
| D | 0（可选择性更新 `architecture.md` 的结构描述） |

### 3.3 用户习惯影响

| 方案 | 用户习惯影响 |
|------|-------------|
| A | **高**：所有 `pixi run python main.py` 命令失效，需重新学习 |
| B | **无** |
| C | **低**：`main.py` 用法不变，仅 `interactive.py` 用户需改用 `main.py --interactive` |
| D | **无** |

### 3.4 .gitignore / .pre-commit-config 等配置影响

经检查：
- `.gitignore` 中无 `main.py` 或 `interactive.py` 的特定规则
- `.pre-commit-config.yaml` 中无对这两个文件的特定引用
- `pixi.toml` 的 `ruff-check` 和 `ruff-format` task 仅覆盖 `src/`、`eval/`、`tests/`，**不包含根目录 .py 文件**

| 方案 | 配置影响 |
|------|---------|
| A | `pixi.toml` 的 ruff task 需更新路径 |
| B | 无（但根目录 .py 文件仍不在 ruff 检查范围内，这是一个已存在的问题） |
| C | 无（同上） |
| D | `pixi.toml` 的 ruff task 需新增 `src/cli/` 路径 |

**注意**：当前根目录的 `main.py` 和 `interactive.py` **不在 ruff lint 范围内**（`pixi run lint` 仅检查 `src/ eval/ tests/`），这是一个代码质量盲区。无论选择哪个方案，都应将根目录 .py 文件纳入 lint 检查范围。

---

## 4. 推荐方案及理由

### 推荐：方案 C（合并 interactive.py 到 main.py）+ 方案 D 的部分思路

**具体建议**：

1. **合并 `interactive.py` 到 `main.py`**：
   - 新增 `--interactive` 参数，作为显式的交互式问答入口
   - 将 `interactive.py` 中的中文界面、emoji、来源数量限制等 UX 优化融入 `--interactive` 模式
   - 保留 `--meal <name>`（无 `--query`）时的隐式交互模式（行为不变）
   - `--interactive` 不指定 `--meal` 时，使用默认 Pipeline（等价于原 `interactive.py` 行为）
   - 删除 `interactive.py`

2. **后续可考虑内部重构**（方案 D 的思路）：
   - 当 `main.py` 进一步增长时，将 `_handle_*` 函数提取到 `src/cli/handlers.py`
   - 将 `_print_query_result` 和 `_interactive_qa` 提取到 `src/cli/interactive.py`
   - 根目录 `main.py` 变为薄入口脚本

3. **修复 lint 盲区**：
   - 在 `pixi.toml` 的 ruff task 中加入根目录 .py 文件

**推荐理由**：

| 维度 | 评估 |
|------|------|
| **消除冗余** | `interactive.py` 是 `main.py` 的功能子集，合并后维护一套逻辑 |
| **迁移成本** | 仅需更新约 4 处文档引用，成本极低 |
| **用户体验** | 统一入口，消除"该用哪个脚本"的困惑；`--interactive` 参数语义清晰 |
| **向后兼容** | `main.py` 的所有现有用法完全不变 |
| **渐进式** | 合并是第一步，后续可按需进行内部重构 |
| **风险可控** | 不涉及目录结构变更，不影响导入路径 |

**不推荐方案 A 的理由**：对于学习型 RAG 项目，将入口脚本移入 `src/cli/` 属于过度工程化，且文档更新量（65+ 处）远超收益。

**不推荐纯方案 B 的理由**：虽然零成本，但两个入口脚本的功能重叠问题将持续存在，随着项目演进会越来越令人困惑。

---

## 附录：交互式 Q&A 功能逐行对比

### main.py `_interactive_qa()` (L559-596)

```python
def _interactive_qa(pipeline: RAGPipeline, meal_name: str) -> None:
    print(f"\nInteractive Q&A mode (meal: {meal_name})")
    print("Type your question, or 'quit'/'exit'/'q' to exit.\n")
    while True:
        try:
            question = input("Q> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting.")
            break
        if not question:
            continue
        if question.lower() in ("quit", "exit", "q"):
            # token tracker 汇总
            break
        try:
            result = pipeline.query(question)
            print(f"\nA: {result['answer']}")
            # token usage 显示
            # 全部 sources + scores 显示
        except Exception as e:
            logger.error(f"Query failed: {str(e)}")
```

### interactive.py `interactive_chat()` (L9-56)

```python
def interactive_chat(pipeline: RAGPipeline) -> None:
    # 启动时显示 collection info（chunk 数量）
    print(f"\n🤖 RAG 问答系统已启动（输入 'quit' 或 'exit' 退出）")
    print(f"📝 数据库中已有 {chunks_count} 个文档片段\n")
    while True:
        try:
            query = input("💬 You: ").strip()
        except KeyboardInterrupt:
            print("\n\n👋 再见！\n")
            break
        if not query:
            continue
        if query.lower() in ["quit", "exit", "q"]:
            # token tracker 汇总
            print("👋 再见！\n")
            break
        result = pipeline.query(query)
        print(f"\n🤖 Assistant: {result['answer']}\n")
        # token usage 显示
        # 前 3 个 sources + scores，路径格式化
        except Exception as e:
            logger.error(f"Error processing query: {str(e)}")
            print(f"\n❌ 处理问题时出错: {str(e)}\n")
```

**重叠率**：约 80% 的逻辑相同，差异主要在 UI 呈现层面。
