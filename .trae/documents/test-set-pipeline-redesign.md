# 测试集管线整合方案

> 版本：v1.0 | 日期：2026-05-02 | 状态：待确认

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
| `scripts/ai_reviewer.py` | AI 预审 | 硬编码依赖 `scripts/` 路径 |
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

### 1.3 用户最痛的场景

> "上次审了 30 题，这次想要 60 题 → 我不想重新生成 60 题，只想追加 30 题并自动合并 JSON"

当前代码中 `merge_test_sets()` 已支持合并，但：
- 只支持跨 meal 合并（source_specs 必须指定 meal）
- 没有**同 meal 增量追加**的工作流
- 合并后不携带审核状态（被合并集合中的 `review_status` 被保留但没有智能标记）
- 用户需要手动管理 JSON 文件命名

---

## 二、目标架构

### 2.1 核心理念

**测试集是 RAG 系统的一等资产**，应该具备完整生命周期管理：

```
SYNTHESIZE  →  ENRICH    →  REVIEW    →  APPROVE   →  COMPOSE   →  DELIVER
(机器生成)     (AI预审)     (人工审核)    (定稿)       (组合复用)    (用于评测)
```

### 2.2 数据模型统一

废弃"Golden"概念，引入**质量状态（quality_status）** 和**可移植性（portability）**：

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
    quality_status: str          # "draft" | "ai_reviewed" | "human_reviewed" | "approved"
    review_progress: dict        # {"total": 150, "approved": 120, "rejected": 8, "pending": 22}

    # 可移植性
    portable: bool               # True = 可以跨 meal 使用（由审核通过触发）
    invalid_policy: str          # "immutable" | "trim" | "regenerate" — 仅 portable=True 时有意义

    # 组合溯源
    composition: dict            # {"type": "merged"|"incremental", "sources": [...], ...}
    audit_log: list[dict]
    suppress_warnings: bool
