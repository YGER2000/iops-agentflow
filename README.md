# AgentFlow 多智能体平台

面向生产的多智能体平台，开箱即用：**智能体自动加载**、**共享/独立表架构**、统一 REST API、SSE 流式输出、**服务容器依赖注入**、Redis 会话管理（自动降级）、可选 MySQL/MongoDB/Apollo、动态 API Key 服务、**智能体隔离的日志**、**智能体隔离的数据存储**、完善的内网和外网 Docker 部署与文档。

## ✨ 核心特性

### 🤖 智能体架构
- **自动发现与加载**：扫描 `agents/` 目录，自动加载所有启用的智能体
- **配置驱动**：通过 `agent.yaml` 声明式配置，支持环境变量引用
- **热重载支持**：开发环境下支持代码热重载，无需重启
- **统一管理接口**：REST API 启用/禁用/删除/重载智能体

### 💾 数据存储
- **共享表/独立表架构**：智能体可选择共享表或独立表存储数据
- **自动模型注册**：CoreModelsLoader 和 AgentLoader 自动发现并注册模型
- **数据库自动初始化**：启动时自动创建表/集合和索引
- **灵活的数据隔离**：支持物理隔离（独立表）或逻辑隔离（共享表）

### 🔧 服务容器
- **依赖注入**：ServiceContainer 统一管理所有服务，注入到智能体
- **可选服务**：MySQL、MongoDB、Apollo 可按需启用/禁用
- **优雅降级**：Redis 连接失败自动降级到内存存储
- **生命周期管理**：自动初始化和关闭所有服务

### 💬 会话管理
- **多轮对话**：基于 thread_id 的会话机制
- **Redis 优先**：默认使用 Redis 存储会话历史，性能优越
- **内存降级**：Redis 不可用时自动切换到内存存储
- **持久化可选**：支持 MySQL/MongoDB 持久化会话历史

### 👨‍💻 开发友好
- **LangGraph/LangChain 集成**：智能体内可自定义图与节点
- **智能体隔离日志**：每个智能体独立的日志文件
- **完整文档**：快速入门、API 文档、架构设计、部署指南
- **统一 API**：标准化的调用、流式输出、健康检查接口

### 🐳 部署运维
- **Docker 双模式**：生产环境（优化体积）和开发环境（热重载）
- **内网部署支持**：完整的内网部署方案和镜像构建指南
- **健康检查**：内置健康检查端点，支持容器编排
- **非 root 运行**：安全的容器运行方式

---

## 🏗️ 架构概览

### 整体架构

```
┌─────────────────────────────────────────────────────────────┐
│                        用户请求                               │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                   FastAPI (统一 API)                         │
│         /api/v1/agent/invoke, /api/v1/agent/stream          │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│              AgentRegistry (智能体注册中心)                    │
│           根据 agent_name 路由到对应智能体实例                   │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                      智能体实例                               │
│  ┌───────────────────────────────────────────────────────┐  │
│  │ 服务容器注入 (ServiceContainer)                         │  │
│  │  ├─ LLM Service (ChatOpenAI)                          │  │
│  │  ├─ MySQL Service (可选)                               │  │
│  │  ├─ MongoDB Service (可选)                             │  │
│  │  ├─ Redis (会话存储，失败降级内存)                        │  │
│  │  └─ Apollo Service (可选)                              │  │
│  └───────────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────────┐  │
│  │ 智能体业务逻辑                                           │  │
│  │  - LangGraph/LangChain 图                              │  │
│  │  - 自定义节点和状态                                      │  │
│  │  - 提示词模板                                           │  │
│  └───────────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────────┐  │
│  │ 数据存储                                                │  │
│  │  ├─ 共享表 (多智能体共用)                                 │  │
│  │  └─ 独立表 (智能体专属，完全隔离)                          │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### 启动流程

```
应用启动
  ↓
1. 服务容器初始化 (ServiceContainer)
   ├─ 注册核心服务 (Config, LLM, ApiKey)
   ├─ 注册可选服务 (MySQL, MongoDB, Apollo)
   └─ 初始化所有服务
  ↓
