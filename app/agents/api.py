import asyncio

from http.client import HTTPException


import os
from starlette.concurrency import run_in_threadpool

from configs import apollo_config_chatService, dify_chat_url, dify_api_key, folded_thinking_process_list
from configs import difyKBclient,dataset_metadata_kb_name
import time
import logging

from .agent_route import  query_route_by_scene_id
from .auth.auth import AuthMiddleware, get_current_user
from .knowledge.knowledage_api import knowledage_router
from .scene.agent_api import platform_router
from .scene.dao.scene_dao import update_visit_count, get_scene_by_scene_name
from .scene.scene_api import scene_router
from .start_up_init import  StartUp

from .time_job.data_sync_timer import execute_sync_task, control_scheduler

import json
import requests
import aiohttp

from service.response import register_exception_handler, ApiException
from service.routes.itsm import router as itsm_router
from fastapi import FastAPI, Response, status, BackgroundTasks, Request

from starlette.responses import StreamingResponse
from DifyClient.client import ChatClient
from service.privilege import getAgentRoute
from service.models import (
    ChatRequest,
    ChatResponse,
TaskResponse,
JobControlRequest
)


import uuid
from service.scriptConf.script_api import router as script_router
from service.conversation.conversation_api import router as conversation_router, save_conversation, gen_summary, \
    save_conversation_async, gen_summary_async
from service.conversation.message_api import router as message_router, save_messages_async
from service.conversation.feedback_api import router as feedback_router, feedback_manager_router as feedback_manager_router
from utils.component_data_format import convert_planner_to_step_chat
from service.kb_api import router as kb_router
from service.cmdb.cmdb_api import router as cmdb_router
from service.notify.notify_api import router as notify_router
from service.user.user_api import router as user_router
from service.settings.settings_api import router as settings_router
from service.dictionary.dictionary_api import router as dictionary_router
from service.ai_models.ai_models_api import router as ai_models_router
from service.privilege import router as privilege_router

logger = logging.getLogger("uvicorn.access")
handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.handlers = [handler]

logger = logging.getLogger("uvicorn.access")
handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.handlers = [handler]

app = FastAPI()
# 添加中间件
app.add_middleware(AuthMiddleware,
    exclude_paths=[
        "/itsm/attachment/extract",
        "/api/v1/read_file",
        "/api/v1/segments_by_kb",
        "/api/chat/kb/save",
        "/api/bitmind/kb/upload",
        "/bitmind/service/api/v1/ai_models/query_all"
    ]
)

# 注册异常处理器
register_exception_handler(app)
# 将路由注册到应用中
app.include_router(itsm_router, prefix="/itsm")
app.include_router(scene_router,prefix="/bitmind/service/api/v1/scene")
app.include_router(knowledage_router,prefix="/bitmind/service/api/v1/knowledage")
app.include_router(platform_router,prefix="/bitmind/service/api/v1/platform")
app.include_router(conversation_router, prefix="/bitmind/service/api/v1")
app.include_router(message_router,prefix="/bitmind/service/api/v1")
app.include_router(feedback_router,prefix="/bitmind/service/api/v1")
app.include_router(script_router, prefix="/bitmind/service/api/v1")
app.include_router(cmdb_router, prefix="/bitmind/service/api/v1/cmdb")
app.include_router(user_router, prefix="/bitmind/service/api/v1/user")
app.include_router(notify_router, prefix="/bitmind/service/api/v1/notify")
app.include_router(kb_router)
app.include_router(feedback_manager_router, prefix="/bitmind/service/api/v1/feedback")
app.include_router(settings_router, prefix="/bitmind/service/api/v1/settings")
app.include_router(dictionary_router, prefix="/bitmind/service/api/v1/dict")
app.include_router(ai_models_router, prefix="/bitmind/service/api/v1/ai_models")
app.include_router(privilege_router, prefix="/bitmind/service/api/v1")

logger = logging.getLogger(__name__)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)

default_scene_name = '通识问答'

@app.on_event("startup")
async def start_up():
    # 系统初始化执行
    StartUp.init()



