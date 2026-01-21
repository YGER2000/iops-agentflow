import json
import logging
from typing import Dict, Any, AsyncGenerator, Optional, List

from langgraph.graph import StateGraph
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

from app.agents.base import AgentBase
from app.core.chat_history import get_chat_history_manager
from app.core.models import SharedConversationHistory

from .graph import build_rag_graph
from .state import RAGState, RetrievedSlice

# 检索客户端（本目录自包含实现，避免依赖任何“旧目录”）
from .services.req_client import ReqSearchClient

logger = logging.getLogger(__name__)


def _build_references_card_from_retrieved(retrieved: List[RetrievedSlice]) -> str:
    """将 retrieved 构建为前端可渲染的参考来源卡片

    注意：这里严格按你的要求保留原有拼接逻辑与格式，只是从 state 中取数据。
    """
    reference_content = []
    for i, ref in enumerate(retrieved or [], 1):
        title = ref.get("title", "")
        content = ref.get("content", ref.get("para", ""))
        reference_content.append(f"\n\n:::modal [{i}]{title}\n{content}\n\n:::\n\n")

    references_str = "\n".join(reference_content)
    references_part = f"\n\n:::card 参考来源\n{references_str}\n:::"
    return references_part


class RAGAgent(AgentBase):
    """RAG 问答智能体

    设计原则：
    - 持久化/历史对话逻辑与 `common_qa` 保持一致，避免出现“一个智能体一套逻辑”的维护灾难。
    - 图/节点尽量简洁，最大化复用既有组件（ReqSearchClient、提示词文件等）。
    - 流式输出修复：只流式输出回答正文；回答完成后再追加参考来源卡片；不再输出改写查询。
    """

    def __init__(self):
        super().__init__(
            name="rag_agent",
            description="基于检索增强生成的问答智能体，支持输入标签进行过滤检索，支持流式回答与参考来源输出。"
        )
        self._graph: Optional[StateGraph] = None
        self._req_client: Optional[ReqSearchClient] = None
        self.chat_history = None  # 延迟初始化（异步）
        self._system_prompt: Optional[str] = None

    async def _ensure_chat_history(self) -> None:
        """确保 chat_history 已初始化"""
        if self.chat_history is None:
            self.chat_history = await get_chat_history_manager()
            logger.info("[agent] chat_history initialized")

    @property
    def system_prompt(self) -> str:
        """懒加载系统提示词"""
        if self._system_prompt is None:
            self._system_prompt = self.load_prompt("system.md")
            logger.info("[agent] system prompt loaded")
        return self._system_prompt

    @property
    def req_client(self) -> ReqSearchClient:
        """懒加载检索客户端"""
        if self._req_client is None:
            self._req_client = ReqSearchClient(
                base_url=self.config.get("RAG_AGENT_BASE_URL"),
                user_id=self.config.get("RAG_AGENT_USER_ID"),
                timeout_seconds=8,
            )
            logger.info(
                "[agent] req_client initialized | base_url=%s | user_id=%s",
                self.config.get("RAG_AGENT_BASE_URL"),
                self.config.get("RAG_AGENT_USER_ID"),
            )
        return self._req_client

    def build_graph(self) -> StateGraph:
        """构建并编译图（只做一次）"""
        if self._graph is None:
            logger.info("[agent] build_graph (compile) start")
            self._graph = build_rag_graph(
                llm_service=self.llm,
                req_client=self.req_client,
            ).compile()
            logger.info("[agent] build_graph (compile) done")
        return self._graph

    async def invoke(self, message: str, thread_id: str, context: Dict[str, Any] = None) -> str:
        """非流式调用

        API 层当前声明 `response_model=str`，所以这里保持返回 string（与现有系统兼容）。
        """
        context = context or {}
        await self._ensure_chat_history()

        is_new_conversation = context.get("is_new_conversation", False)
        logger.info(
            "[invoke] start | thread_id=%s | is_new_conversation=%s | has_tag=%s",
            thread_id,
            is_new_conversation,
            bool(context.get("tag")),
        )

        # ========== 持久化用户消息（共享表） ==========
        try:
            async with self.mysql.get_session() as session:
                user_msg = SharedConversationHistory(
                    thread_id=thread_id,
                    agent_name=self.name,
                    role="user",
                    content=message,
                    extra_metadata=json.dumps(context) if context else None,
                )
                session.add(user_msg)
                await session.commit()
            logger.info("[invoke] MySQL saved user message")
        except Exception as e:
            logger.error("[invoke] MySQL save user message failed | err=%s", e, exc_info=True)

        # ========== 历史消息（与 common_qa 一致） ==========
        if is_new_conversation:
            history_messages = []
            logger.info("[invoke] new conversation: skip history loading")
        else:
            history_messages = await self.chat_history.get_messages(thread_id)
            logger.info("[invoke] history loaded | count=%s", len(history_messages))

        if not history_messages:
            history_messages = [SystemMessage(content=self.system_prompt)]

        # ========== 图调用 ==========
        initial_state: RAGState = {
            "agent_config": self.config,
            "domain_context": None,
            "raw_input": message,
            "tag": context.get("tag"),
            "parsed_query": None,
            "rewritten_query": None,
            "retrieved": [],
            "references": [],
            "metadata": {"thread_id": thread_id},
            "history_messages": history_messages,
        }

        graph = self.get_graph()
        result_state = await graph.ainvoke(initial_state)

        answer = (result_state.get("answer") or "").strip()
        retrieved = result_state.get("retrieved") or []

        # 拼接参考来源（保持你的原始格式）
        if retrieved:
            references_part = _build_references_card_from_retrieved(retrieved)
            formatted_message = f"\n{answer}{references_part}"
        else:
            formatted_message = f"\n{answer}"

        logger.info(
            "[invoke] graph done | answer_len=%s | retrieved_count=%s | answer_source=%s",
            len(answer),
            len(retrieved),
            result_state.get("answer_source"),
        )

        # ========== 保存 Redis 历史（与 common_qa 一致） ==========
        try:
            await self.chat_history.add_message(thread_id, HumanMessage(content=message))
            await self.chat_history.add_message(thread_id, AIMessage(content=formatted_message))
            logger.info("[invoke] redis history saved")
        except Exception as e:
            logger.warning("[invoke] redis history save failed | err=%s", e, exc_info=True)

        # ========== 持久化 AI 回复（共享表） ==========
        try:
            async with self.mysql.get_session() as session:
                ai_msg = SharedConversationHistory(
                    thread_id=thread_id,
                    agent_name=self.name,
                    role="assistant",
                    content=formatted_message,
                    extra_metadata=json.dumps(
                        {
                            "tag": context.get("tag"),
                            "rewritten_query": result_state.get("rewritten_query"),
                            "can_answer": result_state.get("can_answer"),
                            "answer_source": result_state.get("answer_source"),
                            "fallback_reason": result_state.get("fallback_reason"),
                        },
                        ensure_ascii=False,
                    ),
                )
                session.add(ai_msg)
                await session.commit()
            logger.info("[invoke] MySQL saved assistant message")
        except Exception as e:
            logger.error("[invoke] MySQL save assistant message failed | err=%s", e, exc_info=True)

        return formatted_message

    async def stream(self, message: str, thread_id: str, context: Dict[str, Any] = None) -> AsyncGenerator[Dict[str, Any], None]:
        """流式调用

        关键修复点：
        - rewrite_query 节点是非流式（ainvoke），因此不会产生 on_chat_model_stream → 不会把“改写查询”流到前端。
        - 只有 compose_answer 节点使用 streaming → 前端只看到答案 token。
        - 当图执行结束（on_end）后，**立刻输出参考来源卡片**（type=message）。
        """
        context = context or {}
        await self._ensure_chat_history()

        is_new_conversation = context.get("is_new_conversation", False)
        logger.info(
            "[stream] start | thread_id=%s | is_new_conversation=%s",
            thread_id,
            is_new_conversation,
        )

        # ========== 持久化用户消息（共享表） ==========
        try:
            async with self.mysql.get_session() as session:
                user_msg = SharedConversationHistory(
                    thread_id=thread_id,
                    agent_name=self.name,
                    role="user",
                    content=message,
                    extra_metadata=json.dumps(context) if context else None,
                )
                session.add(user_msg)
                await session.commit()
            logger.info("[stream] MySQL saved user message")
        except Exception as e:
            logger.error("[stream] MySQL save user message failed | err=%s", e, exc_info=True)

        # ========== 历史消息 ==========
        if is_new_conversation:
            history_messages = []
            logger.info("[stream] new conversation: skip history loading")
        else:
            history_messages = await self.chat_history.get_messages(thread_id)
            logger.info("[stream] history loaded | count=%s", len(history_messages))

        if not history_messages:
            history_messages = [SystemMessage(content=self.system_prompt)]

        initial_state: RAGState = {
            "agent_config": self.config,
            "domain_context": None,
            "raw_input": message,
            "tag": context.get("tag"),
            "parsed_query": None,
            "rewritten_query": None,
            "retrieved": [],
            "references": [],
            "metadata": {"thread_id": thread_id},
            "history_messages": history_messages,
        }

        graph = self.get_graph()
        full_answer = ""
        final_state: Optional[Dict[str, Any]] = None

        try:
            async for event in graph.astream_events(initial_state, version="v2"):
                evt_type = event.get("event")
                evt_data = event.get("data") or {}

                # 详细日志：用于排查事件流结构与最终 output 是否包含 retrieved/references
                # try:
                #     if evt_type in ("on_chat_model_stream", "on_end"):
                #         logger.debug(
                #             "[stream] event=%s | data_keys=%s",
                #             evt_type,
                #             list(evt_data.keys()) if isinstance(evt_data, dict) else None,
                #         )
                # except Exception:
                #     pass

                # ========== 透传模型 token ==========
                if evt_type == "on_chat_model_stream":
                    chunk = evt_data.get("chunk")
                    if chunk is None:
                        continue
                    content = getattr(chunk, "content", None)
                    if content:
                        full_answer += content
                        yield {"type": "message", "data": content}

                # ========== 获取最终状态 ==========
                if evt_type == "on_end":
                    final_state = evt_data.get("output") if isinstance(evt_data, dict) else None
                    if isinstance(final_state, dict):
                        logger.info(
                            "[stream] on_end | keys=%s | retrieved_count=%s",
                            list(final_state.keys()),
                            len(final_state.get("retrieved") or []),
                        )
                    else:
                        logger.warning("[stream] on_end without dict output | output_type=%s", type(final_state))

            # ========== 回答结束后，追加参考来源 ==========
            retrieved = (final_state or {}).get("retrieved") or []
            references_part = ""
            if retrieved:
                references_part = _build_references_card_from_retrieved(retrieved)
                # 注意：必须保持 type 只有 message（按你的约束）
                yield {"type": "message", "data": references_part}

            # ========== 保存历史与持久化 ==========
            formatted_message = f"\n{full_answer}{references_part}" if references_part else f"\n{full_answer}"

            try:
                await self.chat_history.add_message(thread_id, HumanMessage(content=message))
                await self.chat_history.add_message(thread_id, AIMessage(content=formatted_message))
                logger.info("[stream] redis history saved")
            except Exception as e:
                logger.warning("[stream] redis history save failed | err=%s", e, exc_info=True)

            try:
                async with self.mysql.get_session() as session:
                    ai_msg = SharedConversationHistory(
                        thread_id=thread_id,
                        agent_name=self.name,
                        role="assistant",
                        content=formatted_message,
                        extra_metadata=json.dumps(
                            {
                                "tag": context.get("tag"),
                                "rewritten_query": (final_state or {}).get("rewritten_query"),
                                "can_answer": (final_state or {}).get("can_answer"),
                                "answer_source": (final_state or {}).get("answer_source"),
                                "fallback_reason": (final_state or {}).get("fallback_reason"),
                            },
                            ensure_ascii=False,
                        ),
                    )
                    session.add(ai_msg)
                    await session.commit()
                logger.info("[stream] MySQL saved assistant message")
            except Exception as e:
                logger.error("[stream] MySQL save assistant message failed | err=%s", e, exc_info=True)

            # ========== 输出元数据 ==========
            yield {
                "type": "metadata",
                "data": {
                    "thread_id": thread_id,
                    "can_answer": (final_state or {}).get("can_answer"),
                    "answer_source": (final_state or {}).get("answer_source"),
                    "fallback_reason": (final_state or {}).get("fallback_reason"),
                },
            }

        except Exception as e:
            logger.error("[stream] LangGraph stream failed | err=%s", e, exc_info=True)
            yield {"type": "error", "data": str(e)}

