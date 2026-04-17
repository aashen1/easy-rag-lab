# Dev Log & TODO

当前进度：v0.1.x -- 开发并调整评测系统

下次发版计划：v0.2.0 -- 当已经实现完善的自动化评测系统，标定出一条合理且稳定的baseline后可以考虑发版

上次发版：v0.1.0 -- 跑通了基本RAG问答，评测系统还有bug

## 2026-04-18

- [x] 完成 [code-issues-fix-requirements.md](.trae\documents\code-issues-fix-requirements.md)  2:38 周六
- [x] TODO Backlog 大清洗（本次对话）
  - [x] 修复 PytestCollectionWarning（TestCaseResult 添加 `__test__ = False`）
  - [x] 修复 src/chunker.py 尾随空格
  - [x] 删除 test_e2e_experiment.py 重复的本地 temp_project_dir fixture
  - [x] 修改 conftest.py mock_embedder 使用固定向量
  - [x] 清洗 CHANGELOG.md，移除已修复的 Known Issues
  - [x] 标注 test-review-suggestions.md 各建议状态
  - [x] 标注 test-future-directions.md 各方向状态
  - [x] 标注 02-code-quality-standards.md 各问题状态
  - [x] 标注 04-known-bugs-functional-issues.md 各问题状态
  - [x] 标注 05-open-source-readiness.md 各项状态
  - [x] 更新 TODO.md


## 2026-04-17-[alldone]

- [x] 修好llm报告的功能（可能是超上下文了？）3:53 周五
- [x] 优化LLM报告的提示词，现在生成的报告开头有一句"好的……"在那里
- [x] 增加token统计的功能，要求与美团的相一致（增加tiktoken统计功能；增加每个基模的折算系数，加入配置中）
- [x] 验收上面的token统计的功能，要求与美团的相一致，并标定折算系数 5:26 周五 （完美！本地和网页端给出的token总消耗**完全一致**！）
- [x] 把问题也一并加到实验资产包里，除非单个问题集的大小超过10MB（这个阈值增加在总配置里）（其实已经做了，之前没发现）
- [x] 更新CHANGELOG 4:23 周五
- [x] 增加pixi task，快捷指令开测试 2:53 周五
- [x] 修复测试问题 3:15 周五（后注：这条写得有点随意了，回看都想不起到底是什么问题了，还是要写得更有指向性一点）
- [x] 大任务：测试系统重构（2026年4月18日 2:46 周六，完成，准备merge）
  - [x] spec模式生成三份文档 6:31 周五
  - [x] spec模型执行完成 8:08 周五
  - [x] 新对话进行初步验收 8:08 周五
  - [x] 验收回归测试，看AI写的实现能否保证未来更新过程中，基本的功能不出岔子 9:01 周五（好好好好好，AI修完bug还知道来我这边打个钩）
  - [x] 注意到`pixi run pytest tests/ -m "integration" -v`说是真实测试，实际并不会产生API调用，得排查 9:01 周五（这个打钩和下面的说明也是AI写的）
    - 问题原因：测试函数内部直接调用 `pytest.skip()`，没有实现真实逻辑
    - 解决方案：
      1. 添加环境变量 `RUN_INTEGRATION_TESTS=true` 控制是否运行
      2. 实现前置条件检查（API key、Meal、向量索引）
      3. 实现真实的 `RAGPipeline.query()` 调用
    - 验证结果：✅ 已产生真实 API 调用（见 token 使用量日志）
    - 注意：测试失败是数据问题（golden_qa.json 期望茅台数据，但 Meal 只有格力数据），非功能问题
  - [x] 全面评估目前的pytest设计是否有用，是否应当精简 8:27 周五（看AI写的code view蛮详细的，应该可以）
  - [x] 参考 [test-future-directions.md](.trae\documents\test-future-directions.md) 当中方向一的Step3-6，手调一下golden测试集问题，保证meal当中的数据源能正确检索到测试集的问题答案
  - [x] 最后过一遍所有的测试方式，没大问题的话就可以把这一项结了，然后发个补丁版本（其实叫功能版本更合适，不过现在大版本是0，所以推后到了第三位）（不过或许可以叫`v0.1.5.0`之类的？改天和AI聊聊能不能这么写） 2:39 周六
    - [x] `pixi run pytest tests/ -m "not integration" -v`，所有不产生API调用的，10s左右
    - [x] `pixi run pytest tests/ -m "integration" -v`，会产生API调用，跑一次2-3万token，180s
