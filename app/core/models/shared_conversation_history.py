"""MySQL 共享会话历史模型 - SQLAlchemy

用于多个智能体共享的会话历史表。
通过 agent_name 字段区分不同智能体的会话。
"""

from typing import Optional
from sqlalchemy import String, Text, Integer, Index
from sqlalchemy.dialects.mysql import MEDIUMTEXT
from sqlalchemy.orm import Mapped, mapped_column
from app.core.services.db_base import Base, TimestampMixin


class SharedConversationHistory(Base, TimestampMixin):
    """共享会话历史记录表

    用于存储多个智能体的对话历史，每条消息一行记录。
    通过 agent_name 字段区分不同智能体的会话。
    """
    __tablename__ = 'agentflow_shared_conversation_history'

    # 主键
    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
        comment="主键ID"
    )

    # 会话ID（用于多轮对话）
    thread_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
        comment="会话线程ID"
    )

    # 智能体名称（用于区分不同智能体）
    agent_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
        comment="智能体名称"
    )

    # 角色（user/assistant/system）
    role: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="消息角色"
    )

    # 消息内容
    content: Mapped[str] = mapped_column(
        MEDIUMTEXT,
        nullable=True,
        comment="消息内容"
    )

    # 元数据（JSON 字符串）
    extra_metadata: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="元数据（JSON）"
    )

    # 索引定义
    __table_args__ = (
        Index('idx_thread_agent_created', 'thread_id', 'agent_name', 'created_at'),
        Index('idx_agent_created', 'agent_name', 'created_at'),
        {'comment': '共享会话历史记录表（支持多智能体）'}
    )

    def __repr__(self) -> str:
        return (
            f"<SharedConversationHistory("
            f"id={self.id}, "
            f"thread_id={self.thread_id}, "
            f"agent_name={self.agent_name}, "
            f"role={self.role})>"
        )

