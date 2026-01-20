"""SQLAlchemy ORM 基础类

提供 SQLAlchemy 声明式基类和通用 Mixin。
"""

from datetime import datetime
from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """SQLAlchemy 声明式基类
    
    所有 SQLAlchemy 模型都应继承此类。
    """
    pass


class TimestampMixin:
    """时间戳 Mixin
    
    提供 created_at 和 updated_at 字段。
    """
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        comment="创建时间"
    )
    
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        comment="更新时间"
    )

