import logging
import json
from typing import Dict, Any, AsyncGenerator
from langgraph.graph import StateGraph
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

from app.agents.base import AgentBase
from app.schemas.agent import AgentResponse
from app.core.chat_history import get_chat_history_manager
from .graph import build_rag_graph
from .state import RAGState
from .services.req_client import ReqSearchClient
from .services.message_formatter import format_response_message

from app.core.models import SharedConversationHistory

logger = logging.getLogger(__name__)


class RAGAgent(AgentBase):
    """通识问答智能体"""

    def __init__(self):
        super().__init__(
            name="rag_agent",
            description="基于检索增强生成的问答智能体，支持输入标签进行过滤检索。"
        )
        self._graph: StateGraph | None = None
        self._req_client: ReqSearchClient | None = None
        self.chat_history = None
        self._system_prompt: str | None = None

    async def _ensure_chat_history(self):
        """确保 chat_history 已初始化"""
        if self.chat_history is None:
            self.chat_history = await get_chat_history_manager()
    
    @property
    def system_prompt(self):
        """懒加载系统提示词"""
        # 原始
        if self._system_prompt is None:
            self._system_prompt = self.load_prompt("system.md")
        return self._system_prompt

    @property
    def req_client(self) -> ReqSearchClient:
        if self._req_client is None:
            self._req_client = ReqSearchClient(
                base_url="",
                timeout_seconds=8
            )
        return self._req_client

    def build_graph(self) -> StateGraph:
        """构建图"""
        if self._graph is None:
            self._graph = build_rag_graph(
                llm_service=self.llm,
                req_client=self.req_client
            ).compile()
        return self._graph

    async def invoke(
            self,
            message: str,
            thread_id: str,
            context: Dict[str, Any] = None
    ) -> str:
        """调用智能体"""
        context = context or {}     # 默认为空字典
        # 确保 chat_history 已初始化
        await self._ensure_chat_history()
        logger.debug(f"========== 传入的content:{context} ==============")
        is_new_conversation = context.get('is_new_conversation', False)
        # ========== 持久化用户消息（共享表） ==========
        # MySQL: 保存用户消息到共享表
        try:
            mysql = self.get_service("mysql")
            if mysql:
                async with mysql.get_session() as session:
                    user_msg = SharedConversationHistory(
                        thread_id=thread_id,
                        agent_name=self.name,  # 使用 agent_name 区分不同智能体
                        role="user",
                        content=message,
                        extra_metadata=json.dumps({"tag": context.get("tag")}) if context.get("tag") else None
                    )
                    session.add(user_msg)
                    await session.commit()
                    logger.debug("MySQL: 用户消息已保存到共享表")
        except Exception as e:
            logger.error(f"MySQL 保存用户消息失败: {e}")

        if is_new_conversation:
            history_messages = []
            logger.debug(f"新对话 (thread_id={thread_id})，跳过历史消息查询")

        else:
            history_messages = await self.chat_history.get_messages(thread_id)


        initial_state: RAGState = {
            "agent_config": self.config,
            "domain_context": None,
            "raw_input": message,
            "tag": context.get("tag") if context else None,
            "parsed_query": None,
            "rewritten_query": None,
            "retrieved": [],
            "references": [],
            "metadata": {"thread_id": thread_id},
            "history_messages": history_messages,
        }

        # ========== 原有逻辑 ==========
        graph = self.get_graph()
        result_state = await graph.ainvoke(initial_state)

        answer = result_state.get("answer")
        #references = result_state.get("references") or  []
        retrieved = result_state.get("retrieved") or []
        # response_data = {
        #     "rewritten_query": result_state.get("rewritten_query"),
        #     "references": references,
        #     "retrieved": result_state.get("retrieved") or [],
        #     "answer_source": result_state.get("answer_source"),
        #     "tag": result_state.get("tag"),
        # }

        # 调用拼接服务，拼接answer和retrieved
        formatted_message = format_response_message(answer, retrieved)

        try:
            await self.chat_history.add_message(thread_id, AIMessage(content=formatted_message))
        except Exception as e:
            logger.warning(f"写入会话历史失败(ai): {e}")

        # ========== 持久化AI回复（共享表） ==========
        # MySQL: 保存AI回复到共享表
        try:
            mysql = self.get_service("mysql")
            if mysql:
                async with mysql.get_session() as session:
                    ai_msg = SharedConversationHistory(
                        thread_id=thread_id,
                        agent_name=self.name,  # 使用 agent_name 区分不同智能体
                        role="assistant",
                        content=formatted_message,  # 使用拼接后的消息
                        extra_metadata=json.dumps(
                            {
                                "tag": context.get("tag"),
                                "rewritten_query": result_state.get("rewritten_query"),
                                "can_answer": result_state.get("can_answer")
                            }
                        )
                    )
                    session.add(ai_msg)
                    await session.commit()
                    logger.debug("MySQL: AI回复已保存到共享表")
        except Exception as e:
            logger.error(f"MySQL 保存AI回复失败: {e}")

        # return AgentResponse(
        #     message=answer,
        #     thread_id=thread_id,
        #     need_user_action=False,
        #     data=response_data,
        #     metadata={
        #         "can_answer": result_state.get("can_answer"),
        #         "fallback_reason": result_state.get("fallback_reason"),
        #         "answer_source": result_state.get("answer_source"),
        #     }
        # )
        return formatted_message

    async def stream(
            self,
            message: str,
            thread_id: str,
            context: Dict[str, Any] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """流式调用智能体 - 只流式输出最终格式化消息"""
        # 确保 chat_history 已初始化
        await self._ensure_chat_history()

        # ========== 持久化用户消息（共享表） ==========
        try:
            mysql = self.get_service("mysql")
            if mysql:
                async with mysql.get_session() as session:
                    user_msg = SharedConversationHistory(
                        thread_id=thread_id,
                        agent_name=self.name,
                        role="user",
                        content=message,
                        extra_metadata=json.dumps(context) if context else None
                    )
                    session.add(user_msg)
                    await session.commit()
                    logger.debug("MySQL: 用户消息已保存到共享表（流式）")
        except Exception as e:
            logger.error(f"MySQL 保存用户消息失败（流式）: {e}")

        # ========== 原有逻辑 ==========
        # 获取历史消息
        is_new_conversation = context and context.get('is_new_conversation', False)
        if is_new_conversation:
            history_messages = []
            logger.debug(f"新对话 (thread_id={thread_id})，跳过历史消息查询（流式）")
        else:
            history_messages = await self.chat_history.get_messages(thread_id)

        # 如果是首次对话，添加系统提示词
        if not history_messages:
            history_messages = [SystemMessage(content=self.system_prompt)]

        # 添加当前用户消息
        current_message = HumanMessage(content=message)
        messages = history_messages + [current_message]

        graph = self.get_graph()

        try:
            # 执行完整处理流程（与invoke方法一致）
            initial_state: RAGState = {
                "agent_config": self.config,
                "domain_context": None,
                "raw_input": message,
                "tag": context.get("tag") if context else None,
                "parsed_query": None,
                "rewritten_query": None,
                "retrieved": [],
                "references": [],
                "metadata": {"thread_id": thread_id},
                "history_messages": history_messages,
            }

            result_state = await graph.ainvoke(initial_state)

            answer = result_state.get("answer")
            retrieved = result_state.get("retrieved") or []

            # 调用拼接服务，拼接answer和retrieved
            formatted_message = format_response_message(answer, retrieved)

            # 流式输出最终格式化消息
            # 将格式化消息按字符流式输出
            for char in formatted_message:
                yield {
                    "type": "message",
                    "data": char
                }

            # 保存对话历史到 Redis
            await self.chat_history.add_message(thread_id, current_message)
            await self.chat_history.add_message(thread_id, AIMessage(content=formatted_message))

            # ========== 持久化AI回复（共享表） ==========
            try:
                mysql = self.get_service("mysql")
                if mysql:
                    async with mysql.get_session() as session:
                        ai_msg = SharedConversationHistory(
                            thread_id=thread_id,
                            agent_name=self.name,
                            role="assistant",
                            content=formatted_message,
                            extra_metadata=json.dumps({
                                "tag": context.get("tag") if context else None,
                                "rewritten_query": result_state.get("rewritten_query"),
                                "can_answer": result_state.get("can_answer")
                            })
                        )
                        session.add(ai_msg)
                        await session.commit()
                        logger.debug("MySQL: AI回复已保存到共享表（流式）")
            except Exception as e:
                logger.error(f"MySQL 保存AI回复失败（流式）: {e}")

            # 发送元数据
            yield {
                "type": "metadata",
                "data": {
                    "thread_id": thread_id,
                    "can_answer": result_state.get("can_answer"),
                    "answer_source": result_state.get("answer_source"),
                    "fallback_reason": result_state.get("fallback_reason")
                }
            }

        except Exception as e:
            logger.error(f"LangGraph流式调用失败（流式）: {e}")
            yield {
                "type": "error",
                "data": str(e)
            }