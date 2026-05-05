# Web UI 五项改进计划

## 涉及 Issue

| # | Issue ID | 标题 | 类型 |
|---|----------|------|------|
| 1 | BUG-20260428-068-wt1 | 全局灰色遮罩消除 | BUG |
| 2 | FEAT-20260505-004-w0 | 维修工流式输出 | FEAT |
| 3 | FEAT-20260505-002-w0 | PDF 预览自动跳 Tab + 隐藏页面跳转 | FEAT |
| 4 | FEAT-20260505-001-w0 | PDF 搜索 Combobox | FEAT |
| 5 | RF-20260505-003-w0 | User Message 自动换行 | RF |

---

## Issue 1：全局灰色遮罩消除

### 问题

Streamlit 脚本 rerun 时前端会对全页面施加灰色半透明遮罩（"running" 状态）。当前项目所有交互（按钮、下拉框、mermaid 节点点击等）都会触发全局 rerun，导致遮罩频繁出现。

### 方案

**CSS 注入 + `.streamlit/config.toml` 双管齐下**：

1. **创建 `.streamlit/config.toml`**（项目级配置，非全局）：
   ```toml
   [runner]
   fastReruns = true

   [client]
   toolbarMode = "minimal"
   ```
   - `fastReruns = true`：减少遮罩闪烁时间
   - `toolbarMode = "minimal"`：隐藏开发工具栏，减少视觉干扰

2. **在 `app.py` 的 `st.set_page_config` 之后注入 CSS**：
   ```python
   st.html("""
   <style>
   [data-testid="stDecoration"] { display: none !important; }
   .stApp > header { display: none !important; }
   </style>
   """)
   ```
   - `[data-testid="stDecoration"]`：隐藏顶部彩色装饰条
   - `.stApp > header`：隐藏运行状态栏

3. **验证**：启动 `pixi run web`，在各个页面点击交互，确认无灰色遮罩。

### 修改文件

- `app.py`：添加 CSS 注入
- `.streamlit/config.toml`：新建（项目级）

### 注意

- CSS 方案是视觉层面的隐藏，底层 rerun 机制不变
- 长期可考虑 `@st.fragment` 改造，但本次不涉及（改动量大，单独排期）

---

## Issue 2：维修工流式输出

### 问题

当前维修工使用 `agent.invoke()` 同步调用，用户只看到 `st.spinner("维修工思考中...")`，直到 Agent 完成所有循环后才一次性显示最终文本。中间的工具调用、思考过程、状态变化全部不可见。

### 方案

**将 `agent.invoke()` 替换为 `agent.astream(stream_mode="updates")`，逐节点实时渲染中间过程**。

#### 核心改造

1. **将 `maintenance.py` 的 `render_maintenance` 改为 `@st.fragment`**：
   - 维修工 tab 内的交互只重跑 fragment，不触发全局 rerun
   - 移除 fragment 内的 `st.rerun()` 调用

2. **替换 `agent.invoke()` 为 `agent.astream()`**：
   ```python
   async for event in agent.astream(state, config=config, stream_mode="updates"):
       # event = {"agent": {...}} 或 {"tools": {...}} 或 {"approval": {...}}
       # 实时渲染每个节点的输出
   ```

3. **实时渲染策略**：

   | 节点 | 渲染内容 | UI 组件 |
   |------|---------|---------|
   | `agent` | LLM 思考文本 + tool_calls 决策 | `st.status()` 容器，展开显示思考过程 |
   | `tools` | 工具名 + 参数 + 执行结果摘要 | `st.status()` 容器，工具名作为标签 |
   | `approval` | 高风险操作确认请求 | `st.warning()` + 批准/拒绝按钮 |

4. **最终答案折叠**：
   - 侧边栏新增 toggle：**"折叠思考过程"**（默认开启）
   - 当 toggle 开启且最终答案出现时，将所有中间步骤折叠到一个 `st.expander("思考与工具调用过程", expanded=False)` 中
   - 当 toggle 关闭时，所有中间步骤保持展开

5. **初始加载状态**：
   - `_get_compiled_agent()` 是 `@st.cache_resource`，首次加载时会初始化 LLM、checkpointer 等
   - 在调用前显示 `st.status("正在初始化维修工...")` 提示

6. **interrupt 处理**：
   - 流式模式下遇到 `interrupt()` 时，流自然结束
   - 在 fragment 内渲染批准/拒绝按钮，用户点击后通过 `Command(resume=decision)` 恢复

#### 异步兼容

- Streamlit 原生不支持 async，需要用 `asyncio.run()` 或事件循环桥接
- 使用 `asyncio.get_event_loop().run_until_complete()` 包装 `astream` 调用
- 或使用同步的 `agent.stream()` （LangGraph 同样支持同步流式）

**优先使用同步 `agent.stream()`**，避免异步事件循环的复杂性。

### 修改文件

- `src/app_pages/maintenance.py`：核心改造
- `src/app.py`：将维修工 tab 改为 fragment 包装

### 验收标准

- 维修工思考过程中，每一步（LLM 思考、工具调用、工具结果）都实时显示
- 最终答案出现后，中间过程可折叠
- 侧边栏 toggle 控制折叠行为
- interrupt（高风险操作确认）正常工作

---

## Issue 3：PDF 预览自动跳 Tab + 隐藏页面跳转

### 问题

1. 点击预览按钮后，用户需要手动点击 "PDF 预览" tab
2. PDF 预览中的页面跳转控件多余（Edge 内置 PDF 渲染器自带导航）

### 方案

#### 3a. 自动跳 Tab

**JS Hack 方案**：在 `_open_pdf_preview` 回调中设置标志位，页面渲染后注入 JS 自动点击目标 tab。

