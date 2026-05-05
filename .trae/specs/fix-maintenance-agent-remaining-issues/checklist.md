# Checklist

## P0 核心功能正确性

### P0-1 经验存储持久化
- [x] ExperienceStore 支持持久化到 JSON 文件
- [x] 经验在进程重启后可通过 get_all_experiences 检索到
- [x] CLI 和 Streamlit 使用相同的持久化路径（data/agent_experience.json）
- [x] 持久化写入使用 tempfile + os.replace() 保证原子性
- [x] 现有经验检索/保存功能不受影响
- [x] 测试通过：经验保存→重新加载→检索

### P0-2 白名单硬拦截
- [x] delete_count >= threshold 时 delete_source 被硬拦截（返回错误 ToolMessage，非 interrupt）
- [x] 硬拦截消息包含已删除数量和提示
- [x] delete_count < threshold 时行为不变（interrupt 警告）
- [x] update_meal 字段白名单完整（只允许 description 和 tags）
- [x] prompt 包含累计操作影响说明
- [x] 测试通过

### P0-3 报告工具不依赖 LLM 传参
- [x] generate_maintenance_report_tool 只要求 LLM 传入 session_id
- [x] execution_log、stage_history、diagnosis 等从 state 自动注入
- [x] 报告内容完整，不依赖 LLM 记忆
- [x] 工具 docstring 明确标注自动填充参数
- [x] 测试通过

### P0-4 Phase C 迁移
- [x] parse_all_pdfs_unified() 内部调用 parse_pdf() 共享单元
- [x] 实验系统和 Agent 对同一 PDF 得到一致结果
- [x] 实验系统测试全部通过
- [x] 无行为回归

## P1 功能增强

### P1-1 全量模式行为差异化
- [x] 全量模式 prompt 包含批量操作指导
- [x] 全量模式使用更高的删除阈值（如 10 vs 3）
- [x] 全量模式自动列出 Meal 和索引状态
- [x] 轻量模式行为不受影响
- [x] 测试通过

### P1-2 CLI 快捷指令完整
- [x] :parse <parser> 指令已实现
- [x] :back <stage> 指令已实现
- [x] :compare 指令已实现
- [x] :report 指令已实现
- [x] :history 指令已实现（直接打印，不调用 LLM）
- [x] :status 指令已实现（直接打印，不调用 LLM）
- [x] :mode light/full 指令已实现
- [x] 启动提示显示所有可用指令
- [x] 测试通过

### P1-3 Streamlit interrupt 恢复
- [x] interrupt 后页面刷新可恢复批准/拒绝按钮
- [x] 批准/拒绝后 Agent 正常继续执行
- [x] interrupt 状态记录在 st.session_state 中
- [ ] 手动测试通过

### P1-4 MaintenanceState TypedDict
- [x] MaintenanceState 改为 TypedDict 子类
- [x] IDE 类型提示正常工作
- [x] LangGraph 图编译和执行正常
- [x] 全量测试通过
- [x] 如果 spike 不通过，有记录说明限制

### P1-5 移除 _agent_store 全局变量
- [x] _agent_store 全局变量已移除
- [x] store 通过 LangGraph 内置机制注入
- [x] agent_node 和 tool_node 通过 config 获取 store
- [x] 多实例并发不冲突
- [x] 测试通过

## P2 代码质量

### P2-1 execution_log 结构化
- [x] execution_log 条目为 JSON 格式，包含 tool、time、status 字段
- [x] 维修报告操作时间线包含时间和工具列
- [x] 测试通过

### P2-2 Streamlit 报告展示/下载
- [x] 报告在主区域以 Markdown 渲染展示
- [x] 提供下载按钮
- [x] 测试通过

### P2-3 search_experiences 启用或标注
- [x] search_experiences 被实际调用，或 docstring 明确标注为待启用
- [x] 测试通过

### P2-4 evaluate_single Phase A 标注
- [x] evaluate_single docstring 标注 Phase A 基础指标限制
- [x] 测试通过
