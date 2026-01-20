# 智能体管理 API 文档

本文档介绍如何通过 API 管理智能体。

## API 端点概览

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/api/v1/agent-management/agents` | 列出所有智能体 |
| GET | `/api/v1/agent-management/agents/{agent_name}` | 获取智能体详情 |
| POST | `/api/v1/agent-management/agents/{agent_name}/enable` | 启用智能体 |
| POST | `/api/v1/agent-management/agents/{agent_name}/disable` | 禁用智能体 |
| DELETE | `/api/v1/agent-management/agents/{agent_name}` | 删除智能体 |
| POST | `/api/v1/agent-management/reload` | 重新加载所有智能体 |
| GET | `/api/v1/agent-management/health` | 健康检查 |

## API 详细说明

### 1. 列出所有智能体

列出所有已安装的智能体（包括已启用和已禁用的）。

**请求:**
```http
GET /api/v1/agent-management/agents
```

**响应:**
```json
{
  "total": 2,
  "agents": [
    {
      "name": "cmdb_smart_query_agent",
      "version": "1.0.0",
      "description": "CMDB智能问数智能体",
      "author": "CMDB团队",
      "enabled": true,
      "is_loaded": true,
      "entry_class": "CMDBSmartQueryAgent",
      "dependencies": [],
      "has_requirements": true,
      "directory": "cmdb_smart_query"
    },
    {
      "name": "common_agent",
      "version": "1.0.0",
      "description": "通识问答智能体",
      "author": "平台团队",
      "enabled": true,
      "is_loaded": true,
      "entry_class": "CommonQAAgent",
      "dependencies": [],
      "has_requirements": false,
      "directory": "common_qa"
    }
  ]
}
```

**字段说明:**
- `enabled`: 配置文件中的启用状态
- `is_loaded`: 是否已加载到注册中心（运行中）
- `has_requirements`: 是否有依赖包需要安装

### 2. 获取智能体详情

获取指定智能体的详细信息。

**请求:**
```http
GET /api/v1/agent-management/agents/cmdb_smart_query
```

**响应:**
```json
{
  "name": "cmdb_smart_query_agent",
  "version": "1.0.0",
  "description": "CMDB智能问数智能体",
  "author": "CMDB团队",
  "enabled": true,
  "is_loaded": true,
  "entry_class": "CMDBSmartQueryAgent",
  "dependencies": [],
  "has_requirements": true,
  "directory": "cmdb_smart_query",
  "requirements": [
    "httpx>=0.24.0",
    "pyyaml>=6.0"
  ],
  "readme": "# CMDB 智能体\n\n...",
  "files": {
    "prompts": ["validate.md", "parse.md", "intent.md"],
    "schemas": ["mcp.py"],
    "services": ["base.py", "search.py", "relation.py"]
  }
}
```

### 3. 启用智能体

启用一个已禁用的智能体。

**请求:**
```http
POST /api/v1/agent-management/agents/my_agent/enable
```

**响应:**
```json
{
  "success": true,
  "message": "智能体 my_agent 已启用",
  "note": "需要重新加载才能生效"
}
```

### 4. 禁用智能体

禁用一个智能体（不会删除文件）。

**请求:**
```http
POST /api/v1/agent-management/agents/my_agent/disable
```

**响应:**
```json
{
  "success": true,
  "message": "智能体 my_agent 已禁用",
  "note": "需要重新加载才能生效"
}
```

### 5. 删除智能体

永久删除智能体（删除整个目录）。

**请求:**
```http
DELETE /api/v1/agent-management/agents/my_agent
```

**响应:**
```json
{
  "success": true,
  "message": "智能体 my_agent 已删除",
  "deleted_agent": {
    "name": "my_agent",
    "version": "1.0.0",
    "description": "我的智能体"
  },
  "note": "需要重新加载才能从注册中心移除"
}
```

### 6. 重新加载智能体

清空注册中心并重新加载所有启用的智能体。

**请求:**
```http
POST /api/v1/agent-management/reload
```

**响应:**
```json
{
  "success": true,
  "message": "智能体重新加载成功",
  "loaded_count": 2,
  "agents": [
    {
      "name": "cmdb_smart_query_agent",
      "description": "CMDB智能问数智能体"
    },
    {
      "name": "common_agent",
      "description": "通识问答智能体"
    }
  ]
}
```

**⚠️ 警告**: 重新加载会清空当前运行中的所有智能体实例。

### 7. 健康检查

检查智能体管理服务的状态。

**请求:**
```http
GET /api/v1/agent-management/health
```

**响应:**
```json
{
  "status": "healthy",
  "agents_directory": "/path/to/app/agents",
  "loaded_agents_count": 2
}
```

## 常见使用场景

### 场景 1: 临时禁用智能体

```bash
# 1. 禁用智能体
curl -X POST http://localhost:8000/api/v1/agent-management/agents/my_agent/disable

