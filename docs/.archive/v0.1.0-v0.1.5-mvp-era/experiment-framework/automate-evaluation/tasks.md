# Tasks

## Phase 1: 核心模块开发

- [x] Task 1: 创建实验配置系统
  - [x] SubTask 1.1: 定义 ExperimentConfig 数据类（src/experiment.py）
  - [x] SubTask 1.2: 实现 load_experiment_config 函数，支持YAML加载和验证
  - [x] SubTask 1.3: 实现 merge_config 函数，支持配置继承和覆盖
  - [x] SubTask 1.4: 编写单元测试（tests/test_experiment.py）

- [x] Task 2: 创建实验管理器
  - [x] SubTask 2.1: 实现 ExperimentManager 类（src/experiment.py）
  - [x] SubTask 2.2: 实现 create_experiment_dir 方法，生成实验目录结构
  - [x] SubTask 2.3: 实现 save_snapshots 方法，保存配置和问题集快照
  - [x] SubTask 2.4: 实现 load_experiment_result 方法，加载已有实验结果
  - [x] SubTask 2.5: 编写单元测试

- [x] Task 3: 创建实验报告生成器（支持两种模式）
  - [x] SubTask 3.1: 创建 eval/experiment_reporter.py
  - [x] SubTask 3.2: 实现 ExperimentReporter 类
  - [x] SubTask 3.3: 实现 generate_markdown_report 方法（主入口）
  - [x] SubTask 3.4: 实现 _generate_template_report 方法（程序模板生成标准报告）
  - [x] SubTask 3.5: 实现 _generate_llm_report 方法（调用LLM撰写报告）
  - [x] SubTask 3.6: 实现各章节生成方法（概述、数据、配置、结果、对比）
  - [x] SubTask 3.7: 设计LLM报告生成Prompt模板
  - [x] SubTask 3.8: 编写单元测试

## Phase 2: 自动化流程实现

- [x] Task 4: 实现自动化评测脚本
  - [x] SubTask 4.1: 创建 eval/run_experiment.py
  - [x] SubTask 4.2: 实现实验主流程函数 run_experiment
  - [x] SubTask 4.3: 实现 prepare_meal 函数，自动创建或加载meal
  - [x] SubTask 4.4: 实现 prepare_test_sets 函数，自动生成或加载问题集
  - [x] SubTask 4.5: 实现 run_variant_evaluation 函数，执行单个变体的评测
  - [x] SubTask 4.6: 实现命令行参数解析（包括 --llm-report 参数）

- [x] Task 5: 实现多变体支持
  - [x] SubTask 5.1: 修改 MealManager，支持基于配置变体创建独立collection
  - [x] SubTask 5.2: 实现 get_or_create_variant_collection 函数
  - [x] SubTask 5.3: 实现变体结果对比和汇总

- [x] Task 6: 实现实验复现功能
  - [x] SubTask 6.1: 实现 reproduce_experiment 函数
  - [x] SubTask 6.2: 实现配置和资产验证逻辑
  - [x] SubTask 6.3: 实现实验对比功能（--compare）

## Phase 3: 配置系统重构

- [x] Task 7: 重构 config.yaml
  - [x] SubTask 7.1: 移除 evaluation 配置段
  - [x] SubTask 7.2: 添加 experiments 配置段（dir: "data/exp_reports", configs_dir: "exp_configs"）
  - [x] SubTask 7.3: 更新 config.yaml 文档注释
  - [x] SubTask 7.4: 更新 src/utils.py 中的 load_config 函数（如有必要）

- [x] Task 8: 创建示例实验配置
  - [x] SubTask 8.1: 创建 exp_configs/ 目录
  - [x] SubTask 8.2: 创建 exp_configs/baseline.yaml 示例配置
  - [x] SubTask 8.3: 创建 exp_configs/chunk_comparison.yaml 示例配置
  - [x] SubTask 8.4: 创建 exp_configs/README.md 说明文档

## Phase 4: 集成与测试

- [x] Task 9: 更新现有评测模块
  - [x] SubTask 9.1: 修改 eval/run_eval.py，支持从实验配置加载参数
  - [x] SubTask 9.2: 确保 run_eval.py 仍可独立使用（向后兼容）
  - [x] SubTask 9.3: 更新相关测试

- [x] Task 10: 端到端测试
  - [x] SubTask 10.1: 创建测试用PDF文件和meal
  - [x] SubTask 10.2: 编写端到端测试脚本，验证完整流程
  - [x] SubTask 10.3: 验证程序模板报告生成的正确性
  - [x] SubTask 10.4: 验证LLM报告生成的正确性
  - [x] SubTask 10.5: 验证实验复现功能

## Phase 5: 文档与示例

- [x] Task 11: 更新项目文档
  - [x] SubTask 11.1: 更新 CLAUDE.md，添加自动化评测说明
  - [x] SubTask 11.2: 创建 notes/experiment_system.md 开发手记
  - [x] SubTask 11.3: 更新 README.md（如有必要）

- [x] Task 12: 创建使用示例
  - [x] SubTask 12.1: 编写快速开始指南
  - [x] SubTask 12.2: 编写常见实验场景示例
  - [x] SubTask 12.3: 编写实验报告解读指南
  - [x] SubTask 12.4: 编写LLM报告模式使用说明

# Task Dependencies

- Task 2 depends on Task 1
- Task 3 depends on Task 1
- Task 4 depends on Task 1, Task 2, Task 3
- Task 5 depends on Task 4
- Task 6 depends on Task 4, Task 5
- Task 9 depends on Task 4
- Task 10 depends on Task 4, Task 5, Task 6, Task 9
- Task 11 depends on Task 10

# Parallelizable Work

以下任务可以并行执行：
- Task 1, Task 3, Task 7, Task 8 可以并行开发
- Task 11 和 Task 12 可以在核心功能完成后并行进行
