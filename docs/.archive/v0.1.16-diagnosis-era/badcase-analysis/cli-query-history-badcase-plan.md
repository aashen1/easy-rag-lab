# Plan: CLI 单行问答历史记录 & Badcase/Goodcase 收集功能

## 需求概述

将 Web 模式的 Badcase/Goodcase 收集功能迁移到 CLI 单行问答（`--query`）模式。核心思路：

1. 每次 `--query` 执行后，自动将问答记录存入一个**环形历史缓冲区**（持久化到磁盘）
2. 提供 CLI 子命令 `history list` 列出最近 N 条问答摘要
3. 提供 CLI 子命令 `history save <id> --type bad|good` 将指定历史记录录入为 badcase/goodcase
4. 历史记录条数上限可在 `config.yaml` 中配置，超出自动淘汰最旧记录
5. **去重逻辑**：同一条历史记录不能重复录入为同类型的 case
6. **类型转换逻辑**：已录入为 badcase 的记录可以转为 goodcase（删除原 badcase，新建 goodcase），反之亦然

## 现有代码分析

| 组件 | 文件 | 说明 |
|------|------|------|
| Case 核心 | `src/case_collector.py` | `save_case()`, `list_cases()`, `load_case()` — 5 文件落盘 |
| Web 去重 | `src/app_pages/qa_demo.py:173-207` | `_do_save_case()` — 会话级去重（`msg["saved_case_type"]`） |
| CLI 交互 | `main.py:820-922` | `_interactive_qa()` — `/badcase` `/goodcase` 命令，无去重 |
| CLI 单查 | `main.py:279-281` | `--query` 执行一次即退出，无历史、无 case 收集 |
| 配置 | `config.yaml` | 无 history 相关配置项 |

### 关键发现

- Web 去重是**会话级**的（`st.session_state`），页面刷新后丢失
- CLI 交互模式**无去重**，每次 `/badcase` 都会新建一个 case 目录
- **不存在** badcase→goodcase 转换功能（Web 端也只是允许同时保存两种类型，并非转换）
- `case_collector.py` 中没有删除 case 的函数

## 实现方案

### Step 1: 新建 `src/query_history.py` — 查询历史管理器

**职责**：管理 CLI 单行问答的历史记录环形缓冲区

**存储结构**：`data/query_history/history.json`

```json
[
  {
    "id": "qh_001",
    "timestamp": "2026-05-03T14:30:00",
    "question": "茅台营收增长率是多少？",
    "answer_preview": "根据2024年年报...",
    "meal_name": "all",
    "llm_preset": "default",
    "saved_case_type": null,
    "query_result_path": "data/query_history/qh_001_result.json",
    "config_overrides": {}
  }
]
```

**核心 API**：

```python
class QueryHistory:
    def __init__(self, max_entries: int = 10):
        """初始化历史管理器，max_entries 从 config 读取"""

    def add(self, question, result, meal_name, llm_preset, config_overrides) -> str:
        """添加一条记录，返回记录 ID。超出上限时自动淘汰最旧记录。"""

    def list_recent(self, limit: int | None = None) -> list[dict]:
        """列出最近 N 条记录摘要（不含完整 result，仅 preview）"""

    def get(self, record_id: str) -> dict | None:
        """获取指定 ID 的完整记录（含 query_result）"""

    def mark_saved(self, record_id: str, case_type: str) -> None:
        """标记该记录已保存为某类型 case"""

    def check_saved(self, record_id: str) -> str | None:
        """检查该记录已保存的 case 类型，返回 'bad'/'good'/None"""

    def _evict_oldest(self) -> None:
        """淘汰最旧记录，删除对应的 _result.json 文件"""
```

**设计要点**：
- `history.json` 存摘要列表，每条完整 `query_result` 单独存为 `data/query_history/qh_{id}_result.json`，避免大文件
- ID 格式：`qh_{4位序号}`（如 `qh_0001`），简洁易输入
- `saved_case_type` 字段实现**持久化级去重**（比 Web 的会话级去重更强）
- 淘汰时同时删除对应的 `_result.json` 文件

### Step 2: 在 `config.yaml` 中添加配置项

```yaml
# 查询历史配置
query_history:
  max_entries: 10        # 保留最近 N 条单行问答记录
  dir: "data/query_history"  # 历史记录存储目录
```

### Step 3: 扩展 `src/case_collector.py` — 增加删除和转换功能

新增函数：

```python
def delete_case(case_id: str) -> None:
    """删除指定 case 目录（移入 .trashbin/）"""

def convert_case(source_case_id: str, target_type: str) -> Path:
    """将一个 case 从 bad→good 或 good→bad 转换。
    1. 加载原 case 全部数据
    2. 以新类型调用 save_case() 创建新 case
    3. 删除原 case 目录
    4. 返回新 case 目录路径
    """

def find_case_by_question(question: str, case_type: str | None = None) -> dict | None:
    """根据问题文本查找已有 case（用于去重检查）"""
```

