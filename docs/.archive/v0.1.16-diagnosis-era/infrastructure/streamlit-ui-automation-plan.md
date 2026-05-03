# Streamlit UI 自动化三层策略规划

## 背景

当前项目 Streamlit 应用（`src/app.py`）有 3 个 Tab：问答演示、系统信息、PDF 预览（条件显示）。
后端有 39 个测试文件，但 **0 个 UI 测试**。所有 GUI 验证完全依赖人工手动操作。

目标：建立三层递进的自动化体系，让"左点点右点点检查 error"由机器完成，
UX 优化有人工发现+自动守护，新功能迁移在测试保护下安全推进。

---

## 三层策略总览

```
┌──────────────────────────────────────────────────────────────┐
│  Layer 3: 新功能开发 (人 + 机器协作)                           │
│  CLI → GUI 迁移，每迁一个就补一层 Layer 1 测试                  │
│  交付物：新 Tab/组件 + 对应冒烟测试                              │
├──────────────────────────────────────────────────────────────┤
│  Layer 2: UX 优化 (人主导，机器守护)                            │
│  人工体验 → 记录问题 → 写自动化回归测试 → 修 bug                │
│  交付物：UX 修复 + 回归测试用例                                  │
├──────────────────────────────────────────────────────────────┤
│  Layer 1: 冒烟测试 (机器主导，人只看报告)  ← 本次重点实施         │
│  AppTest 自动遍历所有 GUI 功能 → 检查 exception/error           │
│  交付物：test_app_smoke.py + conftest UI fixtures              │
└──────────────────────────────────────────────────────────────┘
```

---

## Layer 1：冒烟测试 — 详细实现计划

### 1.1 目标

- 每次改代码后，`pixi run test-unit` 自动验证 GUI 不崩
- 覆盖所有现有 Tab 的交互路径
- 检查标准：`assert not app.exception`（等价于"日志里有没有 error"）

### 1.2 技术选型：Streamlit AppTest

| 考量 | 决策 |
|------|------|
| 框架 | `streamlit.testing.v1.AppTest`（Streamlit 内置，无需额外依赖） |
| Mock 策略 | Mock 外部依赖（Qdrant、LLM API、PDF 文件），测试只验证 UI 不崩 |
| 测试 marker | `@pytest.mark.unit`（纯内存运行，无外部依赖） |
| 运行命令 | `pixi run test-unit`（融入现有三层测试体系） |

### 1.3 需要覆盖的交互路径

基于对 `src/app_pages/qa_demo.py` 的分析，现有 GUI 交互路径如下：

#### 问答演示 Tab（核心，交互最多）

| # | 交互路径 | 涉及组件 | 验证点 |
|---|---------|---------|--------|
| 1 | 页面加载 | `st.title`, `st.markdown` | 无 exception |
| 2 | 侧边栏 Meal 选择器 | `st.selectbox["meal_select"]` | 无 exception，选项包含"(无 Meal)"/"+ 新建 Meal" |
| 3 | 选择已有 Meal | `st.selectbox` 切换 | 无 exception，Meal 文件列表渲染 |
| 4 | 选择"(无 Meal)" | `st.selectbox` 切换 | 无 exception |
| 5 | 选择"+ 新建 Meal" | `st.selectbox` 切换 | 新建表单出现 |
| 6 | 新建 Meal - 填写名称 | `st.text_input["new_meal_name"]` | 无 exception |
| 7 | 新建 Meal - 切换采样方式 | `st.selectbox["sample_mode"]` | 对应输入控件出现 |
| 8 | 新建 Meal - 点击创建 | `st.button["create_meal_btn"]` | Mock 成功时无 exception |
| 9 | 检索策略选择 | `st.selectbox["retrieval_method"]` | 无 exception |
| 10 | Top-K 滑块 | `st.slider["top_k"]` | 无 exception |
| 11 | 启用 Reranker | `st.checkbox["use_reranker"]` | 无 exception |
| 12 | 启用查询改写 | `st.checkbox["use_query_rewrite"]` | 改写策略下拉出现 |
| 13 | 改写策略选择 | `st.selectbox["query_rewrite_strategy"]` | 无 exception |
| 14 | 清空对话 | `st.button["clear_btn"]` | 无 exception，messages 清空 |
| 15 | 聊天输入 | `st.chat_input["chat_input_widget"]` | Mock pipeline.query 后无 exception |
| 16 | 聊天输入 - BM25 错误 | pipeline.query 抛 BM25 异常 | error 消息包含"BM25" |
| 17 | 聊天输入 - Reranker 错误 | pipeline.query 抛 reranker 异常 | error 消息包含"Reranker" |

#### 系统信息 Tab（静态展示）

| # | 交互路径 | 验证点 |
|---|---------|--------|
| 1 | 页面渲染 | 无 exception，包含标题"系统信息" |
| 2 | Mermaid 图表渲染 | 无 exception（st.iframe 不崩溃） |

