# Case 自动收集功能实现计划（Badcase + Goodcase）

## 目标

在 Streamlit Web UI 中，当用户发现某次问答结果好或不好时，一键将完整查询上下文落盘为 case（bad/good），确保**全部可追溯、可唯一复现**。CLI 交互模式同步支持 `/badcase` 和 `/goodcase` 命令。

---

## 设计概览

### Case 目录结构

```
data/cases/
└── {case_type}_{YYYYMMDD}_{HHMMSS}_{question_hash[:6]}/
    ├── manifest.json          # 元数据（ID、类型、时间、问题摘要、状态）
    ├── config_snapshot.yaml   # 完整 effective config（脱敏后）
    ├── meal_snapshot.json     # Meal 信息 + PDF SHA256
    ├── query_result.json      # 完整查询结果（含 contexts/scores/sources/chunk_ids/token_usage）
    └── environment.json       # 运行环境信息（OS/Python/关键包版本）
```

其中 `case_type` 为 `bc`（badcase）或 `gc`（goodcase），目录 ID 示例：
- `bc_20260502_143000_a1b2c3` — badcase
- `gc_20260502_150000_d4e5f6` — goodcase

参考实验系统资产包的三层保障（配置可复现 + 数据可复现 + 环境可追溯），但精简为单次查询场景。

### 核心原则

1. **完整可复现**：只凭 case 目录即可重建完全相同的查询条件
2. **脱敏安全**：API Key 自动替换为 `***`（复用 `sanitize_config`）
3. **轻量无侵入**：不修改 pipeline 核心逻辑，只在 UI 层和独立模块中实现
4. **唯一标识**：类型前缀 + 时间戳 + 问题哈希前6位，避免冲突且可读
5. **Goodcase 价值**：回归测试断言、Golden 测试集积累、Few-shot 示例库、A/B 基线对照

---

## 实现步骤

### Step 1: 创建 `src/case_collector.py` — 核心落盘模块

**职责**：case 的创建、序列化、查询

```python
CASE_TYPE_BAD = "bad"
CASE_TYPE_GOOD = "good"
CASE_DIR_PREFIX = {"bad": "bc", "good": "gc"}

def save_case(
    case_type: str,                    # "bad" or "good"
    question: str,
    result: dict[str, Any],
    config_overrides: dict[str, Any],
    base_config: dict[str, Any],
    meal_config: MealConfig | None,
    meal_name: str | None,
) -> Path
    # 1. 生成 case ID: {prefix}_{timestamp}_{question_hash[:6]}
    # 2. 创建目录 data/cases/{case_id}/
    # 3. 写入 manifest.json（ID、case_type、时间、问题前50字、meal名、状态=open）
    # 4. 写入 config_snapshot.yaml（deep_merge(base_config, config_overrides) 后脱敏）
    # 5. 写入 meal_snapshot.json（复用 meal_config 信息，含 PDF SHA256）
    # 6. 写入 query_result.json（完整 result dict）
    # 7. 写入 environment.json（复用 collect_environment_info()）
    # 8. 返回 case 目录路径

def list_cases(case_type: str | None = None) -> list[dict[str, Any]]
    # 扫描 data/cases/ 目录，可选按 case_type 过滤，返回 manifest 摘要列表

def load_case(case_id: str) -> dict[str, Any]
    # 加载指定 case 的全部文件，返回合并字典

def get_cases_dir() -> Path
    # 返回 data/cases/ 路径
```

**关键依赖**：
- `eval.runner.asset_verifier.sanitize_config` — 配置脱敏
- `eval.runner.asset_verifier.collect_environment_info` — 环境采集
- `src.utils.deep_merge` — 配置合并
- `src.meal.compute_file_sha256` — PDF 哈希（已通过 MealConfig 间接获取）

### Step 2: 修改 `src/app_pages/qa_demo.py` — Web UI 集成

**改动点**：

1. **在 `_display_result()` 函数末尾添加两个按钮**：
   - `st.button("🚨 Badcase", key=f"badcase_{msg_index}")`
   - `st.button("✅ Goodcase", key=f"goodcase_{msg_index}")`
   - 两个按钮并排放在一行（`st.columns(2)`）
   - 需要传入 `msg_index` 以区分不同消息的按钮

