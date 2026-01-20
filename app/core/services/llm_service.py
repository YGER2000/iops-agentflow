"""LLM 服务

提供统一的 LLM 访问接口。
"""

import logging
import re
from typing import AsyncGenerator, List, Optional
from langchain_openai import ChatOpenAI
from app.core.config import settings
from app.core.container import IService
from .interfaces import ILLMService, IApiKeyService

logger = logging.getLogger(__name__)


class LLMService(IService, ILLMService):
    """LLM 服务实现
    
    封装对 LLM 的访问，支持多模型、流式响应等。
    """
    
    def __init__(self, apikey_service: Optional[IApiKeyService] = None):
        """初始化 LLM 服务
        
        Args:
            apikey_service: API Key 服务实例（可选）
        """
        self._apikey_service = apikey_service
        self._current_api_key: Optional[str] = None
        logger.debug("LLM 服务已创建")
    
    async def initialize(self) -> None:
        """初始化服务"""
        # 如果启用了动态 API key，获取初始值
        if settings.apikey_service_enabled and self._apikey_service:
            try:
                self._current_api_key = self._apikey_service.get_api_key_sync()
                logger.info(f"LLM 服务初始化完成 (model={settings.llm_model}, 使用动态 API key)")
            except Exception as e:
                logger.warning(f"获取动态 API key 失败，使用配置文件值: {e}")
                self._current_api_key = settings.llm_api_key
        else:
            self._current_api_key = settings.llm_api_key
            logger.info(f"LLM 服务初始化完成 (model={settings.llm_model}, 使用固定 API key)")
    
    async def shutdown(self) -> None:
        """关闭服务"""
        self._current_api_key = None
        logger.info("LLM 服务已关闭")
    
    def _get_current_api_key(self) -> str:
        """获取当前的 API key
        
        Returns:
            API key 字符串
        """
        # 如果启用了动态 API key 且有 API key 服务
        if settings.apikey_service_enabled and self._apikey_service:
            try:
                self._current_api_key = self._apikey_service.get_api_key_sync()
            except Exception as e:
                logger.error(f"获取动态 API key 失败: {e}")
                # 如果有缓存的 API key，继续使用
                if not self._current_api_key:
                    self._current_api_key = settings.llm_api_key
        else:
            # 使用配置文件中的固定值
            self._current_api_key = settings.llm_api_key
        
        return self._current_api_key
    
    def get_model(self, model: str = None, temperature: float = None) -> ChatOpenAI:
        """获取 LLM 模型实例
        
        注意：当启用动态 API key 时，每次都会创建新的模型实例。
        
        Args:
            model: 模型名称，默认使用配置中的模型
            temperature: 温度参数，默认使用配置中的温度
            
        Returns:
            LLM 模型实例
        """
        self._get_current_api_key()
        model = model or settings.llm_model
        temperature = temperature if temperature is not None else settings.llm_temperature
        
        # 使用当前缓存的 API key（避免在同步方法中调用异步方法）
        api_key = self._current_api_key or settings.llm_api_key
        
        # 创建新实例（不再缓存，因为 API key 可能会变化）
        llm = ChatOpenAI(
            model=model,
            api_key=api_key,
            base_url=settings.llm_base_url,
            temperature=temperature
        )
        
        logger.debug(f"创建 LLM 模型实例: {model}_{temperature}_{api_key}")
        
        return llm
    
    async def chat(self, messages: List, model: str = None, temperature: float = None) -> str:
        """聊天接口（非流式）
        
        Args:
            messages: 消息列表
            model: 模型名称
            temperature: 温度参数
            
        Returns:
            模型响应内容
        """
        llm = self.get_model(model, temperature)
        response = await llm.ainvoke(messages)
        return response.content if hasattr(response, 'content') else str(response)
    
    async def stream(self, messages: List, model: str = None, temperature: float = None) -> AsyncGenerator:
        """流式聊天接口
        
        Args:
            messages: 消息列表
            model: 模型名称
            temperature: 温度参数
            
        Yields:
            响应内容块
        """
        llm = self.get_model(model, temperature)
        async for chunk in llm.astream(messages):
            content = chunk.content if hasattr(chunk, 'content') else str(chunk)
            if content:
                yield content
    
    def clean_response(self, content: str) -> str:
        """清理响应内容，移除思考标签
        
        移除 <think>...</think> 和 <thinking>...</thinking> 标签及其内容。
        
        Args:
            content: 原始内容
            
        Returns:
            清理后的内容
        """
        # 移除 <think>...</think> 标签及其内容
        cleaned = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL)
        
        # 移除 <thinking>...</thinking> 标签及其内容
        cleaned = re.sub(r'<thinking>.*?</thinking>', '', cleaned, flags=re.DOTALL)
        
        # 去除多余的空白字符
        cleaned = cleaned.strip()
        
        return cleaned

