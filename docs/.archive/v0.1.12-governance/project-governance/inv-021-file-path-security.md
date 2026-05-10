# INV-021: 文件路径安全审计报告

> 审计日期：2026-04-23
> 审计范围：`src/` 和 `eval/` 目录下所有 Python 文件
> 审计目标：识别路径遍历（Path Traversal）攻击面，评估已有保护措施，发现缺失的安全检查

---

## 一、审计方法

通过代码搜索与分析，检查以下路径构造模式：

1. **`Path()` 构造**：所有使用 `pathlib.Path()` 的位置
2. **`open()` 调用**：所有文件读写操作
3. **`.resolve()` 调用**：路径规范化（可消除 `..` 等遍历符号）
4. **`.is_absolute()` 调用**：绝对路径检查
5. **`.relative_to()` 调用**：路径包含关系检查（防遍历核心手段）
6. **配置驱动路径**：从 `config.yaml` 读取的目录/路径字段
7. **CLI 参数路径**：从命令行参数获取的路径

---

## 二、路径构造入口清单

### 2.1 配置驱动路径（config.yaml 中的 dir/path 字段）

以下路径均从 `config.yaml` 读取，由 `_resolve_data_paths()` 根据 `data_dir` 重写前缀后传入代码：

| 配置键 | 默认值 | 使用位置 |
|--------|--------|----------|
| `parser.input_dir` | `data/raw` | `pipeline.py:177,185`, `parser.py:217`, `meal.py:538,557` |
| `parser.output_dir` | `data/parsed` | `pipeline.py:186,198,219`, `parser.py:218`, `test_generator.py:399` |
| `chunker.input_dir` | `data/parsed` | `pipeline.py:224,233,244`, `chunker.py:465` |
| `chunker.output_dir` | `data/chunks` | `pipeline.py:225,257,265`, `chunker.py:466`, `test_generator.py:430`, `bm25_retriever.py:309`, `hybrid_retriever.py:280` |
| `vector_store.persist_dir` | `data/vector_store` | `pipeline.py:56,325`, `retriever.py:114`, `indexer.py:299` |
| `meals.dir` | `data/meals` | `meal.py:536` |
| `artifacts.dir` | `data/artifacts` | `meal.py:544`, `pipeline.py:335`, `test_generator.py:392,423`, `run_experiment.py:682,1330` |
| `experiments.dir` | `data/exp_reports` | `experiment.py:582`, `run_experiment.py:1801` |
| `experiments.configs_dir` | `exp_configs` | `experiment.py:583` |
| `logging.log_dir` | `logs` | `utils.py:78` |
| `data_dir` | `data` | `utils.py:36`（路径重写基准） |

**风险分析**：配置文件由系统管理员控制，非外部输入源。若攻击者能修改 `config.yaml`，则已拥有更高权限，路径遍历不再是主要威胁。但 `data_dir` 重写机制（`_resolve_data_paths`）仅做字符串前缀替换，不验证目标路径的合法性。

### 2.2 用户输入路径（CLI 参数）

| 参数 | 类型 | 传递路径 | 风险描述 |
|------|------|----------|----------|
| `--config` | `str` | `load_config(args.config)` → `open(config_path)` | 直接打开用户指定文件，可读取任意文件 |
| `--add-pdfs` | `nargs="+"` | `meal_manager.extend_meal(source_meal, args.add_pdfs)` → `meal.py:1528 Path(pdf_input)` | 用户提供的 PDF 路径列表，**已有部分保护**（见 2.3） |
| `--meal` | `str` | 用作 meal 名称查找目录 | 仅用于目录名查找，有 `validate_meal_name` 校验 |
| `--create-meal` | `str` | 用作 meal 名称 | 同上，有名称校验 |
| `--delete-meal` | `str` | 用作 meal 名称 | 同上 |
| `--rename-meal` | `2×str` | 用作 meal 名称 | 同上 |
| `--repair-meal` | `str` | 用作 meal 名称 | 同上 |
| `--generate-test-set` | `str` | 用作 meal 名称 | 同上 |
| `--llm-preset` | `str` | 用作 LLM 配置查找键 | 不涉及文件路径 |
| `--query` | `str` | 传递给 LLM | 不涉及文件路径 |

**eval/ 目录 CLI 参数**：

| 文件 | 参数 | 风险描述 |
|------|------|----------|
| `recommend_testset.py` | `--output` | 直接 `Path(args.output).write_text()`，可写入任意路径 |
| `run_eval.py` | `test_data_path`, `output_dir` | 函数参数，由调用方控制 |

### 2.3 硬编码默认路径

