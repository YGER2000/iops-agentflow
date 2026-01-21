from typing import TypedDict, List, Optional, Dict, Any
from langchain_core.messages import BaseMessage


class DomainContext(TypedDict, total=False):
    """领域上下文

    这里保留与旧实现一致的结构，便于后续扩展（例如：指代消解、领域识别等）。
    """

    last_query: Optional[str]
    pronoun_resolution: Optional[Dict[str, str]]


class RetrievedSlice(TypedDict, total=False):
    """检索切片（接口返回的原样/最小加工结果）

    重要约定：
    - `retrieved` 保存的是检索接口返回的“原样信息”（在本项目里，ReqSearchClient 已做了轻微清洗：title/content）。
    - `references` 则保存为前端展示而“整理/拼接”后的信息（例如更统一的结构、去重后的结果等）。
    """

    title: str
    content: str

    # 兼容字段（旧代码/历史数据可能存在）
    para: str
    nid: str
    url: Optional[str]
    doc_guid: Optional[str]
    knowledge_id: Optional[str]
    raw: Optional[Dict[str, Any]]


class RAGState(TypedDict, total=False):
    """RAG 智能体状态

    与 `common_qa` 的核心差异：
    - 增加了 query 解析/改写/检索/参考来源等字段。
    - `history_messages` 由 agent 层注入，保证持久化/历史逻辑与 `common_qa` 一致。
    """

    # 依赖注入/配置
    agent_config: Dict[str, Any]

    # 上下文
    domain_context: Optional[DomainContext]
    history_messages: List[BaseMessage]

    # 输入与解析
    raw_input: str
    tag: Optional[str]
    parsed_query: Optional[str]
    rewritten_query: Optional[str]

    # 检索结果与参考来源
    retrieved: List[RetrievedSlice]
    references: List[Dict[str, Any]]

    # 输出与溯源
    can_answer: Optional[bool]
    answer: Optional[str]
    fallback_reason: Optional[str]
    answer_source: Optional[str]  # kb | llm_fallback

    # 其他
    metadata: Optional[Dict[str, Any]]
    error: Optional[str]

