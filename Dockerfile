# 多阶段构建 - 生产环境 Dockerfile
# Stage 1: 构建阶段 - 安装依赖
FROM python:3.12-slim as builder

# 设置工作目录
WORKDIR /app

# 安装系统依赖
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt .

# 安装 Python 依赖到临时目录
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Stage 2: 运行阶段 - 最小化镜像
FROM python:3.12-slim

# 设置环境变量
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/install/bin:$PATH" \
    PYTHONPATH="/install/lib/python3.12/site-packages:$PYTHONPATH" \
    DEBIAN_FRONTEND=noninteractive \
    TZ=Asia/Shanghai

# 设置工作目录
WORKDIR /app

# 创建非 root 用户
RUN groupadd -r appuser && useradd -r -g appuser appuser

# 安装时区数据并设置时区为 Asia/Shanghai
RUN apt-get update && \
    apt-get install -y --no-install-recommends tzdata && \
    ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone && \
    rm -rf /var/lib/apt/lists/*

# 从构建阶段复制依赖
COPY --from=builder /install /install

# 复制应用代码
COPY --chown=appuser:appuser app ./app
COPY --chown=appuser:appuser run.py .

# 创建日志目录和 Apollo 缓存目录
RUN mkdir -p logs .apollo_cache && chown -R appuser:appuser logs .apollo_cache

# 切换到非 root 用户
USER appuser

# 暴露端口
EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/api/v1/health')" || exit 1

# 启动命令 - 生产模式（无热重载）
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]


# # 在项目根目录构建镜像
# docker build -t agentflow:latest -f /Users/jamison/coding/agentFlow/Dockerfile /Users/jamison/coding/agentFlow

# # 运行容器
# docker run -d \
#   --name agentflow-app \
#   -p 8000:8000 \
#   --env-file /Users/jamison/coding/agentFlow/.env \
#   -e HOST=0.0.0.0 \
#   -e PORT=8000 \
#   -v /Users/jamison/coding/agentFlow/logs:/app/logs \
#   -v /Users/jamison/coding/agentFlow/app/agents:/app/app/agents:ro \
#   --restart unless-stopped \
#   agentflow:latest


# # 可选：健康检查
# docker run -d \
#   --name agentflow-app \
#   -p 8000:8000 \
#   --env-file /Users/jamison/coding/agentFlow/.env \
#   -e HOST=0.0.0.0 -e PORT=8000 \
#   -v /Users/jamison/coding/agentFlow/logs:/app/logs \
#   -v /Users/jamison/coding/agentFlow/app/agents:/app/app/agents:ro \
#   --restart unless-stopped \
#   --health-cmd="python -c \"import requests; requests.get('http://localhost:8000/api/v1/health')\"" \
#   --health-interval=30s --health-timeout=10s --health-retries=3 --health-start-period=10s \
#   agentflow:latest