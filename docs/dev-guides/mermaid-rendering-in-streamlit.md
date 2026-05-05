# Streamlit 中 Mermaid 图渲染方案选型

<!-- status: active -->

> 最后更新: 2026-05-05

本文档记录在 Streamlit 中渲染 Mermaid 图的方案选型过程、踩坑记录和最终决策，以备后查。

---

## 背景

项目中有两处需要渲染 Mermaid 图：

1. **RAG 链路流程图**（系统信息 Tab）—— 手写的 `flowchart LR` 语法，无 HTML 标签
2. **Agent 架构图**（维修工 Tab）—— 由 LangGraph 的 `draw_mermaid()` 自动生成，包含 YAML frontmatter、`<p>` 标签、`&nbsp;` 等 Mermaid 11 特有语法

---

## 方案一览

### 方案 A：CDN + `st.iframe`（原方案）

通过 `st.iframe()` 嵌入一段完整 HTML，内含 Mermaid CDN `<script>` 标签和自定义 Diagram/Code 切换按钮。

```python
st.iframe(f"""
    <div class="mermaid">{chart}</div>
    <script>
        loadMermaid('https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js', fallback);
    </script>
""", height=400)
```

**优点：**

- 无需安装额外 Python 依赖
- 代码完全可控，可自定义 UI（Diagram/Code 切换、样式等）
- 理论上支持任意 Mermaid 版本（取决于 CDN 提供的版本）

**缺点：**

- **时序问题**：`startOnLoad: true` 依赖 `DOMContentLoaded` 事件，但 Mermaid JS 是异步加载的，等它加载完时该事件早已触发，导致图永远不会被渲染。必须显式调用 `mermaid.run()`
- **竞态条件**：页面上多个 `st.iframe` 各自独立加载 Mermaid CDN，可能互相干扰。实际表现为"刷新一下 RAG 图出来了 Agent 图没了，再刷新又反过来了"
- **CDN 不稳定**：`cdn.bootcdn.net` 的 Mermaid 11.4.1 已返回 404；`cdn.jsdelivr.net` 在国内访问可能受限
- **iframe 高度问题**：`height="content"` 在 Mermaid 异步渲染完成前就测量高度，导致 iframe 过小图被裁剪；改用固定高度 `height=400` 又不够灵活
- **HTML 标签冲突**：LangGraph 生成的 `<p>__start__</p>` 被浏览器在 Mermaid 解析前当作真实 HTML 元素处理，导致 Mermaid 源码被"吃掉"变成残缺语法。需要通过 JavaScript `textContent` 注入而非直接写入 innerHTML

**结论：** 方案 A 在单图场景下勉强可用，但在多图场景下因竞态条件极不稳定，不推荐。

---

### 方案 B：`streamlit-mermaid`

第三方 Streamlit 组件，封装了 Mermaid 渲染逻辑。

```python
import streamlit_mermaid as stmd
stmd.st_mermaid(code)
```

**优点：**

- 安装简单，一行代码即可渲染
- 无 CDN 依赖，Mermaid JS 打包在组件内部

**缺点：**

- **Mermaid 版本过旧**：使用 Mermaid 10.2.4，不支持 YAML frontmatter（`---config:...---`）等 Mermaid 11 新语法
- **无主题参数**：不支持 `theme="dark"`，在 Streamlit 暗色模式下图表背景为黑色，箭头和文字难以辨认
- **无交互功能**：只能静态渲染，不能捕获节点点击事件
- **高度固定**：默认 `height="250px"`，对复杂图表可能不够

**结论：** 方案 B 适合简单的 Mermaid 图，但不支持 LangGraph 生成的 Mermaid 11 语法，且无暗色主题，不满足项目需求。

---

### 方案 C：`streamlit-mermaid-interactive`（当前方案）

第三方 Streamlit 组件，基于 Mermaid 11，支持主题和交互。

```python
from streamlit_mermaid_interactive import mermaid
mermaid(code, theme="dark", key="unique_key")
```

**优点：**