2. CoreModelsLoader 加载共享模型
   ├─ 扫描 app/core/models/ 目录
   ├─ 发现 SharedConversationHistory (MySQL)
   ├─ 发现 SharedConversationHistoryMongo (MongoDB)
   └─ 注册到对应的数据库服务
  ↓
3. AgentLoader 加载智能体
   ├─ 扫描 app/agents/ 目录
   ├─ 对每个智能体：
   │   ├─ 读取 agent.yaml 配置
   │   ├─ 实例化智能体类
   │   ├─ 注入服务容器
   │   ├─ 扫描 models/ 目录（独立模型）
   │   └─ 注册模型到数据库服务
   └─ 注册到 AgentRegistry
  ↓
4. 数据库初始化
   ├─ MySQL: 创建所有表（共享表 + 各智能体独立表）
   └─ MongoDB: 使用 Motor 初始化连接并创建索引
  ↓
5. 应用就绪，开始处理请求
```

### 核心组件

| 组件 | 职责                        | 位置 |
|------|---------------------------|------|
| **ServiceContainer** | 依赖注入容器，管理所有服务的生命周期        | `app/core/container.py` |
| **AgentLoader** | 自动发现和加载智能体，触发模型注册         | `app/agents/loader.py` |
| **CoreModelsLoader** | 自动扫描和注册共享数据模型             | `app/core/models/loader.py` |
| **AgentRegistry** | 智能体注册中心，提供查询和路由           | `app/agents/registry.py` |
| **LLMService** | LLM 服务封装，支持动态 API Key     | `app/core/services/llm_service.py` |
| **MySQLService** | MySQL 连接池和模型管理            | `app/core/services/mysql_service.py` |
| **MongoDBService** | MongoDB 连接与集合/索引管理(Motor) | `app/core/services/mongodb_service.py` |

---

## 🚀 快速开始

### 前置要求

- **Python 3.12.9**
- **Redis**（推荐，不可用时自动降级到内存）
- **MySQL**（可选，启用数据持久化时需要）
- **MongoDB**（可选，启用文档存储时需要）

### 本地运行

#### 1. 安装依赖

```bash
# 创建虚拟环境
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt
```

#### 2. 配置环境变量

```bash
# 复制配置模板
cp env.example .env

# 编辑 .env，至少配置以下必填项：
# LLM_API_KEY=your_openai_api_key
# LLM_BASE_URL=https://api.openai.com/v1
# LLM_MODEL=gpt-4
```

#### 3. 启动应用

生产环境需要根据CPU的核心数，合理设置workers的数量

```python
if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.uvicorn_reload,  # 生产环境应关闭
        log_level="info",
        workers= settings.uvicorn_workers,  # 根据 CPU 核心数调整，建议设置成CPU核心数或者+1
        loop="asyncio"
    )
```

```bash
python run.py
```

#### 4. 验证启动

**查看启动日志，确认以下内容：**

```
==================================================
多智能体平台启动中...
LLM模型: gpt-4
服务地址: http://0.0.0.0:8000
==================================================

服务初始化完成:
  ✓ config
  ✓ llm
  ✓ apikey
  (如果启用了 MySQL/MongoDB，这里会显示对应服务)

正在加载核心共享模型...
发现共享 SQLAlchemy 模型: SharedConversationHistory
✓ 注册了 1 个共享 SQLAlchemy 模型

正在加载智能体...
正在加载智能体: common_agent (v1.0.0)
✓ 智能体加载成功: common_agent

=== 智能体加载完成 ===
  - common_agent: 通识问答智能体,可以回答各种常识性问题,支持多轮对话
  - cmdb_smart_query_agent: CMDB智能问数智能体,支持查询CMDB资源和资源关系
==================================================
```

**访问 API 文档：**

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

**快速测试：**

```bash
# 健康检查
curl http://localhost:8000/api/v1/health

# 查看已加载的智能体
curl http://localhost:8000/api/v1/agents