- [x] 那个output_dir到底什么东西 （2:22 周六，修好了）
  - 8:07 周五 又出现了，重新纳入排查
  - 现象：时不时就会多出一个空文件夹在根目录里。
  - [x] 对策：准备照Qwen的建议，埋个钩子把mkdir系统函数替换了，来进行排查 23:45 周五，埋好了，并且写入了日志，跑一会儿之后看能不能抓到
  - [x] 通过埋钩子替换mkdir系统函数的方式抓出来了，并已整理为笔记并提交


## Backlog

> 以下各项已在对应文档中标注状态。建议开新对话以 plan/spec 模式逐项推进。

- [ ] 重写问题生成策略，与chunk解耦，看看考虑做成基于整个MD的 📋 已安排（建议 spec 模式，规模大）
- [ ] 实验报告`baseline.json`当中记录AI回答的`"sources"`字段，给出的来源都是大的总文件名，这策略没啥用感觉，看看能不能细化到标题头或者chunk啥的。这个不着急，跟问题生成策略一块重写 📋 已安排（与上一项耦合）
- [ ] 现在的项目结构是不是有点乱？根目录里还放着两个`.py`文件 📋 已安排（建议 spec 模式，需评估影响范围）
- [ ] 优化"新用户"链路的性能。PDF→parse→chunk→embed这一条还是要测一下速，有些地方可以提速或者上GPU的也做一下 📋 已安排（建议 plan 模式，需性能基准测试）
- [ ] [test-future-directions.md](.trae\documents\test-suite\test-future-directions.md)当中提到了"**可扩展性**：新功能上线只需向 `golden_qa.json` 添加条目"，验证一下，如果是换了问题生成策略是否也可以 ⏳ 待定（依赖黄金测试集落地）
- [ ] 目前的日志系统似乎并不是"应记尽记"的，比如pytest有些就不会体现在日志里（例如`pixi run pytest tests/ -m "not integration" -v`就不会被记录），分析一下怎么做符合最佳实践 📋 已安排（建议 plan 模式，需调研最佳实践）
- [ ] 完成 [test-review-suggestions.md](.trae\documents\test-suite\test-review-suggestions.md) 📋 已安排（已标注状态：3项✅已修复，8项📋已安排，建议逐项 spec）
- [ ] 完成 [test-future-directions.md](.trae\documents\test-suite\test-future-directions.md) 📋 已安排（已标注状态：1项⏳待定，5项📋已安排，建议逐项 spec）
- [ ] 全面更新文档，主要改善可读性，例如把README作为唯一且易读的文档入口，整理一些过时的文档，精简总的文档数目，重新组织目前文档的存放路径 📋 已安排（建议 spec 模式，规模大）
- [ ] `exp_configs`当中一些模板yaml是不是有可能已经不符合现在版本了？等实验系统新版做好可以整个整理一下。📋 已安排（建议 spec 模式）
- [ ] `pixi run pytest tests/ -m "integration" -v` 需要`10 passed, 385 deselected, 1 warning in 182.32s (0:03:02)`，用的时间有点久啊，是不是测试策略不对？看看是否有优化空间 📋 已安排（建议 plan 模式，需分析瓶颈）
- [ ] [02-code-quality-standards.md](.trae\code_reviews\v0.1.5\02-code-quality-standards.md) 优化代码 📋 已安排（已标注状态：2项✅已修复，5项📋已安排，建议 spec 模式）
- [ ] 更新README和CLAUDE两份文件，同步到目前版本，并调整开发重心 📋 已安排（建议 plan 模式）
- [ ] [04-known-bugs-functional-issues.md](.trae\code_reviews\v0.1.5\04-known-bugs-functional-issues.md) 核实并修复 📋 已安排（已标注状态：4项✅已修复，9项📋已安排，剩余项建议逐项 spec）
- [x] 把CHANGELOG清洗一下，只写做了的，不写bug和TODO ✅ 已完成（2026-04-18）
- [ ] 核实 [05-open-source-readiness.md](.trae\code_reviews\v0.1.5\05-open-source-readiness.md) 📋 已安排（已标注状态：3项✅已修复，4项❌已弃用，其余📋已安排）
- [ ] 实验资产包里有没有一并记录CLI里面打印的那个很漂亮的token summary，以及详细到每个问题消耗多少token的全部token消耗数据？一打眼好像都没看见 📋 已安排（需了解现有资产包结构）
