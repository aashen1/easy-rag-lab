# Streamlit Web Demo 开发手记

<!-- status: active -->

> 创建时间：2026-04-28
> 目的：记录 Streamlit Web Demo 功能的开发过程，方便后续维护和扩展

---

## 一、开发背景

### 1.1 需求来源

项目作为简历展示项目，存在以下问题：
- **缺乏可视化界面**：纯 CLI 工具，面试官/HR 无法直观理解项目价值
- **演示门槛高**：需要本地部署才能体验，无法快速分享
- **实验结果展示困难**：无法直观展示多策略对比效果

### 1.2 目标

- 提供可视化 Web 界面，支持问答演示
- 支持动态创建 Meal
- 展示答案、来源文档、检索片段、Token 消耗
- 状态跨页面保持

---

## 二、技术选型

### 2.1 Streamlit vs Gradio

| 维度 | Streamlit | Gradio |
|------|-----------|--------|
| 定位 | 数据科学应用快速原型 | ML 模型演示/Demo |
| 布局能力 | 灵活（多列、侧边栏、标签页） | 有限 |
| 状态管理 | `st.session_state` | 较弱 |
| 部署 | Streamlit Cloud | Hugging Face Spaces |

**选择 Streamlit** 的原因：
- 布局灵活，适合复杂交互
- 状态管理完善
- 可扩展实验对比功能

### 2.2 页面架构

最终采用 **单页面 + Tabs** 方案：

```python
tab1, tab2 = st.tabs(["💬 问答演示", "📖 系统信息"])

with tab1:
    render_qa_demo()

with tab2:
    render_about()
```

**原因**：`st.navigation` 多页面模式下状态保持不稳定，Tabs 方案更可靠。

---

## 三、文件结构

```
src/
├── app.py                    # Streamlit 主入口
├── app_pages/                # 页面模块
│   ├── __init__.py
│   ├── qa_demo.py            # 问答演示页
│   └── about.py              # 系统信息页
└── ...
```

### 3.1 主入口 `src/app.py`

```python
import os
import sys
import warnings
from pathlib import Path

# 1. 设置项目根目录到 sys.path
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# 2. 抑制 transformers 警告
os.environ["TRANSFORMERS_VERBOSITY"] = "error"
warnings.filterwarnings("ignore", message="Accessing `__path__` from", category=FutureWarning)

# 3. 尽早初始化日志（避免 DEBUG 日志刷屏）
from src.utils import load_config, setup_logger
config = load_config()
setup_logger(config)

# 4. 导入页面模块
from src.app_pages.about import render_about
from src.app_pages.qa_demo import render_qa_demo

import streamlit as st

st.set_page_config(
    page_title="Easy RAG Lab",
    page_icon="🏦",
    layout="wide",
    initial_sidebar_state="expanded",
)

# 5. 使用 Tabs 而非 navigation（状态保持更稳定）
tab1, tab2 = st.tabs(["💬 问答演示", "📖 系统信息"])

with tab1:
    render_qa_demo()

with tab2:
    render_about()
```

### 3.2 问答演示页 `src/app_pages/qa_demo.py`

**核心功能**：
1. Meal 选择器 + 新建 Meal 功能
2. 检索策略配置（vector/bm25/hybrid, Top-K, Reranker, 查询改写）
3. 问答交互
4. 结果展示（答案、来源文档、检索片段、Token 消耗）
5. 状态跨 Tabs 保持

**状态管理**：
```python
def _init_session_state():
    if "meals_cache" not in st.session_state:
        st.session_state.meals_cache = get_meals()
    if "last_result" not in st.session_state:
        st.session_state.last_result = None
    if "saved_question" not in st.session_state:
        st.session_state.saved_question = ""
    if "query_running" not in st.session_state:
        st.session_state.query_running = False
```

**Pipeline 缓存**：
```python
@st.cache_resource
def get_pipeline(meal_name: str | None) -> RAGPipeline:
    return RAGPipeline(config_path="config.yaml", meal_name=meal_name)
```

---

## 四、遇到的问题与解决方案

### 4.1 模块导入错误

**问题**：
```
ModuleNotFoundError: No module named 'src'
```

**原因**：Streamlit 运行时的工作目录不是项目根目录

**解决方案**：在 `app.py` 开头添加项目根目录到 `sys.path`
```python
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))
```

### 4.2 transformers 警告刷屏

**问题**：
```
Accessing `__path__` from `.models.mobilenet_v2.image_processing_pil_mobilenet_v2`
```

**原因**：`transformers` 库内部的弃用警告