# 调用智能体
curl -X POST http://localhost:8000/api/v1/agent/invoke \
  -H 'Content-Type: application/json' \
  -d '{
    "agent_name": "common_agent",
    "message": "你好，请介绍一下你自己",
    "thread_id": "",
    "context": {}
  }'
```

**预期响应：**

```json
{
  "message": "你好！我是通识问答智能体...",
  "thread_id": "uuid-generated-thread-id",
  "metadata": {}
}
```

### 使用 Docker / Docker Compose

#### 生产环境（推荐）

```bash
# 启动
docker-compose --profile production up -d

# 查看日志
docker-compose --profile production logs -f app

# 停止
docker-compose --profile production down
```

#### 开发环境（热重载）

```bash
# 启动
docker-compose --profile development up -d

# 查看日志
docker-compose --profile development logs -f app-dev

# 停止
docker-compose --profile development down
```

更多部署细节见：[Docker 部署指南](docs/DOCKER_GUIDE.md) 和 [内网部署指南](docs/INTRANET_DEPLOYMENT.md)

---

## ⚙️ 环境变量配置

复制 `env.example` 为 `.env` 并按需修改。

### 必填配置

| 变量 | 说明 | 示例 |
|------|------|------|
| `LLM_API_KEY` | OpenAI API Key（或启用动态 API Key 服务） | `sk-...` |
| `LLM_BASE_URL` | LLM API 基础地址 | `https://api.openai.com/v1` |
| `LLM_MODEL` | 使用的模型名称 | `gpt-4` |

### 推荐配置（Redis）

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `REDIS_HOST` | Redis 主机地址 | `localhost` |
| `REDIS_PORT` | Redis 端口 | `6379` |
| `REDIS_DB` | Redis 数据库编号 | `0` |
| `REDIS_PASSWORD` | Redis 密码（可选） | 空 |

> ⚠️ **注意**：如果 Redis 不可用，系统会自动降级到内存存储，但会话历史不会持久化。

### 可选配置

#### MySQL（默认禁用）

```bash
MYSQL_ENABLED=true
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=your_password
MYSQL_DATABASE=agentflow
```

#### MongoDB（默认禁用）

```bash
MONGODB_ENABLED=true
MONGODB_HOST=localhost
MONGODB_PORT=27017
MONGODB_USER=your_user
MONGODB_PASSWORD=your_password
MONGODB_DATABASE=agentflow
```

#### 动态 API Key 服务（默认启用）

```bash
APIKEY_SERVICE_ENABLED=true
APIKEY_SERVICE_URL=http://your-api-key-service/getApikey
APIKEY_EXPIRE_SECONDS=600          # API Key 有效期
APIKEY_REFRESH_BEFORE_SECONDS=120  # 提前刷新时间
```

#### Apollo 配置中心（默认禁用）

```bash
APOLLO_ENABLED=true
APOLLO_APP_ID=your_app_id
APOLLO_CONFIG_SERVER_URL=http://localhost:8080
APOLLO_NAMESPACE=application
APOLLO_ENV=DEV
```

#### 日志配置

```bash
LOG_LEVEL=INFO                    # DEBUG, INFO, WARNING, ERROR
LOG_DIR=logs                      # 日志目录
LOG_FILE=app.log                  # 平台主日志文件
LOG_TO_FILE=true                  # 是否输出到文件
LOG_TO_CONSOLE=true               # 是否输出到控制台
```

> 📝 智能体日志会自动分离到独立文件：`logs/{agent_name}.log`

### 智能体配置

智能体可以在 `agent.yaml` 的 `config` 中使用 `${VAR_NAME}` 引用环境变量：

```yaml
# agent.yaml
config:
  cmdb_search_url: ${CMDB_SEARCH_URL}
  cmdb_token: ${CMDB_TOKEN}
```

---

## 🧩 API 概览

### 基础接口

