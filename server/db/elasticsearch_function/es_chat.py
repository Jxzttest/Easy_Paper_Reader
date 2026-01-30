#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import datetime
import uuid
from typing import Optional, List, Dict, Any
from fastapi import HTTPException
from elasticsearch.exceptions import NotFoundError
from server.db.elasticsearch_function.es_base import ElasticsearchBase
from server.utils.logger import logger

class ESChatStore(ElasticsearchBase):
    storage_name = "es_chat"

    def __init__(self):
        super().__init__()
        # 从配置中提取特定字段
        self.message_body = self.config_dict['body']['message_body']
        self.messages_index = self.config_dict['messages_index']

        default_mapping = {
            "mappings": {
                "properties": {
                    "user_id": {"type": "keyword"},
                    "session_id": {"type": "keyword"},
                    "message_id": {"type": "keyword"},
                    "chat_message": {"type": "text", "analyzer": "standard"},
                    "timestamp": {"type": "date" }
                }
            }
        }
        self.message_body = self.config_dict['body'].get('message_body', default_mapping)

    async def initialize(self):
        await self._create_index_if_not_exists(self.messages_index, self.message_body)

    async def add_message(
        self,
        user_uuid: str,
        session_id: str,
        role: str,
        content: str,
        parent_message_id: Optional[str] = None,
    ) -> str:
        """添加消息到对话中，支持agent和tool调用记录"""
        message_id = "chat_message_" + str(uuid.uuid4())
        timestamp = datetime.datetime.utcnow().isoformat()
        
        message_data = {
            "message_id": message_id,
            "user_id": user_uuid,
            "session_id": session_id,
            "parent_message_id": parent_message_id,
            "role": role,
            "content": content,
            "timestamp": timestamp,
        }
        try:
            await self.es_connect.index(
                index=self.messages_index,
                body=message_data,
                refresh=True
            )
            return message_id
        except Exception as e:
            logger.error(f"Add message failed: {e}")
            raise HTTPException(status_code=500, detail=f"Add message failed: {str(e)}")
   
    async def search_messages(
        self,
        user_uuid: str,
        query: str,
        fields: List[str] = ["content", "search_vector"],
        session_id: Optional[str] = None,
        role: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        size: int = 20
    ) -> List[Dict]:
        """搜索消息内容"""
        search_query = {
            "query": {
                "bool": {
                    "must": [
                        {"term": {"user_id": user_uuid}},
                        {
                            "multi_match": {
                                "query": query,
                                "fields": fields,
                                "type": "best_fields"
                            }
                        }
                    ]
                }
            },
            "highlight": {
                "fields": {
                    "content": {},
                    "search_vector": {}
                }
            },
            "size": size
        }
        
        if session_id:
            search_query["query"]["bool"]["must"].append({"term": {"session_id": session_id}})
        
        if role:
            search_query["query"]["bool"]["must"].append({"term": {"role": role}})
        
        if start_time and end_time:
            search_query["query"]["bool"]["filter"] = {
                "range": {
                    "timestamp": {
                        "gte": start_time,
                        "lte": end_time
                    }
                }
            }
        
        try:
            res = await self.es_connect.search(index=self.messages_index, body=search_query)
            return [
                {
                    "message": hit['_source'],
                    "highlight": hit.get('highlight', {})
                }
                for hit in res['hits']['hits']
            ]
        except Exception as e:
            logger.error(f"Search messages failed: {e}")
            return []

    async def get_message_tree(
        self,
        message_id: str,
        max_depth: int = 10
    ) -> Dict:
        """获取消息树（用于追踪对话链）"""
        try:
            # 获取指定消息
            search_response = await self.es_connect.search(
                index=self.messages_index,
                body={
                    "query": {
                        "term": {"message_id": message_id}
                    }
                }
            )
            
            if not search_response['hits']['hits']:
                return {}
            
            root_message = search_response['hits']['hits'][0]['_source']
            tree = {
                "message": root_message,
                "children": []
            }
            
            # 递归获取子消息
            await self._build_message_tree(tree, max_depth - 1)
            
            return tree
        except Exception as e:
            logger.error(f"Get message tree failed: {e}")
            return {}
    
    async def _build_message_tree(self, node: Dict, depth: int):
        """递归构建消息树"""
        if depth <= 0:
            return
        
        current_message_id = node["message"]["message_id"]
        
        # 查找以当前消息为父消息的所有消息
        search_response = await self.es_connect.search(
            index=self.messages_index,
            body={
                "query": {
                    "term": {"parent_message_id": current_message_id}
                }
            }
        )
        
        for hit in search_response['hits']['hits']:
            child_node = {
                "message": hit['_source'],
                "children": []
            }
            node["children"].append(child_node)
            
            # 递归处理子节点
            await self._build_message_tree(child_node, depth - 1)
    
    async def delete_message(self, user_uuid: str, message_id: str):
        try:
            response = await self.es_connect.delete_by_query(index=self.messages_index,
                                                            body={
                                                                "query": {
                                                                    "bool": {
                                                                        "filter": [
                                                                            {"term": {"user_id": user_uuid}},
                                                                            {"term": {"message_id": message_id}}
                                                                        ]
                                                                    }
                                                                }
                                                            })
        except Exception as e:
            logger.info(f"对话{user_uuid}_{message_id}删除失败 Error occurred: {e}")
            raise HTTPException(status_code=400, detail={"result": f"对话{user_uuid}_{message_id}删除失败"})
        if response["deleted"] > 0:
            return "success"
        else:
            logger.info(f"对话{user_uuid}_{message_id}删除失败 Error occurred")
            raise HTTPException(status_code=400, detail={"result": f"对话{user_uuid}_{message_id}删除失败"})