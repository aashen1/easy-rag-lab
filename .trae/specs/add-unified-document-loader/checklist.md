# Checklist

## 统一文档加载器模块

- [x] `LoadedDocument` 数据类定义正确，包含 name, content, source_path, metadata 字段
- [x] `DocumentLoader` 抽象基类定义正确，包含 `load()` 和 `load_all()` 抽象方法
- [x] `MarkdownLoader` 能正确加载 `.md` 文件并返回 `LoadedDocument` 对象
- [x] `PagesJsonLoader` 能正确加载 `.pages.json` 文件，拼接所有页面文本
- [x] `get_loader()` 工厂函数能根据文件扩展名自动选择加载器

## 懒加载机制

- [x] `LazyDocumentLoader` 初始化时仅构建文件索引，不加载文档内容
- [x] `get()` 方法能按需加载文档并缓存
- [x] `iter_documents()` 方法能迭代访问文档，避免一次性加载所有文档
- [x] 缓存机制工作正常，避免重复加载同一文档

## 重构 test_generator

- [x] `_load_full_documents()` 使用 `LazyDocumentLoader` 加载文档
- [x] 重构后功能与原有实现保持一致
- [x] 支持 `.md` 和 `.pages.json` 两种格式
- [x] 向后兼容，现有测试通过

## 单元测试

- [x] `MarkdownLoader` 测试覆盖正常加载、空文件、编码错误等场景
- [x] `PagesJsonLoader` 测试覆盖正常加载、JSON 解析错误、缺失字段等场景
- [x] `LazyDocumentLoader` 测试覆盖懒加载、缓存、迭代器等场景
- [x] `_load_full_documents()` 测试覆盖两种格式的文档加载

## 代码质量

- [x] 所有公共函数有类型标注
- [x] 所有公共函数有 docstring
- [x] 代码通过 `pixi run lint` 检查
- [x] 异常处理完善，IO 操作有 try/except
