# 安全 Issue 处理计划

## 背景

当前有两个 worktree 在并行工作：
- **Worktree A**：golden_qa 重做（FEAT-031），涉及 `src/test_set_manager.py`、`src/test_generator.py`、`tests/fixtures/golden_qa.json`、`tests/test_regression.py`、`exp_configs/golden_tests/`
- **Worktree B**：基线链路测试与优化，涉及 `eval/run_experiment.py`、`src/pipeline.py`、`src/experiment.py`、`config.yaml`、`src/meal.py`、`src/chunker.py`、`src/retriever.py`、`src/generator.py`、`src/embedder.py`、`src/indexer.py`、`eval/metrics/*`、`eval/evaluators/*`、`eval/experiment_reporter.py`、`exp_configs/baseline/`

## 冲突分析

| Issue | 涉及文件 | 是否冲突 | 原因 |
|-------|---------|---------|------|
| RF-001 (print→logger) | main.py, interactive.py, **eval/run_experiment.py**, **src/pipeline.py**, eval/run_eval.py, eval/metrics/generation.py, eval/visualize.py | ⚠️ 部分冲突 | eval/run_experiment.py 和 src/pipeline.py 在 Worktree B 范围内 |
| RF-002 (根目录.py) | main.py, interactive.py, pyproject.toml/pixi.toml | ✅ 安全 | 不与任何 worktree 重叠 |
| RF-008 (backlog详情) | docs/backlog.md, TODO.md | ✅ 安全 | 纯文档 |
| FEAT-017 (CI/CD) | .github/workflows/ (新建) | ✅ 安全 | 全新文件 |
| FEAT-034 (开源准备) | CONTRIBUTING.md (新建), README.md, .github/ (新建) | ✅ 安全 | 纯文档+新文件 |
| RF-013 (chunk_id) | chunker.py, pipeline.py, indexer.py, retriever.py 等 22 个文件 | ❌ 严重冲突 | 核心链路文件全在 Worktree B 范围 |
| RF-014 (normalize_source) | eval/metrics/utils.py, retrieval.py, dedup.py, builtin_evaluator.py | ❌ 冲突 | 评测指标文件在 Worktree B 范围 |
| OPT-002 (集成测试优化) | test_regression.py, test_e2e_experiment.py | ❌ 冲突 | test_regression.py 在 Worktree A 范围 |
| FEAT-022 (RAGAS token追踪) | ragas_evaluator.py, token_tracker.py, **run_experiment.py** | ❌ 冲突 | run_experiment.py 在 Worktree B 范围 |
| FEAT-036 (PDF表格解析) | src/parsers/* | ✅ 安全 | 解析器模块独立，不在任何 worktree 范围 |

## 选定的安全 Issue（按优先级排序）

### 1. FEAT-034：开源准备度完善
- **规模**：中
- **冲突风险**：零
- **工作内容**：
  - 新建 CONTRIBUTING.md（开发流程、提交规范、PR 模板）
  - 新建 .github/ISSUE_TEMPLATE/（Bug Report + Feature Request）
  - 新建 .github/PULL_REQUEST_TEMPLATE.md
  - 更新 README.md（补充安装指引、项目架构、贡献指南链接）
  - 可选：新建 SECURITY.md

### 2. FEAT-017：CI/CD 集成
- **规模**：中
- **冲突风险**：零
- **工作内容**：
  - 新建 .github/workflows/ci.yml（lint + unit test）
  - 配置 pixi 环境安装步骤
  - 配置 pytest markers（排除 integration 测试）
  - 可选：dependabot.yml

### 3. RF-001（部分）：CLI 输出标准化
- **规模**：中（仅处理安全文件）
- **冲突风险**：低（避开 Worktree B 的文件）
- **工作内容**：
  - 仅替换以下文件中的 print → loguru：
    - main.py（80 处）
    - interactive.py（13 处）
    - eval/visualize.py（1 处）
    - eval/metrics/generation.py（2 处）
    - eval/run_eval.py（19 处，已 deprecated 的旧入口）
  - **暂不处理** eval/run_experiment.py（76 处）和 src/pipeline.py（4 处），留给 Worktree B

### 4. RF-002：项目结构整理
- **规模**：小
- **冲突风险**：低
- **工作内容**：
  - 将 main.py 移入 src/cli/main.py，根目录保留 thin wrapper
  - 将 interactive.py 移入 src/cli/interactive.py，根目录保留 thin wrapper
  - 更新 pyproject.toml / pixi.toml 入口点配置
  - 更新所有 import 引用

### 5. RF-008：backlog issue 详情记录
- **规模**：中
- **冲突风险**：零
- **工作内容**：
  - 在 docs/backlog.md 中为每个 issue 增加详情字段（复现步骤、影响范围、修复方案等）
  - 或使用超链接引用独立详情文档
  - 更新归档 skill 以支持详情记录

## 执行顺序

1. **FEAT-034** → 纯文档，零风险，先做热身
2. **FEAT-017** → 新建 CI 配置，零风险
3. **RF-001（部分）** → 替换安全文件中的 print，低风险
4. **RF-002** → 项目结构调整，需注意入口点配置
5. **RF-008** → 文档格式优化，零风险

## 暂不处理的 Issue（留给其他 worktree 或后续）

- RF-013（chunk_id）：全链路影响，等基线稳定后再统一处理
- RF-014（normalize_source）：评测核心，等基线评测确认后再改
- OPT-002（集成测试优化）：与 golden_qa worktree 冲突
- FEAT-022（RAGAS token 追踪）：与基线 worktree 冲突
- 所有涉及 eval/metrics/*、eval/evaluators/*、src/pipeline.py 的 issue
