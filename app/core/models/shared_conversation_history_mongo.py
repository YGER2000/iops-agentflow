# """MongoDB 共享会话历史模型 - Beanie
#
# 用于多个智能体共享的会话历史集合。
# 通过 agent_name 字段区分不同智能体的会话。
# """
#
# from typing import List, Optional, ClassVar
# from pydantic import Field
# from app.core.services.mongo_base import BaseDocument
#
#
# class SharedConversationHistoryMongo(BaseDocument):
#     """共享会话历史文档
#
#     用于存储多个智能体的对话历史，一个会话一个文档。
#     消息以数组形式存储，便于查询整个会话上下文。
#     通过 agent_name 字段区分不同智能体的会话。
#     """
#
#     # 会话ID（用于多轮对话）
#     thread_id: str = Field(..., description="会话线程ID")
#
#     # 智能体名称（用于区分不同智能体）
#     agent_name: str = Field(..., description="智能体名称")
#
#     # 消息列表
#     messages: List[dict] = Field(default_factory=list, description="消息列表")
#
#     # 会话元数据
#     user_id: Optional[str] = Field(None, description="用户ID")
#
#     # 集合名称（用于 motor 操作）
#     COLLECTION_NAME: ClassVar[str] = "agentflow_shared_conversation_history"
#
#     def add_message(self, role: str, content: str, extra_metadata: Optional[dict] = None):
#         """添加消息到会话
#
#         Args:
#             role: 消息角色
#             content: 消息内容
#             extra_metadata: 元数据
#         """
#         message = {
#             "role": role,
#             "content": content,
#             "extra_metadata": extra_metadata
#         }
#         self.messages.append(message)
#
#     def get_recent_messages(self, limit: int = 10) -> List[dict]:
#         """获取最近的 N 条消息
#
#         Args:
#             limit: 消息数量
#
#         Returns:
#             消息列表
#         """
#         return self.messages[-limit:]
#
#     def __repr__(self) -> str:
#         return (
#             f"<SharedConversationHistoryMongo("
#             f"thread_id={self.thread_id}, "
#             f"agent_name={self.agent_name}, "
#             f"messages={len(self.messages)})>"
#         )
#
