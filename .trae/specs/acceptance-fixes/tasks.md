# Tasks

- [x] Task 1: 修复多轮对话上下文重复（P0）
  - [x] 1.1 修改 `qa_demo.py`：将 `build_chat_history` 调用移到 `messages.append` 之前（第 609 行和第 627 行交换顺序）
  - [x] 1.2 确认 `interactive_qa.py` 无同样问题（已验证顺序正确，无需修改）
  - [x] 1.3 编写/补充测试：验证 `build_chat_history` 不包含当前用户消息

- [x] Task 2: Case Analyzer 支持所有 Case 类型（P0）
  - [x] 2.1 将 `_cached_list_bad_cases()` 替换为 `_cached_list_all_cases()`，调用 `list_cases(case_type=None)`
  - [x] 2.2 修改 Case 列表选项格式：添加 `[BAD]`/`[GOOD]` 前缀
  - [x] 2.3 修改空列表提示文案为"暂无 Case 记录。在问答页面标记 Badcase 或 Goodcase 后，这里会显示。"
  - [x] 2.4 修改页面标题 `st.title("🔍 Bad Case 深度分析")` → `st.title("🔍 Case 深度分析")`
  - [x] 2.5 修改 `app.py` Tab 名称 `"🔍 Bad Case 分析"` → `"🔍 Case 分析"`

- [x] Task 3: Ground Truth PDF 模糊搜索 + 排序（P1）
  - [x] 3.1 PDF 列表按文件名字母升序排序（`sorted(pdf_options)`）
  - [x] 3.2 添加 `st.text_input` 关键词过滤输入框
  - [x] 3.3 实现不区分大小写的子串匹配过滤逻辑
  - [x] 3.4 过滤结果用 `st.selectbox` 展示，无匹配时显示提示

- [x] Task 4: 修复 Streamlit 废弃 API（P1）
  - [x] 4.1 `case_analyzer.py:189`：`use_container_width=True` → `width="stretch"`

- [x] Task 5: 测试 + Lint + 提交
  - [x] 5.1 运行 `pixi run test` 确保所有测试通过
  - [x] 5.2 运行 `pixi run ruff check` 确保无 lint 错误
  - [x] 5.3 原子提交

# Task Dependencies

- Task 2 和 Task 3 可并行（修改 `case_analyzer.py` 的不同区域）
- Task 1 独立于其他 Task
- Task 4 独立于其他 Task
- Task 5 依赖 Task 1-4 全部完成