**解决方案**：
```python
os.environ["TRANSFORMERS_VERBOSITY"] = "error"
warnings.filterwarnings("ignore", message="Accessing `__path__` from", category=FutureWarning)
```

### 4.3 chunker DEBUG 日志刷屏

**问题**：
```
2026-04-28 00:08:03.552 | DEBUG | src.chunker:chunk_text:287 - Created 3 chunks from text with 1142 tokens
```

**原因**：`setup_logger` 在 Pipeline 初始化时才调用，此时 loguru 使用默认 DEBUG 级别

**解决方案**：
1. 在 `app.py` 开头尽早调用 `setup_logger(config)`
2. 移除 `chunker.py` 中 `chunk_text` 函数内的 DEBUG 日志

### 4.4 页面切换后状态丢失

**问题**：切换到"系统信息"页后，问答结果丢失

**原因**：`st.navigation` 多页面模式下 `st.session_state` 不稳定

**解决方案**：
1. 改用 `st.tabs` 单页面方案
2. 使用独立的 session_state 变量保存状态：
   - `saved_question`：保存问题内容
   - `last_result`：保存查询结果
3. text_area 使用 `saved_question` 作为默认值

### 4.5 Fragment run_every 与 st.rerun() 冲突

**问题**：`@st.fragment(run_every=1s)` 内调用 `st.rerun()` 后，控制台持续输出警告：

```
The fragment with id xxx does not exist anymore - it might have been removed during a preceding full-app rerun.
```

**原因**：`st.rerun()` 触发全应用重跑，销毁 fragment，但 `run_every` 定时器仍持续触发，反复访问已销毁的 fragment

**解决方案**：移除 `@st.fragment(run_every=...)` 异步轮询，改用 `st.spinner()` + 同步调用。详见迭代记录 10.3。

---

## 五、Pixi Task

```toml
# pixi.toml
[tasks.web]
cmd = "streamlit run src/app.py --server.port 8501"
```

启动命令：
```bash
pixi run web
```

---

## 六、后续改进方向

### 6.1 已实现

- [x] 问答演示页
- [x] Meal 选择器
- [x] 新建 Meal 功能
- [x] 检索策略配置
- [x] 结果展示（答案、来源、Token）
- [x] 状态跨 Tabs 保持
- [x] 当前 Meal 文件列表展示（侧边栏 expander）
- [x] PDF 预览弹窗（st.dialog + st.pdf）
- [x] 来源文档可点击预览（检索结果中 📄预览 按钮）

### 6.2 待实现

- [ ] 配置热切换（检索策略、Top-K、Reranker 实时生效）
- [ ] 实验对比页（加载 `data/exp_reports/` 结果，可视化对比）
- [x] PDF 来源预览（点击来源文档可预览 PDF）
- [ ] 历史记录（保存问答历史，支持回溯）
- [ ] Streamlit Cloud 部署

---

## 七、关键代码片段

### 7.1 新建 Meal

```python
def create_new_meal(
    name: str | None,
    sample_mode: str,
    sample_value: int | float,
    seed: int | None,
) -> Any:
    config = load_config()
    manager = MealManager(config)
    sampling_config = SamplingConfig(mode=sample_mode, value=sample_value)
    return manager.create_meal(
        name=name,
        sampling_config=sampling_config,
        seed=seed,
    )
```

### 7.2 状态恢复

```python
# 初始化状态
_init_session_state()

# 恢复问题内容
default_question = st.session_state.saved_question
question = st.text_area(
    "💬 输入问题",
    value=default_question,
    height=100,
    key="question_input_widget",
)

# 提交时保存
if submit_clicked:
    st.session_state.saved_question = question
    # ... 执行查询
    st.session_state.last_result = result

# 渲染结果
if st.session_state.last_result is not None:
    _display_result(st.session_state.last_result)
```

---

## 八、依赖

```toml
# pixi.toml [pypi-dependencies]
streamlit = ">=1.56.0, <2"
plotly = ">=6.7.0, <7"  # 可选，用于图表
```

---

## 九、相关文档

- 用户指南：[docs/guides/operations/streamlit-web-demo.md](../../guides/operations/streamlit-web-demo.md)
- Spec 文件：[.trae/specs/streamlit-web-demo/](../../../../.trae/specs/streamlit-web-demo/)

---

## 十、迭代记录

### 10.1 2026-04-28：Meal 文件列表 + PDF 预览

**需求**：在问答界面中查看当前 Meal 可用的文件名，并支持 PDF 预览。

**技术方案**：

1. **Meal 文件列表**：在侧边栏 Meal 选择器下方，使用 `st.expander` 展示当前 Meal 包含的 PDF 文件名和大小。每个文件旁有 📄 按钮可打开预览。

