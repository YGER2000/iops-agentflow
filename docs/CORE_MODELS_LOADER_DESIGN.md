# 核心共享模型加载器设计文档

## 📋 设计背景

### 为什么需要单独的共享模型加载器？

在之前的设计中，共享模型的注册依赖于智能体的导入：

```
❌ 旧设计：依赖智能体导入
加载智能体 → 导入智能体 models → 触发导入共享模型 → 注册
```

**问题：**
1. ❌ 依赖性强：共享模型必须被某个智能体导入才会注册
2. ❌ 不确定性：如果所有智能体都不使用共享模型，它不会被注册
3. ❌ 逻辑不清晰：共享模型和智能体模型混在一起处理
4. ❌ 顺序敏感：依赖智能体加载顺序

### 改进后的设计

```
✅ 新设计：独立加载
初始化服务 → 加载核心共享模型 → 加载智能体模型 → 创建表
```

**优点：**
1. ✅ **独立性**：共享模型独立于智能体加载
2. ✅ **确定性**：共享模型一定会被加载和注册
3. ✅ **逻辑清晰**：共享模型和智能体模型分开管理
4. ✅ **顺序明确**：先加载共享模型，再加载智能体模型

---

## 🏗️ 架构设计

### 完整的启动流程

```
应用启动 (FastAPI lifespan)
    ↓
1️⃣ 创建服务容器
    ServiceContainer()
    ↓
2️⃣ 注册并初始化服务
    - ConfigService
    - LLMService
    - MySQLService ←── 稍后接收共享模型
    - MongoDBService ←── 稍后接收共享模型
    - ApolloService
    - ApiKeyService
    ↓
3️⃣ 加载核心共享模型 ⭐ 新增步骤
    CoreModelsLoader.load_core_models()
    ├─ 扫描 app/core/models/ 目录
    ├─ 导入 app.core.models 模块
    ├─ 使用 inspect 识别模型类
    ├─ 注册 SQLAlchemy 模型到 MySQLService
    └─ 注册 Beanie Document 到 MongoDBService
    ↓
    输出日志：
    - 发现共享 SQLAlchemy 模型: SharedConversationHistory
    - 发现共享 Beanie Document: SharedConversationHistoryMongo
    - ✓ 注册了 N 个共享模型
    ↓
4️⃣ 加载智能体
    AgentLoader.load_all_agents()
    ├─ 扫描 app/agents/ 目录
    ├─ 对每个智能体：
    │   ├─ 导入智能体类
    │   ├─ 扫描 models/ 目录（如果存在）
    │   ├─ 识别 SQLAlchemy 模型和 Beanie Document
    │   └─ 注册到对应服务
    ↓
5️⃣ 创建数据库表/集合
    mysql.create_tables()
    mongodb.init_beanie()
    ├─ 创建所有已注册的表
    └─ 创建所有已注册的集合
    ↓
✅ 启动完成
```

### 目录结构

```
app/
├── core/
│   └── models/
│       ├── __init__.py                          # 导出共享模型
│       ├── loader.py                            # ⭐ 核心模型加载器
│       ├── shared_conversation_history.py       # MySQL 共享模型
│       └── shared_conversation_history_mongo.py # MongoDB 共享模型
│
├── agents/
│   ├── cmdb_smart_query/
│   │   └── models/
│   │       ├── __init__.py                      # 导入共享模型（可选）
│   │       └── (智能体特有模型)
│   │
│   └── common_qa/
│       └── models/
│           ├── __init__.py
│           ├── conversation_history.py          # 独立模型
│           └── conversation_history_mongo.py    # 独立模型
│
└── main.py                                      # 应用入口，调用加载器
```

---

## 💻 核心代码

### CoreModelsLoader 实现

```python
# app/core/models/loader.py

class CoreModelsLoader:
    """核心共享模型加载器
    
    在应用启动时自动扫描和注册共享模型，
    独立于智能体加载流程，逻辑更清晰。
    """
    
    @classmethod
    def load_core_models(cls, container=None) -> None:
        """加载所有核心共享模型"""
        loader = cls(container)
        loader._load_all()
    
    def _load_all(self) -> None:
        """扫描并注册共享模型"""
        # 1. 导入 app.core.models 模块
        models_module = importlib.import_module('app.core.models')
        
        # 2. 使用 inspect 扫描模块成员
        sqlalchemy_models = []
        beanie_documents = []
        
        for name, obj in inspect.getmembers(models_module):
            if self._is_sqlalchemy_model(obj):
                sqlalchemy_models.append(obj)
            elif self._is_beanie_document(obj):
                beanie_documents.append(obj)
        
        # 3. 注册到对应服务
        if sqlalchemy_models:
            mysql_service = self.container.get('mysql')
            mysql_service.register_models(Base.metadata)
        
        if beanie_documents:
            mongodb_service = self.container.get('mongodb')
            mongodb_service.register_documents(beanie_documents)
```

