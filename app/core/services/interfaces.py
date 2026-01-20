"""服务接口定义

定义所有服务的抽象接口，遵循依赖倒置原则。
"""

from abc import ABC, abstractmethod
from typing import Any, AsyncGenerator, List, AsyncContextManager


class ILLMService(ABC):
    """LLM 服务接口"""
    
    @abstractmethod
    def get_model(self, model: str = None, temperature: float = None):
        """获取 LLM 模型实例
        
        Args:
            model: 模型名称，默认使用配置中的模型
            temperature: 温度参数，默认使用配置中的温度
            
        Returns:
            LLM 模型实例
        """
        pass
    
    @abstractmethod
    async def chat(self, messages: List, model: str = None, temperature: float = None) -> str:
        """聊天接口（非流式）
        
        Args:
            messages: 消息列表
            model: 模型名称
            temperature: 温度参数
            
        Returns:
            模型响应内容
        """
        pass
    
    @abstractmethod
    async def stream(self, messages: List, model: str = None, temperature: float = None) -> AsyncGenerator:
        """流式聊天接口
        
        Args:
            messages: 消息列表
            model: 模型名称
            temperature: 温度参数
            
        Yields:
            响应内容块
        """
        pass
    
    @abstractmethod
    def clean_response(self, content: str) -> str:
        """清理响应内容（移除思考标签等）
        
        Args:
            content: 原始内容
            
        Returns:
            清理后的内容
        """
        pass


class IDatabaseService(ABC):
    """数据库服务接口（MySQL with SQLAlchemy ORM）"""
    
    @abstractmethod
    def get_session(self) -> AsyncContextManager:
        """获取数据库 ORM 会话（上下文管理器）
        
        Returns:
            SQLAlchemy 异步会话上下文管理器
            
        Example:
            async with mysql.get_session() as session:
                user = User(name="张三")
                session.add(user)
                await session.commit()
        """
        pass
    
    @abstractmethod
    def register_models(self, metadata) -> None:
        """注册 SQLAlchemy 模型元数据
        
        Args:
            metadata: SQLAlchemy MetaData 对象
        """
        pass
    
    @abstractmethod
    async def create_tables(self) -> None:
        """创建所有已注册的表"""
        pass


class IMongoDBService(ABC):
    """MongoDB 服务接口（Motor 异步驱动）"""
    
    @abstractmethod
    def get_collection(self, collection_name: str):
        """获取集合对象
        
        Args:
            collection_name: 集合名称
            
        Returns:
            集合对象
        """
        pass
    
    @abstractmethod
    async def ensure_indexes(self, collection_name: str, indexes: List[Any]) -> None:
        """创建集合索引
        
        Args:
            collection_name: 集合名称
            indexes: 索引定义列表
        """
        pass
    
    @abstractmethod
    async def ping(self) -> bool:
        """测试连接
        
        Returns:
            连接是否成功
        """
        pass


class IConfigService(ABC):
    """配置服务接口"""
    
    @abstractmethod
    def get(self, key: str, default: Any = None) -> Any:
        """获取配置项
        
        Args:
            key: 配置键
            default: 默认值
            
        Returns:
            配置值
        """
        pass
    
    @abstractmethod
    def get_all(self) -> dict:
        """获取所有配置
        
        Returns:
            配置字典
        """
        pass
    
    @abstractmethod
    def set(self, key: str, value: Any) -> None:
        """设置配置项（运行时）
        
        Args:
            key: 配置键
            value: 配置值
        """
        pass


class IApiKeyService(ABC):
    """API Key 服务接口"""
    
    @abstractmethod
    def get_api_key_sync(self) -> str:
        """获取当前有效的 API key
        
        Returns:
            API key 字符串
        """
        pass
    
    @abstractmethod
    def refresh_api_key_sync(self) -> str:
        """手动刷新 API key
        
        Returns:
            新的 API key 字符串
        """
        pass
