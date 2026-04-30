# 代码质量重构计划

## 背景

基于 2026-04-29 的代码质量审查，识别出以下可改进点。本计划聚焦于**风险可控、收益明确**的重构任务。

---

## 重构范围选择

### ✅ 纳入本次重构

| 问题 | 文件 | 优先级 | 风险 | 理由 |
|------|------|--------|------|------|
| 类型标注 `str = None` 错误 | generator.py, llm_client.py | P0 | 低 | mypy 会报错，修复简单明确 |
| main.py 缺少 docstring | main.py | P0 | 低 | 15个函数0个docstring，严重违反规范 |
| pipeline.py 部分方法缺少 docstring | pipeline.py | P1 | 低 | 核心模块，docstring 不全会被 reviewer 关注 |
| `__enter__`/`__exit__` 缺少类型标注 | pipeline.py | P2 | 低 | 类型标注不完整 |
| `_get_client()` 缺少返回值类型标注 | query_rewriter.py | P1 | 低 | 类型标注不完整 |
| `_call_llm` 返回值标注为裸 `tuple` | query_rewriter.py | P1 | 低 | 类型标注不精确 |
| `fitz.open` 未使用 `with` 语句 | sampler.py | P2 | 低 | 资源泄漏风险 |
| `batch_size = 16` 硬编码 | reranker.py | P2 | 低 | 应提取为参数 |

### ❌ 暂不纳入

| 问题 | 理由 |
|------|------|
| eval/ 目录 98 条 print 语句 | 影响范围大，需要评估每条 print 的用途，建议单独 issue 处理 |
| embedder.py 模块级副作用 | 需要理解 HF_HUB_OFFLINE 的使用场景，改动可能影响离线模式 |
| run_eval.py deprecated 但仍在用 | 需要先确认替代方案是否完整，属于架构决策 |
| run_experiment.py sys.path 硬编码 | 需要理解项目导入结构，可能涉及打包配置 |

---

## 重构任务

### Task 1: 修复类型标注 `str = None` 错误

**文件**: `src/generator.py`, `src/llm_client.py`

**问题**: `str = None` 类型标注不正确，mypy 会报错，应为 `str | None = None`

**修改点**:

1. `src/generator.py`
   - Line 75: `model_name: str = None` → `model_name: str | None = None`
   - Line 77: `base_url: str = None` → `base_url: str | None = None`
   - Line 178: `system_prompt: str = None` → `system_prompt: str | None = None`

2. `src/llm_client.py`
   - Line 9: `base_url: str = None` → `base_url: str | None = None`

**验证**: 运行 `pixi run lint` 确认无新增错误

---

### Task 2: 补全 main.py 的 docstring

**文件**: `main.py`

**问题**: 15个函数0个docstring，严重违反项目规范

**修改点**: 为以下函数添加 Google-style docstring：

1. `main()` - 入口函数
2. `_handle_parse()` - 解析命令处理
3. `_handle_chunk()` - 分块命令处理
4. `_handle_embed()` - 嵌入命令处理
5. `_handle_index()` - 索引命令处理
6. `_handle_retrieve()` - 检索命令处理
7. `_handle_generate()` - 生成命令处理
8. `_handle_pipeline()` - 管线命令处理
9. `_handle_experiment()` - 实验命令处理
10. `_handle_eval()` - 评测命令处理
11. `_handle_meal()` - Meal 命令处理
12. `_handle_testset()` - 测试集命令处理
13. `_interactive_qa()` - 交互式问答
14. `_print_welcome()` - 打印欢迎信息
15. `_print_menu()` - 打印菜单

**docstring 模板**:
```python
def _handle_parse(args: argparse.Namespace) -> None:
    """处理解析命令，将 PDF 文档解析为 Markdown 格式。

    Args:
        args: 命令行参数，包含 input_dir、output_dir、parser 等字段。

    Raises:
        ParsingError: PDF 解析失败时抛出。
    """
```

**验证**: 运行 `pixi run lint` 确认无新增错误

---

