# Session 专题：Pipeline 性能分析系统与 OCR 对比实验

**日期**: 2026-04-25
**版本基线**: v0.1.8
**分支**: verify-baseline

---

## 概述

本 session 完成了两项核心工作：
1. **从零构建 Pipeline 性能分析（Profiling）系统**，实现 RAG 全流程 8 个环节的精确计时、资源监控、Token 追踪和可视化报告
2. **执行 OCR 对比实验**，量化 OCR 对 PDF 解析性能的影响

---

## 一、Pipeline 性能分析系统

### 1.1 系统架构

创建了以下核心模块：

| 文件 | 功能 |
|------|------|
| `eval/pipeline_profiler.py` | 性能分析器核心：计时、资源监控、累加模式、报告生成 |
| `eval/visualize_profiler.py` | 可视化模块：饼图、柱状图、Token 分布图 |
| `exp_configs/baseline/baseline_1kpage.yaml` | 1000 页 + 10 问题的实验配置 |
| `docs/guides/profiling-configuration.md` | 配置指南文档 |

修改了以下现有模块：

| 文件 | 修改内容 |
|------|---------|
| `eval/run_experiment.py` | 集成 profiler，添加 S1-S8 环节埋点和 Token 报告 |
| `src/pipeline.py` | query() 内添加 S6/S7 埋点，build_index() 内添加 S3/S4 埋点 |
| `config.yaml` | 添加 profiling 配置开关 |

### 1.2 环节定义

| 环节 | 名称 | 计时位置 | 说明 |
|------|------|---------|------|
| S1 | PDF解析 | `prepare_meal()` | 含解析+分块+索引构建（meal 创建为原子操作） |
| S2 | 文档分块 | `prepare_variant_chunks()` | fixed chunking 极快 |
| S3 | 向量嵌入生成 | `prepare_index_for_variant()` → `build_index()` | GPU 加速 |
| S4 | 向量索引构建 | BM25 索引构建 | vector-only 模式不触发 |
| S5 | 测试集生成 | `prepare_test_sets()` | LLM API 调用 |
| S6 | 检索匹配 | `pipeline.query()` 内部 | 每个问题一次，累加 |
| S7 | 答案生成 | `pipeline.query()` 内部 | 每个问题一次，累加 |
| S8 | 报告整合 | 报告生成阶段 | 纯计算 |

### 1.3 关键设计决策

**1. 配置级总开关**

```yaml
experiments:
  profiling:
    enabled: true          # 设为 false 完全禁用，零性能开销
    monitor_interval: 0.5  # 资源监控采样间隔
    generate_charts: true  # 是否生成图表
```

- `enabled: false` 时 profiler=None，所有 `if profiler:` 判断跳过，零开销
- 不需要卸载依赖，通过配置即可控制

**2. 累加模式**

S6/S7 在多问题场景下被多次 begin/end，`PipelineProfiler.end_stage()` 自动累加：
- duration_seconds 累加
- call_count 递增
- CPU/内存取加权平均和峰值
- Token 累加

**3. Token 主动报告**

不再依赖绑定单一 TokenTracker，改为各阶段结束后主动调用 `report_stage_tokens()`：
- S5 结束后报告 `test_generation_tracker` 的 token
- S7 结束后从 `variant_tracker` 中提取 `rag_qa` 类别的 token

**4. 优雅降级**

- psutil 缺失：资源监控自动禁用，仅记录计时
- matplotlib 缺失：图表生成跳过，JSON/Markdown 报告仍生成
- 中文字体缺失：自动 fallback 到 SimHei/Microsoft YaHei

### 1.4 修复的 Bug

| Bug | 根因 | 修复 |
|-----|------|------|
| `ImportError: parse_all_pdfs` | 函数已重命名为 `parse_all_pdfs_unified` | 修正导入名和参数 |
| S3/S4 缺失 | `prepare_index_for_variant()` 未被 profiler 包裹 | 添加 S3/S4 包裹 |
| S6/S7 划分错误 | S6 包含检索+生成+评估，S7 仅含聚合计算 | 在 `pipeline.query()` 内部添加 S6/S7 埋点 |
| Token 全为 0 | profiler 绑定的 tracker 与实际记录 token 的 tracker 不同 | 改用 `report_stage_tokens()` 主动报告 |
| 图表中文方框 | matplotlib 默认字体不支持 CJK | 添加 SimHei/Microsoft YaHei 字体 |
| `AttributeError: get_total_input` | TokenTracker 无此方法 | 改用 `get_total()` 返回 TokenUsage 对象 |

---

## 二、首次 Profiling 结果（OCR 开启）

### 实验参数

- 数据：12 个 PDF，1000 页，2288 chunks
- 问题：10 个
- 配置：chunk_size=512, overlap=0, BAAI/bge-large-zh-v1.5, Qdrant Cosine

### 关键数据

