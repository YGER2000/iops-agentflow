"""检索接口客户端（自包含实现）

重要说明：
- 当前实现沿用既有接口协议/拼接方式，避免影响线上行为与检索召回。

TODO（可选优化）：
- 这里当前用的是 `requests` 同步请求，包了一层 async 方法，会阻塞事件循环；
  如果后续要提升并发/流式体验，建议改为 `httpx.AsyncClient`。
"""

import json
import logging
from typing import List, Dict, Any, Optional

import requests

logger = logging.getLogger(__name__)


class ReqSearchClient:
    """调用检索接口的客户端"""

    def __init__(self, base_url: str, user_id: str, timeout_seconds: int = 8):
        self.base_url = base_url
        self.user_id = user_id
        self.timeout_seconds = timeout_seconds

    async def search(self, query: str, tag: Optional[str]) -> List[Dict[str, Any]]:
        """调用检索接口

        Args:
            query: 查询文本（通常是改写后的 query）
            tag: 可选标签过滤（searchTagFilter）

        Returns:
            List[Dict[str, Any]]: 检索切片列表（最小加工后的结构：title/content）
        """
        retrival_url = self.base_url
        user_id = self.user_id

        headers = {"Jumpcloud-Env": "BASE"}

        req_data = {
            "REQ_MESSAGE": json.dumps(
                {
                    "REQ_HEAD": {"TRAN_PROCESS": "searchSlicing"},
                    "REQ_BODY": {
                        "body": {
                            "query": query,
                            "userId": user_id,
                            # 旧逻辑：tag 为空时默认写死 "数据中心"（保持兼容）
                            **({"searchTagFilter": [tag]} if tag else {"searchTagFilter": ["数据中心"]}),
                            "sort": "relevance",
                            "searchType": "normal",
                            "matchFields": ["title", "content", "attachTitles", "attachContent"],
                            "ps": 10,
                            "pn": 1,
                            "categoryFilter": "全行-部门事务-工作手册",
                        }
                    },
                }
            )
        }

        # 打印请求体用于排查：但注意不要打印敏感信息（此处 userId/base_url 在配置中）
        try:
            logger.info(
                "[req_client] search request | url=%s | payload=%s",
                retrival_url,
                json.dumps(json.loads(req_data["REQ_MESSAGE"]), indent=2, ensure_ascii=False),
            )
        except Exception:
            logger.info("[req_client] search request | url=%s | payload=<unserializable>", retrival_url)

        if not retrival_url:
            logger.warning("[req_client] base_url is empty, return []")
            return []

        try:
            # 注意：requests 是同步调用，这里会阻塞事件循环（保持旧实现以最大化兼容）
            response = requests.post(
                retrival_url,
                headers=headers,
                data=req_data,
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            logger.error("[req_client] request failed | err=%s", e, exc_info=True)
            return []

        try:
            response_json = response.json()
        except Exception as e:
            logger.error("[req_client] response not json | err=%s | text=%s", e, response.text[:500], exc_info=True)
            return []

        try:
            status = response_json["RSP_BODY"]["status"]
            logger.info("[req_client] search status=%s", status)
        except Exception:
            logger.warning("[req_client] response missing status | keys=%s", list(response_json.keys()))

        try:
            data_items = response_json["RSP_BODY"]["data"]["data"]
        except KeyError as e:
            logger.error("[req_client] unexpected response structure | missing=%s | rsp_keys=%s", e, list(response_json.keys()))
            return []

        result_list: List[Dict[str, Any]] = []
        # 旧逻辑只取前 5 条（保持一致）
        for item in data_items[:5]:
            try:
                title = (item.get("title") or "").replace("<em>", "").replace("</em>", "")
                nid = item.get("nid") or ""
                _, _, tail = nid.partition("_")
                suffix = "—" + tail if tail else ""
                chunk_title = title + suffix
                para_content = item.get("para") or ""

                result_list.append({"title": chunk_title, "content": para_content})
            except Exception as e:
                logger.error("[req_client] parse item failed | err=%s | item=%s", e, str(item)[:300], exc_info=True)
                continue

        logger.info("[req_client] search done | result_count=%s", len(result_list))
        logger.debug("[req_client] result_preview=%s", result_list[:2])
        return result_list