### Task 3: 补全 pipeline.py 缺失的 docstring 和类型标注

**文件**: `src/pipeline.py`

**问题**: 核心模块部分方法缺少 docstring 和类型标注

**修改点**:

1. 补全 `__init__` docstring（Line 42-49）
2. 补全 `__enter__`/`__exit__` 返回值类型标注（Line 386-390）
3. 补全 `_get_retrieval_strategy` docstring（Line 550）
4. 补全 `_retrieve_multi` docstring（Line 563）
5. 补全 `_compute_scores` docstring（Line 578）

**验证**: 运行 `pixi run lint` 确认无新增错误

---

### Task 4: 修复 query_rewriter.py 类型标注问题

**文件**: `src/query_rewriter.py`

**问题**: 类型标注不完整、不精确

**修改点**:

1. Line 65: `_get_client()` 添加返回值类型标注 `Anthropic`
2. Line 195: `_call_llm` 返回值从 `tuple` 改为 `tuple[str, dict[str, Any] | None]`

**验证**: 运行 `pixi run lint` 确认无新增错误

---

### Task 5: 修复 sampler.py 资源泄漏风险

**文件**: `src/sampler.py`

**问题**: `fitz.open` 未使用 `with` 语句，异常时可能泄漏文件句柄

**修改点**: Line 66 附近，将 `fitz.open` 改为 `with` 语句

**修改前**:
```python
doc = fitz.open(pdf_path)
page_count = doc.page_count
doc.close()
return page_count
```

**修改后**:
```python
with fitz.open(pdf_path) as doc:
    return doc.page_count
```

**验证**: 运行 `pixi run lint` 和 `pixi run test tests/test_sampler.py` 确认无回归

---

### Task 6: 提取 reranker.py 硬编码 batch_size

**文件**: `src/reranker.py`

**问题**: `batch_size = 16` 硬编码在 `_score_pairs` 方法中

**修改点**: 将 `batch_size` 提取为 `__init__` 参数，默认值 16

**修改内容**:

1. `__init__` 添加 `batch_size: int = 16` 参数
2. 存储为 `self._batch_size`
3. `_score_pairs` 使用 `self._batch_size` 替代硬编码

**验证**: 运行 `pixi run lint` 和 `pixi run test tests/test_reranker.py` 确认无回归

---

## 执行顺序

1. Task 1: 类型标注修复（最简单，风险最低）
2. Task 5: sampler.py 资源泄漏修复（独立模块，不影响其他）
3. Task 6: reranker.py batch_size 提取（独立模块，不影响其他）
4. Task 4: query_rewriter.py 类型标注修复
5. Task 3: pipeline.py docstring 和类型标注补全
6. Task 2: main.py docstring 补全（工作量最大，放最后）

---

## 验证步骤

每个 Task 完成后：
1. 运行 `pixi run lint` 确认无新增 lint 错误
2. 运行相关模块的测试确认无回归
3. 提交 commit，格式：`refactor: <简短描述>`

全部完成后：
1. 运行 `pixi run test` 全量测试
2. 确认所有测试通过

---

## 预期收益

- 消除 3 处 mypy 类型标注错误
- 补全 main.py 15 个函数的 docstring，docstring 覆盖率从 0% 提升到 100%
- 补全 pipeline.py 核心模块的 docstring 和类型标注
- 修复 1 处潜在资源泄漏
- 消除 1 处硬编码

---

## 风险评估

| 风险 | 可能性 | 影响 | 缓解措施 |
|------|--------|------|----------|
| 类型标注修改导致 mypy 新错误 | 低 | 低 | 逐个修改，每次运行 lint |
| docstring 描述不准确 | 中 | 低 | 参考已有代码风格，保持简洁 |
| reranker batch_size 提取破坏现有调用 | 低 | 低 | 使用默认参数，保持向后兼容 |
| sampler.py with 语句行为差异 | 低 | 低 | fitz.open 的 with 语义是标准的 |

**总体风险**: 低。所有修改都是增量式的，不改变现有逻辑。
