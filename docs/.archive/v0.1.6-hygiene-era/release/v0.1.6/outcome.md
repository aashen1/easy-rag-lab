# v0.1.6 交付对照

<!-- status: archived -->

> ⚠️ **文档状态**：v0.1.6 历史交付记录，所列任务均已完成。本文档仅保留供历史参考。

> 归档日期: 2026-04-18

---

## 版本主题

项目卫生 + 文档系统重构

---

## 主要变更

### 1. 文档系统重构

- **新目录结构**：创建 `docs/guides/`、`docs/reviews/`、`docs/archive/`、`docs/troubleshooting/` 四级目录
- **版本历史系统**：添加 `docs/version-history.md` 记录版本演进
- **Backlog 系统**：添加 `docs/backlog.md` 统一管理待做事项
- **Review 系统**：每个版本创建 `docs/reviews/vX.X.X/` 目录存放验收文档
- **归档机制**：将已完成的 specs、历史文档移入 `docs/archive/`
- **文档清洗**：清理根级文档、重命名中文文件名、删除冗余文档

### 2. 代码质量改进

- **类型标注**：为所有公共函数添加类型标注
- **Docstrings**：为核心模块、数据管理模块、工具模块添加 docstrings
- **代码重构**：提取 `detect_document_category` 工具函数消除重复代码
- **小修复**：修复尾部空白、PytestCollectionWarning 等

### 3. 测试改进

- **新增测试**：添加 MRR 重复 source、get_llm_config 缺失 API key、get_collection_info 错误路径等测试
- **测试修复**：使用公共 API 替代私有 `_records`、使用固定向量使 mock_embedder 确定性
- **测试清理**：移除重复的 temp_project_dir fixture

### 4. 功能增强

- **动态 metric 配置**：`run_evaluation` 支持动态配置评测指标
- **进度显示**：`Embedder.embed_texts` 支持 `show_progress` 参数

---

## 统计数据

| 指标 | 数值 |
|------|------|
| 提交数量 | 47 |
| 文档变更 | 30+ 文件 |
| 代码变更 | 15+ 文件 |
| 新增测试 | 5+ |

---

## 技术债清理

| 项目 | 状态 |
|------|------|
| 类型标注缺失 | ✅ 已完成 |
| Docstrings 缺失 | ✅ 已完成 |
| 测试覆盖不足 | ✅ 已改进 |
| 文档结构混乱 | ✅ 已重构 |

---

## 下版本方向

- [v0.2.0 开发方向](next-direction.md)
