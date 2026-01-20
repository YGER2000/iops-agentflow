"""统一的日志处理器

提供统一的日志配置和管理功能，支持：
- 可配置的日志级别
- 控制台和文件输出
- 日志文件轮转
- 不同模块的日志级别配置
- 按智能体名称分离日志文件
"""

import logging
import logging.handlers
import sys
from pathlib import Path
from typing import Optional, Dict

from app.core.config import settings


class ColoredFormatter(logging.Formatter):
    """带颜色的日志格式化器（用于控制台输出）"""
    
    # ANSI 颜色代码
    COLORS = {
        'DEBUG': '\033[36m',      # 青色
        'INFO': '\033[32m',       # 绿色
        'WARNING': '\033[33m',   # 黄色
        'ERROR': '\033[31m',      # 红色
        'CRITICAL': '\033[35m',  # 紫色
        'RESET': '\033[0m'        # 重置
    }
    
    def format(self, record: logging.LogRecord) -> str:
        """格式化日志记录，添加颜色"""
        log_color = self.COLORS.get(record.levelname, self.COLORS['RESET'])
        
        # 添加颜色到级别名称
        record.levelname = f"{log_color}{record.levelname}{self.COLORS['RESET']}"
        
        return super().format(record)


class AgentLoggingHandler(logging.Handler):
    """智能体日志处理器
    
    根据日志记录器的名称自动路由日志到对应的智能体日志文件
    """
    
    def __init__(self, log_dir: str, main_log_file: str, max_bytes: int = 10 * 1024 * 1024, backup_count: int = 5):
        """初始化智能体日志处理器
        
        Args:
            log_dir: 日志文件目录
            main_log_file: 主日志文件名（用于非智能体模块）
            max_bytes: 单个日志文件最大字节数
            backup_count: 保留的备份文件数量
        """
        super().__init__()
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.main_log_file = main_log_file
        self.max_bytes = max_bytes
        self.backup_count = backup_count
        
        # 缓存已创建的文件处理器
        self._handlers: Dict[str, logging.Handler] = {}
        
        # 创建主日志文件处理器
        main_log_path = self.log_dir / main_log_file
        main_handler = logging.handlers.RotatingFileHandler(
            main_log_path,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding='utf-8'
        )
        main_handler.setFormatter(self._get_formatter())
        self._handlers['__main__'] = main_handler
    
    def _get_formatter(self) -> logging.Formatter:
        """获取日志格式化器"""
        detailed_format = (
            '%(asctime)s | %(process)d | %(levelname)-8s | %(name)s | %(filename)s:%(lineno)d | %(message)s'
        )
        return logging.Formatter(detailed_format)
    
    def _get_agent_name_from_logger(self, logger_name: str) -> Optional[str]:
        """从日志记录器名称中提取智能体名称
        
        Args:
            logger_name: 日志记录器名称，例如 'app.agents.common_qa.agent'
        
        Returns:
            智能体名称，如果不是智能体模块则返回 None
        """
        # 检查是否是智能体模块
        if not logger_name.startswith('app.agents.'):
            return None
        
        # 提取智能体目录名（例如 'app.agents.common_qa.agent' -> 'common_qa'）
        parts = logger_name.split('.')
        if len(parts) < 3:
            return None
        
        agent_dir_name = parts[2]
        
        # 查找智能体目录名对应的智能体名称
        try:
            from app.agents.registry import AgentRegistry
            
            # 尝试通过目录名直接获取智能体（如果智能体名称和目录名相同）
            try:
                agent = AgentRegistry.get(agent_dir_name)
                return agent.name
            except ValueError:
                # 如果目录名不是智能体名称，遍历所有智能体查找匹配的目录名
                # 通过访问智能体的 agent_dir 属性来匹配
                agents_dict = AgentRegistry._agents
                for agent_name, agent_instance in agents_dict.items():
                    if hasattr(agent_instance, 'agent_dir'):
                        # 提取目录名（从完整路径中）
                        agent_dir = Path(agent_instance.agent_dir).name
                        if agent_dir == agent_dir_name:
                            return agent_instance.name
                
                # 如果找不到匹配的，使用目录名（避免日志混乱）
                return agent_dir_name
        except Exception:
            # 如果智能体注册表还未初始化或出错，使用目录名
            return agent_dir_name
    
    def _get_handler_for_agent(self, agent_name: str) -> logging.Handler:
        """获取或创建智能体的日志文件处理器
        
        Args:
            agent_name: 智能体名称
        
        Returns:
            日志文件处理器
        """
        if agent_name not in self._handlers:
            # 创建智能体日志文件（文件名：{agent_name}.log）
            log_file = f"{agent_name}.log"
            log_path = self.log_dir / log_file
            
            handler = logging.handlers.RotatingFileHandler(
                log_path,
                maxBytes=self.max_bytes,
                backupCount=self.backup_count,
                encoding='utf-8'
            )
            handler.setFormatter(self._get_formatter())
            self._handlers[agent_name] = handler
        
        return self._handlers[agent_name]
    
    def emit(self, record: logging.LogRecord) -> None:
        """处理日志记录
        
        Args:
            record: 日志记录
        """
        try:
            # 判断日志来源
            agent_name = self._get_agent_name_from_logger(record.name)
            
            if agent_name:
                # 智能体日志，写入对应的文件
                handler = self._get_handler_for_agent(agent_name)
            else:
                # 平台日志，写入主日志文件
                handler = self._handlers['__main__']
            
            handler.emit(record)
        except Exception:
            # 如果出错，至少写入主日志文件
            try:
                self._handlers['__main__'].emit(record)
            except Exception:
                self.handleError(record)
    
    def close(self) -> None:
        """关闭所有处理器"""
        for handler in self._handlers.values():
            handler.close()
        super().close()


