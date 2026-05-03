# 验收修复 Spec

## Why

Bad Case 深度分析功能已实现，但验收测试发现 5 个需修复的问题：多轮对话上下文重复导致追问丢失、Case Analyzer 只显示 Bad Case 无法分析 Good Case、初始显示"暂无"但历史 case 存在、Ground Truth PDF 下拉不支持模糊搜索、Streamlit 废弃 API 警告。

## What Changes

- 修复 `qa_demo.py` 中 `build_chat_history` 调用顺序，消除多轮对话当前问题重复
- 将 `_cached_list_bad_cases()` 替换为 `_cached_list_all_cases()`，支持 Bad + Good Case
- Case Analyzer 标题和 Tab 名称从"Bad Case 分析"改为"Case 深度分析"
- Case 列表中用 `[BAD]`/`[GOOD]` 前缀区分类型
- Ground Truth PDF 选择改为关键词过滤 + 排序列表
- `use_container_width=True` 替换为 `width="stretch"`

## Impact

- Affected code: `src/app_pages/qa_demo.py`（消息追加顺序）、`src/app_pages/case_analyzer.py`（列表函数、标题、PDF 选择、废弃 API）、`src/app.py`（Tab 名称）
- Affected specs: bad-case-deep-analysis（UI 行为变更）
- 向后兼容: 无破坏性变更，`list_cases(case_type=None)` 已原生支持列出所有类型

---

## ADDED Requirements

### Requirement: Case Analyzer 支持所有 Case 类型

系统 SHALL 在 Case Analyzer 中同时列出 Bad Case 和 Good Case，不再仅限于 Bad Case。

#### Scenario: 列出所有类型 Case
- **WHEN** 用户进入 Case 深度分析 Tab
- **THEN** 展示所有 Bad Case 和 Good Case 列表（按时间倒序）
- **AND** 每条记录前缀显示 `[BAD]` 或 `[GOOD]` 类型标签

#### Scenario: 无任何 Case
- **WHEN** 系统中无任何 Case 记录
- **THEN** 显示"暂无 Case 记录。在问答页面标记 Badcase 或 Goodcase 后，这里会显示。"

### Requirement: Ground Truth PDF 模糊搜索

系统 SHALL 在 Ground Truth 标注界面的 PDF 选择中支持关键词过滤和排序。

#### Scenario: PDF 列表排序
- **WHEN** 展示 PDF 文件列表
- **THEN** 文件名按字母升序排列（不再保持 shuffle 顺序）

#### Scenario: 关键词过滤
- **WHEN** 用户在搜索框中输入关键词
- **THEN** PDF 列表仅显示文件名包含关键词（不区分大小写）的条目
- **AND** 如果无匹配结果，显示"无匹配的 PDF 文件"

#### Scenario: 空关键词
- **WHEN** 搜索框为空
- **THEN** 展示全部 PDF 文件（排序后）

## MODIFIED Requirements

### Requirement: 多轮对话上下文构建顺序

现有 `qa_demo.py` 中先 append 用户消息到 `st.session_state.messages`，再调用 `build_chat_history(st.session_state.messages)`，导致当前问题被包含在 chat_history 中，与 `generator.py` 第 295 行的显式追加形成重复。

修改为：先构建 chat_history，再 append 用户消息。与 `interactive_qa.py` 的正确实现保持一致。

```python
# 修复前（qa_demo.py:609-627）：
st.session_state.messages.append({"role": "user", "content": question})
# ... config_overrides 构建 ...
chat_history_for_query = build_chat_history(st.session_state.messages)

# 修复后：
# ... config_overrides 构建 ...
chat_history_for_query = build_chat_history(st.session_state.messages)
st.session_state.messages.append({"role": "user", "content": question})
```

#### Scenario: 多轮对话第二次追问
- **WHEN** 用户在已有对话历史的基础上进行第二次追问
- **THEN** LLM 收到的 messages 中当前问题仅出现一次
- **AND** 上下文正确包含之前的对话历史

### Requirement: Case Analyzer 标题和 Tab 名称

现有标题为"🔍 Bad Case 深度分析"，Tab 名称为"🔍 Bad Case 分析"。

修改为：标题改为"🔍 Case 深度分析"，Tab 名称改为"🔍 Case 分析"。

### Requirement: Case 列表缓存函数

现有 `_cached_list_bad_cases()` 仅查询 `CASE_TYPE_BAD`。

修改为：`_cached_list_all_cases()` 查询所有类型（`case_type=None`）。

### Requirement: Streamlit 废弃 API 替换

现有 `case_analyzer.py:189` 使用 `use_container_width=True`，Streamlit 1.56 已标记废弃。

修改为：`width="stretch"`。

## REMOVED Requirements

无。