#权限注册
# initPrivilege()
#支持流程任务接口
# @app.post("/bitmind/service/api/v2/chat")
# async def chat_streaming(request:Request,req: ChatRequest, resp: Response,background_tasks: BackgroundTasks):
#     # 流模式请求
#     req.stream = True
#     # 扩展source参数，区分dify和multi-agent
#     source = req.context.get("source")
#     scene = req.context.get("scene")
#
#     # 获取用户信息
#     user = get_current_user(request)
#
#     ## 如果前端没传scene字段，默认走的是dify的通识问答
#     if not scene:
#         return await handle_default(background_tasks,req,user)
#
#     source = scene.get("source")
#
#
#     try:
#         if source == "OpsMind" or source == "BitMind":
#             # 变更报告，变更追溯等
#             return await handle_uyun(background_tasks, req, resp,user)
#         elif source == "dify":
#             # 风险评估，合规检查，数据探查，通识问答等
#             return await handle_dify(background_tasks, req,user)
#         else:
#             raise ApiException(500, "暂无平台来源，请联系管理员！")
#     except Exception as e:
#         logger.exception(e)
#         resp.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
#         raise ValueError(f"APIError: {str(e)}")
@app.post("/bitmind/service/api/v2/chat")
async def chat_streaming(request:Request,req: ChatRequest, resp: Response,background_tasks: BackgroundTasks):
    # 流模式请求
    req.stream = True
    # 扩展source参数，区分dify和multi-agent
    source = req.context.get("source")
    scene = req.context.get("scene")
    token = request.cookies.get("token")
    req.context["token"] = token

    # 获取用户信息
    user = get_current_user(request)

    ## 如果前端没传scene字段，默认走的是dify的通识问答
    if not scene:
        return await handle_uyun(background_tasks, req, resp, user)

        # return await handle_default(background_tasks, req, user)
        # default_scene = get_scene_by_scene_name(default_scene_name)
        # if default_scene:
        #     scene_dict = {k: v for k, v in default_scene.__dict__.items() if not k.startswith('_')}
        #     req.context["scene"] = scene_dict
        #     scene = scene_dict

        # logger.info(f"默认场景：{default_scene.id}")


    source = scene.get("source")

    try:
        if source == "OpsMind" or source == "BitMind":
            # 变更报告，变更追溯等
            return await handle_uyun(background_tasks, req, resp,user)
        elif source == "dify":
            # 风险评估，合规检查，数据探查，通识问答等
            return await handle_dify(background_tasks, req,user)
        elif source == "agentflow":
            return await handle_agent_flow(background_tasks, req,user)
        else:
            raise ApiException(500, "暂无平台来源，请联系管理员！")
    except Exception as e:
        logger.exception(e)
        resp.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        raise ValueError(f"APIError: {str(e)}")

""" 处理 agentFlow 平台智能体 """
async def handle_agent_flow(background_tasks, req, user):
    # 捕获流聚合数据
    answers = []
    thought = []
    userId = user.get("userId")
    account = user.get("account")
    agentId = req.context.get("agent_id")

    # 如果是新会话创建一条记录
    conversation_id = req.context.get("conversation_id")
    if not conversation_id:
        conversation_id = uuid.uuid4().hex
        asyncio.create_task(save_conversation_async(conversation_id, agentId, userId, account, req.context.get("isScene")))

        # 启动异步线程，不阻塞后面的流程
        asyncio.create_task(gen_summary_async(conversation_id, req.question))

    # 从 scene 中获取 agent_name (agentFlow 需要的智能体名称),暂时使用apikey字段
    agent_name = req.context.get("scene", {}).get("apikey", "")
    if not agent_name:
        raise ApiException(400, "agentFlow 智能体需要提供 agent_name 参数")

    # 构建 agentFlow 请求参数
    agentflow_request = {
        "agent_name": agent_name,
        "message": req.question,
        "thread_id": conversation_id,  # 使用 conversation_id 作为 thread_id
        "context": req.context
    }

    base_url = req.context.get("scene", {}).get("base_url", "")

    session = None
    try:
        timeout = aiohttp.ClientTimeout(total=1000)
        session = aiohttp.ClientSession(timeout=timeout)
        response = await session.post(
            f"{base_url}/api/v1/agent/stream",
            json=agentflow_request
        )
        if response.status != 200:
            error_msg = await response.text()
            await session.close()
            raise Exception(f"Status: {response.status}, Error: {error_msg}")
            
    except Exception as e:
        if session:
            await session.close()
        logger.exception(f"调用 agentFlow 接口失败: {e}")
        raise ApiException(500, f"调用 agentFlow 接口失败: {str(e)}")

    logger.info(f"agentFlow response content-type: {response.headers.get('Content-Type')}")

    # 消息id
    message_id = uuid.uuid4().hex

    # 生成流式响应
    response_generator = agentflow_stream_generator(response, session, answers, thought, conversation_id, message_id)

    # 构建响应头
    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",  # 禁用nginx缓冲
        "Content-Encoding": "identity"  # 禁用压缩
    }

    # 从原始响应中添加其他头（排除可能引起问题的头）
    for k, v in response.headers.items():
        if k.lower() not in ("content-length", "content-encoding"):
            headers[k] = v

    # 将异步保存消息任务添加到后台任务
    background_tasks.add_task(save_messages_async, conversation_id, message_id, userId, req, answers, thought)

    return StreamingResponse(
        response_generator,
        status_code=response.status,
        media_type=response.headers.get("Content-Type", "text/event-stream"),
        headers=headers
    )


