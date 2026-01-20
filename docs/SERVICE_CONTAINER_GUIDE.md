# 服务容器与依赖注入指南

## 概述

AgentFlow 使用**服务容器**(ServiceContainer)实现依赖注入，统一管理所有服务的生命周期，并将服务自动注入到智能体中。这种设计提供了：

- ✅ **松耦合**：智能体不直接创建服务实例，只声明依赖
- ✅ **易测试**：可以轻松替换服务实现进行单元测试
- ✅ **统一管理**：所有服务的初始化和关闭集中管理
- ✅ **懒加载**：服务在首次使用时才创建实例
- ✅ **单例模式**：避免重复创建服务实例，节省资源

---

## 目录

1. [核心概念](#核心概念)
2. [服务容器架构](#服务容器架构)
3. [在智能体中使用服务](#在智能体中使用服务)
4. [添加自定义服务](#添加自定义服务)
5. [服务生命周期](#服务生命周期)
6. [完整实例](#完整实例)
7. [最佳实践](#最佳实践)
8. [常见问题](#常见问题)

---

## 核心概念

### 什么是服务容器？

服务容器（ServiceContainer）是一个**依赖注入容器**，负责：

1. **注册服务**：将服务工厂函数注册到容器
2. **创建实例**：根据工厂函数创建服务实例（懒加载）
3. **管理生命周期**：统一初始化和关闭所有服务
4. **依赖注入**：自动将服务注入到智能体

### 什么是依赖注入？

依赖注入（Dependency Injection，DI）是一种设计模式，对象不自己创建依赖，而是从外部接收。

**传统方式（硬编码依赖）：**

```python
class MyAgent:
    def __init__(self):
        # 直接创建依赖，紧耦合
        self.llm = LLMService()
        self.mysql = MySQLService()
```

**依赖注入方式：**

```python
class MyAgent(AgentBase):
    def __init__(self):
        super().__init__(name="my_agent", description="...")
        # 不创建依赖，通过容器获取
    
    async def invoke(self, message, thread_id, context):
        # 使用注入的服务
        llm = self.llm  # 通过 property 从容器获取
        mysql = self.mysql
```

### 核心组件

| 组件 | 职责 | 位置 |
|------|------|------|
| **ServiceContainer** | 依赖注入容器 | `app/core/container.py` |
| **IService** | 服务接口（定义生命周期方法） | `app/core/container.py` |
| **AgentBase** | 智能体基类（提供服务访问接口） | `app/agents/base.py` |
| **各种 Service** | 具体服务实现（LLM、MySQL 等） | `app/core/services/` |

---

## 服务容器架构

### 容器工作流程

```
应用启动
  ↓
1. 创建 ServiceContainer 实例
  ↓
2. 注册服务工厂函数
   container.register('llm', lambda: LLMService())
   container.register('mysql', lambda: MySQLService())
   ...
  ↓
3. 初始化所有服务
   await container.initialize_all()
   ├─ 调用工厂函数创建实例
   ├─ 调用 service.initialize()
   └─ 标记为已初始化
  ↓
4. 加载智能体
   ├─ 实例化智能体
   ├─ 注入容器：agent.container = container
   └─ 智能体通过 self.llm、self.mysql 访问服务
  ↓
5. 智能体运行
   使用 self.llm、self.mysql 等访问服务
  ↓
6. 应用关闭
   await container.shutdown_all()
   └─ 反序调用 service.shutdown()
```

### 服务注册流程

```python
# app/main.py（简化版）

from app.core.container import ServiceContainer
from app.core.services import LLMService, MySQLService, MongoDBService

# 1. 创建容器
container = ServiceContainer()

# 2. 注册服务（使用工厂函数）
container.register('llm', lambda: LLMService())

# 3. 可选服务（根据配置决定是否注册）
if settings.mysql_enabled:
    container.register('mysql', lambda: MySQLService())

if settings.mongodb_enabled:
    container.register('mongodb', lambda: MongoDBService())

# 4. 初始化所有服务
await container.initialize_all()

# 5. 加载智能体（注入容器）
AgentLoader.load_all_agents(container=container)
```

### 服务生命周期

```
注册 → 创建 → 初始化 → 使用 → 关闭
 ↓      ↓      ↓       ↓      ↓
register get  initialize  使用  shutdown
         (懒加载)
```

---

## 在智能体中使用服务

### 访问内置服务

智能体基类（`AgentBase`）提供了便捷的 property 来访问常用服务：

```python
class MyAgent(AgentBase):
    async def invoke(self, message, thread_id, context):
        # 1. 访问 LLM 服务
        llm = self.llm
        chat_model = await llm.get_chat_model()
        
        # 2. 访问 MySQL 服务
        mysql = self.mysql
        async with mysql.get_session() as session:
            # 数据库操作
            pass
        
        # 3. 访问 MongoDB 服务
        mongodb = self.mongodb
        # MongoDB 操作
        
        # 4. 访问 Apollo 配置服务
        apollo = self.apollo
        config = apollo.get_config("some_key")
        
        # 5. 访问任意已注册的服务
        custom_service = self.get_service('custom_service')
```

### LLM 服务使用示例

```python
from app.agents.base import AgentBase
from langchain_core.messages import HumanMessage, SystemMessage

class CommonQAAgent(AgentBase):
    async def invoke(self, message, thread_id, context):
        # 1. 获取 LLM 服务
        llm_service = self.llm
        
        # 2. 获取 ChatOpenAI 实例
        chat_model = await llm_service.get_chat_model()
        
        # 3. 调用 LLM
        messages = [
            SystemMessage(content="你是一个通识问答助手"),
            HumanMessage(content=message)
        ]
        response = await chat_model.ainvoke(messages)
        
        # 4. 清理响应内容（移除 thinking 标签）
        cleaned_content = llm_service.clean_response(response.content)
        
        return AgentResponse(
            message=cleaned_content,
            thread_id=thread_id
        )
```

### MySQL 服务使用示例

```python
from app.agents.base import AgentBase
from sqlalchemy import select
from .models import MyDataModel

class MyAgent(AgentBase):
    async def save_data(self, thread_id, data):
        """保存数据到 MySQL"""
        # 1. 获取 MySQL 服务
        mysql = self.mysql
        
        # 2. 获取 session（上下文管理器）
        async with mysql.get_session() as session:
            # 3. 创建数据对象
            record = MyDataModel(
                thread_id=thread_id,
                content=data
            )
            
            # 4. 保存
            session.add(record)
            await session.commit()
    
    async def query_data(self, thread_id):
        """查询数据"""
        mysql = self.mysql
        
        async with mysql.get_session() as session:
            # 使用 SQLAlchemy 查询
            result = await session.execute(
                select(MyDataModel)
                .where(MyDataModel.thread_id == thread_id)
                .order_by(MyDataModel.created_at.desc())
                .limit(10)
            )
            records = result.scalars().all()
            return records
```

### MongoDB 服务使用示例

```python
from app.agents.base import AgentBase
from .models import MyDocumentModel

class MyAgent(AgentBase):
    async def save_to_mongodb(self, thread_id, data):
        """保存数据到 MongoDB"""
        # 1. 查找或创建文档
        document = await MyDocumentModel.find_one(
            MyDocumentModel.thread_id == thread_id
        )
        
        if not document:
            document = MyDocumentModel(
                thread_id=thread_id,
                messages=[]
            )
        
        # 2. 添加数据
        document.messages.append(data)
        
        # 3. 保存
        await document.save()
    
    async def query_from_mongodb(self, thread_id):
        """查询 MongoDB 数据"""
        document = await MyDocumentModel.find_one(
            MyDocumentModel.thread_id == thread_id
        )
        return document.messages if document else []
```

### 服务可用性检查

在使用可选服务前，应检查其是否可用：

```python
class MyAgent(AgentBase):
    async def invoke(self, message, thread_id, context):
        # 方式 1：通过容器检查服务是否注册
        if self.container.has('mysql'):
            mysql = self.mysql
            # 使用 MySQL
        
        # 方式 2：使用 get_service 并提供默认值
        mysql = self.get_service('mysql', default=None)
        if mysql is not None:
            # 使用 MySQL
            pass
        
        # 方式 3：捕获异常
        try:
            mysql = self.mysql
            # 使用 MySQL
        except Exception as e:
            logger.warning(f"MySQL 不可用: {e}")
            # 降级处理
```

---

## 添加自定义服务

### 步骤 1：定义服务类

创建 `app/core/services/my_custom_service.py`：

```python
import logging
from app.core.container import IService

logger = logging.getLogger(__name__)


class MyCustomService(IService):
    """自定义服务示例"""
    
    def __init__(self):
        """初始化服务"""
        self.client = None
        self.config = {}
    
    async def initialize(self) -> None:
        """初始化服务（启动时调用）"""
        logger.info("初始化 MyCustomService...")
        
        # 初始化客户端
        self.client = SomeClient()
        await self.client.connect()
        
        # 加载配置
        self.config = self._load_config()
        
        logger.info("MyCustomService 初始化完成")
    
    async def shutdown(self) -> None:
        """关闭服务（应用关闭时调用）"""
        logger.info("关闭 MyCustomService...")
        
        if self.client:
            await self.client.disconnect()
        
        logger.info("MyCustomService 已关闭")
    
    def do_something(self, param: str) -> str:
        """服务方法"""
        return f"Processed: {param}"
    
    def _load_config(self) -> dict:
        """私有方法：加载配置"""
        return {"key": "value"}
```

### 步骤 2：注册服务

在 `app/main.py` 中注册：

```python
from app.core.services.my_custom_service import MyCustomService

# 在 lifespan 函数中注册
_container.register('my_custom', lambda: MyCustomService())
```

### 步骤 3：在智能体中使用

**方式 1：通过 get_service 访问**

```python
class MyAgent(AgentBase):
    async def invoke(self, message, thread_id, context):
        # 获取自定义服务
        custom_service = self.get_service('my_custom')
        
        # 使用服务
        result = custom_service.do_something(message)
        return AgentResponse(message=result, thread_id=thread_id)
```

**方式 2：添加 property 到 AgentBase**

修改 `app/agents/base.py`，添加便捷访问：

```python
class AgentBase(ABC):
    # ... 现有代码 ...
    
    @property
    def my_custom(self) -> 'MyCustomService':
        """获取自定义服务"""
        if self.container is None:
            raise RuntimeError("服务容器未注入")
        return self.container.get('my_custom')
```

然后在智能体中：

```python
class MyAgent(AgentBase):
    async def invoke(self, message, thread_id, context):
        # 直接访问
        result = self.my_custom.do_something(message)
        return AgentResponse(message=result, thread_id=thread_id)
```

---

## 服务生命周期

### 初始化流程

```python
# app/main.py 中的 lifespan 函数

async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    
    # ========== 启动阶段 ==========
    
    # 1. 创建服务容器
    _container = ServiceContainer()
    
    # 2. 注册所有服务
    _container.register('config', lambda: ConfigService())
    _container.register('llm', lambda: LLMService())
    
    if settings.mysql_enabled:
        _container.register('mysql', lambda: MySQLService())
    
    # 3. 初始化所有服务
    try:
        await _container.initialize_all()
        # 输出：
        # ✓ 服务 'config' 初始化成功
        # ✓ 服务 'llm' 初始化成功
        # ✓ 服务 'mysql' 初始化成功
    except Exception as e:
        logger.error(f"服务初始化失败: {e}")
    
    # 4. 加载智能体（注入容器）
    AgentLoader.load_all_agents(container=_container)
    
    yield  # 应用运行
    
    # ========== 关闭阶段 ==========
    
    # 5. 关闭所有服务
    await _container.shutdown_all()
```

### 服务初始化顺序

服务按照注册顺序初始化，关闭时按照**反序**：

```python
# 注册顺序
container.register('config', ...)   # 1. 先注册
container.register('llm', ...)      # 2. 后注册
container.register('mysql', ...)    # 3. 最后注册

# 初始化顺序（正序）
await container.initialize_all()
# 1. config.initialize()
# 2. llm.initialize()
# 3. mysql.initialize()

# 关闭顺序（反序）
await container.shutdown_all()
# 1. mysql.shutdown()
# 2. llm.shutdown()
# 3. config.shutdown()
```

### 懒加载机制

服务在首次使用时才创建实例：

```python
# 注册服务
container.register('llm', lambda: LLMService())

# 此时服务尚未创建
print(container._services)  # {}

# 首次获取时创建实例
llm = container.get('llm')  # 触发工厂函数

# 再次获取时返回缓存实例（单例模式）
llm2 = container.get('llm')  # 返回相同实例
assert llm is llm2  # True
```

---

## 完整实例

### 实例 1：Common QA 智能体使用服务

```python
# app/agents/common_qa/agent.py

import logging
import json
from app.agents.base import AgentBase
from app.schemas.agent import AgentResponse
from app.core.chat_history import get_chat_history_manager
from .models import CommonQAConversationHistory

logger = logging.getLogger(__name__)


class CommonQAAgent(AgentBase):
    """通识问答智能体"""
    
    def __init__(self):
        super().__init__(
            name="common_agent",
            description="通识问答智能体"
        )
        self.chat_history = None
    
    async def invoke(self, message, thread_id, context):
        """调用智能体"""
        
        # ========== 1. 使用 MySQL 服务保存用户消息 ==========
        try:
            async with self.mysql.get_session() as session:
                user_msg = CommonQAConversationHistory(
                    thread_id=thread_id,
                    role="user",
                    content=message,
                    extra_metadata=json.dumps(context) if context else None
                )
                session.add(user_msg)
                await session.commit()
                logger.debug("MySQL: 用户消息已保存")
        except Exception as e:
            logger.error(f"MySQL 保存失败: {e}")
        
        # ========== 2. 使用 LLM 服务生成回复 ==========
        llm_service = self.llm
        chat_model = await llm_service.get_chat_model()
        
        # 获取历史消息
        if self.chat_history is None:
            self.chat_history = await get_chat_history_manager()
        
        history_messages = await self.chat_history.get_messages(thread_id)
        
        # 调用 LLM
        from langchain_core.messages import HumanMessage, SystemMessage
        messages = history_messages + [HumanMessage(content=message)]
        
        response = await chat_model.ainvoke(messages)
        cleaned_content = llm_service.clean_response(response.content)
        
        # ========== 3. 保存 AI 回复到 MySQL ==========
        try:
            async with self.mysql.get_session() as session:
                ai_msg = CommonQAConversationHistory(
                    thread_id=thread_id,
                    role="assistant",
                    content=cleaned_content
                )
                session.add(ai_msg)
                await session.commit()
                logger.debug("MySQL: AI回复已保存")
        except Exception as e:
            logger.error(f"MySQL 保存AI回复失败: {e}")
        
        # 返回响应
        return AgentResponse(
            message=cleaned_content,
            thread_id=thread_id
        )
```

### 实例 2：自定义服务完整示例

**1. 定义服务**

```python
# app/core/services/email_service.py

import logging
from app.core.container import IService

logger = logging.getLogger(__name__)


class EmailService(IService):
    """邮件服务"""
    
    def __init__(self):
        self.smtp_client = None
    
    async def initialize(self) -> None:
        """初始化 SMTP 客户端"""
        logger.info("初始化邮件服务...")
        # 初始化 SMTP 连接
        self.smtp_client = SMTPClient()
        await self.smtp_client.connect()
        logger.info("邮件服务初始化完成")
    
    async def shutdown(self) -> None:
        """关闭 SMTP 客户端"""
        logger.info("关闭邮件服务...")
        if self.smtp_client:
            await self.smtp_client.disconnect()
        logger.info("邮件服务已关闭")
    
    async def send_email(self, to: str, subject: str, body: str):
        """发送邮件"""
        await self.smtp_client.send(to, subject, body)
        logger.info(f"邮件已发送到: {to}")
```

**2. 注册服务**

```python
# app/main.py

from app.core.services.email_service import EmailService

# 在 lifespan 中注册
_container.register('email', lambda: EmailService())
```

**3. 在智能体中使用**

```python
# app/agents/notification_agent/agent.py

class NotificationAgent(AgentBase):
    async def invoke(self, message, thread_id, context):
        # 使用邮件服务
        email_service = self.get_service('email')
        
        if email_service:
            await email_service.send_email(
                to="user@example.com",
                subject="智能体通知",
                body=f"您的请求已处理: {message}"
            )
        
        return AgentResponse(
            message="已发送邮件通知",
            thread_id=thread_id
        )
```

---

## 最佳实践

### 1. 服务设计原则

✅ **单一职责**：每个服务只负责一个领域
```python
# 好的设计
class LLMService:  # 只负责 LLM 调用
class MySQLService:  # 只负责数据库操作

# 不好的设计
class MegaService:  # 包含 LLM、数据库、邮件等所有功能
```

✅ **实现服务接口**：所有服务应实现 `IService` 接口
```python
from app.core.container import IService

class MyService(IService):
    async def initialize(self) -> None:
        # 初始化逻辑
        pass
    
    async def shutdown(self) -> None:
        # 清理逻辑
        pass
```

✅ **幂等性**：initialize 和 shutdown 应该是幂等的
```python
async def initialize(self) -> None:
    if self.client is not None:
        return  # 已初始化，跳过
    
    self.client = create_client()
```

### 2. 错误处理

✅ **优雅降级**：可选服务不可用时不应中断应用
```python
try:
    async with self.mysql.get_session() as session:
        # 数据库操作
        pass
except Exception as e:
    logger.error(f"MySQL 操作失败: {e}")
    # 继续执行，不中断
```

✅ **检查服务可用性**
```python
# 方式 1：检查是否注册
if self.container.has('mysql'):
    mysql = self.mysql
    # 使用 MySQL

# 方式 2：提供默认值
mysql = self.get_service('mysql', default=None)
if mysql is not None:
    # 使用 MySQL
```

### 3. 性能优化

✅ **懒加载**：服务在首次使用时才创建
```python
# 容器会自动处理懒加载
llm = self.llm  # 首次访问时创建实例
```

✅ **连接池**：使用连接池管理数据库连接
```python
class MySQLService:
    def __init__(self):
        # 使用连接池
        self.engine = create_async_engine(
            url,
            pool_size=10,
            max_overflow=20
        )
```

✅ **避免重复创建**：使用单例模式
```python
# 容器默认使用单例模式
container.register('llm', lambda: LLMService(), singleton=True)
```

### 4. 日志记录

✅ **关键操作记录日志**
```python
async def initialize(self) -> None:
    logger.info("初始化 MyService...")
    # 初始化逻辑
    logger.info("MyService 初始化完成")

async def shutdown(self) -> None:
    logger.info("关闭 MyService...")
    # 清理逻辑
    logger.info("MyService 已关闭")
```

✅ **异常日志**
```python
try:
    await service.do_something()
except Exception as e:
    logger.error(f"操作失败: {e}", exc_info=True)
```

---

## 常见问题

### Q1: 服务容器是什么时候创建的？

**A:** 在应用启动时（`app/main.py` 的 `lifespan` 函数中）：

```python
async def lifespan(app: FastAPI):
    # 应用启动
    _container = ServiceContainer()  # 创建容器
    # ... 注册和初始化服务 ...
    yield
    # 应用关闭
    await _container.shutdown_all()
```

### Q2: 如何在智能体中访问服务？

**A:** 通过智能体基类提供的 property：

```python
class MyAgent(AgentBase):
    async def invoke(self, message, thread_id, context):
        # 访问内置服务
        llm = self.llm
        mysql = self.mysql
        mongodb = self.mongodb
        
        # 访问自定义服务
        custom = self.get_service('custom_service')
```

### Q3: 服务是单例吗？

**A:** 是的，默认情况下所有服务都是单例：

```python
# 注册时默认 singleton=True
container.register('llm', lambda: LLMService())

# 多次获取返回同一实例
llm1 = container.get('llm')
llm2 = container.get('llm')
assert llm1 is llm2  # True
```

### Q4: 如何添加自定义服务？

**A:** 三个步骤：

1. **定义服务类**（实现 `IService` 接口）
2. **注册服务**（在 `app/main.py` 中）
3. **使用服务**（在智能体中通过 `self.get_service()` 访问）

详见：[添加自定义服务](#添加自定义服务)

### Q5: 服务初始化失败会影响应用启动吗？

**A:** 不会。容器会捕获异常并记录日志，不会中断应用：

```python
try:
    await service.initialize()
    logger.info(f"✓ 服务 '{name}' 初始化成功")
except Exception as e:
    logger.error(f"初始化服务 '{name}' 失败: {e}")
    # 继续初始化其他服务
```

### Q6: 如何处理可选服务？

**A:** 在使用前检查服务是否可用：

```python
# 方式 1：检查容器
if self.container.has('mysql'):
    mysql = self.mysql

# 方式 2：使用 get_service 并提供默认值
mysql = self.get_service('mysql', default=None)
if mysql is not None:
    # 使用 MySQL

# 方式 3：try-except
try:
    mysql = self.mysql
    # 使用 MySQL
except Exception:
    # 服务不可用，降级处理
    pass
```

### Q7: 服务的生命周期是怎样的？

**A:** 服务的完整生命周期：

```
注册 → 创建（懒加载）→ 初始化 → 使用 → 关闭
 ↓       ↓            ↓      ↓     ↓
register get      initialize  运行  shutdown
```

详见：[服务生命周期](#服务生命周期)

### Q8: 为什么要使用依赖注入？

**A:** 依赖注入的优势：

- ✅ **松耦合**：智能体不依赖具体实现
- ✅ **易测试**：可以轻松替换服务进行单元测试
- ✅ **易维护**：统一管理所有服务，修改方便
- ✅ **灵活配置**：根据配置启用/禁用服务

### Q9: 容器中的服务可以互相依赖吗？

**A:** 可以，但要注意依赖顺序：

```python
# 注册顺序很重要
container.register('config', lambda: ConfigService())
container.register('llm', lambda: LLMService(
    # 在工厂函数中获取其他服务
    config=container.get('config')
))
```

### Q10: 如何在非智能体代码中使用服务？

**A:** 通过全局容器获取：

```python
# app/main.py
from app.main import get_container

def my_function():
    container = get_container()
    llm = container.get('llm')
    # 使用 LLM 服务
```

---

## 相关文档

- [核心服务使用指南](./CORE_SERVICES_GUIDE.md) - Redis、MySQL、MongoDB、Apollo 具体使用方法
- [共享表与独立表指南](./SHARED_VS_INDEPENDENT_TABLES.md) - 数据存储架构
- [智能体开发指南](./AGENT_MANAGEMENT_API.md) - 智能体开发完整指南

---

## 总结

ServiceContainer 是 AgentFlow 平台的核心组件之一，它提供了：

✅ **统一的服务管理**：所有服务集中注册和管理  
✅ **自动依赖注入**：服务自动注入到智能体  
✅ **生命周期管理**：统一初始化和关闭  
✅ **懒加载机制**：按需创建服务实例  
✅ **单例模式**：避免重复创建，节省资源  

通过服务容器，智能体可以专注于业务逻辑，无需关心服务的创建和管理，实现了真正的**松耦合**和**高内聚**。

