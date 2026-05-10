* [x] comparative/reasoning/multi\_fact 类型使用 2048 max\_tokens，其他类型保持 1024

* [x] 专有名词"电子行业"在 evidence 包含"电子"时匹配成功（去后缀匹配）

* [x] 专有名词完全不匹配时仍记录 issue

* [x] adversarial 类型答案中 LLM 推理产生的数值不触发 issue

* [x] adversarial 类型答案中引用的文档原始数据仍需 evidence 支撑

* [x] 中文引用 >= 15 字符通过长度检查

* [x] 英文/混合引用 >= 30 字符通过长度检查

* [x] missing 类型使用独立 prompt 生成，一次成功率显著提升

* [x] 答案字数超过类型限制时截断到最近句号并标记 answer\_truncated

* [x] 答案字数在限制内时原样保留

* [x] 未覆盖数值在文档中找到时自动追加 evidence（match\_type=auto\_supplemented）

* [x] 未覆盖数值在文档中找不到时保留 issue 不追加 evidence

* [ ] 端到端生成 20 题测试集，ground\_truth\_confidence >= 0.90

* [x] 端到端生成 20 题测试集，answer\_evidence\_issues 总数比修复前减少 50%+

* [x] pixi run lint 通过

* [x] pixi run python -m pytest tests/test\_golden\_testset.py -v 全部通过