# 2. 重新加载
curl -X POST http://localhost:8000/api/v1/agent-management/reload

# 3. 验证已禁用
curl http://localhost:8000/api/v1/agent-management/agents/my_agent
```

### 场景 2: 删除智能体

```bash
# 1. 删除智能体
curl -X DELETE http://localhost:8000/api/v1/agent-management/agents/my_agent

# 2. 重新加载
curl -X POST http://localhost:8000/api/v1/agent-management/reload

# 3. 验证已删除
curl http://localhost:8000/api/v1/agents
```

## 前端集成示例

### React 示例

```typescript
// 列出所有智能体
async function listAgents() {
  const response = await fetch('/api/v1/agent-management/agents');
  return await response.json();
}

// 启用智能体
async function enableAgent(agentName: string) {
  const response = await fetch(`/api/v1/agent-management/agents/${agentName}/enable`, {
    method: 'POST'
  });
  return await response.json();
}

// 禁用智能体
async function disableAgent(agentName: string) {
  const response = await fetch(`/api/v1/agent-management/agents/${agentName}/disable`, {
    method: 'POST'
  });
  return await response.json();
}

// 删除智能体
async function deleteAgent(agentName: string) {
  const response = await fetch(`/api/v1/agent-management/agents/${agentName}`, {
    method: 'DELETE'
  });
  return await response.json();
}

// 重新加载智能体
async function reloadAgents() {
  const response = await fetch('/api/v1/agent-management/reload', {
    method: 'POST'
  });
  return await response.json();
}

// 使用示例
function AgentManagement() {
  const [agents, setAgents] = React.useState([]);

  const loadAgents = async () => {
    const result = await listAgents();
    setAgents(result.agents);
  };

  const handleToggle = async (agentName: string, enabled: boolean) => {
    if (enabled) {
      await disableAgent(agentName);
    } else {
      await enableAgent(agentName);
    }
    await reloadAgents();
    await loadAgents();
  };

  React.useEffect(() => {
    loadAgents();
  }, []);

  return (
    <div>
      {agents.map(agent => (
        <div key={agent.name}>
          <span>{agent.name}</span>
          <button onClick={() => handleToggle(agent.name, agent.enabled)}>
            {agent.enabled ? '禁用' : '启用'}
          </button>
        </div>
      ))}
    </div>
  );
}
```

## 安全建议

1. **权限控制**: 在生产环境中应该添加身份验证和授权
2. **审计日志**: 记录所有管理操作
3. **备份**: 在删除智能体前备份数据

## 错误处理

### 常见错误

| 状态码 | 错误 | 说明 |
|--------|------|------|
| 404 | Not Found | 智能体不存在 |
| 500 | Internal Server Error | 服务器内部错误 |

### 错误响应格式

```json
{
  "detail": "错误描述信息"
}
```

## 注意事项

1. **重新加载**: 启用/禁用/删除智能体后需要调用 `/reload` 才能生效
2. **服务重启**: 某些情况下可能需要完全重启服务
3. **线程安全**: 重新加载会影响所有正在进行的对话
4. **持久化**: 智能体的运行时状态不会被持久化

## API 文档访问

启动服务后，可以通过以下地址访问交互式 API 文档：

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

在 Swagger UI 中可以直接测试所有 API 接口。

