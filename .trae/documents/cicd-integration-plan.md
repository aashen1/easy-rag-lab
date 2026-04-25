# CI/CD 接入计划书

> 状态：未完成

> 给 AI 的说明：这份计划书还挺详细，但是看了之后感觉项目眼下还是太凌乱，接入 CI/CD 的时机可能还不成熟。不过探索一下功能类似于CI的本地自动化测试，比如钩子之类的，可能现阶段收益比会更明显。

> 处理建议：先把这份文档归档并记录issue作为低优先级，等后面再考虑怎么做接入。

## 项目现状审查摘要

### 已有的基础设施（好消息）
- ✅ pytest 测试框架已就位（33 个测试文件）
- ✅ ruff lint + format 已配置
- ✅ pre-commit 钩子已配置
- ✅ pixi 包管理器统一管理依赖
- ✅ 测试中大量使用 mock（`mock_embedder`, `mock_qdrant_client`, `mock_anthropic_client`）
- ✅ pytest markers 已定义（`unit`, `integration`, `slow`）

### 阻塞性问题（必须先解决才能接入 CI）
- ❌ `pixi.toml` 仅支持 `win-64` 平台，CI runner 是 Linux
- ❌ `pixi.toml` 硬编码 `cuda = "12.6"` 系统需求，CI 无 GPU
- ❌ `pixi.toml` 硬编码 `torch==2.6.0+cu126`，CI 需要 CPU 版
- ❌ `pixi.toml` 的 `find-links` 指向本地 `B:/useradmin/torch_cache`，CI 不存在此路径
- ❌ `pytest.ini` 与 `pyproject.toml` 的 pytest 配置冲突（两处同时定义 markers）
- ❌ `config.yaml` 中 `device: "cuda"` 硬编码，CI 无法运行

### 高风险问题（测试可能在 CI 中失败）
- ⚠️ `eval/evaluators/__init__.py` 导入 `RagasEvaluator`，可能触发 ragas 包的 GPU 检查
- ⚠️ `test_e2e_experiment.py` 是端到端测试但缺少 `integration` 标记
- ⚠️ `unit` 标记未在 `pyproject.toml` 中注册，pytest 产生 unknown marker 警告
- ⚠️ 部分测试缺少标记，CI 中无法精确筛选

### 中风险问题
- ⚡ `src/llm_client.py` 无独立测试
- ⚡ `eval/recommend_testset.py` 和 `eval/visualize.py` 无测试
- ⚡ 多处代码硬编码默认路径 `"data/raw"` 等
- ⚡ `pixi.toml` 缺少 `test` 和 `ci` task 定义
- ⚡ `.pre-commit-config.yaml` 的 ruff 版本与 `pixi.toml` 不一致

---

## 分步实施计划

### 第一阶段：修复阻塞性问题（让项目能在 Linux CPU 环境中运行）

**目标**：让 `pixi install` 和基础测试能在无 GPU 的 Linux 环境中成功执行。

#### Step 1.1 — pixi.toml 添加 linux-64 平台支持

- 将 `platforms = ["win-64"]` 改为 `platforms = ["win-64", "linux-64"]`
- 运行 `pixi install` 重新生成 lockfile，确保 Linux 依赖可解析

#### Step 1.2 — pixi.toml 创建 CPU-only feature 环境

使用 pixi 的 `[feature]` 机制区分 GPU/CPU 环境：

```toml
[feature.cuda]
system-requirements = { cuda = "12.6" }

[feature.cuda.pypi-dependencies]
torch = "==2.6.0+cu126"
torchvision = "==0.21.0+cu126"

[feature.cpu.pypi-dependencies]
torch = "==2.6.0+cpu"
torchvision = "==0.21.0+cpu"

[environments]
default = ["cuda"]   # 本地开发用 GPU 环境
ci = ["cpu"]         # CI 用 CPU 环境
```

