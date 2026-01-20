from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from app.schemas.agent import AgentRequest, AgentResponse, AgentStreamRequest
from app.agents.registry import AgentRegistry
import uuid
import json
import asyncio

router = APIRouter(prefix="/api/v1", tags=["agent"])


@router.post("/agent/invoke", response_model=str)
async def invoke_agent(request: AgentRequest):
    """
    调用智能体

    Args:
        request: 包含智能体名称、消息、线程ID等信息

    Returns:
        智能体的响应
    """
    try:
        # 获取智能体
        agent = AgentRegistry.get(request.agent_name)

        # 生成或使用线程ID
        is_new_conversation = not request.thread_id  # 如果用户没传 thread_id，则是新对话
        thread_id = request.thread_id or str(uuid.uuid4())

        # 准备上下文（添加是否为新对话的标志）
        context = request.context or {}
        context['is_new_conversation'] = is_new_conversation

        # 调用智能体
        response = await agent.invoke(
            message=request.message,
            thread_id=thread_id,
            context=context
        )

        return response

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"智能体调用失败: {str(e)}")


@router.get("/agents")
async def list_agents():
    """
    列出所有已注册的智能体

    Returns:
        智能体名称和描述的字典
    """
    return {
        "agents": AgentRegistry.list_agents()
    }


@router.post("/agent/stream")
async def stream_agent(request: AgentStreamRequest):
    """
    流式调用智能体（使用 Server-Sent Events）
    
    Args:
        request: 包含智能体名称、消息、线程ID等信息
        
    Returns:
        Server-Sent Events 流
        
    事件格式：
        - event: message - 流式文本片段
        - event: data - 结构化数据
        - event: metadata - 元数据
        - event: done - 完成信号
        - event: error - 错误信息
    """
    try:
        # 获取智能体
        agent = AgentRegistry.get(request.agent_name)
        
        # 生成或使用线程ID
        is_new_conversation = not request.thread_id  # 如果用户没传 thread_id，则是新对话
        thread_id = request.thread_id or str(uuid.uuid4())
        
        # 准备上下文（添加是否为新对话的标志）
        context = request.context or {}
        context['is_new_conversation'] = is_new_conversation
        
        # 检查智能体是否支持流式输出
        if not hasattr(agent, 'stream'):
            raise HTTPException(
                status_code=400, 
                detail=f"智能体 '{request.agent_name}' 不支持流式输出"
            )
        
        async def event_generator():
            """生成 SSE 事件流"""
            try:
                # 调用智能体的流式方法
                async for chunk in agent.stream(
                    message=request.message,
                    thread_id=thread_id,
                    context=context
                ):
                    # 发送事件到客户端
                    event_type = chunk.get("type", "message")
                    event_data = chunk.get("data", "")
                    
                    # SSE 格式: event: type\ndata: json_data\n\n
                    yield f"event: {event_type}\n"
                    yield f"data: {json.dumps(event_data, ensure_ascii=False)}\n\n"
                    
                    # 确保数据立即发送
                    await asyncio.sleep(0)
                
                # 发送完成信号
                yield "event: done\n"
                yield f"data: {json.dumps({'thread_id': thread_id})}\n\n"
                
            except Exception as e:
                # 发送错误信号
                yield "event: error\n"
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
        
        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"  # 禁用 Nginx 缓冲
            }
        )
        
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"智能体调用失败: {str(e)}")


