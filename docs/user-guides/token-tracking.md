# Token 追踪与成本估算

<!-- status: active -->

> 最后更新: 2026-04-18

本文档介绍 Token 追踪功能的使用方法。

---

## 概述

Token 追踪系统用于：
- 统计 LLM 调用的 token 消耗
- 估算 API 调用成本
- 在查询结果中显示详细 token 用量

---

## 使用方式

### 查询时自动追踪

使用 `--query` 或交互模式时，系统自动追踪 token 消耗：

```bash
pixi run python main.py --query "问题"

# 输出包含 token 用量
# Token Usage:
#   Input:  1,234
#   Output: 567
#   Total:  1,801
#     System Prompt: 456
#     Contexts:      654
#     Query:         124
```

### 交互模式会话统计

交互模式退出时显示会话总消耗：

```bash
pixi run python main.py --meal <meal_name>

# 退出时显示
# Session Token Usage: in=12,345 out=5,678 total=18,023
```

---

## 配置

### config.yaml 中的成本配置

```yaml
token_cost:
  models:
    LongCat-Flash-Lite:
      input_price: 0.000001     # 每千 token 输入价格
      output_price: 0.000002    # 每千 token 输出价格
    claude-3-opus-20240229:
      input_price: 0.015
      output_price: 0.075
    claude-3-5-sonnet-20241022:
      input_price: 0.003
      output_price: 0.015
    claude-3-haiku-20240307:
      input_price: 0.00025
      output_price: 0.00125
```

---

## 实验报告中的 Token 统计

实验报告包含每个 variant 的 token 消耗统计：

```json
{
  "token_usage": {
    "input_tokens": 12345,
    "output_tokens": 5678,
    "total_tokens": 18023,
    "estimated_cost": 0.0123
  }
}
```

---

## 相关文档

- [配置参考](config-reference.md)
- [实验系统](experiment-system.md)
