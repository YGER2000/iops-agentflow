"""Apollo 配置服务

提供统一的 Apollo 配置中心访问接口。
"""

import logging
from pathlib import Path
from typing import Optional, Dict, Any, Callable

try:
    from pyapollo.apollo_client import ApolloClient
    APOLLO_AVAILABLE = True
except ImportError:
    APOLLO_AVAILABLE = False
    ApolloClient = None

from app.core.config import settings
from app.core.container import IService
from .interfaces import IConfigService

logger = logging.getLogger(__name__)


class ApolloService(IService, IConfigService):
    """Apollo 配置服务实现
    
    提供从 Apollo 配置中心读取配置的功能。
    注意：本服务实现了 IConfigService 接口，可以作为配置服务使用。
    """
    
    def __init__(self):
        """初始化 Apollo 服务"""
        self._client: Optional[ApolloClient] = None
        self._config_cache: Dict[str, Any] = {}
        self._change_callbacks: Dict[str, list] = {}
        logger.debug("Apollo 服务已创建")
    
    async def initialize(self) -> None:
        """初始化服务，创建 Apollo 客户端"""
        if not APOLLO_AVAILABLE:
            raise ImportError(
                "apollo-client 未安装。请运行: pip install apollo-client"
            )
        
        if not settings.apollo_enabled:
            logger.warning("Apollo 未启用，跳过初始化")
            return
        
        logger.info(
            "正在连接 Apollo 配置中心: %s (AppId: %s, Namespace: %s)",
            settings.apollo_config_server_url,
            settings.apollo_app_id,
            settings.apollo_namespace
        )
        
        # 设置 Apollo 缓存目录为应用目录下的 .apollo_cache，确保用户有权限写入
        cache_dir = Path("/app/.apollo_cache")
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file_path = str(cache_dir)
        logger.debug(f"Apollo 缓存目录: {cache_file_path}")
        
        # 构建 ApolloClient 参数
        client_params = {
            'app_id': settings.apollo_app_id,
            'cluster': settings.apollo_cluster,
            'config_server_url': settings.apollo_config_server_url,
            'env': settings.apollo_env,
            'cache_file_path': cache_file_path  # 指定用户有权限的缓存目录
        }
        
        # 如果配置了 authorization，则添加
        if settings.apollo_secret:
            client_params['authorization'] = settings.apollo_secret
        
        self._client = ApolloClient(**client_params)
        
        # 手动加载默认 namespace（确保配置可用）
        try:
            if settings.apollo_namespace not in self._client._cache:
                logger.info(f"手动加载 namespace: {settings.apollo_namespace}")
                self._client._get_config_by_namespace(settings.apollo_namespace)
        except Exception as e:
            logger.warning(f"手动加载 namespace 失败: {e}")
        
        # 检查缓存状态
        if hasattr(self._client, '_cache'):
            loaded_namespaces = list(self._client._cache.keys())
            if loaded_namespaces:
                logger.info(f"已加载的 namespaces: {loaded_namespaces}")
            else:
                logger.warning("未加载任何 namespace，配置可能不可用")
        
        logger.info("Apollo 客户端初始化成功")
    
    async def shutdown(self) -> None:
        """关闭服务"""
        self._client = None
        self._config_cache.clear()
        self._change_callbacks.clear()
        logger.info("Apollo 服务已关闭")
    
    def get(self, key: str, default: Any = None) -> Any:
        """从 Apollo 获取配置项
        
        Args:
            key: 配置键
            default: 默认值
            
        Returns:
            配置值，如果不存在则返回默认值
        """
        return self.get_config(key, default, namespace=None)
    
    def get_all(self) -> Dict[str, Any]:
        """获取所有配置
        
        Returns:
            配置字典
        """
        return self.get_all_configs(namespace=None)
    
    def set(self, key: str, value: Any) -> None:
        """设置配置项（Apollo 不支持运行时设置）
        
        Args:
            key: 配置键
            value: 配置值
        """
        logger.warning("Apollo 配置服务不支持运行时设置配置，忽略: %s", key)
    
    def get_config(self, key: str, default: Any = None, namespace: str = None) -> Any:
        """从 Apollo 获取配置项
        
        Args:
            key: 配置键
            default: 默认值
            namespace: 命名空间，默认使用配置中的命名空间
            
        Returns:
            配置值，如果不存在则返回默认值
        """
        if self._client is None:
            logger.warning("Apollo 客户端未初始化，返回默认值")
            return default
        
        try:
            ns = namespace or settings.apollo_namespace
            value = self._client.get_value(key, default_val=default, namespace=ns)
            
            # 更新缓存
            cache_key = f"{ns}:{key}"
            self._config_cache[cache_key] = value
            
            return value
        except Exception as e:
            logger.warning("从 Apollo 获取配置失败 [%s]: %s，使用默认值", key, e)
            return default
    
    def get_all_configs(self, namespace: str = None) -> Dict[str, Any]:
        """获取指定命名空间的所有配置
        
        Args:
            namespace: 命名空间，默认使用配置中的命名空间
            
        Returns:
            配置字典
        """
        if self._client is None:
            logger.warning("Apollo 客户端未初始化，返回空字典")
            return {}
        
        try:
            ns = namespace or settings.apollo_namespace
            configs = self._client.get_json_namespace(ns)
            
            # 更新缓存
            for key, value in configs.items():
                cache_key = f"{ns}:{key}"
                self._config_cache[cache_key] = value
            
            return configs
        except Exception as e:
            logger.warning("从 Apollo 获取所有配置失败 [%s]: %s", namespace, e)
            return {}
    
    def start_config_listener(self, callback: Callable[[str, Any, Any], None], namespace: str = None) -> None:
        """启动配置变更监听
        
        Args:
            callback: 配置变更回调函数，签名为 callback(key, old_value, new_value)
            namespace: 命名空间，默认使用配置中的命名空间
        """
        if self._client is None:
            logger.warning("Apollo 客户端未初始化，无法启动监听")
            return
        
        try:
            ns = namespace or settings.apollo_namespace
            
            # 注册回调
            if ns not in self._change_callbacks:
                self._change_callbacks[ns] = []
            self._change_callbacks[ns].append(callback)
            
            # 启动监听
            def on_change(change_type: str, key: str, value: Any):
                cache_key = f"{ns}:{key}"
                old_value = self._config_cache.get(cache_key)
                self._config_cache[cache_key] = value
                
                logger.info(
                    "Apollo 配置变更 [%s]: %s = %s (旧值: %s)",
                    ns, key, value, old_value
                )
                
                # 触发所有注册的回调
                for cb in self._change_callbacks.get(ns, []):
                    try:
                        cb(key, old_value, value)
                    except Exception as e:
                        logger.error("配置变更回调执行失败: %s", e, exc_info=True)
            
            self._client.start_with_long_poll(on_change_callback=on_change)
            logger.info("Apollo 配置监听已启动 [%s]", ns)
            
        except Exception as e:
            logger.error("启动 Apollo 配置监听失败: %s", e, exc_info=True)

