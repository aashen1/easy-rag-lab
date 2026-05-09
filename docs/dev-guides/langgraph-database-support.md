# LangGraph 数据库支持指南

> 基于 LangChain 官方文档（2026-05-09 调研），系统梳理 LangGraph 对各类数据库的支持状态、使用方式与选型建议。

---

## 1. 架构概览

LangGraph 的持久化层由两个独立但互补的子系统构成：

| 子系统 | 接口 | 职责 | 生命周期 |
|--------|------|------|----------|
| **Checkpointer（短期记忆）** | `BaseCheckpointSaver` | 保存图执行状态快照（checkpoint），支持 human-in-the-loop、时间旅行、容错恢复 | 绑定到 thread（会话线程） |
| **Store（长期记忆）** | `BaseStore` | 跨线程持久化用户/应用级数据，支持语义搜索 | 跨 thread 持久 |

两者在 `graph.compile()` 时分别注入：

```python
graph = builder.compile(
    checkpointer=checkpointer,  # 短期：线程内状态
    store=store,                # 长期：跨线程记忆
)
```

---

## 2. Checkpointer（短期记忆）支持矩阵

### 2.1 官方 Checkpointer 一览

| 后端 | 包名 | 仓库 | 同步类 / 异步类 | 适用场景 |
|------|------|------|-----------------|----------|
| **In-Memory** | `langgraph-checkpoint`（内置） | langchain-ai/langgraph | `InMemorySaver` | 开发调试 |
| **SQLite** | `langgraph-checkpoint-sqlite` | langchain-ai/langgraph | `SqliteSaver` / `AsyncSqliteSaver` | 本地实验、轻量工作流 |
| **PostgreSQL** | `langgraph-checkpoint-postgres` | langchain-ai/langgraph | `PostgresSaver` / `AsyncPostgresSaver` | **生产首选** |
| **MongoDB** | `langgraph-checkpoint-mongodb` | langchain-ai/langchain-mongodb | `MongoDBSaver` / `AsyncMongoDBSaver` | 已有 MongoDB 基础设施 |
| **Redis** | `langgraph-checkpoint-redis` | redis-developer/langgraph-redis | `RedisSaver` / `AsyncRedisSaver` | 低延迟、缓存友好 |
| **AWS (DynamoDB/Bedrock/Valkey)** | `langgraph-checkpoint-aws` | langchain-ai/langchain-aws | — | AWS 原生生态 |
| **Azure Cosmos DB NoSQL** | `langchain-azure-cosmosdb` | langchain-ai/langchain-azure | `CosmosDBSaverSync` / `CosmosDBSaver` | Azure 云原生 |
| **CockroachDB** | `langchain-cockroachdb` | cockroachdb/langchain-cockroachdb | — | 分布式 SQL |
| **Aerospike** | `langgraph-checkpoint-aerospike` | aerospike-community/aerospike-langgraph | — | 高吞吐 KV |

### 2.2 Checkpointer 接口规范

所有 checkpointer 必须实现 `BaseCheckpointSaver` 接口：

**基础方法（必需）：**

| 方法 | 说明 |
|------|------|
| `aput` | 存储一个 checkpoint |
| `aput_writes` | 存储 pending writes（中间写入） |
| `aget_tuple` | 根据 config 获取 checkpoint 元组 |
| `alist` | 列出匹配条件的 checkpoint |
| `adelete_thread` | 删除线程 |

**扩展方法（可选）：**

| 方法 | 说明 | 缺失时回退 |
|------|------|-----------|
| `adelete_for_runs` | 删除特定 run 的 checkpoint | 回滚 multitask 策略不可用 |
| `acopy_thread` | 复制线程 | 慢速回退（逐条重插） |
| `aprune` | 修剪线程历史 | 历史修剪不可用 |

### 2.3 PostgreSQL Checkpointer 详解（生产推荐）

安装：

