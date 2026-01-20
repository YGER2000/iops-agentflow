# 内网离线部署指南

本文档说明如何在无法访问互联网的内网环境中部署 AgentFlow 应用。

## 部署架构

采用"外网构建基础镜像 → 内网构建应用镜像"的两阶段部署方式：

```
外网环境                          内网环境
┌─────────────────┐             ┌─────────────────┐
│ Dockerfile.base │ ──build──>  │ 基础镜像 tar    │
│ + requirements  │             │ agentflow-base  │
└─────────────────┘             └────────┬────────┘
                                         │ load
                                         ↓
                                ┌─────────────────┐
                                │ Dockerfile.intra│ ──build──>
                                │ + 应用代码       │
                                └─────────────────┘
                                         ↓
                                ┌─────────────────┐
                                │  应用容器运行    │
                                └─────────────────┘
```

## 文件说明

### 外网环境使用
- **Dockerfile.base**: 构建包含所有 Python 依赖的基础镜像
- **requirements.txt**: Python 依赖列表

### 内网环境使用
- **Dockerfile.intra**: 基于基础镜像构建应用镜像
- **app/**: 应用源代码
- **run.py**: 应用入口

## 外网环境操作流程

### 1. 构建基础镜像

在有网络的环境中执行：

```bash
cd /path/to/agentFlow

# 构建基础镜像（会自动下载所有依赖）
docker build -t agentflow-base:py312 -f Dockerfile.base .
```

### 2. 导出基础镜像

```bash
# 导出为 tar 文件
docker save -o agentflow-base-py312.tar agentflow-base:py312

# 查看文件大小
ls -lh agentflow-base-py312.tar
```

### 3. 传输到内网

使用适合的方式将以下文件传输到内网环境：

- `agentflow-base-py312.tar` - 基础镜像文件
- `Dockerfile.intra` - 内网构建文件
- `app/` - 应用代码目录
- `run.py` - 应用入口文件
- `.env` - 环境变量配置文件（需根据实际情况配置）

传输方式示例：
```bash
# 方式 1: SCP（如果内网可通过跳板机访问）
scp agentflow-base-py312.tar user@intranet-server:/path/to/destination/

# 方式 2: 物理介质（USB、移动硬盘等）
# 复制到移动存储设备，再在内网环境中读取
```

## 内网环境操作流程

### 1. 加载基础镜像

```bash
# 进入存放 tar 文件的目录
cd /path/to/destination/

# 加载基础镜像
docker load -i agentflow-base-py312.tar

# 验证镜像已加载
docker images | grep agentflow-base
# 应该看到：
# agentflow-base   py312   <IMAGE_ID>   <SIZE>
```

### 2. 构建应用镜像

```bash
# 进入项目目录
cd /path/to/agentFlow/

# 构建应用镜像
docker build -t agentflow:intra -f Dockerfile.intra .

# 如果需要指定不同的基础镜像
docker build --build-arg BASE_IMAGE=agentflow-base:py312 -t agentflow:intra -f Dockerfile.intra .
```

### 3. 配置环境变量

创建或修改 `.env` 文件：

```bash
# 复制示例配置
cp env.example .env

# 编辑配置文件
vi .env
```

必需的配置项：
```env
# 应用配置
HOST=0.0.0.0
PORT=8000

# LLM 配置
LLM_API_KEY=your-api-key
LLM_BASE_URL=your-api-base-url
LLM_MODEL=gpt-4

# Redis 配置（用于会话存储）
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=

# 其他配置...
```

**关于 Apollo 配置中心：**

应用支持可选的 Apollo 配置中心用于动态配置管理。如果内网环境有 Apollo 服务：

```env
# Apollo 配置（可选）
APOLLO_ENABLED=true
APOLLO_APP_ID=agentflow
APOLLO_CLUSTER=default
APOLLO_CONFIG_SERVER_URL=http://内网apollo服务器:8080
APOLLO_NAMESPACE=application
APOLLO_SECRET=your_secret
```

如果内网没有 Apollo 或不使用动态配置，设置为 `false` 即可：

```env
# 禁用 Apollo
APOLLO_ENABLED=false
```

> **注意**：
> - `.env` 文件是必需的，包含应用启动的基础配置
> - Apollo 是可选的，用于运行时动态配置管理
> - 两者可以共存，Apollo 会在运行时补充或覆盖部分配置

### 4. 运行应用容器

**基础运行方式：**

```bash
docker run -d \
  --name agentflow-app \
  -p 8000:8000 \
  --env-file .env \
  -e HOST=0.0.0.0 \
  -e PORT=8000 \
  -v ./logs:/app/logs \
  -v ./app/agents:/app/app/agents:ro \
  --restart unless-stopped \
  agentflow:intra
```

**推荐运行方式（带健康检查）：**

```bash
docker run -d \
  --name agentflow-app \
  -p 8000:8000 \
  --env-file .env \
  -e HOST=0.0.0.0 \
  -e PORT=8000 \
  -v ./logs:/app/logs \
  -v ./app/agents:/app/app/agents:ro \
  --restart unless-stopped \
  --health-cmd="python -c \"import requests; requests.get('http://localhost:8000/api/v1/health')\"" \
  --health-interval=30s \
  --health-timeout=10s \
  --health-retries=3 \
  --health-start-period=10s \
  agentflow:intra
```

参数说明：
- `-p 8000:8000`: 端口映射（主机端口:容器端口）
- `--env-file .env`: 从文件加载环境变量
- `-v ./logs:/app/logs`: 挂载日志目录（持久化日志）
- `-v ./app/agents:/app/app/agents:ro`: 挂载智能体配置（只读）
- `--restart unless-stopped`: 容器自动重启策略

### 5. 验证运行状态

```bash
# 查看容器状态
docker ps -a | grep agentflow

# 查看实时日志
docker logs -f agentflow-app

# 查看最近 100 行日志
docker logs --tail 100 agentflow-app

# 检查健康状态
docker inspect --format='{{.State.Health.Status}}' agentflow-app

# 测试 API 端点
curl http://localhost:8000/api/v1/health
```

## 常用管理命令

### 容器管理

```bash
# 停止容器
docker stop agentflow-app

# 启动已停止的容器
docker start agentflow-app

# 重启容器
docker restart agentflow-app

# 删除容器
docker rm agentflow-app

# 强制删除运行中的容器
docker rm -f agentflow-app

# 查看容器资源占用
docker stats agentflow-app
```

### 日志管理

```bash
# 查看实时日志
docker logs -f agentflow-app

# 查看最近 N 行日志
docker logs --tail 100 agentflow-app

# 查看指定时间范围的日志
docker logs --since "2025-01-01T00:00:00" agentflow-app

# 导出日志到文件
docker logs agentflow-app > app.log 2>&1
```

### 进入容器调试

```bash
# 进入容器 shell
docker exec -it agentflow-app /bin/bash

# 以 root 用户进入（用于排查权限问题）
docker exec -it -u root agentflow-app /bin/bash

# 在容器中执行单个命令
docker exec agentflow-app python -c "print('Hello')"
```

## 应用更新流程

### 仅更新应用代码（依赖不变）

如果只是修改了业务代码，不需要重新构建基础镜像：

```bash
# 1. 停止并删除旧容器
docker stop agentflow-app
docker rm agentflow-app

# 2. 重新构建应用镜像
docker build -t agentflow:intra -f Dockerfile.intra .

# 3. 运行新容器
docker run -d \
  --name agentflow-app \
  -p 8000:8000 \
  --env-file .env \
  -v ./logs:/app/logs \
  -v ./app/agents:/app/app/agents:ro \
  --restart unless-stopped \
  agentflow:intra
```

### 更新依赖（需要重新构建基础镜像）

如果 `requirements.txt` 有变化：

**外网环境：**
```bash
# 1. 重新构建基础镜像
docker build -t agentflow-base:py312 -f Dockerfile.base .

# 2. 导出新的基础镜像
docker save -o agentflow-base-py312-new.tar agentflow-base:py312

# 3. 传输到内网
```

**内网环境：**
```bash
# 1. 加载新的基础镜像
docker load -i agentflow-base-py312-new.tar

# 2. 按照前面的流程重新构建和运行
```

## 镜像清理

```bash
# 查看所有镜像
docker images

# 删除旧的应用镜像
docker rmi agentflow:intra

# 删除悬空镜像（节省空间）
docker image prune -f

# 查看磁盘占用
docker system df

# 清理所有未使用的资源（慎用）
docker system prune -a
```

## Apollo 配置中心说明

### 配置架构

应用采用分层配置策略：

```
层级 1: .env 文件（基础配置，必需）
  ↓
层级 2: Apollo 配置中心（动态配置，可选）
```

### 工作方式

1. **应用启动时**
   - 从 `.env` 加载所有基础配置（包括 Apollo 连接信息）
   - 如果 `APOLLO_ENABLED=true`，连接到 Apollo 服务器

2. **运行时**
   - 智能体可从 Apollo 获取动态配置
   - 支持配置热更新（无需重启应用）

3. **降级策略**
   - 如果 Apollo 连接失败，自动使用 `.env` 中的默认值
   - 不影响应用正常运行

### 内网使用 Apollo 的方案

**方案 A：内网部署 Apollo（推荐）**

如果内网有独立的 Apollo 服务器：

```bash
# .env 配置
APOLLO_ENABLED=true
APOLLO_CONFIG_SERVER_URL=http://内网apollo地址:8080
APOLLO_APP_ID=agentflow

# 运行容器
docker run -d \
  --name agentflow-app \
  -p 8000:8000 \
  --env-file .env \
  agentflow:intra
```

**方案 B：禁用 Apollo（简化部署）**

如果内网没有 Apollo 或不需要动态配置：

```bash
# .env 配置
APOLLO_ENABLED=false

# 或在运行时覆盖
docker run -d \
  --name agentflow-app \
  -p 8000:8000 \
  --env-file .env \
  -e APOLLO_ENABLED=false \
  agentflow:intra
```

**方案 C：使用 Apollo 容器化部署**

可以在内网单独部署 Apollo 容器：

```bash
# 1. 部署 Apollo Config Service
docker run -d \
  --name apollo-config \
  -p 8080:8080 \
  apolloconfig/apollo-configservice:latest

# 2. 应用连接到本地 Apollo
docker run -d \
  --name agentflow-app \
  -p 8000:8000 \
  --env-file .env \
  -e APOLLO_CONFIG_SERVER_URL=http://apollo-config:8080 \
  --link apollo-config \
  agentflow:intra
```

### Apollo 配置依赖说明

如果启用 Apollo（`APOLLO_ENABLED=true`），需要在基础镜像中包含 `apollo-client` 依赖。

检查 `requirements.txt` 是否包含：

```bash
# 在外网构建基础镜像前，确认 requirements.txt 包含
grep -i apollo-client requirements.txt
```

如果没有，需要添加：

```txt
# Apollo 配置中心
apollo-client
```

然后重新构建基础镜像。

## 故障排查

### Apollo 连接问题

```bash
# 查看 Apollo 连接日志
docker logs agentflow-app | grep -i apollo

# 常见错误及解决方案
# 1. "Apollo 未启用" - 检查 APOLLO_ENABLED 配置
# 2. "apollo-client 未安装" - 需要重新构建基础镜像并包含 apollo-client
# 3. "连接超时" - 检查 APOLLO_CONFIG_SERVER_URL 和网络连通性
# 4. "认证失败" - 检查 APOLLO_APP_ID 和 APOLLO_SECRET

# 手动测试 Apollo 连通性
docker exec agentflow-app python -c "
import httpx
resp = httpx.get('http://apollo-server:8080/services/config')
print(resp.status_code)
"
```

### 容器无法启动

```bash
# 查看容器日志
docker logs agentflow-app

# 检查容器退出状态码
docker inspect --format='{{.State.ExitCode}}' agentflow-app

# 以交互模式运行（便于调试）
docker run -it --rm --env-file .env agentflow:intra /bin/bash
```

### 健康检查失败

```bash
# 查看健康检查详情
docker inspect --format='{{json .State.Health}}' agentflow-app | python -m json.tool

# 手动执行健康检查命令
docker exec agentflow-app python -c "import requests; requests.get('http://localhost:8000/api/v1/health')"
```

### 网络问题

```bash
# 检查端口映射
docker port agentflow-app

# 检查容器网络
docker network inspect bridge

# 从容器内部测试
docker exec agentflow-app curl http://localhost:8000/api/v1/health
```

### 权限问题

```bash
# 检查文件权限
docker exec agentflow-app ls -la /app

# 检查日志目录权限
docker exec agentflow-app ls -la /app/logs

# 以 root 身份修复权限
docker exec -u root agentflow-app chown -R appuser:appuser /app/logs
```

## 性能优化建议

### 资源限制

```bash
# 限制内存和 CPU
docker run -d \
  --name agentflow-app \
  --memory="2g" \
  --cpus="2.0" \
  -p 8000:8000 \
  --env-file .env \
  agentflow:intra
```

### 日志限制

```bash
# 限制日志大小，防止磁盘占满
docker run -d \
  --name agentflow-app \
  --log-opt max-size=100m \
  --log-opt max-file=3 \
  -p 8000:8000 \
  --env-file .env \
  agentflow:intra
```

## 安全建议

1. **不要在镜像中硬编码敏感信息**
   - 使用 `.env` 文件或环境变量传递敏感配置
   - 确保 `.env` 文件权限设置为 `600`

2. **使用非 root 用户运行**
   - 镜像已配置使用 `appuser` 用户运行
   - 避免以 root 身份运行容器

3. **限制容器权限**
   ```bash
   docker run -d \
     --name agentflow-app \
     --read-only \
     --tmpfs /tmp \
     --security-opt=no-new-privileges \
     agentflow:intra
   ```

4. **定期更新依赖**
   - 定期检查并更新 `requirements.txt` 中的包版本
   - 关注安全漏洞公告

## 附录

### 镜像大小参考

- **基础镜像** (`agentflow-base:py312`): 约 500-800 MB（取决于依赖数量）
- **应用镜像** (`agentflow:intra`): 约 50-100 MB（仅代码）
- **总大小**: 基础镜像 + 应用镜像

### 端口说明

- `8000`: 应用 HTTP 服务端口（默认）
- 可通过环境变量 `PORT` 自定义

### 目录结构

```
/app/
├── app/              # 应用代码
│   ├── agents/      # 智能体配置
│   ├── api/         # API 路由
│   ├── core/        # 核心模块
│   └── main.py      # FastAPI 应用入口
├── logs/            # 日志目录（挂载卷）
└── run.py           # 启动脚本
```

## 支持与反馈

如遇到问题，请检查：
1. 容器日志：`docker logs agentflow-app`
2. 应用日志：`./logs/app.log`
3. 环境变量配置是否正确

---

**最后更新**: 2025-11-03