**基础前缀：** `/api/v1`

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/health` | 健康检查 |
| GET | `/api/v1/agents` | 列出所有已加载的智能体 |
| POST | `/api/v1/agent/invoke` | 调用智能体（同步） |
| POST | `/api/v1/agent/stream` | 调用智能体（SSE 流式） |

### 智能体管理接口

**管理前缀：** `/api/v1/agent-management`

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/agent-management/agents` | 获取智能体列表（含详细信息） |
| GET | `/agent-management/agents/{agent_name}` | 获取智能体详情 |
| POST | `/agent-management/agents/{agent_name}/enable` | 启用智能体 |
| POST | `/agent-management/agents/{agent_name}/disable` | 禁用智能体 |
| DELETE | `/agent-management/agents/{agent_name}` | 删除智能体 |
| POST | `/agent-management/reload` | 重载所有智能体 |

详见：[智能体管理 API 文档](docs/AGENT_MANAGEMENT_API.md)

### 调用示例

#### 同步调用

```bash
curl -X POST http://localhost:8000/api/v1/agent/invoke \
  -H 'Content-Type: application/json' \
  -d '{
    "agent_name": "common_agent",
    "message": "什么是机器学习？",
    "thread_id": "",
    "context": {}
  }'
```

**响应：**

```json
{
  "message": "机器学习是人工智能的一个分支...",
  "thread_id": "550e8400-e29b-41d4-a716-446655440000",
  "metadata": {
    "model": "gpt-4",
    "tokens": 150
  }
}
```

#### 流式调用（SSE）

```bash
curl -N -X POST http://localhost:8000/api/v1/agent/stream \
  -H 'Content-Type: application/json' \
  -d '{
    "agent_name": "common_agent",
    "message": "什么是机器学习？",
    "thread_id": "",
    "context": {}
  }'
```

**事件类型：**
- `message`: 消息内容（增量）
- `data`: 结构化数据
- `metadata`: 元数据
- `done`: 流式结束
- `error`: 错误信息

详见：[流式输出集成指南](docs/streaming_integration.md)

---

## 🧠 内置智能体

| 智能体名称 | Agent Name | 说明 | 状态 |
|-----------|-----------|------|------|
| 通识问答智能体 | `common_agent` | 回答各种常识性问题，支持多轮对话 | ✅ 启用 |

### 查看已加载的智能体

```bash
# 通过 API 查看
curl http://localhost:8000/api/v1/agents

# 查看启动日志
# 启动时会显示：
# === 智能体加载完成 ===
#   - common_agent: 通识问答智能体...
#   - cmdb_smart_query_agent: CMDB智能问数智能体...
```

### 新增智能体
1. 在 `app/agents/` 下开发新智能体

2. 重启应用，智能体会自动加载

---

## 📁 项目结构