2. **来源文档可点击**：在检索结果的"来源文档"Tab 中，每个来源文档旁增加 📄预览 按钮。通过 `_source_to_pdf_path()` 函数将 chunk 的 source 路径（如 `company/report.md`）映射回原始 PDF 路径（如 `company/report.pdf`），匹配策略为：先精确匹配替换后缀的路径，再按文件名 stem 模糊匹配。

**新增函数**：

| 函数 | 作用 |
|------|------|
| `_get_raw_dir()` | 从 config 获取 PDF 原始目录路径 |
| `_format_file_size()` | 格式化文件大小（MB/KB/B） |
| `_source_to_pdf_path()` | 将 chunk source 路径映射到 PDF 文件路径 |
| `_open_pdf_preview()` | 设置 session_state 触发 PDF 预览 |
| `_render_meal_files()` | 渲染侧边栏 Meal 文件列表 |

### 10.2 2026-04-28：Tab 式 PDF 预览 + 页码跳转

**需求**：dialog 弹窗预览手感差，改为独立 Tab 页，增加页码跳转和关闭按钮。

**技术方案**：

1. **Tab 式预览**：`app.py` 中根据 `_pdf_preview_path` session state 动态添加第三个 Tab「📄 PDF 预览」。点击预览按钮时设置 session state 并触发 rerun，新 Tab 自动出现。点击 ✕ 关闭按钮清除 state 后 Tab 消失。

2. **PDF 渲染**：使用 `streamlit-pdf-viewer`（基于 pdf.js）替代原生 `st.pdf()`，支持 `scroll_to_page` 页码跳转、`render_text` 文本选择、`show_page_separator` 页面分隔线。

3. **页码跳转**：使用 `st.form` 包裹页码输入和跳转按钮，避免输入时触发不必要的 rerun。点击跳转后更新 `_pdf_preview_page` session state，通过 `key=f"pdf_viewer_p{target_page}"` 强制组件重新渲染到目标页。

4. **总页数**：使用 `count_pdf_pages()`（来自 `src/sampler`）+ `@st.cache_data` 获取并缓存 PDF 总页数。

5. **Toast 提示**：点击预览按钮时弹出 toast，提醒用户切换到「PDF 预览」Tab。

**新增依赖**：

```toml
streamlit-pdf-viewer = ">=0.0.28, <1"
```

**新增/变更函数**：

| 函数 | 作用 |
|------|------|
| `render_pdf_preview()` | PDF 预览 Tab 页面渲染（含页码跳转、关闭按钮） |
| `_get_pdf_page_count()` | 缓存 PDF 总页数 |

**移除函数**：

| 函数 | 原因 |
|------|------|
| `_pdf_preview_dialog()` | dialog 方案已废弃 |

**已知限制**：

- `streamlit-pdf-viewer` 与 Streamlit ≥ 1.41 存在已知兼容性问题（st.dialog 关闭后滚动位置重置），但因已改用 Tab 方案，此问题不影响。
- 页码跳转时组件需重新渲染（通过 key 变化），大 PDF 可能需要几秒加载。

### 10.3 2026-04-28：移除 fragment 轮询，改用同步查询

**问题**：`@st.fragment(run_every=1s)` + `st.rerun()` 导致大量控制台警告：

```
The fragment with id xxx does not exist anymore - it might have been removed during a preceding full-app rerun.
```

**根因**：fragment 内部调用 `st.rerun()` 触发全应用重跑，销毁了 fragment 自身，但 `run_every` 定时器仍在触发，反复尝试访问已销毁的 fragment。

**修复方案**：移除 `@st.fragment(run_every=...)` 异步轮询机制，改用 `st.spinner()` + 同步调用 `pipeline.query()`。对于 Demo 应用，查询期间 UI 短暂冻结完全可以接受。

**移除代码**：

| 代码 | 原因 |
|------|------|
| `_query_store` 全局字典 | 不再需要后台线程通信 |
| `_run_query()` | 不再需要后台线程执行 |
| `_check_completed_query()` | 不再需要轮询检查 |
| `_render_query_status()` (fragment) | 不再需要 fragment 轮询 |
| `import threading, uuid, timedelta` | 不再需要 |
| `query_running` / `current_query_id` session state | 不再需要异步状态追踪 |

**简化后的查询流程**：

```python
if question:
    with st.spinner("🔍 正在检索相关文档并生成答案..."):
        try:
            pipeline = get_pipeline(meal_name)
            result = pipeline.query(question)
            st.session_state.last_result = result
        except Exception as e:
            st.session_state.query_error = str(e)
    st.rerun()
```