async def agentflow_stream_generator(response, session, answers: list, thought: list,
                                     conversation_id: str, message_id: str):
    """
    处理 agentFlow 返回的 SSE 流

    agentFlow 的事件格式：
    - event: message - 流式文本片段
    - event: data - 结构化数据
    - event: metadata - 元数据
    - event: done - 完成信号
    - event: error - 错误信息
    """
    logger.info(f"conversation_id: {conversation_id}, 开始处理 agentFlow 流式响应")

    current_event_type = None

    try:
        async for line in response.content:
            raw = line.decode('utf-8').strip()
            if not raw or raw.startswith(":"):
                # 注释行或空行，跳过
                continue

            # 解析 SSE 格式
            if raw.startswith("event:"):
                # 提取事件类型
                current_event_type = raw.replace("event:", "").strip()
                continue

            if raw.startswith("data:"):
                # 提取数据
                data_str = raw.replace("data:", "").strip()

                if not data_str:
                    continue

                try:
                    data_json = json.loads(data_str)
                except json.JSONDecodeError:
                    # 如果不是 JSON，当作纯文本处理
                    data_json = {"text": data_str}

                # 根据事件类型处理数据
                if current_event_type == "message":
                    # 流式文本消息
                    text_content = data_json.get("text", "") if isinstance(data_json, dict) else str(data_json)

                    if text_content:
                        # 构建返回给前端的消息格式
                        output_msg = {
                            "conversation_id": conversation_id,
                            "thread_id": conversation_id,
                            "message_id": message_id,
                            "agent": "agentflow",
                            "content": text_content,
                            "type": "message"
                        }

                        # 累积答案用于保存
                        answers.append(text_content)

                        yield f"data: {json.dumps(output_msg, ensure_ascii=False)}\n\n"
                        await asyncio.sleep(0)

                elif current_event_type == "data":
                    # 结构化数据（如查询结果）
                    output_msg = {
                        "conversation_id": conversation_id,
                        "thread_id": conversation_id,
                        "message_id": message_id,
                        "agent": "agentflow",
                        "data": data_json,
                        "type": "data"
                    }

                    # 保存结构化数据
                    answers.append(json.dumps(data_json, ensure_ascii=False))

                    yield f"data: {json.dumps(output_msg, ensure_ascii=False)}\n\n"
                    await asyncio.sleep(0)

                elif current_event_type == "metadata":
                    # 元数据（如思考过程、工具调用等）
                    metadata_content = json.dumps(data_json, ensure_ascii=False)

                    output_msg = {
                        # 保存思考过程
                        # thought.append(metadata_content.get("thought", ""))
                        "conversation_id": conversation_id,
                        "thread_id": conversation_id,
                        "message_id": message_id,
                        "agent": "agentflow",
                        "context": metadata_content,
                        "type": "metadata"
                    }

                    yield f"data: {json.dumps(output_msg, ensure_ascii=False)}\n\n"
                    await asyncio.sleep(0)

                elif current_event_type == "done":
                    # 完成信号
                    output_msg = {
                        "conversation_id": conversation_id,
                        "thread_id": conversation_id,
                        "message_id": message_id,
                        "agent": "agentflow",
                        "thread_id": data_json.get("thread_id", conversation_id),
                        "type": "done",
                        "finished": True
                    }

                    yield f"data: {json.dumps(output_msg, ensure_ascii=False)}\n\n"
                    await asyncio.sleep(0)
                    break

                elif current_event_type == "error":
                    # 错误信息
                    error_msg = data_json.get("error", "未知错误") if isinstance(data_json, dict) else str(data_json)
                    logger.error(f"conversation_id: {conversation_id}, agentFlow 返回错误: {error_msg}")

                    output_msg = {
                        "conversation_id": conversation_id,
                        "thread_id": conversation_id,
                        "message_id": message_id,
                        "agent": "agentflow",
                        "error": error_msg,
                        "type": "error",
                        "finished": True
                    }

                    yield f"data: {json.dumps(output_msg, ensure_ascii=False)}\n\n"
                    await asyncio.sleep(0)
                    break

                # 重置事件类型
                current_event_type = None

    except Exception as e:
        logger.exception(f"conversation_id: {conversation_id}, agentFlow 流处理异常")
        error_msg = {
            "conversation_id": conversation_id,
            "thread_id": conversation_id,
            "message_id": message_id,
            "agent": "agentflow",
            "error": f"流处理异常: {str(e)}",
            "type": "error",
            "finished": True
        }
        yield f"data: {json.dumps(error_msg, ensure_ascii=False)}\n\n"
    finally:
        if response:
            response.release()
        if session:
            await session.close()

