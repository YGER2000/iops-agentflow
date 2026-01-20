# 多轮对话状态管理机制

## 概述

本平台使用 **thread_id** 机制和 **Redis** 存储来支持多轮对话，每个会话的对话历史和状态都会持久化存储。

## 核心组件

### 1. ChatHistoryManager（会话历史管理器）

位置：`app/core/chat_history.py`

**主要功能：**
- 存储和检索对话消息历史
- 存储和检索会话状态数据
- 支持Redis和内存两种存储方式

**关键方法：**

```python
# 消息管理
add_message(thread_id, message)           # 添加单条消息
add_messages(thread_id, messages)         # 批量添加消息
get_messages(thread_id, limit=None)       # 获取历史消息
clear_history(thread_id)                  # 清空消息历史

# 状态管理
save_state(thread_id, state_data)         # 保存会话状态
get_state(thread_id)                      # 获取会话状态
clear_state(thread_id)                    # 清空会话状态
```

### 2. thread_id（会话标识符）

- 每个对话会话由唯一的 `thread_id` 标识
- 客户端可以指定 `thread_id`，如果不指定则自动生成
- 同一个 `thread_id` 下的所有对话共享历史消息和状态

## 多轮对话工作流程

### 通识问答智能体（Common QA Agent）

```
第一轮对话:
  用户: "什么是Python?"
  → 智能体加载历史消息（空）
  → 添加系统提示词
  → 调用LLM生成回答
  → 保存用户消息和AI回答到Redis
  
第二轮对话（同一thread_id）:
  用户: "它有哪些特点?"
  → 智能体从Redis加载历史消息
  → 包含之前关于Python的对话
  → AI理解"它"指的是Python
  → 保存新的对话到Redis
```

### CMDB智能体（CMDB Smart Query Agent）

CMDB智能体除了消息历史，还需要保存**状态数据**（如查询到的资源列表）。

```
第一轮对话:
  用户: "查询浦江25号支付系统"
  → 加载历史消息（空）
  → 加载历史状态（空）
  → 执行资源查询
  → 返回资源列表
  → 保存消息历史到Redis
  → 保存状态到Redis: {resources: [...], last_intent: "query_resource"}
  
第二轮对话（同一thread_id）:
  用户: "已选择资源[浦江25号支付系统]"
  → 加载历史消息（包含第一轮对话）
  → 加载历史状态（包含resources列表）✅ 关键！
  → 智能体知道之前返回过哪些资源
  → 用户已选择资源，可以查询关系
  → 保存新的对话和状态
```

## 数据存储结构

### Redis Key设计

```
chat_history:{thread_id}   → 消息列表 (List)
  - 存储格式: JSON字符串
  - 过期时间: 7天
  - 示例: [
      {"type": "HumanMessage", "content": "你好"},
      {"type": "AIMessage", "content": "您好！有什么可以帮您？"}
    ]

chat_state:{thread_id}     → 状态数据 (String)
  - 存储格式: JSON字符串
  - 过期时间: 7天
  - 示例: {
      "resources": [{...}],
      "last_intent": "query_resource"
    }
```

## CMDB智能体状态持久化

### 持久化的状态字段

在 `CMDBSmartQueryAgent.invoke()` 中：

```python
# 恢复上一轮的状态
previous_state = self.chat_history.get_state(thread_id) or {}

initial_state = {
    "resources": previous_state.get("resources"),  # 从上一轮恢复
    # ... 其他字段
}

# 执行智能体逻辑
result = await graph.ainvoke(initial_state)

# 保存本轮状态供下一轮使用
state_to_save = {
    "resources": result.get("resources"),
    "last_intent": result.get("intent"),
}
self.chat_history.save_state(thread_id, state_to_save)
```

### 为什么需要状态持久化？

**问题场景：**
如果每次对话都创建全新的 `CMDBState`，会导致：
1. ❌ 第二轮对话时不知道第一轮查询了哪些资源
2. ❌ 无法判断"用户是否已经收到资源列表"
3. ❌ 多轮对话逻辑无法正常工作

**解决方案：**
通过 `save_state()` 和 `get_state()` 在多轮对话之间传递状态：
1. ✅ resources 字段持久化，下一轮可以访问
2. ✅ 智能体能判断"之前是否返回过资源"
3. ✅ 支持"查资源 → 选资源 → 查关系"的完整流程

## 使用示例

### API调用

```python
# 第一轮对话
response1 = await invoke_agent({
    "agent_name": "cmdb_smart_query_agent",
    "message": "查询浦江25号支付系统",
    "thread_id": "user123-session-001"  # 指定会话ID
})

# 第二轮对话（相同thread_id）
response2 = await invoke_agent({
    "agent_name": "cmdb_smart_query_agent",
    "message": "已选择资源[浦江25号支付系统]",
    "thread_id": "user123-session-001",  # 相同会话ID
    "context": {
        "selected_resource": {
            "id": "68c5352324462a16b91bb076",
            "classCode": "AppModule"
        }
    }
})
```

### 清空会话

```python
# 清空消息历史和状态
chat_history = get_chat_history_manager()
chat_history.clear_history("user123-session-001")
chat_history.clear_state("user123-session-001")
```

## 配置

### Redis配置（.env文件）

```bash
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=  # 可选
```

### 容错机制

如果Redis连接失败，系统会自动降级使用**内存存储**：
```
警告: Redis连接失败，使用内存存储: Connection refused
```

## 最佳实践

1. **客户端管理thread_id**：建议客户端维护 thread_id，确保同一用户会话使用相同ID
2. **定期清理**：对于已结束的会话，及时调用 `clear_history` 和 `clear_state`
3. **状态字段选择**：只持久化必要的状态字段，避免存储过大对象
4. **过期时间**：当前设置为7天，可根据业务需求调整

## 与Checkpoint的区别

| 特性 | Checkpoint机制 | thread_id + 状态管理 |
|------|----------------|---------------------|
| 对话历史 | 自动保存整个图状态 | 手动保存消息和状态 |
| 灵活性 | 低（LangGraph内置） | 高（自定义存储内容） |
| 存储控制 | 黑盒 | 透明可控 |
| 状态恢复 | 自动 | 手动加载 |
| 适用场景 | 简单对话 | 复杂业务逻辑 |

我们选择 thread_id + 状态管理方案是因为：
- ✅ 更灵活地控制状态持久化
- ✅ 清晰的状态管理逻辑
- ✅ 便于调试和监控
- ✅ 支持复杂的业务状态

