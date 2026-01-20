import json
import logging
from typing import List, Dict, Any, Optional
from redis.asyncio import Redis
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from app.core.config import settings

logger = logging.getLogger(__name__)


class ChatHistoryManager:
    """会话历史管理器，使用异步 Redis 存储对话记录"""

    def __init__(self):
        """初始化异步 Redis 连接"""
        self.redis_client = Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            db=settings.redis_db,
            password=settings.redis_password if settings.redis_password else None,
            decode_responses=True,
            max_connections=50,  # 连接池大小
            socket_timeout=5.0,  # 套接字超时（秒）
            socket_connect_timeout=5.0,  # 连接超时（秒）
            socket_keepalive=True,  # 启用 TCP keepalive
            health_check_interval=30,  # 健康检查间隔（秒）
        )
        self._is_healthy = True  # Redis 连接健康状态

    def _get_key(self, thread_id: str) -> str:
        """生成Redis key（消息历史）"""
        return f"chat_history:{thread_id}"

    def _get_state_key(self, thread_id: str) -> str:
        """生成Redis key（状态存储）"""
        return f"chat_state:{thread_id}"

    async def add_message(self, thread_id: str, message: BaseMessage) -> None:
        """添加消息到会话历史
        
        Args:
            thread_id: 会话ID
            message: 消息对象
        """
        try:
            key = self._get_key(thread_id)
            
            # 将消息序列化
            message_dict = {
                "type": message.__class__.__name__,
                "content": message.content,
            }
            
            # 添加到Redis列表
            await self.redis_client.rpush(key, json.dumps(message_dict, ensure_ascii=False))
            
            # 设置过期时间(7天)
            await self.redis_client.expire(key, 7 * 24 * 60 * 60)
        except Exception as e:
            logger.error(f"添加消息到 Redis 失败: {e}")
            self._is_healthy = False
            raise

    async def add_messages(self, thread_id: str, messages: List[BaseMessage]) -> None:
        """批量添加消息到会话历史
        
        Args:
            thread_id: 会话ID
            messages: 消息列表
        """
        for message in messages:
            await self.add_message(thread_id, message)

    async def _get_from_redis(self, thread_id: str, limit: Optional[int] = None) -> List[BaseMessage]:
        """从 Redis 获取会话历史消息
        
        Args:
            thread_id: 会话ID
            limit: 限制返回的消息数量，None表示返回全部
            
        Returns:
            消息列表
        """
        try:
            key = self._get_key(thread_id)
            
            # 从Redis获取消息
            if limit:
                messages_data = await self.redis_client.lrange(key, -limit, -1)
            else:
                messages_data = await self.redis_client.lrange(key, 0, -1)
            
            # 反序列化消息
            messages = []
            for msg_str in messages_data:
                msg_dict = json.loads(msg_str)
                msg_type = msg_dict["type"]
                content = msg_dict["content"]
                
                if msg_type == "HumanMessage":
                    messages.append(HumanMessage(content=content))
                elif msg_type == "AIMessage":
                    messages.append(AIMessage(content=content))
                elif msg_type == "SystemMessage":
                    messages.append(SystemMessage(content=content))
            
            return messages
        except Exception as e:
            logger.error(f"从 Redis 获取消息失败: {e}")
            self._is_healthy = False
            return []
    
    async def _load_from_mongodb(self, thread_id: str) -> List[BaseMessage]:
        """从 MongoDB 加载会话历史
        
        注意：现在使用共享集合 SharedConversationHistoryMongo，需要 agent_name 参数才能准确查询。
        此方法已废弃，建议在各智能体内部直接使用 SharedConversationHistoryMongo 查询。
        
        Args:
            thread_id: 会话ID
            
        Returns:
            消息列表（现在返回空列表）
        """
        logger.debug(
            f"_load_from_mongodb 已废弃：无法在没有 agent_name 的情况下查询共享集合。"
            f"请在智能体内部使用 SharedConversationHistoryMongo 直接查询。"
        )
        return []
    
    async def _load_from_mysql(self, thread_id: str) -> List[BaseMessage]:
        """从 MySQL 加载会话历史
        
        Args:
            thread_id: 会话ID
            
        Returns:
            消息列表
        """
        try:
            # 延迟导入避免循环依赖
            from app.agents.cmdb_smart_query.models import CMDBConversationHistory
            from app.agents.common_qa.models import CommonQAConversationHistory
            from app.main import get_container
            from sqlalchemy import select
            
            # 获取 MySQL 服务
            container = get_container()
            mysql = container.get('mysql')
            
            if not mysql:
                logger.debug("MySQL 服务未注册，跳过")
                return []
            
            messages = []
            
            async with mysql.get_session() as session:
                # 尝试从两个表中查询（使用 UNION 查询）
                # 先尝试 CMDB 表
                result = await session.execute(
                    select(CMDBConversationHistory)
                    .where(CMDBConversationHistory.thread_id == thread_id)
                    .order_by(CMDBConversationHistory.created_at)
                )
                records = result.scalars().all()
                
                # 如果 CMDB 表没有，尝试 Common QA 表
                if not records:
                    result = await session.execute(
                        select(CommonQAConversationHistory)
                        .where(CommonQAConversationHistory.thread_id == thread_id)
                        .order_by(CommonQAConversationHistory.created_at)
                    )
                    records = result.scalars().all()
                
                # 将记录转换为 LangChain 消息对象
                for record in records:
                    if record.role == "user":
                        messages.append(HumanMessage(content=record.content))
                    elif record.role == "assistant":
                        messages.append(AIMessage(content=record.content))
                    elif record.role == "system":
                        messages.append(SystemMessage(content=record.content))
            
            if messages:
                logger.info(f"从 MySQL 加载了 {len(messages)} 条历史记录 (thread_id={thread_id})")
            
            return messages
        except ImportError:
            logger.debug("MySQL 模型类未找到，跳过")
            return []
        except Exception as e:
            logger.warning(f"从 MySQL 加载历史记录失败: {e}")
            return []
    
    async def _restore_to_redis(self, thread_id: str, messages: List[BaseMessage]) -> None:
        """将消息恢复到 Redis 缓存
        
        Args:
            thread_id: 会话ID
            messages: 消息列表
        """
        try:
            key = self._get_key(thread_id)
            
            # 批量添加消息到 Redis
            for message in messages:
                message_dict = {
                    "type": message.__class__.__name__,
                    "content": message.content,
                }
                await self.redis_client.rpush(key, json.dumps(message_dict, ensure_ascii=False))
            
            # 设置过期时间(7天)
            await self.redis_client.expire(key, 7 * 24 * 60 * 60)
            
            logger.info(f"已将 {len(messages)} 条消息恢复到 Redis (thread_id={thread_id})")
        except Exception as e:
            logger.warning(f"恢复消息到 Redis 失败: {e}")
    
    async def get_messages(self, thread_id: str, limit: Optional[int] = None) -> List[BaseMessage]:
        """获取会话历史消息（带数据库回退）
        
        优先从 Redis 读取，如果 Redis 中没有，则尝试从数据库恢复。
        
        Args:
            thread_id: 会话ID
            limit: 限制返回的消息数量，None表示返回全部
            
        Returns:
            消息列表
        """
        # 1. 先尝试从 Redis 读取
        messages = await self._get_from_redis(thread_id, limit=None)
        
        # 2. 如果 Redis 为空，尝试从数据库恢复
        if not messages:
            logger.info(f"Redis 中未找到历史记录 (thread_id={thread_id})，尝试从数据库恢复...")
            
            # 2.1 优先尝试 MongoDB（查询更快）
            # messages = await self._load_from_mongodb(thread_id)
            
            # 2.2 如果 MongoDB 没有，尝试 MySQL
            if not messages:
                messages = await self._load_from_mysql(thread_id)
            
            # 2.3 如果从数据库加载成功，回写到 Redis
            if messages:
                logger.info(f"从数据库恢复了 {len(messages)} 条历史记录，正在回写到 Redis...")
                await self._restore_to_redis(thread_id, messages)
            else:
                logger.debug(f"数据库中也未找到历史记录 (thread_id={thread_id})")
        
        # 3. 如果指定了 limit，截取最后 N 条
        if limit and len(messages) > limit:
            messages = messages[-limit:]
        
        return messages

    async def clear_history(self, thread_id: str) -> None:
        """清空会话历史
        
        Args:
            thread_id: 会话ID
        """
        try:
            key = self._get_key(thread_id)
            await self.redis_client.delete(key)
        except Exception as e:
            logger.error(f"清空 Redis 会话历史失败: {e}")
            self._is_healthy = False
            raise

    async def get_context_summary(self, thread_id: str) -> Dict[str, Any]:
        """获取会话上下文摘要
        
        Args:
            thread_id: 会话ID
            
        Returns:
            包含会话统计信息的字典
        """
        try:
            key = self._get_key(thread_id)
            message_count = await self.redis_client.llen(key)
            
            return {
                "thread_id": thread_id,
                "message_count": message_count,
                "has_history": message_count > 0
            }
        except Exception as e:
            logger.error(f"获取 Redis 会话摘要失败: {e}")
            self._is_healthy = False
            raise

    async def save_state(self, thread_id: str, state_data: Dict[str, Any]) -> None:
        """保存会话状态数据
        
        Args:
            thread_id: 会话ID
            state_data: 要保存的状态数据（字典）
        """
        try:
            key = self._get_state_key(thread_id)
            
            # 序列化状态数据
            state_json = json.dumps(state_data, ensure_ascii=False)
            
            # 保存到Redis
            await self.redis_client.set(key, state_json)
            
            # 设置过期时间(7天)
            await self.redis_client.expire(key, 7 * 24 * 60 * 60)
        except Exception as e:
            logger.error(f"保存会话状态到 Redis 失败: {e}")
            self._is_healthy = False
            raise

    async def get_state(self, thread_id: str) -> Optional[Dict[str, Any]]:
        """获取会话状态数据
        
        Args:
            thread_id: 会话ID
            
        Returns:
            状态数据字典，如果不存在返回None
        """
        try:
            key = self._get_state_key(thread_id)
            
            # 从Redis获取状态
            state_json = await self.redis_client.get(key)
            
            if state_json:
                return json.loads(state_json)
            return None
        except Exception as e:
            logger.error(f"从 Redis 获取会话状态失败: {e}")
            self._is_healthy = False
            raise

    async def clear_state(self, thread_id: str) -> None:
        """清空会话状态
        
        Args:
            thread_id: 会话ID
        """
        try:
            key = self._get_state_key(thread_id)
            await self.redis_client.delete(key)
        except Exception as e:
            logger.error(f"清空 Redis 会话状态失败: {e}")
            self._is_healthy = False
            raise
    
    async def ping(self) -> bool:
        """检查 Redis 连接健康状态
        
        Returns:
            连接是否正常
        """
        try:
            await self.redis_client.ping()
            self._is_healthy = True
            return True
        except Exception as e:
            logger.error(f"Redis ping 失败: {e}")
            self._is_healthy = False
            return False
    
    async def close(self) -> None:
        """关闭 Redis 连接"""
        try:
            await self.redis_client.close()
        except Exception as e:
            logger.error(f"关闭 Redis 连接失败: {e}")


