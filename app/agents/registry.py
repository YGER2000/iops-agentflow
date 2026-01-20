from typing import Dict
from app.agents.base import AgentBase
from app.core.logger import get_logger

logger = get_logger(__name__)


class AgentRegistry:
    """智能体注册中心

    管理所有智能体的注册和获取
    """

    _agents: Dict[str, AgentBase] = {}

    @classmethod
    def register(cls, agent: AgentBase):
        """注册智能体

        Args:
            agent: 智能体实例
        """
        cls._agents[agent.name] = agent
        logger.info(f"已注册智能体: {agent.name} - {agent.description}")

    @classmethod
    def get(cls, agent_name: str) -> AgentBase:
        """获取智能体

        Args:
            agent_name: 智能体名称

        Returns:
            智能体实例

        Raises:
            ValueError: 智能体不存在
        """
        if agent_name not in cls._agents:
            available = ", ".join(cls._agents.keys())
            raise ValueError(
                f"智能体 '{agent_name}' 不存在。可用的智能体: {available}"
            )

        return cls._agents[agent_name]

    @classmethod
    def list_agents(cls) -> Dict[str, str]:
        """列出所有已注册的智能体

        Returns:
            智能体名称到描述的映射
        """
        return {
            name: agent.description
            for name, agent in cls._agents.items()
        }

    @classmethod
    def clear(cls):
        """清空注册表(主要用于测试)"""
        cls._agents.clear()