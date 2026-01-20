import logging
import os
import re
from typing import Any, Dict, List
import json

from langchain_core.messages import SystemMessage, HumanMessage
from pandas.core.arrays.arrow import ListAccessor
from pyexpat.errors import messages

from .state import RAGState

logger = logging.getLogger(__name__)

_llm_service = None
_req_client = None
_rewrite_prompt = None
_answer_prompt = None

def _load_prompt(file_name: str) -> str:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    prompt_path = os.path.join(base_dir, "prompts", file_name)
    with open(prompt_path, "r", encoding="utf-8") as f:
        return f.read()

def set_llm_service(llm_service):
    global _llm_service
    _llm_service = llm_service

def set_req_client(req_client):
    global _req_client
    _req_client = req_client


async def parse_input_node(state: RAGState) -> RAGState:
    """解析输入中的query与tag
    1) searchTagFilter:xxx, query:yyy
    2) yyy
    """
    raw_text = state.get("raw_input").strip()
    if raw_text.startswith("searchTagFilter:"):
        parts = raw_text.split(", query:", 1)
        tag = parts[0].replace("searchTagFilter:", "").strip()
        query_text = parts[1].strip()
    else:
        query_text = raw_text
        tag = None

    domain_context = {"last_query":query_text}

    logger.info("[parse_input_node]tag=%s | query=%s",tag,query_text)
    return {**state, "parsed_query": query_text, "tag": tag, "domain_context": domain_context}

async def rewrite_query_node(state: RAGState) -> RAGState:
    """查询改写"""
    logger.info("[rewrite_query_node]正在执行")
    query_text = state.get("parsed_query") or state.get("raw_input") or ""

    if not _llm_service:
        logger.error("[rewrite_query_node]LLM服务未设置")
        return {**state, "rewritten_query": query_text}
    global _rewrite_prompt
    if _rewrite_prompt is None:
        _rewrite_prompt = _load_prompt("rewrite_query.md")

    llm = _llm_service.get_model(temperature=0.1)
    messages = [
        SystemMessage(content=_rewrite_prompt),
        HumanMessage(content=f"原始问题：{query_text}")
    ]

    try:
        resp = await llm.ainvoke(messages)
        content = _llm_service.clean_response(resp.content)
        rewritten_query = content.strip()
        logger.info("已将查询改写为：%s",rewritten_query)
    except Exception as e:
        logger.warning("[rewrite_query_node]改写失败使用原始查询，：%s", e)
        rewritten_query = query_text

    domain_context = state.get("domain_context") or {}
    domain_context.update({"last_query": rewritten_query})

    return {
        **state,
        "rewritten_query": rewritten_query,
        "domain_context": domain_context
    }


async def req_search_node(state: RAGState) -> RAGState:
    """调用接口，拼接返回的结果，存进retrieved里"""
    logger.info("[req_search_node]==========正在调用检索接口==========")

    query_text = state.get("rewritten_query") or state.get("parsed_query") or state.get("raw_input") or ""
    tag = state.get("tag")

    if not _req_client:
        logger.error("[req_search_node]req_client服务未设置")
        return {**state, "retrieved":[]}

    slices = await _req_client.search(query_text, tag)
    logger.debug("[req_search_node]检索的结果：%s", slices)
    return {**state, "retrieved": slices}



async def preprocess_results_node(state: RAGState) -> RAGState:
    """对检索结果进行简单预处理，格式重组之类，（index、title、nid、snippet）
    想根据retrieved生成references。
    没用了，因为上一个节点已经没有nid了，保留这个节点是为了后续去重。
    （1.4更新，已经去重了，这个节点应该可以删除了）
    """
    logger.debug("[preprocess_results_node]==========正在对检索的结果进行简单处理==========")
    retrieved = state.get("retrieved") or []
    references = []
    for idx, item in enumerate(retrieved,start=1):
        references.append(
            {
                "index": idx,
                "title": item.get("title"),
                "nid": item.get("nid"),
                "snippet": item.get("para")
            }
        )
    return {**state,"references": references, "retrieved": retrieved}