```bash
pip install -U "psycopg[binary,pool]" langgraph langgraph-checkpoint-postgres
```

同步用法：

```python
from langgraph.checkpoint.postgres import PostgresSaver

DB_URI = "postgresql://user:pass@localhost:5432/mydb?sslmode=disable"

with PostgresSaver.from_conn_string(DB_URI) as checkpointer:
    checkpointer.setup()  # 首次使用需建表
    graph = builder.compile(checkpointer=checkpointer)
    result = graph.invoke(
        {"messages": [{"role": "user", "content": "hello"}]},
        config={"configurable": {"thread_id": "1"}},
    )
```

异步用法：

```python
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

async with AsyncPostgresSaver.from_conn_string(DB_URI) as checkpointer:
    await checkpointer.setup()
    graph = builder.compile(checkpointer=checkpointer)
    async for chunk in graph.astream(
        {"messages": [{"role": "user", "content": "hello"}]},
        config={"configurable": {"thread_id": "1"}},
        stream_mode="values",
    ):
        chunk["messages"][-1].pretty_print()
```

### 2.4 MongoDB Checkpointer 详解

安装：

```bash
pip install -U pymongo langgraph langgraph-checkpoint-mongodb
```

前提条件：需要 MongoDB 副本集（standalone mongod 不支持），可用 MongoDB Atlas 或自建 replica set。

```python
from langgraph.checkpoint.mongodb import MongoDBSaver

MONGODB_URI = "localhost:27017"

with MongoDBSaver.from_conn_string(MONGODB_URI) as checkpointer:
    graph = builder.compile(checkpointer=checkpointer)
```

异步版本：`AsyncMongoDBSaver`（从 `langgraph.checkpoint.mongodb.aio` 导入）。

### 2.5 Redis Checkpointer 详解

安装：

```bash
pip install -U langgraph langgraph-checkpoint-redis
```

```python
from langgraph.checkpoint.redis import RedisSaver

DB_URI = "redis://localhost:6379"

with RedisSaver.from_conn_string(DB_URI) as checkpointer:
    checkpointer.setup()  # 首次使用
    graph = builder.compile(checkpointer=checkpointer)
```

### 2.6 自定义 Checkpointer

当官方实现不满足需求时，可继承 `BaseCheckpointSaver` 自定义实现：

```python
import contextlib
from langgraph.checkpoint.base import BaseCheckpointSaver

class MyCheckpointer(BaseCheckpointSaver):
    def __init__(self):
        super().__init__()

@contextlib.asynccontextmanager
async def generate_checkpointer():
    async with AsyncSqliteSaver.from_conn_string("./checkpoints.db") as saver:
        await saver.setup()
        yield saver
```

在 `langgraph.json` 中注册：

```json
{
    "checkpointer": {
        "path": "./src/agent/checkpointer.py:generate_checkpointer"
    }
}
```

**合规性测试**：自定义 checkpointer 必须通过 conformance 测试套件：

```bash
pip install langgraph-checkpoint-conformance
```

```python
import asyncio
from langgraph.checkpoint.conformance import checkpointer_test, validate

@checkpointer_test(name="MyCheckpointer")
async def my_checkpointer():
    async with MyCheckpointer(...) as saver:
        yield saver

async def main():
    report = await validate(my_checkpointer)
    report.print_report()
    assert report.passed_all_base()

asyncio.run(main())
```

---

## 3. Store（长期记忆）支持矩阵

### 3.1 Store 后端一览

| 后端 | 类 | 适用场景 | 语义搜索 |
|------|-----|---------|---------|
| **In-Memory** | `InMemoryStore` | 开发调试 | 支持（配置 index） |
| **PostgreSQL** | `PostgresStore` / `AsyncPostgresStore` | **生产首选**，内置 pgvector | 支持（pgvector） |
| **MongoDB** | `MongoDBStore` | 已有 MongoDB 基础设施 | — |
| **Redis** | `RedisStore` | 低延迟场景 | — |
| **SQLite** | `AsyncSqliteStore` | 本地/测试 | 支持（配置 index） |
| **自定义** | 继承 `BaseStore` | 任意后端 | 取决于实现 |