| 路径 | 文件 | 行号 | 说明 |
|------|------|------|------|
| `"data/meals"` | `meal.py` | 536 | meals_dir 默认值 |
| `"data/raw"` | `meal.py` | 538,557 | raw_dir 默认值 |
| `"data/chunks"` | `meal.py` | 540 | chunks_dir 默认值 |
| `"data/artifacts"` | `meal.py` | 544 | artifacts_dir 默认值 |
| `"data/parsed"` | `test_generator.py` | 399 | parsed_dir 回退值 |
| `"data/chunks"` | `test_generator.py` | 430 | chunks_dir 回退值 |
| `"data/exp_reports"` | `experiment.py` | 582 | exp_dir 默认值 |
| `"exp_configs"` | `experiment.py` | 583 | configs_dir 默认值 |
| `"data/artifacts"` | `pipeline.py` | 335 | artifacts_dir 默认值 |
| `"logs"` | `utils.py` | 78 | log_dir 默认值 |
| `"data/raw"` | `run_experiment.py` | 189 | raw_dir 默认值 |
| `"data/meals"` | `recommend_testset.py` | 307 | meals_dir 硬编码 |
| `"data/parsed"` | `recommend_testset.py` | 320 | parsed_dir 硬编码 |
| `"data/exp_reports"` | `recommend_testset.py` | 339 | 输出目录硬编码 |

**风险分析**：硬编码路径均为项目内相对路径，不涉及外部输入，风险极低。

---

## 三、已有保护措施

### 3.1 meal.py 的 `relative_to()` 路径遍历防护（第 1528-1542 行）

这是项目中**唯一**显式的路径遍历防护机制，位于 `extend_meal` 方法中：

```python
# meal.py:1524-1542
for pdf_input in new_pdfs:
    if isinstance(pdf_input, Path):
        pdf_path = pdf_input
    else:
        pdf_path = Path(pdf_input)

    if not pdf_path.is_absolute():
        pdf_path = self.raw_dir / pdf_path

    if not pdf_path.exists():
        raise ValueError(f"PDF file does not exist: {pdf_input}")

    try:
        rel_path_obj = pdf_path.relative_to(self.raw_dir)
        rel_path = rel_path_obj.as_posix()
    except ValueError as e:
        raise ValueError(
            f"PDF file '{pdf_input}' is not within the raw directory"
        ) from e
```

**防护逻辑**：
1. 将相对路径转换为基于 `raw_dir` 的绝对路径
2. 使用 `relative_to()` 验证 PDF 文件必须在 `raw_dir` 目录内
3. 若 `relative_to()` 抛出 `ValueError`（路径不在目标目录内），则拒绝操作

**局限性**：
- **仅检查 `raw_dir` 包含关系**，不验证解析输出目录、切块目录等其他敏感目录
- **不处理符号链接**：若 `raw_dir` 内存在指向外部目录的符号链接，`relative_to()` 不会检测到
- **不调用 `.resolve()`**：路径中的 `..` 组件在 `is_absolute()` 为 True 时不会被规范化。例如 `raw_dir / "../../etc/passwd"` 经 `is_absolute()` 判断为 False 后拼接为 `raw_dir / ../../etc/passwd`，此时 `relative_to(raw_dir)` 会抛出 ValueError，所以此场景实际被防护住了
- **仅保护 `extend_meal` 入口**，其他路径构造点无类似检查

### 3.2 `validate_meal_name()` 名称校验

`main.py` 中 `--rename-meal` 和 `--copy-meal` 使用 `validate_meal_name()` 校验 meal 名称，限制为字母数字、下划线和连字符，防止路径注入。

### 3.3 `FileNotFoundError` 检查

`parser.py:100`、`chunker.py:151`、`semantic_chunker.py:374`、`bm25_retriever.py:87`、`indexer.py:193` 等处检查输入目录是否存在，但这是功能性检查而非安全检查——不阻止遍历到已存在的敏感目录。

---

## 四、缺失保护清单

### 4.1 高风险

| # | 文件 | 行号 | 风险描述 | 推荐修复方案 |
|---|------|------|----------|-------------|
| H1 | `main.py` | 41,115 | `--config` 参数直接传入 `load_config()`，可读取系统上任意 YAML 文件。攻击者可构造 `--config /etc/shadow` 或 `--config ../../secret.yaml` 来读取敏感文件。 | 在 `load_config()` 中添加路径白名单检查，限制配置文件必须在项目根目录或 `exp_configs/` 目录下；或至少验证文件扩展名为 `.yaml`/`.yml` |
| H2 | `eval/recommend_testset.py` | 336 | `--output` 参数直接 `Path(args.output).write_text()`，可写入系统任意位置。攻击者可覆盖关键文件。 | 限制输出路径必须在项目目录内，添加 `relative_to(project_root)` 检查 |
| H3 | `main.py` | 84-85,183 | `--add-pdfs` 参数传入 `extend_meal()`，虽有 `relative_to(raw_dir)` 检查，但攻击者可提供绝对路径指向 `raw_dir` 之外的文件（如 `/etc/passwd`），此时 `is_absolute()` 为 True 不会拼接 `raw_dir`，但 `relative_to(raw_dir)` 会抛出 ValueError 被捕获——**此路径实际已被防护**。然而，若 `raw_dir` 本身被配置为 `/`，则所有绝对路径都会通过检查。 | 在 `extend_meal()` 中增加对 `raw_dir` 配置值的合理性校验，禁止 `raw_dir` 为根目录或系统敏感目录 |

