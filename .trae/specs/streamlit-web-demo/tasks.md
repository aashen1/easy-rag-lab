# Tasks

## Phase 1: 环境准备与基础框架

- [ ] Task 1: 添加 Streamlit 依赖
  - [ ] SubTask 1.1: 在 `pixi.toml` 的 `[pypi-dependencies]` 中添加 `streamlit = ">=1.32.0, <2"`
  - [ ] SubTask 1.2: 执行 `pixi install` 安装依赖
  - [ ] SubTask 1.3: 验证 Streamlit 安装成功（`pixi run python -c "import streamlit; print(streamlit.__version__)"`）

- [ ] Task 2: 创建项目结构
  - [ ] SubTask 2.1: 创建 `src/app.py` 主入口文件
  - [ ] SubTask 2.2: 创建 `src/app_pages/` 目录
  - [ ] SubTask 2.3: 创建 `src/app_pages/__init__.py`
  - [ ] SubTask 2.4: 创建 `src/app_pages/qa_demo.py` 问答演示页
  - [ ] SubTask 2.5: 创建 `src/app_pages/about.py` 系统信息页

- [ ] Task 3: 添加 Pixi Task
  - [ ] SubTask 3.1: 在 `pixi.toml` 的 `[tasks]` 中添加 `[tasks.web]`
  - [ ] SubTask 3.2: 配置命令 `cmd = "streamlit run src/app.py --server.port 8501"`
  - [ ] SubTask 3.3: 验证 `pixi run web` 能启动 Streamlit

## Phase 2: 主入口实现

- [ ] Task 4: 实现主入口 `src/app.py`
  - [ ] SubTask 4.1: 配置 `st.set_page_config()` 设置页面标题、图标、布局
  - [ ] SubTask 4.2: 实现侧边栏导航（问答演示、系统信息）
  - [ ] SubTask 4.3: 实现页面路由逻辑
  - [ ] SubTask 4.4: 添加全局样式配置（可选）

## Phase 3: 问答演示页实现

- [ ] Task 5: 实现侧边栏配置面板
  - [ ] SubTask 5.1: 实现 Meal 选择器（下拉菜单，从 `MealManager.list_meals()` 获取列表）
  - [ ] SubTask 5.2: 实现检索策略选择器（vector/bm25/hybrid）
  - [ ] SubTask 5.3: 实现 Top-K 滑块（范围 1-10，默认 5）
  - [ ] SubTask 5.4: 实现 Reranker 开关（Checkbox）
  - [ ] SubTask 5.5: 实现查询改写开关（Checkbox）
  - [ ] SubTask 5.6: 使用 `st.session_state` 保存配置状态

- [ ] Task 6: 实现主界面布局
  - [ ] SubTask 6.1: 添加页面标题和描述
  - [ ] SubTask 6.2: 实现问题输入文本框（`st.text_area`，高度 100px）
  - [ ] SubTask 6.3: 实现提交按钮（`st.button`，type="primary"）
  - [ ] SubTask 6.4: 实现空问题校验（显示警告）

- [ ] Task 7: 实现 Pipeline 缓存机制
  - [ ] SubTask 7.1: 使用 `@st.cache_resource` 实现 Pipeline 缓存
  - [ ] SubTask 7.2: 实现 Meal 切换时的 Pipeline 重新加载
  - [ ] SubTask 7.3: 添加加载进度提示（`st.spinner`）

- [ ] Task 8: 实现答案展示
  - [ ] SubTask 8.1: 调用 `RAGPipeline.query()` 获取结果
  - [ ] SubTask 8.2: 使用 `st.success()` 或 `st.markdown()` 展示答案
  - [ ] SubTask 8.3: 处理查询异常，显示错误信息

- [ ] Task 9: 实现检索详情展示
  - [ ] SubTask 9.1: 创建三个标签页（来源文档、检索片段、评分详情）
  - [ ] SubTask 9.2: 实现来源文档列表（文件名 + 相关度分数）
  - [ ] SubTask 9.3: 实现检索片段展示（可展开的 `st.expander`）
  - [ ] SubTask 9.4: 实现评分详情 JSON 展示（`st.json`）

- [ ] Task 10: 实现 Token 消耗统计
  - [ ] SubTask 10.1: 从 `result["token_usage"]` 提取 Token 数据
  - [ ] SubTask 10.2: 使用 `st.columns()` 创建三列布局
  - [ ] SubTask 10.3: 使用 `st.metric()` 展示输入/输出/总计 Token

## Phase 4: 系统信息页实现

- [ ] Task 11: 实现系统信息页
  - [ ] SubTask 11.1: 添加页面标题
  - [ ] SubTask 11.2: 展示 RAG 链路流程图（使用 Mermaid 或图片）
  - [ ] SubTask 11.3: 展示技术栈列表（PDF 解析、Embedding、向量存储、LLM、评测）
  - [ ] SubTask 11.4: 添加使用指南链接

## Phase 5: 配置热切换（可选）

- [ ] Task 12: 实现检索策略热切换
  - [ ] SubTask 12.1: 检测检索策略变更
  - [ ] SubTask 12.2: 更新 Pipeline 配置或重建 Pipeline
  - [ ] SubTask 12.3: 验证切换后检索结果正确

- [ ] Task 13: 实现 Top-K 热更新
  - [ ] SubTask 13.1: 检测 Top-K 变更
  - [ ] SubTask 13.2: 更新检索参数

- [ ] Task 14: 实现 Reranker/查询改写热开关
  - [ ] SubTask 14.1: 检测开关状态变更
  - [ ] SubTask 14.2: 更新 Pipeline 配置

## Phase 6: 测试与验收

- [ ] Task 15: 功能测试
  - [ ] SubTask 15.1: 测试 `pixi run web` 启动成功
  - [ ] SubTask 15.2: 测试 Meal 选择功能
  - [ ] SubTask 15.3: 测试问答功能（输入问题 → 获取答案）
  - [ ] SubTask 15.4: 测试检索详情展示
  - [ ] SubTask 15.5: 测试 Token 消耗统计
  - [ ] SubTask 15.6: 测试配置切换功能

- [ ] Task 16: 代码质量检查
  - [ ] SubTask 16.1: 运行 `pixi run lint` 检查代码格式
  - [ ] SubTask 16.2: 修复所有 lint 错误
  - [ ] SubTask 16.3: 添加必要的类型标注和 docstring

## Phase 7: 文档更新

- [ ] Task 17: 更新项目文档
  - [ ] SubTask 17.1: 更新 `README.md` 添加 Web Demo 使用说明
  - [ ] SubTask 17.2: 添加 Web Demo 截图
  - [ ] SubTask 17.3: 更新 `docs/cli-reference.md` 添加 `pixi run web` 说明

---

# Task Dependencies

```
Task 1 → Task 2 → Task 3 → Task 4
                    ↓
                Task 5 → Task 6 → Task 7 → Task 8 → Task 9 → Task 10
                    ↓
                Task 11
                    ↓
                Task 12 → Task 13 → Task 14 (可选)
                    ↓
                Task 15 → Task 16 → Task 17
```

---

# Estimated Time

| Phase | 预计时间 |
|-------|---------|
| Phase 1: 环境准备与基础框架 | 0.5 天 |
| Phase 2: 主入口实现 | 0.5 天 |
| Phase 3: 问答演示页实现 | 1 天 |
| Phase 4: 系统信息页实现 | 0.5 天 |
| Phase 5: 配置热切换（可选） | 0.5 天 |
| Phase 6: 测试与验收 | 0.5 天 |
| Phase 7: 文档更新 | 0.5 天 |
| **总计** | **3-4 天** |