| 环节 | 耗时 | 占比 | 单次耗时 |
|------|------|------|---------|
| S1 PDF解析 | 412.35s | 78.3% | 412.35s |
| S5 测试集生成 | 38.68s | 7.3% | 38.68s |
| S7 答案生成 | 17.96s | 3.4% | 1.80s/问题 |
| S3 向量嵌入 | 0.33s | 0.1% | 0.33s |
| S6 检索匹配 | 0.43s | 0.1% | 0.043s/问题 |
| **总计** | **526.46s** | **100%** | - |

归一化：
- 单页处理耗时：0.4127s/页
- 单问题处理耗时：1.8392s/问题
- 峰值内存：1987.5 MB
- 总 Token：86,210

### 归档位置

- 报告：`docs/reviews/v0.1.8/profiling-baseline-1kpage.md`
- 原始数据：`data/exp_reports/exp_20260425_034425_baseline_1kpage/profiling/`

---

## 三、OCR 对比实验

### 3.1 实验设计

**控制变量**：只改 OCR 开关，保持同一套 PDF 文件。

**缓存安全性验证**：系统的三层缓存隔离机制（data_id → config_hash → index_key）确保不同配置使用独立缓存路径，不存在污染风险：
- OCR 开：parser_hash = `e936d3e3`，解析目录 `parsed_e936d3e3/`
- OCR 关：parser_hash = `6a7f018d`，解析目录 `parsed_6a7f018d/`

**Meal 复用**：创建新 meal `1kpage_no_ocr`，使用相同 seed=42 确保采样同一套 PDF（data_id 相同）。

### 3.2 对比结果

| 指标 | OCR 开 | OCR 关 | 变化 |
|------|--------|--------|------|
| S1 PDF解析 | 412.35s | 151.81s | **-63.2%** |
| 单页耗时 | 0.412s/页 | 0.152s/页 | -63.2% |
| CPU 平均 | 73.3% | 58.3% | -20.5% |
| 内存峰值 | 1907.2 MB | 1547.5 MB | -18.8% |
| Faithfulness | 0.7771 | 0.8143 | **+4.8%** |
| Answer Relevancy | 0.7650 | 0.7680 | +0.4% |

### 3.3 核心发现

1. **OCR 贡献了 63.2% 的解析时间**（260s），关闭后解析速度提升 2.7 倍
2. **OCR 不提升 RAG 质量**：关闭 OCR 后 Faithfulness 反而提升 4.8%，OCR 文本中的识别错误可能引入噪声
3. **S7 答案生成异常**：从 17.96s 飙升至 132.85s（+639.6%），最可能是 LLM API 延迟波动

### 3.4 建议

- 默认关闭 OCR，仅对扫描件按需启用
- 可实现智能 OCR 策略：先检测页面是否有文本层，无文本层时才启用 OCR

### 3.5 归档位置

- 报告：`docs/reviews/v0.1.8/ocr-comparison-report.md`
- OCR 关实验数据：`data/exp_reports/exp_20260425_043733_baseline_1kpage_no_ocr/`

---

## 四、Commit 记录

| Commit | 类型 | 描述 |
|--------|------|------|
| `65b256c` | feat | 添加 Pipeline 性能分析系统 |
| `2a9e957` | docs | 添加性能分析实施方案文档 |
| `a5edfd4` | fix | 修正 parser 导入名 parse_all_pdfs → parse_all_pdfs_unified |
| `de4c6d2` | fix | 修正 profiling 阶段计时和 Token 追踪 |
| `82f0636` | docs | 添加 profiling 修复方案文档 |
| `a5edfd4` | docs | 归档 baseline-1kpage profiling 结果 |
| `6f0a947` | feat | 添加 OCR 对比实验和报告 |

---

## 五、遗留问题与后续方向

### 遗留问题

1. **S1 覆盖范围仍膨胀**：`prepare_meal()` 在 meal 创建时包含解析+分块+索引构建，S1 计时无法精确拆分为纯解析时间。需要在 `create_meal()` 内部添加子阶段埋点。

2. **S7 答案生成时间异常**：OCR 关闭实验中 S7 从 17.96s 飙升至 132.85s，需要排查是否为 LLM API 延迟波动。建议在 `pipeline.query()` 内记录每次调用的精确时间戳。

3. **评估阶段未独立计时**：faithfulness 和 answer_relevancy 的 LLM API 调用时间被计入 S7，但实际属于评估而非生成。需要添加独立的评估阶段计时。

4. **资源监控精度不足**：当前使用 `cpu_percent(interval=0)` 非阻塞采样，精度有限。建议在关键阶段使用 `interval=0.1` 阻塞采样获取更精确的 CPU 数据。

### 后续方向

1. **智能 OCR 策略**：实现页面文本层检测，仅对无文本层的页面启用 OCR
2. **并行 PDF 解析**：多进程解析，充分利用多核 CPU
3. **性能回归检测**：对比历史实验的 profiling 数据，自动检测性能退化
4. **S1 子阶段拆分**：在 `create_meal()` 内部添加解析/分块/索引构建的子阶段计时