async def judge_answerable_node(state: RAGState) -> RAGState:
    """判断是否能回答，可能取消该节点, 暂时为简易实现,不调大模型
    如果有检索内容，则回答来源为kb，否则为llm_fallback
    """
    can_answer = bool(state.get("retrieved"))
    answer_source = "kb" if can_answer else "llm_fallback"
    fallback_reason = None if can_answer else "未检索到相关内容"
    # 记录 retrieved 的简要信息，便于排查中间状态是否丢失
    try:
        retrieved_preview = state.get("retrieved")
        logger.debug("[judge_answerable_node] retrieved count=%s, sample=%s", len(retrieved_preview) if retrieved_preview else 0, (retrieved_preview[:2] if retrieved_preview else []))
    except Exception:
        logger.debug("[judge_answerable_node] 无法获取 retrieved 预览")
    logger.debug("[judge_answerable_node]正在执行，answer_source=%s", answer_source)
    return {
        **state,
        "can_answer": can_answer,
        "fallback_reason": fallback_reason,
        "answer_source": answer_source
    }
async def compose_answer_node(state: RAGState) -> RAGState:
    """生成带参考来源的回答"""
    logger.debug("[compose_answer_node]==========正在生成回答==========")

    answer_source = state.get("answer_source")
    query_text = state.get("raw_input") or ""
    rewritten = state.get("rewritten_query") or query_text

    if answer_source == "llm_fallback":
        llm = _llm_service.get_model(temperature=0.1)
        messages = [HumanMessage(
            content=(
                f"用户原始问题：{query_text}\n"
                f"改写后的问题：{rewritten}\n"
            )
           )]

        # 使用流式调用以支持astream_events
        resp_content = ""
        try:
            async for chunk in llm.astream(messages):
                if hasattr(chunk, "content") and chunk.content:
                    resp_content += chunk.content
        except Exception as e:
            logger.warning(f"[compose_answer_node] 流式调用失败: {e}")
            # 回退到普通调用
            resp = await llm.ainvoke(messages)
            resp_content = resp.content
            
        answer = _llm_service.clean_response(resp_content)
        # 保持原始的 retrieved 信息，不要在回退路径中清空，便于后续处理和记录参考来源
        logger.debug("[compose_answer_node] llm_fallback, preserved retrieved count=%s", len(state.get("retrieved") or []))
        return {
            **state,
            "answer": answer,
            "references": state.get("references") or [],
            "retrieved": state.get("retrieved") or [],
            "answer_source": "llm_fallback"
        }

    retrieved:List[dict] = state.get("retrieved")

    global _answer_prompt
    if _answer_prompt is None and _llm_service:
        _answer_prompt = _load_prompt("answer_with_refs.md")

    llm = _llm_service.get_model(temperature=0.2)
    messages = [
        SystemMessage(content=_answer_prompt),
        HumanMessage(
            content=(
                f"用户原始问题：{query_text}\n"
                f"改写后的问题：{rewritten}\n"
                f"检索切片：\n{retrieved}"
            )
        )
    ]

    try:
        # 使用流式调用以支持astream_events
        resp_content = ""
        async for chunk in llm.astream(messages):
            if hasattr(chunk, "content") and chunk.content:
                resp_content += chunk.content
        answer = _llm_service.clean_response(resp_content)
    except Exception as e:
        logger.warning("[compose_answer_node] 流式调用失败，回退到普通调用: %s", e)
        try:
            resp = await llm.ainvoke(messages)
            answer = _llm_service.clean_response(resp.content)
        except Exception as e2:
            logger.warning("[compose_answer_node] 普通调用也失败，使用参考文段代替: %s", e2)
            answer = retrieved or "未检索到相关内容"

    return {**state, "answer": answer, "answer_source": "kb", "retrieved": retrieved}
