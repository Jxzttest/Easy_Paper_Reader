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
                    "is_user": {"type": "boolean"},
                    "timestamp": {"type": "date" }
                }
            }
        }
        self.message_body = self.config_dict['body'].get('message_body', default_mapping)

    async def initialize(self):
        await self._create_index_if_not_exists(self.messages_index, self.message_body)
        

    async def add_message(
        self,
        user_id: str,
        session_id: str,
        role: str,
        content: str,
        parent_message_id: Optional[str] = None,
        agent_info: Optional[Dict] = None,
        tool_calls: Optional[List[Dict]] = None,
        reasoning_steps: Optional[List[Dict]] = None,
        **kwargs
    ) -> str:
        """添加消息到对话中，支持agent和tool调用记录"""
        message_id = str(uuid.uuid4())
        timestamp = datetime.datetime.utcnow().isoformat()
        
        message_data = {
            "message_id": message_id,
            "user_id": user_id,
            "session_id": session_id,
            "parent_message_id": parent_message_id,
            "role": role,
            "content": content,
            "timestamp": timestamp,
            "content_type": kwargs.get("content_type", "text"),
            "content_format": kwargs.get("content_format", "plain_text"),
            "status": kwargs.get("status", "completed"),
            "search_vector": content,  # 用于全文搜索
        }
        
        # 添加agent信息
        if agent_info:
            message_data.update({
                "agent_id": agent_info.get("agent_id"),
                "agent_name": agent_info.get("agent_name"),
                "agent_type": agent_info.get("agent_type"),
                "agent_config": agent_info.get("config", {})
            })
        
        # 添加tool调用信息
        if tool_calls:
            processed_tools = []
            for tool in tool_calls:
                processed_tool = {
                    "tool_call_id": tool.get("tool_call_id", str(uuid.uuid4())),
                    "tool_name": tool.get("tool_name"),
                    "tool_params": tool.get("params", {}),
                    "tool_input": tool.get("input"),
                    "tool_output": tool.get("output"),
                    "tool_error": tool.get("error"),
                    "start_time": tool.get("start_time", timestamp),
                    "end_time": tool.get("end_time"),
                    "duration_ms": tool.get("duration_ms"),
                    "status": tool.get("status", "completed"),
                    "metadata": tool.get("metadata", {})
                }
                processed_tools.append(processed_tool)
            message_data["tool_calls"] = processed_tools
        
        # 添加推理步骤
        if reasoning_steps:
            message_data["reasoning_steps"] = reasoning_steps
        
        # 添加性能指标
        if "tokens_used" in kwargs:
            message_data["tokens_used"] = kwargs["tokens_used"]
        if "latency_ms" in kwargs:
            message_data["latency_ms"] = kwargs["latency_ms"]
        
        # 添加自定义字段
        if "metadata" in kwargs:
            message_data["metadata"] = kwargs["metadata"]
        
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
        user_id: str,
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
                        {"term": {"user_id": user_id}},
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
    