# 共享表与独立表机制详解

## 概述

### 什么是共享表和独立表？

AgentFlow 多智能体平台支持两种数据存储架构：

- **共享表（Shared Tables）**：多个智能体共用同一个数据表/集合，通过 `agent_name` 字段区分不同智能体的数据
- **独立表（Independent Tables/私有表）**：每个智能体拥有专属的数据表/集合，数据完全隔离

### 为什么需要这种架构设计？

不同的智能体有不同的数据需求：

1. **通用场景**：大部分智能体的会话历史结构相似，使用共享表可以：
   - 简化数据库管理
   - 便于跨智能体数据分析
   - 减少表/集合数量

2. **特殊场景**：某些智能体可能需要：
   - 特殊的数据结构和字段
   - 完全隔离的数据存储
   - 独立的性能优化策略
   - 不同的数据生命周期管理

### 适用场景概览

| 特性 | 共享表 | 独立表 |
|------|--------|--------|
| 数据隔离性 | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| 跨智能体访问 | ⭐⭐⭐⭐⭐ | ⭐ |
| 维护成本 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ |
| 结构灵活性 | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| 统一数据分析 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ |

**推荐选择：**
- **默认使用共享表** - 适合大多数通用场景
- **特殊需求使用独立表** - 如特殊数据结构、严格隔离、巨大数据量等

---

## 核心机制详解

### 自动加载流程

AgentFlow 在应用启动时自动扫描和注册所有数据模型，整个流程如下(以oceanbase/mysql为例)：

```
┌─────────────────────────────────────────────────────────────┐
│ 应用启动                                                      │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ 1. 服务容器初始化                                            │
│    - MySQL Service                                          │
│    - LLM Service                                            │
│    - 其他服务...                                             │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ 2. CoreModelsLoader 加载共享表模型（优先）                   │
│    ├─ 扫描 app/core/models/ 目录                            │
│    ├─ 发现 SharedConversationHistory (MySQL)               │
│    └─ 注册到对应的服务                                       │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ 3. AgentLoader 加载智能体及其独立表模型                      │
│    ├─ 扫描 app/agents/ 目录                                 │
│    ├─ 对每个智能体：                                         │
│    │   ├─ 加载智能体类                                       │
│    │   ├─ 注入服务容器                                       │
│    │   └─ 执行 _discover_and_register_models()             │
│    │       ├─ 检查是否存在 models/ 目录                     │
│    │       ├─ 扫描目录中的模型类                            │
│    │       ├─ 识别 SQLAlchemy 模型│
│    │       └─ 注册到对应的服务                              │
│    └─ 注册到 AgentRegistry                                  │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ 4. 数据库初始化                                              │
│    ├─ MySQL: 创建所有表（共享表 + 各智能体独立表）           │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ 应用就绪，可以接收请求                                       │
└─────────────────────────────────────────────────────────────┘
```

### 共享表加载机制

#### 工作原理

共享表模型由 `CoreModelsLoader` 类负责加载，该加载器在智能体加载之前运行。

**核心代码位置：** `app/core/models/loader.py`

#### 加载过程

1. **扫描共享模型目录**
   ```python
   # CoreModelsLoader 扫描 app/core/models/ 目录
   models_module = importlib.import_module('app.core.models')
   ```

2. **识别模型类**
   - 检查是否继承自 `Base`（SQLAlchemy 模型）
   - 验证是否定义了 `__tablename__` 或 `Settings.name`

3. **注册到服务**
   ```python
   # SQLAlchemy 模型注册到 MySQL Service
   mysql_service.register_models(Base.metadata)
   ```

#### 日志输出示例

```
正在加载核心共享模型...
发现共享 SQLAlchemy 模型: SharedConversationHistory (表: shared_conversation_history)
✓ 注册了 1 个共享 SQLAlchemy 模型
```

### 独立表加载机制

#### 工作原理

独立表模型在智能体加载时自动发现和注册，由 `AgentLoader` 类的 `_discover_and_register_models()` 方法负责。

**核心代码位置：** `app/agents/loader.py`

#### 加载过程

1. **检查 models 目录**
   ```python
   # 对每个智能体，检查是否存在 models/ 目录
   models_dir = agent_dir / "models"
   if models_dir.exists() and (models_dir / "__init__.py").exists():
       # 继续扫描
   ```

