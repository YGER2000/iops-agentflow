"""MongoDB 操作辅助函数

提供常用的 MongoDB CRUD 操作封装，简化业务代码。
"""

from typing import Optional, Dict, Any, Type
from datetime import datetime
from bson import ObjectId
from pydantic import BaseModel


async def find_one_document(
    collection,
    model_class: Type[BaseModel],
    filter_dict: Dict[str, Any]
) -> Optional[BaseModel]:
    """查询单个文档并转换为 Pydantic 模型
    
    Args:
        collection: Motor 集合对象
        model_class: Pydantic 模型类
        filter_dict: 查询过滤条件
        
    Returns:
        模型实例，如果未找到则返回 None
    """
    doc_dict = await collection.find_one(filter_dict)
    if doc_dict is None:
        return None
    return model_class(**doc_dict)


async def save_document(
    collection,
    document: BaseModel,
    upsert: bool = True
) -> ObjectId:
    """保存文档（插入或更新）
    
    Args:
        collection: Motor 集合对象
        document: Pydantic 模型实例
        upsert: 是否使用 upsert（找不到时插入）
        
    Returns:
        文档的 ObjectId
    """
    # 更新 updated_at 时间戳
    if hasattr(document, 'updated_at'):
        document.updated_at = datetime.now()
    
    # 转换为字典
    doc_dict = document.model_dump(by_alias=True, exclude_none=False)
    
    # 如果有 _id，执行更新
    if doc_dict.get('_id'):
        doc_id = doc_dict['_id']
        # 从更新数据中移除 _id
        update_data = {k: v for k, v in doc_dict.items() if k != '_id'}
        
        if upsert:
            result = await collection.update_one(
                {'_id': doc_id},
                {'$set': update_data},
                upsert=True
            )
            return doc_id
        else:
            await collection.update_one(
                {'_id': doc_id},
                {'$set': update_data}
            )
            return doc_id
    else:
        # 没有 _id，执行插入
        # 移除 None 值的 _id
        if '_id' in doc_dict and doc_dict['_id'] is None:
            del doc_dict['_id']
        
        result = await collection.insert_one(doc_dict)
        # 更新模型的 id
        if hasattr(document, 'id'):
            document.id = result.inserted_id
        return result.inserted_id


async def insert_document(
    collection,
    document: BaseModel
) -> ObjectId:
    """插入新文档
    
    Args:
        collection: Motor 集合对象
        document: Pydantic 模型实例
        
    Returns:
        新文档的 ObjectId
    """
    # 转换为字典
    doc_dict = document.model_dump(by_alias=True, exclude={'id'})
    
    # 插入
    result = await collection.insert_one(doc_dict)
    
    # 更新模型的 id
    if hasattr(document, 'id'):
        document.id = result.inserted_id
    
    return result.inserted_id


async def update_document(
    collection,
    doc_id: ObjectId,
    update_data: Dict[str, Any]
) -> bool:
    """更新文档
    
    Args:
        collection: Motor 集合对象
        doc_id: 文档 ID
        update_data: 更新数据
        
    Returns:
        是否更新成功
    """
    # 添加 updated_at 时间戳
    update_data['updated_at'] = datetime.now()
    
    result = await collection.update_one(
        {'_id': doc_id},
        {'$set': update_data}
    )
    
    return result.modified_count > 0

