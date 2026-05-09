# pytest-xdist 稳定性问题修复计划

## 问题概述

在 Windows 环境下使用 `-n auto` 参数运行 pytest-xdist 并行测试时出现：
- Worker 进程崩溃（`node down: Not properly terminated`）
- 内存错误（`MemoryError`、`stack overflow`）
- 测试不稳定

根本原因：`-n auto` 在 Windows 上创建过多 worker 进程（与 CPU 逻辑核心数相同），导致资源耗尽。

---

## 实施计划

### 阶段 1：立即修复（推荐方案 1 + 方案 2）

**目标**：限制 worker 数量并添加容错机制

**修改文件**：`pixi.toml`

**具体变更**：

1. **修改 `test-unit` 任务**
   - 当前：`pytest tests/ -m "unit" --tb=short -q --durations=5 -n auto`
   - 修改为：`pytest tests/ -m "unit" --tb=short -q --durations=5 -n 4 --max-worker-restart=2`

2. **修改 `test` 任务**
   - 当前：`pytest tests/ -m "not integration and not slow" --tb=short -q --durations=10 -n auto`
   - 修改为：`pytest tests/ -m "not integration and not slow" --tb=short -q --durations=10 -n 4 --max-worker-restart=2`

3. **修改 `test-all` 任务**
   - 当前：`pytest tests/ --tb=short -q --durations=10 -n auto`
   - 修改为：`pytest tests/ --tb=short -q --durations=10 -n 4 --max-worker-restart=2`

**理由**：
- 固定 4 个 worker：在大多数 Windows 机器上稳定运行，避免过度并行化
- `--max-worker-restart=2`：限制 worker 重启次数，避免无限循环崩溃
- 仍然能获得显著的并行加速效果

---

### 阶段 2：验证测试

**目标**：确保修改后测试稳定运行

**验证步骤**：

1. 运行 `pixi run test-unit`，确认：
   - 无 worker 崩溃
   - 测试正常完成
   - 耗时在预期范围内（~10s）

2. 运行 `pixi run test`，确认：
   - 无内存错误
   - 测试正常完成
   - 耗时在预期范围内（~35s）

3. 运行 `pixi run test-all`，确认：
   - 全量测试稳定完成
   - 耗时在预期范围内（~60s）

---

### 阶段 3：可选优化（如果阶段 1 仍有问题）

**方案 A：添加 `--dist loadfile` 参数**
- 让同一文件的测试在同一个 worker 运行
- 减少文件系统竞争
- 修改示例：`-n 4 --max-worker-restart=2 --dist loadfile`

**方案 B：环境自适应配置（方案 3）**
- 在 `conftest.py` 中添加逻辑
- Windows 上限制为物理核心数（最多 4）
- Linux/macOS 上使用逻辑核心数
- 风险：需要修改测试配置文件，需要额外测试

**方案 C：分离 CI 配置（方案 4）**
- 创建 `test-ci` 任务
- 使用更保守的参数：`-n 2 --max-worker-restart=1`
- 适用于 CI 环境资源受限场景

---

## 风险评估

- **低风险**：阶段 1 只修改命令行参数，不改变测试逻辑
- **中风险**：阶段 3 方案 B 需要修改 conftest.py，需要充分测试
- **无风险**：阶段 3 方案 C 只是新增命令，不影响现有流程

---

## 预期效果

1. **稳定性提升**：消除 worker 崩溃和内存错误
2. **性能保持**：4 个 worker 仍能提供显著加速
3. **跨平台兼容**：在 Windows 上稳定运行
4. **容错能力**：即使个别 worker 出问题也能继续运行

---

## 实施顺序

1. ✅ 读取调研报告，理解问题
2. 📝 修改 `pixi.toml` 中的三个测试任务
3. 🧪 运行测试验证稳定性
4. 📊 观察后续测试运行情况
5. 🔄 如有必要，实施阶段 3 优化方案

---

## 注意事项

- 遵循项目规范，修改后需要提交 commit
- 只 stage 修改的 `pixi.toml` 文件
- 使用 Conventional Commits 格式：`fix(test): limit xdist workers to 4 for Windows stability`