### 3.2 Store 基本用法

```python
from langgraph.store.memory import InMemoryStore
import uuid

store = InMemoryStore()

user_id = "1"
namespace = (user_id, "memories")

memory_id = str(uuid.uuid4())
memory = {"food_preference": "I like pizza"}
store.put(namespace, memory_id, memory)

memories = store.search(namespace)
print(memories[-1].value)  # {'food_preference': 'I like pizza'}
```

### 3.3 语义搜索

Store 支持基于嵌入的语义搜索，通过配置 `index` 参数启用：

```python
from langchain.embeddings import init_embeddings
from langgraph.store.memory import InMemoryStore

store = InMemoryStore(
    index={
        "embed": init_embeddings("openai:text-embedding-3-small"),
        "dims": 1536,
        "fields": ["$"]  # 索引所有字段；也可指定 ["text", "metadata.title"]
    }
)

memories = store.search(
    namespace,
    query="What does the user like to eat?",
    limit=3
)
```

在部署环境中，通过 `langgraph.json` 配置语义搜索：

```json
{
    "store": {
        "index": {
            "embed": "openai:text-embedding-3-small",
            "dims": 1536,
            "fields": ["$"]
        }
    }
}
```

也可使用自定义嵌入函数：

```json
{
    "store": {
        "index": {
            "embed": "path/to/embedding_function.py:aembed_texts",
            "dims": 1536,
            "fields": ["$"]
        }
    }
}
```

### 3.4 PostgreSQL Store（生产推荐）

```python
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.store.postgres import PostgresStore

DB_URI = "postgresql://user:pass@localhost:5432/mydb?sslmode=disable"

with PostgresSaver.from_conn_string(DB_URI) as checkpointer, \
     PostgresStore.from_conn_string(DB_URI) as store:
    checkpointer.setup()
    store.setup()
    graph = builder.compile(checkpointer=checkpointer, store=store)
```

### 3.5 自定义 Store

```python
import contextlib
from langgraph.store.base import BaseStore

@contextlib.asynccontextmanager
async def generate_store():
    async with AsyncSqliteStore.from_conn_string(
        "./custom_store.sql",
        index=IndexConfig(
            dims=1536,
            embed=embeddings,
            fields=["$"],
        ),
    ) as store:
        await store.setup()
        yield store
```

在 `langgraph.json` 中注册：

```json
{
    "store": {
        "path": "./src/agent/store.py:generate_store"
    }
}
```

> **注意**：自定义 Store 当前为 Alpha 状态，可能在小版本更新中引入破坏性变更。

---

## 4. LangSmith Agent Server 中的数据库配置

当使用 LangSmith Agent Server 部署时，数据库由平台自动管理，开发者无需手动配置 checkpointer。

### 4.1 默认架构

Agent Server 持久化三类数据，默认全部使用 PostgreSQL：

| 数据类型 | 说明 | 默认后端 |
|---------|------|---------|
| 核心资源 | assistants、threads、runs、cron jobs | PostgreSQL（必须） |
| Checkpoints（短期记忆） | 图执行状态快照 | PostgreSQL（可切换为 MongoDB 或自定义） |
| Store（长期记忆） | 跨线程记忆 | PostgreSQL（可替换为自定义） |

### 4.2 切换 Checkpointer 后端为 MongoDB

在 `langgraph.json` 中配置：

```json
{
    "checkpointer": {
        "backend": "mongo",
        "ttl": {
            "strategy": "delete",
            "default_ttl": 43200,
            "sweep_interval_minutes": 10
        }
    }
}
```

或通过环境变量：