2. **动态导入模型模块**
   ```python
   module_path = f"app.agents.{agent_dir.name}.models"
   models_module = importlib.import_module(module_path)
   ```

3. **扫描并识别模型**
   - 遍历模块中的所有类
   - 使用 `_is_sqlalchemy_model()` 检查 SQLAlchemy 模型

4. **注册到服务**
   ```python
   # 与共享表类似，注册到对应服务
   mysql_service.register_models(Base.metadata)
   ```

#### 日志输出示例

```
正在加载智能体: common_qa (v1.0.0)
已导入智能体 [common_qa] 的 models 模块
发现 SQLAlchemy 模型: CommonQAConversationHistory
智能体 [common_qa] 注册了 1 个 SQLAlchemy 模型
✓ 智能体加载成功: common_qa
```

### 关键区别

| 特性 | 共享表加载 | 独立表加载 |
|------|-----------|-----------|
| 加载时机 | 智能体加载前（优先） | 智能体加载时 |
| 负责类 | `CoreModelsLoader` | `AgentLoader` |
| 扫描路径 | `app/core/models/` | `app/agents/{agent_name}/models/` |
| 表命名 | `shared_*` | `{agent_name}_*` |
| 是否需要 agent_name 字段 | 是 | 否 |

---

## 使用指南

### 使用共享表

共享表适用于多个智能体共用相同数据结构的场景。

#### 步骤 1：在智能体中导入共享模型

在智能体的 `models/__init__.py` 中导入共享模型：

```python
# app/agents/your_agent/models/__init__.py
"""智能体数据模型 - 使用共享表"""

from app.core.models import SharedConversationHistory

# 可选：为了代码简洁，可以使用别名
ConversationHistory = SharedConversationHistory

__all__ = ['ConversationHistory']
```

#### 步骤 2：在智能体代码中使用（必须包含 agent_name）

**MySQL 使用示例：**

```python
# app/agents/your_agent/agent.py
from .models import ConversationHistory

class YourAgent(AgentBase):
    async def save_message(self, thread_id: str, message: str):
        """保存消息到共享表"""
        async with self.mysql.get_session() as session:
            msg = ConversationHistory(
                thread_id=thread_id,
                agent_name=self.name,  # ⚠️ 关键：必须设置 agent_name
                role="user",
                content=message,
                extra_metadata=None
            )
            session.add(msg)
            await session.commit()
```

#### 步骤 3：查询时过滤 agent_name

查询共享表时，必须同时过滤 `thread_id` 和 `agent_name`：

```python
from sqlalchemy import select

async def get_history(self, thread_id: str, limit: int = 10):
    """查询当前智能体的历史记录"""
    async with self.mysql.get_session() as session:
        result = await session.execute(
            select(ConversationHistory)
            .where(
                ConversationHistory.thread_id == thread_id,
                ConversationHistory.agent_name == self.name  # ⚠️ 必须过滤
            )
            .order_by(ConversationHistory.created_at.desc())
            .limit(limit)
        )
        history = result.scalars().all()
        return history
```

### 使用独立表（私有表）

独立表适用于有特殊数据结构需求或需要完全隔离的场景。

#### 步骤 1：创建 models/ 目录结构

在智能体目录下创建 `models/` 目录：

```
app/agents/your_agent/
  ├── __init__.py
  ├── agent.py
  ├── agent.yaml
  └── models/
      ├── __init__.py
      └── conversation_history.py       # MySQL 模型
```

#### 步骤 2：定义独立表模型

**MySQL 模型示例：**

```python
# app/agents/your_agent/models/conversation_history.py
"""MySQL 独立会话历史模型"""

from typing import Optional
from sqlalchemy import String, Text, Integer, Index
from sqlalchemy.orm import Mapped, mapped_column
from app.core.services.db_base import Base, TimestampMixin


class YourAgentConversationHistory(Base, TimestampMixin):
    """YourAgent 独立会话历史表"""
    __tablename__ = 'agentflow_your_agent_conversation_history'  # 独立表名
    
    # 主键
    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
        comment="主键ID"
    )
    
    # 会话ID
    thread_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
        comment="会话线程ID"
    )
    
    # 角色
    role: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="消息角色"
    )
    
    # 消息内容
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="消息内容"
    )
    
    # 可选的元数据字段
    extra_metadata: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="元数据（JSON）"
    )
    
    # 索引定义
    __table_args__ = (
        Index('idx_thread_id_created', 'thread_id', 'created_at'),
        {'comment': 'YourAgent 独立会话历史表'}
    )
    
    def __repr__(self) -> str:
        return (
            f"<YourAgentConversationHistory("
            f"id={self.id}, "
            f"thread_id={self.thread_id}, "
            f"role={self.role})>"
        )
```


