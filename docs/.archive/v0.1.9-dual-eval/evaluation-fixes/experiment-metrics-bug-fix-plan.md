# 实验报告指标数值问题分析与修复计划

## 问题分析

### 现象
最近几次实验报告中，不同变体的指标数值完全相同，例如 `exp_20260419_141053_chunking_strategy_comparison` 实验：

| Variant | Hit Rate | MRR | NDCG |
|---------|----------|-----|------|
| fixed_512_overlap_0 | 0.8000 | 0.7283 | 1.8584 |
| semantic_threshold_50 | 0.8000 | 0.7283 | 1.8584 |
| semantic_threshold_30 | 0.8000 | 0.7283 | 1.8584 |
| semantic_percentile_25 | 0.8000 | 0.7283 | 1.8584 |

这显然不正常，不同的分块策略应该产生不同的检索结果。

### 根本原因

问题出在 [src/meal.py:128-136](file:///b:/project/ash-easy-rag/src/meal.py#L128-L136) 的 `compute_chunker_config_hash` 函数：

```python
def compute_chunker_config_hash(chunker_config: Dict) -> str:
    overlap = chunker_config.get(
        "chunk_overlap", chunker_config.get("overlap", 0))
    relevant = {
        "chunk_size": chunker_config["chunk_size"],
        "overlap": overlap,
        "encoding": chunker_config.get("encoding", "cl100k_base"),
    }
    return hashlib.sha256(json.dumps(relevant, sort_keys=True).encode()).hexdigest()[:8]
```

**该函数只考虑了 `chunk_size`、`overlap`、`encoding` 三个参数，没有考虑：**

1. **`strategy` 字段**：`fixed` vs `semantic` 等不同分块策略
2. **`semantic` 策略的参数**：`similarity_threshold`、`breakpoint_percentile`、`min_chunk_size`

这导致不同分块策略产生相同的 hash，进而：
- 使用相同的 chunks 目录
- 使用相同的向量索引
- 最终产生完全相同的检索结果和指标

### 影响范围

所有涉及分块策略变化的实验都会受到影响：
- `chunking_strategy_comparison` 实验
- 任何使用 `semantic` 分块的变体
- 任何修改分块参数的实验

## 修复计划

### Step 1: 修复 `compute_chunker_config_hash` 函数

修改 [src/meal.py](file:///b:/project/ash-easy-rag/src/meal.py) 中的 `compute_chunker_config_hash` 函数，将所有影响分块结果的参数纳入 hash 计算：

```python
def compute_chunker_config_hash(chunker_config: Dict) -> str:
    overlap = chunker_config.get(
        "chunk_overlap", chunker_config.get("overlap", 0))
    relevant = {
        "strategy": chunker_config.get("strategy", "fixed"),
        "chunk_size": chunker_config["chunk_size"],
        "overlap": overlap,
        "encoding": chunker_config.get("encoding", "cl100k_base"),
    }

    # 如果是 semantic 策略，纳入 semantic 参数
    if chunker_config.get("strategy") == "semantic":
        semantic_config = chunker_config.get("semantic", {})
        relevant["semantic"] = {
            "similarity_threshold": semantic_config.get("similarity_threshold", 0.5),
            "breakpoint_percentile": semantic_config.get("breakpoint_percentile"),
            "min_chunk_size": semantic_config.get("min_chunk_size", 100),
        }

    return hashlib.sha256(json.dumps(relevant, sort_keys=True).encode()).hexdigest()[:8]
```

### Step 2: 更新相关测试

修改 [tests/test_meal.py](file:///b:/project/ash-easy-rag/tests/test_meal.py) 中相关的测试用例，确保：
1. 不同 `strategy` 产生不同的 hash
2. 不同 `semantic` 参数产生不同的 hash
3. 相同配置仍然产生相同的 hash

### Step 3: 清理旧的缓存数据

由于 hash 计算方式改变，需要：
1. 清理 `data/artifacts/chunks/` 目录下的旧 chunks
2. 清理 Qdrant 中使用旧 hash 的 collection
3. 重新运行实验

### Step 4: 验证修复

重新运行 `chunking_strategy_comparison` 实验，验证：
1. 不同变体产生不同的指标
2. 日志显示不同的 collection 名称
3. chunks 目录下生成不同的子目录

## 预期结果

修复后，不同分块策略的实验应该产生明显不同的指标，例如：

| Variant | Expected Hit Rate | Expected MRR | Expected NDCG |
|---------|-------------------|--------------|---------------|
| fixed_512_overlap_0 | ~0.80 | ~0.73 | ~1.86 |
| semantic_threshold_50 | 不同值 | 不同值 | 不同值 |
| semantic_threshold_30 | 不同值 | 不同值 | 不同值 |
| semantic_percentile_25 | 不同值 | 不同值 | 不同值 |

## 风险评估

- **低风险**：修改仅影响 hash 计算，不影响核心逻辑
- **向后兼容**：旧的实验数据可能需要重新生成
- **测试覆盖**：需要确保测试用例覆盖各种分块配置