**去重逻辑**（持久化级，比 Web 更强）：
- 保存前先检查 `query_history` 中该记录的 `saved_case_type`
- 如果已保存为**同类型** → 拒绝，提示"已标记为 XXX，无需重复保存"
- 如果已保存为**不同类型** → 执行转换：删除旧 case，创建新 case，更新 `saved_case_type`
- 如果未保存过 → 正常保存，更新 `saved_case_type`

### Step 4: 修改 `main.py` — 集成历史记录和 case 命令

#### 4a: `--query` 执行后自动记录历史

在 `main.py:279-281` 的 `--query` 处理逻辑中，查询完成后自动调用 `QueryHistory.add()`：

```python
if args.query:
    result = pipeline.query(args.query)
    _print_query_result(result)
    # 新增：自动记录到历史
    history = QueryHistory(max_entries=config.get("query_history", {}).get("max_entries", 10))
    record_id = history.add(
        question=args.query,
        result=result,
        meal_name=resolved_meal,
        llm_preset=args.llm_preset,
        config_overrides={},
    )
    print(f"📝 已记录到历史 (ID: {record_id})")
```

#### 4b: 新增 CLI 子命令

在 argparse 中新增 `--history` 参数组：

```
--history list [--limit N]          列出最近 N 条问答记录
--history save <id> --type bad|good 将指定历史记录保存为 badcase/goodcase
--history show <id>                 显示指定历史记录详情
```

由于 argparse 不太方便做子命令，采用如下方式：

```bash
pixi run python main.py --history-list [--limit 5]
pixi run python main.py --history-save qh_0001 --case-type bad
pixi run python main.py --history-show qh_0001
```

#### 4c: `--history-list` 输出格式

```
📝 最近 5 条问答记录：
──────────────────────────────────────────────────
ID        时间                 问题预览                    状态
qh_0005   05-03 14:30:00      茅台营收增长率是多少？       🚨 bad
qh_0004   05-03 14:25:00      五粮液毛利率变化趋势？       ✅ good
qh_0003   05-03 14:20:00      泸州老窖渠道改革进展？       —
qh_0002   05-03 14:15:00      山西汾酒产品结构分析？       —
qh_0001   05-03 14:10:00      食品饮料行业估值水平？       —
──────────────────────────────────────────────────
使用 --history-save <id> --case-type bad|good 保存为 case
```

#### 4d: `--history-save` 去重和转换逻辑

```
$ pixi run python main.py --history-save qh_0005 --case-type bad
⚠️ 该记录已标记为 Badcase，无需重复保存

$ pixi run python main.py --history-save qh_0005 --case-type good
✅ 已将 Badcase 转换为 Goodcase: gc_20260503_143500_a1b2c3
   原 Badcase (bc_20260503_143000_a1b2c3) 已删除

$ pixi run python main.py --history-save qh_0003 --case-type bad
🚨 Badcase 已保存: bc_20260503_144000_d4e5f6
```

### Step 5: 同步增强 CLI 交互模式（`_interactive_qa`）

现有的 `/badcase` `/goodcase` 命令也需要加入去重和转换逻辑：

- 维护一个内存字典 `saved_types: dict[str, str]`（question_hash → case_type）
- 保存前检查去重
- 支持 `/goodcase` 转换已保存的 badcase（删除旧的，创建新的）

### Step 6: 编写测试

- `tests/test_query_history.py`：测试 `QueryHistory` 的增删查、环形淘汰、去重标记
- `tests/test_case_collector.py`：新增 `delete_case`、`convert_case`、`find_case_by_question` 的测试
- 集成测试：`--history-list`、`--history-save` 的端到端流程

## 文件变更清单

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `src/query_history.py` | **新建** | 查询历史管理器 |
| `src/case_collector.py` | 修改 | 新增 `delete_case`、`convert_case`、`find_case_by_question` |
| `main.py` | 修改 | 集成历史记录、新增 `--history-*` 参数 |
| `config.yaml` | 修改 | 新增 `query_history` 配置节 |
| `tests/test_query_history.py` | **新建** | QueryHistory 单元测试 |
| `tests/test_case_collector.py` | 修改 | 新增函数的测试 |

## 实现顺序

1. `config.yaml` — 添加 `query_history` 配置节
2. `src/query_history.py` — 实现查询历史管理器 + 测试
3. `src/case_collector.py` — 扩展删除/转换/查找功能 + 测试
4. `main.py` — 集成历史记录到 `--query` 流程
5. `main.py` — 添加 `--history-*` CLI 命令
6. `main.py` — 增强 `_interactive_qa` 的去重/转换逻辑
7. 端到端验证
