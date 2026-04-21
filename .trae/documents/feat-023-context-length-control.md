# FEAT-023: Context 长度控制（防止超出模型 context window）

## 问题分析

**来源**：[pipeline-deep-audit.md P5-3](docs/pipeline-deep-audit.md) — 无 Context 长度控制

**现状**：`Generator.generate()` 将所有检索到的 context 直接拼接后传给 LLM，没有任何长度保护。5 个 512-token chunk ≈ 2560 token，加上 system prompt + query + max_tokens（输出），可能接近或超过模型的 context window 限制。

**风险**：
- 超出模型 context window 导致 API 报错（如 Anthropic 的 `overloaded_error`）
- 即使不报错，过长的输入也会降低回答质量、增加成本
- 不同模型的 context window 大小不同，当前无法适配

## 实现方案

### 核心思路

在 `Generator.generate()` 中，**发送 API 请求之前**，估算拼接后 user_message 的 token 数，若超出模型 context window 的安全余量，则从尾部截断 contexts 列表，确保不会超限。

### 设计决策

1. **Token 估算方式**：复用已有的 `estimate_tokens_tiktoken()`（来自 `token_tracker.py`），保持一致性
2. **Context window 大小配置化**：在 `config.yaml` 的 `generation` 段新增 `max_context_tokens` 字段，默认 `None`（不限制），用户按模型设定
3. **截断策略**：从 contexts 列表**尾部**逐个移除 chunk（保留相似度最高的前排 chunk），直到总 token 数在安全范围内
4. **安全余量**：预留 `max_tokens`（输出配额）+ 200 token 缓冲（消息格式开销），即 `available = max_context_tokens - max_tokens - 200`
5. **日志记录**：截断时记录 warning 日志，包含原始/截断后的 chunk 数量和 token 数

### 不做的事

- 不做 chunk 内部截断（只移除整个 chunk，不切割 chunk 内容）
- 不做 token 级精确计算（tiktoken 估算已足够，且与现有 token_tracker 保持一致）
- 不修改 `pipeline.py` 调用方式（完全在 Generator 内部透明处理）

## 实现步骤

### Step 1: 修改 `config.yaml` — 新增 `max_context_tokens` 配置

在 `generation` 段新增字段：

```yaml
generation:
  system_prompt: null
  max_context_tokens: null   # Maximum total input tokens (system_prompt + contexts + query). null = no limit.
```

### Step 2: 修改 `src/generator.py` — 添加 context 长度控制逻辑

1. `__init__` 新增 `max_context_tokens: int | None = None` 参数
2. 新增私有方法 `_truncate_contexts()`：接收 contexts、system_prompt、query，估算总 token 数，超限时从尾部移除 chunk
3. `generate()` 中在拼接 user_message 之前调用 `_truncate_contexts()`

关键代码逻辑：

```python
def _truncate_contexts(
    self,
    contexts: list[str],
    system_prompt: str,
    query: str,
) -> list[str]:
    if not contexts or self.max_context_tokens is None:
        return contexts

    safety_buffer = 200
    available = self.max_context_tokens - self.max_tokens - safety_buffer

    system_tokens = estimate_tokens_tiktoken(system_prompt)
    query_tokens = estimate_tokens_tiktoken(query)
    overhead = system_tokens + query_tokens

    if overhead >= available:
        logger.warning(
            f"System prompt + query ({overhead} tokens) already exceeds "
            f"available context ({available} tokens). No contexts will be sent."
        )
        return []

    remaining = available - overhead
    truncated = []
    total = 0
    for ctx in contexts:
        ctx_tokens = estimate_tokens_tiktoken(ctx)
        if total + ctx_tokens > remaining:
            break
        truncated.append(ctx)
        total += ctx_tokens

    if len(truncated) < len(contexts):
        logger.warning(
            f"Context truncated: {len(contexts)} -> {len(truncated)} chunks, "
            f"estimated tokens: {overhead + total}/{self.max_context_tokens}"
        )

    return truncated
```

### Step 3: 修改 `src/pipeline.py` — 传递 `max_context_tokens` 配置

在 `RAGPipeline.__init__` 中构造 Generator 时，从 config 读取 `max_context_tokens` 并传入。

### Step 4: 编写 TDD 测试

在 `tests/test_generator.py` 中新增以下测试用例：

1. **test_truncate_contexts_removes_tail_chunks** — 超限时从尾部移除 chunk
2. **test_truncate_contexts_no_limit_when_null** — `max_context_tokens=None` 时不截断
3. **test_truncate_contexts_fits_within_limit** — 未超限时不截断
4. **test_truncate_contexts_all_exceed_returns_empty** — system_prompt+query 已超限，返回空列表
5. **test_truncate_contexts_logs_warning** — 截断时记录 warning 日志
6. **test_max_context_tokens_passed_from_config** — pipeline 正确传递配置

### Step 5: 运行 lint 和测试

- `pixi run lint` 检查代码格式
- `pixi run test tests/test_generator.py` 确保所有测试通过

## 文件变更清单

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `config.yaml` | 修改 | generation 段新增 `max_context_tokens` |
| `src/generator.py` | 修改 | 新增 `max_context_tokens` 参数 + `_truncate_contexts()` 方法 |
| `src/pipeline.py` | 修改 | 传递 `max_context_tokens` 配置给 Generator |
| `tests/test_generator.py` | 修改 | 新增 6 个测试用例 |
