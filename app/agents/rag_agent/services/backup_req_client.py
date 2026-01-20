# 调用行方接口的客户端
import json
import logging
from typing import List, Dict, Any, Optional
import requests
import httpx

logger = logging.getLogger(__name__)

class ReqSearchClient:
    def __init__(self, base_url: str, timeout_seconds: int = 8):
        self.base_url = base_url
        self.timeout_seconds = timeout_seconds

    async def search(self, query: str, tag: Optional[ str]) -> List[Dict[str, Any]]:

        retrival_url = (
            self.base_url or "http://12.244.203.235:9099/OKIC.OKIC-CNUN.V-1.0/searchSlicing.bocms"
        )

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
                        "userId": "5000259879",
                        #"searchTagFilter": tag,
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

        try:
            response = requests.post(retrival_url, headers=headers, data=req_data)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            logger.error(f"发送请求时出错: {e}")
            return {"error": "发送请求时出错"}

        response_json = response.json()
        status = response_json["RSP_BODY"]["status"]
        logger.info(f"检索工具状态: {status}")


        result_list = []
        para_num = 3

        try:
            data_items = response_json["RSP_BODY"]["data"]["data"]

        except KeyError as e:
            logger.error(f"无法找到期望的数据结构: {e}")
            return result_list

        # 遍历每个数据项
        for item in data_items:
            try:
                title = item["title"]
                para_items = item["paraItems"]

                # 提取前para_num个段落并拼接
                paras = []
                for i in range(min(para_num, len(para_items))):
                    paras.append(para_items[i]["para"])

                # 将段落拼接成一个完整字符串
                combined_para = "".join(paras)
                result_list.append({
                    "title": title,
                    "content": combined_para
                })

            except KeyError as e:
                logger.error(f"处理条目时出错，缺少必要字段: {e}")
                continue
        #logger.debug(f"检索结果: {result_list}")
        return result_list