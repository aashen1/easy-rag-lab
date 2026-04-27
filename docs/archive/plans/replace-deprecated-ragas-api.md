# Plan: Replace Deprecated RAGAS API with Modern Equivalents

## Background

ragas 0.4.3 中 `LangchainLLMWrapper` 和 `LangchainEmbeddingsWrapper` 均被标记为 deprecated，推荐使用 `llm_factory` 和原生 embedding providers。当前代码（上一轮已修复参数名问题）仍使用 deprecated API，需要迁移到现代 API。

## Changes

### 1. `_create_llm()`: Replace `LangchainLLMWrapper` with `llm_factory`

**Before:**

```python
from langchain_anthropic import ChatAnthropic
from ragas.llms.base import LangchainLLMWrapper
# ... create ChatAnthropic instance ...
return LangchainLLMWrapper(langchain_llm=lc_llm)
```

**After:**

```python
from anthropic import Anthropic
from ragas.llms import llm_factory

client = Anthropic(
    api_key=llm_config["api_key"],
    base_url=base_url,
    default_headers={...},
)
return llm_factory(llm_config["model_name"], provider="anthropic", client=client)
```

**Key points:**

* `llm_factory` 返回 `InstructorLLM`（ragas 0.4.3 推荐类型），而非 deprecated 的 `LangchainLLMWrapper`

* `anthropic` 包已在 pixi.toml 中声明（`>=0.95.0`），无需新增依赖

* `Anthropic` 原生客户端支持 `base_url` 和 `default_headers`，与 LongCat API 兼容

* 不再需要 `langchain-anthropic` 依赖来创建 LLM（但其他模块可能仍在使用，不删除依赖）

* `llm_factory` 的 `provider="anthropic"` 会自动选择 instructor adapter

### 2. `_create_embeddings()`: Replace `LangchainEmbeddingsWrapper` with ragas native `HuggingFaceEmbeddings`

**Before:**

```python
from langchain_community.embeddings import HuggingFaceEmbeddings
from ragas.embeddings.base import LangchainEmbeddingsWrapper
# ... create langchain embeddings ...
return LangchainEmbeddingsWrapper(embeddings=embeddings)
```

**After:**

```python
from ragas.embeddings import HuggingFaceEmbeddings
return HuggingFaceEmbeddings(model=model_name, device=device)
```

**Key points:**

* ragas 0.4.3 原生提供 `HuggingFaceEmbeddings`，无需再通过 langchain 中转

*  ragas 的 `HuggingFaceEmbeddings` 本地模式需要 \```sentence-transformers`，该依赖已由用户新增。``

* 这也移除了对 `langchain-community` embeddings 的依赖（仅限此模块）

### 3. `_create_metrics()`: No change needed

上一轮修复已将 metrics 改为使用 `ragas.metrics` 的基础类（`_Faithfulness` 等），这些接受 `Optional[BaseRagasLLM]`，与 `InstructorLLM` 兼容。`InstructorLLM` 可以直接设置到 `metric.llm` 属性上（ragas evaluate 内部也是这样做的）。

### 4. Add `sentence-transformers` dependency to `pixi.toml`

ragas 原生 `HuggingFaceEmbeddings` 本地模式需要此包。

## Files to Modify

1. `eval/evaluators/ragas_evaluator.py` — 主要修改文件
2. `pixi.toml` — 添加 `sentence-transformers` 依赖（已由用户完成）

## Verification

* 导入测试：验证 `llm_factory` + `InstructorLLM` 可正常创建

* 导入测试：验证 `ragas.embeddings.HuggingFaceEmbeddings` 可正常创建

* Metrics 创建测试：验证 `_Faithfulness(llm=instructor_llm)` 等可正常工作

* `RagasEvaluator` 类实例化测试