2. **按钮回调逻辑**：
   - 从 `st.session_state.messages[msg_index]` 获取 result 和 config_overrides
   - 调用 `save_case(case_type, ...)` 落盘
   - 显示 `st.toast()` 确认（如 "🚨 Badcase 已保存" / "✅ Goodcase 已保存"）

3. **存储 config_overrides 到 message dict**：
   - 当前 message 结构为 `{"role": "assistant", "result": result}`
   - 改为 `{"role": "assistant", "result": result, "config_overrides": config_overrides, "meal_name": meal_name}`
   - 这样每条助手消息都自带完整的查询配置，case 收集时无需额外状态

4. **侧边栏添加 case 统计**：
   - 在侧边栏底部显示当前 badcase/goodcase 数量

### Step 3: 修改 `main.py` — CLI 交互模式集成

**改动点**：在 `_interactive_qa()` 中添加 `/badcase` 和 `/goodcase` 命令

- 在 `while True` 循环中，检测用户输入是否为 `/badcase` 或 `/goodcase`
- 保存最近一次查询的 result + config_overrides
- 需要在循环中维护 `last_result` 和 `last_config_overrides` 变量
- CLI 的 config_overrides 较简单（只有 `--llm-preset` 和 `--meal`），但仍需记录 base_config

**交互示例**：
```
💬 You: 中芯国际2024年营业收入是多少？
🤖 Assistant: ...

💬 You: /badcase
🚨 Badcase 已保存: data/cases/bc_20260502_143000_a1b2c3/

💬 You: /goodcase
✅ Goodcase 已保存: data/cases/gc_20260502_150000_d4e5f6/
```

### Step 4: 编写测试 `tests/test_case_collector.py`

- `test_save_case_creates_all_files` — 验证落盘后5个文件全部存在
- `test_save_case_config_sanitized` — 验证 API Key 被脱敏
- `test_save_case_manifest_structure` — 验证 manifest.json 结构完整（含 case_type）
- `test_save_badcase_prefix` — 验证 badcase 目录前缀为 bc_
- `test_save_goodcase_prefix` — 验证 goodcase 目录前缀为 gc_
- `test_list_cases_filter_by_type` — 验证按类型过滤
- `test_load_case` — 验证加载功能
- `test_case_id_uniqueness` — 验证不同问题产生不同 ID

### Step 5: Lint & 验证

- 运行 `pixi run lint` 确保代码质量
- 运行 `pixi run test` 确保现有测试不受影响

---

## 关键设计决策

### Q: 为什么不直接复用实验系统的资产包？
A: 实验系统是批量评估场景（多变体 + 测试集），case 是单次查询场景。结构差异大，强行复用会增加不必要的复杂度。但复用其**子能力**（脱敏、环境采集、哈希计算）。

### Q: 为什么把 config_overrides 存到 message dict？
A: Streamlit 的 session_state 在 rerun 后可能被覆盖或丢失上下文。将 config_overrides 附加到对应消息上是唯一可靠的方式，确保"标记 Case"时能获取当时的完整配置。

### Q: CLI 为什么也能做？
A: 交互模式下维护 `last_result` 变量即可，实现简单。单次查询模式（`--query`）不适合做 case 收集，因为用户看不到结果就无法判断好坏。

### Q: 为什么 goodcase 和 badcase 放同一目录而非分开？
A: 统一 `data/cases/` 便于统一查询、对比分析。通过 `case_type` 字段和目录前缀区分类型，`list_cases(case_type=)` 支持过滤。

### Q: case 状态管理？
A: 初始状态为 `open`，后续可扩展 `resolved`/`wontfix`/`regression` 等状态（通过修改 manifest.json）。当前版本不实现状态流转 UI。

---

## 文件变更清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `src/case_collector.py` | 新建 | 核心落盘模块（bad + good 统一） |
| `src/app_pages/qa_demo.py` | 修改 | 添加 badcase/goodcase 按钮 + message 结构扩展 |
| `main.py` | 修改 | CLI 交互模式添加 `/badcase` `/goodcase` 命令 |
| `tests/test_case_collector.py` | 新建 | 单元测试 |
| `data/cases/` | 运行时创建 | case 存储目录（.gitignore 已覆盖 data/） |
