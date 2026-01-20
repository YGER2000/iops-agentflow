"""
智能体加载器

自动扫描 agents/ 目录，加载所有启用的智能体，并自动发现和注册数据模型。
"""

import os
import sys
import yaml
import importlib
import logging
import inspect
from pathlib import Path
from typing import Dict, Any, Type
from .registry import AgentRegistry
from .base import AgentBase

logger = logging.getLogger(__name__)


class AgentLoader:
    """智能体加载器
    
    负责自动发现、加载和注册智能体
    """
    
    def __init__(self, container=None):
        """初始化加载器
        
        Args:
            container: 服务容器实例（用于依赖注入）
        """
        self.container = container
    
    @classmethod
    def load_all_agents(cls, container=None) -> None:
        """加载所有智能体
        
        Args:
            container: 服务容器实例（用于依赖注入）
        """
        loader = cls(container)
        loader._load_all()
    
    def _load_all(self) -> None:
        """内部方法：加载所有智能体"""
        agents_dir = Path(__file__).parent
        logger.info(f"开始扫描智能体目录: {agents_dir}")
        
        # 遍历 agents 目录下的所有子目录
        for item in agents_dir.iterdir():
            if item.is_dir() and not item.name.startswith('_'):
                # 检查是否包含 agent.yaml
                config_file = item / "agent.yaml"
                if config_file.exists():
                    try:
                        self._load_agent(item, config_file)
                    except Exception as e:
                        logger.error(f"加载智能体失败 [{item.name}]: {str(e)}", exc_info=True)
                        continue
        
        logger.info(f"智能体加载完成，共加载 {len(AgentRegistry.list_agents())} 个智能体")
    
    def _load_agent(self, agent_dir: Path, config_file: Path) -> None:
        """加载单个智能体
        
        Args:
            agent_dir: 智能体目录
            config_file: 配置文件路径
        """
        # 读取配置文件
        with open(config_file, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        # 检查是否启用
        if not config.get('enabled', True):
            logger.info(f"智能体 [{config.get('name', agent_dir.name)}] 已禁用，跳过加载")
            return
        
        # 验证必填字段
        required_fields = ['name', 'version', 'description', 'entry_class']
        for field in required_fields:
            if field not in config:
                raise ValueError(f"配置文件缺少必填字段: {field}")
        
        agent_name = config['name']
        entry_class = config['entry_class']
        if not isinstance(entry_class, str) or not entry_class.strip():
            raise ValueError("配置文件中的 entry_class 必须为非空字符串")
        
        logger.info(f"正在加载智能体: {agent_name} (v{config['version']})")
        
        # 核心文件校验
        required_files = [
            agent_dir / "__init__.py",
            agent_dir / "agent.py",
        ]
        for file_path in required_files:
            if not file_path.exists():
                raise FileNotFoundError(f"智能体缺少必需文件: {file_path}")

        # 动态导入智能体模块
        module_path = f"app.agents.{agent_dir.name}.agent"
        module_prefix = f"app.agents.{agent_dir.name}."
        try:
            # 清理已缓存的模块，确保加载最新代码
            modules_to_clear = [
                name for name in list(sys.modules.keys())
                if name == module_path or name.startswith(module_prefix)
            ]
            package_path = f"app.agents.{agent_dir.name}"
            if package_path in sys.modules:
                modules_to_clear.append(package_path)

            if modules_to_clear:
                logger.info(
                    "清理缓存模块以重新加载: %s",
                    ", ".join(sorted(set(modules_to_clear)))
                )
                for name in modules_to_clear:
                    sys.modules.pop(name, None)

            module = importlib.import_module(module_path)
        except ImportError as e:
            raise ImportError(f"无法导入模块 {module_path}: {str(e)}")
        
        # 获取智能体类
        if not hasattr(module, entry_class):
            raise AttributeError(f"模块 {module_path} 中找不到类 {entry_class}")
        
        agent_class = getattr(module, entry_class)
        
        # 验证是否继承自 AgentBase
        if not issubclass(agent_class, AgentBase):
            raise TypeError(f"智能体类 {entry_class} 必须继承自 AgentBase")
        
        # 实例化智能体
        agent_instance = agent_class()
        
        # 注入服务容器
        if self.container is not None:
            agent_instance.container = self.container
            logger.debug(f"已注入服务容器到智能体: {agent_name}")
        
        # 注入配置和元数据
        if config.get('config'):
            agent_instance.config = self._resolve_config(config.get('config', {}))
        agent_instance.version = config['version']
        agent_instance.author = config.get('author', 'Unknown')
        agent_instance.agent_dir = str(agent_dir)
        agent_instance.dependencies = config.get('dependencies', [])
        
        # 注册到注册中心
        AgentRegistry.register(agent_instance)
        
        # 自动发现和注册数据模型
        self._discover_and_register_models(agent_dir, agent_name)
        
        logger.info(f"✓ 智能体加载成功: {agent_name}")
    
    def _discover_and_register_models(self, agent_dir: Path, agent_name: str) -> None:
        """自动发现并注册智能体的数据模型
        
        Args:
            agent_dir: 智能体目录
            agent_name: 智能体名称
        """
        models_dir = agent_dir / "models"
        
        # 检查是否存在 models 目录
        if not models_dir.exists() or not models_dir.is_dir():
            logger.debug(f"智能体 [{agent_name}] 没有 models 目录，跳过模型注册")
            return
        
        # 检查是否存在 __init__.py
        init_file = models_dir / "__init__.py"
        if not init_file.exists():
            logger.warning(f"智能体 [{agent_name}] 的 models 目录缺少 __init__.py，跳过模型注册")
            return
        
        # 动态导入 models 模块
        module_path = f"app.agents.{agent_dir.name}.models"
        try:
            models_module = importlib.import_module(module_path)
            logger.debug(f"已导入智能体 [{agent_name}] 的 models 模块")
        except ImportError as e:
            logger.error(f"导入智能体 [{agent_name}] 的 models 模块失败: {e}")
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
                logger.debug(f"发现 SQLAlchemy 模型: {obj.__name__}")
        
        # 注册到对应的服务
        if sqlalchemy_models and self.container:
            mysql_service = self.container.get('mysql')
            if mysql_service:
                # 获取 Base.metadata
                from app.core.services.db_base import Base
                mysql_service.register_models(Base.metadata)
                logger.info(f"智能体 [{agent_name}] 注册了 {len(sqlalchemy_models)} 个 SQLAlchemy 模型")
    
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
    
    def _resolve_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """解析配置，支持环境变量替换
        
        Args:
            config: 原始配置字典
            
        Returns:
            解析后的配置字典
        """
        resolved_config = {}

        if config is None:
            return {}
        
        for key, value in config.items():
            if isinstance(value, str) and value.startswith('${') and value.endswith('}'):
                # 环境变量格式: ${ENV_VAR_NAME}
                env_var_name = value[2:-1]
                env_value = os.getenv(env_var_name)
                
                if env_value is None:
                    logger.warning(f"环境变量 {env_var_name} 未设置，使用空字符串")
                    resolved_config[key] = ""
                else:
                    resolved_config[key] = env_value
            else:
                resolved_config[key] = value
        
        return resolved_config

