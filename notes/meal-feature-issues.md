# Meal 功能潜在问题记录

> 创建时间：2026-04-16
> 状态：待优化（非阻塞，功能可正常使用）

---

## 1. `random.seed()` 全局随机状态污染

**位置**：`src/meal.py:L265-268`

**代码**：
```python
if seed is None:
    seed = random.randint(0, 2**32 - 1)
random.seed(seed)
```

**问题**：`random.seed(seed)` 影响 Python 全局随机状态，可能在套餐创建后干扰其他模块（如 `sampler.py`、`test_generator.py`）的随机行为。

**影响**：
- 同一进程中连续调用 `create_meal()` 和依赖随机数的其他功能时，可能导致不可预期的抽样结果
- 多线程环境下可能引发竞争条件

**建议修复**：
```python
# 使用局部随机实例，避免全局污染
rng = random.Random(seed)
# 后续使用 rng.randint() 替代 random.randint()
sampled_pdfs = rng.sample(all_pdfs, k)
```

---

## 2. `repair_meal()` 中 `parse_results` 返回值未使用

**位置**：`src/meal.py:L672`

**代码**：
```python
parse_results = parse_all_pdfs(...)
```

**问题**：`parse_results` 变量被赋值但从未被使用，可能导致误解或掩盖潜在问题。

**建议修复**：
- 如果不需要返回值：`parse_all_pdfs(...)` 直接调用
- 如果需要验证解析结果：添加检查逻辑，如 `if not parse_results: raise ValueError(...)`

---

## 3. `TestSetGenerator` 重复创建 `MealManager`

**位置**：`src/test_generator.py:L83, L346`

**代码**：
```python
# L83
meal_manager = MealManager(self.config)
# L346
meal_manager = MealManager(self.config)
```

**问题**：每次调用 `generate_test_set()` 和 `_save_test_set()` 都创建新的 `MealManager` 实例，增加不必要的对象实例化开销。

**建议修复**：
- 将 `MealManager` 作为类属性，在 `__init__` 中创建一次
- 或作为参数传入方法

---

## 4. `_select_chunks_for_multi_hop` 策略只选择 2 个 chunk

**位置**：`src/test_generator.py:L258-272`

**问题**：设计计划中提到"选同一文档中不相邻的 2-3 个 chunk"，但实际实现只选择 2 个 chunk (`[chunks[i], chunks[j]]`)。

**影响**：多跳推理问题的难度上限受限，缺少需要综合 3 段信息的高难度场景。

**建议修复**：
- 增加 3-chunk 组合的采样逻辑
- 可考虑在配置中指定每组的 chunk 数量范围

---

## 5. `eval/run_eval.py` 中变量命名不一致

**位置**：`eval/run_eval.py:L212`

**代码**：
```python
jsonl_files = sorted(test_sets_dir.glob("*.json"))
```

**问题**：变量名 `jsonl_files` 但实际匹配的是 `*.json` 文件，命名不一致，容易引起混淆。

**建议修复**：重命名为 `json_files` 或 `test_set_files`

---

## 6. 缺失开发记录文档

**位置**：`notes/` 目录

**问题**：根据开发规范，每个开发阶段应在 `notes/` 下创建记录文档，但 meal 功能尚无对应的开发记录。

**建议**：补充 `notes/meal-feature-implementation.md`，记录：
- 功能概述
- 设计决策
- 实施步骤
- 遇到的问题与解决思路

---

## 优先级排序

| 优先级 | 问题 | 修复难度 | 影响 |
|-------|------|---------|------|
| 高 | 1. `random.seed()` 全局污染 | 低 | 可能影响随机抽样结果 |
| 中 | 2. `parse_results` 未使用 | 低 | 代码清洁度 |
| 中 | 3. `MealManager` 重复创建 | 低 | 性能优化 |
| 低 | 4. `multi_hop` 缺少 3-chunk | 中 | 功能增强 |
| 低 | 5. 变量命名不一致 | 低 | 代码清洁度 |
| 低 | 6. 缺失开发记录 | 低 | 文档完整性 |