- 将全局的 `torch`/`torchvision` 依赖和 `[system-requirements] cuda` 移入 `[feature.cuda]`
- `find-links` 的本地缓存路径移到用户级 pixi 配置（`~/.pixi/config.toml`），不提交到仓库

#### Step 1.3 — config.yaml 支持 CPU 设备回退

- 将 `embedding.device: "cuda"` 改为支持环境变量覆盖
- 将 `retrieval.reranker.device: "cuda"` 同样处理
- 方案：在代码中读取 `TORCH_DEVICE` 环境变量，默认值为 `"cuda"`，CI 中设为 `"cpu"`

#### Step 1.4 — 合并 pytest 配置，消除冲突

- 删除 `pytest.ini`，将所有 pytest 配置统一到 `pyproject.toml` 的 `[tool.pytest.ini_options]`
- 合并后的配置：

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
markers = [
    "unit: marks unit tests with no external dependencies",
    "integration: marks tests that call external APIs (deselect with '-m \"not integration\"')",
    "slow: marks tests as slow (execution time >5s)",
    "gpu: marks tests that require GPU (deselect with '-m \"not gpu\"')",
]
addopts = "--basetemp=.pytest_tmp --tb=short -v --durations=10 --strict-markers"
tmp_path_retention_count = 0
tmp_path_retention_policy = "failed"
```

- 添加 `--strict-markers` 确保未注册的标记会报错而非警告
- 添加 `--tb=short` 和 `--durations=10` 优化 CI 输出

#### Step 1.5 — 验证 CPU 环境可运行

- 在本地运行 `pixi run -e ci pytest tests/ -m "not integration" --co`（仅收集测试，不执行）
- 确认无导入错误、无 CUDA 相关崩溃

---

### 第二阶段：完善测试标记与质量（让 CI 能精确筛选测试）

**目标**：确保每个测试都有正确的标记，CI 中可以安全地只跑 `unit` 测试。

#### Step 2.1 — 为所有测试添加标记

审查全部 33 个测试文件，为每个测试函数/类添加合适的标记：

- `@pytest.mark.unit`：纯单元测试，使用 mock，不依赖外部服务
- `@pytest.mark.integration`：调用真实 API（LLM、Qdrant）或需要真实数据文件
- `@pytest.mark.slow`：执行时间 >5s
- `@pytest.mark.gpu`：需要 GPU 才能正确运行

标记原则：
- 已使用 mock 的测试 → `unit`
- 调用真实 API 的测试 → `integration`
- 需要下载模型的测试 → `integration` + `slow`
- 端到端测试 → `integration` + `slow`

#### Step 2.2 — 修复未标记的端到端/回归测试

- `test_e2e_experiment.py`：添加 `@pytest.mark.integration` + `@pytest.mark.slow`
- `test_regression.py`：确认所有 integration 测试都有标记保护
- 审查所有测试中是否有隐式的外部依赖（如模块级 `load_dotenv()` 后直接使用 `os.getenv`）

#### Step 2.3 — 添加 pixi test/ci task

在 `pixi.toml` 中添加：

```toml
[tasks.test]
cmd = "pytest tests/ -m 'not integration and not gpu' --tb=short -v --durations=10"

[tasks.test-all]
cmd = "pytest tests/ --tb=short -v --durations=10"

[tasks.test-integration]
cmd = "pytest tests/ -m integration --tb=short -v --durations=10"

[tasks.ci]
depends-on = ["lint", "test"]
```

#### Step 2.4 — 对齐 ruff 版本

- 将 `.pre-commit-config.yaml` 中的 ruff 版本与 `pixi.toml` 中的版本范围对齐
- 或者 CI 中不使用 pre-commit，仅使用 `pixi run lint`（推荐，减少维护负担）

#### Step 2.5 — 运行完整测试验证

- `pixi run -e ci test` 确认所有 unit 测试通过
- `pixi run lint` 确认 lint 通过
- 修复任何发现的问题

---

### 第三阶段：创建 GitHub Actions CI 工作流

**目标**：在 GitHub 上建立自动化 CI pipeline。

#### Step 3.1 — 创建 CI 工作流文件

创建 `.github/workflows/ci.yml`：

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  lint-and-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: prefix-dev/setup-pixi@v0.8.1
        with:
          environments: ci
          cache: true

      - name: Lint
        run: pixi run -e ci lint

      - name: Run unit tests
        run: pixi run -e ci test

      - name: Upload test results
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: test-results
          path: .pytest_tmp/
```

