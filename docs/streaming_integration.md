# 流式响应集成指南

## 概述

平台支持两种调用方式：
1. **普通调用** (`/api/v1/agent/invoke`) - 一次性返回完整结果
2. **流式调用** (`/api/v1/agent/stream`) - 实时流式返回结果（推荐用于文本生成）, 优云前端bitmind默认调用流式接口

## 流式响应优势

✅ **更好的用户体验** - 用户可以实时看到 AI 的思考过程  
✅ **降低感知延迟** - 不需要等待完整响应  
✅ **适合长文本** - 特别适合通识问答等需要生成大量文本的场景  

## API 规范

### 请求格式

```http
POST /api/v1/agent/stream
Content-Type: application/json

{
  "agent_name": "common_agent",
  "message": "什么是人工智能?",
  "thread_id": "session-001",  // 可选，用于多轮对话
  "context": {}                // 可选，额外上下文
}
```

### 响应格式（Server-Sent Events）

响应使用 SSE (Server-Sent Events) 格式，包含多种事件类型：

#### 事件类型

| 事件类型 | 说明 | 数据格式 |
|---------|------|---------|
| `message` | 文本片段（流式输出） | `string` - 文本内容 |
| `data` | 结构化数据（如资源列表） | `object` - 包含 data, need_user_action, action_type |
| `metadata` | 元数据 | `object` - 统计信息、线程ID等 |
| `done` | 完成信号 | `object` - 包含 thread_id |
| `error` | 错误信息 | `object` - 包含 error 字段 |

#### 示例流

```
event: message
data: "人工智能"

event: message
data: "（Artificial Intelligence, AI）是"

event: message
data: "计算机科学的一个分支..."

event: metadata
data: {"thread_id": "session-001", "message_length": 256}

event: done
data: {"thread_id": "session-001"}
```

## 前端集成
直接与优云bitmind页面对接，bitmind会调用智能体的/api/v1/agent/stream接口

## 智能体流式支持情况

| 智能体 | 流式支持 | 说明 |
|--------|---------|------|
| `common_agent` | ✅ 完全支持 | 使用 LLM 流式 API，逐字输出 |
| `cmdb_smart_query_agent` | ⚠️ 降级支持 | 回退到普通调用，一次性返回 |

### 自定义智能体添加流式支持

如果您要为自定义智能体添加流式支持，需要重写 `stream()` 方法：

```python
from typing import AsyncGenerator, Dict, Any

class MyCustomAgent(AgentBase):
    async def stream(
        self,
        message: str,
        thread_id: str,
        context: Dict[str, Any] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """流式调用"""
        
        # 1. 发送文本片段
        for word in ["你好", "，", "世界", "！"]:
            yield {
                "type": "message",
                "data": word
            }
        
        # 2. 发送结构化数据（可选）
        yield {
            "type": "data",
            "data": {
                "data": {"result": "some data"},
                "need_user_action": False,
                "action_type": None
            }
        }
        
        # 3. 发送元数据（可选）
        yield {
            "type": "metadata",
            "data": {
                "thread_id": thread_id,
                "word_count": 4
            }
        }
```

## 性能优化建议

1. **连接复用** - 对于多轮对话，使用同一个 `thread_id`
2. **错误处理** - 务必处理网络断开、超时等异常情况
3. **用户反馈** - 显示加载动画或闪烁光标，提升体验
4. **取消请求** - 允许用户中途取消流式请求

```javascript
// 可取消的流式请求
const controller = new AbortController();

fetch('/api/v1/agent/stream', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(request),
  signal: controller.signal  // 添加信号
});

// 用户点击"停止"按钮时
stopButton.onclick = () => {
  controller.abort();
};
```

## 常见问题

### Q: 如何处理流式请求中的错误？

A: 监听 `error` 事件，捕获异常后显示错误信息并停止渲染。

### Q: 流式响应支持断点续传吗？

A: 不支持。如果连接中断，需要重新发起请求。建议在连接不稳定的环境使用普通调用。

## 总结

流式响应特别适合：
- ✅ 通识问答（长文本生成）
- ✅ 需要实时反馈的场景
- ✅ 提升用户体验

不适合流式响应的场景：
- ❌ 快速 API 调用（如资源查询）
- ❌ 结构化数据返回
- ❌ 需要完整响应才能处理的逻辑

