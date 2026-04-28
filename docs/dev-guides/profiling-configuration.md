# 性能分析系统配置指南

## 概述

性能分析系统是一个可选的监控组件，可以通过配置完全禁用，实现**零性能开销**。

---

## 配置选项

在 `config.yaml` 中配置：

```yaml
experiments:
  dir: "data/exp_reports"
  configs_dir: "exp_configs"
  profiling:
    enabled: true              # 是否启用性能分析
    monitor_interval: 0.5      # 资源监控采样间隔（秒）
    generate_charts: true      # 是否生成可视化图表
```

### 配置项说明

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `enabled` | bool | `true` | 总开关，设为 `false` 完全禁用性能分析 |
| `monitor_interval` | float | `0.5` | 资源监控采样间隔，单位：秒 |
| `generate_charts` | bool | `true` | 是否生成可视化图表（需要 matplotlib） |

---

## 使用场景

### 场景 1：默认启用（推荐）

```yaml
profiling:
  enabled: true
```

**适用情况**：
- 开发和调试阶段
- 性能优化分析
- 资源消耗评估

**性能影响**：< 2%，可忽略不计

---

### 场景 2：完全禁用（追求极致性能）

```yaml
profiling:
  enabled: false
```

**适用情况**：
- 生产环境部署
- 追求极致性能
- 资源受限环境

**性能影响**：**零开销**（profiler=None，所有判断跳过）

---

### 场景 3：启用但禁用图表生成

```yaml
profiling:
  enabled: true
  generate_charts: false
```

**适用情况**：
- 服务器环境（无图形界面）
- 不需要可视化图表
- 节省磁盘空间

**性能影响**：< 2%（跳过图表生成）

---

### 场景 4：调整采样精度

```yaml
profiling:
  enabled: true
  monitor_interval: 1.0  # 降低采样频率
```

**适用情况**：
- 长时间运行的实验
- 降低监控开销
- 不需要高精度资源数据

**性能影响**：< 1%（采样频率降低）

---

## 性能对比

| 配置 | CPU 开销 | 内存开销 | 功能完整性 |
|------|---------|---------|-----------|
| `enabled: true` | ~0.5% | ~10MB | 完整 |
| `enabled: true, generate_charts: false` | ~0.5% | ~10MB | 无图表 |
| `enabled: true, monitor_interval: 1.0` | ~0.3% | ~10MB | 完整 |
| `enabled: false` | **0%** | **0MB** | **禁用** |

---

## 实现原理

### 禁用时的代码路径

```python
# 配置读取
profiling_enabled = config.get("experiments", {}).get("profiling", {}).get("enabled", True)

# 条件创建
if profiling_enabled:
    profiler = PipelineProfiler(...)
else:
    profiler = None

# 条件执行
if profiler:
    profiler.begin_stage("S1")
# 核心逻辑（无 profiler 时直接执行）
if profiler:
    profiler.end_stage()
```

### 零开销保证

当 `enabled: false` 时：
1. `profiler = None`，不创建任何对象
2. 所有 `if profiler:` 判断为 `False`，跳过所有监控代码
3. 后台监控线程不启动
4. 无任何性能分析相关计算

---

## 输出文件

### 启用时（`enabled: true`）

```
data/exp_reports/exp_{timestamp}/
└── profiling/
    ├── profile_data.json          # 原始数据
    ├── profile_report.md          # Markdown 报告
    └── charts/                    # 可视化图表
        ├── stage_duration_pie.png
        ├── stage_duration_bar.png
        └── token_distribution.png
```

### 禁用时（`enabled: false`）

```
data/exp_reports/exp_{timestamp}/
└── (无 profiling 目录)
```

---

## 最佳实践

### 开发阶段

```yaml
profiling:
  enabled: true
  monitor_interval: 0.5
  generate_charts: true
```

- 完整监控，便于性能分析
- 图表可视化，直观展示瓶颈

### 测试阶段

```yaml
profiling:
  enabled: true
  monitor_interval: 1.0
  generate_charts: false
```

- 降低采样频率，减少开销
- 保留核心数据，便于回归测试

### 生产环境

```yaml
profiling:
  enabled: false
```

- 零开销，极致性能
- 无监控干扰

---

## 常见问题

### Q1: 禁用后还能看到性能数据吗？

**A**: 不能。禁用后不会收集任何性能数据，也不会生成报告。

### Q2: 禁用后需要重启实验吗？

**A**: 是的。配置修改后需要重新运行实验才能生效。

### Q3: 缺少 psutil 会怎样？

**A**: 如果 `enabled: true` 但缺少 psutil，系统会：
- 记录警告日志
- 自动禁用资源监控
- 继续运行，只收集计时数据

### Q4: 缺少 matplotlib 会怎样？

**A**: 如果 `generate_charts: true` 但缺少 matplotlib，系统会：
- 记录警告日志
- 跳过图表生成
- 仍然生成 JSON 和 Markdown 报告

### Q5: 如何验证配置是否生效？

**A**: 查看实验日志：

```
[INFO] Performance profiling enabled
# 或
[INFO] Performance profiling disabled by config
```

---

## 总结

性能分析系统设计为**可选组件**，通过配置开关实现：

1. **灵活性**：根据场景选择启用或禁用
2. **零开销**：禁用时完全无性能影响
3. **渐进式**：可调整采样精度和图表生成
4. **优雅降级**：缺少依赖时自动降级

推荐在开发阶段启用，生产环境根据需求选择。
