# 完整流程性能评估方案

## 概述

本文档描述对 `baseline_1kpage` 实验进行全面性能评估的实施方案，从PDF解析到问题回答的完整Pipeline进行系统性测量和分析。

---

## 1. 评估目标

对 1000 页 PDF + 10 个问题的实验规模，实现：
- 环节拆解与精确计时
- 资源消耗评估（CPU、内存、Token）
- 归一化分析（单页耗时、单问题耗时）
- 可视化报告生成

---

## 2. 环节定义

将完整流程拆分为以下 8 个核心环节：

| 环节编号 | 环节名称 | 描述 | 包含操作 |
|---------|---------|------|---------|
| S1 | PDF解析 | 使用 pymupdf4llm 解析PDF为Markdown | `parse_all_pdfs()` |
| S2 | 文档分块 | 固定长度分块策略 | `process_parsed_files()` |
| S3 | 向量嵌入生成 | 文本转换为向量 | `embedder.encode()` 批量调用 |
| S4 | 向量索引构建 | 构建 Qdrant 索引 | `indexer.build_index()` |
| S5 | 测试集生成 | 生成评估问题 | `TestSetGenerator.generate()` |
| S6 | 检索匹配 | 每个问题的 Top-K 检索 | `retriever.retrieve()` × N |
| S7 | 答案生成 | LLM 生成回答 | `generator.generate()` × N |
| S8 | 报告整合 | 指标计算与报告生成 | 所有评估后处理 |

---

## 3. 实施方案

### 3.1 新增模块：`eval/pipeline_profiler.py`

创建性能分析器，使用装饰器模式实现无侵入式计时：

**核心功能**：
1. `@profile_stage` 装饰器：为每个环节自动计时
2. `PipelineProfiler` 类：收集、聚合、输出性能数据
3. 资源监控子模块：采样 CPU/内存使用率

**设计原则**：
- 最小侵入性：通过装饰器包装，不修改现有核心逻辑
- 低开销：使用高精度时钟 `time.perf_counter()`，监控采样间隔 0.5 秒
- 可扩展：支持新增环节和指标

### 3.2 修改现有模块

**文件：`eval/run_experiment.py`**
- 在 `run_experiment()` 函数中集成 `PipelineProfiler`
- 在 `prepare_meal()`、`prepare_test_sets()`、`run_variant_evaluation()` 调用处添加性能埋点
- 在 `evaluate_test_set()` 中为每个问题添加计时

**文件：`src/pipeline.py`**
- 在 `build_index()` 方法中为 S1-S4 环节添加计时装饰器
- 在 `query()` 方法中为 S6-S7 环节添加计时

### 3.3 资源监控实现

**CPU 监控**：
```python
import psutil
process = psutil.Process(os.getpid())
cpu_percent = process.cpu_percent(interval=0)  # 非阻塞采样
```

**内存监控**：
```python
memory_info = process.memory_info()
rss_mb = memory_info.rss / 1024 / 1024  # 驻留集大小
```

**采样策略**：
- 后台线程每 0.5 秒采样一次
- 环节结束后计算平均值、峰值、时间序列

### 3.4 Token 统计增强

利用现有的 `TokenTracker`，增加：
- 按环节分类的 Token 记录
- 区分问题生成阶段（S5）和问答阶段（S7）的 Token 消耗
- 在报告中展示各环节 Token 占比

---

## 4. 评估报告格式

### 4.1 输出结构

```
data/profiling_reports/
└── profile_baseline_1kpage_{timestamp}/
    ├── profile_data.json          # 原始性能数据
    ├── resource_timeline.json     # 资源时间序列数据
    ├── profile_report.md          # 人类可读报告
    └── charts/                    # 可视化图表
        ├── stage_duration_pie.png
        ├── stage_duration_bar.png
        ├── resource_timeline.png
        └── token_distribution.png
```

### 4.2 报告内容模板

