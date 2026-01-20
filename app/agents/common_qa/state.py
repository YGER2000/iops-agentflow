from typing import TypedDict, List
from langchain_core.messages import BaseMessage


class CommonQAState(TypedDict):
    """通识问答智能体状态"""
    messages: List[BaseMessage]