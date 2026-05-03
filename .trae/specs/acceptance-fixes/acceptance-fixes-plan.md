# 验收修复计划：better-badcase-tracker Web UI 问题

## 问题清单与优先级

### 🔴 P0 — 本次必须修复

#### 1. 多轮对话上下文第二次追问丢失
**根因**：`qa_demo.py` 第 609 行先把当前 question append 到 `st.session_state.messages`，然后第 627 行 `build_chat_history(st.session_state.messages)` 会把当前 question 也包含进去。`generator.py` 第 295 行又把当前 question 作为 `user_message` append 一次。导致 Anthropic API 收到的 messages 中当前问题出现两次，被合并逻辑合并为 `{user: "问题\n问题"}`。

**修复**：`build_chat_history` 调用时排除最后一条（刚 append 的当前用户消息），用 `up_to_index=-1` 或在 append 之前构建 chat_history。

具体：在 `qa_demo.py` 中，先构建 chat_history 再 append 当前消息：
```python
# 修复前：
st.session_state.messages.append({"role": "user", "content": question})
chat_history_for_query = build_chat_history(st.session_state.messages)

# 修复后：
chat_history_for_query = build_chat_history(st.session_state.messages)
st.session_state.messages.append({"role": "user", "content": question})
```

#### 2. Case Analyzer 只显示 Bad Case，Good Case 也应可分析
**现状**：`_cached_list_bad_cases()` 只查 `CASE_TYPE_BAD`，bc 转 gc 后就无法分析了。

**修复**：改为同时列出 bad 和 good case，UI 标题改为"🔍 Case 深度分析"，case 列表中用类型标签区分。具体方案：
- 新增 `_cached_list_all_cases()` 函数
- 下拉列表中每项前缀显示 `[BAD]` 或 `[GOOD]`
- 标题改为"🔍 Case 深度分析"

#### 3. Case Analyzer 初始显示"暂无 Bad Case"但历史 case 存在
**根因**：`_cached_list_bad_cases()` 有 `ttl=10` 缓存，且只查 bad 类型。如果本次会话没有新建 badcase，但磁盘上有历史 case，应该显示。

**修复**：与问题 2 合并，改为列出所有 case。同时在列表中用分隔线区分"本次会话"和"历史"case（通过比对 case 创建时间与 session 启动时间）。

### 🟡 P1 — 本次修复

#### 4. Ground Truth PDF 下拉菜单需支持模糊搜索 + 排序
**现状**：`st.selectbox` 只能滚动选择，PDF 列表是 shuffle 后的乱序，几百个 PDF 难以找到目标。

**修复**：
- 将 `st.selectbox` 替换为文本输入 + 过滤列表的组合：
  - `st.text_input` 输入关键词
  - 对 PDF 文件名做模糊匹配（子串匹配即可，无需复杂算法）
  - 匹配结果排序后用 `st.selectbox` 或 `st.radio` 展示
- PDF 列表按文件名排序（不再保持 shuffle 顺序）

#### 5. Streamlit `use_container_width` 废弃警告
**现状**：`case_analyzer.py:189` 使用 `use_container_width=True`，Streamlit 1.56 已标记废弃。

**修复**：替换为 `width="stretch"`。

### 🟢 P2 — 提 Issue，本次不修

#### 6. Ground Truth chunk_ids 匹配不准
**现象**：填了页数后找到的 chunk_ids 为空列表，显示"Ground truth chunk (ids: []) 未出现在检索结果中"。

**原因**：`find_chunks_by_source_page` 的匹配逻辑依赖 chunk 元数据中的 `page_numbers` 字段，但 chunk 元数据可能不包含此字段或页码范围不精确。

**处理**：提 BUG issue。

#### 7. 终端其他 warning
- Qdrant 本地模式大集合 warning（已知，非本次引入）
- 其他零散 warning

**处理**：检查日志，如有新问题提 issue。

---

## 实施步骤

### Step 1: 修复多轮对话上下文丢失（P0）
- 修改 `qa_demo.py`：在 append 当前消息之前构建 chat_history
- 同步检查 `interactive_qa.py` 是否有同样问题
- 添加测试：验证 `build_chat_history` 不包含当前消息

### Step 2: Case Analyzer 支持 Good Case + 历史分隔（P0）
- 修改 `case_analyzer.py`：
  - `_cached_list_bad_cases()` → `_cached_list_all_cases()`
  - 标题改为"🔍 Case 深度分析"
  - 下拉列表前缀 `[BAD]`/`[GOOD]`
  - 添加"本次会话"/"历史"分隔提示
- 修改 `app.py` tab 名称

### Step 3: Ground Truth PDF 模糊搜索 + 排序（P1）
- 修改 `case_analyzer.py` 的 `_render_ground_truth_annotation`：
  - PDF 列表按文件名排序
  - 添加 `st.text_input` 关键词过滤
  - 匹配结果用 `st.selectbox` 展示

### Step 4: 修复 Streamlit 废弃 API（P1）
- `case_analyzer.py:189`：`use_container_width=True` → `width="stretch"`

### Step 5: 提 Issue（P2）
- Ground Truth chunk_ids 匹配不准
- 终端日志中的其他问题

### Step 6: 测试 + 提交
- 运行 `pixi run test`
- 运行 `pixi run ruff check`
- 原子提交
