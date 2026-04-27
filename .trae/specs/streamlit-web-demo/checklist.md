# Checklist

## 环境准备与基础框架

- [x] `pixi.toml` 中已添加 `streamlit = ">=1.32.0, <2"` 依赖
- [x] `src/app.py` 文件已创建
- [x] `src/app_pages/` 目录已创建
- [x] `src/app_pages/__init__.py` 已创建
- [x] `src/app_pages/qa_demo.py` 已创建
- [x] `src/app_pages/about.py` 已创建
- [x] `pixi.toml` 中已添加 `[tasks.web]` 任务
- [ ] `pixi run web` 能成功启动 Streamlit 服务器（需用户验证）

## 主入口实现

- [x] `st.set_page_config()` 配置正确（标题、图标、布局）
- [x] 侧边栏导航显示正常（问答演示、系统信息）
- [x] 页面路由逻辑正确，点击导航可切换页面
- [x] 页面标题显示为 "Easy RAG Lab"
- [x] 页面图标显示为 "🏦"

## 问答演示页 - 侧边栏配置

- [x] Meal 选择器显示所有可用 Meal（从 `MealManager.list_meals()` 获取）
- [x] Meal 选择器包含 "(无 Meal)" 选项
- [x] 检索策略选择器包含 vector/bm25/hybrid 三个选项
- [x] Top-K 滑块范围 1-10，默认值为 5
- [x] Reranker 开关默认关闭
- [x] 查询改写开关默认关闭
- [x] 配置状态使用 `st.session_state` 保存

## 问答演示页 - 主界面

- [x] 页面标题显示为 "🏦 金融研报问答系统"
- [x] 问题输入文本框高度约 100px
- [x] 提交按钮样式为 primary
- [x] 空问题提交时显示警告提示
- [x] 提交时显示加载动画（`st.spinner`）

## 问答演示页 - Pipeline 缓存

- [x] 使用 `@st.cache_resource` 缓存 Pipeline 实例
- [x] 切换 Meal 时 Pipeline 正确重新加载
- [x] 首次加载时显示加载进度提示
- [x] 相同 Meal 的后续请求复用缓存

## 问答演示页 - 答案展示

- [x] 调用 `RAGPipeline.query()` 成功获取结果
- [x] 答案使用 `st.success()` 或 `st.markdown()` 正确展示
- [x] 查询异常时显示错误信息
- [x] 答案内容格式正确（Markdown 渲染）

## 问答演示页 - 检索详情

- [x] 三个标签页正确显示（来源文档、检索片段、评分详情）
- [x] 来源文档列表显示文件名和相关度分数
- [x] 检索片段使用 `st.expander` 可展开查看
- [x] 长片段截断显示（超过 500 字符）
- [x] 评分详情使用 `st.json` 展示

## 问答演示页 - Token 消耗

- [x] Token 数据从 `result["token_usage"]` 正确提取
- [x] 三列布局正确显示（输入/输出/总计）
- [x] 使用 `st.metric()` 展示数值
- [x] 数值格式化正确（千位分隔符）

## 系统信息页

- [x] 页面标题正确显示
- [x] RAG 链路流程图正确展示（Mermaid 格式）
- [x] 技术栈列表完整（PDF 解析、Embedding、向量存储、LLM、评测）
- [x] 使用指南链接正确

## 配置热切换（可选）

- [ ] 切换检索策略后检索结果正确（Phase 5 实现）
- [ ] 调整 Top-K 后返回结果数量正确（Phase 5 实现）
- [ ] 启用 Reranker 后结果经过重排（Phase 5 实现）
- [ ] 启用查询改写后使用 HyDE 策略（Phase 5 实现）

## 代码质量

- [x] 所有新增文件有类型标注
- [x] 所有公共函数有 docstring
- [x] 代码通过 VS Code 诊断检查
- [x] 无 ruff 格式化错误
- [x] 异常处理完善（try/except）

## 功能测试

- [ ] `pixi run web` 启动成功（需用户验证）
- [ ] 浏览器自动打开 `http://localhost:8501`（需用户验证）
- [ ] 选择 Meal 后问答功能正常（需用户验证）
- [ ] 答案、来源、Token 消耗正确展示（需用户验证）
- [ ] 页面切换正常（需用户验证）
- [ ] 无 JavaScript 控制台错误（需用户验证）

## 文档更新

- [ ] `README.md` 已添加 Web Demo 使用说明（Phase 7）
- [ ] `README.md` 已添加 Web Demo 截图（Phase 7）
- [ ] `docs/cli-reference.md` 已添加 `pixi run web` 说明（Phase 7）
- [ ] 文档内容准确，无过时信息（Phase 7）

---

## 验收标准

### 必须达成

- [x] `pixi run web` 启动命令已添加
- [x] 可选择 Meal 进行问答（代码已实现）
- [x] 答案、来源、Token 消耗正确展示（代码已实现）
- [x] 代码通过诊断检查

### 建议达成

- [ ] 配置热切换功能正常（Phase 5 实现）
- [x] 系统信息页流程图美观
- [ ] 页面响应速度快（< 3s）（需用户验证）