"""处理 dify 平台智能体"""
async def handle_dify(background_tasks, req,user):
    # 捕获流聚合数据
    answers = []
    thought = []
    userId = user.get("userId")
    account = user.get("account")
    agentId = req.context.get("agent_id")
    scene_name = req.context["scene"].get("scene_name")
    '''
        hasPrivilege = checkUserPrivilege(userId, agentId)
        if hasPrivilege is False:
            # 生成错误流并立即结束
            return StreamingResponse(
                error_stream_generator("当前用户未授权", 403),
                status_code=403,  # 明确设置状态码
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "close"  # 明确关闭连接
                }
            )
        '''
    # 如果是新会话创建一条记录
    conversation_id = req.context.get("conversation_id")
    if not conversation_id:
        conversation_id = uuid.uuid4().hex
        asyncio.create_task(
            save_conversation_async(conversation_id, agentId, userId, account, req.context.get("isScene")))
        # try:
        #     save_conversation(new_conversation_id, agentId, userId,account, req.context.get("isScene"))
        # except Exception as e:
        #     print(f"保存会话时出错: {e}")

        # 启动异步线程，不阻塞后面的流程
        asyncio.create_task(gen_summary_async(conversation_id,req.question))

    #  根据scene_id 查找对应场景绑定的智能体的url和key
    key, url = query_route_by_scene_id(req.context.get("scene").get("id"))
    chatClient = ChatClient(key, url)


    userName = user.get("realname")

    completion_response = chatClient.create_chat_message(
        inputs=req.context,
        query=req.question,
        user=userName,
        response_mode="streaming")
    completion_response.raise_for_status()

    print("dify response content-type: {}".format(completion_response.headers.get("Content-Type")))
    # 构建响应头
    headers = {}
    # 添加禁用缓冲的头
    headers["Cache-Control"] = "no-cache"
    headers["Connection"] = "keep-alive"
    headers["X-Accel-Buffering"] = "no"  # 禁用nginx缓冲
    headers["Content-Encoding"] = "identity"  # 禁用压缩

    # 从原始响应中添加其他头（排除可能引起问题的头）
    for k, v in completion_response.headers.items():
        if k.lower() not in ("content-length", "content-encoding"):
            headers[k] = v

    # 消息id
    message_id = uuid.uuid4().hex
    # 包装成 StreamingResponse，透传 Content-Type
    folded_thinking_process = True if scene_name in folded_thinking_process_list else False
    response_generator = dify_stream_generator(completion_response, answers, thought, conversation_id, message_id,
                                               folded_thinking_process)
    streaming_response = StreamingResponse(
        response_generator,
        status_code=completion_response.status_code,
        media_type=completion_response.headers.get("Content-Type", "text/event-stream"),
        headers=headers
    )

    # 将异步保存消息任务添加到后台任务
    background_tasks.add_task(save_messages_async, conversation_id, message_id, userId, req, answers,thought)
    return streaming_response


""" 处理 uyun 平台智能体 """
async def handle_uyun(background_tasks, req, resp, user):
    # 捕获流聚合数据
    answers = []
    thought = []
    userId = user.get("userId")
    account = user.get("account")
    agentId = req.context.get("agent_id")
    # 如果是新会话创建一条记录
    conversation_id = req.context.get("conversation_id")
    if not conversation_id:
        conversation_id = uuid.uuid4().hex
    asyncio.create_task(
            save_conversation_async(conversation_id, agentId, userId, account, req.context.get("isScene")))
        # try:
        #     save_conversation(conversation_id, agentId, userId,account, req.context.get("isScene"))
        # except Exception as e:
        #     print(f"保存会话时出错: {e}")

        # 启动异步线程，不阻塞后面的流程
    logger.info(f"摘要生成开始: {conversation_id}")
    asyncio.create_task(gen_summary_async(conversation_id, req.question))

    req.context["conversation_id"] = conversation_id
    completion_response = engingService(req, resp,userId)
    # 消息id
    message_id = uuid.uuid4().hex
    response_generator = multi_agent_stream_generator(completion_response, answers,thought, conversation_id, message_id)
    # 将异步保存消息任务添加到后台任务
    background_tasks.add_task(save_messages_async, conversation_id, message_id, userId, req, answers,thought)
    # 构建响应头
    headers = {}
    # 添加禁用缓冲的头
    headers["Cache-Control"] = "no-cache"
    headers["Connection"] = "keep-alive"
    headers["X-Accel-Buffering"] = "no"  # 禁用nginx缓冲
    headers["Content-Encoding"] = "identity"  # 禁用压缩

    # 从原始响应中添加其他头（排除可能引起问题的头）
    for k, v in completion_response.headers.items():
        if k.lower() not in ("content-length", "content-encoding"):
            headers[k] = v

    return StreamingResponse(
        response_generator,
        status_code=completion_response.status_code,
        media_type=completion_response.headers.get("Content-Type", "text/event-stream"),
        headers=headers
    )