### 4.2 中风险

| # | 文件 | 行号 | 风险描述 | 推荐修复方案 |
|---|------|------|----------|-------------|
| M1 | `src/utils.py` | 33 | `load_config()` 中 `open(config_path)` 直接打开用户指定路径，无路径合法性验证。与 H1 同源。 | 同 H1 修复方案 |
| M2 | `src/experiment.py` | 363,369 | `load_experiment_config()` 接受任意 `config_path` 参数并直接 `open()`。若该参数来自用户输入，可读取任意文件。 | 添加路径范围检查，限制在 `exp_configs/` 目录内 |
| M3 | `src/meal.py` | 536-545 | `MealManager.__init__()` 从配置读取 `meals_dir`、`raw_dir`、`chunks_dir`、`artifacts_dir` 等路径，直接 `Path()` 构造，无合法性验证。若配置被篡改，可指向系统任意目录。 | 添加路径合理性校验函数，验证配置路径在项目目录树内 |
| M4 | `src/pipeline.py` | 177-178 | `Path(parser_config["input_dir"]).rglob("*.pdf")` 可遍历配置指定的任意目录。若配置被篡改为 `/`，将遍历整个文件系统。 | 添加目录深度和范围限制 |
| M5 | `eval/run_experiment.py` | 1799 | `Path(report_path)` 直接使用用户提供的报告路径写入文件。 | 添加路径范围检查 |
| M6 | `eval/run_experiment.py` | 2165 | `Path(exp_dir)` 直接使用外部传入的实验目录路径。 | 添加路径范围检查 |
| M7 | `eval/run_eval.py` | 87-88 | `Path(test_data_path)` 和 `Path(output_dir)` 直接使用函数参数构造路径，无验证。 | 添加路径范围检查 |

### 4.3 低风险

| # | 文件 | 行号 | 风险描述 | 推荐修复方案 |
|---|------|------|----------|-------------|
| L1 | `src/utils.py` | 57-62 | `_resolve_data_paths()` 仅做字符串前缀替换 `data/` → `data_dir/`，不验证 `data_dir` 的合法性。若 `data_dir` 被设为 `../../etc`，所有 `data/` 前缀路径将被重定向。 | 验证 `data_dir` 为合法的项目内路径或绝对路径 |
| L2 | `src/meal.py` | 1745 | `_parse_pdfs_for_meal()` 中 `pdf_file.relative_to(self.raw_dir)` 用于构造输出路径，但未在之前验证 `pdf_file` 确实在 `raw_dir` 内（依赖调用方保证）。 | 添加防御性 `relative_to()` 检查 |
| L3 | `src/parser.py` | 124 | `pdf_file.relative_to(input_path)` 假设 PDF 文件在输入目录内，但未显式验证。 | 添加 try/except ValueError 保护 |
| L4 | `src/chunker.py` | 167,184 | `md_file.relative_to(input_path)` 同上，未显式验证。 | 添加 try/except ValueError 保护 |
| L5 | `src/semantic_chunker.py` | 390,415 | 同 L4，语义分块器中的 `relative_to()` 未显式验证。 | 添加 try/except ValueError 保护 |
| L6 | `src/bm25_retriever.py` | 101 | 同 L4，BM25 检索器中的 `relative_to()` 未显式验证。 | 添加 try/except ValueError 保护 |
| L7 | `src/indexer.py` | 209 | 同 L4，索引器中的 `relative_to()` 未显式验证。 | 添加 try/except ValueError 保护 |
| L8 | `src/pipeline.py` | 200,221,259 | 同 L4，管线中的 `relative_to()` 未显式验证。 | 添加 try/except ValueError 保护 |
| L9 | `src/test_generator.py` | 464,1163 | 同 L4，测试生成器中的 `relative_to()` 未显式验证。 | 添加 try/except ValueError 保护 |
| L10 | `eval/recommend_testset.py` | 307,320 | 硬编码 `Path("data/meals")` 和 `Path("data/parsed")`，不读取配置，与配置系统不一致。 | 统一使用 `load_config()` 获取路径 |
| L11 | `src/meal.py` | 112 | `compute_file_sha256()` 中 `open(file_path, "rb")` 直接打开传入路径，无范围检查。但该函数仅用于内部已验证的路径。 | 维持现状，记录为已知限制 |

