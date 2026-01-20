# Core 模块基础组件使用指南

本文档详细介绍如何使用 AgentFlow 平台的核心服务组件，包括 Redis、MySQL（SQLAlchemy ORM）、MongoDB（Beanie ODM）和 Apollo 配置中心的完整操作示例。

> **文档特点**：本指南所有示例均基于实际运行的 `cmdb_smart_query` 智能体代码，确保 100% 可用性。

## 📋 目录

- [1. Redis 操作](#1-redis-操作)
- [2. MySQL 操作（SQLAlchemy ORM）](#2-mysql-操作sqlalchemy-orm)
- [3. MongoDB 操作（Beanie ODM）](#3-mongodb-操作beanie-odm)
- [4. Apollo 配置中心](#4-apollo-配置中心)
- [5. 在智能体中定义和使用数据模型](#5-在智能体中定义和使用数据模型)
- [6. 系统内部机制详解](#6-系统内部机制详解)
- [7. 高级查询技巧](#7-高级查询技巧)
- [8. 故障排查指南](#8-故障排查指南)
- [9. 最佳实践](#9-最佳实践)

---

## 1. Redis 操作

### 基础配置

在 `.env` 文件中配置 Redis 连接信息：

```bash
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=
```

### 完整示例代码

```python
from app.core.chat_history import get_chat_history_manager
from langchain_core.messages import HumanMessage, AIMessage

async def redis_operations_example():
    """Redis CRUD 操作示例"""
    
    # 获取 ChatHistoryManager（封装了 Redis 操作）
    chat_manager = await get_chat_history_manager()
    
    thread_id = "user_123_session_456"
    
    # ========== 插入/添加操作 ==========
    
    # 1. 添加单条消息
    user_msg = HumanMessage(content="你好，请介绍一下 Redis")
    await chat_manager.add_message(thread_id, user_msg)
    
    ai_msg = AIMessage(content="Redis 是一个高性能的键值数据库...")
    await chat_manager.add_message(thread_id, ai_msg)
    
    # 2. 批量添加消息
    messages = [
        HumanMessage(content="Redis 支持哪些数据结构？"),
        AIMessage(content="Redis 支持字符串、列表、集合、哈希表等...")
    ]
    await chat_manager.add_messages(thread_id, messages)
    
    # ========== 查询操作 ==========
    
    # 1. 查询所有历史消息
    all_messages = await chat_manager.get_messages(thread_id)
    print(f"历史消息总数: {len(all_messages)}")
    
    # 2. 查询最近 N 条消息
    recent_messages = await chat_manager.get_messages(thread_id, limit=5)
    print(f"最近 5 条消息: {recent_messages}")
    
    # 3. 获取会话摘要信息
    summary = await chat_manager.get_context_summary(thread_id)
    print(f"会话摘要: {summary}")
    
    # ========== 保存/查询状态数据 ==========
    
    # 1. 保存自定义状态
    state_data = {
        "current_topic": "Redis",
        "user_level": "beginner",
        "resources": [{"id": 1, "name": "Redis 文档"}]
    }
    await chat_manager.save_state(thread_id, state_data)
    
    # 2. 查询状态
    saved_state = await chat_manager.get_state(thread_id)
    print(f"保存的状态: {saved_state}")
    
    # ========== 删除操作 ==========
    
    # 1. 删除会话历史
    await chat_manager.clear_history(thread_id)
    
    # 2. 删除会话状态
    await chat_manager.clear_state(thread_id)
    
    # ========== 健康检查 ==========
    is_healthy = await chat_manager.ping()
    print(f"Redis 连接状态: {'正常' if is_healthy else '异常'}")
    
    # ========== 关闭连接（应用关闭时）==========
    await chat_manager.close()
```

---

## 2. MySQL 操作（SQLAlchemy ORM）

### 基础配置

在 `.env` 文件中配置 MySQL 连接信息：

```bash
MYSQL_ENABLED=true
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=your_password
MYSQL_DATABASE=agentflow
MYSQL_POOL_SIZE=10
MYSQL_POOL_RECYCLE=3600
```

### 2.1 定义数据模型

以下是来自 `app/agents/cmdb_smart_query/models/conversation_history.py` 的真实模型示例：

```python
# app/agents/cmdb_smart_query/models/conversation_history.py
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Text, DateTime, Integer, Index
from sqlalchemy.orm import Mapped, mapped_column
from app.core.services.db_base import Base, TimestampMixin


class ConversationHistory(Base, TimestampMixin):
    """会话历史记录表
    
    用于存储用户与智能体的对话历史，每条消息一行记录。
    """
    __tablename__ = 'conversation_history'
    
    # 主键
    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
        comment="主键ID"
    )
    
    # 会话ID（用于多轮对话）
    thread_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
        comment="会话线程ID"
    )
    
    # 角色（user/assistant/system）
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
    
    # 元数据（JSON 字符串）
    metadata: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="元数据（JSON）"
    )
    
    # 索引定义
    __table_args__ = (
        Index('idx_thread_id_created', 'thread_id', 'created_at'),
        {'comment': '会话历史记录表'}
    )
    
    def __repr__(self) -> str:
        return f"<ConversationHistory(id={self.id}, thread_id={self.thread_id}, role={self.role})>"
```

**关键要点**：

1. **继承 Base 和 TimestampMixin**：`Base` 是 SQLAlchemy 声明式基类，`TimestampMixin` 自动添加 `created_at` 和 `updated_at` 字段
2. **类型注解**：使用 `Mapped[类型]` 进行类型标注（SQLAlchemy 2.0 新特性）
3. **mapped_column**：定义列属性，支持丰富的参数（nullable、index、comment 等）
4. **索引定义**：通过 `__table_args__` 定义复合索引和表注释

### 2.2 CRUD 操作示例

```python
from app.main import get_container
from sqlalchemy import select, and_, or_, func
from app.agents.cmdb_smart_query.models.conversation_history import ConversationHistory

async def mysql_orm_operations_example():
    """MySQL ORM CRUD 操作示例"""
    
    # 获取 MySQL 服务
    container = get_container()
    mysql = container.get('mysql')
    
    # ========== 插入操作 ==========
    
    # 1. 插入单条记录
    async with mysql.get_session() as session:
        history = ConversationHistory(
            thread_id="user_123_session_456",
            role="user",
            content="查询服务器信息",
            metadata='{"ip": "192.168.1.1"}'
        )
        session.add(history)
        await session.commit()
        # 提交后可以访问自动生成的 ID 和时间戳
        print(f"插入成功，ID: {history.id}, 创建时间: {history.created_at}")
    
    # 2. 批量插入
    async with mysql.get_session() as session:
        histories = [
            ConversationHistory(
                thread_id="user_123_session_456",
                role="assistant",
                content="找到 5 台服务器"
            ),
            ConversationHistory(
                thread_id="user_123_session_456",
                role="user",
                content="显示详细信息"
            )
        ]
        session.add_all(histories)
        await session.commit()
        print(f"批量插入了 {len(histories)} 条记录")
    
    # ========== 查询操作 ==========
    
    # 1. 查询所有记录
    async with mysql.get_session() as session:
        result = await session.execute(select(ConversationHistory))
        all_histories = result.scalars().all()
        print(f"总记录数: {len(all_histories)}")
    
    # 2. 条件查询 - 单条件
    async with mysql.get_session() as session:
        result = await session.execute(
            select(ConversationHistory)
            .where(ConversationHistory.thread_id == "user_123_session_456")
        )
        thread_histories = result.scalars().all()
        for h in thread_histories:
            print(f"{h.role}: {h.content}")
    
    # 3. 条件查询 - 多条件（AND）
    async with mysql.get_session() as session:
        result = await session.execute(
            select(ConversationHistory)
            .where(
                and_(
                    ConversationHistory.thread_id == "user_123_session_456",
                    ConversationHistory.role == "user"
                )
            )
        )
        user_messages = result.scalars().all()
    
    # 4. 条件查询 - 多条件（OR）
    async with mysql.get_session() as session:
        result = await session.execute(
            select(ConversationHistory)
            .where(
                or_(
                    ConversationHistory.role == "user",
                    ConversationHistory.role == "system"
                )
            )
        )
        filtered_messages = result.scalars().all()
    
    # 5. 查询单条记录
    async with mysql.get_session() as session:
        result = await session.execute(
            select(ConversationHistory)
            .where(ConversationHistory.id == 1)
        )
        history = result.scalar_one_or_none()
        if history:
            print(f"找到记录: {history}")
    
    # 6. 模糊查询
    async with mysql.get_session() as session:
        result = await session.execute(
            select(ConversationHistory)
            .where(ConversationHistory.content.like("%服务器%"))
        )
        matching_histories = result.scalars().all()
    
    # 7. 排序查询
    async with mysql.get_session() as session:
        result = await session.execute(
            select(ConversationHistory)
            .where(ConversationHistory.thread_id == "user_123_session_456")
            .order_by(ConversationHistory.created_at.desc())
            .limit(10)
        )
        recent_histories = result.scalars().all()
    
    # 8. 分页查询
    async with mysql.get_session() as session:
        page = 1
        page_size = 10
        offset = (page - 1) * page_size
        
        result = await session.execute(
            select(ConversationHistory)
            .order_by(ConversationHistory.created_at.desc())
            .limit(page_size)
            .offset(offset)
        )
        page_data = result.scalars().all()
        
        # 获取总数
        count_result = await session.execute(
            select(func.count()).select_from(ConversationHistory)
        )
        total = count_result.scalar()
        print(f"第 {page} 页，共 {total} 条记录")
    
    # ========== 更新操作 ==========
    
    # 1. 查询并更新
    async with mysql.get_session() as session:
        result = await session.execute(
            select(ConversationHistory)
            .where(ConversationHistory.id == 1)
        )
        history = result.scalar_one_or_none()
        if history:
            history.content = "更新后的内容"
            history.metadata = '{"updated": true}'
            await session.commit()
            # updated_at 会自动更新（由 TimestampMixin 提供）
            print(f"更新成功: {history}")
    
    # 2. 批量更新（使用 update 语句）
    from sqlalchemy import update
    async with mysql.get_session() as session:
        stmt = (
            update(ConversationHistory)
            .where(ConversationHistory.thread_id == "old_thread_id")
            .values(thread_id="new_thread_id")
        )
        result = await session.execute(stmt)
        await session.commit()
        print(f"更新了 {result.rowcount} 条记录")
    
    # ========== 删除操作 ==========
    
    # 1. 查询并删除
    async with mysql.get_session() as session:
        result = await session.execute(
            select(ConversationHistory)
            .where(ConversationHistory.thread_id == "old_session")
        )
        histories_to_delete = result.scalars().all()
        for history in histories_to_delete:
            await session.delete(history)
        await session.commit()
        print(f"删除了 {len(histories_to_delete)} 条记录")
    
    # 2. 批量删除（使用 delete 语句）
    from sqlalchemy import delete
    async with mysql.get_session() as session:
        stmt = (
            delete(ConversationHistory)
            .where(ConversationHistory.created_at < some_date)
        )
        result = await session.execute(stmt)
        await session.commit()
        print(f"删除了 {result.rowcount} 条记录")
    
    # ========== 事务操作 ==========
    
    async with mysql.get_session() as session:
        try:
            # 多个操作在同一个事务中
            history1 = ConversationHistory(
                thread_id="transaction_test",
                role="user",
                content="操作1"
            )
            session.add(history1)
            
            history2 = ConversationHistory(
                thread_id="transaction_test",
                role="assistant",
                content="操作2"
            )
            session.add(history2)
            
            # 如果这里出现异常，上面的操作都会回滚
            await session.commit()
            print("事务提交成功")
        except Exception as e:
            await session.rollback()
            print(f"事务失败，已回滚: {e}")
```

### 2.3 在智能体中使用 MySQL ORM

```python
from app.agents.base import AgentBase
from sqlalchemy import select
from .models.conversation_history import ConversationHistory

class CMDBSmartQueryAgent(AgentBase):
    async def invoke(self, message: str, thread_id: str, context=None):
        # 保存用户消息到数据库
        async with self.mysql.get_session() as session:
            user_message = ConversationHistory(
                thread_id=thread_id,
                role="user",
                content=message
            )
            session.add(user_message)
            await session.commit()
            
            # 查询历史消息
            result = await session.execute(
                select(ConversationHistory)
                .where(ConversationHistory.thread_id == thread_id)
                .order_by(ConversationHistory.created_at.desc())
                .limit(10)
            )
            history = result.scalars().all()
        
        # 处理消息...
        response = await self._process_message(message, history)
        
        # 保存助手响应
        async with self.mysql.get_session() as session:
            assistant_message = ConversationHistory(
                thread_id=thread_id,
                role="assistant",
                content=response
            )
            session.add(assistant_message)
            await session.commit()
        
        return response
```

---

## 3. MongoDB 操作 -- Motor + Pydantic

**关键要点**：
由于交行mongo版本较低，没有使用Beanie，所以需要自己实现ODM，较为繁琐，建议直接使用oceanbase/mysql

### 基础配置

在 `.env` 文件中配置 MongoDB 连接信息：

```bash
MONGODB_ENABLED=true
MONGODB_HOST=localhost
MONGODB_PORT=27017
MONGODB_USER=admin
MONGODB_PASSWORD=your_password
MONGODB_DATABASE=agentflow
MONGODB_AUTH_SOURCE=admin
```

### 3.1 定义数据模型

app/core/models/shared_conversation_history_mongo.py


### 3.2 CRUD 操作示例
 参考app/core/services/mongo_helpers.py

---

## 4. Apollo 配置中心

### 基础配置

在 `.env` 文件中配置 Apollo 连接信息：

```bash
APOLLO_ENABLED=true
APOLLO_APP_ID=my-app
APOLLO_CLUSTER=default
APOLLO_CONFIG_SERVER_URL=http://apollo.example.com:8080
APOLLO_NAMESPACE=application
APOLLO_SECRET=your_secret_key
```

### 完整示例代码

```python
from app.main import get_container

async def apollo_operations_example():
    """Apollo 配置中心操作示例"""
    
    # 获取 Apollo 服务
    container = get_container()
    apollo = container.get('apollo')
    
    # ========== 读取配置 ==========
    
    # 1. 读取单个配置项
    db_host = apollo.get('database.host', default='localhost')
    db_port = apollo.get('database.port', default=3306)
    print(f"数据库配置: {db_host}:{db_port}")
    
    # 2. 读取所有配置
    all_configs = apollo.get_all()
    print(f"所有配置: {all_configs}")
    
    # ========== 配置变更监听 ==========
    
    def on_config_change(key: str, old_value, new_value):
        """配置变更回调函数"""
        print(f"配置变更: {key} 从 {old_value} 变为 {new_value}")
    
    # 启动配置监听
    apollo.start_config_listener(on_config_change)
```

---

## 5. 在智能体中定义和使用数据模型

### 5.1 创建模型目录结构

基于 `cmdb_smart_query` 智能体的实际目录结构：

```
app/agents/cmdb_smart_query/
├── models/
│   ├── __init__.py                      # 导出所有模型
│   ├── conversation_history.py          # MySQL 模型（SQLAlchemy）
│   └── conversation_history_mongo.py    # MongoDB 模型（Beanie）
├── prompts/
│   └── ...
├── agent.py                              # 智能体实现
├── agent.yaml                            # 智能体配置
└── graph.py                              # LangGraph 图定义
```

### 5.2 导出模型（重要！）

在 `models/__init__.py` 中导出模型，系统会自动发现：

```python
# app/agents/cmdb_smart_query/models/__init__.py
"""CMDB Smart Query 智能体数据模型

包含 MySQL 和 MongoDB 的会话历史模型示例。
"""

from .conversation_history import ConversationHistory
from .conversation_history_mongo import ConversationHistoryMongo

__all__ = ['ConversationHistory', 'ConversationHistoryMongo']
```

**关键要点**：

1. **必须导出模型**：在 `__init__.py` 中 import 并添加到 `__all__`
2. **系统自动发现**：加载器会扫描 `__all__` 中的所有类
3. **自动注册**：SQLAlchemy 模型注册到 MySQL 服务，Beanie Document 注册到 MongoDB 服务

### 5.3 定义 MySQL 模型（完整模板）

```python
# app/agents/your_agent/models/your_model.py
from sqlalchemy import String, Integer, Text, Index
from sqlalchemy.orm import Mapped, mapped_column
from app.core.services.db_base import Base, TimestampMixin


class YourModel(Base, TimestampMixin):
    """你的模型说明"""
    __tablename__ = 'your_table_name'
    
    # 主键
    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
        comment="主键ID"
    )
    
    # 字符串字段
    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
        comment="名称"
    )
    
    # 文本字段
    description: Mapped[str] = mapped_column(
        Text,
        nullable=True,
        comment="描述"
    )
    
    # 索引定义
    __table_args__ = (
        Index('idx_name', 'name'),  # 单字段索引
        Index('idx_name_created', 'name', 'created_at'),  # 复合索引
        {'comment': '表注释'}
    )
    
    def __repr__(self) -> str:
        return f"<YourModel(id={self.id}, name={self.name})>"
```

### 5.4 定义 MongoDB 模型（完整模板）

```python
# app/agents/your_agent/models/your_document.py
from typing import List, Optional
from pydantic import Field
from app.core.services.mongo_base import BaseDocument


class YourDocument(BaseDocument):
    """你的文档说明"""
    
    # 必填字段
    name: str = Field(..., description="名称")
    
    # 可选字段
    description: Optional[str] = Field(None, description="描述")
    
    # 列表字段
    items: List[dict] = Field(default_factory=list, description="项目列表")
    
    # 嵌套字段
    metadata: Optional[dict] = Field(None, description="元数据")
    
    class Settings:
        name = "your_collection_name"  # 集合名称
        indexes = [
            "name",  # 单字段索引
            [("name", 1), ("created_at", -1)],  # 复合索引
        ]
    
    def __repr__(self) -> str:
        return f"<YourDocument(name={self.name})>"
```

### 5.5 在智能体中访问数据库服务

```python
from app.agents.base import AgentBase
from sqlalchemy import select
from .models.your_model import YourModel
from .models.your_document import YourDocument

class YourAgent(AgentBase):
    async def invoke(self, message: str, thread_id: str, context=None):
        # ========== 使用 MySQL ==========
        async with self.mysql.get_session() as session:
            # 查询
            result = await session.execute(
                select(YourModel).where(YourModel.name == "test")
            )
            model = result.scalar_one_or_none()
            
            # 插入
            new_model = YourModel(name="new", description="test")
            session.add(new_model)
            await session.commit()
        
        # ========== 使用 MongoDB ==========
        # 查询
        document = await YourDocument.find_one(
            YourDocument.name == "test"
        )
        
        # 插入或更新
        if not document:
            document = YourDocument(name="test", items=[])
        document.items.append({"key": "value"})
        await document.save()
        
        return response
```

---

## 6. 系统内部机制详解

### 6.1 智能体加载流程

当应用启动时，`app/main.py` 的 `lifespan` 函数会触发智能体加载：

```python
# app/main.py (简化版)
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. 创建服务容器
    _container = ServiceContainer()
    
    # 2. 注册并初始化所有服务
    await _container.initialize_all()
    
    # 3. 加载所有智能体（触发模型自动发现）
    AgentLoader.load_all_agents(container=_container)
    
    # 4. 初始化数据库（创建表/集合和索引）
    if settings.mysql_enabled:
        mysql = _container.get('mysql')
        await mysql.create_tables()  # 创建所有已注册的表
    
    if settings.mongodb_enabled:
        mongodb = _container.get('mongodb')
        await mongodb.init_beanie()  # 初始化 Beanie（创建索引）
    
    yield
    
    # 应用关闭时清理
    await _container.shutdown_all()
```

### 6.2 模型自动发现机制

`AgentLoader` 在加载每个智能体时会自动发现模型（`app/agents/loader.py`）：

```python
def _discover_and_register_models(self, agent_dir: Path, agent_name: str):
    """自动发现并注册智能体的数据模型"""
    
    # 1. 检查是否存在 models 目录
    models_dir = agent_dir / "models"
    if not models_dir.exists():
        return
    
    # 2. 检查是否存在 __init__.py
    init_file = models_dir / "__init__.py"
    if not init_file.exists():
        logger.warning(f"智能体 [{agent_name}] 的 models 目录缺少 __init__.py")
        return
    
    # 3. 动态导入 models 模块
    module_path = f"app.agents.{agent_dir.name}.models"
    models_module = importlib.import_module(module_path)
    
    # 4. 扫描 SQLAlchemy 模型和 Beanie Document
    sqlalchemy_models = []
    beanie_documents = []
    
    for name, obj in inspect.getmembers(models_module):
        if not inspect.isclass(obj):
            continue
        
        # 检查是否是 SQLAlchemy 模型
        if self._is_sqlalchemy_model(obj):
            sqlalchemy_models.append(obj)
        
        # 检查是否是 Beanie Document
        elif self._is_beanie_document(obj):
            beanie_documents.append(obj)
    
    # 5. 注册到对应的服务
    if sqlalchemy_models:
        mysql_service = self.container.get('mysql')
        from app.core.services.db_base import Base
        mysql_service.register_models(Base.metadata)
        logger.info(f"智能体 [{agent_name}] 注册了 {len(sqlalchemy_models)} 个 SQLAlchemy 模型")
    
    if beanie_documents:
        mongodb_service = self.container.get('mongodb')
        mongodb_service.register_documents(beanie_documents)
        logger.info(f"智能体 [{agent_name}] 注册了 {len(beanie_documents)} 个 Beanie Document")
```

**检测逻辑**：

- **SQLAlchemy 模型**：继承自 `Base` 且有 `__tablename__` 属性
- **Beanie Document**：继承自 `Document` 或 `BaseDocument`

### 6.3 启动日志示例

当系统正常运行时，你会看到类似以下的日志：

```
==================================================
多智能体平台启动中...
LLM模型: gpt-4
服务地址: http://0.0.0.0:8000
==================================================

服务初始化完成:
  ✓ config
  ✓ llm
  ✓ mysql
  ✓ mongodb

正在加载智能体...
INFO:app.agents.loader:正在加载智能体: cmdb_smart_query (v1.0.0)
INFO:app.agents.loader:已导入智能体 [cmdb_smart_query] 的 models 模块
INFO:app.agents.loader:发现 SQLAlchemy 模型: ConversationHistory
INFO:app.agents.loader:发现 Beanie Document: ConversationHistoryMongo
INFO:app.agents.loader:智能体 [cmdb_smart_query] 注册了 1 个 SQLAlchemy 模型
INFO:app.agents.loader:智能体 [cmdb_smart_query] 注册了 1 个 Beanie Document
INFO:app.agents.loader:✓ 智能体加载成功: cmdb_smart_query

=== 智能体加载完成 ===
  - cmdb_smart_query: CMDB 智能查询助手
==================================================

正在初始化数据库...
INFO:app.core.services.mysql_service:开始创建数据库表...
INFO:app.core.services.mysql_service:已创建/检查 1 个表
INFO:app.core.services.mysql_service:数据库表创建完成
  ✓ MySQL 表创建完成

INFO:app.core.services.mongodb_service:开始初始化 Beanie ODM，共 1 个 Document...
INFO:app.core.services.mongodb_service:✓ ConversationHistoryMongo -> 集合: conversation_history
INFO:app.core.services.mongodb_service:Beanie ODM 初始化完成（索引已自动创建）
  ✓ MongoDB Beanie 初始化完成
==================================================
```

### 6.4 表和集合创建时机

- **MySQL 表**：调用 `mysql.create_tables()` 时创建，使用 SQLAlchemy 的 `metadata.create_all()`
  - 如果表已存在，不会重复创建
  - 不会自动修改表结构（需要手动迁移或删除表重建）

- **MongoDB 集合和索引**：调用 `mongodb.init_beanie()` 时创建
  - Beanie 会自动创建集合（如果不存在）
  - 自动创建 Settings 中定义的所有索引
  - 索引创建是幂等的（多次运行不会出错）

---

## 7. 高级查询技巧

### 7.1 SQLAlchemy 高级查询

#### 7.1.1 关联查询（Join）

假设你有多个关联的模型：

```python
from sqlalchemy import ForeignKey
from sqlalchemy.orm import relationship

class User(Base, TimestampMixin):
    __tablename__ = 'users'
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    
    # 关系
    posts = relationship("Post", back_populates="author")

class Post(Base, TimestampMixin):
    __tablename__ = 'posts'
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey('users.id'))
    
    # 关系
    author = relationship("User", back_populates="posts")

# 查询用户及其所有文章
async with mysql.get_session() as session:
    result = await session.execute(
        select(User)
        .join(Post)
        .where(Post.title.like("%Python%"))
    )
    users = result.unique().scalars().all()
    
    for user in users:
        # 访问关联对象（需要配置 eager loading）
        print(f"{user.name}: {len(user.posts)} 篇文章")
```

#### 7.1.2 聚合查询

```python
from sqlalchemy import func

async with mysql.get_session() as session:
    # 统计每个 thread_id 的消息数
    result = await session.execute(
        select(
            ConversationHistory.thread_id,
            func.count(ConversationHistory.id).label('message_count')
        )
        .group_by(ConversationHistory.thread_id)
        .having(func.count(ConversationHistory.id) > 10)
    )
    stats = result.all()
    
    for thread_id, count in stats:
        print(f"Thread {thread_id}: {count} 条消息")
```

#### 7.1.3 子查询

```python
from sqlalchemy import subquery

async with mysql.get_session() as session:
    # 查询最新的 10 个会话
    subq = (
        select(ConversationHistory.thread_id)
        .order_by(ConversationHistory.created_at.desc())
        .limit(10)
        .subquery()
    )
    
    result = await session.execute(
        select(ConversationHistory)
        .where(ConversationHistory.thread_id.in_(select(subq)))
    )
    messages = result.scalars().all()
```

#### 7.1.4 性能优化 - Eager Loading

```python
from sqlalchemy.orm import selectinload

async with mysql.get_session() as session:
    # 一次性加载用户和文章（避免 N+1 查询问题）
    result = await session.execute(
        select(User)
        .options(selectinload(User.posts))
        .where(User.id == 1)
    )
    user = result.scalar_one_or_none()
    
    # 现在可以直接访问 posts，不会触发额外查询
    for post in user.posts:
        print(post.title)
```

### 7.2 Beanie 高级查询

#### 7.2.1 聚合管道

```python
# 统计每个智能体的消息总数
pipeline = [
    {"$unwind": "$messages"},  # 展开消息数组
    {"$group": {
        "_id": "$agent_name",
        "total_messages": {"$sum": 1},
        "avg_messages_per_conversation": {"$avg": {"$size": "$messages"}}
    }},
    {"$sort": {"total_messages": -1}}
]

result = await ConversationHistoryMongo.aggregate(pipeline).to_list()
for item in result:
    print(f"智能体: {item['_id']}, 总消息数: {item['total_messages']}")
```

#### 7.2.2 复杂条件查询

```python
from beanie.operators import In, RegEx, Exists
from datetime import datetime, timedelta

# 多重条件查询
conversations = await ConversationHistoryMongo.find(
    In(ConversationHistoryMongo.agent_name, ["agent1", "agent2"]),
    ConversationHistoryMongo.created_at >= datetime.now() - timedelta(days=7),
    Exists(ConversationHistoryMongo.user_id, True),  # user_id 字段存在且非空
).to_list()

# 正则表达式查询
conversations = await ConversationHistoryMongo.find(
    RegEx(ConversationHistoryMongo.thread_id, "^user_123_", "i")  # 不区分大小写
).to_list()
```

#### 7.2.3 数组查询

```python
# 查询包含特定消息的会话
conversations = await ConversationHistoryMongo.find(
    {
        "messages": {
            "$elemMatch": {
                "role": "user",
                "content": {"$regex": "服务器"}
            }
        }
    }
).to_list()

# 查询消息数量大于 10 的会话
conversations = await ConversationHistoryMongo.find(
    {"messages.10": {"$exists": True}}  # 数组第 10 个元素存在
).to_list()
```

#### 7.2.4 投影和部分更新

```python
# 只返回部分字段（减少网络传输）
conversations = await ConversationHistoryMongo.find_all().project(
    ConversationHistoryMongo.thread_id,
    ConversationHistoryMongo.created_at
).to_list()

# 部分更新（避免加载整个文档）
await ConversationHistoryMongo.find_one(
    ConversationHistoryMongo.thread_id == "user_123"
).update({
    "$set": {"user_id": "new_user_id"},
    "$push": {"messages": {"role": "system", "content": "test"}}
})
```

---

## 8. 故障排查指南

### 8.1 MySQL ORM 常见问题

#### 问题 1：模型未被发现

**症状**：启动时没有看到 "注册了 X 个 SQLAlchemy 模型" 的日志

**排查步骤**：

1. 检查 `models/__init__.py` 是否导出了模型：
```python
from .your_model import YourModel
__all__ = ['YourModel']
```

2. 检查模型是否继承了 `Base` 和定义了 `__tablename__`：
```python
from app.core.services.db_base import Base

class YourModel(Base):
    __tablename__ = 'your_table'
    # ...
```

3. 检查启动日志，查看是否有导入错误

#### 问题 2：表没有创建

**症状**：查询时报错 "Table doesn't exist"

**解决方案**：

1. 检查 `.env` 中 `MYSQL_ENABLED=true`
2. 检查启动日志是否有 "MySQL 表创建完成"
3. 手动连接数据库检查表是否存在：
```bash
mysql -u root -p
USE agentflow;
SHOW TABLES;
```

4. 如果需要重建表：
```bash
# 删除表
DROP TABLE conversation_history;
# 重启应用，表会自动创建
```

#### 问题 3：会话管理错误

**症状**：`RuntimeError: MySQL 服务未初始化`

**原因**：在服务初始化之前访问了数据库

**解决方案**：确保在 `lifespan` 完成后才访问数据库（FastAPI 会自动处理）

#### 问题 4：事务回滚问题

**症状**：数据没有保存到数据库

**解决方案**：确保调用了 `await session.commit()`：

```python
async with mysql.get_session() as session:
    model = YourModel(name="test")
    session.add(model)
    await session.commit()  # 必须提交！
```

### 8.2 MongoDB ODM 常见问题

#### 问题 1：Document 未被发现

**症状**：启动时没有看到 "注册了 X 个 Beanie Document" 的日志

**排查步骤**：

1. 检查 `models/__init__.py` 是否导出了 Document：
```python
from .your_document import YourDocument
__all__ = ['YourDocument']
```

2. 检查 Document 是否继承了 `BaseDocument` 或 `Document`：
```python
from app.core.services.mongo_base import BaseDocument

class YourDocument(BaseDocument):
    # ...
```

3. 检查是否定义了 Settings：
```python
class Settings:
    name = "your_collection"
```

#### 问题 2：索引没有创建

**症状**：查询慢或索引相关错误

**解决方案**：

1. 检查 Settings 中的索引定义：
```python
class Settings:
    indexes = [
        "field_name",  # 单字段索引
        [("field1", 1), ("field2", -1)],  # 复合索引
    ]
```

2. 手动验证索引是否存在：
```javascript
// 在 MongoDB shell 中
use agentflow
db.conversation_history.getIndexes()
```

3. 如果需要重建索引：
```javascript
// 删除旧索引
db.conversation_history.dropIndex("index_name")
// 重启应用，索引会自动创建
```

#### 问题 3：Beanie 初始化顺序问题

**症状**：`RuntimeError: Beanie 未初始化`

**原因**：在 `init_beanie()` 之前尝试使用 Document

**解决方案**：确保在 `lifespan` 中正确初始化：

```python
# app/main.py
await mongodb.init_beanie()  # 必须在使用 Document 之前调用
```

#### 问题 4：updated_at 没有自动更新

**症状**：`updated_at` 字段不会自动更新

**原因**：必须使用 `save()` 方法（不是 `update()`）

**解决方案**：

```python
# 正确方式
document = await YourDocument.find_one(...)
document.field = "new value"
await document.save()  # save() 会触发 BaseDocument 的 updated_at 更新

# 错误方式
await YourDocument.find_one(...).update({"$set": {"field": "new value"}})  # 不会更新 updated_at
```

### 8.3 通用问题

#### 问题：导入错误

**症状**：`ImportError: cannot import name 'Base'`

**解决方案**：检查依赖是否安装完整：

```bash
pip install -r requirements.txt

# 或手动安装
pip install sqlalchemy[asyncio]>=2.0.0 greenlet aiomysql
pip install motor>=3.3.0 beanie>=1.23.0
```

#### 问题：服务未启用

**症状**：`RuntimeError: MySQL 服务未初始化`

**解决方案**：检查 `.env` 配置：

```bash
# 必须启用对应的服务
MYSQL_ENABLED=true
MONGODB_ENABLED=true
```

---

## 9. 最佳实践

### 9.1 在智能体中统一获取服务

```python
from app.agents.base import AgentBase

class MyAgent(AgentBase):
    async def invoke(self, message: str, thread_id: str, context=None):
        # 使用属性访问服务（推荐）
        llm = self.llm          # LLM 服务
        mysql = self.mysql      # MySQL 服务（ORM）
        mongodb = self.mongodb  # MongoDB 服务（ODM）
        apollo = self.apollo    # Apollo 配置服务
        
        # 或使用 get_service() 方法
        custom_service = self.get_service('custom', default=None)
```

### 9.2 错误处理

```python
async def safe_database_operation():
    """安全的数据库操作示例"""
    try:
        async with mysql.get_session() as session:
            # ORM 操作
            model = YourModel(name="测试")
            session.add(model)
            await session.commit()
    except RuntimeError as e:
        # 服务未初始化或未启用
        print(f"MySQL 服务不可用: {e}")
    except Exception as e:
        # 其他数据库错误
        print(f"数据库操作失败: {e}")
        raise
```

### 9.3 事务处理

```python
async def transfer_operation():
    """事务示例：确保数据一致性"""
    async with mysql.get_session() as session:
        try:
            # 多个操作在同一个事务中
            model1 = await session.get(YourModel, 1)
            model2 = await session.get(YourModel, 2)
            
            # 执行业务逻辑
            model1.value -= 100
            model2.value += 100
            
            # 提交事务
            await session.commit()
            print("操作成功")
        except Exception as e:
            # 发生错误时自动回滚
            await session.rollback()
            print(f"操作失败，已回滚: {e}")
            raise
```

### 9.4 使用索引优化查询

**MySQL**：
```python
from sqlalchemy import Index

class YourModel(Base):
    __tablename__ = 'your_table'
    
    name: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime)
    
    # 定义索引
    __table_args__ = (
        Index('idx_name', 'name'),  # 单字段索引
        Index('idx_name_created', 'name', 'created_at'),  # 复合索引
    )
```

**MongoDB**：
```python
class YourDocument(BaseDocument):
    name: str
    created_at: datetime
    
    class Settings:
        name = "your_collection"
        indexes = [
            "name",  # 单字段索引
            [("name", 1), ("created_at", -1)],  # 复合索引
        ]
```

### 9.5 分页查询最佳实践

**MySQL**：
```python
async def get_paginated_results(page: int, page_size: int = 20):
    """分页查询"""
    async with mysql.get_session() as session:
        # 获取总数
        count_result = await session.execute(
            select(func.count()).select_from(YourModel)
        )
        total = count_result.scalar()
        
        # 获取分页数据
        offset = (page - 1) * page_size
        result = await session.execute(
            select(YourModel)
            .order_by(YourModel.created_at.desc())
            .limit(page_size)
            .offset(offset)
        )
        items = result.scalars().all()
        
        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size
        }
```

**MongoDB**：
```python
async def get_paginated_results(page: int, page_size: int = 20):
    """分页查询"""
    # 获取总数
    total = await YourDocument.find_all().count()
    
    # 获取分页数据
    skip = (page - 1) * page_size
    items = await YourDocument.find_all()\
        .sort(-YourDocument.created_at)\
        .skip(skip)\
        .limit(page_size)\
        .to_list()
    
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size
    }
```

### 9.6 性能优化建议

1. **使用连接池**：已在 MySQL 服务中配置（`MYSQL_POOL_SIZE`）
2. **索引优化**：为常用查询字段创建索引
3. **批量操作**：使用 `add_all()` 和 `insert_many()` 而不是循环插入
4. **投影查询**：只查询需要的字段，减少网络传输
5. **避免 N+1 查询**：使用 eager loading（SQLAlchemy）或聚合（Beanie）
6. **合理使用缓存**：对于不常变化的数据，可以使用 Redis 缓存

### 9.7 数据模型设计建议

1. **选择合适的数据库**：
   - MySQL：结构化数据、需要事务、关联查询
   - MongoDB：文档型数据、嵌套结构、灵活 schema

2. **字段设计**：
   - 使用合适的数据类型（String vs Text，Integer vs BigInteger）
   - 添加注释（comment）便于维护
   - 设置合理的默认值

3. **索引设计**：
   - 为频繁查询的字段创建索引
   - 考虑复合索引的顺序（最常用的字段放前面）
   - 避免过多索引（影响写入性能）

---

## 📚 相关文档

- [Docker 部署指南](./DOCKER_GUIDE.md)
- [智能体管理 API](./AGENT_MANAGEMENT_API.md)
- [多轮对话集成](./multi_turn_conversation.md)
- [流式输出集成](./streaming_integration.md)

---

## ⚠️ 注意事项

1. **服务启用**：所有可选服务（MySQL、MongoDB、Apollo）需要在 `.env` 中设置 `*_ENABLED=true` 才会初始化
2. **异步操作**：所有数据库操作都是异步的，必须使用 `await` 关键字
3. **自动迁移**：系统启动时会自动创建表/集合和索引，无需手动执行迁移脚本
4. **模型定义**：在智能体的 `models/` 目录下定义模型，并在 `__init__.py` 中导出
5. **索引管理**：SQLAlchemy 和 Beanie 都会自动创建索引，无需手动操作
6. **会话管理**：MySQL 使用 `async with mysql.get_session()` 管理会话，异常时自动回滚
7. **时间戳**：`TimestampMixin` 和 `BaseDocument` 提供自动时间戳管理
8. **事务处理**：MySQL 支持事务，MongoDB 需要副本集才支持事务

---

## 🎓 参考资料

- [SQLAlchemy 2.0 文档](https://docs.sqlalchemy.org/en/20/)
- [Beanie 官方文档](https://beanie-odm.dev/)
- [Pydantic 文档](https://docs.pydantic.dev/)
- [Motor（异步 MongoDB 驱动）文档](https://motor.readthedocs.io/)

---

**最后更新**: 2025-11-04

**实际代码参考**：`app/agents/cmdb_smart_query/models/` - 包含完整的工作示例