class MemoryChatHistoryManager:
    """内存版本的会话历史管理器（用于测试或不使用Redis的场景）"""

    def __init__(self):
        self._storage: Dict[str, List[Dict[str, Any]]] = {}
        self._state_storage: Dict[str, Dict[str, Any]] = {}
        self._is_healthy = True

    def _get_storage(self, thread_id: str) -> List[Dict[str, Any]]:
        """获取或创建存储"""
        if thread_id not in self._storage:
            self._storage[thread_id] = []
        return self._storage[thread_id]

    async def add_message(self, thread_id: str, message: BaseMessage) -> None:
        """添加消息到会话历史"""
        storage = self._get_storage(thread_id)
        message_dict = {
            "type": message.__class__.__name__,
            "content": message.content,
        }
        storage.append(message_dict)

    async def add_messages(self, thread_id: str, messages: List[BaseMessage]) -> None:
        """批量添加消息"""
        for message in messages:
            await self.add_message(thread_id, message)

    async def _get_from_memory(self, thread_id: str, limit: Optional[int] = None) -> List[BaseMessage]:
        """从内存获取会话历史消息"""
        storage = self._get_storage(thread_id)
        
        if limit:
            messages_data = storage[-limit:]
        else:
            messages_data = storage
        
        messages = []
        for msg_dict in messages_data:
            msg_type = msg_dict["type"]
            content = msg_dict["content"]
            
            if msg_type == "HumanMessage":
                messages.append(HumanMessage(content=content))
            elif msg_type == "AIMessage":
                messages.append(AIMessage(content=content))
            elif msg_type == "SystemMessage":
                messages.append(SystemMessage(content=content))
        
        return messages
    
    async def _load_from_mongodb(self, thread_id: str) -> List[BaseMessage]:
        """从 MongoDB 加载会话历史（与 ChatHistoryManager 保持一致）
        
        注意：现在使用共享集合 SharedConversationHistoryMongo，需要 agent_name 参数才能准确查询。
        此方法已废弃，建议在各智能体内部直接使用 SharedConversationHistoryMongo 查询。
        """
        logger.debug(
            f"_load_from_mongodb 已废弃：无法在没有 agent_name 的情况下查询共享集合。"
            f"请在智能体内部使用 SharedConversationHistoryMongo 直接查询。"
        )
        return []
    
    async def _load_from_mysql(self, thread_id: str) -> List[BaseMessage]:
        """从 MySQL 加载会话历史（与 ChatHistoryManager 保持一致）"""
        try:
            from app.agents.cmdb_smart_query.models import CMDBConversationHistory
            from app.agents.common_qa.models import CommonQAConversationHistory
            from app.main import get_container
            from sqlalchemy import select
            
            container = get_container()
            mysql = container.get('mysql')
            
            if not mysql:
                logger.debug("MySQL 服务未注册，跳过")
                return []
            
            messages = []
            
            async with mysql.get_session() as session:
                result = await session.execute(
                    select(CMDBConversationHistory)
                    .where(CMDBConversationHistory.thread_id == thread_id)
                    .order_by(CMDBConversationHistory.created_at)
                )
                records = result.scalars().all()
                
                if not records:
                    result = await session.execute(
                        select(CommonQAConversationHistory)
                        .where(CommonQAConversationHistory.thread_id == thread_id)
                        .order_by(CommonQAConversationHistory.created_at)
                    )
                    records = result.scalars().all()
                
                for record in records:
                    if record.role == "user":
                        messages.append(HumanMessage(content=record.content))
                    elif record.role == "assistant":
                        messages.append(AIMessage(content=record.content))
                    elif record.role == "system":
                        messages.append(SystemMessage(content=record.content))
            
            if messages:
                logger.info(f"从 MySQL 加载了 {len(messages)} 条历史记录 (thread_id={thread_id})")
            
            return messages
        except ImportError:
            logger.debug("MySQL 模型类未找到，跳过")
            return []
        except Exception as e:
            logger.warning(f"从 MySQL 加载历史记录失败: {e}")
            return []
    
    async def _restore_to_memory(self, thread_id: str, messages: List[BaseMessage]) -> None:
        """将消息恢复到内存存储"""
        storage = self._get_storage(thread_id)
        for message in messages:
            message_dict = {
                "type": message.__class__.__name__,
                "content": message.content,
            }
            storage.append(message_dict)
        logger.info(f"已将 {len(messages)} 条消息恢复到内存 (thread_id={thread_id})")
    
    async def get_messages(self, thread_id: str, limit: Optional[int] = None) -> List[BaseMessage]:
        """获取会话历史消息（带数据库回退）"""
        # 1. 先尝试从内存读取
        messages = await self._get_from_memory(thread_id, limit=None)
        
        # 2. 如果内存为空，尝试从数据库恢复
        if not messages:
            logger.info(f"内存中未找到历史记录 (thread_id={thread_id})，尝试从数据库恢复...")
            
            # 2.1 优先尝试 MongoDB
            messages = await self._load_from_mongodb(thread_id)
            
            # 2.2 如果 MongoDB 没有，尝试 MySQL
            if not messages:
                messages = await self._load_from_mysql(thread_id)
            
            # 2.3 如果从数据库加载成功，回写到内存
            if messages:
                logger.info(f"从数据库恢复了 {len(messages)} 条历史记录，正在回写到内存...")
                await self._restore_to_memory(thread_id, messages)
            else:
                logger.debug(f"数据库中也未找到历史记录 (thread_id={thread_id})")
        
        # 3. 如果指定了 limit，截取最后 N 条
        if limit and len(messages) > limit:
            messages = messages[-limit:]
        
        return messages

    async def clear_history(self, thread_id: str) -> None:
        """清空会话历史"""
        if thread_id in self._storage:
            del self._storage[thread_id]

    async def get_context_summary(self, thread_id: str) -> Dict[str, Any]:
        """获取会话上下文摘要"""
        storage = self._get_storage(thread_id)
        return {
            "thread_id": thread_id,
            "message_count": len(storage),
            "has_history": len(storage) > 0
        }

    async def save_state(self, thread_id: str, state_data: Dict[str, Any]) -> None:
        """保存会话状态数据"""
        self._state_storage[thread_id] = state_data.copy()

    async def get_state(self, thread_id: str) -> Optional[Dict[str, Any]]:
        """获取会话状态数据"""
        return self._state_storage.get(thread_id)

    async def clear_state(self, thread_id: str) -> None:
        """清空会话状态"""
        if thread_id in self._state_storage:
            del self._state_storage[thread_id]
    
    async def ping(self) -> bool:
        """检查连接健康状态（内存版本始终返回 True）"""
        return True
    
    async def close(self) -> None:
        """关闭连接（内存版本无需操作）"""
        pass


# 全局单例
_chat_history_manager = None


async def get_chat_history_manager():
    """获取会话历史管理器单例（异步）
    
    Returns:
        ChatHistoryManager 或 MemoryChatHistoryManager 实例
    """
    global _chat_history_manager
    
    if _chat_history_manager is None:
        try:
            _chat_history_manager = ChatHistoryManager()
            # 测试Redis连接
            is_connected = await _chat_history_manager.ping()
            if not is_connected:
                # Redis 连接失败，降级到内存存储
                logger.warning("Redis 连接失败，降级使用内存存储")
                _chat_history_manager = MemoryChatHistoryManager()
                logger.info("会话历史管理器已初始化（使用内存存储）")
            else:
                logger.info("会话历史管理器已初始化（使用 Redis）")
        except Exception as e:
            logger.warning(f"Redis 初始化失败，降级使用内存存储: {e}")
            _chat_history_manager = MemoryChatHistoryManager()
            logger.info("会话历史管理器已初始化（使用内存存储）")
    
    return _chat_history_manager

