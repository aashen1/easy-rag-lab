# 测试覆盖增强计划

> 创建时间: 2026-04-24
> 目标: 补充 generator/experiment/run\_experiment 三个模块的边界条件与异常路径测试

## 背景

根据 backlog.md，以下测试待办项尚未处理：

* TEST-001: generator 模块边界条件测试

* TEST-003: experiment 模块边界条件测试

* TEST-004: run\_experiment 模块边界条件测试

* TEST-005: generator 模块异常路径测试

* TEST-006: experiment 模块异常路径测试

* TEST-007: run\_experiment 模块异常路径测试

这些测试不涉及解析链路核心代码，主要是针对已有模块增加测试覆盖率，与主解析链路重构工作完全平行。

## 任务分解

### 任务 1: Generator 边界条件测试

在 `tests/test_generator.py` 中补充：

1. **空上下文列表** (已有 `test_generate_empty_contexts_warning`，但缺少以下场景)：

   * `allow_no_contexts=True` 时的行为验证

   * `None` 作为 contexts 输入

2. **上下文截断边界**：

   * max\_context\_tokens 刚好等于系统提示+查询的 token 数

   * 单个上下文超过限制时的行为

   * 所有上下文都超过限制时的行为

3. **sources 参数边界**：

   * sources 列表比 contexts 长

   * sources 中包含空字符串

   * sources 中包含 None 值

4. **token tracker 为 None 时** (已有测试但未显式验证无 tracker 时不记录)

### 任务 2: Generator 异常路径测试

在 `tests/test_generator.py` 中补充：

1. **API 调用异常** (已有 `test_generate_api_error`，但缺少)：

   * 网络超时异常

   * 认证失败异常

   * 响应格式异常 (message.content 为空)

2. **初始化异常**：

   * API key 无效时的构造函数行为

   * base\_url 无效时的构造函数行为

### 任务 3: Experiment 模块边界条件测试

在 `tests/test_experiment.py` 中补充：

1. **ExperimentConfig 验证**：

   * 空 test\_sets 列表

   * 空 variants 列表

   * evaluation.metrics 为空字典

2. **deep\_merge 边界**：

   * None 值覆盖

   * 列表类型不合并 (已有测试但缺少显式验证)

3. **ExperimentManager**：

   * 空实验目录的 list\_experiments

   * 损坏的 manifest.json

   * 部分文件缺失的 load\_experiment\_result

### 任务 4: Experiment 模块异常路径测试

在 `tests/test_experiment.py` 中补充：

1. **load\_experiment\_config 异常**：

   * 权限不足无法读取文件

   * 超大 YAML 文件处理

2. **ExperimentManager 文件操作异常**：

   * save\_snapshots 时磁盘满

   * save\_variant\_result 时权限错误

### 任务 5: run\_experiment 模块边界条件测试

在 `tests/test_run_experiment.py` 中补充：

1. **compute\_aggregate\_metrics**：

   * 空结果列表

   * 所有结果都有 error

   * 部分结果缺失某些指标

2. **sanitize\_config**：

   * 无 llm\_presets 的配置

   * 多层嵌套的 api\_key

3. **\_collect\_rag\_samples**：

   * 问题文本为空时跳过

   * 单个问题失败不影响其他问题

### 任务 6: run\_experiment 模块异常路径测试

在 `tests/test_run_experiment.py` 中补充：

1. **verify\_experiment\_assets**：

   * 实验目录不存在

   * meal\_snapshot.json 格式错误

   * PDF 文件哈希计算异常

2. **evaluate\_test\_set**：

   * 缺少 exp\_config 参数

   * 缺少 system\_config 参数

   * 评估器创建失败

## 实施步骤

1. 先运行现有测试确保基线通过
2. 按任务 1→6 顺序添加测试
3. 每个任务完成后运行 `pixi run pytest tests/ -m unit` 验证
4. 最终运行完整测试套件确认无回归

## 风险分析

* **冲突风险**: 低。这些测试只涉及测试文件修改，不改动源文件

* **依赖风险**: 无。使用已有的 mock 框架和测试工具

* **时间风险**: 每个任务约 15-30 分钟，总计 1.5-3 小时

## 验收标准

* 新增测试全部通过

* 现有测试无回归

* 覆盖率报告显示出目标模块的改进