- **Mermaid 11**：支持最新语法，兼容 LangGraph 生成的代码
- **主题支持**：`theme="dark"` 适配暗色模式，可选 `"neutral"` / `"dark"` / `"forest"` / `"base"`
- **交互功能**：可捕获节点点击事件（`result.get("entity_clicked")`），未来可用于点击节点触发操作
- **稳定**：无 CDN 依赖，无时序/竞态问题
- **key 参数**：支持 Streamlit 的 `key` 机制，多图不冲突

**缺点：**

- 需要额外安装依赖（`pixi add --pypi streamlit-mermaid-interactive`）
- LangGraph 生成的 `<p>` 标签和 `&nbsp;` 仍需手动清理（Mermaid 11 的 `classDef` 语法与 HTML 标签冲突）
- Diagram/Code 切换需要自行实现（当前用 Streamlit 按钮 + session_state 实现）

**结论：** 方案 C 是当前最佳选择，兼顾稳定性、主题适配和 Mermaid 版本兼容性。

---

### 方案 D：预渲染 SVG 缓存（待评估）

将 Mermaid 源码预渲染为 SVG 文件缓存到磁盘，每次加载时对比源码哈希，仅在源码变动时重新渲染。

```python
import hashlib

def _get_cached_svg(chart: str, cache_dir: Path) -> str:
    h = hashlib.sha256(chart.encode()).hexdigest()[:12]
    svg_path = cache_dir / f"mermaid_{h}.svg"
    if svg_path.exists():
        return svg_path.read_text(encoding="utf-8")
    svg = _render_mermaid_to_svg(chart)
    svg_path.write_text(svg, encoding="utf-8")
    return svg

def _render_mermaid_to_svg(chart: str) -> str:
    # 使用 mermaid-cli (mmdc) 或 Python 绑定渲染
    ...
```

**优点：**

- **零前端依赖**：SVG 是纯静态内容，用 `st.image()` 或 `st.html()` 直接展示，无需加载 Mermaid JS
- **渲染 100% 稳定**：不存在 CDN、时序、竞态等任何前端问题
- **加载极快**：SVG 从磁盘读取，毫秒级
- **离线可用**：不依赖任何 CDN 或网络资源
- **版本可控**：SVG 文件可提交到 git，图的变化可追溯

**缺点：**

- **需要渲染引擎**：Mermaid 源码转 SVG 需要 `mmdc`（Mermaid CLI，依赖 Node.js）或 `playwright`/`pyppeteer` 等无头浏览器。这引入了重量级依赖
- **开发体验差**：修改 Mermaid 源码后需要运行渲染命令才能看到效果，不如前端实时渲染直观
- **渲染失败处理**：如果渲染引擎不可用或 Mermaid 语法有误，需要优雅降级。用户提出的"挂 info 框提示当前 diagram 非最新版 code 渲染所得"是合理的降级策略
- **缓存一致性**：需要可靠的哈希机制判断源码是否变动。如果 LangGraph 代码改了但生成的 Mermaid 源码没变（如只改了内部逻辑），哈希不会变，不会触发重新渲染——这其实是正确行为
- **环境要求**：`mmdc` 需要 Node.js + npm，在 pixi 环境中需要额外配置

**可行性评估：**

技术上完全可行，但投入产出比不高：

- 当前方案 C 已经解决了稳定性问题
- SVG 缓存方案的核心价值在于"零前端依赖"和"离线可用"，但项目本身就需要浏览器访问 Streamlit，离线场景意义不大
- 引入 `mmdc` 或无头浏览器的成本（环境配置、CI 适配、维护）远大于收益
- **推荐时机**：如果未来 Mermaid 渲染再次出现不稳定问题，或者需要在无浏览器环境（如 CI 生成报告）中输出图表，再考虑此方案

**实现草案（供参考）：**

