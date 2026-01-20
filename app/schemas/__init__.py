"""
数据模型模块

定义请求响应的数据结构
"""

from .agent import AgentRequest, AgentResponse

__all__ = [
    # Agent 相关
    "AgentRequest",
    "AgentResponse",
]