from abc import ABC, abstractmethod
from typing import Dict, Any, AsyncGenerator, TYPE_CHECKING, Optional
from langgraph.graph import StateGraph
from app.schemas.agent import AgentResponse
import os

if TYPE_CHECKING:
    from app.core.container import ServiceContainer
    from app.core.services.interfaces import ILLMService, IDatabaseService, IMongoDBService, IConfigService


class AgentBase(ABC):
    """智能体基类

    所有智能体都需要继承此基类并实现相关方法
    """

    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description
        self._graph = None
        
        # 依赖注入容器（由加载器注入）
        self.container: Optional['ServiceContainer'] = None
        
        # 插件化相关属性（由加载器注入）
        self.config: Dict[str, Any] = {}  # 智能体配置
        self.version: str = "1.0.0"  # 版本号
        self.author: str = "Unknown"  # 作者
        self.agent_dir: str = ""  # 智能体目录路径
        self.dependencies: list = []  # 依赖的其他智能体

    @abstractmethod
    def build_graph(self) -> StateGraph:
        """构建 LangGraph 图

        每个智能体需要实现自己的图结构
        """
        pass

    def get_graph(self):
        """获取编译后的图"""
        if self._graph is None:
            self._graph = self.build_graph()
        return self._graph

    @abstractmethod
    async def invoke(
            self,
            message: str,
            thread_id: str,
            context: Dict[str, Any] = None
    ) -> AgentResponse:
        """调用智能体

        Args:
            message: 用户消息
            thread_id: 线程ID(用于多轮对话)
            context: 额外上下文

        Returns:
            AgentResponse: 智能体响应
        """
        pass

    async def stream(
            self,
            message: str,
            thread_id: str,
            context: Dict[str, Any] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """流式调用智能体（可选实现）

        Args:
            message: 用户消息
            thread_id: 线程ID(用于多轮对话)
            context: 额外上下文

        Yields:
            Dict[str, Any]: 包含 type 和 data 的字典
                - type: 'message' | 'data' | 'metadata'
                - data: 对应的数据

        默认实现：回退到非流式调用
        """
        # 默认实现：调用非流式方法并一次性返回
        result = await self.invoke(message, thread_id, context)
        
        # 先发送消息
        yield {
            "type": "message",
            "data": result.message
        }
        
        # 发送数据
        if result.data:
            yield {
                "type": "data",
                "data": {
                    "data": result.data,
                    "need_user_action": result.need_user_action,
                    "action_type": result.action_type
                }
            }
        
        # 发送元数据
        if result.metadata:
            yield {
                "type": "metadata",
                "data": result.metadata
            }

    def get_agent_dir(self) -> str:
        """获取智能体目录路径
        
        Returns:
            智能体目录的绝对路径
        """
        return self.agent_dir
    
    def load_prompt(self, prompt_file: str) -> str:
        """加载提示词文件

        Args:
            prompt_file: 提示词文件名(相对于智能体的 prompts/ 目录)
                        例如: "system.md" 或 "intent.md"

        Returns:
            提示词内容
        """
        # 如果是绝对路径，直接使用（兼容旧代码）
        if os.path.isabs(prompt_file):
            file_path = prompt_file
        else:
            # 否则从智能体的 prompts/ 目录加载
            if self.agent_dir:
                file_path = os.path.join(self.agent_dir, "prompts", prompt_file)
            else:
                # 兼容性：如果没有设置 agent_dir，尝试从项目根目录加载
                file_path = prompt_file
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        except FileNotFoundError:
            raise FileNotFoundError(f"提示词文件不存在: {file_path}")
    
    # ============================================================
    # 新的依赖注入方式 - 通过服务容器访问组件
    # ============================================================
    
    @property
    def llm(self) -> 'ILLMService':
        """获取 LLM 服务
        
        Returns:
            LLM 服务实例
        """
        if self.container is None:
            raise RuntimeError("服务容器未注入，请确保智能体已正确加载")
        return self.container.get('llm')
    
    @property
    def mysql(self) -> 'IDatabaseService':
        """获取 MySQL 服务
        
        Returns:
            MySQL 服务实例
        """
        if self.container is None:
            raise RuntimeError("服务容器未注入，请确保智能体已正确加载")
        return self.container.get('mysql')
    
    @property
    def mongodb(self) -> 'IMongoDBService':
        """获取 MongoDB 服务
        
        Returns:
            MongoDB 服务实例
        """
        if self.container is None:
            raise RuntimeError("服务容器未注入，请确保智能体已正确加载")
        return self.container.get('mongodb')
    
    @property
    def apollo(self) -> 'IConfigService':
        """获取 Apollo 配置服务
        
        Returns:
            Apollo 配置服务实例
        """
        if self.container is None:
            raise RuntimeError("服务容器未注入，请确保智能体已正确加载")
        return self.container.get('apollo')
    
    def get_service(self, name: str, default: Any = None) -> Any:
        """获取任意已注册的服务
        
        Args:
            name: 服务名称
            default: 默认值
            
        Returns:
            服务实例
        """
        if self.container is None:
            raise RuntimeError("服务容器未注入，请确保智能体已正确加载")
        return self.container.get(name, default)
    