```

### 2.3 存储重新布局

```
data/
├── test_sets/                          # ★ 新建：可移植测试集（替代 data/golden_testset/）
│   └── financial_reviewed_2026.json     #   - 审核通过后自动提升到此目录
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
pixi run testset approve      # 定稿 + 提升为 portable
pixi run testset compose      # 增量追加 / 多源合并
pixi run testset audit        # 质量审计报告
pixi run testset list         # 列出可用测试集
pixi run testset info         # 显示测试集详情
pixi run testset migrate      # 从旧 golden 目录迁移到新结构
```

---

## 三、实施计划

### Phase 1：数据模型与存储重构

**目标**：统一 `TestSetMetadata`、新建 `data/test_sets/`、迁移脚本

| 步骤 | 内容 | 涉及文件 |
|------|------|---------|
| 1.1 | 扩展 `TestSetMetadata`：添加 `quality_status`、`review_progress`、`portable` 字段 | `src/test_set_manager.py` |
| 1.2 | 更新 `_migrate_test_set()` 支持新字段默认值，旧格式自动补齐 | `src/test_set_manager.py` |
| 1.3 | 新增 `PortableTestSetManager`：管理 `data/test_sets/` 目录的读写 | 新建 `src/test_set_portable.py` |
| 1.4 | 编写 `testset migrate` 命令：将 `data/golden_testset/*.json` 迁移到 `data/test_sets/`，更新 metadata | 新建 `src/testset_cli/migrate.py` |
| 1.5 | 向后兼容：`load_golden_testset()` 先查新目录，再回退旧目录 | `src/test_set_manager.py` |
| 1.6 | 单元测试：metadata 序列化/迁移/兼容性 | `tests/test_test_set_metadata.py` |

**验收标准**：
- 旧 `golden_150.json` 可通过 `testset migrate` 自动迁移到新目录
- `load_golden_testset("golden_150")` 在新/旧目录下均可正常加载
- 所有现有测试通过

---

### Phase 2：生成管线整合

**目标**：消除 `supplement.py` 与 `generator.py` 的职责重叠，抽取公共逻辑

| 步骤 | 内容 | 涉及文件 |
|------|------|---------|
| 2.1 | 将 `_calculate_question_distribution` 抽取为 `src/test_generation/distribution.py` 中的公共函数 | 新建文件，修改 `generator.py`、`supplement.py` |
| 2.2 | 将 `_distribute_questions_across_docs` 同样挪至公共模块 | 同上 |
| 2.3 | `supplement.py` 改为委托 `TestSetGenerator._generate_hybrid_question()` 而非独立实现 | `supplement.py` |
| 2.4 | `TestSetGenerator.generate_test_set()` 输出 metadata 使用新的 `quality_status="draft"` 字段 | `generator.py` |
| 2.5 | 实现 `testset generate` 子命令：统一的生成入口 | 新建 `src/testset_cli/generate.py` |
| 2.6 | 单元测试：generator 输出格式、supplement 委托正确性 | 现有测试扩展 |

**验收标准**：
- `pixi run testset generate --meal my_meal --strategy hybrid --num 30` 可工作
- supplement 不再复制生成逻辑
- 生成的测试集 metadata 包含 `quality_status: "draft"`

---

### Phase 3：审核管线通用化

**目标**：将 `review_golden_testset.py` 重构为可审核**任意测试集**的通用工具

| 步骤 | 内容 | 涉及文件 |
|------|------|---------|
| 3.1 | 将 `review_golden_testset.py` 核心逻辑抽取为 `src/testset_review/` 包 | 新建目录 |
| 3.2 | - `src/testset_review/engine.py`：审核状态机（approve/edit/reject/skip/quit） | 从 script 迁移 |
| 3.3 | - `src/testset_review/display.py`：终端渲染（进度条、tier badge、chunk context） | 从 script 迁移 |
| 3.4 | - `src/testset_review/ai_reviewer.py`：AI 预审逻辑（从 `scripts/ai_reviewer.py` 迁移） | 从 script 迁移 |
| 3.5 | - `src/testset_review/pdf_viewer.py`：PDF 定位（从 `scripts/pdf_viewer.py` 迁移） | 从 script 迁移 |
| 3.6 | 审核工具支持通过 `--input` 指定任意 test set JSON 路径（不再硬编码 golden 目录） | `engine.py` |
| 3.7 | 审核完成后更新 `quality_status`：`"ai_reviewed"` → `"human_reviewed"` | `engine.py` |
| 3.8 | 实现 `testset enrich` 子命令：AI 预审 | 新建 `src/testset_cli/enrich.py` |
| 3.9 | 实现 `testset review` 子命令：交互式审核 | 新建 `src/testset_cli/review.py` |
| 3.10 | 实现 `testset approve` 子命令：定稿 + 提升为 portable | 新建 `src/testset_cli/approve.py` |
| 3.11 | 单元测试：审核状态机、AI reviewer 打分逻辑 | `tests/test_testset_review.py` |

**验收标准**：
- `pixi run testset review --input data/my_meal/test_sets/hybrid_n30.json` 可审核任意测试集
- 审核状态正确在 metadata 中反映
- AI 预审可独立运行，不依赖交互式审核

---

### Phase 4：资产组合系统（核心用户需求）

**目标**："上次 30 题 → 这次追加 30 题 → 自动合成 60 题"

| 步骤 | 内容 | 涉及文件 |
|------|------|---------|
| 4.1 | 设计 `TestSetComposer` 类 | 新建 `src/testset_composer.py` |
| 4.2 | `compose_incremental()`：以现有测试集为基础，生成 N 道新题并合并 | 同上 |
| 4.3 | `compose_merge()`：合并多个测试集（现有 `merge_test_sets` 重构至此） | 同上 |
| 4.4 | `compose_filter()`：按条件筛选（审核状态、类型、难度等）抽取子集 | 同上 |
| 4.5 | 组合后自动去重（基于 question text + key_entities）、重新编号 | 同上 |
| 4.6 | composition metadata 记录完整溯源链 | 同上 |
| 4.7 | 实现 `testset compose` 子命令 | 新建 `src/testset_cli/compose.py` |
| 4.8 | 单元测试：增量组合、多源合并、去重逻辑、溯源记录 | `tests/test_testset_composer.py` |

**关键使用示例**：

```bash
# 场景1：增量追加 — 已有 30 题已审核，追加 30 题凑 60
pixi run testset compose \
  --base data/my_meal/test_sets/hybrid_n30_reviewed.json \
  --supplement 30 \
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

---

### Phase 5：审计与可观测性

**目标**：测试集质量可度量、可追踪

| 步骤 | 内容 | 涉及文件 |
|------|------|---------|
| 5.1 | 将 `audit_testset()` 从 script 迁移至 `src/testset_audit.py` | 新建文件 |
| 5.2 | 增强审计报告：增加审核覆盖率、类型均衡度、来源文档分布、去重分析 | 同上 |
| 5.3 | 审计结果可导出为 JSON/Markdown | 同上 |
| 5.4 | 实现 `testset audit` 子命令 | 新建 `src/testset_cli/audit.py` |
| 5.5 | 实现 `testset info` 和 `testset list` 子命令 | 新建 `src/testset_cli/info.py` |

---

### Phase 6：CLI 入口统一与旧代码清理

**目标**：`pixi run testset` 作为唯一入口

| 步骤 | 内容 | 涉及文件 |
|------|------|---------|
| 6.1 | 创建 `src/testset_cli/__init__.py` → `main()` 统一入口，注册所有子命令 | 新建 |
| 6.2 | 在 `pyproject.toml` / `pixi.toml` 中注册 `testset` 任务 | 配置修改 |
| 6.3 | 将 `main.py` 中的 `--generate-test-set`、`--merge-test-sets` 改为调用新 CLI 或标记 deprecated | `main.py` |
| 6.4 | 将 `scripts/generate_golden_testset.py` 标记为 deprecated，指向新 CLI | 脚本修改 |
| 6.5 | 将 `scripts/review_golden_testset.py` 标记为 deprecated，指向新 CLI | 脚本修改 |
| 6.6 | 全量回归测试 | `pixi run test-all` |
| 6.7 | 更新 `docs/user-guides/test-set-management.md` | 文档 |

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
| 7.6 | 记录审核体验问题并修复 |

---

## 四、文件变更总览

### 新增文件

```
src/testset_cli/                   # 统一 CLI 入口
├── __init__.py                     # main() 入口 + argparse 子命令注册
├── generate.py                     # testset generate
├── enrich.py                       # testset enrich (AI 预审)
├── review.py                       # testset review (人工审核)
├── approve.py                      # testset approve (定稿)
├── compose.py                      # testset compose (组合复用)
├── audit.py                        # testset audit (审计)
├── info.py                         # testset list / info
└── migrate.py                      # testset migrate (旧目录→新目录)

src/testset_review/                # 审核引擎（从 scripts/ 迁移）
├── __init__.py
├── engine.py                       # 审核状态机
├── display.py                      # 终端渲染
├── ai_reviewer.py                  # AI 预审
└── pdf_viewer.py                   # PDF 定位

src/testset_composer.py            # 测试集组合器（增量/合并/抽取）
src/testset_portable.py            # 可移植测试集管理（data/test_sets/）
src/testset_audit.py               # 审计报告生成
src/test_generation/distribution.py # 公共：题目分发算法
```

### 重构文件

```
src/test_set_manager.py            # 简化职责：纯 CRUD + 校验，移除 resolve 逻辑
src/test_set_cleaner.py            # 解耦与 manager 的紧耦合
src/test_generation/generator.py   # 使用新的 distribution 模块，更新 metadata 格式
src/test_generation/supplement.py  # 委托 generator，消除重复
src/test_generator.py              # 可能废弃（由 CLI 入口替代）
```

### 废弃（deprecate）文件

```
scripts/generate_golden_testset.py   # → testset generate
scripts/review_golden_testset.py     # → testset review
scripts/ai_reviewer.py                # → 迁移到 src/testset_review/
scripts/pdf_viewer.py                 # → 迁移到 src/testset_review/
data/golden_testset/                  # → data/test_sets/（通过 testset migrate 迁移）
```

### 修改文件

```
main.py                              # 标记旧参数 deprecated，指引到 testset CLI
pixi.toml / pyproject.toml          # 注册 testset 任务
docs/user-guides/test-set-management.md  # 完全重写
config.yaml                          # 可能需要新增 test_sets_dir 配置
```

---

## 五、风险与缓解

| 风险 | 缓解 |
|------|------|
| 大规模重构导致回归 | 每个 Phase 独立提交、独立测试，Phase 间先后依赖但可独立验证 |
| review 脚本功能丢失 | Phase 3 迁移过程中保留原 script 文件，新包通过测试后再标记 deprecated |
| 旧实验脚本依赖旧路径 | `load_golden_testset()` 保留兼容层，先查新目录再回退旧目录 |
| CLI 学习成本 | 保留 `--help` 完整输出，废弃命令打印迁移指引而非直接报错 |
| 时间/精力限制 | Phase 1-4 是核心，Phase 5-7 可以渐进完成 |

---

## 六、执行顺序建议

```
Phase 1 (数据模型) → Phase 2 (生成整合) → Phase 4 (组合系统) → Phase 3 (审核通用化) → Phase 5 (审计) → Phase 6 (CLI 统一) → Phase 7 (验收)
```

Phase 3（审核通用化）放在 Phase 4 之后是因为：
- Phase 2 的生成输出 → Phase 4 先验证组合系统可用 → Phase 3 审核时面对的是已组合好的测试集
- 实际上 Phase 3 和 Phase 4 可以并行推进

---

## 七、点睛之笔：一个完整的故事

重构完成后，用户的故事线将是：

```bash
# 1. 生成第一批测试集
pixi run testset generate --meal banking --strategy hybrid --num 30
# → data/banking/test_sets/hybrid_n30.json  (quality_status: draft)

# 2. AI 预审（自动分级）
pixi run testset enrich --input data/banking/test_sets/hybrid_n30.json
# → 每道题获得 AI score + tier (A/B/C)，auto_approve A 级

# 3. 人工审核 B/C 级
pixi run testset review --input data/banking/test_sets/hybrid_n30.json --tiered
# → 逐题审，通过/拒绝/编辑，进度自动保存

# 4. 定稿 + 可移植化
pixi run testset approve --input data/banking/test_sets/hybrid_n30.json
# → quality_status: approved, portable: true
# → 文件提升到 data/test_sets/banking_reviewed_2026.json

# 5. 几周后：需要 60 题了！增量追加
pixi run testset compose \
  --base data/test_sets/banking_reviewed_2026.json \
  --supplement 30 \
  --strategy hybrid \
  --output banking_60
# → 30 题审核过的 + 30 题新生成的 → 合并去重 → 60 题
# → 旧题保持 approved，新题标记 draft

# 6. 再审核 + 再定稿
pixi run testset review --input data/banking/test_sets/banking_60.json --only-new
pixi run testset approve --input data/banking/test_sets/banking_60.json

# 7. 查看资产
pixi run testset list
pixi run testset audit --input data/test_sets/banking_60.json
```

**这是一个从合成数据到人工审核到资产复用的完整故事，每个环节都通过统一的 `testset` CLI 串联。**

---

> 计划确认后将按 Phase 顺序逐步实施，每个 Phase 完成一个原子提交。
