# RF-017: Define Custom Exception Types Spec

## Why

当前代码库中所有异常都使用 Python 内置类型（ValueError、Exception、RuntimeError、FileNotFoundError 等），无法通过异常类型区分错误来源（配置错误 vs 解析失败 vs 检索失败等），不利于精确的错误处理和日志分析。引入自定义异常层次结构可以提供更清晰的错误分类，使调用方能够按类型捕获特定领域的异常。

## What Changes

- 创建 `src/exceptions.py`，定义 8 个自定义异常类，全部继承自 `RAGPipelineError`
- 替换 `src/` 和 `eval/` 目录下所有 `raise ValueError/Exception/RuntimeError/FileNotFoundError/TypeError/ImportError` 为对应的自定义异常
- 更新 `src/__init__.py` 导出所有异常类
- 更新 `except ValueError/FileNotFoundError` 模式以兼容自定义异常
- 更新 `tests/` 目录下所有 `pytest.raises(ValueError/Exception/...)` 为对应的自定义异常类型

## Impact

- Affected code: `src/` 全部模块、`eval/` 全部模块、`tests/` 全部测试文件
- **BREAKING**: 所有 `except ValueError` / `pytest.raises(ValueError)` 捕获本项目抛出的异常时，需改为捕获对应的自定义异常类型
- 外部库抛出的 ValueError/FileNotFoundError 等不受影响

## ADDED Requirements

### Requirement: Custom Exception Hierarchy

系统 SHALL 提供以下自定义异常层次结构：

```
RAGPipelineError (继承 Exception)
├── ConfigurationError    — 配置验证失败
├── ParsingError          — PDF/文档解析失败
├── RetrievalError        — 检索执行失败
├── IndexingError         — 索引构建或查询失败
├── GenerationError       — LLM 生成或 API 调用失败
├── MealError             — Meal 管理操作失败
├── TestSetError          — 测试集管理操作失败
└── EvaluationError       — 评估计算失败
```

每个异常类 SHALL：
- 继承自 `RAGPipelineError`
- 包含中文 docstring 说明用途
- 支持标准异常参数（message, cause chain）

#### Scenario: 异常层次正确性

- **WHEN** 代码 `raise ConfigurationError("bad config")`
- **THEN** `except RAGPipelineError` 能捕获该异常
- **AND** `except Exception` 能捕获该异常
- **AND** `except ValueError` 不能捕获该异常

### Requirement: Exception Mapping Rules

系统 SHALL 按以下规则替换异常：

| 原异常类型 | 上下文 | 替换为 |
|-----------|--------|--------|
| `ValueError` | 配置/参数验证 | `ConfigurationError` |
| `ValueError` | PDF/文档解析 | `ParsingError` |
| `ValueError` | 检索参数/操作 | `RetrievalError` |
| `ValueError` | 索引操作 | `IndexingError` |
| `ValueError` | LLM 生成参数 | `GenerationError` |
| `ValueError` | Meal 管理 | `MealError` |
| `ValueError` | 测试集管理 | `TestSetError` |
| `ValueError` | 评估计算 | `EvaluationError` |
| `Exception from e` | LLM/API 调用失败 | `GenerationError` |
| `Exception from e` | 检索执行失败 | `RetrievalError` |
| `Exception from e` | 索引操作失败 | `IndexingError` |
| `Exception from e` | 解析失败 | `ParsingError` |
| `Exception from e` | 嵌入操作失败 | `IndexingError` |
| `Exception from e` | 评估计算失败 | `EvaluationError` |
| `FileNotFoundError` | 解析上下文 | `ParsingError` |
| `FileNotFoundError` | 索引上下文 | `IndexingError` |
| `FileNotFoundError` | Meal 上下文 | `MealError` |
| `FileNotFoundError` | 测试集上下文 | `TestSetError` |
| `FileNotFoundError` | 实验配置上下文 | `ConfigurationError` |
| `FileNotFoundError` | 可视化上下文 | `EvaluationError` |
| `RuntimeError` | BM25 索引未构建 | `RetrievalError` |
| `TypeError` | 解析器注册 | `ConfigurationError` |
| `ImportError` | 解析器注册/依赖缺失 | `ConfigurationError` |
| `ImportError` | RAGAS/评估依赖缺失 | `EvaluationError` |
| `ImportError` | 可视化依赖缺失 | `EvaluationError` |

#### Scenario: 替换后行为一致

- **WHEN** 将 `raise ValueError("Question must be a non-empty string")` 替换为 `raise ConfigurationError("Question must be a non-empty string")`
- **THEN** 错误消息文本保持不变
- **AND** 异常链 `from e` 保持不变

### Requirement: Except Clause Updates

系统 SHALL 更新所有 `except ValueError/FileNotFoundError/TypeError/RuntimeError` 模式：

- `except ValueError as e` 捕获本项目 ValueError → 改为 `except ConfigurationError as e`（或对应类型）
- `except FileNotFoundError as e` 捕获本项目 FileNotFoundError → 改为 `except ParsingError as e`（或对应类型）
- `except RuntimeError as e` 捕获本项目 RuntimeError → 改为 `except RetrievalError as e`
- `except Exception as e` → 保持不变（已能捕获所有自定义异常）
- `except ImportError as e` → 保持不变（外部依赖导入错误，非自定义异常）
- 混合场景（同时捕获本项目和外部库异常）→ 使用 `except (ValueError, ConfigurationError) as e`

#### Scenario: Experiment config loading

- **WHEN** `load_experiment_config` 内部 `ExperimentConfig.from_dict` 抛出 `ConfigurationError`
- **AND** 外层有 `except ValueError as e` 捕获
- **THEN** 该 except 子句 SHALL 更新为 `except ConfigurationError as e`

### Requirement: Test File Updates

系统 SHALL 更新所有 `pytest.raises()` 中的异常类型：

- `pytest.raises(ValueError, match="...")` → `pytest.raises(ConfigurationError, match="...")`（或对应类型）
- `pytest.raises(FileNotFoundError)` → `pytest.raises(ParsingError)`（或对应类型）
- `pytest.raises(Exception, match="...")` → `pytest.raises(GenerationError, match="...")`（或对应类型）
- `pytest.raises(RuntimeError, match="...")` → `pytest.raises(RetrievalError, match="...")`

#### Scenario: Test still passes after update

- **WHEN** 将 `pytest.raises(ValueError, match="Question must be a non-empty string")` 改为 `pytest.raises(ConfigurationError, match="Question must be a non-empty string")`
- **THEN** 测试 SHALL 仍然通过

### Requirement: Module Exports

`src/__init__.py` SHALL 导出所有自定义异常类：

```python
from src.exceptions import (
    RAGPipelineError,
    ConfigurationError,
    ParsingError,
    RetrievalError,
    IndexingError,
    GenerationError,
    MealError,
    TestSetError,
    EvaluationError,
)
```

## MODIFIED Requirements

### Requirement: Error Handling Convention

所有 `src/` 和 `eval/` 中的公共函数 SHALL 使用自定义异常类型而非 Python 内置异常类型。错误消息文本和异常链保持不变。
