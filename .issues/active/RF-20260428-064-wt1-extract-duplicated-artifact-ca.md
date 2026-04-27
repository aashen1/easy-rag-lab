---
id: RF-20260428-064-wt1
title: extract-duplicated-artifact-cache-construction-code
type: RF
status: todo
priority: medium
labels:
- refactor
- DRY
assignee: null
milestone: null
created_at: '2026-04-28T03:45:34.390376'
updated_at: '2026-04-28T03:45:34.390376'
source: active\RF-20260428-064-wt1-extract-duplicated-artifact-ca.md
legacy_id: null
---
## 重构目标

提取重复的 ArtifactCache 构建代码为统一的工厂方法或上下文对象，消除 DRY 违规。

## 问题分析

以下代码模式在项目中至少出现了 5 次：

```python
from src.meal import ArtifactCache
artifacts_config = merged_config.get("artifacts", {})
artifacts_dir = Path(artifacts_config.get("dir", "data/artifacts"))
raw_dir = Path(merged_config.get("parser", {}).get("input_dir", "data/raw"))
cache = ArtifactCache(artifacts_dir, raw_dir)
```

出现位置：
- `src/pipeline.py` L200-L213（build_index 方法内）
- `eval/run_experiment.py` L729-L732（prepare_variant_chunks 函数内）
- `eval/run_experiment.py` L819-L822（prepare_index_for_variant 函数内）
- `eval/run_experiment.py` L1729-L1734（run_variant_evaluation 函数内）
- `src/meal.py` MealManager.__init__（L811-L814）

每次修改 artifacts 配置结构时，需要同步修改 5 处代码。

## 重构范围

涉及 `src/pipeline.py`、`eval/run_experiment.py`、`src/meal.py`

## 重构步骤

1. 在 `src/meal/cache.py`（或 `src/meal.py` 拆分后）中新增工厂函数：
   ```python
   def create_artifact_cache(config: dict[str, Any]) -> ArtifactCache:
       artifacts_config = config.get("artifacts", {})
       artifacts_dir = Path(artifacts_config.get("dir", "data/artifacts"))
       raw_dir = Path(config.get("parser", {}).get("input_dir", "data/raw"))
       return ArtifactCache(artifacts_dir, raw_dir)
   ```
2. 替换所有 5 处重复代码为 `cache = create_artifact_cache(config)`
3. 运行全量测试确保行为不变

## 验收标准

- `create_artifact_cache` 调用点覆盖所有原重复位置
- 所有现有测试通过
- artifacts 配置结构变更只需修改一处

## 更新记录

- 2026-04-28：创建
