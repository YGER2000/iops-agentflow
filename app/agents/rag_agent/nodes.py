import logging
import os
from typing import Dict, Any, List, Optional, Tuple

from langchain_core.messages import SystemMessage, HumanMessage

from .state import RAGState, RetrievedSlice

logger = logging.getLogger(__name__)

# ============================================================
# 依赖注入（由 graph.build_* 注入）
# ============================================================
_llm_service = None
_req_client = None

# Prompt 懒加载缓存（避免频繁读文件）
_rewrite_prompt: Optional[str] = None
_answer_prompt: Optional[str] = None


def set_llm_service(llm_service) -> None:
    """注入 LLM 服务（由 graph 构建阶段调用）"""
    global _llm_service
    _llm_service = llm_service
    logger.info("[nodes] llm_service injected: %s", type(llm_service).__name__)


def set_req_client(req_client) -> None:
    """注入检索客户端（由 graph 构建阶段调用）"""
    global _req_client
    _req_client = req_client
    logger.info("[nodes] req_client injected: %s", type(req_client).__name__)


def _load_prompt(file_name: str) -> str:
    """从当前智能体 prompts 目录读取提示词文件"""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    prompt_path = os.path.join(base_dir, "prompts", file_name)
    with open(prompt_path, "r", encoding="utf-8") as f:
        return f.read()


def _build_references_from_retrieved(retrieved: List[RetrievedSlice]) -> List[Dict[str, Any]]:
    """根据 retrieved 构造 references（用于后续展示/去重/扩展）

    约定：
    - retrieved：检索接口“原样/最小加工”的返回。
    - references：结构化整理后的引用信息（当前先做一层轻整理）。
    """
    references: List[Dict[str, Any]] = []
    for idx, item in enumerate(retrieved or [], start=1):
        references.append(
            {
                "index": idx,
                "title": item.get("title", ""),
                "content": item.get("content", item.get("para", "")),
            }
        )
    return references


async def parse_input_node(state: RAGState) -> RAGState:
    """解析输入中的 query 与 tag

    支持两种输入格式：
    1) searchTagFilter:xxx, query:yyy
    2) yyy（纯 query）

    注意：这一步只做字符串解析，不做任何模型调用。
    """
    raw_text = (state.get("raw_input") or "").strip()
    tag: Optional[str] = None
    query_text: str = raw_text

    if raw_text.startswith("searchTagFilter:"):
        parts = raw_text.split(", query:", 1)
        tag = parts[0].replace("searchTagFilter:", "").strip() if parts else None
        query_text = parts[1].strip() if len(parts) > 1 else ""

    domain_context = state.get("domain_context") or {}
    domain_context.update({"last_query": query_text})

    logger.info(
        "[parse_input_node] parsed query ok | tag=%s | query=%s",
        tag,
        query_text,
    )
    return {**state, "parsed_query": query_text, "tag": tag, "domain_context": domain_context}


async def rewrite_query_node(state: RAGState) -> RAGState:
    """查询改写（非流式）

    关键点（修复你现在的“改写内容被前端输出”的问题）：
    - 本节点**只使用 ainvoke**（非流式），因此不会产生 on_chat_model_stream 事件。
    - 改写结果写入 state.rewritten_query，供后续检索使用。
    """
    query_text = state.get("parsed_query") or state.get("raw_input") or ""
    logger.info("[rewrite_query_node] start | query_len=%s", len(query_text))

    if not _llm_service:
        logger.error("[rewrite_query_node] llm_service not injected, fallback to original query")
        return {**state, "rewritten_query": query_text}

    global _rewrite_prompt
    if _rewrite_prompt is None:
        _rewrite_prompt = _load_prompt("rewrite_query.md")
        logger.info("[rewrite_query_node] rewrite prompt loaded")

    llm = _llm_service.get_model(temperature=0.1)
    messages = [
        SystemMessage(content=_rewrite_prompt),
        HumanMessage(content=f"原始问题：{query_text}"),
    ]

    rewritten_query = query_text
    try:
        resp = await llm.ainvoke(messages)
        content = _llm_service.clean_response(resp.content)
        rewritten_query = (content or "").strip() or query_text
        logger.info(
            "[rewrite_query_node] rewrite ok | original=%s | rewritten=%s",
            query_text,
            rewritten_query,
        )
    except Exception as e:
        logger.warning("[rewrite_query_node] rewrite failed, fallback | err=%s", e, exc_info=True)
        rewritten_query = query_text

    domain_context = state.get("domain_context") or {}
    domain_context.update({"last_query": rewritten_query})

    return {**state, "rewritten_query": rewritten_query, "domain_context": domain_context}