#### 步骤 3：在 models/__init__.py 中导出

```python
# app/agents/your_agent/models/__init__.py
"""YourAgent 数据模型 - 使用独立表"""

from .conversation_history import YourAgentConversationHistory

__all__ = [
    'YourAgentConversationHistory'
]
```

#### 步骤 4：在智能体中使用（无需 agent_name）

**MySQL 使用示例：**

```python
# app/agents/your_agent/agent.py
from .models import YourAgentConversationHistory

class YourAgent(AgentBase):
    async def save_message(self, thread_id: str, message: str):
        """保存消息到独立表"""
        async with self.mysql.get_session() as session:
            msg = YourAgentConversationHistory(
                thread_id=thread_id,
                role="user",
                content=message
                # 无需 agent_name，因为是独立表
            )
            session.add(msg)
            await session.commit()
```

**查询示例（无需过滤 agent_name）：**

```python
from sqlalchemy import select

async def get_history(self, thread_id: str, limit: int = 10):
    """查询历史记录"""
    async with self.mysql.get_session() as session:
        result = await session.execute(
            select(YourAgentConversationHistory)
            .where(YourAgentConversationHistory.thread_id == thread_id)
            # 无需过滤 agent_name
            .order_by(YourAgentConversationHistory.created_at.desc())
            .limit(limit)
        )
        history = result.scalars().all()
        return history
```

---

## 完整实例对比

### 实例 1：common_qa 使用独立表

**文件结构：**

```
app/agents/common_qa/
├── __init__.py
├── agent.py
├── agent.yaml
├── models/
│   ├── __init__.py
│   └── conversation_history.py
├── prompts/
│   └── system.md
└── state.py
```

**模型定义（MySQL）：**

```python
# app/agents/common_qa/models/conversation_history.py
from sqlalchemy import String, Text, Integer, Index
from sqlalchemy.orm import Mapped, mapped_column
from app.core.services.db_base import Base, TimestampMixin


class CommonQAConversationHistory(Base, TimestampMixin):
    """Common QA 会话历史记录表"""
    __tablename__ = 'agentflow_common_qa_conversation_history'  # 独立表名
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    thread_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(50), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    
    __table_args__ = (
        Index('idx_thread_id_created', 'thread_id', 'created_at'),
        {'comment': 'Common QA 智能体会话历史记录表'}
    )
```

**使用代码：**

```python
# app/agents/common_qa/agent.py
from .models import CommonQAConversationHistory

async with self.mysql.get_session() as session:
    user_msg = CommonQAConversationHistory(
        thread_id=thread_id,
        role="user",
        content=message
    )
    session.add(user_msg)
    await session.commit()
```


### 对比总结

| 特性 | common_qa（独立表） | 使用共享表的智能体 |
|------|--------------------|--------------------|
| 表名 | `agentflow_common_qa_conversation_history` | `agentflow_shared_conversation_history` |
| agent_name 字段 | 无 | 有，必须设置 |
| 查询过滤 | 只需 thread_id | 需要 thread_id + agent_name |
| 数据隔离 | 完全隔离 | 逻辑隔离 |
| 表结构灵活性 | 可自由定制 | 受共享表结构限制 |

---

## 表命名规范

为了保持代码库的一致性和可维护性，请遵循以下命名规范：

### MySQL 表命名

| 表类型 | 命名格式                            | 示例 |
|--------|---------------------------------|------|
| 共享表 | `agentflow_shared_<table_name>` | `agentflow_shared_conversation_history`<br>`agentflow_shared_user_preferences`<br>`agentflow_shared_analytics_events` |
| 独立表 | `agentflow_<agent_name>_<table_name>`     | `agentflow_common_qa_conversation_history`<br>`agentflow_cmdb_conversation_history`<br>`agentflow_code_review_results` |

### MongoDB 集合命名

