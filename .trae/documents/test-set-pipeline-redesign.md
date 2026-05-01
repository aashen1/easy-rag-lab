# 测试集管线整合方案

> 版本：v1.1 | 日期：2026-05-02 | 状态：待确认
>
> v1.1 变更：新增 Phase 0 兼容性审计；修正 portable 语义（需数据覆盖条件）；完善 quality_status 状态机（加入 auto_approved）；修正 Phase 排序（3→4）；拆分 Phase 3 为 3a/3b；补充评估管线兼容性、AIReviewer 解耦、supplement 委托差异等盲区；修正 CLI 注册方式（需 `__main__.py`）。

---

## 一、现状诊断

### 1.1 碎片化全景

当前测试集相关功能分散在多个层级，缺乏统一的入口和一致的 UX：

| 位置 | 功能 | 问题 |
|------|------|------|
| `src/test_generation/generator.py` | `TestSetGenerator` 核心生成器 | 与 CLI 脱钩，generator 和 supplement 有重复逻辑 |
| `src/test_generation/supplement.py` | 补充生成、文档级生成 | 与 generator.py 职责重叠（都定义了 `_calculate_question_distribution`） |
| `src/test_set_manager.py` | CRUD + 校验 + 路由 resolve | 承担了过多职责（resolve 是业务逻辑，不应在 manager 中） |
| `src/test_set_cleaner.py` | trim/regenerate/immutable 清洗 | 与 manager 紧耦合（通过 `_manager` 引用相互调用） |
| `src/test_generator.py` | 兼容性 re-export 层 | 纯转发文件，增加认知负担 |
| `scripts/generate_golden_testset.py` | CLI 生成入口 | 与 `main.py` 并行存在，不统一 |
| `scripts/review_golden_testset.py` | 交互式审核（~1386行） | **只支持 golden 目录**，普通测试集无法审核 |
| `scripts/ai_reviewer.py` | AI 预审 | 硬编码依赖 `scripts/` 路径；**Anthropic SDK 硬耦合**（直接调用 `client.messages.create()`） |
| `scripts/pdf_viewer.py` | PDF 定位 | 与 Streamlit 的 PDF 服务器功能重叠 |
| `main.py` CLI | `--generate-test-set`, `--merge-test-sets` | 命令行参数散乱，无子命令分组 |

### 1.2 "黄金测试集"的概念模糊

对比 golden 与普通测试集的**实际差异**：

| 维度 | Golden | 普通 (machine) |
|------|--------|---------------|
| 存储路径 | `data/golden_testset/` | `data/<meal>/test_sets/` |
| metadata.user_defined | `True` | `False` |
| metadata.invalid_policy | `"immutable"` | `None` |
| ID 前缀 | `golden_XXX` | `qXXX` |
| 类型分布 | `GOLDEN_TYPE_DISTRIBUTION`（adversarial=20%） | `TYPE_DISTRIBUTION`（adversarial=10%） |
| 后处理 | `author`, `reviewed`, `review_notes`, `target_failure_mode` | 无 |
| 数据来源 | 全量 meal（sampling=1.0） | 当前 meal |

**结论**：Golden 本质上就是「已审核通过的、跨 meal 可移植的、使用全量数据的测试集」。这三个特征应该通过组合元数据来表达，而非成为独立的"类型"。

**⚠️ 关键补充**：Golden 的可移植性不仅来自审核通过，更来自**数据覆盖**——它使用 `sampling=1.0` 的全量 meal，覆盖了所有文档。一个从部分 meal 生成的测试集，即使审核通过了，跨 meal 使用也会导致大量 `source_files` 找不到。因此"可移植"必须是**数据覆盖 + 审核通过**的组合条件。

### 1.3 用户最痛的场景

> "上次审了 30 题，这次想要 60 题 → 我不想重新生成 60 题，只想追加 30 题并自动合并 JSON"

当前代码中 `merge_test_sets()` 已支持合并，但：
- 只支持跨 meal 合并（source_specs 必须指定 meal）
- 没有**同 meal 增量追加**的工作流
- 合并后不携带审核状态（被合并集合中的 `review_status` 被保留但没有智能标记）
- 用户需要手动管理 JSON 文件命名

### 1.4 评估管线对测试集的依赖（v1.1 新增）

评估管线是测试集的**核心消费者**，任何元数据格式变更都必须保证评估管线不断裂：