#### Step 3.2 — 配置 HuggingFace 模型缓存

CI 中首次运行需要下载 embedding 模型（即使测试用了 mock，导入时可能触发下载）。添加缓存步骤：

```yaml
      - name: Cache HuggingFace models
        uses: actions/cache@v4
        with:
          path: ~/.cache/huggingface
          key: hf-models-${{ runner.os }}-${{ hashFiles('pixi.lock') }}
          restore-keys: |
            hf-models-${{ runner.os }}-
```

#### Step 3.3 — 配置环境变量

在 CI 工作流中设置：

```yaml
env:
  TORCH_DEVICE: cpu
  RUN_INTEGRATION_TESTS: false
```

#### Step 3.4 — 验证 CI 工作流

- 推送到 GitHub，观察 CI 是否成功运行
- 修复任何 CI 环境特有的问题

---

### 第四阶段：增强 CI 能力（可选，按需实施）

**目标**：在基础 CI 之上添加更多自动化能力。

#### Step 4.1 — 添加 pre-commit CI（可选）

使用 [pre-commit CI](https://pre-commit.ci/) 作为轻量级 lint 检查补充，无需自己维护 runner。

#### Step 4.2 — 添加测试覆盖率报告（可选）

- 安装 `pytest-cov`
- CI 中运行 `pytest --cov=src --cov=eval --cov-report=xml`
- 使用 `codecov` 或 GitHub 的覆盖率注释展示结果

#### Step 4.3 — 添加 integration 测试定时任务（可选）

- 使用 `cron` 触发器，每天/每周自动运行 integration 测试
- 需要配置 GitHub Secrets 存放 `LLM_API_KEY` 等

#### Step 4.4 — 添加自动发布工作流（可选）

- 当打 `v*` tag 时自动触发发布
- 自动生成 changelog
- 自动更新版本号

---

## 实施优先级与依赖关系

```
Step 1.1 ─┐
Step 1.2 ─┤
Step 1.3 ─┼──→ Step 1.5 (验证) ──→ Step 2.1 ──→ Step 2.3 ──→ Step 2.5 (验证)
Step 1.4 ─┘                        Step 2.2 ──→ Step 2.4 ──┘
                                                          │
                                                          ↓
                                                    Step 3.1 ──→ Step 3.2
                                                          │         │
                                                    Step 3.3 ──→ Step 3.4
                                                          │
                                                          ↓
                                                    Step 4.x (可选)
```

**关键路径**：Step 1.1-1.4 → Step 1.5 → Step 2.1-2.4 → Step 2.5 → Step 3.1-3.4

**预计工作量**：
- 第一阶段：4 个文件修改，核心改动
- 第二阶段：33 个测试文件审查 + 标记，工作量最大
- 第三阶段：1 个新文件创建，配置调试
- 第四阶段：按需实施

## 风险与注意事项

1. **pixi feature 机制兼容性**：pixi 的 `[feature]` 是较新的功能，需确认当前 pixi 版本支持
2. **torch CPU 版本可用性**：`torch==2.6.0+cpu` 需确认在 PyPI 上可用且与项目其他依赖兼容
3. **ragas 包的 GPU 假设**：ragas 可能在导入时假设 GPU 可用，需要在 CI 中实际验证
4. **HuggingFace 模型下载**：即使测试用了 mock，某些导入路径可能触发模型下载，CI 中需要缓存或进一步 mock
5. **pixi.lock 提交**：添加 linux-64 平台后 lockfile 会变大，确保提交以保障可复现性
