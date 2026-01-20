"""配置服务

提供统一的配置访问接口。
"""

import logging
from typing import Any, Dict
from app.core.config import settings
from app.core.container import IService
from .interfaces import IConfigService

logger = logging.getLogger(__name__)


class ConfigService(IService, IConfigService):
    """配置服务实现
    
    封装对 settings 的访问，支持运行时配置覆盖。
    """
    
    def __init__(self):
        """初始化配置服务"""
        self._runtime_config: Dict[str, Any] = {}  # 运行时配置覆盖
        logger.debug("配置服务已创建")
    
    async def initialize(self) -> None:
        """初始化服务"""
        logger.info("配置服务初始化完成")
    
    async def shutdown(self) -> None:
        """关闭服务"""
        self._runtime_config.clear()
        logger.info("配置服务已关闭")
    
    def get(self, key: str, default: Any = None) -> Any:
        """获取配置项
        
        优先级：运行时配置 > settings 配置
        
        Args:
            key: 配置键
            default: 默认值
            
        Returns:
            配置值
        """
        # 先检查运行时配置
        if key in self._runtime_config:
            return self._runtime_config[key]
        
        # 再检查 settings
        if hasattr(settings, key):
            return getattr(settings, key)
        
        return default
    
    def get_all(self) -> Dict[str, Any]:
        """获取所有配置
        
        Returns:
            配置字典（settings + 运行时配置）
        """
        # 从 settings 获取所有配置
        all_config = {}
        for key in dir(settings):
            if not key.startswith('_') and key not in ['Config']:
                value = getattr(settings, key)
                if not callable(value):
                    all_config[key] = value
        
        # 覆盖运行时配置
        all_config.update(self._runtime_config)
        
        return all_config
    
    def set(self, key: str, value: Any) -> None:
        """设置运行时配置
        
        注意：这不会修改 settings 对象，只是在内存中覆盖。
        
        Args:
            key: 配置键
            value: 配置值
        """
        self._runtime_config[key] = value
        logger.debug(f"运行时配置已设置: {key} = {value}")
    
    def get_settings(self):
        """获取原始 settings 对象
        
        Returns:
            Settings 对象
        """
        return settings