async def req_search_node(state: RAGState) -> RAGState:
    """调用检索接口，将结果写入 retrieved，并构造 references

    需求对齐：
    - **retrieved**：接口返回内容存进 retrieved（原样/最小加工）。
    - **references**：把“拼接/整理后的结果”存进 references（结构化整理）。
    """
    query_text = state.get("rewritten_query") or state.get("parsed_query") or state.get("raw_input") or ""
    tag = state.get("tag")

    logger.info(
        "[req_search_node] start | query=%s | tag=%s",
        query_text,
        tag,
    )

    if not _req_client:
        logger.error("[req_search_node] req_client not injected, skip search")
        return {**state, "retrieved": [], "references": [], "error": "req_client_not_injected"}

    retrieved: List[RetrievedSlice] = []
    try:
        retrieved = await _req_client.search(query_text, tag)
        logger.info("[req_search_node] search ok | retrieved_count=%s", len(retrieved))
        logger.debug("[req_search_node] retrieved_preview=%s", (retrieved[:2] if retrieved else []))
    except Exception as e:
        logger.error("[req_search_node] search failed | err=%s", e, exc_info=True)
        return {**state, "retrieved": [], "references": [], "error": f"search_failed:{e}"}

    references = _build_references_from_retrieved(retrieved)
    logger.info("[req_search_node] references built | references_count=%s", len(references))

    return {**state, "retrieved": retrieved, "references": references}


async def compose_answer_node(state: RAGState) -> RAGState:
    """生成回答（支持 RAG 与 fallback）

    行为：
    - 有检索结果：使用 answer_with_refs.md + 检索切片生成回答（流式，供 agent 层透传）。
    - 无检索结果/检索异常：走 llm_fallback，用通识能力直接回答（流式）。

    注意：
    - 这里不负责拼接参考来源卡片（为了让 agent 层能控制“回答结束后再输出参考来源”）。
    - 这里也不输出任何“改写后的问题”到前端，只用于上下文输入。
    """
    if not _llm_service:
        logger.error("[compose_answer_node] llm_service not injected")
        return {**state, "answer": "系统错误：LLM 服务不可用", "answer_source": "llm_fallback", "can_answer": False}

    raw_q = state.get("raw_input") or ""
    rewritten = state.get("rewritten_query") or state.get("parsed_query") or raw_q
    retrieved: List[RetrievedSlice] = state.get("retrieved") or []
    has_kb = bool(retrieved)

    logger.info(
        "[compose_answer_node] start | has_kb=%s | retrieved_count=%s | err_flag=%s",
        has_kb,
        len(retrieved),
        state.get("error"),
    )

    # ========== fallback：无检索结果或检索异常 ==========
    if not has_kb:
        llm = _llm_service.get_model(temperature=0.1)
        messages = [
            HumanMessage(
                content=(
                    f"用户原始问题：{raw_q}\n"
                    f"改写后的问题：{rewritten}\n"
                    f"说明：未检索到可用知识库内容，请使用通识能力回答。"
                )
            )
        ]

        # 使用流式调用，确保 agent.stream 能从 graph.astream_events 捕获 on_chat_model_stream
        resp_content = ""
        try:
            async for chunk in llm.astream(messages):
                if hasattr(chunk, "content") and chunk.content:
                    resp_content += chunk.content
            answer = _llm_service.clean_response(resp_content)
        except Exception as e:
            logger.warning("[compose_answer_node] fallback stream failed, try ainvoke | err=%s", e, exc_info=True)
            resp = await llm.ainvoke(messages)
            answer = _llm_service.clean_response(resp.content)

        return {
            **state,
            "answer": answer,
            "answer_source": "llm_fallback",
            "can_answer": True,
            "fallback_reason": state.get("error") or "未检索到相关内容",
        }

    # ========== RAG：有检索结果 ==========
    global _answer_prompt
    if _answer_prompt is None:
        _answer_prompt = _load_prompt("answer_with_refs.md")
        logger.info("[compose_answer_node] answer prompt loaded")

    # 将检索切片以更友好的格式拼入 prompt（便于模型专注使用）
    slices_lines: List[str] = []
    for idx, item in enumerate(retrieved, start=1):
        title = item.get("title", "")
        content = item.get("content", item.get("para", ""))
        slices_lines.append(f"[{idx}] {title}\n{content}")
    slices_text = "\n\n".join(slices_lines)

    llm = _llm_service.get_model(temperature=0.2)
    messages = [
        SystemMessage(content=_answer_prompt),
        HumanMessage(
            content=(
                f"用户原始问题：{raw_q}\n"
                f"改写后的问题：{rewritten}\n"
                f"检索切片：\n{slices_text}"
            )
        ),
    ]

    resp_content = ""
    try:
        async for chunk in llm.astream(messages):
            if hasattr(chunk, "content") and chunk.content:
                resp_content += chunk.content
        answer = _llm_service.clean_response(resp_content)
    except Exception as e:
        logger.warning("[compose_answer_node] rag stream failed, try ainvoke | err=%s", e, exc_info=True)
        resp = await llm.ainvoke(messages)
        answer = _llm_service.clean_response(resp.content)

    return {
        **state,
        "answer": answer,
        "answer_source": "kb",
        "can_answer": True,
        "fallback_reason": None,
    }

