# CLI 命令速查手册

<!-- status: active -->

> 最后更新: 2026-05-01

本文档列出所有 CLI 命令及其参数。

---

## 主入口 (`main.py`)

### 问答命令

```bash
# 单次查询
pixi run python main.py --query "问题"

# 使用指定 Meal
pixi run python main.py --meal <meal_name> --query "问题"

# 使用不同 LLM preset
pixi run python main.py --query "问题" --llm-preset <preset>
```

| 参数 | 说明 |
|------|------|
| `--query` | 查询问题 |
| `--meal` | 使用指定的 Meal |
| `--llm-preset` | LLM preset 名称（default, opus, sonnet, haiku） |

### 索引构建命令

```bash
# 构建索引
pixi run python main.py --build-index

# 重建索引
pixi run python main.py --rebuild

# 强制重新解析 PDF
pixi run python main.py --build-index --force-parse
```

| 参数 | 说明 |
|------|------|
| `--build-index` | 构建向量索引 |
| `--rebuild` | 重建索引（清空现有索引） |
| `--force-parse` | 强制重新解析 PDF |

### 采样参数

```bash
# 按文档数采样
pixi run python main.py --build-index --sample-count 10

# 按总页数采样
pixi run python main.py --build-index --sample-pages 5000

# 按比例采样
pixi run python main.py --build-index --sample-ratio 0.1

# 设置随机种子
pixi run python main.py --build-index --sample-count 10 --seed 42
```

| 参数 | 说明 |
|------|------|
| `--sample-count` | 采样 N 个 PDF |
| `--sample-pages` | 采样直到总页数达到 N |
| `--sample-ratio` | 采样比例（0.0-1.0） |
| `--seed` | 随机种子 |

### Meal 管理命令

```bash
# 创建 Meal
pixi run python main.py --create-meal --sample-count 10
pixi run python main.py --create-meal my_meal --sample-ratio 0.1

# 列出所有 Meal
pixi run python main.py --list-meals

# 查看 Meal 详情
pixi run python main.py --meal-info <meal_name>

# 删除 Meal
pixi run python main.py --delete-meal <meal_name>

# 重命名 Meal
pixi run python main.py --rename-meal <old_name> <new_name>

# 复制 Meal
pixi run python main.py --copy-meal <source> <target>

# 修复 Meal
pixi run python main.py --repair-meal <meal_name>
```

| 参数 | 说明 |
|------|------|
| `--create-meal` | 创建 Meal（可选指定名称） |
| `--list-meals` | 列出所有 Meal |
| `--meal-info` | 查看 Meal 详情 |
| `--delete-meal` | 删除 Meal |
| `--rename-meal` | 重命名 Meal |
| `--copy-meal` | 复制 Meal |
| `--repair-meal` | 修复 Meal |

### 测试集生成命令

```bash
# 生成测试集
pixi run python main.py --generate-test-set <meal_name>

# 指定策略和数量
pixi run python main.py --generate-test-set <meal_name> --strategy factual --num-questions 20
```

| 参数 | 说明 |
|------|------|
| `--generate-test-set` | 为指定 Meal 生成测试集 |
| `--strategy` | 问题策略（factual, boundary, multi_hop） |
| `--num-questions` | 问题数量 |

---

## 交互式问答

```bash
pixi run interactive
# 或
pixi run python main.py --interactive

# 指定 Meal 进入交互模式
pixi run python main.py --meal <meal_name>
```

启动交互式命令行，连续提问。输入 `quit`、`exit` 或 `q` 退出。

| 参数 | 说明 |
|------|------|
| `--interactive` | 启动交互式问答模式 |
| `--meal` | 指定 Meal 进入交互模式（无 `--query` 时自动进入） |

---

## 评测命令

### 基础评测

> ⚠️ `eval/run_eval.py` 已废弃，请使用 `eval/run_experiment.py`。

```bash
# 运行完整评测（推荐使用实验系统）
pixi run python eval/run_experiment.py --config exp_configs/your_config.yaml

# 旧方式（已废弃）
# pixi run python eval/run_eval.py
# pixi run python eval/run_eval.py --sample-count 5
# pixi run python eval/run_eval.py --build-index
```

### 实验系统

```bash
# 运行实验（便捷写法）
pixi run exp baseline
pixi run exp baseline.yaml

# 运行实验（完整写法）
pixi run python eval/run_experiment.py --config exp_configs/baseline.yaml

# 列出所有实验
pixi run python eval/run_experiment.py --list

# 查看实验详情
pixi run python eval/run_experiment.py --info <exp_name>

# 对比多个实验
pixi run python eval/run_experiment.py --compare <exp1> <exp2>

# 复现实验
pixi run python eval/run_experiment.py --reproduce <exp_dir>

# 生成 LLM 报告
pixi run python eval/run_experiment.py --config <config> --llm-report

# 增量实验：resume 已有实验目录
pixi run python eval/run_experiment.py --config <config> --resume <exp_dir>

# 增量实验：选择性重跑指定 variant
pixi run python eval/run_experiment.py --config <config> --resume <exp_dir> --force-variant variant_a

# 强制重跑所有 variant
pixi run python eval/run_experiment.py --config <config> --resume <exp_dir> --force-rerun
```

#### 实验系统参数

| 参数 | 说明 |
|------|------|
| `--config <path>` | 实验配置 YAML 文件路径 |
| `--list` | 列出所有实验 |
| `--info <exp_id>` | 查看实验详情 |
| `--compare <ids...>` | 对比多个实验 |
| `--reproduce <dir>` | 复现实验 |
| `--resume <dir>` | 复用已有实验目录，跳过已完成的 variant（自动验证 Config Hash） |
| `--force-rerun` | 强制重跑所有 variant，忽略 checkpoint |
| `--force-variant <names...>` | 选择性重跑指定 variant，不影响其他已完成的 variant |
| `--llm-report` | 使用 LLM 生成深度分析报告 |
| `--skip-preprocessing` | 跳过 Meal 和测试集创建 |
| `--skip-verification` | 复现实验时跳过资产验证 |
| `--skip-hash-verification` | 跳过 PDF SHA256 验证 |
| `--system-config <path>` | 系统配置文件路径（默认 config.yaml） |
| `--output-format <fmt>` | 对比输出格式：table / json |
| `--save-report` | 保存对比报告为 Markdown |
| `--report-path <path>` | 指定对比报告保存路径 |

> 增量实验工作流的详细说明请参阅 [实验评测系统使用指南](experiment-system.md#增量实验工作流)。

---

## 测试命令

```bash
# 纯单元测试（秒级反馈，开发中频繁使用）
pixi run test-unit

# 标准测试（排除 integration 和 slow，~35s）
pixi run test

# 全量测试（包括 integration 和 slow，~60s）
pixi run test-all

# 运行特定模块测试
pixi run pytest tests/test_parser.py -v
```

---

## 通用参数

| 参数 | 说明 |
|------|------|
| `--config` | 配置文件路径（默认：config.yaml） |
