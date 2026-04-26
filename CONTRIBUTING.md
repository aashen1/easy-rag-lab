# 贡献指南

感谢你对 ASH Easy RAG 项目的关注！本文档介绍如何参与项目开发。

---

## 开发环境搭建

### 前置条件

- Python 3.12+
- [pixi](https://pixi.prefix.dev/latest/installation/) 包管理器
- Git

### 安装步骤

```bash
git clone <repo-url>
cd ash-easy-rag
pixi install
```

复制 `.env.example` 为 `.env` 并填写必要的 API Key。

---

## 代码规范

### 日志

使用 `loguru`，禁止使用 `print`（CLI 工具的面向用户输出除外）。

```python
from loguru import logger

logger.info("Processing started")
logger.error(f"Failed to load: {path}")
```

### 类型标注

所有公共函数必须标注参数类型与返回值类型。

```python
def process_text(text: str, max_length: int = 512) -> dict[str, Any]:
    ...
```

### Docstring

所有公共函数须包含功能描述、参数说明（Args）、返回值说明（Returns）、异常说明（Raises）。

### 异常处理

所有 IO 操作（PDF 读取、网络请求、文件写入）必须有 `try/except`，捕获异常后记录日志并优雅降级。

### 代码格式化

使用 `ruff` 自动格式化和检查：

```bash
pixi run lint          # 自动修复 + 格式化
pixi run ruff-check    # 仅检查不修改
```

### 配置管理

所有超参数、模型名、路径等均写入 `config.yaml`，禁止在代码中硬编码。

---

## 提交规范

遵循 [Conventional Commits](https://www.conventionalcommits.org/) 格式，使用英文 ASCII 字符：

```
<type>: <description>

# 示例
feat: add hybrid retrieval support
fix: correct FPR metric calculation
docs: update hyperparameter guide
test: add boundary condition tests for generator
refactor: extract CLI handlers to separate module
chore: update ruff configuration
```

### 提交原则

- 每个逻辑工作单元完成后立即提交
- 只 stage 自己修改的文件，禁止 `git add -A` 或 `git add .`
- 提交前运行 `pixi run lint` 确保代码质量

---

## 测试

```bash
pixi run test          # 快速测试（不含集成测试）
pixi run test-all      # 全量测试（含 API 调用）
```

使用 Red/Green TDD 进行开发，每步开发必须附带 pytest 测试。

测试文件与源文件保持对应关系（如 `src/parser.py` → `tests/test_parser.py`）。

---

## 分支与合并

- `main`：稳定发布分支
- `dev`：开发主线，所有功能分支最终合并到此
- 功能分支命名：`feat/<name>`、`fix/<name>`、`refactor/<name>` 等

---

## 问题反馈

- 在 Issue 中描述问题或建议
- 包含复现步骤、预期行为和实际行为
- 附上相关日志（注意不要泄露 API Key 等敏感信息）