1. 在 `_open_pdf_preview` 中设置 `st.session_state._switch_to_pdf_tab = True`
2. 在 `app.py` 末尾检查标志位，注入 JS：
   ```python
   if st.session_state.get("_switch_to_pdf_tab"):
       st.html("""
       <script>
       setTimeout(function() {
           var tabs = document.querySelectorAll('[data-testid="stTabs"] button[role="tab"]');
           for (var tab of tabs) {
               if (tab.textContent.includes("PDF")) {
                   tab.click();
                   break;
               }
           }
       }, 200);
       </script>
       """, unsafe_allow_javascript=True)
       st.session_state._switch_to_pdf_tab = False
   ```
3. `setTimeout(200ms)` 确保 DOM 渲染完成后再点击

**风险**：JS 选择器依赖 Streamlit 内部 DOM 结构，版本升级可能失效。但项目已使用 `st.html(unsafe_allow_javascript=True)` 注入 JS（浮动导航按钮），技术栈一致。

#### 3b. 隐藏页面跳转控件

在 `render_pdf_preview` 中，将页面跳转表单和上/下一页按钮用 CSS 隐藏，保留代码以便将来恢复：

```python
st.html("""
<style>
[data-testid="stForm"] { display: none !important; }
/* 保留代码，CSS 隐藏 */
</style>
""")
```

或者更精确地用 `st.expander` 包裹，默认折叠。

### 修改文件

- `src/app_pages/qa_demo.py`：`_open_pdf_preview` 添加标志位
- `src/app_pages/case_analyzer.py`：同上（如有预览入口）
- `src/app.py`：末尾添加 JS 注入逻辑
- `src/app_pages/qa_demo.py`：`render_pdf_preview` 隐藏页面跳转

---

## Issue 4：PDF 搜索 Combobox

### 问题

两处需要 PDF 搜索：
1. QA Demo 侧边栏的 Meal 文件列表（可能有 210+ 个 PDF）
2. Case Analyzer 的 Ground Truth 标注（当前用 text_input + selectbox 两个控件）

### 方案

**引入 `streamlit-searchbox` 第三方组件**，实现一体化 combobox 体验。

#### 新增依赖

```bash
pixi add --pypi streamlit-searchbox
```

- 版本：0.1.24（最新）
- 兼容 Streamlit >=1.35（项目用 1.56，OK）
- 支持 `rerun_scope="fragment"` 配合 fragment 使用

#### 改造点 1：QA Demo Meal 文件搜索

在 `_render_meal_files` 中，将文件列表改为可搜索：

```python
from streamlit_searchbox import st_searchbox

def _search_meal_pdfs(searchterm: str, pdf_files: list) -> list[tuple[str, str]]:
    results = []
    for mf in pdf_files:
        name = Path(mf.path).name
        if not searchterm or searchterm.lower() in name.lower():
            results.append((name, mf.path))
    return results

selected = st_searchbox(
    lambda term: _search_meal_pdfs(term, pdf_files),
    placeholder="搜索 PDF 文件...",
    key=f"meal_pdf_search_{meal_name}",
    default_options=[(Path(mf.path).name, mf.path) for mf in pdf_files[:20]],
)
```

选中后显示预览按钮。

#### 改造点 2：Case Analyzer Ground Truth 标注

替换现有的 `st.text_input` + `st.selectbox` 组合：

```python
selected = st_searchbox(
    lambda term: [p for p in pdf_options if term.lower() in p.lower()] if term else pdf_options[:30],
    placeholder="搜索或选择 PDF...",
    key=f"gt_pdf_{case_id}",
    default_options=pdf_options[:30],
)
```

### 修改文件

- `pixi.toml`：新增 `streamlit-searchbox` 依赖
- `src/app_pages/qa_demo.py`：`_render_meal_files` 改造
- `src/app_pages/case_analyzer.py`：`_render_ground_truth_annotation` 改造

---

## Issue 5：User Message 自动换行

### 问题

`case_analyzer.py` 中 User Message 使用 `st.code()` 渲染，code 块默认不换行，长文本横向溢出。

### 方案

将 `st.code(user_message, language="markdown")` 改为带换行的渲染方式：

```python
st.markdown(
    f'<div style="white-space:pre-wrap;word-break:break-word;'
    f'background:#f0f2f6;padding:12px;border-radius:4px;'
    f'font-family:monospace;font-size:0.85em;">{user_message}</div>',
    unsafe_allow_html=True,
)
```

或更简单地用 `st.text()` + CSS override：

```python
st.html("""
<style>
[data-testid="stCodeBlock"] pre { white-space: pre-wrap !important; word-break: break-word !important; }
</style>
""")
```

**推荐第二种**（CSS override），改动最小且全局生效。

### 修改文件

- `src/app_pages/case_analyzer.py`：添加 CSS 或替换渲染方式

---

## 实施顺序

按依赖关系和风险排序：

1. **Issue 1**（灰色遮罩）→ 最简单，先做，立刻改善体验
2. **Issue 5**（自动换行）→ 最简单，顺手做
3. **Issue 4**（Combobox）→ 需新增依赖，先装包验证兼容性
4. **Issue 3**（跳 Tab + 隐藏跳转）→ JS hack，需要浏览器调试
5. **Issue 2**（维修工流式）→ 最复杂，改动最大，最后做

每完成一个 issue，提交一次 commit + 运行 `pixi run lint` + `pixi run test-unit`。

---

## 依赖变更

| 包 | 操作 | 理由 |
|----|------|------|
| `streamlit-searchbox` | 新增 | PDF 搜索 combobox 组件 |

无其他依赖变更。
