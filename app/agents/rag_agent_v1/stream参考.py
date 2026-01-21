from typing import Dict, Any, AsyncGenerator
from langgraph.graph import StateGraph
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from app.agents.base import AgentBase
from app.schemas.agent import AgentResponse
from app.core.chat_history import get_chat_history_manager
from .graph import build_ombs_exceptidentify_graph
from app.core.logger import get_logger

logger = get_logger(__name__)


class OmbsExceptIdentifyAgent(AgentBase):
    """蓝图架构图异常识别及分析智能体"""

    def __init__(self):
        super().__init__(
            name="ombs_exceptidentify_agent",
            description="运维蓝图-架构图异常识别智能体,对运维蓝图的架构图进行异常识别，判断是否存在告警，并对告警进行分析"
        )
        self.chat_history = None  # 延迟初始化（异步）
        # 提示词将在首次使用时加载（因为需要 agent_dir）
        self._system_prompt = None

    async def _ensure_chat_history(self):
        """确保 chat_history 已初始化"""
        if self.chat_history is None:
            self.chat_history = await get_chat_history_manager()

    @property
    def system_prompt(self):
        """懒加载系统提示词"""
        if self._system_prompt is None:
            self._system_prompt = self.load_prompt("system.md")
        return self._system_prompt

    def build_graph(self) -> StateGraph:
        """构建图"""
        # 传入 LLM 服务以便 graph 节点使用
        workflow = build_ombs_exceptidentify_graph(llm_service=self.llm, custom_config=self.config)
        # 不再使用checkpointer，直接编译
        return workflow.compile()

    async def invoke(
            self,
            message: str,
            thread_id: str,
            context: Dict[str, Any] = None
    ) -> AgentResponse:
        """调用智能体"""
        # 确保 chat_history 已初始化
        await self._ensure_chat_history()

        # ========== 原有逻辑 ==========
        graph = self.get_graph()

        # 获取历史消息
        # 优化：如果是新对话（第一次调用），直接使用空列表，避免不必要的数据库查询
        logger.debug(f"========== 传入的content:{context} ==============")
        is_new_conversation = context and context.get('is_new_conversation', False)

        if is_new_conversation:
            history_messages = []
            logger.debug(f"新对话 (thread_id={thread_id})，跳过历史消息查询")
        else:
            history_messages = await self.chat_history.get_messages(thread_id)
        logger.debug("========= 1. 获取历史对话信息： 完成 =========")

        # 获取传入的图片路径
        # req_parm = context.get('thread_id', '')

        # 如果是首次对话，添加系统提示词
        if not history_messages:
            history_messages = [SystemMessage(content=self.system_prompt)]

        # 添加当前用户消息
        current_message = HumanMessage(content=message)
        messages = history_messages + [current_message]

        # 调用图
        result = await graph.ainvoke(
            {"messages": messages}
        )
        logger.debug("========= 2. 调用图信息： 完成 =========")

        # 获取最后的 AI 响应
        last_message = result["messages"][-1]
        logger.debug("========= 3. 获取AI响应信息： 完成 =========")

        # 清理响应内容中的 thinking 标签
        cleaned_content = self.llm.clean_response(last_message.content)

        # 保存对话历史到 Redis（保存用户消息和清理后的AI响应）
        await self.chat_history.add_message(thread_id, current_message)
        cleaned_message = AIMessage(content=cleaned_content)
        await self.chat_history.add_message(thread_id, cleaned_message)
        logger.debug("========= 4. 保存对话信息到Redis： 完成 =========")

        return AgentResponse(
            message=cleaned_content,
            thread_id=thread_id,
            need_user_action=False
        )

    async def stream(
            self,
            message: str,
            thread_id: str,
            context: Dict[str, Any] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """流式调用智能体"""
        # 确保 chat_history 已初始化
        await self._ensure_chat_history()

        # ========== 持久化用户消息（共享表） ==========
        # MySQL: 保存用户消息到共享表
        # try:
        #     async with self.mysql.get_session() as session:
        #         user_msg = SharedConversationHistory(
        #             thread_id=thread_id,
        #             agent_name=self.name,  # 使用 agent_name 区分不同智能体
        #             role="user",
        #             content=message,
        #             extra_metadata=json.dumps(context) if context else None
        #         )
        #         session.add(user_msg)
        #         await session.commit()
        #         logger.debug("MySQL: 用户消息已保存到共享表（流式）")
        # except Exception as e:
        #     logger.error(f"MySQL 保存用户消息失败（流式）: {e}")

        # MongoDB: 保存用户消息到共享集合
        # try:
        #     from app.core.services.mongo_helpers import find_one_document, save_document
        #     mongodb = self.container.get('mongodb')
        #     collection = mongodb.get_collection(SharedConversationHistoryMongo.COLLECTION_NAME)
        #
        #     conversation = await find_one_document(
        #         collection,
        #         SharedConversationHistoryMongo,
        #         {"thread_id": thread_id, "agent_name": self.name}
        #     )
        #
        #     if not conversation:
        #         conversation = SharedConversationHistoryMongo(
        #             thread_id=thread_id,
        #             agent_name=self.name,  # 使用 agent_name 区分不同智能体
        #             messages=[]
        #         )
        #
        #     conversation.add_message(
        #         role="user",
        #         content=message,
        #         extra_metadata=context
        #     )
        #
        #     await save_document(collection, conversation)
        #     logger.debug("MongoDB: 用户消息已保存到共享集合（流式）")
        # except Exception as e:
        #     logger.error(f"MongoDB 保存用户消息失败（流式）: {e}")

        # ========== 原有逻辑 ==========
        # 获取历史消息
        # 优化：如果是新对话（第一次调用），直接使用空列表，避免不必要的数据库查询
        is_new_conversation = context and context.get('is_new_conversation', False)

        if is_new_conversation:
            history_messages = []
            logger.debug(f"新对话 (thread_id={thread_id})，跳过历史消息查询（流式）")
        else:
            history_messages = await self.chat_history.get_messages(thread_id)

        # 获取传入的图片路径
        req_parm = context.get('thumbnailUrl', '')
        logger.info(f"======= req_parm:{req_parm} =========")

        # 如果是首次对话，添加系统提示词
        if not history_messages:
            history_messages = [SystemMessage(content=self.system_prompt)]

        # 添加当前用户消息
        current_message = HumanMessage(content=message)
        messages = history_messages + [current_message]

        graph = self.get_graph()
        # 累积完整响应
        full_response = ""
        # 该智能体产生的所有事件，用于debug，选择需要的事件输出
        # events = []
        try:
            async for event in graph.astream_events(
                    {
                        "messages": messages,
                        "thumbnail_url": req_parm
                    },
                    version="v2"  # 使用v2版本
            ):
                # events.append(event)
                if event["event"] == "on_chat_model_stream":
                    try:
                        chunk_data = event["data"]["chunk"]

                        if chunk_data is None:
                            continue

                        if hasattr(chunk_data, "content"):
                            content = chunk_data.content
                        else:  # 其他情况自行补充
                            try:
                                content = str(chunk_data)
                            except:
                                content = ""

                        if content:
                            full_response += content
                            yield {
                                "type": "message",
                                "data": content
                            }
                    except Exception as e:
                        logger.warning(f"处理chunk出错: {e}")
                        continue

        except Exception as e:
            logger.error(f"LangGraph流式调用失败（流式）: {e}")
            yield {
                "type": "error",
                "data": str(e)
            }

        # 保存对话历史到 Redis（保存清理后的内容）
        # 运维蓝图暂不保存历史记录
        # ai_message = AIMessage(content=full_response)
        # await self.chat_history.add_message(thread_id, current_message)
        # await self.chat_history.add_message(thread_id, ai_message)

        # ========== 持久化AI回复（共享表） ==========
        # 运维蓝图暂不保存历史记录
        # MySQL: 保存AI回复到共享表
        # try:
        #     async with self.mysql.get_session() as session:
        #         ai_msg = SharedConversationHistory(
        #             thread_id=thread_id,
        #             agent_name=self.name,  # 使用 agent_name 区分不同智能体
        #             role="assistant",
        #             content=full_response,
        #             extra_metadata=None
        #         )
        #         session.add(ai_msg)
        #         await session.commit()
        #         logger.debug("MySQL: AI回复已保存到共享表（流式）")
        # except Exception as e:
        #     logger.error(f"MySQL 保存AI回复失败（流式）: {e}")

        # MongoDB: 保存AI回复到共享集合
        # try:
        #     from app.core.services.mongo_helpers import find_one_document, save_document
        #     mongodb = self.container.get('mongodb')
        #     collection = mongodb.get_collection(SharedConversationHistoryMongo.COLLECTION_NAME)
        #
        #     conversation = await find_one_document(
        #         collection,
        #         SharedConversationHistoryMongo,
        #         {"thread_id": thread_id, "agent_name": self.name}
        #     )
        #
        #     if conversation:
        #         conversation.add_message(
        #             role="assistant",
        #             content=cleaned_response,
        #             extra_metadata=None
        #         )
        #         await save_document(collection, conversation)
        #         logger.debug("MongoDB: AI回复已保存到共享集合（流式）")
        # except Exception as e:
        #     logger.error(f"MongoDB 保存AI回复失败（流式）: {e}")

        # 发送元数据
        yield {
            "type": "metadata",
            "data": {
                "thread_id": thread_id,
                "full_response": full_response
            }
        }