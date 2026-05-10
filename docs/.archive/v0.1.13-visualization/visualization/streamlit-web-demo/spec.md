# Streamlit Web Demo Spec

## Why

当前项目作为简历展示项目存在以下问题：
1. **缺乏可视化界面**：纯 CLI 工具，面试官/HR 无法直观理解项目价值
2. **演示门槛高**：需要本地部署才能体验，无法快速分享
3. **实验结果展示困难**：无法直观展示多策略对比效果

## What Changes

- 创建 `src/app.py` 作为 Streamlit 主入口
- 创建 `src/app_pages/` 目录存放页面模块
- 实现问答演示页、配置面板、系统信息页
- 添加 `pixi run web` 启动命令
- 支持 Streamlit Cloud 部署

## Impact

- Affected specs: Web 可视化能力
- Affected code: 新增 `src/app.py`, `src/app_pages/`, 修改 `pixi.toml`
- Affected docs: `README.md`, `docs/architecture.md`

---

## ADDED Requirements

### Requirement: Streamlit 应用主入口

系统应提供 Streamlit Web 应用主入口，支持多页面导航。

#### Scenario: 启动 Web 应用
- **WHEN** 用户执行 `pixi run web`
- **THEN** 系统启动 Streamlit 服务器，监听 8501 端口
- **AND** 浏览器自动打开 `http://localhost:8501`

#### Scenario: 页面导航
- **WHEN** 用户在侧边栏选择不同页面
- **THEN** 系统切换到对应页面内容
- **AND** 保持侧边栏配置状态

### Requirement: 问答演示页

系统应提供问答演示页面，支持问题输入、答案展示、检索详情查看。

#### Scenario: 输入问题获取答案
- **WHEN** 用户在文本框输入问题并点击提交
- **THEN** 系统调用 `RAGPipeline.query()` 获取答案
- **AND** 展示答案、来源文档、检索片段、Token 消耗

#### Scenario: 查看检索详情
- **WHEN** 答案展示后
- **THEN** 系统提供三个标签页：来源文档、检索片段、评分详情
- **AND** 来源文档显示文件名和相关度分数
- **AND** 检索片段可展开查看完整内容

#### Scenario: Token 消耗统计
- **WHEN** 问答完成后
- **THEN** 系统展示输入 Token、输出 Token、总 Token 数量
- **AND** 使用指标卡片形式展示

### Requirement: 配置面板

系统应提供侧边栏配置面板，支持 Meal 选择、检索策略切换、参数调节。

#### Scenario: 选择 Meal
- **WHEN** 用户在侧边栏选择 Meal
- **THEN** 系统切换到对应的 Meal 数据集
- **AND** 后续问答使用该 Meal 的向量索引

#### Scenario: 切换检索策略
- **WHEN** 用户选择不同的检索策略（vector/bm25/hybrid）
- **THEN** 系统更新检索配置
- **AND** 后续问答使用新策略

#### Scenario: 调节 Top-K
- **WHEN** 用户拖动 Top-K 滑块
- **THEN** 系统更新检索数量参数
- **AND** 后续问答返回对应数量的结果

#### Scenario: 启用 Reranker
- **WHEN** 用户勾选"启用 Reranker"
- **THEN** 系统启用重排序功能
- **AND** 后续问答结果经过 Reranker 重排

#### Scenario: 启用查询改写
- **WHEN** 用户勾选"启用查询改写"
- **THEN** 系统启用 HyDE 查询改写
- **AND** 后续问答使用改写后的查询进行检索

### Requirement: 系统信息页

系统应提供系统信息页面，展示架构流程图、技术栈说明、使用指南。

#### Scenario: 查看架构流程图
- **WHEN** 用户访问系统信息页
- **THEN** 系统展示 RAG 链路流程图
- **AND** 标注各阶段的关键技术

#### Scenario: 查看技术栈
- **WHEN** 用户查看技术栈部分
- **THEN** 系统展示项目使用的核心技术栈
- **AND** 包含版本信息和用途说明

### Requirement: Pipeline 缓存机制

系统应实现 Pipeline 缓存机制，避免重复加载模型。

#### Scenario: 首次加载 Pipeline
- **WHEN** 用户首次提交问题
- **THEN** 系统初始化 Pipeline 并缓存
- **AND** 显示加载进度提示

#### Scenario: 复用已缓存的 Pipeline
- **WHEN** 用户再次提交问题且 Meal 未变更
- **THEN** 系统复用已缓存的 Pipeline
- **AND** 跳过模型加载步骤

#### Scenario: 切换 Meal 时重新加载
- **WHEN** 用户切换到不同的 Meal
- **THEN** 系统释放旧 Pipeline 并加载新 Pipeline
- **AND** 更新缓存

### Requirement: 错误处理与用户反馈

系统应提供友好的错误处理和用户反馈机制。

#### Scenario: 空问题提交
- **WHEN** 用户提交空问题
- **THEN** 系统显示警告提示"请输入问题"
- **AND** 不执行检索

#### Scenario: 检索失败
- **WHEN** 检索过程发生错误
- **THEN** 系统显示错误信息
- **AND** 记录错误日志

#### Scenario: 加载中状态
- **WHEN** 执行检索或生成时
- **THEN** 系统显示加载动画
- **AND** 禁用提交按钮

### Requirement: Pixi Task 集成

系统应提供 `pixi run web` 命令启动 Web 应用。

#### Scenario: 执行 pixi run web
- **WHEN** 用户执行 `pixi run web`
- **THEN** 系统启动 Streamlit 服务器
- **AND** 监听 8501 端口

---

## MODIFIED Requirements

无

---

## REMOVED Requirements

无

---

## Technical Design

### 文件结构

```
src/
├── app.py                    # Streamlit 主入口
├── app_pages/                # 页面模块
│   ├── __init__.py
│   ├── qa_demo.py            # 问答演示页
│   └── about.py              # 系统信息页
└── ...
```

### 依赖添加

```toml
# pixi.toml [pypi-dependencies]
streamlit = ">=1.32.0, <2"
```

### Task 添加

```toml
# pixi.toml [tasks]
[tasks.web]
cmd = "streamlit run src/app.py --server.port 8501"
```

### 核心类设计

```python
# src/app_pages/qa_demo.py

class QADemoPage:
    """问答演示页面"""

    def __init__(self):
        self._pipeline_cache: dict[str, RAGPipeline] = {}

    def render(self):
        """渲染页面"""
        self._render_sidebar()
        self._render_main()

    def _render_sidebar(self):
        """渲染侧边栏配置"""
        pass

    def _render_main(self):
        """渲染主界面"""
        pass

    def _get_pipeline(self, meal_name: str | None) -> RAGPipeline:
        """获取或创建 Pipeline 实例"""
        pass
```

---

## Out of Scope

以下功能不在本次 Spec 范围内：

1. **实验对比页**：Phase 2 实现
2. **PDF 预览**：需要额外的 PDF 渲染组件
3. **历史记录**：需要持久化存储
4. **用户认证**：单用户演示场景不需要
5. **Streamlit Cloud 部署**：Phase 4 实现
