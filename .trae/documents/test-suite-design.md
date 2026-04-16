结合你的需求（防破坏、自动化、低成本），我建议你建立以下**三层测试体系**：

#### 1. 快速反馈层：本地 Pre-commit Hook
*   **目标**：拦截低级语法错误和核心逻辑错误。
*   **内容**：
    *   Lint 检查（代码格式）。
    *   **关键单元测试**：只测那些纯 Python 逻辑的复杂函数（如文本清洗、Chunk 切割算法）。
    *   **不包含**：任何网络请求、任何 LLM 调用、任何数据库连接。
*   **速度**：< 5 秒。
*   **心态**：这是“卫生检查”，不是“功能验证”。

#### 2. 核心保障层：GitHub CI (Push/PR 触发)
*   **目标**：确保提交到仓库的代码，核心功能是好的。
*   **内容**：
    *   **集成测试（Mock LLM）**：
        *   使用 `pytest-mock` 模拟 LLM 返回固定答案。
        *   测试：Prompt 组装是否正确？向量检索是否调用了正确的接口？返回结构是否符合预期？
    *   **回归测试（小型黄金集）**：
        *   选取 3-5 个最核心的问题。
        *   由于 Mock 了 LLM，这里测的是**检索环节（Retrieval）**的准确性。即：给定一个问题，是否能召回正确的文档片段？
        *   *注意：RAG 的核心是检索，如果检索错了，LLM 再好也没用。所以这一步重点测向量相似度匹配逻辑。*
*   **速度**：< 2 分钟。
*   **心态**：这是“逻辑验证”，确保代码重构没有破坏数据流。

#### 3. 真实验证层：定时心跳 (Scheduled Cron)
*   **目标**：发现外部依赖问题和端到端效果退化。
*   **内容**：
    *   **真实 E2E 测试**：
        *   调用真实的 LLM API。
        *   使用**语义评估**（而非字符串匹配）。例如，使用一个小模型（或简单的关键词匹配）来判断返回的答案是否包含了预期信息。
    *   **覆盖范围**：全量黄金数据集（10-20 个问题）。
*   **频率**：每天 1 次，或每次重大版本发布后手动触发。
*   **成本**：极低（每天几次调用，几美分）。
*   **心态**：这是“健康体检”，确保系统在真实世界中是活的。

---

### 🛠️ 具体落地建议：如何维护“功能清单”

你担心的“老功能被改坏”，需要通过**版本化的测试用例**来解决。

1.  **建立 `tests/fixtures/golden_qa.json`**：
    ```json
    [
      {
        "id": "core_001",
        "category": "basic_qa",
        "question": "RAG 的基本原理是什么？",
        "expected_keywords": ["检索", "增强", "生成"],
        "description": "验证最基础的问答链路"
      },
      {
        "id": "feat_002",
        "category": "citation",
        "question": "刚才提到的观点出自哪篇文章？",
        "expected_keywords": ["来源", "参考文献"],
        "description": "验证引用溯源功能"
      }
    ]
    ```

2.  **编写通用的测试驱动器**：
    不要为每个问题写一个 `test_xxx` 函数。写一个参数化测试：
    ```python
    import json
    import pytest
    from my_rag_app import query_rag
    
    # 加载黄金数据集
    with open('tests/fixtures/golden_qa.json') as f:
        GOLDEN_DATA = json.load(f)
    
    @pytest.mark.parametrize("case", GOLDEN_DATA, ids=lambda c: c['id'])
    def test_regression_golden_set(case):
        """
        回归测试：确保所有历史核心功能依然正常工作
        """
        # 1. 执行查询 (这里可以配合 Mock 或 真实调用，取决于测试层级)
        response = query_rag(case['question'])
        
        # 2. 验证结果 (使用关键词包含，比字符串匹配更鲁棒)
        for keyword in case['expected_keywords']:
            assert keyword in response.answer, f"Missing keyword '{keyword}' in answer for question: {case['question']}"
    ```

3.  **工作流**：
    *   **新增功能时**：往 `golden_qa.json` 里加一个新案例。
    *   **重构代码时**：运行 `pytest tests/test_regression.py`。如果报错，说明你改坏了老功能。
    *   **AI 瞎改时**：如果 AI 修改了核心逻辑，这个测试会立刻红掉，提醒你“嘿，你把基本问答搞挂了”。

### 总结

*   **单元测试**：只测复杂算法，别测胶水代码。忽略覆盖率数字。
*   **集成测试**：Mock LLM，真测向量库。重点保检索逻辑。
*   **回归测试**：维护一个 JSON 格式的“黄金问题集”，这是你的**资产**。
*   **心跳测试**：每天真调一次 API，保活。

这套方案既避免了 AI 生成的冗余测试，又抓住了 RAG 项目最怕的“检索失效”和“逻辑回退”痛点。你可以先从**建立那个 `golden_qa.json`** 开始，这是性价比最高的一步。