@router.get("/health")
async def health_check():
    """健康检查
    
    检查所有核心服务的健康状态。
    
    Returns:
        健康状态响应，包含：
        - status: "healthy" (所有服务正常), "degraded" (部分服务故障), "unhealthy" (关键服务故障)
        - services: 各个服务的状态详情
        - timestamp: 检查时间戳
    """
    import time
    from app.main import get_container
    from app.core.chat_history import get_chat_history_manager
    from app.core.config import settings
    
    services_status = {}
    overall_status = "healthy"
    critical_services_down = []
    
    # 获取服务容器
    container = get_container()
    
    # 1. 检查 Redis / ChatHistory
    try:
        chat_manager = await get_chat_history_manager()
        redis_healthy = await asyncio.wait_for(chat_manager.ping(), timeout=2.0)
        services_status["redis"] = {
            "status": "healthy" if redis_healthy else "unhealthy",
            "type": "ChatHistoryManager" if isinstance(chat_manager, type(await get_chat_history_manager())) else "Memory",
        }
        if not redis_healthy:
            overall_status = "degraded"
    except asyncio.TimeoutError:
        services_status["redis"] = {"status": "unhealthy", "error": "timeout"}
        overall_status = "degraded"
    except Exception as e:
        services_status["redis"] = {"status": "unhealthy", "error": str(e)}
        overall_status = "degraded"
    
    # 2. 检查 LLM 服务
    try:
        llm_service = container.get('llm')
        if llm_service:
            # 检查是否能获取 API key
            if hasattr(llm_service, '_current_api_key') and llm_service._current_api_key:
                services_status["llm"] = {
                    "status": "healthy",
                    "model": settings.llm_model,
                    "api_key_status": "active"
                }
            else:
                services_status["llm"] = {
                    "status": "healthy",
                    "model": settings.llm_model,
                    "api_key_status": "not_initialized"
                }
        else:
            services_status["llm"] = {"status": "unhealthy", "error": "services not found"}
            critical_services_down.append("llm")
            overall_status = "unhealthy"
    except Exception as e:
        services_status["llm"] = {"status": "unhealthy", "error": str(e)}
        critical_services_down.append("llm")
        overall_status = "unhealthy"
    
    # 3. 检查 MySQL（如果启用）
    if settings.mysql_enabled:
        try:
            mysql_service = container.get('mysql')
            if mysql_service and hasattr(mysql_service, '_pool') and mysql_service._pool:
                # 简单检查连接池是否存在
                services_status["mysql"] = {"status": "healthy"}
            else:
                services_status["mysql"] = {"status": "unhealthy", "error": "not initialized"}
                if overall_status == "healthy":
                    overall_status = "degraded"
        except Exception as e:
            services_status["mysql"] = {"status": "unhealthy", "error": str(e)}
            if overall_status == "healthy":
                overall_status = "degraded"
    
    # 4. 检查 MongoDB（如果启用）
    if settings.mongodb_enabled:
        try:
            mongodb_service = container.get('mongodb')
            if mongodb_service:
                mongo_healthy = await asyncio.wait_for(mongodb_service.ping(), timeout=2.0)
                services_status["mongodb"] = {
                    "status": "healthy" if mongo_healthy else "unhealthy"
                }
                if not mongo_healthy and overall_status == "healthy":
                    overall_status = "degraded"
            else:
                services_status["mongodb"] = {"status": "unhealthy", "error": "not initialized"}
                if overall_status == "healthy":
                    overall_status = "degraded"
        except asyncio.TimeoutError:
            services_status["mongodb"] = {"status": "unhealthy", "error": "timeout"}
            if overall_status == "healthy":
                overall_status = "degraded"
        except Exception as e:
            services_status["mongodb"] = {"status": "unhealthy", "error": str(e)}
            if overall_status == "healthy":
                overall_status = "degraded"
    
    # 5. 检查 API Key 服务（如果启用）
    if settings.apikey_service_enabled:
        try:
            apikey_service = container.get('apikey')
            if apikey_service:
                services_status["apikey_service"] = {
                    "status": "healthy",
                    "last_fetch": getattr(apikey_service, '_fetch_time', 0)
                }
            else:
                services_status["apikey_service"] = {"status": "unhealthy", "error": "not initialized"}
                if overall_status == "healthy":
                    overall_status = "degraded"
        except Exception as e:
            services_status["apikey_service"] = {"status": "unhealthy", "error": str(e)}
            if overall_status == "healthy":
                overall_status = "degraded"
    
    return {
        "status": overall_status,
        "services": services_status,
        "timestamp": time.time(),
        "critical_services_down": critical_services_down if critical_services_down else None
    }