# 调用行方接口的客户端
# 此版本为完整检索上下文
import json
import logging
from typing import List, Dict, Any, Optional
import requests
import re
import os

logger = logging.getLogger(__name__)


class ReqSearchClient:
    def __init__(self, base_url: str, timeout_seconds: int = 8):
        self.base_url = base_url
        self.timeout_seconds = timeout_seconds

    async def search(self, query: str, tag: Optional[str]) -> List[Dict[str, Any]]:

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

        # 按title分组存储结果
        grouped_items: Dict[str, Dict[str, Any]] = {}

        # 遍历每个数据项
        for item in data_items:
            try:
                title = item["title"]
                # 去除title中的<em>标签
                title = title.replace("<em>", "").replace("</em>", "")
                para_items = item.get("paraItems", [])

                # 如果paraItems不存在或为空，跳过该项
                if not para_items:
                    continue

                if title not in grouped_items:
                    grouped_items[title] = {
                        "title": title,
                        "text_chunks": {},
                        "table_chunks": {}
                    }

                # 处理每个段落项
                for para_item in para_items:
                    nid = para_item.get("nid", "")
                    para_content = para_item.get("para", "")
                    # 跳过空内容的段落
                    if not para_content.strip():
                        continue

                    # 处理text类型的nid
                    text_match = re.search(r"text_(\d+)", nid)
                    if text_match:
                        chunk_index = int(text_match.group(1))
                        # 去重，保留每个chunk序号对应的内容
                        if chunk_index not in grouped_items[title]["text_chunks"]:
                            grouped_items[title]["text_chunks"][chunk_index] = para_content
                        continue

                    # 处理table类型的nid
                    table_match = re.search(r"table_(\d+)", nid)
                    if table_match:
                        chunk_index = int(table_match.group(1))
                        # 每个table作为一个独立的片段
                        grouped_items[title]["table_chunks"][chunk_index] = para_content

            except KeyError as e:
                logger.error(f"处理条目时出错，缺少必要字段: {e}")
                continue

        # 构建最终结果
        result_list = []
        for title, item_data in grouped_items.items():
            # 检查是否有chunks内容
            if not item_data["text_chunks"] and not item_data["table_chunks"]:
                continue

            content_parts = []

            # 处理text类型的chunks
            if item_data["text_chunks"]:
                # 按chunk序号排序
                sorted_text_chunks = sorted(item_data["text_chunks"].items())

                # 将连续的chunk合并为片段
                segments = []
                if sorted_text_chunks:
                    current_segment = [sorted_text_chunks[0]]

                    for i in range(1, len(sorted_text_chunks)):
                        prev_index = sorted_text_chunks[i - 1][0]
                        curr_index = sorted_text_chunks[i][0]

                        # 如果当前chunk与前一个chunk序号连续，则合并到同一个片段
                        if curr_index == prev_index + 1:
                            current_segment.append(sorted_text_chunks[i])
                        else:
                            # 否则，结束当前片段，开始新片段
                            segments.append(current_segment)
                            current_segment = [sorted_text_chunks[i]]

                    # 添加最后一个片段
                    segments.append(current_segment)

                # 按指定格式构建text内容
                for i, segment in enumerate(segments):
                    # 合并同一个片段中的所有chunk内容
                    segment_content = "".join([chunk[1] for chunk in segment])
                    # 只有当片段内容不为空时才添加
                    if segment_content.strip():
                        content_parts.append(f":::card 片段{i + 1}\n{segment_content}\n:::")

            # 处理table类型的chunks
            if item_data["table_chunks"]:
                # table类型的chunks每个都是独立的片段
                sorted_table_chunks = sorted(item_data["table_chunks"].items())
                start_index = len(segments) if 'segments' in locals() else 0  # table片段的起始编号

                for i, (chunk_index, chunk_content) in enumerate(sorted_table_chunks):
                    if chunk_content.strip():
                        content_parts.append(f":::card 片段{start_index + i + 1}\n{chunk_content}\n\n:::")

            combined_content = "\n".join(content_parts)

            # 只有当内容不为空时才添加到结果列表
            if combined_content.strip():
                result_list.append({
                    "title": title,
                    "content": combined_content
                })

        return result_list