#### PDF 预览 Tab（条件显示）

| # | 交互路径 | 验证点 |
|---|---------|--------|
| 1 | 无 PDF 时不显示 | tab_names 不含"PDF 预览" |
| 2 | 设置 PDF 路径后显示 | session_state 设 `_pdf_preview_path` 后 Tab 出现 |
| 3 | 关闭 PDF 预览 | 点击关闭按钮，session_state 清除 |

### 1.4 实现步骤

#### Step 1: 创建 UI 测试 conftest fixtures

文件：`tests/conftest_ui.py`（独立文件，避免污染现有 conftest）

提供以下 fixtures：

- **`mock_config`**：Mock `load_config()` 返回最小配置字典
- **`mock_meal_manager`**：Mock `MealManager`，返回预设 Meal 列表
- **`mock_pipeline`**：Mock `RAGPipeline`，`query()` 返回预设结果
- **`mock_pdf_server`**：Mock `PdfServer`，避免启动真实 HTTP 服务器
- **`app`**：加载 `src/app.py` 并运行，注入所有 mock

#### Step 2: 创建冒烟测试文件

文件：`tests/test_app_smoke.py`

结构：

```
test_app_smoke.py
├── TestAppLoad
│   ├── test_app_loads_no_exception          # 应用加载不崩
│   └── test_tab_count                       # Tab 数量正确
├── TestQADemoTab
│   ├── test_title_renders                   # 标题渲染
│   ├── test_sidebar_meal_selector           # Meal 选择器存在
│   ├── test_select_existing_meal            # 选择已有 Meal
│   ├── test_select_no_meal                  # 选择"(无 Meal)"
│   ├── test_select_new_meal_form            # 新建 Meal 表单出现
│   ├── test_new_meal_sample_mode_switch     # 采样方式切换
│   ├── test_retrieval_method_selector       # 检索策略选择
│   ├── test_top_k_slider                    # Top-K 滑块
│   ├── test_reranker_checkbox               # Reranker 复选框
│   ├── test_query_rewrite_checkbox          # 查询改写复选框
│   ├── test_query_rewrite_strategy          # 改写策略下拉
│   ├── test_clear_conversation              # 清空对话
│   ├── test_chat_input_send                 # 发送消息
│   ├── test_chat_input_bm25_error           # BM25 错误处理
│   └── test_chat_input_reranker_error       # Reranker 错误处理
├── TestAboutTab
│   ├── test_about_renders                   # 系统信息页渲染
│   └── test_about_contains_tech_stack       # 包含技术栈信息
└── TestPDFPreviewTab
    ├── test_no_pdf_no_tab                   # 无 PDF 时无 Tab
    ├── test_pdf_tab_appears_with_path       # 有 PDF 时 Tab 出现
    └── test_close_pdf_preview               # 关闭 PDF 预览
```

#### Step 3: 注册 pytest marker

在 `pyproject.toml` 的 `[tool.pytest.ini_options].markers` 中添加：

```toml
"ui: marks tests for Streamlit AppTest UI smoke tests",
```

#### Step 4: 添加 pixi 测试命令

在 `pixi.toml` 的 `[tasks]` 中添加：

```toml
[tasks.test-ui]
cmd = "pytest tests/test_app_smoke.py -m \"ui\" --tb=short -q --durations=5"
```

同时修改 `test` 命令，将 UI 测试纳入标准测试（排除 integration 和 slow，但包含 ui）。

#### Step 5: Mock 策略细节

需要 mock 的模块和函数：

| 模块 | 函数/类 | Mock 方式 |
|------|---------|----------|
| `src.utils` | `load_config()` | 返回最小配置 dict |
| `src.utils` | `setup_logger()` | no-op |
| `src.app_pages.qa_demo` | `get_pipeline()` | 返回 Mock RAGPipeline |
| `src.app_pages.qa_demo` | `get_meals()` | 返回预设 Meal 列表 |
| `src.app_pages.qa_demo` | `create_new_meal()` | 返回 Mock Meal |
| `src.app_pages.qa_demo` | `_ensure_pdf_server()` | 返回 Mock PdfServer |
| `src.app_pages.qa_demo` | `_get_pdf_page_count()` | 返回固定页数 |
| `src.app_pages.qa_demo` | `count_pdf_pages()` | 返回固定页数 |

Mock 的 RAGPipeline.query() 返回值：

```python
{
    "answer": "ROE（Return on Equity）是股东权益回报率...",
    "sources": ["annual_reports/2023/company_a/report.pdf"],
    "scores": [0.95],
    "contexts": ["ROE 是衡量公司盈利能力的重要指标..."],
    "chunk_ids": ["chunk_001"],
    "token_usage": {
        "input_tokens": 500,
        "output_tokens": 200,
        "total_tokens": 700,
    },
}
```