```
实验配置 YAML (test_sets)
    │
    ▼
prepare_test_sets() ─── resolve_test_set() ─── load_golden_testset()
    │                                              │
    │                                    data/golden_testset/*.json
    │
    ▼
test_sets: list[dict]
    │
    ├─► collect_rag_samples() ── 读取 questions[], 过滤 review_status=="rejected"
    │       │
    │       ▼
    │   _query_single_question() ── 读取每个 question 的 12 个字段:
    │       id, question, source_files, answer,
    │       ground_truth_excerpt, source_chunks,
    │       question_type, category, difficulty,
    │       expect_retrieval, expect_no_answer, metadata.review_status
    │
    └─► core.py 快照保存 ── 读取 metadata.name, .meal_id, .generation, .created_at
```

**关键消费点**：

| 消费位置 | 读取字段 | 影响 |
|----------|----------|------|
| `eval/runner/evaluation.py:163` | `metadata.review_status` | 过滤 rejected 问题，直接影响评测题目集 |
| `eval/runner/evaluation.py:297-311` | `source_files`, `answer`, `ground_truth_excerpt`, `source_chunks`, `question_type`, `expect_retrieval`, `expect_no_answer` | 决定检索/生成指标的计算结果 |
| `eval/runner/core.py:673-688` | `metadata.name`, `metadata.generation.strategy`, `metadata.meal_id` | 快照保存与实验指纹计算 |
| `src/test_set_cleaner.py:279` | `metadata.invalid_policy` | 决定清洗策略 |
| `src/test_set_cleaner.py:197` | `metadata.generation` | 判断是否有 generation config 用于补充 |
| `src/experiment_reuse.py:269-283` | `test_sets[].generation.strategy`, `.num_questions` | 实验指纹匹配 |

**结论**：元数据格式变更必须保证 `resolve_test_set()` 的输出结构不变（或向后兼容），否则评估管线会断裂。

---

## 二、目标架构

### 2.1 核心理念

**测试集是 RAG 系统的一等资产**，应该具备完整生命周期管理：

```
SYNTHESIZE  →  ENRICH    →  REVIEW    →  APPROVE   →  COMPOSE   →  DELIVER
(机器生成)     (AI预审)     (人工审核)    (定稿)       (组合复用)    (用于评测)
```

### 2.2 数据模型统一

废弃"Golden"概念，引入**质量状态（quality_status）**、**可移植性（portability）** 和**数据覆盖（data_coverage）**：

```python
# 新 TestSetMetadata 核心字段
@dataclass
class TestSetMetadata:
    name: str
    meal_id: str
    created_at: str
    updated_at: str
    generation: dict | None

    # 质量管线
    quality_status: str          # 见下方状态机定义
    review_progress: dict        # {"total": 150, "approved": 120, "rejected": 8, "pending": 22}

    # 可移植性（v1.1 修正：需同时满足数据覆盖 + 审核通过）
    portable: bool               # True = 可以跨 meal 使用
                                 # 提升条件：quality_status ∈ {"approved", "auto_approved"}
                                 #            AND data_coverage == "full"
    data_coverage: str           # "full" = 全量 meal（sampling=1.0）| "partial" = 部分 meal
    invalid_policy: str          # "immutable" | "trim" | "regenerate" — 仅 portable=True 时有意义

    # 组合溯源
    composition: dict            # {"type": "merged"|"incremental", "sources": [...], ...}
    audit_log: list[dict]
    suppress_warnings: bool
```

#### quality_status 状态机（v1.1 完善）

```
                    ┌──────────────────────┐
                    │       draft          │ ← 机器生成后的初始状态
                    └──────┬───────────────┘
                           │ testset enrich (AI 预审)
                           ▼
                    ┌──────────────────────┐
              ┌─────│     ai_reviewed      │
              │     └──────┬───────────────┘
              │            │ testset review (人工审核)
              │            ▼
              │     ┌──────────────────────┐
              │     │   human_reviewed     │
              │     └──────┬───────────────┘
              │            │ testset approve (定稿)
              │            ▼
              │     ┌──────────────────────┐
              └────►│      approved        │ ← 可移植化前提之一
                    └──────────────────────┘
                           ▲
                    ┌──────┴───────────────┐
                    │   auto_approved      │ ← AI 预审 Tier A 自动通过
                    └──────────────────────┘
                           │ testset approve
                           ▼
                    ┌──────────────────────┐
                    │      approved        │
                    └──────────────────────┘
```

**状态定义**：

| 状态 | 含义 | 触发条件 |
|------|------|----------|
| `draft` | 机器生成，未审核 | 生成完成后的默认状态 |
| `ai_reviewed` | AI 预审完成，有 tier 分级 | `testset enrich` 执行后 |
| `auto_approved` | AI 预审 Tier A 自动通过 | `testset enrich --auto-approve-tier-a` |
| `human_reviewed` | 人工审核完成 | `testset review` 执行后 |
| `approved` | 定稿，可提升为 portable | `testset approve` 执行后 |

