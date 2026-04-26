# 快速上手指南

<!-- status: active -->

> 最后更新: 2026-04-18

本指南帮助你在 5 分钟内跑通 RAG 系统。

---

## 前置条件

1. **安装 pixi**：参考 [官方文档](https://pixi.prefix.dev/latest/installation/)
2. **配置环境变量**：复制 `.env.example` 为 `.env` 并填写 API Key
3. **准备数据**：将 PDF 文件放入 `data/raw/` 目录

---

## 三步上手

### 1. 单次问答

直接问一个问题，立即获得答案：

```bash
pixi run python main.py --query "中芯国际2024年的营业收入是多少？"
```

### 2. 构建向量索引

首次使用需要构建向量索引：

```bash
# 构建完整索引
pixi run python main.py --build-index

# 使用采样进行快速测试
pixi run python main.py --build-index --sample-count 5
pixi run python main.py --build-index --sample-pages 5000
pixi run python main.py --build-index --sample-ratio 0.1
```

### 3. 交互式问答

启动交互式命令行，连续提问：

```bash
pixi run interactive
# 或
pixi run python main.py --interactive
```

---

## 常用命令速查

### 问答

```bash
# 单次查询
pixi run python main.py --query "问题"

# 使用指定 Meal
pixi run python main.py --meal <meal_name> --query "问题"

# 使用不同 LLM preset
pixi run python main.py --query "问题" --llm-preset opus
```

### Meal 管理

```bash
# 创建 Meal
pixi run python main.py --create-meal --sample-count 10

# 列出所有 Meal
pixi run python main.py --list-meals

# 查看 Meal 详情
pixi run python main.py --meal-info <meal_name>
```

### 实验

```bash
# 运行实验
pixi run exp baseline

# 列出所有实验
pixi run python eval/run_experiment.py --list
```

---

## 下一步

- [系统架构](architecture.md) — 了解系统整体设计
- [CLI 参考](cli-reference.md) — 完整的命令行使用指南
- [配置参考](config-reference.md) — config.yaml 完整说明
