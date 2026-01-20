from pydantic import BaseModel
from typing import Optional, Dict, Any, List


class AgentRequest(BaseModel):
    """Agent 请求模型"""
    agent_name: str
    message: str
    thread_id: Optional[str] = None  # 用于多轮对话
    context: Optional[Dict[str, Any]] = None  # 额外上下文(如选中的资源)


class AgentStreamRequest(BaseModel):
    """Agent 流式请求模型"""
    agent_name: str
    message: str
    thread_id: Optional[str] = None  # 用于多轮对话
    context: Optional[Dict[str, Any]] = None  # 额外上下文(如选中的资源)


class AgentResponse(BaseModel):
    """Agent 响应模型"""
    message: str
    thread_id: str
    data: Optional[Dict[str, Any]] = None  # 返回的结构化数据(如查询结果)
    need_user_action: bool = False  # 是否需要用户操作(如选择资源)
    action_type: Optional[str] = None  # 操作类型: select_resource
    metadata: Optional[Dict[str, Any]] = None