```bash
LS_DEFAULT_CHECKPOINTER_BACKEND=mongo
LS_MONGODB_URI="mongodb://user:password@host:27017/langgraph?replicaSet=rs0"
```

> **重要**：即使切换 checkpointer 后端为 MongoDB，PostgreSQL 仍然是必需的（用于 threads、runs、assistants、crons 和 memory store）。

### 4.3 Kubernetes 部署（Helm Chart）

内置 MongoDB 支持（v0.2.6+）：

```yaml
# 开发/测试：内置 MongoDB
mongo:
  enabled: true
  resources:
    requests:
      cpu: 500m
      memory: 1Gi
  persistence:
    size: 8Gi

# 生产：外部 MongoDB
mongo:
  enabled: true
  external:
    enabled: true
    connectionUrl: "mongodb://user:password@mongo.example.net:27017/langgraph?replicaSet=rs0"
```

---

## 5. TTL（数据生命周期管理）

### 5.1 Checkpoint TTL

在 `langgraph.json` 中配置：

```json
{
    "checkpointer": {
        "ttl": {
            "strategy": "delete",
            "sweep_interval_minutes": 60,
            "default_ttl": 43200
        }
    }
}
```

| 参数 | 说明 |
|------|------|
| `strategy` | `"delete"`：删除整个线程及关联数据；`"keep_latest"`：保留线程和最新 checkpoint，删除旧数据 |
| `sweep_interval_minutes` | 扫描过期数据的间隔（分钟） |
| `default_ttl` | 默认存活时间（分钟），43200 = 30 天 |

### 5.2 Store Item TTL

```json
{
    "store": {
        "ttl": {
            "refresh_on_read": true,
            "sweep_interval_minutes": 120,
            "default_ttl": 10080
        }
    }
}
```

| 参数 | 说明 |
|------|------|
| `refresh_on_read` | 读取时是否重置过期计时器（默认 true） |
| `sweep_interval_minutes` | 扫描间隔 |
| `default_ttl` | 默认存活时间（分钟），10080 = 7 天 |

### 5.3 Per-Thread TTL

可通过 SDK 为特定线程设置 TTL：

```python
thread = await client.threads.create(
    ttl={
        "strategy": "delete",
        "ttl": 43200
    }
)
```

---

## 6. 存储优化：DeltaChannel（Beta）

### 6.1 问题

默认情况下，LangGraph 在每个 super-step 都会写入所有 state channel 的完整值。对于长期运行的线程（如多轮对话），消息列表不断增长，导致 checkpoint 线性膨胀。

### 6.2 解决方案

`DeltaChannel`（需 langgraph>=1.2，Beta）仅存储增量 delta，而非完整累积值：

```python
from typing import Annotated, Sequence
from langgraph.channels import DeltaChannel

def my_reducer(state: list[str], writes: Sequence[list[str]]) -> list[str]:
    result = list(state)
    for write in writes:
        result.extend(write)
    return result

class State(TypedDict):
    messages: Annotated[list[str], DeltaChannel(my_reducer)]
```

### 6.3 读取延迟控制

DeltaChannel 读取需要回放完整写入历史（O(N)）。通过 `snapshot_frequency` 参数定期写入完整快照：

```python
class State(TypedDict):
    messages: Annotated[
        list[str],
        DeltaChannel(my_reducer, snapshot_frequency=5),
    ]
```

- `snapshot_frequency=K`：每 K 步写一次完整快照，读取最多回放 K 步
- 值越大 → 存储越省 → 读取越慢
- 值越小 → 读取越快 → 存储越大
- `None`（默认）：不写快照，适合短线程或极少读取

### 6.4 Bulk Reducer 要求

DeltaChannel 的 reducer 必须是**批量 reducer**（bulk reducer），且满足结合律：

```python
reducer(reducer(state, [xs]), [ys]) == reducer(state, [xs, ys])
```

常见批量 reducer 模板：

