# PDF 预览轻量化改造计划

## 问题

`streamlit-pdf-viewer`（pdf.js）将每页 PDF 渲染为 canvas 位图，100 页研报 = 100 个 canvas ≈ 100 MB 像素数据。
而原来 `st.pdf()` 使用浏览器原生 PDF 渲染器（Chrome PDFium），仅渲染可视区域，内存 \~2-4 MB。

## 方案：轻量 HTTP 文件服务 + `st.iframe` + `#page=N` 页码跳转

### 核心思路

1. 启动一个轻量 HTTP 服务器（Python `http.server`，后台守护线程），专门服务 `data/raw/` 下的 PDF 文件
2. 用 `st.iframe(f"http://localhost:{port}/path/to/file.pdf#page={page}")` 嵌入 PDF
3. 浏览器原生 PDF 渲染器负责显示（和 `st.pdf()` 一样轻量：懒加载 + GPU 加速 + 连续滚动）
4. `#page=N` 是 PDF Open Parameters 标准，浏览器原生支持页码跳转

### 为什么不用 `st.components.v1.html`（blob URL 方案）

`st.components.v1.html` 已在 Streamlit 1.56 标记弃用，2026-06-01 后移除，替代品是 `st.iframe`。
而 `st.iframe` 对本地 PDF 文件走 Streamlit 内部 media storage，无法在 URL 上追加 `#page=N`。
所以需要一个独立的 HTTP 服务来提供可控 URL。

### 资源对比

| 方案                         | 100 页研报内存    | 滚动       | 页码跳转  | API 弃用   |
| -------------------------- | ------------ | -------- | ----- | -------- |
| st.pdf()（旧弹窗）              | \~2-4 MB     | ✅ 原生     | ❌     | ✅ 安全     |
| streamlit-pdf-viewer 全量    | \~100 MB     | ✅        | ✅     | ✅ 安全     |
| streamlit-pdf-viewer 单页    | \~1 MB       | ❌        | ✅     | ✅ 安全     |
| components.html + blob URL | \~2-4 MB     | ✅ 原生     | ✅     | ❌ 弃用     |
| **HTTP 服务 + st.iframe**    | **\~2-4 MB** | **✅ 原生** | **✅** | **✅ 安全** |

## 实施步骤

### Step 1: 创建 `src/app_pages/pdf_server.py`

轻量 PDF 文件服务器模块：

```python
@st.cache_resource
def get_pdf_server() -> PdfServer:
    """启动 PDF 文件服务器（仅启动一次）"""
```

* 使用 `http.server.HTTPServer` + `SimpleHTTPRequestHandler`

* 服务目录：`data/raw/`（从 config.yaml 的 `parser.input_dir` 读取）

* 端口：从 8502 开始尝试，最多尝试 10 个端口（8502-8511）

* 运行在守护线程（`daemon=True`），随主进程退出

* 路径安全：`SimpleHTTPRequestHandler` 限制在指定目录内，额外校验 `os.path.realpath()` 防止路径穿越

* 返回 `PdfServer` 对象，包含 `base_url` 属性（如 `http://localhost:8502`）

### Step 2: 修改 `src/app_pages/qa_demo.py`

* 移除 `streamlit_pdf_viewer` 导入和 `pdf_viewer()` 调用

* 移除 `_get_pdf_page_count()` 中的 `@st.cache_data`（改用 `count_pdf_pages` 直接调用）

* 修改 `render_pdf_preview()`：

  * 获取 `PdfServer` 实例

  * 计算相对路径：`pdf_rel_path = os.path.relpath(file_path, raw_dir).replace("\\", "/")`

  * 使用 `st.iframe(f"{server.base_url}/{pdf_rel_path}#page={current_page}", height=800)`

  * 保留现有 UI（标题栏、✕ 关闭、◀ 上一页 / 下一页 ▶、页码跳转表单）

* 移除 `_cleanup_pdf_blob()` 等 blob 相关逻辑

### Step 3: 修改 `src/app.py`

* 无需修改（`st.iframe` 是 Streamlit 原生 API，无需额外导入）

### Step 4: 移除 `streamlit-pdf-viewer` 依赖

* 从 `pixi.toml` 删除 `streamlit-pdf-viewer = ">=0.0.28, <1"`

* 运行 `pixi install` 更新锁文件

### Step 5: 运行 lint + 手动验证

* `pixi run lint`

* `pixi run web` 手动测试：

  * 打开 PDF → 原生渲染，连续滚动

  * 点击下一页/上一页 → 跳转流畅

  * 输入页码跳转 → 正确定位

  * 关闭预览 → Tab 消失

  * 检查浏览器任务管理器 → 内存 \~2-4 MB

### Step 6: 更新 session 文档

* 记录改造过程和技术决策

## 风险与降级

| 风险                       | 应对                                                        |
| ------------------------ | --------------------------------------------------------- |
| 端口 8502-8511 均被占用        | 抛出明确错误提示用户释放端口或修改配置                                       |
| 路径穿越攻击                   | `os.path.realpath()` 校验 + `SimpleHTTPRequestHandler` 内置限制 |
| 浏览器不支持 `#page=N`（Safari） | Chrome/Edge/Firefox 均支持；Safari 降级为打开第 1 页                 |
| 远程访问时 localhost 不可达      | 当前为本地开发工具，暂不处理；后续可改为读取 Streamlit server address           |
| HTTP 服务线程意外退出            | `@st.cache_resource` 保证单例；守护线程随主进程退出                      |



------


成功了！让我把这一趟的完整历程写进 session 文档。

toolName: view_files

status: success

filePath: b:\project\ash-easy-rag\docs\reviews\sessions\streamlit-web-demo-session.md

toolName: edit_file_search_replace

status: success

filePath: b:\project\ash-easy-rag\docs\reviews\sessions\streamlit-web-demo-session.md

changes: undefined

toolName: run_command

status: success

command: cd /b/project/ash-easy-rag && git add docs/reviews/sessions/streamlit-web-demo-session.md && git commit -m "docs: add full five-round iteration log for PDF preview feature" undefined

开发手记已写入 [streamlit-web-demo-session.md](file:///b:/project/ash-easy-rag/docs/reviews/sessions/streamlit-web-demo-session.md) 的 10.3 节。

五轮迭代的教训总结：

| 轮次 | 方案 | 死因 |
|------|------|------|
| 1 | streamlit-pdf-viewer 全量 | 100 MB 内存爆炸 |
| 2 | streamlit-pdf-viewer 单页 | 体验暴跌，不能滚动 |
| 3 | st.iframe + HTTP 服务 | Streamlit 沙箱阻止跨端口加载 |
| 4 | 修复单例 + URL 编码 | 服务器问题修了，但 st.iframe 沙箱仍在 |
| 5 | **st.markdown + 原生 iframe + HTTP 服务** | ✅ 终于通了 |

最关键的发现是 `st.iframe()` 和 `st.markdown(unsafe_allow_html=True)` 生成的 iframe 有本质区别——前者带 `sandbox` 属性，后者不带。这个坑 Streamlit 文档里没写，只能踩出来。
