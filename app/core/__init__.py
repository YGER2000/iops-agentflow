"""
核心模块

提供配置管理、会话历史管理、服务容器等核心功能
"""

from .config import settings, Settings
from .chat_history import get_chat_history_manager, ChatHistoryManager
from .container import ServiceContainer

__all__ = [
    "settings",
    "Settings",
    "get_chat_history_manager",
    "ChatHistoryManager",
    "ServiceContainer",
]