```python
import hashlib
from pathlib import Path

def _get_chart_hash(chart: str) -> str:
    return hashlib.sha256(chart.encode()).hexdigest()[:12]

def _render_mermaid_cached(chart: str, key: str = "mermaid"):
    cache_dir = Path("data/mermaid_cache")
    cache_dir.mkdir(parents=True, exist_ok=True)

    h = _get_chart_hash(chart)
    svg_path = cache_dir / f"{key}_{h}.svg"
    hash_path = cache_dir / f"{key}_hash.txt"

    current_hash = hash_path.read_text().strip() if hash_path.exists() else ""

    if svg_path.exists() and current_hash == h:
        st.image(svg_path, output_format="SVG")
    else:
        try:
            svg = _render_via_mmdc(chart)
            svg_path.write_text(svg, encoding="utf-8")
            hash_path.write_text(h, encoding="utf-8")
            st.image(svg_path, output_format="SVG")
        except Exception:
            if svg_path.exists():
                st.image(svg_path, output_format="SVG")
                st.info("⚠️ 当前图表非最新版代码渲染所得，请检查 Mermaid 渲染环境")
            else:
                st.code(chart, language="markdown")
                st.warning("⚠️ Mermaid 渲染失败，已显示源码。请安装 mmdc 或检查语法")
```

---

## 最终决策

| 维度 | 方案 A (CDN+iframe) | 方案 B (streamlit-mermaid) | 方案 C (streamlit-mermaid-interactive) | 方案 D (SVG 缓存) |
|------|---------------------|---------------------------|---------------------------------------|-------------------|
| 稳定性 | ❌ 竞态/时序问题 | ✅ 稳定 | ✅ 稳定 | ✅ 最稳定 |
| Mermaid 版本 | 取决于 CDN | 10.2.4 | 11 | 取决于渲染引擎 |
| 暗色主题 | 需手动配置 | ❌ 不支持 | ✅ `theme="dark"` | SVG 自带样式 |
| LangGraph 兼容 | 需手动清理 | ❌ 不支持 | ✅ 需 `_clean_mermaid_chart()` | 取决于渲染引擎版本 |
| 交互功能 | ❌ | ❌ | ✅ 节点点击 | ❌ |
| 依赖量 | 无 | 轻量 | 轻量 | 重（需 Node.js） |
| 离线可用 | ❌ | ✅ | ✅ | ✅ |

**当前选择：方案 C** —— `streamlit-mermaid-interactive`

**备选：方案 D** —— 若未来方案 C 出现不稳定或需要 CI 环境输出图表时启用

---

## 踩坑记录

### 1. `startOnLoad: true` 不生效

`mermaid.initialize({startOnLoad: true})` 依赖 `DOMContentLoaded` 事件。但 Mermaid JS 通过 CDN 异步加载，加载完成时该事件早已触发，图永远不会被渲染。

**修复：** 改为 `startOnLoad: false` + 显式调用 `mermaid.run()`。

### 2. 多 iframe 竞态条件

两个 `st.iframe` 各自独立加载 Mermaid CDN，可能互相干扰。表现为"刷新一下这个图出来了那个没了"。

**根因：** 每个 iframe 独立执行 `mermaid.initialize()` 和 `mermaid.run()`，但 Mermaid 的全局状态可能被后执行的 `initialize()` 覆盖，导致先初始化的图丢失配置。

**修复：** 使用 Streamlit 组件（方案 C），每个组件实例独立管理自己的 Mermaid 实例。

### 3. `<p>` 标签被浏览器提前解析

LangGraph 生成的 `__start__([<p>__start__</p>])` 在写入 HTML innerHTML 时，浏览器把 `<p>` 当成真实 HTML 元素，Mermaid 拿到的源码变成残缺的 `__start__([])` 。

**修复：** 通过 `_clean_mermaid_chart()` 用正则清理 `<p>` 标签和 `&nbsp;`。

### 4. CDN 404

`cdn.bootcdn.net/ajax/libs/mermaid/11.4.1/mermaid.min.js` 返回 404。

**修复：** 切换到方案 C 后不再依赖 CDN。

---

## 相关文件

| 文件 | 说明 |
|------|------|
| `src/app_pages/about.py` | `_render_mermaid()` 实现、`_clean_mermaid_chart()` 清理函数 |
| `src/app_pages/maintenance.py` | Agent 架构图渲染，调用 `_render_mermaid()` |
| `src/agent/graph.py` | `build_graph()` + `draw_mermaid()` 生成 Mermaid 源码 |
