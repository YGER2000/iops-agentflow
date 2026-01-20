# 调用行方接口的客户端
import json
import logging
from typing import List, Dict, Any, Optional
import requests
import re
import os

logger = logging.getLogger(__name__)


class ReqSearchClient:
    def __init__(self, base_url: str, user_id: str,timeout_seconds: int = 8):
        self.base_url = base_url
        self.user_id = user_id
        self.timeout_seconds = timeout_seconds

    async def search(self, query: str, tag: Optional[str]) -> List[Dict[str, Any]]:

        retrival_url = self.base_url
        userId = self.user_id
        headers = {
            "Jumpcloud-Env": "BASE"
        }

        req_data = {
            "REQ_MESSAGE": json.dumps({
                "REQ_HEAD": {
                    "TRAN_PROCESS": "searchSlicing"
                },
                "REQ_BODY": {
                    "body": {
                        "query": query,
                        "userId": userId, #"5000259879",
                        #**({"searchTagFilter": [tag]} if tag else {}),
                        **({"searchTagFilter": [tag]} if tag else {"searchTagFilter": ["数据中心"]}),
                        "sort": "relevance",
                        "searchType": "normal",
                        "matchFields": ["title", "content", "attachTitles", "attachContent"],
                        "ps": 10,
                        "pn": 1,
                        "categoryFilter": "全行-部门事务-工作手册"
                    }
                }
            })
        }

        logger.info(f"检索请求体: {json.dumps(json.loads(req_data['REQ_MESSAGE']), indent=2, ensure_ascii=False)}")
        try:
            response = requests.post(retrival_url, headers=headers, data=req_data)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            logger.error(f"发送请求时出错: {e}")
            return []

        response_json = response.json()
        status = response_json["RSP_BODY"]["status"]
        logger.info(f"检索工具状态: {status}")

        try:
            data_items = response_json["RSP_BODY"]["data"]["data"]

        except KeyError as e:
            logger.error(f"无法找到期望的数据结构: {e}")
            return []

        # 构建最终结果
        result_list = []

        # 遍历每个数据项
        for item in data_items[:5]:
            try:
                title = item["title"]
                # 去除title中的<em>标签
                title = title.replace("<em>", "").replace("</em>", "")
                nid = item["nid"] # "nid": "43cf369360cf4189b8117913324e837f_text_11",
                _, sep, tail = nid.partition('_')
                suffix = '—' + tail
                chunk_title = title + suffix
                para_content = item["para"]
                # 添加到结果列表
                result_list.append({
                    "title": chunk_title,
                    "content": para_content
                })

            except KeyError as e:
                logger.error(f"处理条目时出错，缺少必要字段: {e}")
                continue

        return result_list