### main.py 调用

```python
# app/main.py

from app.core.models.loader import CoreModelsLoader

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. 初始化服务
    await _container.initialize_all()
    
    # 2. 加载核心共享模型 ⭐ 优先加载
    print("\n正在加载核心共享模型...")
    CoreModelsLoader.load_core_models(container=_container)
    
    # 3. 加载智能体
    print("\n正在加载智能体...")
    AgentLoader.load_all_agents(container=_container)
    
    # 4. 创建表/集合
    await mysql.create_tables()
    await mongodb.init_beanie()
```

---

## 📊 启动日志对比

### 改进前的日志

```bash
正在加载智能体...
INFO:app.agents.loader:正在加载智能体: cmdb_smart_query (v1.0.0)
INFO:app.agents.loader:已导入智能体 [cmdb_smart_query] 的 models 模块
INFO:app.agents.loader:发现 SQLAlchemy 模型: SharedConversationHistory  # ← 依赖智能体导入
INFO:app.agents.loader:智能体 [cmdb_smart_query] 注册了 1 个 SQLAlchemy 模型

INFO:app.agents.loader:正在加载智能体: common_qa (v1.0.0)
INFO:app.agents.loader:发现 SQLAlchemy 模型: CommonQAConversationHistory
...
```

### 改进后的日志

```bash
正在加载核心共享模型...  # ⭐ 新增步骤
INFO:app.core.models.loader:开始扫描核心共享模型目录
INFO:app.core.models.loader:发现共享 SQLAlchemy 模型: SharedConversationHistory (表: shared_conversation_history)
INFO:app.core.models.loader:发现共享 Beanie Document: SharedConversationHistoryMongo (集合: shared_conversation_history)
INFO:app.core.models.loader:✓ 注册了 1 个共享 SQLAlchemy 模型
INFO:app.core.models.loader:✓ 注册了 1 个共享 Beanie Document

正在加载智能体...  # 智能体加载更纯粹
INFO:app.agents.loader:正在加载智能体: cmdb_smart_query (v1.0.0)
INFO:app.agents.loader:已导入智能体 [cmdb_smart_query] 的 models 模块
# 没有共享模型的日志，因为智能体只是导入使用，不负责注册

INFO:app.agents.loader:正在加载智能体: common_qa (v1.0.0)
INFO:app.agents.loader:发现 SQLAlchemy 模型: CommonQAConversationHistory  # 只有独立模型
INFO:app.agents.loader:智能体 [common_qa] 注册了 1 个 SQLAlchemy 模型
...
```

---

## 🔄 工作流程对比

### 场景 1：智能体使用共享模型

**改进前：**
```python
# app/agents/cmdb_smart_query/models/__init__.py
from app.core.models import SharedConversationHistory  # ← 触发注册

# 问题：如果没有智能体导入，共享模型不会被注册
```

**改进后：**
```python
# 共享模型已在应用启动时注册 ✅
# 智能体只需导入使用，不负责注册

# app/agents/cmdb_smart_query/models/__init__.py
from app.core.models import SharedConversationHistory  # 只是导入使用
```

### 场景 2：新增共享模型

**改进前：**
```python
# 1. 在 app/core/models/ 创建新模型
# 2. 在 __init__.py 中导出
# 3. 必须有至少一个智能体导入它 ❌
# 4. 否则不会被注册和创建表
```

**改进后：**
```python
# 1. 在 app/core/models/ 创建新模型
# 2. 在 __init__.py 中导出
# 3. 重启应用，自动注册 ✅
# 4. 无需任何智能体导入
```

---

## 🎯 设计优势

### 1. 职责分离

```
CoreModelsLoader    → 负责共享模型
    ↓
AgentLoader         → 负责智能体模型
    ↓
MySQLService        → 负责创建表
MongoDBService      → 负责创建集合
```

### 2. 可扩展性