| 集合类型 | 命名格式 | 示例 |
|---------|---------|------|
| 共享集合 | `agentflow_shared_<collection_name>` | `agentflow_shared_conversation_history`<br>`agentflow_shared_user_sessions`<br>`agentflow_shared_audit_logs` |
| 独立集合 | `agentflow_<agent_name>_<collection_name>` | `agentflow_common_qa_conversation_history`<br>`agentflow_document_analysis_results`<br>`agentflow_image_generation_history` |

### 类命名规范

| 类型 | 命名格式 | 示例 |
|------|---------|------|
| 共享 SQLAlchemy 模型 | `Shared<ModelName>` | `SharedConversationHistory` |
| 独立 SQLAlchemy 模型 | `<AgentName><ModelName>` | `CommonQAConversationHistory`<br>`CMDBConversationHistory` |
| 共享 Mongo文档模型 | `Shared<ModelName>Mongo` | `SharedConversationHistoryMongo` |
| 独立 Mongo文档模型 | `<AgentName><ModelName>Mongo` | `CommonQAConversationHistoryMongo` |

---

## 验证和调试

### 查看启动日志

启动应用时，注意观察以下日志输出，确认模型是否正确加载。

#### 共享模型加载日志

```
正在加载核心共享模型...
开始扫描核心共享模型目录: /path/to/app/core/models
已导入 app.core.models 模块
发现共享 SQLAlchemy 模型: SharedConversationHistory (表: shared_conversation_history)
✓ 注册了 1 个共享 SQLAlchemy 模型
```

#### 智能体模型加载日志

```
正在加载智能体...
开始扫描智能体目录: /path/to/app/agents
正在加载智能体: common_qa (v1.0.0)
已导入智能体 [common_qa] 的 models 模块
发现 SQLAlchemy 模型: CommonQAConversationHistory
智能体 [common_qa] 注册了 1 个 SQLAlchemy 模型
✓ 智能体加载成功: common_qa
```

#### 数据库初始化日志

```
正在初始化数据库...
  ✓ MySQL 表创建完成
```

### 检查数据库

#### MySQL 检查

连接到 MySQL 数据库后，使用以下命令验证：

```sql
-- 查看所有表
SHOW TABLES;

-- 应该看到类似：
-- +------------------------------------+
-- | Tables_in_database                 |
-- +------------------------------------+
-- | shared_conversation_history        |
-- | common_qa_conversation_history     |
-- | cmdb_conversation_history          |
-- +------------------------------------+

-- 查看共享表结构
DESC shared_conversation_history;

-- 应该看到 agent_name 字段：
-- +------------------+--------------+------+-----+---------+
-- | Field            | Type         | Null | Key | Default |
-- +------------------+--------------+------+-----+---------+
-- | id               | int          | NO   | PRI | NULL    |
-- | thread_id        | varchar(255) | NO   | MUL | NULL    |
-- | agent_name       | varchar(100) | NO   | MUL | NULL    |
-- | role             | varchar(50)  | NO   |     | NULL    |
-- | content          | text         | NO   |     | NULL    |
-- | extra_metadata   | text         | YES  |     | NULL    |
-- | created_at       | datetime     | NO   |     | NULL    |
-- | updated_at       | datetime     | NO   |     | NULL    |
-- +------------------+--------------+------+-----+---------+

-- 查看独立表结构
DESC common_qa_conversation_history;

-- 应该看到没有 agent_name 字段

-- 查看索引
SHOW INDEX FROM shared_conversation_history;
SHOW INDEX FROM common_qa_conversation_history;
```

### 常见问题排查

#### 问题 1：表没有自动创建

**症状：** 启动后查询数据库，找不到预期的表/集合

**排查步骤：**
1. 检查启动日志，确认模型是否被发现和注册
2. 检查数据库连接配置（`.env` 文件）
3. 确认 MySQL 服务已启用（`MYSQL_ENABLED=true`）
4. 查看错误日志，寻找数据库初始化失败的信息

#### 问题 2：独立表模型未被加载

**症状：** 日志中没有显示智能体模型注册信息

**排查步骤：**
1. 确认 `models/` 目录存在且包含 `__init__.py`
2. 确认模型类正确继承自 `Base`
3. 确认模型类定义了 `__tablename__` 或 `Settings.name`
4. 确认模型类在 `models/__init__.py` 中正确导出

