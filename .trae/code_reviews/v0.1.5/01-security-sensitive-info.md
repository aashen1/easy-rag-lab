# 安全与敏感信息审查

审查日期：2026-04-18
审查范围：全项目文件（.py, .yaml, .json, .md, .toml）

---

## 审查结论

**整体评价：良好。** 未发现真实 API Key 或密钥泄露，敏感信息管理基本规范。但存在 1 处中等风险问题需修复。

---

## 1. 硬编码本地路径泄露（中等风险）

### 问题

`pixi.toml` 第 105 行包含硬编码的本地绝对路径：

```toml
find-links = [
    { path = 'B:/xxxxxx' },
]
```

### 泄露信息

- Windows 用户名：`xxxxx`
- 本地磁盘结构：B 盘存在用户目录
- 开发环境特征：使用本地 torch CUDA whl 缓存

### 修复建议

方案 A（推荐）：注释掉并改为环境变量引用

```toml
find-links = [
    # 本地 torch CUDA whl 缓存，按需配置
    # 取消注释并设置环境变量 TORCH_CACHE_DIR 后生效
    # { path = { env = "TORCH_CACHE_DIR" } },
]
```

方案 B：直接注释掉，在 README 中说明如何配置

```toml
find-links = [
    # { path = 'B:/xxxxxxx' },  # 已移除，按需自行配置
]
```

---

## 2. 个人邮箱暴露（低风险）

### 问题

`pixi.toml` 第 2 行：

```toml
authors = ["xxxx <xxxxxxx.com>"]
```

### 分析

这是 pixi 项目元数据中的作者信息，属于有意公开的内容。开源后此邮箱将暴露给所有用户，可能收到垃圾邮件。

### 建议

- 如果愿意公开此邮箱作为联系方式，无需修改
- 如果不希望暴露，可改为匿名格式：`authors = ["xxx"]` 或使用专用开源邮箱

---

## 3. 硬编码 API 端点（低风险）

> 这个可以修下

### 问题

以下 3 处硬编码了 `https://api.longcat.chat/` 作为默认 API 端点：

| 文件 | 行号 | 内容 |
|------|------|------|
| `src/utils.py` | 80 | `base_url = get_env_var("LLM_BASE_URL", "https://api.longcat.chat/")` |
| `src/generator.py` | 35 | `base_url: str = "https://api.longcat.chat/anthropic"` |
| `eval/experiment_reporter.py` | 873 | `base_url=self.llm_base_url or "https://api.longcat.chat/anthropic"` |

### 分析

- `https://api.longcat.chat/` 是公开的第三方 LLM API 服务端点，不属于机密信息
- 但硬编码为默认值意味着：如果服务地址变更，需要修改多处代码
- 项目规范要求"所有超参数、模型名、路径等均写入 config.yaml，禁止在代码中硬编码"

### 建议

统一在 `config.yaml` 中管理 API 端点，代码中仅引用配置值：

```yaml
llm_presets:
  default:
    base_url: "LLM_BASE_URL"  # 环境变量名
    fallback_url: "https://api.longcat.chat/"  # 配置中的默认值
```

---

## 4. Bearer Token 传递模式（低风险）

### 问题

`src/generator.py` 第 50-53 行和 `eval/experiment_reporter.py` 第 871-875 行使用了 `api_key="dummy"` + Bearer header 的模式：

```python
client = anthropic.Anthropic(
    api_key="dummy",
    default_headers={"Authorization": f"Bearer {api_key}"}
)
```

### 分析

这是为了适配 LongCat API 的认证方式（Anthropic SDK 要求 api_key 参数，但 LongCat 使用 Bearer token 认证）。虽然 `"dummy"` 本身不是泄露，但这种变通方式存在隐患：

- 如果日志级别设置不当，`api_key` 参数值可能被记录
- 调试时可能意外暴露真实 token
- 不符合直觉，新贡献者可能误以为这就是认证方式

### 建议

在代码中添加注释说明此模式的用意，或考虑封装为统一的客户端工厂函数。

---

## 5. API Key 管理审计（合规）

### 检查结果

所有 `api_key` 引用均为以下三种合规情况之一：

| 类型 | 示例 | 文件 |
|------|------|------|
| 测试 fixture | `"test-key"`, `"dummy"` | tests/test_utils.py, tests/test_generator.py 等 |
| 环境变量名引用 | `"LLM_API_KEY"`, `"LLM_KEY_OPUS"` | config.yaml, src/utils.py |
| 文档占位符 | `"your-api-key-here"`, `"ak_yourkey"` | README.md, .env.example |

**无真实 API Key 泄露。** ✅

---

## 6. 敏感数据文件审计（合规）

| 文件 | 内容 | 风险 |
|------|------|------|
| `eval/test_data.json` | 10 条金融研报问答对，无个人身份信息 | 无 |
| `exp_configs/*.yaml` | 实验参数（chunk_size, overlap, seed 等），无密钥 | 无 |
| `notes/*.md` | 开发笔记，无密钥泄露 | 无 |

---

## 7. IP 地址与内网地址审计（合规）

搜索 `\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}` 模式，匹配结果仅为版本号（如 `pymupdf4llm = ">=1.27.2.2, <2"`），非 IP 地址。**无内网地址泄露。** ✅

---

## 8. 密钥字符串前缀审计（合规）

搜索 `["']sk-|["']ak-|["']key-|["']sk_|["']AK|["']SECRET` 模式，无匹配。`.env.example` 中的 `ak_yourkey` 等为占位符模板。**无真实密钥字符串。** ✅