**添加新的共享模型：**
```python
# 1. 创建模型文件
# app/core/models/shared_user_preferences.py
class SharedUserPreferences(Base, TimestampMixin):
    __tablename__ = 'shared_user_preferences'
    # ...

# 2. 在 __init__.py 导出
from .shared_user_preferences import SharedUserPreferences

# 3. 重启应用 → 自动注册 → 自动创建表 ✅
```

### 3. 可维护性

**清晰的分层：**
- `app/core/models/` - 共享模型定义
- `app/core/models/loader.py` - 共享模型加载逻辑
- `app/agents/*/models/` - 智能体独立模型
- `app/agents/loader.py` - 智能体模型加载逻辑

### 4. 可测试性

```python
# 可以独立测试共享模型加载
def test_core_models_loader():
    container = MockContainer()
    CoreModelsLoader.load_core_models(container=container)
    
    # 验证模型已注册
    assert mysql_service.has_model('shared_conversation_history')
    assert mongodb_service.has_document('SharedConversationHistoryMongo')
```

---

## 📝 使用指南

### 定义共享模型

```python
# app/core/models/shared_xxx.py

from app.core.services.db_base import Base, TimestampMixin

class SharedXxx(Base, TimestampMixin):
    __tablename__ = 'shared_xxx'
    # 字段定义...
```

### 在智能体中使用共享模型

```python
# app/agents/your_agent/models/__init__.py

# 方式1：直接导入使用
from app.core.models import SharedConversationHistory

# 方式2：使用别名（向后兼容）
from app.core.models import SharedConversationHistory as ConversationHistory

# 在智能体代码中使用
async with self.mysql.get_session() as session:
    msg = SharedConversationHistory(
        thread_id=thread_id,
        agent_name=self.name,
        # ...
    )
    session.add(msg)
    await session.commit()
```

---

## 🔍 常见问题

### Q1: 共享模型会重复注册吗？

**A:** 不会。`MySQLService.register_models()` 有去重机制：

```python
def register_models(self, metadata: MetaData):
    if metadata not in self._metadata_list:  # ← 防止重复
        self._metadata_list.append(metadata)
```

### Q2: 智能体还需要导入共享模型吗？

**A:** 需要。智能体需要导入共享模型**使用**，但不负责**注册**：

- ✅ 注册：由 `CoreModelsLoader` 在应用启动时完成
- ✅ 使用：智能体导入后正常使用

### Q3: 如果 core/models/ 下没有共享模型会怎样？

**A:** `CoreModelsLoader` 会输出日志 "未发现任何共享模型"，然后继续加载智能体，不会报错。

### Q4: 这个改进是否向后兼容？

**A:** 完全兼容。智能体的使用方式不变，只是注册时机提前了：

```python
# 智能体代码无需修改
from app.core.models import SharedConversationHistory

# 仍然正常工作 ✅
```

---

## 📈 性能影响

### 启动时间

- **增加时间**: < 100ms（只扫描一个 core/models 目录）
- **减少时间**: 共享模型只注册一次（之前可能被多个智能体重复处理）

### 内存占用

- **无额外开销**：模型类本身占用的内存不变

### 运行时性能

- **无影响**：注册只在启动时发生，运行时性能完全相同

---

## 🎉 总结

### 改进前 vs 改进后

| 方面 | 改进前 | 改进后 |
|------|--------|--------|
| **注册时机** | 智能体导入时 | 应用启动时 ⭐ |
| **依赖关系** | 依赖智能体 | 独立 ⭐ |
| **逻辑清晰度** | 混在一起 | 分离清晰 ⭐ |
| **可维护性** | 中等 | 高 ⭐ |
| **可测试性** | 困难 | 容易 ⭐ |
| **确定性** | 不确定 | 确定 ⭐ |

### 核心价值

1. ✅ **职责分离**：共享模型和智能体模型各司其职
2. ✅ **逻辑清晰**：加载流程一目了然
3. ✅ **易于维护**：添加共享模型不需要修改智能体
4. ✅ **向后兼容**：现有代码无需修改

---

## 🔗 相关文档

- [共享表 vs 独立表使用指南](./SHARED_VS_INDEPENDENT_TABLES.md)
- [核心服务使用指南](./CORE_SERVICES_GUIDE.md)
- [实施总结](./IMPLEMENTATION_SUMMARY_SHARED_TABLES.md)

---

**设计日期：** 2025-11-04  
**设计版本：** v2.0.0（改进版）

