1. 这是软件工程中一个非常经典的话题，业界有比较成熟的共识。让我系统讲一下。

   ---

   ## 测试金字塔与分层策略

   ### 经典三层模型

   业界最广泛采用的是 **Mike Cohn 的测试金字塔**，从底到顶分为三层：

   ```
           ╱  E2E / Integration  ╲        ← 少量，慢
          ╱   Service / Unit-IO    ╲       ← 适量，中等
         ╱    Pure Unit Tests       ╲      ← 大量，极快
   ```

   但放在 **CI/CD + Hook 的语境**下，更实用的分法是按**触发时机和耗时预算**来分层：

   ---

   ## 按 Hook/CI 触发时机的分层

   ### 第 1 层：Commit 级（pre-commit / pre-push）

   | 维度         | 共识                                               |
   | ------------ | -------------------------------------------------- |
   | **耗时预算** | **< 10 秒**（pre-commit），**< 60 秒**（pre-push） |
   | **跑什么**   | 纯单元测试（无 IO、无网络、无数据库）              |
   | **核心原则** | 开发者不能感受到"等待"，否则会 `--no-verify` 跳过  |
   | **典型内容** | 逻辑计算、数据转换、参数校验、序列化/反序列化      |
   | **排除什么** | 文件读写、网络请求、数据库、重计算 fixture         |

   > **经验法则**：pre-commit 钩子超过 10 秒，开发者就会开始跳过它。Google 的内部实践是 commit 级检查控制在 **5 秒以内**。

   ### 第 2 层：Push / PR 级（pre-push 或 CI 的快速阶段）

   | 维度         | 共识                                                         |
   | ------------ | ------------------------------------------------------------ |
   | **耗时预算** | **1 ~ 5 分钟**                                               |
   | **跑什么**   | 单元测试 + 轻量集成测试（本地 IO、内存数据库、mock 服务）    |
   | **核心原则** | 推代码前确认"我的改动没破坏已有功能"                         |
   | **典型内容** | 第 1 层全部 + 文件解析测试、索引构建测试、pipeline 串联测试（mock 外部 API） |
   | **排除什么** | 真实外部 API 调用、长时间运行的评估测试                      |

   ### 第 3 层：Merge / CI 完整阶段（post-merge 或 CI pipeline）

   | 维度         | 共识                                                  |
   | ------------ | ----------------------------------------------------- |
   | **耗时预算** | **5 ~ 15 分钟**（可接受），**> 30 分钟**（需要优化）  |
   | **跑什么**   | 全量测试，包括集成测试和端到端测试                    |
   | **核心原则** | 合入主分支前确保整体系统完整性                        |
   | **典型内容** | 第 2 层全部 + 真实 API 调用、数据库集成、跨模块端到端 |
   | **典型手段** | 并行化（多 runner）、增量测试（只跑受影响模块）       |

   ### 第 4 层：夜间 / 定期（Nightly / Scheduled）

   | 维度         | 共识                                             |
   | ------------ | ------------------------------------------------ |
   | **耗时预算** | **无硬限制**，通常 30 分钟 ~ 数小时              |
   | **跑什么**   | 性能测试、压力测试、全量回归、安全扫描、评估基准 |
   | **核心原则** | 不阻塞日常开发，但能发现慢退化                   |

   ---

   ## 各大公司的实践参考

   | 公司                 | Commit 级              | PR 级                      | Merge/CI 级              |
   | -------------------- | ---------------------- | -------------------------- | ------------------------ |
   | **Google**           | < 5s（只跑受影响测试） | ~2-5 min                   | ~10-15 min（大规模并行） |
   | **Meta**             | < 10s                  | ~3 min                     | ~10 min                  |
   | **GitHub**           | lint + typecheck ~3s   | ~5 min                     | ~15 min                  |
   | **典型 Python 项目** | ruff + 纯单元 ~5s      | pytest -m "not slow" ~2min | 全量 pytest ~10min       |

   ---

   ## 回到你的项目

   你现在的配置：

   | 阶段       | 实际内容                      | 耗时  | 对标             |
   | ---------- | ----------------------------- | ----- | ---------------- |
   | pre-commit | ruff lint + format + 通用检查 | ~3-5s | ✅ 合理           |
   | post-merge | 全量 1338 个测试              | ~30s  | ⚠️ 偏快但阶段不对 |

   **核心问题不是 30 秒太慢，而是测试只放在了 post-merge（最晚的阶段），缺少中间层。**

   ### 建议的分层改造

   ```
   pre-commit    →  ruff lint/format（现状，✅ 不动）
                    + 纯单元测试（新增，< 10s）

   post-merge    →  全量测试（现状 30s，加 xdist 可降到 ~10s）

   (可选) pre-push → 中等测试（1-3 min，未来加）
   ```

   具体来说，用 pytest marker 做分层：

   ```python
   # pyproject.toml
   markers = [
       "integration: marks tests that call external APIs",
       "slow: marks tests that take > 1s (IO, file parsing, etc.)",
   ]
   ```

   然后：

   ```toml
   # pixi.toml
   [tasks.test]           # post-merge：全量（排除 integration）
   cmd = "pytest tests/ -m 'not integration' -n auto --tb=short -q"

   [tasks.test-fast]      # pre-commit：纯单元（排除 integration + slow）
   cmd = "pytest tests/ -m 'not integration and not slow' --tb=short -q"
   ```

   钩子配置：

   ```yaml
   # .pre-commit-config.yaml 新增
   - repo: local
     hooks:
       - id: fast-test
         name: fast unit tests
         entry: pixi run test-fast
         language: system
         stages: [pre-commit]
         always_run: true
         pass_filenames: false
   ```

   这样 **commit 时只跑纯逻辑测试（< 10s），merge 后跑全量（~10s with xdist）**，体验和安全性都好。

   ---

   ## 一句话总结

   > **业界共识：commit 级 < 10s，push/PR 级 < 5min，merge/CI 级 < 15min。关键不是"测试要多快"，而是"每个阶段只跑该跑的那一层"。** 你现在缺的是 commit 级的快速测试层，而不是让 post-merge 的测试变快。
