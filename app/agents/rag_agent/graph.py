from langgraph.graph import StateGraph, END
from .state import RAGState
import logging
from . import nodes


def build_rag_graph(llm_service, req_client) -> StateGraph:
    """构建通识问答图
    
    Args:
        llm_service: LLM 服务实例
        req_client: 检索接口客户端
    Returns:
        StateGraph 工作流
    """
    nodes.set_llm_service(llm_service)
    nodes.set_req_client(req_client)
    
    workflow = StateGraph(RAGState)

    # 添加节点
    workflow.add_node("parse_input", nodes.parse_input_node)
    workflow.add_node("rewrite_query", nodes.rewrite_query_node)
    workflow.add_node("req_search", nodes.req_search_node)
    workflow.add_node("preprocess_results", nodes.preprocess_results_node)
    workflow.add_node("judge_answerable", nodes.judge_answerable_node)
    workflow.add_node("compose_answer", nodes.compose_answer_node)
    # 设置入口
    workflow.set_entry_point("parse_input")
    # 设置边
    workflow.add_edge("parse_input", "rewrite_query")
    workflow.add_edge("rewrite_query", "req_search")
    workflow.add_edge("req_search", "preprocess_results")
    workflow.add_edge("preprocess_results", "judge_answerable")
    workflow.add_edge("judge_answerable", "compose_answer")
    workflow.add_edge("compose_answer", END)

    return workflow