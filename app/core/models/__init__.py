"""核心共享数据模型

提供可供所有智能体共享使用的数据模型。
"""

# from .shared_conversation_history import SharedConversationHistory
# from .shared_conversation_history_mongo import SharedConversationHistoryMongo
# from .loader import CoreModelsLoader
#
# __all__ = [
#     'SharedConversationHistory',
#     'SharedConversationHistoryMongo',
#     'CoreModelsLoader',
# ]


from .shared_conversation_history import SharedConversationHistory
from .loader import CoreModelsLoader

__all__ = [
    'SharedConversationHistory',
    'CoreModelsLoader',
]