---

## 五、`.resolve()` 使用情况

项目中 `.resolve()` 仅在 3 处使用，均用于确定项目根目录，不涉及用户输入路径：

| 文件 | 行号 | 用途 |
|------|------|------|
| `eval/run_experiment.py` | 15 | `Path(__file__).resolve().parent.parent` → 确定项目根目录 |
| `eval/run_eval.py` | 41 | 同上 |
| `eval/recommend_testset.py` | 18 | 同上 |

**关键发现**：`src/` 目录下的代码**完全不使用 `.resolve()`**。这意味着路径中的符号链接和 `..` 组件不会被规范化，可能导致 `relative_to()` 检查被绕过（通过符号链接）。

---

## 六、总体安全评估和建议

### 6.1 风险等级总结

| 等级 | 数量 | 主要关注点 |
|------|------|-----------|
| 高 | 3 | CLI 参数直接操作文件系统（`--config` 读取、`--output` 写入、`raw_dir` 配置篡改） |
| 中 | 7 | 配置驱动的路径无合法性验证、eval 脚本中用户可控路径 |
| 低 | 11 | `relative_to()` 缺少防御性检查、硬编码路径不一致 |

### 6.2 攻击面分析

本系统的威胁模型需要考虑以下场景：

1. **本地命令行用户**：主要威胁源。能通过 CLI 参数注入路径。
2. **配置文件篡改**：若攻击者能修改 `config.yaml`，可重定向所有数据目录。
3. **符号链接攻击**：若 `data/raw/` 内存在指向敏感目录的符号链接，现有检查无法防御。

### 6.3 核心建议

#### 建议 1：创建路径安全工具函数（优先级：高）

在 `src/utils.py` 中新增路径安全验证函数：

```python
def validate_path_in_project(path: Path, base_dir: Path) -> Path:
    """验证路径在项目指定目录内，防止路径遍历攻击。"""
    resolved = path.resolve()
    resolved_base = base_dir.resolve()
    resolved.relative_to(resolved_base)
    return resolved
```

关键点：**必须使用 `.resolve()` 规范化路径后再做 `relative_to()` 检查**，以防止符号链接绕过。

#### 建议 2：保护 CLI 文件操作入口（优先级：高）

- `--config`：限制配置文件路径必须在项目根目录或 `exp_configs/` 下
- `--output`（eval 脚本）：限制输出路径在项目目录内
- `--add-pdfs`：现有保护基本有效，但应增加 `.resolve()` 规范化

#### 建议 3：配置路径合理性校验（优先级：中）

在 `MealManager.__init__()` 和 `ExperimentManager.__init__()` 中，对从配置读取的目录路径进行合理性校验：
- 禁止路径指向系统敏感目录（`/etc`、`/usr`、`C:\Windows` 等）
- 禁止 `data_dir` 为根目录
- 验证路径深度不超过合理范围

#### 建议 4：防御性 `relative_to()` 检查（优先级：低）

在所有使用 `relative_to()` 的位置添加 `try/except ValueError` 保护，确保路径不在预期目录内时优雅失败而非崩溃。涉及文件：`parser.py`、`chunker.py`、`semantic_chunker.py`、`bm25_retriever.py`、`indexer.py`、`pipeline.py`、`test_generator.py`。

#### 建议 5：统一 eval 脚本的路径获取方式（优先级：低）

`eval/recommend_testset.py` 中硬编码的 `Path("data/meals")` 和 `Path("data/parsed")` 应改为从配置读取，与 `src/` 模块保持一致。

### 6.4 现有保护有效性评估

| 保护措施 | 有效性 | 说明 |
|----------|--------|------|
| `meal.py` 的 `relative_to()` 检查 | ⚠️ 部分有效 | 防止了 `extend_meal` 的直接路径遍历，但不防符号链接，且仅覆盖单一入口 |
| `validate_meal_name()` | ✅ 有效 | 限制 meal 名称为安全字符，防止目录注入 |
| `FileNotFoundError` 检查 | ❌ 非安全措施 | 仅检查目录存在性，不限制路径范围 |
| 配置文件权限控制 | ⚠️ 依赖运维 | 代码层面无验证，依赖文件系统权限 |

### 6.5 结论

项目当前在路径安全方面存在**明显的防护缺口**。唯一的显式路径遍历防护（`meal.py:1530-1542`）仅覆盖 `extend_meal` 一个入口点，且未使用 `.resolve()` 规范化路径。`--config` 和 eval 脚本中的 `--output` 参数是最高风险的攻击面，允许读取和写入系统任意文件。建议按优先级逐步实施上述修复方案。