**向后兼容映射**（旧格式迁移时）：

| 旧字段值 | 新字段默认值 |
|----------|-------------|
| `user_defined=True` | `quality_status="approved"`, `data_coverage="full"`, `portable=True` |
| `user_defined=False` | `quality_status="draft"`, `data_coverage="partial"`, `portable=False` |
| 无 `user_defined` 字段 | `quality_status="draft"`, `data_coverage="partial"`, `portable=False` |

### 2.3 存储重新布局

```
data/
├── test_sets/                          # ★ 新建：可移植测试集（替代 data/golden_testset/）
│   └── financial_reviewed_2026.json     #   - 审核通过 + 数据覆盖=full 后自动提升到此目录
│                                        #   - 命名体现内容而非"golden"
├── <meal_name>/
│   └── test_sets/                       # meal 级测试集（保留）
│       ├── hybrid_n30.json              #   draft 状态
│       ├── hybrid_n30_reviewed.json     #   review 中/完成
│       └── *.archive.*.json             #   备份
└── golden_testset/                      # ★ 保留兼容（迁移脚本将内容移至 test_sets/）
    └── golden_150.json
```

### 2.4 统一 CLI 设计

所有测试集操作收敛到一个 `pixi run testset` 命令：

```
pixi run testset generate     # 机器生成
pixi run testset enrich       # AI 预审打分+分级
pixi run testset review       # 交互式人工审核
pixi run testset approve      # 定稿 + 提升为 portable（需 data_coverage=="full"）
pixi run testset compose      # 增量追加 / 多源合并
pixi run testset audit        # 质量审计报告
pixi run testset list         # 列出可用测试集
pixi run testset info         # 显示测试集详情
pixi run testset migrate      # 从旧 golden 目录迁移到新结构
```

**CLI 注册方式**（v1.1 修正）：`pixi task` 是简单命令别名，不支持子命令。需要：

1. 创建 `src/testset_cli/__main__.py` 作为 `python -m src.testset_cli` 入口
2. 在 `pixi.toml` 中注册：`testset = "python -m src.testset_cli"`

---

## 三、实施计划

### Phase 0：兼容性审计（v1.1 新增）

**目标**：在动手重构前，梳理所有测试集数据的消费者，确保变更不破坏评估管线

| 步骤 | 内容 | 涉及文件 |
|------|------|---------|
| 0.1 | 梳理 `resolve_test_set()` 的完整调用链，记录所有读取的 metadata 字段 | `eval/runner/preparation.py`, `src/test_set_manager.py` |
| 0.2 | 梳理评估阶段消费的 question 级字段（12 个），确认哪些字段变更会影响指标计算 | `eval/runner/evaluation.py` |
| 0.3 | 梳理 `TestSetCleaner` 对 metadata 的依赖（`user_defined`、`invalid_policy`、`generation`） | `src/test_set_cleaner.py` |
| 0.4 | 梳理实验指纹计算对测试集字段的依赖 | `src/experiment_reuse.py` |
| 0.5 | 梳理快照保存逻辑对测试集字段的依赖 | `eval/runner/core.py` |
| 0.6 | 编写兼容性契约文档：列出所有"不可变更"的字段名和结构，后续 Phase 必须遵守 | 新建 `docs/dev-guides/test-set-compatibility.md` |
| 0.7 | 为现有评估管线编写冒烟测试：给定一个固定测试集 JSON，验证 `resolve_test_set()` → `collect_rag_samples()` 全链路输出不变 | `tests/test_eval_pipeline_compat.py` |

**验收标准**：
- 兼容性契约文档列出所有不可变更的字段名和结构
- 冒烟测试通过（现有评估管线可正常消费现有测试集）
- 后续每个 Phase 完成后都运行此冒烟测试，确保不断裂

---

### Phase 1：数据模型与存储重构

**目标**：统一 `TestSetMetadata`、新建 `data/test_sets/`、迁移脚本

