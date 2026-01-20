from pydantic_settings import BaseSettings
import logging

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """应用配置"""

    # LLM 配置
    llm_api_key: str = "b0d9bf2b017648029c51f951e88fee5c"
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4"
    llm_temperature: float = 0.7

    # API Key 动态获取配置
    apikey_service_enabled: bool = True
    apikey_service_url: str = "http://127.0.0.1:4532/getApikey"
    apikey_expire_seconds: int = 600  # API key 有效期（秒）
    apikey_refresh_before_seconds: int = 120  # 提前多久刷新（秒）
    apikey_scene_code: str = "P2025122"

    # Redis 配置（用于存储会话历史）
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: str = ""

    # MySQL 配置（可选）
    mysql_enabled: bool = False
    mysql_host: str = "localhost"
    mysql_port: int = 3306
    mysql_user: str = "root"
    mysql_password: str = ""
    mysql_database: str = "agentflow"
    mysql_pool_size: int = 10
    mysql_pool_recycle: int = 3600

    # MongoDB 配置（可选）
    mongodb_enabled: bool = False
    mongodb_host: str = "localhost"
    mongodb_port: int = 27017
    mongodb_user: str = ""
    mongodb_password: str = ""
    mongodb_database: str = "agentflow"
    mongodb_auth_source: str = "admin"

    # Apollo 配置中心（可选）
    apollo_enabled: bool = False
    apollo_app_id: str = ""
    apollo_cluster: str = "default"
    apollo_config_server_url: str = "http://localhost:8080"
    apollo_namespace: str = "application"
    apollo_env: str = "DEV"
    apollo_secret: str = ""

    # 服务器配置
    host: str = "0.0.0.0"
    port: int = 8000

    # 日志配置
    log_level: str = "INFO"  # DEBUG, INFO, WARNING, ERROR, CRITICAL
    log_dir: str = "logs"  # 日志文件目录
    log_file: str = "app.log"  # 日志文件名
    log_to_file: bool = True  # 是否输出到文件
    log_to_console: bool = True  # 是否输出到控制台

    # 启动配置
    uvicorn_reload: bool = False
    uvicorn_workers: int = 3

    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"  # 忽略 .env 文件中的额外配置项


settings = Settings()

if __name__ == "__main__":
    # 配置简单的控制台日志
    logging.basicConfig(level=logging.INFO)
    logger.info(settings.dict())