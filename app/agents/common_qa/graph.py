from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage, AIMessage
from .state import CommonQAState
import logging

logger = logging.getLogger(__name__)


def build_common_qa_graph(llm_service) -> StateGraph:
    """构建通识问答图
    
    Args:
        llm_service: LLM 服务实例
    
    Returns:
        StateGraph 工作流
    """
    
    def chat_node(state: CommonQAState) -> CommonQAState:
        """聊天节点 - 使用依赖注入的 LLM 服务"""
        llm = llm_service.get_model()
        response = llm.invoke(state["messages"])
        logger.info("LLM response generated")

        return {
            "messages": state["messages"] + [response]
        }
    
    workflow = StateGraph(CommonQAState)

    # 添加节点
    workflow.add_node("chat", chat_node)

    # 设置入口
    workflow.set_entry_point("chat")

    # 设置边
    workflow.add_edge("chat", END)

    return workflow