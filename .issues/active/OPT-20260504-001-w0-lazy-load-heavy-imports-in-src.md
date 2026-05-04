---
id: OPT-20260504-001-w0
title: Lazy-load heavy imports in src modules to reduce test startup time
type: OPT
status: todo
priority: medium
labels:
- performance
- testing
assignee: null
milestone: null
created_at: '2026-05-04T10:14:24.686264'
updated_at: '2026-05-04T10:14:24.686264'
source: active\OPT-20260504-001-w0-lazy-load-heavy-imports-in-src.md
legacy_id: null
---
## 优化目标

将 `src/` 模块中的重量级顶层 import 改为延迟加载（lazy import），使 `from src.xxx import Yyy` 不再触发 torch / transformers / qdrant_client 等重依赖的加载，从而将测试收集阶段和首次导入的耗时从 ~10s 降至 ~1s。

## 当前问题

### 1. `src/pipeline.py` 是重量级依赖的集散地

`pipeline.py` 在顶层导入了 `embedder`（torch + transformers）和 `reranker`（torch + transformers），导致任何 `from src.pipeline import RAGPipeline` 都要等 ~9.4s 才能完成导入。

实测各重依赖的独立导入耗时：

| 依赖 | 导入耗时 |
|------|---------|
| `torch` | ~1.9s |
| `transformers` (via embedder) | ~3s |
| `qdrant_client` | ~1.0s |
| `streamlit` | ~1.2s |
| `from src.pipeline import RAGPipeline` | **~9.4s** |

### 2. 传递性导入链

```
pipeline.py
  ├── src.embedder       → torch + transformers + numpy  (极重)
  ├── src.reranker       → torch + transformers + numpy  (极重)
  ├── src.indexer        → qdrant_client + numpy          (中重)
  ├── src.bm25_retriever → jieba                          (中等)
  ├── src.retriever      → src.embedder + src.indexer     (极重，传递)
  ├── src.query_rewriter → anthropic                      (中等)
  └── src.generator      → anthropic + tiktoken           (中等)
```

任何测试文件只要 `from src.pipeline import RAGPipeline`（如 `test_pipeline.py`、`test_regression.py`），或 `from src.retriever import Retriever`（如 `test_retriever.py`、`test_hybrid_retriever.py`），都会触发整条链的加载。

### 3. 受影响的测试文件

| 测试文件 | 触发的重导入 | 导入位置 |
|----------|-------------|---------|
| `test_pipeline.py` | pipeline → torch + transformers | 顶层 |
| `test_regression.py` | pipeline → torch + transformers | 函数内 |
| `test_retriever.py` | retriever → embedder → torch | 顶层 |
| `test_hybrid_retriever.py` | retriever → embedder → torch | 顶层 |
| `test_embedder.py` | torch + transformers | 顶层 |
| `test_reranker.py` | torch + transformers | 顶层 |
| `test_indexer.py` | qdrant_client | 顶层 |
| `conftest.py` | streamlit (已修复为延迟导入) | fixture 内 |

### 4. 对 xdist 的影响

pytest-xdist 在 Windows 上使用 spawn 模式，每个 worker 进程都要独立执行一次完整的模块导入。16 个 worker × 9.4s 的 pipeline 导入 = 大量 CPU 时间浪费在重复加载上。这是 xdist 在当前项目上几乎无加速效果的核心原因。

## 优化方案

### 方案 A：`TYPE_CHECKING` 守卫 + 函数内延迟导入（推荐）

对 `pipeline.py`、`retriever.py` 等模块，将重量级导入改为：

```python
from __future__ import annotations  # 已有

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.embedder import Embedder
    from src.reranker import Reranker
    from src.indexer import VectorIndexer

class RAGPipeline:
    def __init__(self, ...):
        from src.embedder import Embedder      # 延迟到实例化时
        from src.reranker import Reranker
        from src.indexer import VectorIndexer
        ...
```

**优点**：
- 类型检查器（mypy/pyright）仍能正确识别类型
- IDE 自动补全不受影响
- 只在实际创建实例时才加载重依赖
- 测试中 mock 掉 `__init__` 后完全跳过重导入

**需要修改的文件**（按优先级排序）：

1. **`src/pipeline.py`** — 收益最大（9.4s → ~0s for import）
   - `embedder`、`reranker`、`indexer`、`bm25_retriever`、`retriever`、`hybrid_retriever` 改为延迟导入
   - `query_rewriter`、`generator`、`chunker` 等中等依赖也可一并处理

2. **`src/retriever.py`** — 传递性导入链的关键节点
   - `from src.embedder import Embedder` 和 `from src.indexer import VectorIndexer` 改为延迟导入
   - 这样 `from src.retriever import Retriever` 不再触发 torch

3. **`src/embedder.py`** — torch + transformers 的直接入口
   - `import torch` 和 `from transformers import AutoModel, AutoTokenizer` 改为 `__init__` 内延迟导入
   - 类属性 `embedding_dim` 等不依赖 torch 的逻辑保持顶层可用

4. **`src/reranker.py`** — 同 embedder
   - `import torch` 和 `from transformers import ...` 改为延迟导入

5. **`src/indexer.py`** — qdrant_client 的入口
   - `from qdrant_client import QdrantClient` 改为 `__init__` 内延迟导入

### 方案 B：可选依赖 + `importlib.util.find_spec` 守卫

对可能不在所有环境安装的依赖（如 torch），增加运行时检测：

```python
import importlib.util

_TORCH_AVAILABLE = importlib.util.find_spec("torch") is not None

def _get_torch():
    if not _TORCH_AVAILABLE:
        raise ImportError("torch is required for this feature")
    import torch
    return torch
```

**适用场景**：未来如果项目需要支持 CPU-only 或轻量部署模式。

### 方案 C：拆分模块（不推荐，工作量大）

将 `pipeline.py` 拆分为 `pipeline_types.py`（纯类型/接口）和 `pipeline_impl.py`（重依赖实现）。

**缺点**：破坏现有 import 路径，需要更新所有下游代码。

### 预期收益

| 场景 | 当前 | 优化后（预期） |
|------|------|---------------|
| `from src.pipeline import RAGPipeline` | 9.4s | <0.1s |
| 测试收集阶段（2076 测试） | ~16s | ~3s |
| xdist worker 启动（16 workers） | 每个 ~10s | 每个 ~2s |
| `pixi run test` 总时间 | 32s | ~15-20s |

### 实施注意事项

1. **`__init__` 内延迟导入的模块仍可被 mock**：测试中 `patch("src.embedder.Embedder")` 不受影响，因为 mock 发生在 `__init__` 调用之前
2. **`from __future__ import annotations`** 必须保留，否则 `TYPE_CHECKING` 守卫的类型注解在运行时求值会报错
3. **逐步实施**：先改 `pipeline.py` 和 `retriever.py`（收益最大），再改 `embedder.py` / `reranker.py` / `indexer.py`
4. **每步验证**：改一个文件就跑一次 `pixi run test`，确保不破坏现有测试

## 更新记录

- 2026-05-04：创建，详细记录问题分析和三种修复方案
