"""API Key 服务

动态获取和管理 LLM API Key。
"""

import logging
import random
import time
from typing import Optional
import httpx
import threading
from app.core.config import settings
from app.core.container import IService
from .interfaces import IApiKeyService

logger = logging.getLogger(__name__)


class ApiKeyService(IService, IApiKeyService):
    """API Key 服务实现
    
    提供动态获取 API key 功能，支持缓存、自动刷新和失败重试。
    """
    
    def __init__(self):
        """初始化 API Key 服务"""
        self._api_key: Optional[str] = None
        self._fetch_time: float = 0
        self._lock_sync = threading.Lock()
        self._http_client_sync: Optional[httpx.Client] = None
        logger.debug("API Key 服务已创建")
    
    async def initialize(self) -> None:
        """初始化服务"""
        # 创建 HTTP 客户端
        self._http_client_sync = httpx.Client(timeout=10.0)
        
        # 如果启用了动态 API key，立即获取一次
        if settings.apikey_service_enabled:
            try:
                self.get_api_key_sync()
                logger.info("API Key 服务初始化完成（已获取初始 API key）")
            except Exception as e:
                logger.warning(f"初始获取 API key 失败，将使用配置文件中的备用值: {e}")
        else:
            logger.info("API Key 服务初始化完成（动态获取已禁用，使用配置文件值）")
    
    async def shutdown(self) -> None:
        """关闭服务"""
        if self._http_client_sync:
            self._http_client_sync.close()
            self._http_client_sync = None
        self._api_key = None
        self._fetch_time = 0
        logger.info("API Key 服务已关闭")

    def get_api_key_sync(self) -> str:
        """获取当前有效的 API key

        如果 API key 即将过期（距离过期时间小于刷新阈值），则自动刷新。
        如果获取失败，返回配置文件中的备用 API key。

        Returns:
            API key 字符串
        """
        # 如果未启用动态获取，直接返回配置文件中的值
        if not settings.apikey_service_enabled:
            return settings.llm_api_key

        with self._lock_sync:
            current_time = time.time()
            time_elapsed = current_time - self._fetch_time
            time_until_refresh = settings.apikey_expire_seconds - settings.apikey_refresh_before_seconds

            # 检查是否需要刷新
            need_refresh = (
                    self._api_key is None or  # 首次获取
                    time_elapsed >= time_until_refresh  # 即将过期
            )

            if need_refresh:
                try:
                    self._api_key = self._fetch_api_key_sync()
                    self._fetch_time = current_time
                    logger.info("API key 已刷新")
                except Exception as e:
                    logger.error(f"获取 API key 失败: {e}")
                    # 如果有旧的 API key，继续使用（即使可能已过期）
                    if self._api_key:
                        logger.warning("使用旧的 API key（可能已过期）")
                        return self._api_key
                    # 否则使用配置文件中的备用值
                    logger.warning("使用配置文件中的备用 API key")
                    return settings.llm_api_key

            return self._api_key

    def refresh_api_key_sync(self) -> str:
        """手动刷新 API key

        强制重新获取 API key，不管当前是否过期。

        Returns:
            新的 API key 字符串
        """
        if not settings.apikey_service_enabled:
            return settings.llm_api_key

        with self._lock_sync:
            try:
                self._api_key = self._fetch_api_key_sync()
                self._fetch_time = time.time()
                logger.info("API key 已手动刷新")
                return self._api_key
            except Exception as e:
                logger.error(f"手动刷新 API key 失败: {e}")
                # 返回备用值
                return settings.llm_api_key

    def _fetch_api_key_sync(self) -> str:
        """从远程服务获取 API key（带重试机制和指数退避）

        Returns:
            API key 字符串

        Raises:
            Exception: 所有重试都失败时抛出异常
        """
        max_retries = 3
        base_delay = 1  # 基础延迟（秒）

        # 准备请求数据
        headers = {
            'Cache-Control': 'no-cache',
            'Jumpcloud-Env': 'BASE'
        }

        # 构造请求体
        req_message = {
            "REQ_HEAD": {},
            "REQ_BODY": {
                "sceneCode": settings.apikey_scene_code
            }
        }

        files = {
            'REQ_MESSAGE': (None, str(req_message).replace("'", '"'), 'application/json')
        }

        last_error = None
        for attempt in range(max_retries):
            try:
                logger.debug(f"正在获取 API key (尝试 {attempt + 1}/{max_retries})...")
                # 修改为POST请求，并使用新的URL和headers
                response = self._http_client_sync.post(
                    settings.apikey_service_url,
                    headers=headers,
                    files=files
                )
                response.raise_for_status()

                data = response.json()
                # 修改响应解析逻辑，从RSP_BODY中获取result
                rsp_body = data.get("RSP_BODY")
                if not rsp_body:
                    raise ValueError("响应中缺少 'RSP_BODY' 字段")

                api_key = rsp_body.get("result")

                if not api_key:
                    raise ValueError("响应中缺少 'result' 字段")

                logger.debug("成功获取 API key")
                return api_key

            except Exception as e:
                last_error = e
                logger.warning(f"获取 API key 失败 (尝试 {attempt + 1}/{max_retries}): {e}")

                # 如果不是最后一次尝试，使用指数退避等待后重试
                if attempt < max_retries - 1:
                    # 指数退避：2^attempt * base_delay
                    exponential_delay = (2 ** attempt) * base_delay
                    # 添加 jitter（±0.5秒的随机延迟）避免雷击效应
                    jitter = random.uniform(-0.5, 0.5)
                    delay = max(0.1, exponential_delay + jitter)  # 确保延迟不小于 0.1 秒

                    logger.debug(f"等待 {delay:.2f} 秒后重试...")
                    time.sleep(delay)

        # 所有重试都失败
        raise Exception(f"获取 API key 失败，已重试 {max_retries} 次: {last_error}")