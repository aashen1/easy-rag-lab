# BUG-024 修复计划：Chunk JSONL 文本编码损坏导致 chunk-level 指标无法计算

## 问题描述

Chunk JSONL 文件中的 `text` 字段存在编码损坏，中文字符显示为乱码（如 `鍦 浜` 而非 `地产`），导致：

* `source_chunks` 始终为空

* chunk-level 指标（chunk\_hit\_rate / chunk\_mrr / chunk\_ndcg）无法计算，返回 null

## 根因分析

问题出在 [chunker.py:chunk\_text()](file:///b:/project/w0-easy-rag/src/chunker.py#L204-L220) 的 `encoding.encode()` → `encoding.decode()` 往返：

```python
tokens = encoding.encode(text)           # 整页文本编码为 token 序列
chunk_tokens = tokens[start:end]         # 按 chunk_size 切割
chunk_text_decoded = encoding.decode(chunk_tokens)  # 解码回文本
```

### 两种编码器的行为差异

1. **tiktoken (`cl100k_base`)**：`decode()` 在 token 不在 UTF-8 边界上时有损。tiktoken 官方文档明确警告："decode() can be lossy for tokens that aren't on utf-8 boundaries"。当 chunk 边界恰好切在多字节 UTF-8 字符的 token 中间时，`decode()` 会产生乱码。

2. **BGE tokenizer (`bge`)**：当前配置使用 `encoding: "bge"`，BGETokenizerEncoder 的 `decode()` 调用 HuggingFace tokenizer 的 `decode()`，通常能正确处理子词边界。但 `chunk_text_page_aware()` 中的 `cross_page_overlap` 逻辑（[chunker.py:472](file:///b:/project/w0-easy-rag/src/chunker.py#L472)）也使用了 `encoding.decode(prev_page_tail_tokens)`，同样可能产生乱码。

### 关键发现

当前配置 `config.yaml` 使用 `encoding: "bge"`，但 BUG 报告中的乱码现象（`鍦 浜` 而非 `地产`）是典型的 **UTF-8 字节被错误解码为 GBK/GB2312** 的表现。这说明：

* 可能存在旧的 chunk JSONL 文件是用 `cl100k_base` 生成的，尚未用 `bge` 重新生成

* 或者 BGE tokenizer 在某些边界情况下也会产生类似问题

## 修复方案

### 方案 A：在 chunk\_text() 中使用字符边界对齐（推荐）

**核心思路**：不再直接对 token 切片后 decode，而是利用原始文本的字符偏移量来确保 chunk 文本始终是原始文本的子串，从而彻底避免编码/解码问题。

**实现步骤**：

1. **在** **`chunk_text()`** **中增加字符偏移追踪**：

   * `encode()` 后，使用 `encoding.decode(tokens[:i])` 的长度来建立 token 索引到字符索引的映射

   * 但这太慢。更好的方式是：先对整个文本 encode，然后对每个 chunk 的 token 子序列，用 `encoding.decode()` 得到文本，但**与原文比对校正**

2. **更简洁的实现**：利用 tiktoken 的 `encode_with_offsets()` 或手动构建 token→char 映射：

   * 对每个 token，记录其对应的原始文本中的字符范围

   * chunk 边界对齐到字符边界，确保 chunk 文本直接从原始文本切片

3. **具体代码修改**（`chunk_text()` 函数）：

```python
def chunk_text(text, chunk_size=512, overlap=0, encoding_name="cl100k_base", model_name=None):
    encoding = _get_encoding(encoding_name, model_name)
    tokens = encoding.encode(text)
    total_tokens = len(tokens)

    # 构建 token → 原始文本字符偏移的映射
    # 方法：逐个 token decode，累计字符数
    token_char_offsets = []  # [(start_char, end_char), ...]
    char_pos = 0
    for i in range(total_tokens):
        token_text = encoding.decode(tokens[i:i+1])
        start_char = char_pos
        end_char = char_pos + len(token_text)
        token_char_offsets.append((start_char, end_char))
        char_pos = end_char

    chunks = []
    start = 0
    while start < total_tokens:
        end = min(start + chunk_size, total_tokens)

        # 从原始文本直接切片，避免 decode 乱码
        char_start = token_char_offsets[start][0]
        char_end = token_char_offsets[end - 1][1]
        chunk_text_decoded = text[char_start:char_end]

        chunks.append({
            "text": chunk_text_decoded,
            "metadata": {
                "chunk_index": chunk_index,
                "char_count": len(chunk_text_decoded),
                "token_count": end - start,
                "start_token": start,
                "end_token": end,
            },
        })
        ...
```

**优点**：

* 彻底解决编码损坏问题，chunk 文本始终是原始文本的子串

* 对 tiktoken 和 BGE tokenizer 都有效

* 不需要重新生成已有数据（但需要重新 chunk）

**缺点**：

* 逐 token decode 构建映射有一定性能开销（但对于 512 token 的 chunk 来说可接受）

* 需要验证 BGE tokenizer 的单 token decode 行为

### 方案 B：在 decode 时使用 errors="replace" 处理

**核心思路**：在 `encoding.decode(chunk_tokens)` 时传入错误处理参数。

**问题**：

* tiktoken 的 `decode()` 方法支持 `errors` 参数

* 但 BGETokenizerEncoder 的 `decode()` 不支持 `errors` 参数（HuggingFace tokenizer 的 decode 接口不同）

* 这只是掩盖问题，乱码字符被替换为 `�`，文本匹配仍然失败

**结论**：不推荐，治标不治本。

### 方案 C：混合方案 — 优先原文切片，fallback 到 decode

在方案 A 的基础上，如果 BGE tokenizer 的单 token decode 行为不一致，则 fallback 到 `encoding.decode(chunk_tokens)` 并记录警告。

## 最终推荐：方案 A

## 实施步骤

### Step 1：修改 `chunk_text()` 函数

* 在 [chunker.py:156-246](file:///b:/project/w0-easy-rag/src/chunker.py#L156-L246) 中，构建 token→char 映射

* 使用原始文本切片替代 `encoding.decode(chunk_tokens)`

* 保留 `token_count` 等元数据不变

### Step 2：修改 `chunk_text_page_aware()` 中的 cross\_page\_overlap 逻辑

* [chunker.py:472](file:///b:/project/w0-easy-rag/src/chunker.py#L472) 的 `encoding.decode(prev_page_tail_tokens)` 也需要用原文切片替代

* 需要在 page\_aware 流程中维护 token→char 映射

### Step 3：编写测试

* 添加中文文本 chunk 的往返测试：`chunk_text()` 对中文文本的输出应与原文子串完全一致

* 添加边界条件测试：chunk 边界恰好落在多字节字符中间

* 添加 BGE encoding 中文测试

* 验证 `chunk_text_page_aware()` 的 cross\_page\_overlap 中文测试

### Step 4：重新生成 chunk JSONL

* 修复代码后，需要重新运行 chunker 生成新的 JSONL 文件

* 验证新 JSONL 文件中中文 text 字段可读

### Step 5：验证 chunk-level 指标

* 运行评估，确认 `source_chunks` 不再为空

* 确认 chunk\_hit\_rate / chunk\_mrr / chunk\_ndcg 能正常计算

### Step 6：更新文档

* 更新 `docs/backlog.md` 中 BUG-024 状态为已完成

* 更新 `docs/guides/development/hybrid-metrics-fix.md` 中第 6 节

## 风险与注意事项

1. **性能**：逐 token decode 构建映射会增加开销。对于长文档（数万 token），可以考虑批量优化：每 N 个 token 计算一次偏移量
2. **BGE tokenizer 兼容性**：需验证 HuggingFace tokenizer 的单 token decode 是否与 tiktoken 行为一致
3. **数据迁移**：旧的 chunk JSONL 文件需要全部重新生成，artifact 缓存可能需要失效
4. **向后兼容**：`chunk_text()` 的返回格式不变，只是 `text` 字段的生成方式改变