| 步骤 | 内容 | 涉及文件 |
|------|------|---------|
| 1.1 | 扩展 `TestSetMetadata`：添加 `quality_status`、`review_progress`、`portable`、`data_coverage` 字段，**所有新字段提供默认值**（`quality_status="draft"`, `portable=False`, `data_coverage="partial"`, `review_progress={}`） | `src/test_set_manager.py` |
| 1.2 | 更新 `_migrate_test_set()` 支持新字段默认值：旧 `user_defined=True` → `quality_status="approved"`, `data_coverage="full"`, `portable=True`；旧 `user_defined=False` → `quality_status="draft"`, `data_coverage="partial"`, `portable=False` | `src/test_set_manager.py` |
| 1.3 | 扩展 `TestSetManager`（而非新建类）添加 `PORTABLE_TESTSET_DIR = "data/test_sets"` 常量和 `load_portable_testset()` / `save_portable_testset()` 方法。**理由**：`load_golden_testset()` 已在 `TestSetManager` 中，新建 `PortableTestSetManager` 会增加不必要的间接层；portable 管理本质就是"换一个目录读写"，不需要独立类 | `src/test_set_manager.py` |
| 1.4 | 编写 `testset migrate` 命令：将 `data/golden_testset/*.json` 迁移到 `data/test_sets/`，更新 metadata（`quality_status="approved"`, `data_coverage="full"`, `portable=True`） | 新建 `src/testset_cli/migrate.py` |
| 1.5 | 向后兼容：`load_golden_testset()` 先查 `data/test_sets/`，再回退 `data/golden_testset/` | `src/test_set_manager.py` |
| 1.6 | 更新 `resolve_test_set()` 中的 `golden: true` 分支：先走新的 `load_portable_testset()`，回退旧的 `load_golden_testset()` | `src/test_set_manager.py` |
| 1.7 | 更新 `TestSetCleaner`：将 `user_defined` 判断改为 `quality_status` 判断（`approved`/`auto_approved` 走 user 路径，`draft`/`ai_reviewed`/`human_reviewed` 走 machine 路径），保留 `user_defined` 作为只读兼容字段 | `src/test_set_cleaner.py` |
| 1.8 | 单元测试：metadata 序列化/迁移/兼容性/cleaner 路由 | `tests/test_test_set_metadata.py` |
| 1.9 | 运行 Phase 0 冒烟测试，确认评估管线不断裂 | `tests/test_eval_pipeline_compat.py` |

**验收标准**：
- 旧 `golden_150.json` 可通过 `testset migrate` 自动迁移到新目录
- `load_golden_testset("golden_150")` 在新/旧目录下均可正常加载
- `resolve_test_set()` 在新旧格式下均可正常工作
- `TestSetCleaner` 基于新字段正确路由清洗策略
- 所有现有测试通过
- Phase 0 冒烟测试通过

---

### Phase 2：生成管线整合

**目标**：消除 `supplement.py` 与 `generator.py` 的职责重叠，抽取公共逻辑

| 步骤 | 内容 | 涉及文件 |
|------|------|---------|
| 2.1 | 将 `_calculate_question_distribution` 抽取为 `src/test_generation/distribution.py` 中的公共函数 | 新建文件，修改 `generator.py`、`supplement.py` |
| 2.2 | 将 `_distribute_questions_across_docs` 同样挪至公共模块（保留 `seed` 参数，默认 `None` 兼容 supplement） | 同上 |
| 2.3 | 将 `_save_test_set` 抽取为公共函数 | 同上 |
| 2.4 | `supplement.py` 改为委托 `TestSetGenerator` 而非独立实现。**⚠️ 注意**：supplement 的 `source_chunks` 使用 `locate_answer_chunks()`（基于 answer_text），generator 使用 `locate_source_chunks()`（基于 page_numbers + quote），两者算法不同。委托时需保留 supplement 的 chunk 定位逻辑作为可选路径，或统一到 `locate_source_chunks()`（需验证对现有测试集的影响） | `supplement.py`, `generator.py` |
| 2.5 | `TestSetGenerator.generate_test_set()` / `generate_hybrid_questions()` / `generate_golden_testset()` 输出 metadata 使用新字段：`quality_status="draft"`, `data_coverage` 根据 meal 的 sampling 值推断（`sampling=1.0` → `"full"`，否则 `"partial"`） | `generator.py` |
| 2.6 | 实现 `testset generate` 子命令：统一的生成入口 | 新建 `src/testset_cli/generate.py` |
| 2.7 | 单元测试：generator 输出格式、supplement 委托正确性、distribution 公共函数 | 现有测试扩展 |
| 2.8 | 运行 Phase 0 冒烟测试 | `tests/test_eval_pipeline_compat.py` |

**验收标准**：
- `pixi run testset generate --meal my_meal --strategy hybrid --num 30` 可工作
- supplement 不再复制生成逻辑（三个公共函数已抽取）
- 生成的测试集 metadata 包含 `quality_status: "draft"` 和正确的 `data_coverage`
- Phase 0 冒烟测试通过

---