""" 处理默认逻辑"""
# async def handle_default(background_tasks, req,user):
#     # 捕获流聚合数据
#     answers = []
#     thought = []
#     userId = user.get("userId")
#     account = user.get("account")
#
#     agentId = req.context.get("agent_id")
#     # 如果是新会话创建一条记录
#     conversation_id = req.context.get("conversation_id")
#     if not conversation_id:
#         conversation_id = uuid.uuid4().hex
#         asyncio.create_task(
#             save_conversation_async(conversation_id, agentId, userId, account, req.context.get("isScene")))
#         # try:
#         #     save_conversation(new_conversation_id, agentId, userId,account, req.context.get("isScene"))
#         # except Exception as e:
#         #     print(f"保存会话时出错: {e}")
#
#         # 启动异步线程，不阻塞后面的流程
#         asyncio.create_task(gen_summary_async(conversation_id, req.question))
#
#     chatClient = ChatClient(dify_api_key, dify_chat_url)
#
#     userName = user.get("realname")
#
#     completion_response = chatClient.create_chat_message(
#         inputs={'context': json.dumps(req.context, ensure_ascii=False)},
#         query=req.question,
#         user=userName,
#         response_mode="streaming")
#     completion_response.raise_for_status()
#
#     logger.debug(f"dify response content-type: {completion_response.headers.get('Content-Type')}")
#     # 消息id
#     message_id = uuid.uuid4().hex
#     # 包装成 StreamingResponse，透传 Content-Type
#     response_generator = dify_stream_generator(completion_response, answers,thought, conversation_id, message_id)
#
#     # 构建响应头
#     headers = {}
#     # 添加禁用缓冲的头
#     headers["Cache-Control"] = "no-cache"
#     headers["Connection"] = "keep-alive"
#     headers["X-Accel-Buffering"] = "no"  # 禁用nginx缓冲
#     headers["Content-Encoding"] = "identity"  # 禁用压缩
#
#     # 从原始响应中添加其他头（排除可能引起问题的头）
#     for k, v in completion_response.headers.items():
#         if k.lower() not in ("content-length", "content-encoding"):
#             headers[k] = v
#
#     streaming_response = StreamingResponse(
#         response_generator,
#         status_code=completion_response.status_code,
#         media_type=completion_response.headers.get("Content-Type", "text/event-stream"),
#         headers=headers
#     )
#
#     # 将异步保存消息任务添加到后台任务
#     background_tasks.add_task(save_messages_async, conversation_id, message_id, userId, req, answers,thought)
#     return streaming_response

async def handle_default(background_tasks, req,user):
    # 捕获流聚合数据
    answers = []
    thought = []
    userId = user.get("userId")
    account = user.get("account")

    agentId = req.context.get("agent_id")
    # 如果是新会话创建一条记录
    conversation_id = req.context.get("conversation_id")
    if not conversation_id:
        conversation_id = uuid.uuid4().hex
        asyncio.create_task(
            save_conversation_async(conversation_id, agentId, userId, account, req.context.get("isScene")))
        # try:
        #     save_conversation(new_conversation_id, agentId, userId,account, req.context.get("isScene"))
        # except Exception as e:
        #     print(f"保存会话时出错: {e}")

        # 启动异步线程，不阻塞后面的流程
        asyncio.create_task(gen_summary_async(conversation_id, req.question))

    chatClient = ChatClient(dify_api_key, dify_chat_url)

    userName = user.get("realname")

    completion_response = chatClient.create_chat_message(
        inputs={'context': json.dumps(req.context, ensure_ascii=False)},
        query=req.question,
        user=userName,
        response_mode="streaming")
    completion_response.raise_for_status()

    logger.debug(f"dify response content-type: {completion_response.headers.get('Content-Type')}")
    # 消息id
    message_id = uuid.uuid4().hex
    # 包装成 StreamingResponse，透传 Content-Type
    response_generator = dify_stream_generator(completion_response, answers,thought, conversation_id, message_id)

    # 构建响应头
    headers = {}
    # 添加禁用缓冲的头
    headers["Cache-Control"] = "no-cache"
    headers["Connection"] = "keep-alive"
    headers["X-Accel-Buffering"] = "no"  # 禁用nginx缓冲
    headers["Content-Encoding"] = "identity"  # 禁用压缩

    # 从原始响应中添加其他头（排除可能引起问题的头）
    for k, v in completion_response.headers.items():
        if k.lower() not in ("content-length", "content-encoding"):
            headers[k] = v

    streaming_response = StreamingResponse(
        response_generator,
        status_code=completion_response.status_code,
        media_type=completion_response.headers.get("Content-Type", "text/event-stream"),
        headers=headers
    )

    # 将异步保存消息任务添加到后台任务
    background_tasks.add_task(save_messages_async, conversation_id, message_id, userId, req, answers,thought)
    return streaming_response


@app.post("/api/v1/read_file")
def read_file() -> dict:
    """
    读取指定路径的文件内容并返回。

    :param req: 包含文件路径的请求体
    :return: 文件内容或错误信息
    """
    # 获取当前脚本文件的目录
    current_dir = os.path.dirname(__file__)
    # 构建dataset.txt的绝对路径
    metadata_path = os.path.join(current_dir, "..", "metadata_file", "dataset.txt")
    metadata_path = os.path.abspath(metadata_path)  # 确保路径是绝对的

    try:
        with open(metadata_path, 'r', encoding='utf-8') as file:
            content = file.read()
        return {"status": "success", "content": content}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="文件未找到")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"读取文件时发生错误: {str(e)}")

@app.get("/api/v1/segments_by_kb")
def read_file() -> str:
    content = ""
    try:
     content  = difyKBclient.get_dify_document_segments(dataset_metadata_kb_name)
     return  content
    except Exception as e:
        print(f"服务错误，分段数据未获取: {str(e)}")
        return  content



