# 评测指标问题修复计划

## 问题概述

运行 `pixi run exp quick_verify_metrics` 后发现以下问题：

| 问题 | 类型 | 优先级 |
|------|------|--------|
| `context_recall=0` for Markdown 表格 | 句子分割逻辑 | 中 |
| q003 回答与 ground_truth 不一致 | 检索系统 | 低（非评测代码问题）|

---

## 问题 1：`context_recall=0` for Markdown 表格

### 现象

- q002（对比分析）：`context_recall=0`
- q003（多知识点综合）：`context_recall=0`

### 根因分析

`ground_truth_excerpt` 是 Markdown 表格格式：

```
|工序环节|传统分立光模块|硅光集成光模块|
|---|---|---|
|贴片|独立工序...|核心工序...|
```

`_split_into_sentences()` 使用 `[。！？.!?]` 分割句子，但表格中没有这些标点，导致：
1. 整个表格被当作一个"句子"
2. 句子被截断成不完整片段
3. LLM 无法判断这些片段是否能从 context 推断

### 修复方向

**方案 A：改进句子分割逻辑**（推荐）

修改 `eval/metrics/llm_retrieval.py` 中的 `_split_into_sentences()`：

```python
def _split_into_sentences(text: str) -> list[str]:
    """Split text into sentences, handling Markdown tables."""
    # 先按换行符分割表格行
    if "|" in text and "---" in text:
        # Markdown 表格：按行分割
        lines = text.split("\n")
        sentences = []
        for line in lines:
            line = line.strip()
            if line and not line.startswith("|---"):
                sentences.append(line)
        return sentences
    
    # 普通文本：按标点分割
    sentences = re.split(r"[。！？.!?]", text)
    return [s.strip() for s in sentences if s.strip()]
```

**方案 B：在测试集生成时处理表格格式**

修改 `src/test_generator.py`，在生成 `ground_truth_excerpt` 时：
- 检测表格格式
- 将表格转换为更易分割的格式（如列表形式）

### 推荐方案

**方案 A**，原因：
1. 修改范围小，只影响评测逻辑
2. 不影响测试集生成流程
3. 可以处理未来可能出现的类似问题

---

## 问题 2：q003 回答与 ground_truth 不一致

### 现象

| 项目 | Ground Truth | 实际回答 |
|------|-------------|---------|
| 每股分红 | 31.69元/10股 | 25.76元/10股 |

### 根因分析

1. `chunk_retrieval` 全为 0，说明检索系统没有找到正确的 chunk
2. 可能原因：
   - 分红信息所在的 chunk 没有被向量检索到
   - chunk 切分位置导致关键信息被截断

### 影响范围

这是**检索系统**的问题，不属于评测代码范畴。

### 修复方向

1. **检查 chunk 切分**：确认分红信息是否在某个完整 chunk 中
2. **优化检索**：考虑增加 chunk 数量或调整相似度阈值
3. **测试集生成优化**：确保 ground_truth 对应的 chunk 在检索范围内

### 建议

暂不修复，原因：
1. 这是检索系统问题，不是评测代码 bug
2. 需要单独排查检索系统
3. 可以作为后续优化项

---

## 实施计划

### Step 1: 修复句子分割逻辑

修改文件：`eval/metrics/llm_retrieval.py`

- 改进 `_split_into_sentences()` 函数
- 添加 Markdown 表格检测和处理逻辑
- 添加单元测试验证

### Step 2: 运行实验验证

```bash
pixi run exp quick_verify_metrics
```

检查 `context_recall` 是否正常计算。

### Step 3: 提交修复

```bash
git add eval/metrics/llm_retrieval.py
git commit -m "fix: handle Markdown tables in context_recall sentence splitting"
```

---

## 不修复项

| 问题 | 原因 |
|------|------|
| q003 回答错误 | 检索系统问题，非评测代码 bug |