### Phase 3：审核管线通用化

**目标**：将 `review_golden_testset.py` 重构为可审核**任意测试集**的通用工具

> ⚠️ **复杂度评估**（v1.1 修正）：`review_golden_testset.py` 有 1386 行，包含 Rich 终端渲染、7 种交互操作、3 种审核模式、断点续审、PDF 唤起。函数间有大量隐式状态共享（全局变量、就地修改 questions 列表），拆分不是"迁移"而是"重写"。因此拆为两个子阶段。

#### Phase 3a：最小通用化（让任意测试集可审）

| 步骤 | 内容 | 涉及文件 |
|------|------|---------|
| 3a.1 | 将 `--input` 默认值从 `data/golden_testset/golden_150.json` 改为必填参数（无默认值），移除 golden 目录硬编码 | `scripts/review_golden_testset.py` |
| 3a.2 | 审核完成后更新 `quality_status`：`"draft"` → `"ai_reviewed"`（AI 预审后）/ `"human_reviewed"`（人工审核后）/ `"auto_approved"`（Tier A 自动通过） | `scripts/review_golden_testset.py` |
| 3a.3 | 将 `"auto_approved"` 魔法字符串定义为常量 `REVIEW_STATUS_AUTO_APPROVED`，与现有 `REVIEW_STATUS_APPROVED` 等常量统一管理 | `scripts/review_golden_testset.py` |
| 3a.4 | 更新 `review_progress` 字段：审核开始时初始化，每次 approve/reject/skip 后更新 | `scripts/review_golden_testset.py` |
| 3a.5 | 测试：使用非 golden 测试集走通审核流程 | 手动验证 |

**验收标准**：
- `python scripts/review_golden_testset.py --input data/my_meal/test_sets/hybrid_n30.json` 可审核任意测试集
- 审核状态正确在 metadata 中反映（`quality_status` + `review_progress`）
- 现有 golden 测试集审核流程不受影响

#### Phase 3b：模块化重写 + AIReviewer 解耦

| 步骤 | 内容 | 涉及文件 |
|------|------|---------|
| 3b.1 | 将审核核心逻辑重写为 `src/testset_review/engine.py`：审核状态机（approve/edit/reject/skip/quit），显式接口（输入 questions 列表 + config，输出修改后的 questions 列表 + 状态摘要），消除隐式状态共享 | 新建 |
| 3b.2 | 将终端渲染逻辑重写为 `src/testset_review/display.py`：进度条、tier badge、chunk context，接收结构化数据而非直接读取全局变量 | 新建 |
| 3b.3 | 将 AI 预审逻辑迁移为 `src/testset_review/ai_reviewer.py`：**同时解耦 Anthropic SDK 硬依赖**——抽象 LLM 调用层，使用项目已有的 `create_llm_client` / `get_llm_config` 统一接口，支持非 Anthropic 后端 | 新建，参考 `scripts/ai_reviewer.py` |
| 3b.4 | 将 PDF 定位逻辑迁移为 `src/testset_review/pdf_viewer.py`：保持 `ArtifactCache` 解耦设计 | 新建，参考 `scripts/pdf_viewer.py` |
| 3b.5 | 实现 `testset enrich` 子命令：AI 预审（支持 `--auto-approve-tier-a` 触发 `auto_approved` 状态） | 新建 `src/testset_cli/enrich.py` |
| 3b.6 | 实现 `testset review` 子命令：交互式审核（支持 `--only-new` 仅审核 `quality_status=="draft"` 的题目） | 新建 `src/testset_cli/review.py` |
| 3b.7 | 实现 `testset approve` 子命令：定稿（`quality_status` → `"approved"`）+ 若 `data_coverage=="full"` 则提升为 portable | 新建 `src/testset_cli/approve.py` |
| 3b.8 | 单元测试：审核状态机、AI reviewer 打分逻辑、LLM 调用层抽象 | `tests/test_testset_review.py` |
| 3b.9 | 运行 Phase 0 冒烟测试 | `tests/test_eval_pipeline_compat.py` |

**验收标准**：
- `pixi run testset review --input data/my_meal/test_sets/hybrid_n30.json` 可审核任意测试集
- `pixi run testset review --input ... --only-new` 仅审核新增题目
- `pixi run testset enrich --input ... --auto-approve-tier-a` 正确设置 `auto_approved` 状态
- `pixi run testset approve --input ...` 正确提升为 portable（仅 `data_coverage=="full"` 时）
- AI 预审不硬依赖 Anthropic SDK
- Phase 0 冒烟测试通过

---

### Phase 4：资产组合系统（核心用户需求）

