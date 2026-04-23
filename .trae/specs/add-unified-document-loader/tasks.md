# Tasks

- [x] Task 1: 创建统一文档加载器模块
  - [x] SubTask 1.1: 定义 `LoadedDocument` 数据类
  - [x] SubTask 1.2: 定义 `DocumentLoader` 抽象基类
  - [x] SubTask 1.3: 实现 `MarkdownLoader` 加载器
  - [x] SubTask 1.4: 实现 `PagesJsonLoader` 加载器
  - [x] SubTask 1.5: 实现 `get_loader()` 工厂函数

- [x] Task 2: 实现懒加载机制
  - [x] SubTask 2.1: 实现 `LazyDocumentLoader` 类
  - [x] SubTask 2.2: 实现 `_build_index()` 方法构建文件索引
  - [x] SubTask 2.3: 实现 `get()` 方法按需加载文档
  - [x] SubTask 2.4: 实现 `iter_documents()` 迭代器方法

- [x] Task 3: 重构 test_generator 使用新加载器
  - [x] SubTask 3.1: 修改 `_load_full_documents()` 使用 `LazyDocumentLoader`
  - [x] SubTask 3.2: 保持向后兼容，确保现有功能不变

- [x] Task 4: 添加单元测试
  - [x] SubTask 4.1: 测试 `MarkdownLoader` 加载功能
  - [x] SubTask 4.2: 测试 `PagesJsonLoader` 加载功能
  - [x] SubTask 4.3: 测试 `LazyDocumentLoader` 懒加载功能
  - [x] SubTask 4.4: 测试重构后的 `_load_full_documents()` 功能

- [x] Task 5: 代码质量检查
  - [x] SubTask 5.1: 运行 `pixi run lint` 检查代码格式
  - [x] SubTask 5.2: 修复所有 lint 错误

# Task Dependencies

- [Task 2] depends on [Task 1]
- [Task 3] depends on [Task 2]
- [Task 4] depends on [Task 3]
- [Task 5] depends on [Task 4]
