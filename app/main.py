from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1.agent import router as agent_router
from app.api.v1.agent_management import router as agent_management_router
from app.agents.loader import AgentLoader
from app.agents.registry import AgentRegistry
from app.core.config import settings
from app.core.logger import init_logging, get_logger
from app.core.container import ServiceContainer
from app.core.services import (
    ConfigService,
    LLMService,
    MySQLService,
    MongoDBService,
    ApolloService,
    ApiKeyService
)
from app.core.models.loader import CoreModelsLoader

from app.agents.rag_agent.agent import RAGAgent



# 初始化日志系统
init_logging()
logger = get_logger(__name__)

# 全局服务容器
_container: ServiceContainer = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    global _container
    
    # 启动
    logger.info("=" * 50)
    logger.info("多智能体平台启动中...")
    logger.info(f"LLM模型: {settings.llm_model}")
    logger.info(f"服务地址: http://{settings.host}:{settings.port}")
    logger.info("=" * 50)
    
    # 创建服务容器
    _container = ServiceContainer()
    logger.info("服务容器已创建")
    
    # 注册核心服务
    _container.register('config', lambda: ConfigService())
    
    # 注册 API Key 服务（在 LLM 服务之前）
    if settings.apikey_service_enabled:
        _container.register('apikey', lambda: ApiKeyService())
    
    # 注册 LLM 服务（注入 API Key 服务）
    _container.register('llm', lambda: LLMService(
        apikey_service=_container.get('apikey') if settings.apikey_service_enabled else None
    ))
    
    # 注册可选服务
    if settings.mysql_enabled:
        _container.register('mysql', lambda: MySQLService())
    
    if settings.mongodb_enabled:
        _container.register('mongodb', lambda: MongoDBService())
    
    if settings.apollo_enabled:
        _container.register('apollo', lambda: ApolloService())
    
    # 初始化所有服务
    try:
        await _container.initialize_all()
        logger.info("服务初始化完成:")
        for service_name, initialized in _container.list_services().items():
            status = "✓" if initialized else "✗"
            logger.info(f"  {status} {service_name}")
    except Exception as e:
        logger.error(f"服务初始化失败: {e}", exc_info=True)
    
    # 加载核心共享模型（优先于智能体加载）
    logger.info("正在加载核心共享模型...")
    CoreModelsLoader.load_core_models(container=_container)
    
    # 加载所有智能体（注入服务容器，触发模型自动发现和注册）
    logger.info("正在加载智能体...")
    AgentLoader.load_all_agents(container=_container)
    
    # 打印已加载的智能体
    logger.info("=== 智能体加载完成 ===")
    agents = AgentRegistry.list_agents()
    if agents:
        for name, desc in agents.items():
            logger.info(f"  - {name}: {desc}")
    else:
        logger.info("  未发现任何智能体")
    logger.info("=" * 50)
    
    # 初始化数据库表和集合
    logger.info("正在初始化数据库...")
    try:
        # MySQL: 创建表
        if settings.mysql_enabled:
            mysql = _container.get('mysql')
            if mysql:
                await mysql.create_tables()
                logger.info("  ✓ MySQL 表创建完成")
        
        # MongoDB: 创建索引
        if settings.mongodb_enabled:
            mongodb = _container.get('mongodb')
            if mongodb:
                # 为共享会话历史集合创建索引
                # from app.core.models.shared_conversation_history_mongo import SharedConversationHistoryMongo
                # await mongodb.ensure_indexes(
                #     SharedConversationHistoryMongo.COLLECTION_NAME,
                #     [
                #         "thread_id",
                #         "agent_name",
                #         [("thread_id", 1), ("agent_name", 1)],
                #         [("thread_id", 1), ("created_at", -1)],
                #         [("agent_name", 1), ("created_at", -1)],
                #     ]
                # )
                
                # 为 CMDB 状态集合创建索引
                # from app.agents.cmdb_smart_query.models.cmdb_state_mongo import CMDBStateMongo
                # await mongodb.ensure_indexes(
                #     CMDBStateMongo.COLLECTION_NAME,
                #     ["thread_id"]
                # )
                
                logger.info("  ✓ MongoDB 索引创建完成")
    except Exception as e:
        logger.error(f"数据库初始化失败: {e}", exc_info=True)
    
    logger.info("=" * 50)
    
    yield
    
    # 关闭
    logger.info("正在关闭多智能体平台...")
    
    # 关闭所有服务
    if _container is not None:
        await _container.shutdown_all()
    
    logger.info("多智能体平台已关闭")


def create_app() -> FastAPI:
    """创建FastAPI应用"""

    app = FastAPI(
        title="多智能体平台",
        description="整合多个智能体的协作开发平台",
        version="1.0.0",
        lifespan=lifespan
    )

    # 配置CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 注册路由
    app.include_router(agent_router)
    app.include_router(agent_management_router)

    return app


def get_container() -> ServiceContainer:
    """获取全局服务容器
    
    Returns:
        服务容器实例
    """
    return _container


app = create_app()