```markdown
# Pipeline 性能评估报告

**实验**: baseline_1kpage
**评估时间**: {timestamp}
**数据规模**: {pdf_count} 个PDF, {total_pages} 页, {total_questions} 个问题

## 1. 总体耗时概览

| 指标 | 耗时 | 占比 |
|------|------|------|
| 总耗时 | {total_seconds}s | 100% |
| S1 PDF解析 | {s1_time}s | {s1_pct}% |
| S2 文档分块 | {s2_time}s | {s2_pct}% |
| S3 向量嵌入生成 | {s3_time}s | {s3_pct}% |
| S4 向量索引构建 | {s4_time}s | {s4_pct}% |
| S5 测试集生成 | {s5_time}s | {s5_pct}% |
| S6-S7 问答阶段 | {s67_time}s | {s67_pct}% |
| S8 报告整合 | {s8_time}s | {s8_pct}% |

## 2. 归一化分析

### 2.1 文档处理归一化
- 单页平均耗时: {total_doc_time / 1000}s/页
- 其中：解析 {s1_time/1000}s/页, 分块 {s2_time/1000}s/页

### 2.2 问答处理归一化
- 单问题平均耗时: {total_qa_time / 10}s/问题
- 其中：检索 {s6_time/10}s/问题, 生成 {s7_time/10}s/问题

## 3. 资源消耗

### 3.1 CPU 使用率
- 平均使用率: {avg_cpu}%
- 峰值使用率: {peak_cpu}%
- 核心占用: {cpu_cores}

### 3.2 内存消耗
- 平均内存: {avg_mem}MB
- 峰值内存: {peak_mem}MB
- 内存增长曲线: ![资源趋势](charts/resource_timeline.png)

### 3.3 Token 消耗
| 环节 | 输入 Token | 输出 Token | 总 Token | 占比 |
|------|-----------|-----------|---------|------|
| S5 测试集生成 | {s5_in} | {s5_out} | {s5_total} | {s5_pct}% |
| S7 答案生成 | {s7_in} | {s7_out} | {s7_total} | {s7_pct}% |
| 报告生成 | {rpt_in} | {rpt_out} | {rpt_total} | {rpt_pct}% |
| **总计** | {total_in} | {total_out} | {total_all} | 100% |

## 4. 可视化图表

### 4.1 环节耗时占比
![环节耗时饼图](charts/stage_duration_pie.png)
![环节耗时柱状图](charts/stage_duration_bar.png)

### 4.2 资源趋势
![资源时间线](charts/resource_timeline.png)

### 4.3 Token 分布
![Token分布](charts/token_distribution.png)

## 5. 分析与结论

### 5.1 性能瓶颈
- 最耗时环节: {bottleneck_stage}
- 优化建议: {recommendations}

### 5.2 资源效率
- CPU 效率评估
- 内存使用评估
- Token 成本分析
```

---

## 5. 实施步骤

### Phase 1: 基础设施搭建 (2个文件)
1. 创建 `eval/pipeline_profiler.py` - 性能分析器核心
2. 创建 `exp_configs/baseline/baseline_1kpage.yaml` - 实验配置

### Phase 2: 集成现有系统 (修改3个文件)
3. 修改 `eval/run_experiment.py` - 添加性能埋点
4. 修改 `src/pipeline.py` - 添加环节计时装饰器
5. 修改 `eval/experiment_reporter.py` - 新增性能报告生成方法

### Phase 3: 可视化与测试 (3个文件)
6. 创建 `eval/visualize_profiler.py` - 图表生成器
7. 创建 `tests/test_pipeline_profiler.py` - 单元测试
8. 运行 `pixi run exp baseline_1kpage` 验证

---

## 6. 关键技术决策

### 6.1 计时精度
- 使用 `time.perf_counter()` 而非 `time.time()`
- 精度可达微秒级，系统调用开销 < 1μs

### 6.2 资源监控开销控制
- 采样间隔 0.5 秒，后台守护线程
- 使用 `psutil` 非阻塞 API
- 预估监控开销 < 2%

### 6.3 数据持久化
- 原始数据保存为 JSON，便于后续分析
- 时间序列数据压缩存储
- 支持断点续传（如果实验中断）

### 6.4 兼容性
- 向后兼容：不修改现有实验报告格式
- 性能分析报告独立存放于 `data/profiling_reports/`
- 可独立运行，不影响正常实验流程

---

## 7. 预期交付物

1. ✅ 完整的性能分析工具链
2. ✅ `baseline_1kpage` 实验配置（1000页+10问）
3. ✅ 综合评估报告（JSON + Markdown + 图表）
4. ✅ 单元测试覆盖核心功能
5. ✅ 使用文档（可选，根据用户需要）

---

## 8. 风险评估

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| psutil 依赖缺失 | 资源监控失败 | 优雅降级，记录警告继续运行 |
| 性能开销过大 | 实验时间增加 | 采样间隔可调，默认 0.5s 平衡精度与开销 |
| 图表生成失败 | 报告不完整 | 使用 matplotlib fallback，失败时跳过图表 |
| 内存监控不准确 | 数据偏差 | 使用多种方法交叉验证 |

---

## 9. 后续扩展方向

1. 支持自定义性能指标
2. 支持多进程/分布式性能分析
3. 集成火焰图生成（需要 py-spy）
4. 支持性能回归检测（对比历史实验）
5. 自动生成优化建议报告

---

**状态**: 待审批
**预计开始**: 审批通过后立即实施
**版本**: v0.1.0
