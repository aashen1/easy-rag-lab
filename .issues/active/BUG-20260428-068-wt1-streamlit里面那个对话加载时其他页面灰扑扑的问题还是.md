---
id: BUG-20260428-068-wt1
title: streamlit里面那个对话加载时其他页面灰扑扑的问题还是没解决
type: BUG
status: todo
priority: medium
labels: []
assignee: null
milestone: null
created_at: '2026-04-28T04:32:07.860110'
updated_at: '2026-04-28T04:32:07.860110'
source: active\BUG-20260428-068-wt1-streamlit里面那个对话加载时其他页面灰扑扑的问题还是.md
legacy_id: null
---
## 问题描述

在等问题出答案的时候，如果切换去另一个“系统信息”页面，它也会像正在加载中一样，整个页面蒙一层灰扑扑的效果，但其实又不是在加载它。这个能调整吗？

## 根因分析

让AI修过一遍，但好像没有修好。以下是当时的分析对话记录，供参考：

好的，这是一个 Streamlit 的经典问题：`st.spinner` 会阻塞整个脚本执行，导致全局出现灰色遮罩，切换到其他 Tab 也受影响。

**根本原因**：`pipeline.query()` 是同步阻塞调用，Streamlit 在等待脚本执行完毕期间，前端会对整个页面施加 "running" 状态的灰色遮罩。

**解决方案**：将查询改为后台线程执行 + `@st.fragment` 轮询结果，这样主脚本快速结束，不会阻塞整个页面。

让我先仔细看一下当前的完整代码，然后实施修改。

toolName: view_files

status: success

filePath: b:\project\ash-easy-rag\src\app_pages\qa_demo.py

现在我完全理解了问题。核心在于第 235 行的 `with st.spinner("检索中...")` —— 它阻塞了整个脚本执行，导致 Streamlit 前端对**全页面**施加灰色遮罩，包括其他 Tab。

**解决方案**：将 `pipeline.query()` 改为后台线程执行，用 `@st.fragment(run_every=...)` 轮询结果。这样主脚本秒级结束，不会阻塞页面。

toolName: todo_write

status: success

Todos updated: 3 items

toolName: Write

status: success

filePath: b:\project\ash-easy-rag\src\app_pages\qa_demo.py

changes: undefined

现在运行 lint 检查确保代码质量：

toolName: run_command

status: success

command: cd b:\project\ash-easy-rag && pixi run ruff-check src/app_pages/qa_demo.py undefined

toolName: run_command

status: success

command: pixi run ruff-check src/app_pages/qa_demo.py undefined

Lint 通过了。让我也验证一下 `app.py` 没有受影响：

toolName: run_command

status: success

command: pixi run ruff-check src/app.py src/app_pages/**init**.py undefined

toolName: todo_write

status: success

Todos updated: 3 items

toolName: run_command

status: success

command: git add src/app_pages/qa_demo.py && git commit -m "fix: use background thread + fragment polling for async query execution

Replace st.spinner blocking call with threading + @st.fragment(run_every=1s)
to prevent grey overlay on all tabs while query is running. Users can now
freely switch to the about tab during query execution." undefined

toolName: todo_write

status: success

Todos updated: 3 items

修改完成！以下是改动要点：

---

### 问题根因

原来的 `with st.spinner("检索中...")` 是**同步阻塞**调用 —— `pipeline.query()` 执行期间，整个 Streamlit 脚本被挂起，前端对**全页面**施加灰色遮罩（"running" 状态），切换到"系统信息"Tab 也一样灰蒙蒙的。

### 解决方案：后台线程 + Fragment 轮询

| 组件 | 作用 |
|------|------|
| `_query_store` | 模块级字典，线程安全地存储查询结果 |
| `_run_query()` | 在后台线程中执行 `pipeline.query()`，结果写入 `_query_store` |
| `_render_query_status()` | `@st.fragment(run_every=1s)`，每秒轮询 `_query_store`，检测到结果后触发 `st.rerun()` |
| `_check_completed_query()` | 主流程中的兜底检查，用户切回 QA Tab 时也能立即拿到结果 |

### 关键改动对比

**之前**（阻塞全页面）：

```python
with st.spinner("检索中..."):
    result = pipeline.query(question)  # 整个脚本卡在这里
```

**之后**（非阻塞）：

```python
# 启动后台线程，主脚本立即结束
thread = threading.Thread(target=_run_query, args=(query_id, question, meal_name), daemon=True)
thread.start()
st.rerun()

# fragment 每秒轮询，不阻塞其他 Tab
@st.fragment(run_every=timedelta(seconds=1))
def _render_query_status():
    entry = _query_store.pop(query_id, None)
    if entry is not None:
        st.session_state.last_result = entry["result"]
        st.rerun()
    else:
        with st.status("🔍 检索中...", expanded=True):
            st.write("正在检索相关文档并生成答案，可切换到其他页面等待...")
```

### 额外改进

- **防重复提交**：查询进行中再次点击"提交"会提示"已有查询正在进行中"
- **清空按钮**：同时清理 `current_query_id` 和 `query_error`
- **加载提示文案**：明确告知用户"可切换到其他页面等待"

你可以用 `pixi run web` 启动试试效果，查询期间切换到"系统信息"页面应该不会再有灰色遮罩了。还有其他改进意见吗？

## 更新记录

- 2026-04-28：创建
