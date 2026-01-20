"""MongoDB 基础模型类

提供 MongoDB 文档的基础 Pydantic 模型。
使用原生 motor 驱动，不依赖 ODM。
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict
from bson import ObjectId


class PyObjectId(ObjectId):
    """自定义 ObjectId 类型，用于 Pydantic 验证"""
    
    @classmethod
    def __get_pydantic_core_schema__(cls, _source_type, _handler):
        from pydantic_core import core_schema
        return core_schema.union_schema([
            core_schema.is_instance_schema(ObjectId),
            core_schema.chain_schema([
                core_schema.str_schema(),
                core_schema.no_info_plain_validator_function(cls.validate),
            ])
        ])
    
    @classmethod
    def validate(cls, v):
        if not ObjectId.is_valid(v):
            raise ValueError("Invalid ObjectId")
        return ObjectId(v)


class BaseDocument(BaseModel):
    """MongoDB Document 基类
    
    所有 MongoDB 文档模型都可以继承此类。
    提供通用的 ID 和时间戳字段。
    """
    id: Optional[PyObjectId] = Field(default=None, alias="_id", description="文档ID")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    updated_at: datetime = Field(default_factory=datetime.now, description="更新时间")
    
    model_config = ConfigDict(
        populate_by_name=True,  # 允许使用字段名或别名
        arbitrary_types_allowed=True,  # 允许自定义类型（如 ObjectId）
        json_encoders={ObjectId: str}  # ObjectId 序列化为字符串
    )

