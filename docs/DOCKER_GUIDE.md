# Docker 部署指南

本文档详细介绍如何使用 Docker 部署和运行 AgentFlow 多智能体平台。

## 📋 目录

- [快速开始](#快速开始)
- [生产环境部署](#生产环境部署)
- [开发环境部署](#开发环境部署)
- [环境变量配置](#环境变量配置)
- [常见问题](#常见问题)
- [最佳实践](#最佳实践)

## 🚀 快速开始

### 前置要求

- Docker 20.10+
- Docker Compose 2.0+
- 可访问的 Redis 服务（必需）
- （可选）MySQL、MongoDB 服务

### 1. 准备环境变量

```bash
# 复制环境变量模板
cp .env.example .env

# 编辑 .env 文件，配置必要的环境变量
vim .env
```

**必须配置的环境变量**：
```env
# LLM 配置
LLM_API_KEY=your_api_key_here
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4

# Redis 配置（必需）
REDIS_HOST=your_redis_host
REDIS_PORT=6379
REDIS_PASSWORD=your_redis_password  # 如果有
```

### 2. 快速启动（生产环境）

```bash
# 构建并启动生产环境容器
docker-compose --profile production up -d

# 查看日志
docker-compose --profile production logs -f app

# 停止服务
docker-compose --profile production down
```

### 3. 快速启动（开发环境）

```bash
# 构建并启动开发环境容器
docker-compose --profile development up -d

# 查看日志
docker-compose --profile development logs -f app-dev

# 停止服务
docker-compose --profile development down
```

### 4. 验证服务

```bash
# 健康检查
curl http://localhost:8000/api/v1/health

# 查看所有智能体
curl http://localhost:8000/api/v1/agents

# API 文档
# 打开浏览器访问 http://localhost:8000/docs
```

## 🏭 生产环境部署

### 使用 Docker Compose（推荐）

生产环境使用优化的 Dockerfile，镜像更小、更安全。

```bash
# 1. 构建镜像
docker-compose --profile production build

# 2. 启动服务
docker-compose --profile production up -d

# 3. 查看运行状态
docker-compose --profile production ps

# 4. 查看日志
docker-compose --profile production logs -f app

# 5. 重启服务
docker-compose --profile production restart app

# 6. 停止服务
docker-compose --profile production down
```

### 使用纯 Docker 命令

如果不使用 Docker Compose，也可以使用纯 Docker 命令：

```bash
# 1. 构建镜像
docker build -t agentflow:latest .

# 2. 运行容器
docker run -d \
  --name agentflow-app \
  -p 8000:8000 \
  --env-file .env \
  -e HOST=0.0.0.0 \
  -e PORT=8000 \
  -v $(pwd)/logs:/app/logs \
  --restart unless-stopped \
  agentflow:latest

# 3. 查看日志
docker logs -f agentflow-app

# 4. 停止容器
docker stop agentflow-app

# 5. 删除容器
docker rm agentflow-app
```

### 生产环境特性

- ✅ **多阶段构建**：减小镜像体积（约 200MB）
- ✅ **非 root 用户**：提高安全性
- ✅ **健康检查**：自动监控服务状态
- ✅ **日志持久化**：日志保存到宿主机
- ✅ **自动重启**：容器异常自动重启

## 🛠️ 开发环境部署

开发环境支持代码热重载，方便调试。

### 使用 Docker Compose（推荐）

```bash
# 1. 启动开发环境
docker-compose --profile development up -d

# 2. 查看日志（实时）
docker-compose --profile development logs -f app-dev

# 3. 进入容器调试
docker-compose --profile development exec app-dev bash

# 4. 在容器内运行测试
docker-compose --profile development exec app-dev pytest

# 5. 停止服务
docker-compose --profile development down
```

### 开发环境特性

- ✅ **代码热重载**：修改代码立即生效
- ✅ **源码挂载**：直接编辑宿主机代码
- ✅ **调试工具**：包含 ipython、ipdb、pytest
- ✅ **详细日志**：LOG_LEVEL=DEBUG
- ✅ **交互终端**：支持 stdin_open 和 tty

### 开发常用命令

```bash
# 重新构建镜像（修改依赖后）
docker-compose --profile development build --no-cache

# 查看容器资源占用
docker stats agentflow-app-dev

# 清理未使用的镜像
docker image prune -f

# 查看容器详细信息
docker inspect agentflow-app-dev
```

## ⚙️ 环境变量配置

### 核心配置

| 变量名 | 说明 | 默认值 | 必需 |
|--------|------|--------|------|
| `LLM_API_KEY` | LLM API 密钥 | - | ✅ |
| `LLM_BASE_URL` | LLM API 地址 | https://api.openai.com/v1 | ✅ |
| `LLM_MODEL` | 模型名称 | gpt-4 | ✅ |
| `REDIS_HOST` | Redis 主机地址 | localhost | ✅ |
| `REDIS_PORT` | Redis 端口 | 6379 | ✅ |
| `REDIS_PASSWORD` | Redis 密码 | - | ❌ |

### API Key 服务配置

| 变量名 | 说明 | 默认值 | 必需 |
|--------|------|--------|------|
| `APIKEY_SERVICE_ENABLED` | 启用动态 API Key | true | ❌ |
| `APIKEY_SERVICE_URL` | API Key 服务地址 | http://127.0.0.1:4532/getApikey | ❌ |
| `APIKEY_EXPIRE_SECONDS` | API Key 有效期（秒） | 600 | ❌ |

### 可选服务配置

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `MYSQL_ENABLED` | 启用 MySQL | false |
| `MYSQL_HOST` | MySQL 主机 | localhost |
| `MYSQL_PORT` | MySQL 端口 | 3306 |
| `MONGODB_ENABLED` | 启用 MongoDB | false |
| `MONGODB_HOST` | MongoDB 主机 | localhost |

### 服务器配置

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `HOST` | 监听地址 | 0.0.0.0 |
| `PORT` | 监听端口 | 8000 |
| `LOG_LEVEL` | 日志级别 | INFO |

### 在 Docker 中使用环境变量

#### 方法 1：使用 .env 文件（推荐）

```bash
# docker-compose 会自动读取 .env 文件
docker-compose --profile production up -d
```

#### 方法 2：命令行传递

```bash
docker run -d \
  -e LLM_API_KEY=your_key \
  -e REDIS_HOST=redis.example.com \
  -e REDIS_PORT=6379 \
  agentflow:latest
```

#### 方法 3：使用环境变量文件

```bash
# 创建 env.prod 文件
cat > env.prod <<EOF
LLM_API_KEY=your_key
REDIS_HOST=redis.example.com
EOF

# 使用 --env-file 参数
docker run -d --env-file env.prod agentflow:latest
```

## 📂 数据持久化

### 日志持久化

日志默认保存在容器内的 `/app/logs` 目录，需要挂载到宿主机：

```yaml
volumes:
  - ./logs:/app/logs
```

### 智能体配置持久化（只读）

如果需要在容器外管理智能体：

```yaml
volumes:
  - ./app/agents:/app/app/agents:ro
```

## 🔍 常见问题

### 1. 容器无法连接到 Redis

**问题**：日志显示 `Redis connection failed`

**解决方案**：
```bash
# 检查 Redis 是否可访问
docker run --rm redis:7-alpine redis-cli -h your_redis_host ping

# 检查网络连通性
docker exec agentflow-app ping your_redis_host

# 确认环境变量是否正确
docker exec agentflow-app env | grep REDIS
```

### 2. 权限问题

**问题**：容器无法写入日志文件

**解决方案**：
```bash
# 确保日志目录有写入权限
chmod 777 ./logs

# 或者更改所有者（容器内 uid 是 1000）
chown -R 1000:1000 ./logs
```

### 3. 无法拉取基础镜像（网络问题）⭐

**问题**：构建时报错 `failed to fetch anonymous token` 或 `connection reset by peer`

**原因**：无法访问 Docker Hub（在中国大陆常见）

**解决方案**：配置 Docker 镜像加速器

#### 方法 1：Docker Desktop GUI（推荐）

1. 打开 Docker Desktop
2. 点击右上角 ⚙️ **Settings/Preferences**
3. 选择 **Docker Engine**
4. 在 JSON 配置中添加镜像源：

```json
{
  "registry-mirrors": [
    "https://docker.m.daocloud.io",
    "https://docker.mirrors.ustc.edu.cn",
    "https://hub-mirror.c.163.com"
  ]
}
```

5. 点击 **Apply & Restart**
6. 等待 Docker 重启完成

#### 方法 2：使用脚本配置

```bash
# 运行配置脚本（查看详细说明）
./docker-mirror-setup.sh
```

#### 验证配置

```bash
# 检查镜像源是否生效
docker info | grep -A 5 'Registry Mirrors'

# 应该看到类似输出：
# Registry Mirrors:
#  https://docker.m.daocloud.io/
#  https://docker.mirrors.ustc.edu.cn/
```

#### 重新构建

```bash
# 清理之前失败的构建
docker builder prune -f

# 重新构建
docker compose --profile production build
```

### 4. 镜像构建失败（依赖问题）

**问题**：Python 依赖安装失败

**解决方案**：
```bash
# 清理缓存重新构建
docker compose build --no-cache

# 使用国内 PyPI 镜像源（可选）
# 在 Dockerfile 中添加：
# RUN pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple
```

### 5. 热重载不生效（开发环境）

**问题**：修改代码后没有自动重载

**解决方案**：
```bash
# 确认使用的是开发环境 profile
docker-compose --profile development up

# 检查源码是否正确挂载
docker-compose --profile development exec app-dev ls -la /app/app

# 查看 uvicorn 是否以 reload 模式运行
docker-compose --profile development exec app-dev ps aux | grep uvicorn
```

### 6. 容器频繁重启

**问题**：容器启动后立即退出

**解决方案**：
```bash
# 查看容器日志
docker logs agentflow-app

# 查看容器退出状态
docker inspect agentflow-app | grep -A 10 "State"

# 临时禁用健康检查
# 在 docker-compose.yml 中注释掉 healthcheck 部分
```

### 7. 健康检查失败

**问题**：容器显示 unhealthy

**解决方案**：
```bash
# 手动测试健康检查端点
docker exec agentflow-app curl http://localhost:8000/api/v1/health

# 查看健康检查日志
docker inspect agentflow-app | grep -A 20 "Health"

# 如果 requests 库未安装，修改 Dockerfile 确保安装
```

## 🎯 最佳实践

### 1. 生产环境

#### 使用环境变量管理配置

```bash
# 不要在镜像中硬编码敏感信息
# 使用环境变量或 secrets 管理
```

#### 配置资源限制

```yaml
services:
  app:
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 2G
        reservations:
          cpus: '1'
          memory: 1G
```

#### 使用专用网络

```yaml
networks:
  agentflow-network:
    driver: bridge
    ipam:
      config:
        - subnet: 172.20.0.0/16
```

#### 配置日志驱动

```yaml
services:
  app:
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

### 2. 安全性

#### 使用 secrets 管理敏感信息

```yaml
services:
  app:
    secrets:
      - llm_api_key
      - redis_password

secrets:
  llm_api_key:
    file: ./secrets/llm_api_key.txt
  redis_password:
    file: ./secrets/redis_password.txt
```

#### 定期更新基础镜像

```bash
# 定期重新构建以获取安全更新
docker-compose build --pull
```

#### 扫描镜像漏洞

```bash
# 使用 Docker Scan
docker scan agentflow:latest

# 或使用 Trivy
trivy image agentflow:latest
```

### 3. 性能优化

#### 使用 BuildKit

```bash
# 启用 BuildKit 加速构建
export DOCKER_BUILDKIT=1
docker-compose build
```

#### 优化镜像层

```dockerfile
# 将不常变化的层放在前面
COPY requirements.txt .
RUN pip install -r requirements.txt

# 将经常变化的代码放在后面
COPY app ./app
```

#### 使用 .dockerignore

确保 `.dockerignore` 排除了不必要的文件，减小 build context。

### 4. 监控和日志

#### 集成日志收集系统

```yaml
services:
  app:
    logging:
      driver: "fluentd"
      options:
        fluentd-address: "localhost:24224"
        tag: "agentflow"
```

#### 使用 Prometheus 监控

```bash
# 添加 metrics 端点
# 在应用中集成 prometheus_client
```

### 5. 高可用部署

#### 使用 Docker Swarm 或 Kubernetes

```bash
# Docker Swarm 示例
docker stack deploy -c docker-compose.yml agentflow

# 配置副本数
docker services scale agentflow_app=3
```

#### 配置健康检查和自动重启

```yaml
services:
  app:
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/api/v1/health"]
      interval: 30s
      timeout: 10s
      retries: 3
```

## 🚀 CI/CD 集成

### GitHub Actions 示例

```yaml
name: Build and Push Docker Image

on:
  push:
    branches: [ main ]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      
      - name: Build Docker image
        run: docker build -t agentflow:${{ github.sha }} .
      
      - name: Push to registry
        run: |
          echo ${{ secrets.DOCKER_PASSWORD }} | docker login -u ${{ secrets.DOCKER_USERNAME }} --password-stdin
          docker push agentflow:${{ github.sha }}
```

### GitLab CI 示例

```yaml
build:
  stage: build
  script:
    - docker build -t $CI_REGISTRY_IMAGE:$CI_COMMIT_SHA .
    - docker push $CI_REGISTRY_IMAGE:$CI_COMMIT_SHA
```

## 📞 获取帮助

如果遇到问题：

1. 查看[常见问题](#常见问题)部分
2. 检查容器日志：`docker logs agentflow-app`
3. 查看 [GitHub Issues](https://github.com/your-repo/issues)
4. 联系开发团队

## 📝 相关文档

- [README.md](../README.md) - 项目概述
- [智能体插件开发指南](./AGENT_PLUGIN_GUIDE.md)
- [多轮对话机制](./multi_turn_conversation.md)