@app.post("/api/v1/task/execute", response_model=TaskResponse)
def execute_task(req: JobControlRequest) -> TaskResponse:
    """立即执行一次数据同步任务"""
    success = execute_sync_task(req.job_type)

    if success:
        return TaskResponse(
            status_code=status.HTTP_200_OK,
            content={"message": "任务执行成功"}
        )
    else:
        return TaskResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"message": "任务执行失败"}
        )


@app.post("/api/v1/task/control", response_model=TaskResponse)
def control_task(req: JobControlRequest) -> TaskResponse:
    """控制定时任务的启动与停止"""
    action = req.action
    job_type = req.job_type
    result = control_scheduler(action,job_type)

    if not result["success"] and "无效的操作类型" in result["message"]:
        return TaskResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"message": result["message"]}
        )
    return TaskResponse(
        status_code=status.HTTP_200_OK,
        content={
            "message": result["message"],
            "status": result["status"]
        }
    )

import os
import requests



# @app.post("/bitmind/service/api/v2/chat")
# async def chat_streaming(request:Request,req: ChatRequest, resp: Response,background_tasks: BackgroundTasks):
#     # 流模式请求
#     req.stream = True
#     # 扩展source参数，区分dify和multi-agent
#     source = req.context.get("source")
#     scene = req.context.get("scene")
#
#     # 获取用户信息
#     user = get_current_user(request)
#
#     ## 如果前端没传scene字段，默认走的是dify的通识问答
#     if not scene:
#         return await handle_default(background_tasks,req,user)
#     source = scene.get("source")
#
#     try:
#         if source == "OpsMind" or source == "BitMind":
#             # 变更报告，变更追溯等
#             return await handle_uyun(background_tasks, req, resp,user)
#         elif source == "dify":
#             # 风险评估，合规检查，数据探查，通识问答等
#             return await handle_dify(background_tasks, req,user)
#         else:
#             raise ApiException(500, "暂无平台来源，请联系管理员！")
#     except Exception as e:
#         logger.exception(e)
#         resp.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
#         raise ValueError(f"APIError: {str(e)}")

async def update_visit_count_async(scene_id):
    """异步修改访问次数"""
    try:
        await run_in_threadpool(
            update_visit_count,
            scene_id
        )
        logger.info(f"场景访问次数更新成功: {scene_id}")
    except Exception as e:
        logger.error(f"场景访问次数更新失败: {e}")

def engingService(req:ChatRequest,resp:Response,userId) -> requests.Response:
    agentId = None
    if req.context.get("agent_id"):
        agentId = req.context.get("agent_id")
    session_id = None
    if req.context.get("conversation_id"):
        session_id = req.context.get("conversation_id")

    logger.info(f"userId:{userId}")
    scene_preference = None

    # 场景偏好参数从scene中取
    # 场景偏好参数从scene中取
    if req.context and "scene" in req.context and req.context.get("scene"):
        if req.context.get("scene").get("scene_preference"):
            scene_preference = req.context.get("scene").get("scene_preference")

        scene_id = req.context.get("scene", {}).get("id")
        # 启动异步线程，不阻塞后面的流程
        logger.info("开始异步更新")
        asyncio.create_task(update_visit_count_async(scene_id))



    json_data = {
            "messages": [{"role": "user", "content": req.question}],
            "agent_code": agentId,
            "user_id": userId,
            "session_id": session_id,
            "scene_preference": scene_preference,
            "auto_accepted_plan": True
        }
    base_url = apollo_config_chatService.get("uyun.baseurl")

    response = requests.request(
        "POST",
        f"{base_url}/bitmind/engine/api/chat/stream",
        json=json_data,
        stream=True,
        timeout=3000,
        verify=False
    )
    response.raise_for_status()
    return response
def DifyService(req: ChatRequest, resp: Response) -> ChatResponse:
    """
        Dify
        """
    print("DifyEngine")
    try:
        agentId = req.context.get("agent_id")
        (url, key) = getAgentRoute(agentId)
        chatClient = ChatClient(key, url)
        # print("receive context:")
        # print(req.context)
        userName = req.context.get("userInfo", {}).get("realname", "None")
        completion_response = chatClient.create_chat_message(
            inputs={'context': json.dumps(req.context, ensure_ascii=False)},
            query=req.question,
            user=userName,
            response_mode="blocking")
        if completion_response.status_code == 400:
            print("请求参数错误，将忽略")
            return ChatResponse(status_code=200, message="")



        completion_response.raise_for_status()
        result = completion_response.json()
        try:
            answer = result.get('answer')
            answer = json.loads(answer)
            if not isinstance(answer, dict):
                print("非字典类型")
                data = json.loads(answer.replace("'", '"'))
                if isinstance(data, list):
                    return ChatResponse(status_code=200, content=data)
                else:
                    return ChatResponse(status_code=200, message=answer)
            result = answer.get("result")
            result_list = []
            for text_item in result:
                # dify jsonarray 不支持，此处传回的为字符串
                if isinstance(text_item, str):
                    result_item = json.loads(text_item)
                else:
                    result_item = text_item
                result_list.append(result_item)
            return ChatResponse(status_code=200, content=result_list)
        except json.decoder.JSONDecodeError:
            return ChatResponse(status_code=200, message=answer)

    except Exception as e:
        logger.exception(e)
        resp.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        return ChatResponse(
            status_code=resp.status_code,
            error_message=f"获取回答异常，{str(e)}",
        )

