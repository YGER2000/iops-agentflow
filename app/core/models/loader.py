"""核心共享模型加载器

负责自动扫描和注册 app/core/models/ 目录下的共享模型。
"""

import logging
import inspect
import importlib
from pathlib import Path
from typing import Type

logger = logging.getLogger(__name__)


class CoreModelsLoader:
    """核心共享模型加载器
    
    在应用启动时自动扫描和注册共享模型，
    独立于智能体加载流程，逻辑更清晰。
    """
    
    def __init__(self, container=None):
        """初始化加载器
        
        Args:
            container: 服务容器实例（用于依赖注入）
        """
        self.container = container
    
    @classmethod
    def load_core_models(cls, container=None) -> None:
        """加载所有核心共享模型
        
        Args:
            container: 服务容器实例（用于依赖注入）
        """
        loader = cls(container)
        loader._load_all()
    
    def _load_all(self) -> None:
        """内部方法：加载所有共享模型"""
        core_models_dir = Path(__file__).parent
        logger.info(f"开始扫描核心共享模型目录: {core_models_dir}")
        
        # 动态导入 core.models 模块
        try:
            models_module = importlib.import_module('app.core.models')
            logger.debug("已导入 app.core.models 模块")
        except ImportError as e:
            logger.error(f"导入 app.core.models 模块失败: {e}")
            return
        
        # 扫描 SQLAlchemy 模型
        sqlalchemy_models = []
        
        # 遍历模块中的所有成员
        for name, obj in inspect.getmembers(models_module):
            # 跳过私有成员和导入的模块
            if name.startswith('_') or inspect.ismodule(obj):
                continue
            
            # 检查是否是类
            if not inspect.isclass(obj):
                continue
            
            # 检查是否是 SQLAlchemy 模型
            if self._is_sqlalchemy_model(obj):
                sqlalchemy_models.append(obj)
                logger.info(f"发现共享 SQLAlchemy 模型: {obj.__name__} (表: {obj.__tablename__})")
        
        # 注册到对应的服务
        if sqlalchemy_models and self.container:
            mysql_service = self.container.get('mysql')
            if mysql_service:
                from app.core.services.db_base import Base
                mysql_service.register_models(Base.metadata)
                logger.info(f"✓ 注册了 {len(sqlalchemy_models)} 个共享 SQLAlchemy 模型")
        
        if not sqlalchemy_models:
            logger.info("未发现任何共享模型")
    
    def _is_sqlalchemy_model(self, obj: Type) -> bool:
        """检查对象是否是 SQLAlchemy 模型
        
        Args:
            obj: 要检查的类
            
        Returns:
            是否是 SQLAlchemy 模型
        """
        try:
            from app.core.services.db_base import Base
            # 检查是否继承自 Base，且不是 Base 本身
            return (
                inspect.isclass(obj) and 
                issubclass(obj, Base) and 
                obj is not Base and
                hasattr(obj, '__tablename__')  # 确保定义了表名
            )
        except ImportError:
            return False