**目标**："上次 30 题 → 这次追加 30 题 → 自动合成 60 题"

> ⚠️ **依赖说明**（v1.1 修正）：Phase 4 的增量追加场景依赖 Phase 3 的 `--only-new` 审核，因此 Phase 3 必须在 Phase 4 之前完成。Phase 4 可先实现 `compose_merge`（多源合并，无审核依赖），再实现 `compose_incremental`（增量追加，依赖 Phase 3）。

| 步骤 | 内容 | 涉及文件 |
|------|------|---------|
| 4.1 | 设计 `TestSetComposer` 类 | 新建 `src/testset_composer.py` |
| 4.2 | `compose_merge()`：合并多个测试集（现有 `merge_test_sets` 重构至此） | 同上 |
| 4.3 | `compose_filter()`：按条件筛选（审核状态、类型、难度等）抽取子集 | 同上 |
| 4.4 | `compose_incremental()`：以现有测试集为基础，生成 N 道新题并合并。**必须指定 `--meal`**（新题需要知道从哪个 meal 生成） | 同上 |
| 4.5 | 组合后自动去重（基于 question text 相似度 > 0.85 + source_files 重叠度）、重新编号。**v1.1 修正**：当前问题数据中没有 `key_entities` 字段，去重改用 `question` 文本相似度 + `source_files` 重叠度 | 同上 |
| 4.6 | composition metadata 记录完整溯源链 | 同上 |
| 4.7 | 实现 `testset compose` 子命令 | 新建 `src/testset_cli/compose.py` |
| 4.8 | 单元测试：增量组合、多源合并、去重逻辑、溯源记录 | `tests/test_testset_composer.py` |
| 4.9 | 运行 Phase 0 冒烟测试 | `tests/test_eval_pipeline_compat.py` |

**关键使用示例**：

```bash
# 场景1：增量追加 — 已有 30 题已审核，追加 30 题凑 60
pixi run testset compose \
  --base data/my_meal/test_sets/hybrid_n30_reviewed.json \
  --supplement 30 \
  --meal my_meal \
  --strategy hybrid \
  --output hybrid_n60

# 场景2：多源合并 — 两个 meal 的审核通过集合并
pixi run testset compose \
  --sources meal_a:hybrid_n20 meal_b:document_n15 \
  --meal target_meal \
  --output combined_n35

# 场景3：抽取子集 — 从 150 题里抽 50 题单知识点
pixi run testset compose \
  --base data/test_sets/financial_reviewed.json \
  --filter "question_type=single_fact" \
  --limit 50 \
  --output single_fact_50
```

**验收标准**：
- 增量追加后保留原有审核状态，新增题目为 `draft`
- 多源合并时去重正确、编号连续
- composition 字段完整记录来源
- Phase 0 冒烟测试通过

---

### Phase 5：审计与可观测性

**目标**：测试集质量可度量、可追踪

| 步骤 | 内容 | 涉及文件 |
|------|------|---------|
| 5.1 | 将 `audit_testset()` 从 script 迁移至 `src/testset_audit.py` | 新建文件 |
| 5.2 | 增强审计报告：增加审核覆盖率（`review_progress` 汇总）、类型均衡度、来源文档分布、去重分析 | 同上 |
| 5.3 | 审计结果可导出为 JSON/Markdown | 同上 |
| 5.4 | 实现 `testset audit` 子命令 | 新建 `src/testset_cli/audit.py` |
| 5.5 | 实现 `testset info` 和 `testset list` 子命令 | 新建 `src/testset_cli/info.py` |

---

### Phase 6：CLI 入口统一与旧代码清理

**目标**：`pixi run testset` 作为唯一入口

| 步骤 | 内容 | 涉及文件 |
|------|------|---------|
| 6.1 | 创建 `src/testset_cli/__init__.py` → `main()` 统一入口，注册所有子命令 | 新建 |
| 6.2 | 创建 `src/testset_cli/__main__.py` → 支持 `python -m src.testset_cli` 调用 | 新建 |
| 6.3 | 在 `pixi.toml` 中注册 `testset` 任务：`testset = "python -m src.testset_cli"` | 配置修改 |
| 6.4 | 将 `main.py` 中的 `--generate-test-set`、`--merge-test-sets` 改为调用新 CLI 或标记 deprecated | `main.py` |
| 6.5 | 将 `scripts/generate_golden_testset.py` 标记为 deprecated，指向新 CLI | 脚本修改 |
| 6.6 | 将 `scripts/review_golden_testset.py` 标记为 deprecated，指向新 CLI | 脚本修改 |
| 6.7 | 全量回归测试 | `pixi run test-all` |
| 6.8 | 更新 `docs/user-guides/test-set-management.md` | 文档 |

