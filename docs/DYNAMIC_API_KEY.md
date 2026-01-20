# 动态 API Key 管理

## 概述

因为交行软开调用大模型的apikey有过期时间，本系统支持从远程服务动态获取 LLM API Key，解决 API Key 会定期变更的问题。

## 功能特性

- **自动获取**：从配置的 URL 自动获取 API Key
- **智能缓存**：缓存 API Key，避免频繁请求
- **失败重试**：获取失败时自动重试 3 次
- **备用机制**：如果动态获取失败，使用配置文件中的备用 API Key
- **向后兼容**：可通过配置开关禁用，使用传统的固定 API Key

## 配置说明

在 `.env` 文件中添加以下配置：

```bash
# LLM 配置
LLM_API_KEY=your_backup_api_key_here  # 备用 API Key
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4
LLM_TEMPERATURE=0.7

# API Key 动态获取配置
APIKEY_SERVICE_ENABLED=true  # 是否启用动态获取（true/false）
APIKEY_SERVICE_URL=http://127.0.0.1:4532/getApikey  # API Key 获取地址
APIKEY_EXPIRE_SECONDS=600  # API Key 有效期（秒，默认 10 分钟）
APIKEY_REFRESH_BEFORE_SECONDS=120  # 提前多久刷新（秒，默认 2 分钟）
APIKEY_SCENE_CODE=P2025122
```

### 配置项说明

| 配置项 | 类型 | 默认值 | 说明                    |
|--------|------|--------|-----------------------|
| `APIKEY_SERVICE_ENABLED` | bool | true | 是否启用动态 API Key 获取     |
| `APIKEY_SERVICE_URL` | str | http://127.0.0.1:4532/getApikey | API Key 获取接口地址        |
| `APIKEY_EXPIRE_SECONDS` | int | 600 | API Key 有效期（秒）        |
| `APIKEY_REFRESH_BEFORE_SECONDS` | int | 120 | 提前刷新时间（秒）             |
| `APIKEY_SCENE_CODE` | str | - | 用来获取Apikey的场景Code     |
| `LLM_API_KEY` | str | - | 备用 API Key（动态获取失败时使用） |

## API 接口要求
获取软开接口服务写在在IOPS下面的ChatOPS应用中

## 工作原理

### 1. 初始化流程

```
启动应用
  ↓
注册 ApiKeyService
  ↓
注册 LLMService（注入 ApiKeyService）
  ↓
初始化 ApiKeyService（获取初始 API Key）
  ↓
初始化 LLMService
  ↓
应用就绪
```

### 2. API Key 刷新策略

```
时间线（假设 API Key 有效期 10 分钟）:
├─ 0分钟    获取 API Key
├─ 8分钟    自动刷新（提前 2 分钟）
└─ 10分钟   API Key 过期（但已刷新）

每次调用 LLM 前都会检查是否需要刷新
```

### 3. 失败处理

```
调用 getApikey 接口
  ↓
失败 → 等待 1 秒后重试（最多 3 次）
  ↓
全部失败
  ↓
使用旧的 API Key（如果有）或配置文件中的备用值
```

## 使用示例

### 禁用动态获取（使用固定 API Key）

在 `.env` 文件中设置：

```bash
APIKEY_SERVICE_ENABLED=false
LLM_API_KEY=your_fixed_api_key
```

系统将使用配置文件中的固定 API Key，行为与之前版本完全一致。

### 启用动态获取

在 `.env` 文件中设置：

```bash
APIKEY_SERVICE_ENABLED=true
APIKEY_SERVICE_URL=http://127.0.0.1:4532/getApikey
APIKEY_SCENE_CODE=P2025122
LLM_API_KEY=your_backup_api_key  # 备用值
```

系统将自动从指定 URL 获取 API Key，并定期刷新。

## 日志监控

系统会记录 API Key 获取和刷新的详细日志：

```
INFO - API Key 服务初始化完成（已获取初始 API key）
INFO - LLM 服务初始化完成 (model=gpt-4, 使用动态 API key)
INFO - API key 已刷新
WARNING - 获取 API key 失败 (尝试 1/3): Connection error
ERROR - 获取 API key 失败: 所有重试都失败
```

## 注意事项

1. **API Key 有效期**：确保 `APIKEY_EXPIRE_SECONDS` 配置与实际 API Key 有效期一致
2. **刷新时机**：建议 `APIKEY_REFRESH_BEFORE_SECONDS` 设置为有效期的 20-30%，留出足够的刷新时间
3. **备用 API Key**：即使启用动态获取，也建议配置 `LLM_API_KEY` 作为备用
4. **网络要求**：确保应用服务器能够访问 `APIKEY_SERVICE_URL`
5. **正在进行的调用**：API Key 刷新不会影响正在进行中的 LLM 调用

## 故障排查

### 问题：启动时提示"初始获取 API key 失败"

**可能原因**：
- getApikey 接口不可访问
- 接口返回格式不正确

**解决方案**：
1. 检查 `APIKEY_SERVICE_URL` 配置是否正确
2. 确认接口是否正常运行：`curl http://127.0.0.1:4532/getApikey`
3. 检查接口返回格式是否为 `{"result": "xxx"}`

### 问题：API Key 频繁失效

**可能原因**：
- `APIKEY_EXPIRE_SECONDS` 配置不正确
- 刷新时间设置过晚

**解决方案**：
1. 确认实际 API Key 有效期
2. 调整 `APIKEY_REFRESH_BEFORE_SECONDS`，增加提前刷新时间

### 问题：想临时禁用动态获取

**解决方案**：
在 `.env` 文件中设置：
```bash
APIKEY_SERVICE_ENABLED=false
```

重启应用即可使用固定 API Key。

## 架构说明

### 服务依赖关系

```
ApiKeyService (独立服务)
    ↓ 注入
LLMService
    ↓ 使用
各智能体 Agent
```

### 核心类

- `IApiKeyService`：API Key 服务接口
- `ApiKeyService`：API Key 服务实现
- `LLMService`：LLM 服务（使用 API Key 服务）

### 相关文件

- `app/core/services/apikey_service.py` - API Key 服务实现
- `app/core/services/llm_service.py` - LLM 服务（已修改）
- `app/core/services/interfaces.py` - 服务接口定义
- `app/core/config.py` - 配置定义
- `app/main.py` - 服务注册