async def multi_agent_stream_generator(response: requests.Response, answers: list,thought:list, conversation_id: str,
                                       message_id: str):
    thought_list = []
    planner_step_card_sent = False
    planner_stop = False
    reporter_stop = False
    general_agent_stop = False
    thread_id = ""
    is_coordinator_thought = False
    curr_step = 1
    all_steps = []
    step =  None
    last_step_feedback_sent = 0  # 记录上次发送反馈的步骤编号
    logger.info(f"conversation_id: {conversation_id},接收到请求.........")
    coordinator_feedback = {"conversation_id": conversation_id, "message_id": message_id, "agent": "coordinator",
                            "content": "","type":"loading","loadingText":"识别用户意图..."}

    yield f"data: {json.dumps(coordinator_feedback, ensure_ascii=False)}\n\n"
    await asyncio.sleep(0)  # 强制刷新
    # time.sleep(1)
    await handle_multi(answers,thought, conversation_id, coordinator_feedback, message_id)
    logger.info(f"conversation_id: {conversation_id}->意图识别进行中:{coordinator_feedback}")
    try:
        for raw in response.iter_lines(decode_unicode=True):
            if "data" in raw:
                line = raw.removeprefix("data:").strip()
                line_json = json.loads(line)
                thread_id = line_json.get("thread_id")
                agent = line_json.get("agent")
                # print(f">>>line_json:{line_json}")
                finish_reason = line_json.get("finish_reason")
                if agent == "coordinator" and (finish_reason == "tool_calls" or finish_reason == "stop"):
                    is_coordinator_thought = True
                if agent == "coordinator" and is_coordinator_thought == True and "content"  in line_json:
                    # line_json["loadingText"] = "正在意图识别中...\n\n"+line_json["content"]
                    content = line_json["content"]
                    if "loading..." in content:
                        answer_result = content.split("|")
                        if len(answer_result) > 0:
                            text = answer_result[1]
                            line_json["content"] = ""
                            line_json["type"] = "loading"
                            texts = ""
                            for char in text:
                                texts += char
                                line_json['loadingText'] = "识别用户意图...\n\n" + texts
                                yield f"data: {json.dumps(line_json, ensure_ascii=False)}\n\n"
                                # time.sleep(0.05)
                            logger.info(f"conversation_id: {conversation_id}->意图识别:{texts}")
                            await asyncio.sleep(0)  # 强制刷新
                            await handle_multi(answers,thought, conversation_id, line_json, message_id)
                            # if "content" not in line_json or line_json.get("content") == "\n\n":
                            # time.sleep(3)
                            logger.info(f"coordinator完成:{json.dumps(line_json, ensure_ascii=False)}")
                            line_json["content"] = ""
                            line_json["loadingText"] = "正在规划任务，请稍后......."
                            logger.info(f"conversation_id: {conversation_id}->{line_json}")
                            yield f"data: {json.dumps(line_json, ensure_ascii=False)}\n\n"
                            await asyncio.sleep(0)  # 强制刷新
                    else:
                        yield f"data: {json.dumps(line_json, ensure_ascii=False)}\n\n"

                if line_json.get("content") and "thought" in line_json.get("content"):


                    content = line_json["content"].replace("thought", "")

                    # 逐字符输出content内容
                    del line_json["content"]
                    line_json["thought"] = content + "\n\n\n"
                    thought_list.append(line_json)
                    thought.append(content+ "\n\n\n")

                    for char in content:
                        line_json["thought"] = char  # 每次输出一个字符到thought字段

                        logger.info(f"thought result -->:{line_json}")
                        yield f"data: {json.dumps(line_json, ensure_ascii=False)}\n\n"
                        await asyncio.sleep(0.05)  # 添加小延迟以产生逐字效果

                    # 添加进thought_list，最后保存至历史消息中

                    # 删除原来的content字段
                    await asyncio.sleep(0)
                try:
                    if  line_json.get("content") and "flag" in line_json.get("content"):
                        content = line_json.get("content").replace("flag", "")
                        line_json['content'] = content
                        yield f"data: {json.dumps(line_json, ensure_ascii=False)}\n\n"

                        await handle_multi(answers,thought, conversation_id, line_json, message_id)
                    # elif line_json.get("content") and "thought" not in line_json.get("content"):
                    #     # 处理其他普通content内容（不包含thought和flag的）
                    #     await handle_multi(answers, thought, conversation_id, line_json, message_id)
                    #     yield f"data: {json.dumps(line_json, ensure_ascii=False)}\n\n"
                except Exception as e:
                    print(f"错误了：{e}")
                    logger.exception(e)

    except Exception as e:
        logger.exception("流生成过程中发生异常")
        end_msg = {"thread_id": thread_id, "id": str(uuid.uuid4()), "role": "assistant",
                   "content": ""}
        logger.info(f"结束流：{end_msg}")
        yield f"data: {json.dumps(end_msg, ensure_ascii=False)}\n\n"
    finally:
        # thought_list = thought_list.join("\n")
        line_json = {"thread_id": thread_id, "id": str(uuid.uuid4()), "role": "assistant",
                   "thought": "\n"}
        await handle_multi(answers,thought, conversation_id, line_json, message_id)


        # answers.append(thought_list.join("\n"))



