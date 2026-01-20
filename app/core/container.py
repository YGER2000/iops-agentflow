"""依赖注入容器

管理所有服务的生命周期、注册和获取。
"""

import asyncio
import logging
from typing import Dict, Any, Callable, Optional, Set
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class IService(ABC):
    """服务接口，所有服务都应实现此接口"""
    
    @abstractmethod
    async def initialize(self) -> None:
        """初始化服务（可选实现）"""
        pass
    
    @abstractmethod
    async def shutdown(self) -> None:
        """关闭服务（可选实现）"""
        pass


class ServiceContainer:
    """服务容器
    
    管理所有服务的生命周期，提供依赖注入功能。
    支持懒加载、单例模式和自动生命周期管理。
    """
    
    def __init__(self):
        """初始化服务容器"""
        self._services: Dict[str, Any] = {}  # 已实例化的服务
        self._factories: Dict[str, Callable] = {}  # 服务工厂函数
        self._initialized_services: Set[str] = set()  # 已初始化的服务名称
        self._lock = asyncio.Lock()  # 异步锁，防止并发初始化
        self._initialization_status = False  # 初始化状态标志
    
    def register(self, name: str, factory: Callable, singleton: bool = True) -> None:
        """注册服务工厂
        
        Args:
            name: 服务名称
            factory: 服务工厂函数（返回服务实例）
            singleton: 是否单例模式（默认 True）
        """
        if name in self._factories:
            logger.warning(f"服务 '{name}' 已存在，将被覆盖")
        
        self._factories[name] = {
            'factory': factory,
            'singleton': singleton
        }
        logger.debug(f"服务 '{name}' 已注册 (singleton={singleton})")
    
    def get(self, name: str, default: Any = None) -> Optional[Any]:
        """获取服务实例（懒加载）
        
        Args:
            name: 服务名称
            default: 服务不存在时的默认值
            
        Returns:
            服务实例，如果不存在则返回 default
        """
        # 如果已实例化，直接返回
        if name in self._services:
            return self._services[name]
        
        # 如果没有注册该服务
        if name not in self._factories:
            if default is not None:
                return default
            logger.warning(f"服务 '{name}' 未注册")
            return None
        
        # 创建服务实例
        factory_info = self._factories[name]
        factory = factory_info['factory']
        singleton = factory_info['singleton']
        
        try:
            service = factory()
            logger.debug(f"服务 '{name}' 已创建")
            
            # 如果是单例，缓存实例
            if singleton:
                self._services[name] = service
            
            return service
        except Exception as e:
            logger.error(f"创建服务 '{name}' 失败: {e}", exc_info=True)
            return default
    
    def has(self, name: str) -> bool:
        """检查服务是否已注册
        
        Args:
            name: 服务名称
            
        Returns:
            是否已注册
        """
        return name in self._factories
    
    async def initialize_all(self) -> None:
        """初始化所有已注册的服务
        
        遍历所有工厂，创建服务实例并调用其 initialize 方法。
        """
        async with self._lock:
            if self._initialization_status:
                logger.warning("容器已经初始化，跳过重复初始化")
                return
            
            self._initialization_status = True
            logger.info("开始初始化所有服务...")
            
            for name in self._factories.keys():
                try:
                    # 获取服务实例（触发懒加载）
                    service = self.get(name)
                    
                    if service is None:
                        logger.warning(f"服务 '{name}' 创建失败，跳过初始化")
                        continue
                    
                    # 调用 initialize 方法（如果存在）
                    if hasattr(service, 'initialize') and callable(service.initialize):
                        await service.initialize()
                        self._initialized_services.add(name)
                        logger.info(f"✓ 服务 '{name}' 初始化成功")
                    else:
                        logger.debug(f"服务 '{name}' 无需初始化")
                
                except Exception as e:
                    logger.error(f"初始化服务 '{name}' 失败: {e}", exc_info=True)
            
            logger.info(f"服务初始化完成，共 {len(self._initialized_services)} 个服务")
    
    async def shutdown_all(self) -> None:
        """关闭所有已初始化的服务
        
        按照初始化的反序关闭服务。
        """
        logger.info("开始关闭所有服务...")
        
        # 反序关闭（后初始化的先关闭）
        for name in reversed(list(self._initialized_services)):
            try:
                service = self._services.get(name)
                
                if service is None:
                    continue
                
                # 调用 shutdown 方法（如果存在）
                if hasattr(service, 'shutdown') and callable(service.shutdown):
                    await service.shutdown()
                    logger.info(f"✓ 服务 '{name}' 已关闭")
            
            except Exception as e:
                logger.error(f"关闭服务 '{name}' 失败: {e}", exc_info=True)
        
        # 清空缓存
        self._services.clear()
        self._initialized_services.clear()
        self._initialization_status = False
        
        logger.info("所有服务已关闭")
    
    def list_services(self) -> Dict[str, bool]:
        """列出所有已注册的服务及其状态
        
        Returns:
            服务名称到是否已初始化的映射
        """
        return {
            name: name in self._initialized_services
            for name in self._factories.keys()
        }

