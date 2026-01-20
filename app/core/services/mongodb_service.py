"""MongoDB 服务 - Motor 异步驱动

提供基于 Motor 的 MongoDB 异步访问接口。
使用原生 motor 驱动，不依赖 ODM。
"""

import logging
from typing import Optional, List, Any

try:
    from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase, AsyncIOMotorCollection
    MONGODB_AVAILABLE = True
except ImportError:
    MONGODB_AVAILABLE = False
    AsyncIOMotorClient = None
    AsyncIOMotorDatabase = None
    AsyncIOMotorCollection = None

from app.core.config import settings
from app.core.container import IService
from .interfaces import IMongoDBService

logger = logging.getLogger(__name__)


class MongoDBService(IService, IMongoDBService):
    """MongoDB 服务实现 - 使用 Motor 异步驱动
    
    提供原生 Motor 接口，支持集合操作和索引管理。
    """
    
    def __init__(self):
        """初始化 MongoDB 服务"""
        self._client: Optional[AsyncIOMotorClient] = None
        self._database: Optional[AsyncIOMotorDatabase] = None
        logger.debug("MongoDB 服务已创建")
    
    async def initialize(self) -> None:
        """初始化服务，创建客户端连接"""
        if not MONGODB_AVAILABLE:
            raise ImportError(
                "motor 未安装。请运行: pip install motor pymongo"
            )
        
        if not settings.mongodb_enabled:
            logger.warning("MongoDB 未启用，跳过初始化")
            return
        
        # 构建连接字符串
        if settings.mongodb_user and settings.mongodb_password:
            connection_string = (
                f"mongodb://{settings.mongodb_user}:{settings.mongodb_password}"
                f"@{settings.mongodb_host}:{settings.mongodb_port}"
                f"/?authSource={settings.mongodb_auth_source}"
            )
        else:
            connection_string = f"mongodb://{settings.mongodb_host}:{settings.mongodb_port}"
        
        logger.info(
            "正在连接 MongoDB: %s:%d",
            settings.mongodb_host,
            settings.mongodb_port
        )
        
        self._client = AsyncIOMotorClient(
            connection_string,
            serverSelectionTimeoutMS=5000,
        )
        
        # 获取数据库（MongoDB 会自动创建数据库，不需要显式创建）
        self._database = self._client[settings.mongodb_database]
        
        # 测试连接
        await self._client.admin.command('ping')
        logger.info(f"MongoDB 客户端初始化成功，数据库: {settings.mongodb_database}")
        
        # 列出已有的数据库（用于调试）
        db_list = await self._client.list_database_names()
        logger.debug(f"可用的数据库: {db_list}")
    
    async def shutdown(self) -> None:
        """关闭服务，关闭客户端连接"""
        if self._client is not None:
            logger.info("正在关闭 MongoDB 客户端")
            self._client.close()
            self._client = None
            self._database = None
            logger.info("MongoDB 客户端已关闭")
    
    def get_collection(self, collection_name: str) -> Optional[AsyncIOMotorCollection]:
        """获取集合对象
        
        Args:
            collection_name: 集合名称
            
        Returns:
            集合对象，如果数据库未初始化则返回 None
        """
        if self._database is None:
            logger.warning(f"MongoDB 服务未初始化，无法获取集合: {collection_name}")
            return None
        return self._database[collection_name]
    
    async def ensure_indexes(self, collection_name: str, indexes: List[Any]) -> None:
        """创建集合索引
        
        Args:
            collection_name: 集合名称
            indexes: 索引定义列表
        """
        if self._database is None:
            logger.warning("MongoDB 服务未初始化，跳过索引创建")
            return
        
        collection = self._database[collection_name]
        
        try:
            for index in indexes:
                if isinstance(index, str):
                    # 单字段索引
                    await collection.create_index(index)
                    logger.debug(f"创建索引: {collection_name}.{index}")
                elif isinstance(index, list):
                    # 复合索引
                    await collection.create_index(index)
                    logger.debug(f"创建复合索引: {collection_name}.{index}")
            
            logger.info(f"集合 {collection_name} 的索引创建完成")
        except Exception as e:
            logger.error(f"创建索引失败 ({collection_name}): {e}")
    
    async def ping(self) -> bool:
        """测试连接
        
        Returns:
            连接是否成功
        """
        if self._client is None:
            return False
        
        try:
            await self._client.admin.command('ping')
            return True
        except Exception as e:
            logger.error("MongoDB 连接测试失败: %s", e)
            return False