### 1.5 已知风险与应对

| 风险 | 影响 | 应对 |
|------|------|------|
| `st.iframe` 在 AppTest 中支持有限 | about.py 的 Mermaid 图可能无法测试 | 先跳过 iframe 内容测试，只验证页面不崩 |
| `st.chat_input` 在 AppTest 中可能不支持 `set_value` | 无法测试发送消息 | 使用 `chat_input[0].set_value()` 或降级为只验证组件存在 |
| `@st.cache_resource` 缓存干扰 | 测试间状态泄漏 | 每个测试前清理缓存或使用独立 AppTest 实例 |
| `st.html` (原 `components.html`) 在 AppTest 中的行为 | 滚动导航按钮测试 | 只验证不崩，不验证 JS 行为 |
| `st.rerun()` 在 AppTest 中的行为 | 某些交互触发 rerun 后状态可能不一致 | 使用 `at.run()` 重新运行而非依赖 rerun |

### 1.6 验收标准

- [ ] `pixi run test-ui` 全部通过
- [ ] `pixi run test-unit` 包含 UI 冒烟测试且全部通过
- [ ] 覆盖 3 个 Tab 的所有交互路径（至少 20 个测试用例）
- [ ] Mock 策略清晰，不依赖外部服务
- [ ] 测试运行时间 < 30 秒

---

## Layer 2：UX 优化 — 规划

### 目标

人工体验发现的问题，修完后有自动化回归守护，不再回退。

### 工作流程

```
手动体验 → 发现 UX 问题 → 写失败测试(Red) → 修 bug(Green) → 提交
```

### 测试组织

UX 回归测试放在 `tests/test_app_ux.py`，标记 `@pytest.mark.ui`。

### 典型 UX 问题及对应测试模式

| UX 问题类型 | 测试模式 |
|------------|---------|
| 状态残留（切换 Meal 后旧数据还在） | 切换后断言 session_state 或 UI 值 |
| 边界条件（空输入、超长输入） | 触发边界输入，断言无 exception |
| 一致性（配置变更后结果应变化） | 修改配置后断言 pipeline.query 收到不同参数 |
| 错误提示不友好 | 触发错误后断言 error 消息包含预期文案 |

### 触发节奏

- 每个版本发布前，花 15-30 分钟手动体验
- 每发现一个 bug，先写测试再修
- 持续积累，守护网越来越厚

---

## Layer 3：新功能开发 — 规划

### 目标

将 CLI 功能逐步迁移到 GUI，每迁一个就有测试守护。

### 迁移优先级

| 优先级 | 功能 | CLI 入口 | 预计新增 Tab/区域 |
|--------|------|---------|-----------------|
| 🥇 P0 | 索引构建 | `--build-index` / `--rebuild` | 侧边栏"索引管理"区域 |
| 🥈 P1 | Meal 完整管理 | `--delete-meal` / `--rename-meal` / `--copy-meal` 等 | 侧边栏 Meal 管理扩展 |
| 🥉 P2 | 实验运行与对比 | `pixi run exp` | 新 Tab"实验" |
| P3 | 测试集管线 | `pixi run testset` | 新 Tab"测试集" |
| P4 | 实验报告可视化 | `eval/visualize.py` | 实验 Tab 内嵌 |
| P5 | Issue/产物管理 | `pixi run issue` / `artifact_cli` | 低优先级 |

### 每个功能的迁移流程（TDD）

```
1. 写 AppTest 测试 (Red)
   - "新 Tab 应该存在"
   - "点击构建按钮不应报错"
   - "构建完成后应显示成功消息"

2. 实现 GUI 功能 (Green)
   - 新增 Tab / 组件
   - 调用已有 CLI 逻辑（src/ 下模块），不新写业务逻辑

3. 测试通过，提交
   - 新功能 + 测试一起提交
   - 守护网自动扩大
```

### 架构原则

- **GUI 是薄壳**：只做展示和交互，核心逻辑复用 `src/` 下已有模块
- **测试先行**：先写"这个 Tab 应该存在"的测试，再写 Tab
- **渐进式**：一次只搬一个功能，搬完测完再搬下一个
- **每个新 Tab 都有对应的 smoke test class**

---

## 时间线建议

| 阶段 | 内容 | 预计耗时 |
|------|------|---------|
| **Phase 1** | Layer 1 冒烟测试搭建 | 1-2 天 |
| **Phase 2** | Layer 2 首轮手动体验 + UX 修复 | 持续进行 |
| **Phase 3** | Layer 3 P0 索引构建迁移 | 2-3 天 |
| **Phase 4** | Layer 3 P1 Meal 管理迁移 | 2-3 天 |
| **Phase 5** | Layer 3 P2 实验运行迁移 | 3-5 天 |

Phase 1 完成后，Phase 2-5 可以并行推进（手动体验 + 功能迁移同时进行）。