---

### Phase 7：验收与打磨（用户特别关注）

**目标**：确保审核工具实际可用

| 步骤 | 内容 |
|------|------|
| 7.1 | 使用现有 `golden_150.json`（或新生成的测试集）完整走通审核流程 |
| 7.2 | 验证 PDF 唤起功能在 Windows 环境下正常工作（SumatraPDF / Edge） |
| 7.3 | 验证 chunk 上下文显示正确 |
| 7.4 | 验证断点续审（`--start-from` / `last_reviewed_index`） |
| 7.5 | 验证 AI 预审的 tier 分级合理 |
| 7.6 | 验证 `--only-new` 仅审核新增题目 |
| 7.7 | 验证 `testset approve` 正确判断 `data_coverage` 并决定是否提升为 portable |
| 7.8 | 记录审核体验问题并修复 |

---

## 四、文件变更总览

### 新增文件

```
src/testset_cli/                   # 统一 CLI 入口
├── __init__.py                     # main() 入口 + argparse 子命令注册
├── __main__.py                     # python -m 入口
├── generate.py                     # testset generate
├── enrich.py                       # testset enrich (AI 预审)
├── review.py                       # testset review (人工审核)
├── approve.py                      # testset approve (定稿)
├── compose.py                      # testset compose (组合复用)
├── audit.py                        # testset audit (审计)
├── info.py                         # testset list / info
└── migrate.py                      # testset migrate (旧目录→新目录)

src/testset_review/                # 审核引擎（从 scripts/ 重写）
├── __init__.py
├── engine.py                       # 审核状态机（显式接口，无隐式状态共享）
├── display.py                      # 终端渲染
├── ai_reviewer.py                  # AI 预审（解耦 Anthropic SDK，使用统一 LLM 调用层）
└── pdf_viewer.py                   # PDF 定位

src/testset_composer.py            # 测试集组合器（增量/合并/抽取）
src/testset_audit.py               # 审计报告生成
src/test_generation/distribution.py # 公共：题目分发算法

docs/dev-guides/test-set-compatibility.md  # 兼容性契约文档
tests/test_eval_pipeline_compat.py         # 评估管线冒烟测试
```

### 重构文件

```
src/test_set_manager.py            # 扩展：添加 portable 管理方法 + 新 metadata 字段；保留向后兼容
src/test_set_cleaner.py            # 更新：user_defined 判断改为 quality_status 判断
src/test_generation/generator.py   # 使用新的 distribution 模块，更新 metadata 格式
src/test_generation/supplement.py  # 委托 generator，消除重复；保留 chunk 定位差异
src/test_generator.py              # 可能废弃（由 CLI 入口替代）
```

### 废弃（deprecate）文件

```
scripts/generate_golden_testset.py   # → testset generate
scripts/review_golden_testset.py     # → testset review
scripts/ai_reviewer.py                # → 重写为 src/testset_review/ai_reviewer.py
scripts/pdf_viewer.py                 # → 重写为 src/testset_review/pdf_viewer.py
data/golden_testset/                  # → data/test_sets/（通过 testset migrate 迁移）
```

### 修改文件

```
main.py                              # 标记旧参数 deprecated，指引到 testset CLI
pixi.toml                            # 注册 testset 任务
docs/user-guides/test-set-management.md  # 完全重写
config.yaml                          # 可能需要新增 test_sets_dir 配置
```

---

## 五、风险与缓解

| 风险 | 缓解 |
|------|------|
| 大规模重构导致评估管线断裂 | **Phase 0 先建立兼容性契约 + 冒烟测试**，每个 Phase 完成后运行冒烟测试 |
| review 脚本功能丢失 | Phase 3a 先做最小改动（`--input` 通用化），Phase 3b 再做模块重写；原 script 保留至 Phase 6 才标记 deprecated |
| 旧实验脚本依赖旧路径 | `load_golden_testset()` 保留兼容层，先查新目录再回退旧目录 |
| CLI 学习成本 | 保留 `--help` 完整输出，废弃命令打印迁移指引而非直接报错 |
| 时间/精力限制 | Phase 0-4 是核心，Phase 5-7 可以渐进完成 |
| **AIReviewer Anthropic SDK 硬耦合**（v1.1 新增） | Phase 3b 迁移时抽象 LLM 调用层，使用项目已有的 `create_llm_client` / `get_llm_config` 统一接口 |
| **supplement chunk 定位差异**（v1.1 新增） | Phase 2 委托时保留 `locate_answer_chunks()` 作为可选路径，或统一到 `locate_source_chunks()` 但需验证影响 |
| **`auto_approved` 魔法字符串**（v1.1 新增） | Phase 3a 先定义为常量，Phase 3b 纳入状态机统一管理 |
| **compose 增量追加依赖审核**（v1.1 新增） | Phase 3 必须在 Phase 4 之前完成；Phase 4 先实现 `compose_merge`，再实现 `compose_incremental` |

