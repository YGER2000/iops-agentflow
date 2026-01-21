async def stream(
        self,
        message: str,
        thread_id: str,
        context: Dict[str, Any] = None
) -> AsyncGenerator[Dict[str, Any], None]:
    """流式调用智能体"""
    # 确保 chat_history 已初始化
    await self._ensure_chat_history()

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
    req_parm = context.get('canvasId', '')
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
                    "canvas_id": req_parm
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
    ai_message = AIMessage(content=full_response)
    await self.chat_history.add_message(thread_id, current_message)
    await self.chat_history.add_message(thread_id, ai_message)

    # 发送元数据
    yield {
        "type": "metadata",
        "data": {
            "thread_id": thread_id,
            # "full_response": full_response
        }
    }