```python
# 列表追加
def list_reducer(state: list[Any], writes: Sequence[list[Any]]) -> list[Any]:
    result = list(state)
    for write in writes:
        result.extend(write)
    return result

# 字典合并
def dict_reducer(state: dict, writes: Sequence[dict]) -> dict:
    result = dict(state)
    for write in writes:
        result.update(write)
    return result
```

---

## 7. 序列化

### 7.1 默认序列化器

`JsonPlusSerializer` 是默认序列化器，底层使用 ormsgpack + JSON，支持：
- LangChain / LangGraph 原语
- datetime、enum 等常见类型

### 7.2 Pickle 回退

对于 ormsgpack 不支持的类型（如 Pandas DataFrame），可启用 pickle 回退。

---

## 8. 选型建议

### 8.1 按场景推荐

| 场景 | Checkpointer | Store | 理由 |
|------|-------------|-------|------|
| 本地开发/调试 | `InMemorySaver` | `InMemoryStore` | 零配置，即开即用 |
| 本地实验（需持久化） | `SqliteSaver` | `AsyncSqliteStore` | 单文件，无需外部服务 |
| 生产部署（通用） | `PostgresSaver` | `PostgresStore` | 功能最全，生态成熟，pgvector 语义搜索 |
| 生产部署（已有 MongoDB） | `MongoDBSaver` | `MongoDBStore` | 复用现有基础设施 |
| 生产部署（低延迟） | `RedisSaver` | `RedisStore` | 内存级延迟 |
| AWS 云原生 | `langgraph-checkpoint-aws` | — | DynamoDB/Bedrock/Valkey |
| Azure 云原生 | `CosmosDBSaver` | — | Cosmos DB NoSQL |

### 8.2 关键决策因素

1. **是否需要语义搜索？** → PostgreSQL（pgvector）是唯一内置向量搜索的生产级方案
2. **是否需要跨线程记忆？** → 必须配置 Store（而非仅 Checkpointer）
3. **对话线程是否很长？** → 考虑 DeltaChannel 优化存储
4. **是否使用 LangSmith Agent Server？** → PostgreSQL 自动管理，无需手动配置
5. **合规性要求？** → 自定义 Checkpointer 需通过 conformance 测试

---

## 9. 与本项目的关联

本项目（ash-easy-rag）是金融研报 RAG 问答系统，以下是与 LangGraph 数据库支持的关联分析：

| 需求 | LangGraph 对应能力 | 建议 |
|------|-------------------|------|
| 多轮对话状态保持 | Checkpointer（短期记忆） | 开发用 InMemorySaver，生产用 PostgresSaver |
| 用户偏好跨会话记忆 | Store（长期记忆） | 配置 PostgresStore + 语义搜索 |
| RAG 检索结果缓存 | Store + 语义搜索 | 利用 pgvector 做相似文档去重 |
| 对话历史审计 | Checkpoint TTL + get_state_history | 配置 keep_latest 策略 |
| 容错恢复 | Checkpointer 自动 pending writes | 生产环境必备 |

---

## 10. 参考链接

- [LangGraph Persistence 官方文档](https://docs.langchain.com/oss/python/langgraph/persistence)
- [LangGraph Add Memory](https://docs.langchain.com/oss/python/langgraph/add-memory)
- [Checkpointer Integrations](https://docs.langchain.com/oss/python/integrations/checkpointers/index)
- [Configure Checkpointer Backend](https://docs.langchain.com/langsmith/configure-checkpointer)
- [Custom Checkpointer](https://docs.langchain.com/langsmith/custom-checkpointer)
- [Custom Store](https://docs.langchain.com/langsmith/custom-store)
- [Semantic Search](https://docs.langchain.com/langsmith/semantic-search)
- [Configure TTL](https://docs.langchain.com/langsmith/configure-ttl)
- [DeltaChannel (Beta)](https://docs.langchain.com/oss/python/langgraph/pregel#deltachannel-beta)