---

## 六、执行顺序建议（v1.1 修正）

```
Phase 0 (兼容性审计) → Phase 1 (数据模型) → Phase 2 (生成整合) → Phase 3a (审核最小通用化) → Phase 4 (组合系统) → Phase 3b (审核模块重写) → Phase 5 (审计) → Phase 6 (CLI 统一) → Phase 7 (验收)
```

**修正理由**：

1. **Phase 0 必须最先**：没有兼容性审计，后续所有 Phase 都可能在不知不觉中破坏评估管线
2. **Phase 3a 在 Phase 4 之前**：增量追加场景（`compose_incremental`）依赖 `--only-new` 审核，而 `--only-new` 需要 `quality_status` 字段来识别新增题目。Phase 3a 提供了最小可用的审核通用化
3. **Phase 3b 在 Phase 4 之后**：模块重写是独立工作，不阻塞组合系统。Phase 4 可以基于 Phase 3a 的最小审核能力闭环
4. **Phase 3a 和 Phase 4 可以部分并行**：3a 完成后即可开始 4，3b 可在 4 进行中同步推进

**依赖关系图**：

```
Phase 0 ──► Phase 1 ──► Phase 2 ──► Phase 3a ──► Phase 4
                                       │              │
                                       └──────────────┤
                                                      │
                                              Phase 3b (可与 4 并行)
                                                      │
                                                      ▼
                                              Phase 5 ──► Phase 6 ──► Phase 7
```

---

## 七、点睛之笔：一个完整的故事

重构完成后，用户的故事线将是：

```bash
# 1. 生成第一批测试集
pixi run testset generate --meal banking --strategy hybrid --num 30
# → data/banking/test_sets/hybrid_n30.json  (quality_status: draft, data_coverage: partial)

# 2. AI 预审（自动分级）
pixi run testset enrich --input data/banking/test_sets/hybrid_n30.json --auto-approve-tier-a
# → 每道题获得 AI score + tier (A/B/C)
# → Tier A 题目自动标记为 auto_approved，其余保持 ai_reviewed

# 3. 人工审核 B/C 级
pixi run testset review --input data/banking/test_sets/hybrid_n30.json --tiered
# → 逐题审，通过/拒绝/编辑，进度自动保存
# → 审核完成后 quality_status: human_reviewed

# 4. 定稿
pixi run testset approve --input data/banking/test_sets/hybrid_n30.json
# → quality_status: approved
# → data_coverage: partial → 不提升为 portable（仅覆盖部分文档）
# → 文件保留在 data/banking/test_sets/

# 5. 几周后：需要 60 题了！增量追加
pixi run testset compose \
  --base data/banking/test_sets/hybrid_n30.json \
  --supplement 30 \
  --meal banking \
  --strategy hybrid \
  --output hybrid_n60
# → 30 题审核过的 + 30 题新生成的 → 合并去重 → 60 题
# → 旧题保持 approved，新题标记 draft

# 6. 仅审核新增题目
pixi run testset review --input data/banking/test_sets/hybrid_n60.json --only-new
# → 只审 quality_status=="draft" 的 30 道新题

# 7. 再定稿
pixi run testset approve --input data/banking/test_sets/hybrid_n60.json
# → quality_status: approved, data_coverage: partial

# 8. 如果想要可移植测试集：用全量 meal 生成
pixi run testset generate --meal full_dataset --strategy hybrid --num 150
# → data/full_dataset/test_sets/hybrid_n150.json  (data_coverage: full)
# → 审核定稿后自动提升为 portable → data/test_sets/financial_reviewed_2026.json

# 9. 查看资产
pixi run testset list
pixi run testset audit --input data/test_sets/financial_reviewed_2026.json
```

**这是一个从合成数据到人工审核到资产复用的完整故事，每个环节都通过统一的 `testset` CLI 串联。可移植性由数据覆盖 + 审核通过共同决定，而非仅靠审核通过。**

---

> 计划确认后将按 Phase 顺序逐步实施，每个 Phase 完成一个原子提交。每个 Phase 完成后必须运行 Phase 0 的冒烟测试，确保评估管线不断裂。