```
agentFlow/
├── app/                          # 应用主目录
│   ├── api/v1/                   # REST API 路由
│   │   ├── agent.py              # 智能体调用接口
│   │   └── agent_management.py  # 智能体管理接口
│   │
│   ├── agents/                   # 智能体目录
│   │   ├── base.py               # 智能体基类
│   │   ├── loader.py             # 智能体加载器（自动发现）
│   │   ├── registry.py           # 智能体注册中心
│   │   │
│   │   └── common_qa/            # 通识问答智能体
│   │       ├── agent.yaml        # 智能体配置
│   │       ├── agent.py          # 智能体实现
│   │       ├── graph.py          # LangGraph 图定义
│   │       ├── state.py          # 状态定义
│   │       ├── models/           # 独立数据模型
│   │       │   ├── __init__.py
│   │       │   ├── conversation_history.py
│   │       │   └── conversation_history_mongo.py
│   │       └── prompts/          # 提示词模板
│   │           └── system.md
│   │    
│   │
│   ├── core/                     # 核心模块
│   │   ├── config.py             # 配置管理
│   │   ├── container.py          # 服务容器（依赖注入）
│   │   ├── logger.py             # 日志系统
│   │   ├── chat_history.py       # 会话历史管理
│   │   │
│   │   ├── models/               # 共享数据模型
│   │   │   ├── __init__.py
│   │   │   ├── loader.py         # 共享模型加载器
│   │   │   ├── shared_conversation_history.py       # MySQL 共享表
│   │   │   └── shared_conversation_history_mongo.py # MongoDB 共享集合
│   │   │
│   │   └── services/             # 核心服务
│   │       ├── __init__.py
│   │       ├── interfaces.py     # 服务接口定义
│   │       ├── db_base.py        # SQLAlchemy 基类
│   │       ├── mongo_base.py     # Pydantic 文档基类 (BeaseDocument)
│   │       ├── config_service.py    # 配置服务
│   │       ├── llm_service.py       # LLM 服务
│   │       ├── mysql_service.py     # MySQL 服务
│   │       ├── mongodb_service.py   # MongoDB 服务
│   │       ├── apollo_service.py    # Apollo 配置中心
│   │       └── apikey_service.py    # 动态 API Key 服务
│   │
│   ├── schemas/                  # API 数据模型
│   │   └── agent.py              # 智能体请求/响应模型
│   │
│   └── main.py                   # FastAPI 应用入口
│
├── docs/                         # 文档目录
│   ├── SHARED_VS_INDEPENDENT_TABLES.md      # 数据存储架构详解
│   ├── CORE_MODELS_LOADER_DESIGN.md         # 模型加载器设计
│   ├── IMPLEMENTATION_SUMMARY_SHARED_TABLES.md  # 共享表实现总结
│   ├── AGENT_MANAGEMENT_API.md              # 智能体管理 API
│   ├── multi_turn_conversation.md           # 多轮对话机制
│   ├── streaming_integration.md             # 流式输出集成
│   ├── CORE_SERVICES_GUIDE.md               # 核心服务使用指南
│   ├── DYNAMIC_API_KEY.md                   # 动态 API Key
│   ├── DOCKER_GUIDE.md                      # Docker 部署
│   └── INTRANET_DEPLOYMENT.md               # 内网部署
│
├── logs/                         # 日志目录
│   ├── app.log                   # 平台主日志
│   └── common_agent.log          # 智能体日志（自动创建）
│
├── docker-compose.yml            # Docker Compose 配置
├── Dockerfile                    # 生产环境镜像
├── Dockerfile.dev                # 开发环境镜像
├── Dockerfile.base               # 基础镜像
├── Dockerfile.intra              # 内网部署镜像
├── requirements.txt              # Python 依赖
├── env.example                   # 环境变量模板
├── run.py                        # 启动脚本
└── README.md                     # 本文件
```

---

## 🛠️ 技术栈

| 类别 | 技术                         | 说明            |
|------|----------------------------|---------------|
| **语言** | Python 3.12+               | 核心语言          |
| **Web 框架** | FastAPI                    | 高性能异步 Web 框架  |
| **AI 框架** | LangChain / LangGraph      | 智能体编排和图执行     |
| **LLM** | ChatOpenAI                 | OpenAI API 封装 |
| **数据库 (SQL)** | MySQL + SQLAlchemy         | 关系型数据库和 ORM   |
| **数据库 (NoSQL)** | MongoDB + Motor + Pydantic | 文档数据库与原生驱动    |
| **缓存/会话** | Redis                      | 会话存储和缓存       |
| **配置中心** | Apollo (可选)                | 动态配置管理        |
| **容器化** | Docker + Docker Compose    | 容器部署          |

---

## 🧾 日志与数据

### 日志管理

- **平台主日志**：`logs/app.log` - 核心平台日志
- **智能体日志**：`logs/{agent_name}.log` - 每个智能体独立的日志文件，会根据智能体名称自动创建
- **加载器日志**：`logs/loader.log` - 智能体加载过程日志

日志会自动按天轮转，保留最近 7 天的日志。

### 数据存储

- **Redis**：会话历史（内存存储，重启后丢失）
- **MySQL**：持久化会话历史、业务数据（可选）
- **MongoDB**：文档型数据、大文本存储（可选）

### Docker 数据持久化

在 `docker-compose.yml` 中已配置日志目录挂载：

```yaml
volumes:
  - ./logs:/app/logs
```

建议同时挂载数据库数据目录以实现持久化。

