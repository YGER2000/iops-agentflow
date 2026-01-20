"""MySQL 服务 - SQLAlchemy ORM

提供基于 SQLAlchemy 2.0 的异步 ORM 访问接口。
"""

import logging
from typing import Optional, List
from contextlib import asynccontextmanager
from urllib.parse import quote_plus

try:
    from sqlalchemy.ext.asyncio import (
        create_async_engine,
        AsyncEngine,
        AsyncSession,
        async_sessionmaker
    )
    from sqlalchemy import MetaData
    SQLALCHEMY_AVAILABLE = True
except ImportError:
    SQLALCHEMY_AVAILABLE = False
    create_async_engine = None
    AsyncEngine = None
    AsyncSession = None
    async_sessionmaker = None
    MetaData = None

from app.core.config import settings
from app.core.container import IService
from .interfaces import IDatabaseService

logger = logging.getLogger(__name__)


class MySQLService(IService, IDatabaseService):
    """MySQL 服务实现 - 使用 SQLAlchemy ORM
    
    提供 SQLAlchemy 异步 ORM 接口。
    """
    
    def __init__(self):
        """初始化 MySQL 服务"""
        self._engine: Optional[AsyncEngine] = None
        self._session_factory: Optional[async_sessionmaker] = None
        self._metadata_list: List[MetaData] = []
        logger.debug("MySQL 服务已创建")
    
    async def _ensure_database_exists(self) -> None:
        """确保目标数据库存在，不存在则创建"""
        try:
            import aiomysql
        except ImportError:
            raise ImportError("aiomysql 未安装。请运行: pip install aiomysql")
        
        # 连接到 MySQL 服务器（不指定数据库）
        conn = await aiomysql.connect(
            host=settings.mysql_host,
            port=settings.mysql_port,
            user=settings.mysql_user,
            password=settings.mysql_password,
            charset='utf8mb4'
        )
        
        try:
            async with conn.cursor() as cursor:
                # 检查数据库是否存在
                await cursor.execute(
                    "SELECT SCHEMA_NAME FROM INFORMATION_SCHEMA.SCHEMATA WHERE SCHEMA_NAME = %s",
                    (settings.mysql_database,)
                )
                result = await cursor.fetchone()
                
                if result is None:
                    # 数据库不存在，创建它
                    logger.info(f"数据库 '{settings.mysql_database}' 不存在，正在创建...")
                    await cursor.execute(
                        f"CREATE DATABASE `{settings.mysql_database}` "
                        f"CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                    )
                    logger.info(f"✅ 数据库 '{settings.mysql_database}' 创建成功")
                else:
                    logger.info(f"数据库 '{settings.mysql_database}' 已存在")
        finally:
            conn.close()
    
    async def initialize(self) -> None:
        """初始化服务，创建异步引擎"""
        if not SQLALCHEMY_AVAILABLE:
            raise ImportError(
                "SQLAlchemy 未安装。请运行: pip install sqlalchemy[asyncio] greenlet"
            )
        
        if not settings.mysql_enabled:
            logger.warning("MySQL 未启用，跳过初始化")
            return
        
        # 先检查并创建数据库（如果不存在）
        await self._ensure_database_exists()

        # 构建连接字符串（使用 aiomysql 驱动）
        user = quote_plus(settings.mysql_user)
        password = quote_plus(settings.mysql_password)
        host = settings.mysql_host  # 确保此处没有额外字符
        connection_string = (
            f"mysql+aiomysql://{user}:{password}"
            f"@{host}:{settings.mysql_port}/{settings.mysql_database}"
            f"?charset=utf8mb4"
        )
        
        logger.info(
            "正在初始化 MySQL ORM 引擎: %s:%d/%s",
            settings.mysql_host,
            settings.mysql_port,
            settings.mysql_database
        )
        
        # 创建异步引擎
        self._engine = create_async_engine(
            connection_string,
            pool_size=settings.mysql_pool_size,
            pool_recycle=settings.mysql_pool_recycle,
            echo=False,  # 设置为 True 可以看到 SQL 日志
            future=True,
        )
        
        # 创建会话工厂
        self._session_factory = async_sessionmaker(
            self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        
        logger.info("MySQL ORM 引擎初始化成功")
    
    async def shutdown(self) -> None:
        """关闭服务，释放引擎资源"""
        if self._engine is not None:
            logger.info("正在关闭 MySQL ORM 引擎")
            await self._engine.dispose()
            self._engine = None
            self._session_factory = None
            logger.info("MySQL ORM 引擎已关闭")
    
    @asynccontextmanager
    async def get_session(self):
        """获取数据库 ORM 会话（上下文管理器）
        
        使用示例:
            async with mysql.get_session() as session:
                user = User(name="张三")
                session.add(user)
                await session.commit()
                
                # 查询
                result = await session.execute(select(User).where(User.name == "张三"))
                users = result.scalars().all()
        
        Yields:
            AsyncSession: SQLAlchemy 异步会话对象
        """
        if self._session_factory is None:
            raise RuntimeError("MySQL 服务未初始化，请先调用 initialize()")
        
        async with self._session_factory() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise
    
    def register_models(self, metadata: MetaData) -> None:
        """注册 SQLAlchemy 模型元数据
        
        Args:
            metadata: SQLAlchemy MetaData 对象（通常是 Base.metadata）
        """
        if metadata not in self._metadata_list:
            self._metadata_list.append(metadata)
            logger.info(f"已注册 SQLAlchemy 元数据，共 {len(metadata.tables)} 个表")
    
    async def create_tables(self) -> None:
        """创建所有已注册的表
        
        这将根据已注册的模型元数据自动创建表结构。
        如果表已存在，则不会重复创建。
        """
        if self._engine is None:
            raise RuntimeError("MySQL 服务未初始化，请先调用 initialize()")
        
        if not self._metadata_list:
            logger.info("没有需要创建的表")
            return
        
        logger.info("开始创建数据库表...")
        
        async with self._engine.begin() as conn:
            for metadata in self._metadata_list:
                # create_all 只会创建不存在的表
                await conn.run_sync(metadata.create_all)
                logger.info(f"已创建/检查 {len(metadata.tables)} 个表")
        
        logger.info("数据库表创建完成")
