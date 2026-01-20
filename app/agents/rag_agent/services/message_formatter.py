# app/agents/rag_agent/services/message_formatter.py
from typing import Dict, Any, List
import json
import logging
logger = logging.getLogger(__name__)
def format_response_message(answer: str, references: List[Dict[str, Any]]) -> str:
    """
    用：：：拼接答案和参考内容

    Args:
        answer: AI生成的答案
        references: 参考资料列表，暂时用retrieved

    Returns:
        拼接后的消息内容
    """
    # 如果没有参考资料，直接返回答案
    if not references:
        # 后续可以在没有参考资料时，返回提示。暂时为冗余设计
        formatted_message = answer
        return formatted_message

    # 构建参考来源部分
    reference_content = []
    for i, ref in enumerate(references, 1):
        title = ref.get('title', '')
        content = ref.get('content', '')
        reference_content.append(f"\n\n:::modal [{i}]{title}\n{content}\n\n:::\n\n")

    references_str = "\n".join(reference_content)

    # 拼接答案和参考资料
    formatted_message = f"\n{answer}\n\n:::card 参考来源\n{references_str}\n:::"
    logger.debug(f"[format_response_message] formatted_message: {formatted_message}")
    return formatted_message