#### 问题 3：共享表查询返回空结果

**症状：** 明明保存了数据，但查询时找不到

**排查步骤：**
1. 检查保存时是否设置了 `agent_name=self.name`
2. 检查查询时是否同时过滤了 `thread_id` 和 `agent_name`
3. 直接在数据库中查询，确认数据是否真的存在
4. 检查 `agent_name` 的值是否与预期一致

---

## 常见问题（FAQ）

### Q1: 共享表和独立表可以混用吗？

**A:** 可以。平台完全支持混合使用：
- 某些智能体可以使用共享表
- 某些智能体可以使用独立表
- 甚至同一个智能体可以同时使用共享表和独立表存储不同类型的数据

例如：
```python
# 使用共享表存储会话历史
from app.core.models import SharedConversationHistory

# 使用独立表存储特定业务数据
from .models import CMDBQueryCache
```

### Q2: 如何选择使用哪种方式？

**A:** 基于以下决策树：

```
是否需要特殊的数据结构？
  ├─ 是 → 使用独立表
  └─ 否 ↓
  
是否需要完全隔离的数据存储？
  ├─ 是 → 使用独立表
  └─ 否 ↓
  
是否需要跨智能体访问数据？
  ├─ 是 → 使用共享表
  └─ 否 ↓
  
是否希望简化数据库管理？
  ├─ 是 → 使用共享表
  └─ 否 → 两者皆可，推荐共享表
```

**简单规则：** 如果没有特殊需求，默认使用共享表。

### Q3: 独立表会自动创建吗？

**A:** 是的，完全自动。只要：
1. 在智能体的 `models/` 目录下定义了模型类
2. 模型类正确继承自 `Base`
3. 模型类在 `models/__init__.py` 中导出

AgentLoader 会自动发现并注册这些模型，数据库初始化时会自动创建表/集合。

### Q4: 如何验证表是否创建成功？

**A:** 三种方法：
1. **查看启动日志** - 查找模型注册和数据库初始化的日志
2. **查询数据库** - 使用 `SHOW TABLES;`（MySQL）
3. **尝试插入数据** - 通过 API 调用智能体，查看是否能正常保存数据

### Q5: 模型文件必须在 models/ 目录下吗？

**A:** 是的，这是约定。AgentLoader 只扫描 `app/agents/{agent_name}/models/` 目录。如果模型定义在其他位置，不会被自动发现和注册。

### Q6: 共享表的 agent_name 如何确保唯一性？

**A:** `agent_name` 从智能体的 `self.name` 属性获取，该值在智能体初始化时设置，由开发者保证唯一性：

```python
class YourAgent(AgentBase):
    def __init__(self):
        super().__init__(
            name="your_agent",  # 必须唯一
            description="..."
        )
```

在 `agent.yaml` 中也定义了唯一的名称，平台会确保不会加载重名的智能体。

### Q7: 可以在运行时动态切换使用共享表还是独立表吗？

**A:** 不可以。表的选择在应用启动时确定，运行时无法切换。如果需要迁移，需要：
1. 修改模型定义和导入
2. 迁移数据（如有必要）
3. 重启应用

### Q8: 共享表的性能会不会受影响？

**A:** 在合理规模下，性能影响很小。关键是：
- 正确建立索引（特别是 `thread_id + agent_name` 的复合索引）
- 查询时始终包含 `agent_name` 过滤条件
- 定期清理历史数据，控制表大小

如果单个智能体的数据量特别大（百万级以上），建议使用独立表。

---

## 相关文档

- [核心服务指南](./CORE_SERVICES_GUIDE.md) - MySQL、MongoDB、Redis 完整使用示例
- [多轮对话机制](./multi_turn_conversation.md) - 会话管理和状态保持
- [智能体开发指南](./AGENT_MANAGEMENT_API.md) - 智能体开发完整指南

---

## 总结

AgentFlow 的共享表与独立表机制提供了灵活的数据存储方案：

✅ **共享表**：
- 适合大多数场景
- 自动管理，开箱即用
- 便于跨智能体数据分析
- 简化数据库维护

✅ **独立表**：
- 适合特殊需求
- 完全数据隔离
- 灵活的表结构
- 独立的性能优化

两种方式都支持自动发现和注册，开发者只需按照规范定义模型，无需手动配置，选择适合您场景的方式。

