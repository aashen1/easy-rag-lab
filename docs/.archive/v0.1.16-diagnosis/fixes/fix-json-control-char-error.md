# 修复 LLM JSON 解析中的控制字符错误

## 问题分析

### 错误信息

```
Failed to parse LLM response as JSON: Invalid control character at: line 6 column 224 (char 335)
```

### 根本原因

在 [eval/metrics/generation.py:382](../eval/metrics/generation.py#L382) 的 `parse_relevancy_response` 函数中，LLM 返回的 JSON 包含未转义的控制字符（如换行符 `\n`、制表符 `\t` 等），导致 `json.loads()` 解析失败。

具体问题：

1. LLM 在 `reasoning` 字段中可能包含换行符或其他控制字符
2. Python 的 `json.loads()` 默认 `strict=True`，遇到控制字符会抛出 `JSONDecodeError`
3. 当前正则表达式 `r"\{[^{}]*\}"` 只能匹配不包含嵌套大括号的简单 JSON

### 影响范围

* `parse_relevancy_response` 函数 (第 367-389 行)

* 其他类似的 JSON 解析逻辑在 `extract_statements` 和 `verify_statements` 函数中也有类似问题

## 修复方案

### 方案：使用 `strict=False` 参数

在 `json.loads()` 调用时添加 `strict=False` 参数，允许解析包含控制字符的 JSON 字符串。

**优点**：

* 简单直接，一行修改

* Python 官方支持的方式

* 不改变 JSON 语义，只是放宽解析限制

**缺点**：

* 可能允许一些非标准 JSON 通过

* 控制字符在字符串值中保留，可能影响后续处理

### 实施步骤

1. **修改** **`parse_relevancy_response`** **函数**

   * 在 `json.loads()` 调用中添加 `strict=False`

   * 两处调用都需要修改（第 382 行和第 387 行）

2. **修改其他类似函数**（可选，预防性修复）

   * `extract_statements` 函数（第 141 行）

   * `verify_statements` 函数（第 228 行）

   * `llm_retrieval.py` 中的相关函数（第 101 行、第 266 行）

3. **添加测试用例**

   * 测试包含控制字符的 JSON 解析

   * 验证修复后功能正常

## 代码修改

### 文件：`eval/metrics/generation.py`

```python
# 第 379-389 行，修改前：
json_match = re.search(r"\{[^{}]*\}", response_text, re.DOTALL)
if json_match:
    try:
        return json.loads(json_match.group())
    except json.JSONDecodeError:
        pass

try:
    return json.loads(response_text)
except json.JSONDecodeError as e:
    raise EvaluationError(f"Failed to parse LLM response as JSON: {e}") from e

# 修改后：
json_match = re.search(r"\{[^{}]*\}", response_text, re.DOTALL)
if json_match:
    try:
        return json.loads(json_match.group(), strict=False)
    except json.JSONDecodeError:
        pass

try:
    return json.loads(response_text, strict=False)
except json.JSONDecodeError as e:
    raise EvaluationError(f"Failed to parse LLM response as JSON: {e}") from e
```

### 文件：`eval/metrics/generation.py`（其他位置）

```python
# 第 141 行
result = json.loads(json_match.group(), strict=False)

# 第 228 行
result = json.loads(json_match.group(), strict=False)
```

### 文件：`eval/metrics/llm_retrieval.py`

```python
# 第 101 行
result = json.loads(json_match.group(), strict=False)

# 第 266 行
result = json.loads(json_match.group(), strict=False)
```

## 测试计划

1. 运行现有测试确保不破坏现有功能
2. 添加新的测试用例验证控制字符处理
3. 可选：重新运行实验验证修复有效

## 风险评估

* **风险等级**：低

* **影响范围**：仅影响 JSON 解析的容错性

* **回滚方案**：移除 `strict=False` 参数即可恢复