def setup_logging(
    log_level: Optional[str] = None,
    log_dir: Optional[str] = None,
    log_file: Optional[str] = None,
    log_to_file: bool = True,
    log_to_console: bool = True,
    max_bytes: int = 10 * 1024 * 1024,  # 10MB
    backup_count: int = 5,
    module_levels: Optional[Dict[str, str]] = None
) -> None:
    """设置全局日志配置
    
    Args:
        log_level: 日志级别 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
                  默认从 settings.log_level 读取
        log_dir: 日志文件目录，默认 logs/
        log_file: 日志文件名，默认 app.log
        log_to_file: 是否输出到文件，默认 True
        log_to_console: 是否输出到控制台，默认 True
        max_bytes: 单个日志文件最大字节数，默认 10MB
        backup_count: 保留的备份文件数量，默认 5
        module_levels: 不同模块的日志级别配置，例如 {'app.core': 'DEBUG'}
    """
    # 获取日志级别
    if log_level is None:
        log_level = getattr(settings, 'log_level', 'INFO').upper()
    
    # 设置根日志级别
    root_level = getattr(logging, log_level, logging.INFO)
    logging.root.setLevel(root_level)
    
    # 清除现有的处理器
    logging.root.handlers.clear()
    
    # 日志格式（控制台使用简化格式）
    simple_format = '%(asctime)s | %(process)d | %(levelname)-8s | %(message)s'
    
    # 控制台输出
    if log_to_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(root_level)
        # 控制台使用彩色格式化器
        console_formatter = ColoredFormatter(simple_format)
        console_handler.setFormatter(console_formatter)
        logging.root.addHandler(console_handler)
    
    # 文件输出
    if log_to_file:
        # 确定日志目录
        if log_dir is None:
            log_dir = getattr(settings, 'log_dir', 'logs')
        
        # 确定日志文件名
        if log_file is None:
            log_file = getattr(settings, 'log_file', 'app.log')
        
        # 使用智能体日志处理器（自动路由到不同文件）
        agent_handler = AgentLoggingHandler(
            log_dir=log_dir,
            main_log_file=log_file,
            max_bytes=max_bytes,
            backup_count=backup_count
        )
        agent_handler.setLevel(root_level)
        logging.root.addHandler(agent_handler)
    
    # 设置第三方库的日志级别
    _setup_third_party_loggers()
    
    # 设置特定模块的日志级别
    if module_levels:
        for module_name, level in module_levels.items():
            module_logger = logging.getLogger(module_name)
            module_logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    
    # 记录日志系统初始化信息
    logger = logging.getLogger(__name__)
    logger.info(f"日志系统已初始化，级别: {log_level}")
    if log_to_file and log_dir:
        logger.info(f"主日志文件: {log_dir}/{log_file}")
        logger.info(f"智能体日志将自动分离到独立的日志文件中（格式: {log_dir}/<agent_name>.log）")


def _setup_third_party_loggers() -> None:
    """设置第三方库的日志级别"""
    # 降低某些第三方库的日志级别，避免噪音
    third_party_loggers = {
        'httpx': logging.WARNING,
        'httpcore': logging.WARNING,
        'urllib3': logging.WARNING,
        'asyncio': logging.WARNING,
        'uvicorn.access': logging.WARNING,
        'motor': logging.WARNING,
        'aiomysql': logging.WARNING,
        'langchain': logging.INFO,
        'langgraph': logging.INFO,
        'langchain_openai': logging.INFO,
    }
    
    for logger_name, level in third_party_loggers.items():
        logger = logging.getLogger(logger_name)
        logger.setLevel(level)


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """获取日志记录器
    
    Args:
        name: 日志记录器名称，通常使用 __name__
              如果为 None，返回调用模块的日志记录器
    
    Returns:
        Logger 实例
    """
    if name is None:
        # 尝试获取调用者的模块名
        import inspect
        frame = inspect.currentframe().f_back
        name = frame.f_globals.get('__name__', 'app')
    
    return logging.getLogger(name)


# 初始化日志系统（使用默认配置）
def init_logging() -> None:
    """初始化日志系统（从配置读取）"""
    log_level = getattr(settings, 'log_level', 'INFO')
    log_dir = getattr(settings, 'log_dir', 'logs')
    log_file = getattr(settings, 'log_file', 'app.log')
    log_to_file = getattr(settings, 'log_to_file', True)
    log_to_console = getattr(settings, 'log_to_console', True)
    
    module_levels = {}
    if hasattr(settings, 'log_module_levels'):
        module_levels = getattr(settings, 'log_module_levels', {})
    
    setup_logging(
        log_level=log_level,
        log_dir=log_dir,
        log_file=log_file,
        log_to_file=log_to_file,
        log_to_console=log_to_console,
        module_levels=module_levels if module_levels else None
    )

