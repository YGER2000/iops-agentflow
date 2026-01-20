from typing import TypedDict, List, Optional, Dict, Any

class DomainContext(TypedDict, total=False):
    """领域上下文
    保存用户当前的业务领域与代词解析信息
    """
    last_query: Optional[str]
    pronoun_resolution: Optional[Dict[str, str]]

class RetrievedSlice(TypedDict, total=False):
    """
    RAG智能体状态
    """
    raw: Optional[Dict[str, Any]]
    title: str
    para: str
    nid: str
    para_items:list[Dict[str, str]]

    url: Optional[str]
    doc_guid: Optional[str]
    knowledge_id: Optional[str]


class RAGState(TypedDict, total=False):
    """
    RAG智能体状态
    """
    agent_config: Dict[str, Any]
    domain_context: Optional[DomainContext]

    raw_input: str
    tag: Optional[str]
    parsed_query: Optional[str]

    rewritten_query: Optional[str]
    retrieved: List[RetrievedSlice]
    references: List[Dict[str, Any]]

    can_answer: Optional[bool]
    answer: Optional[str]
    fallback_reason: Optional[str]
    answer_source: Optional[str] # kb | llm_fallback

    metadata: Optional[Dict[str, Any]]