async def handle_multi(answers,thought, conversation_id, line_json, message_id):
    ## 获取content字段作为历史消息
    if line_json.get("content"):
        answers.append(line_json.get("content"))
    if "thought" in line_json and line_json.get("thought"):
        thought.append(line_json.get("thought"))
    # 返回报文时需要提供给前端会话id和消息id，方便后续处理
    line_json['conversation_id'] = conversation_id
    line_json['message_id'] = message_id



#生成流数据
async def dify_stream_generator(response: requests.Response, answers: list,thought: list,conversation_id: str,message_id:str=None, folded_thinking_process:bool=False):

    step_one_topic = "识别用户意图..."
    coordinator_feedback = {"conversation_id": conversation_id, "message_id": message_id, "agent": "coordinator",
                            "content":"",
                            "loadingText": step_one_topic,"type":"loading"}

    yield f"data: {json.dumps(coordinator_feedback, ensure_ascii=False)}\n\n"
    await asyncio.sleep(0)  # 强制刷新
    await handle_multi(answers,thought, conversation_id, coordinator_feedback, message_id)
    # time.sleep(1)
    logger.info(f"意图识别进行中:{coordinator_feedback}")
    for raw in response.iter_lines(decode_unicode=True, delimiter="\n"):

        if not raw or raw.startswith(":"):
            # 注释行或者空行：发送一个空行触发客户端心跳，也可跳过
            #yield "\n"
            continue

        line = raw.removeprefix("data:").strip()
        if line == "ping":
            # 心跳，可选地回应一个 comment 保持连接
            #yield ": pong\n\n"
            continue

        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            # 如果不是合法 JSON，就当文本事件发出
            #yield f"data: {line}\n\n"
            continue
        if payload.get("event") == "message" and "loading..." in payload.get("answer"):
            coordinator_feedback['loadingText'] = payload.get("answer")
            text =payload.get("answer")
            answer_result =text.split("|")
            if len(answer_result)>0:
                texts = ""
                for char in answer_result[2]:
                    texts += char
                    coordinator_feedback['loadingText'] = answer_result[1] + "\n\n" + texts
                    yield f"data: {json.dumps(coordinator_feedback, ensure_ascii=False)}\n\n"
                    # time.sleep(0.05)


            # yield f"data: {json.dumps(coordinator_feedback, ensure_ascii=False)}\n\n"
            await asyncio.sleep(0)  # 强制刷新
            # time.sleep(3)
            # coordinator_feedback = {"conversation_id": conversation_id, "message_id": message_id,
            #                         "agent": "coordinator",
            #                         "content": "",
            #                         "loadingText": "数据处理中...", "type": "loading"}
            #
            # yield f"data: {json.dumps(coordinator_feedback, ensure_ascii=False)}\n\n"
            # await asyncio.sleep(0)  # 强制刷新

        # 这里只处理 event=message
        if payload.get("event") == "message"  or payload.get("event")== "message_end" :
            try:
                if "loading..." in payload.get("answer"):
                    print(f"loading...{payload.get("answer")}")
                else:
                    # 按照 SSE 规范包装 data 字段，并以空行分隔
                    # print(json.dumps(payload))

                    # 获取answer字段保存作为会话历史
                    if payload.get("answer"):
                        answers.append(payload.get("answer"))

                    # 适配知识库召回溯源信息
                    if payload.get("metadata"):
                        metadata = json.dumps(payload.get("metadata"), ensure_ascii=False)
                        print("知识库召回溯源信息:", metadata)
                        answers.append(metadata)
                    if folded_thinking_process:
                        payload["answer"] = "<details open> <summary>深度思考</summary>" + payload.get("answer")
                        folded_thinking_process = False
                    ## 如果是普通聊天助手/dify，需要返回conversation_id和message_id,
                    # 供前端调用生成摘要接口和消息反馈接口
                    payload['conversation_id'] = conversation_id
                    payload['message_id'] = message_id
                    yield f"data: {json.dumps(payload)}\n\n"
            except Exception as e:
                logger.warn("忽略数据流")

#流模式异常数据处理
async def start_stream_generator():
     #开始工作流：
    start_sign = {
        "start": {
            "code": 0,
            "message": "start"
        }
    }
    yield f"data: {json.dumps(start_sign)}\n\n"


#流模式异常数据处理
async def error_stream_generator(message: str, code: int):
    """生成错误信息的流式响应生成器"""
    error_data = {
        "error": {
            "code": code,
            "message": message
        },
        "finished": True  # 标识流结束
    }
    # 按照SSE格式返回错误
    yield f"data: {json.dumps(error_data)}\n\n"