---

## ❓ 故障排查

### Redis 连接失败

**症状：** 启动时提示 Redis 连接失败，但应用仍正常运行

**原因：** Redis 不可用时，系统自动降级到内存存储

**解决方案：**
1. 检查 Redis 服务是否启动：`redis-cli ping`
2. 检查 `.env` 中 Redis 配置是否正确
3. 如果不需要 Redis，可以忽略此警告（会话历史不持久化）

### 智能体未加载

**症状：** 调用智能体时提示"智能体不存在"

**排查步骤：**
1. 查看启动日志，确认智能体是否成功加载
2. 检查 `agent.yaml` 中 `enabled: true`
3. 检查智能体目录结构是否完整（必须有 `agent.yaml` 和 `agent.py`）
4. 查看 `logs/loader.log` 中的详细错误信息

### 数据库连接失败

**症状：** 启动时提示 MySQL/MongoDB 连接失败

**解决方案：**
1. 如果不需要数据库，设置 `MYSQL_ENABLED=false` 或 `MONGODB_ENABLED=false`
2. 检查数据库服务是否启动
3. 验证 `.env` 中的数据库连接信息
4. 检查数据库用户权限

### API Key 相关问题

**症状：** LLM 调用失败，提示 API Key 无效

**解决方案：**
1. 检查 `.env` 中 `LLM_API_KEY` 是否正确
2. 如果使用动态 API Key 服务：
   - 检查 `APIKEY_SERVICE_URL` 是否可访问
   - 查看日志确认 API Key 是否成功获取
   - 检查 API Key 有效期配置

### 模型加载失败

**症状：** 启动时提示模型注册失败，或数据库表未创建

**排查步骤：**
1. 查看启动日志中的模型加载部分
2. 确认模型类继承自 `Base`（SQLAlchemy）
3. 确认模型类定义了 `__tablename__`
4. 查看 `logs/app.log` 中的详细错误堆栈

### Docker 构建失败

**症状：** Docker 镜像构建失败或拉取依赖超时

**解决方案：**
- 使用镜像加速：参考 [Docker 部署指南](docs/DOCKER_GUIDE.md)
- 内网环境：参考 [内网部署指南](docs/INTRANET_DEPLOYMENT.md)
- 增加构建超时：`docker-compose build --build-arg TIMEOUT=600`

### 热重载不生效

**症状：** 修改代码后没有自动重启

**解决方案：**
1. 确认使用 development profile：`docker-compose --profile development up`
2. 确认源码目录正确挂载：检查 `docker-compose.yml` 中的 volumes 配置
3. 查看容器日志确认 uvicorn 是否以 reload 模式运行

---

## 📚 相关文档

### 📖 核心指南
- **[服务容器与依赖注入](docs/SERVICE_CONTAINER_GUIDE.md)** ⭐ - ServiceContainer 工作原理和在智能体中使用服务
- [智能体管理 API](docs/AGENT_MANAGEMENT_API.md) - 智能体的启用、禁用、删除、重载等管理接口
- [多轮对话机制](docs/multi_turn_conversation.md) - 会话管理和状态保持
- [流式输出集成](docs/streaming_integration.md) - SSE 流式输出完整指南
- **[Core 服务使用指南](docs/CORE_SERVICES_GUIDE.md)** - Redis、MySQL、MongoDB、Apollo 完整使用示例
- [动态 API Key 服务](docs/DYNAMIC_API_KEY.md) - 动态拉取和刷新 API Key 的配置与使用
- **[共享表 vs 独立表详解](docs/SHARED_VS_INDEPENDENT_TABLES.md)** - 数据存储架构完整指南
- **[核心模型加载器设计](docs/CORE_MODELS_LOADER_DESIGN.md)** - 模型自动加载机制

### 🔧 部署运维
- [Docker 部署指南](docs/DOCKER_GUIDE.md) - 生产环境和开发环境的 Docker 配置
- [内网部署指南](docs/INTRANET_DEPLOYMENT.md) - 内网环境部署完整方案
---

## 🔒 License

TBD
