# Tasks

- [x] Task 1: 定义测试集元数据数据模型与 TestSetManager 骨架
  - [x] SubTask 1.1: 在 `src/test_set_manager.py` 中定义 `TestSetMetadata` dataclass（name, meal_id, created_at, updated_at, generation, user_defined, invalid_policy, audit_log, suppress_warnings）
  - [x] SubTask 1.2: 定义 `TestSetManager` 类骨架，包含 `__init__(config)`, `find_by_name()`, `list_test_sets()`, `save_test_set()`, `load_test_set()`, `delete_test_set()` 方法签名
  - [x] SubTask 1.3: 编写 `tests/test_test_set_manager.py` 基础测试（数据模型创建、序列化/反序列化）
  - [x] SubTask 1.4: 实现 `save_test_set()` 和 `load_test_set()`，支持新的 JSON 结构（metadata + quality_metrics + questions）

- [x] Task 2: 实现有效性判定逻辑
  - [x] SubTask 2.1: 实现 `validate_test_set()` 方法，基于 meal_id 快速判定
  - [x] SubTask 2.2: 实现 `_check_questions_validity()` 逐条数据源检查 fallback
  - [x] SubTask 2.3: 编写有效性判定测试（meal_id 一致/不一致、数据源完整/缺失场景）

- [x] Task 3: 修改 ExperimentConfig 适配新格式
  - [x] SubTask 3.1: 修改 `ExperimentConfig.validate()` 支持新格式（含 name 字段时校验 generation 中的 strategy/num_questions）
  - [x] SubTask 3.2: 添加 `on_missing` 值校验（auto / clean_only / strict）
  - [x] SubTask 3.3: 旧格式检测与 deprecation warning 输出
  - [x] SubTask 3.4: 添加辅助方法 `is_new_format(test_set_config)` 和 `get_test_set_name(test_set_config)`
  - [x] SubTask 3.5: 编写 ExperimentConfig 新格式校验测试

- [x] Task 4: 实现 on_missing 三种模式路由逻辑
  - [x] SubTask 4.1: 在 TestSetManager 中实现 `resolve_test_set(meal_name, test_set_config, meal_config)` 方法
  - [x] SubTask 4.2: 实现 `auto` 模式完整流程（查找 → 清洗 → 生成兜底）
  - [x] SubTask 4.3: 实现 `clean_only` 模式完整流程
  - [x] SubTask 4.4: 实现 `strict` 模式完整流程
  - [x] SubTask 4.5: 编写 on_missing 三种模式路由测试

- [x] Task 5: 实现机器生成测试集的自动清洗
  - [x] SubTask 5.1: 实现 `_clean_machine_test_set()` 方法
  - [x] SubTask 5.2: 实现失效问题标记与删除逻辑
  - [x] SubTask 5.3: 实现补充生成逻辑（调用 TestSetGenerator.supplement_document_based_questions）
  - [x] SubTask 5.4: 实现 generation 参数冲突处理（实验配置优先）
  - [x] SubTask 5.5: 实现 audit_log 追加写入
  - [x] SubTask 5.6: 编写机器生成集清洗测试

- [x] Task 6: 实现用户定义测试集的三种 invalid_policy 清洗逻辑
  - [x] SubTask 6.1: 实现 `_clean_user_test_set()` 方法，根据 invalid_policy 分发
  - [x] SubTask 6.2: 实现 `immutable` 策略（仅更新 meal_id 或 ERROR）
  - [x] SubTask 6.3: 实现 `trim` 策略（备份 → 删减 → audit_log → warning）
  - [x] SubTask 6.4: 实现 `regenerate` 策略（备份 → 删减 → 补充 → audit_log → generation 冲突以元数据为准）
  - [x] SubTask 6.5: 实现 archive 备份机制（`<name>.archive.<ISO8601_timestamp>`）
  - [x] SubTask 6.6: 实现 suppress_warnings 读取与 warning 输出逻辑
  - [x] SubTask 6.7: 编写用户定义集三种 invalid_policy 清洗测试

- [x] Task 7: 修改 TestSetGenerator 适配新元数据结构
  - [x] SubTask 7.1: 修改 `generate_document_based_questions()` 输出包含 metadata 的新 JSON 结构
  - [x] SubTask 7.2: 修改 `supplement_document_based_questions()` 更新 metadata（updated_at, audit_log）
  - [x] SubTask 7.3: 修改 `_save_test_set()` 支持按 name 命名
  - [x] SubTask 7.4: 编写 TestSetGenerator 新元数据结构测试

- [x] Task 8: 重构 prepare_test_sets() 使用 TestSetManager
  - [x] SubTask 8.1: 重构 `eval/run_experiment.py` 中的 `prepare_test_sets()` 使用 TestSetManager
  - [x] SubTask 8.2: 新格式走 TestSetManager.resolve_test_set() 路径
  - [x] SubTask 8.3: 旧格式保持原逻辑，触发 deprecation warning
  - [x] SubTask 8.4: 修改 `eval/run_eval.py` 测试集加载支持按名称查找
  - [x] SubTask 8.5: 编写 prepare_test_sets 重构后的集成测试

- [x] Task 9: 更新 CLI 和配置模板
  - [x] SubTask 9.1: 修改 `main.py` 中 `--generate-test-set` 处理器支持 name 参数
  - [x] SubTask 9.2: 更新 `exp_configs/templates/_minimal.yaml` 展示新格式
  - [x] SubTask 9.3: 更新 `exp_configs/templates/_complete.yaml` 展示新格式
  - [x] SubTask 9.4: 编写 CLI 新参数测试

- [x] Task 10: 端到端验证与旧数据迁移兼容
  - [x] SubTask 10.1: 验证旧格式测试集 JSON 可正常加载（向后兼容读取）
  - [x] SubTask 10.2: 验证旧格式实验配置可正常运行并输出 deprecation warning
  - [x] SubTask 10.3: 验证新格式完整流程（配置 → 查找 → 清洗/生成 → 评测）
  - [x] SubTask 10.4: 运行全量测试确保无回归

# Task Dependencies

- [Task 2] depends on [Task 1]
- [Task 4] depends on [Task 2, Task 3]
- [Task 5] depends on [Task 2, Task 7]
- [Task 6] depends on [Task 2, Task 7]
- [Task 7] depends on [Task 1]
- [Task 8] depends on [Task 4, Task 5, Task 6, Task 7]
- [Task 9] depends on [Task 8]
- [Task 10] depends on [Task 8, Task 9]
