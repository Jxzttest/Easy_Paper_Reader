#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import datetime
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
        self.session_body = self.config_dict['body']['session_body']
        self.session_index = self.config_dict['session_index']
        self.messages_index = self.config_dict['messages_index']

    async def initialize(self):
        await self._create_index_if_not_exists(self.session_index, self.session_body)
        await self._create_index_if_not_exists(self.messages_index, self.message_body)

    # --- Session 相关 ---
    async def add_session(self, user_id, session_id):
        now = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        await self.es_connect.index(
            index=self.session_index,
            body={"user_id": user_id, "session_id": session_id, "create_time": now, "title": ""},
            refresh=True
        )
    
    async def add_session_title(self, user_id, session_id, title):
        try:
            search_response = await self.es_connect.search(
                index=self.session_index,
                body={
                    "query": {
                        "bool": {
                            "filter": [
                                {"term": {"user_id": user_id}},
                                {"term": {"session_id": session_id}}
                            ]
                        }
                    }
                }
            )

            # 检查搜索结果
            if search_response['hits']['total']['value'] == 0:
                raise ValueError(f"No document found for user_id: {user_id} and session_id: {session_id}")

            # 获取文档的 ID
            document_id = search_response['hits']['hits'][0]['_id']

            # 更新文档的 title 字段
            update_response = await self.es_connect.update(
                index=self.session_index,
                id=document_id,
                refresh="true",
                body={
                    "doc": {
                        "title": title
                    }
                }
            )
            print(update_response)
            search_response = await self.es_connect.search(
                index=self.session_index,
                body={
                    "query": {
                        "bool": {
                            "filter": [
                                {"term": {"user_id": user_id}},
                                {"term": {"session_id": session_id}}
                            ]
                        }
                    }
                }
            )
            print(search_response)
        except NotFoundError as e:
            logger.error(f"chat_history_{user_id}_{session_id} not in db, can't find title")
        except Exception as e:
            logger.error(f"add title failed: {str(e)}")
            raise HTTPException(status_code=400, detail=f"add title failed: {str(e)}")

    async def get_user_sessions(self, user_id):
        query = {"query": {"term": {"user_id": user_id}}, "sort": [{"create_time": {"order": "desc"}}]}
        res = await self.es_connect.search(index=self.session_index, body=query, size=100)
        return res['hits']['hits']

    async def delete_session(self, user_id, session_id):
        try:
            response = await self.es_connect.delete_by_query(index=self.session_index,
                                                                body={
                                                                    "query": {
                                                                        "bool": {
                                                                            "filter": [
                                                                                {"term": {"user_id": user_id}},
                                                                                {"term": {"session_id": session_id}}
                                                                            ]
                                                                        }
                                                                    }
                                                                })
        except Exception as e:
            logger.info(f"对话{user_id}_{session_id}删除失败 Error occurred: {e}")
            raise HTTPException(status_code=400, detail={"result": f"对话{user_id}_{session_id}删除失败"})
        if response["deleted"] > 0:
            return "success"
        else:
            logger.info(f"对话{user_id}_{session_id}删除失败 Error occurred")
            raise HTTPException(status_code=400, detail={"result": f"对话{user_id}_{session_id}删除失败"})
    
    async def get_session_title(self, user_id, session_id):
        try:
            search_result = await self.es_connect.search(
                index=self.session_index,
                body={
                    "query": {
                        "bool": {
                            "filter": [
                                {"term": {"user_id": user_id}},
                                {"term": {"session_id": session_id}}
                            ]
                        }
                    },
                    "_source": ["title"],
                }
            )
        except NotFoundError as e:
            logger.error(f"chat_history_{user_id}_{session_id} not in db, can't find title")
            raise HTTPException(status_code=400, detail=f"chat_history_{user_id}_{session_id} not in db, can't find title")
        except Exception as e:
            logger.error(f"search session title failed: {str(e)}")
            raise HTTPException(status_code=400, detail=f"search session title failed: {str(e)}")
        if len(search_result['hits']['hits']) == 0:
            return ""
        else:
            return search_result['hits']['hits'][0]['_source']['title']
        
    # --- Message 相关 ---
    async def add_message(self, body):
        await self.es_connect.index(index=self.messages_index, body=body, refresh=True)

    async def get_all_messages(self, user_id, session_id):
        query = {
            "query": {"bool": {"filter": [{"term": {"user_id": user_id}}, {"term": {"session_id": session_id}}]}},
            "sort": [{"timestamp": {"order": "asc"}}],
            "size": 10000
        }
        res = await self.es_connect.search(index=self.messages_index, body=query)
        return res['hits']['hits']

    async def delete_select_message(self, user_id, session_id, message):
        try:
            response = await self.es_connect.delete_by_query(
                index=self.messages_index,
                body={
                    "query": {
                        "bool": {
                            "filter": [
                                {"term": {"user_id": user_id}},
                                {"term": {"session_id": session_id}},
                                {"match_phrase": {"chat_message": message}}
                            ]
                        }
                    }
                },
            )
        except NotFoundError as e:
            logger.error(f"this message: {message} not in db, can't delete")
            return True
        except Exception as e:
            logger.error(f"Delete messages failed: {str(e)}")
            raise HTTPException(status_code=400, detail=f"Delete messages failed: {str(e)}")
        if response["deleted"] > 0:
            return "success"
        else:
            logger.error(f"Delete messages failed")
            raise HTTPException(status_code=400, detail=f"Delete messages failed")

    async def delete_message(self, user_id, session_id):
        try:
            search_response = await self.es_connect.search(
                index=self.messages_index,
                body={
                    "query": {
                        "bool": {
                            "filter": [
                                {"term": {"user_id": user_id}},
                                {"term": {"session_id": session_id}}
                            ]
                        }
                    }
                }
            )
            if search_response['hits']['total']['value'] == 0:
                logger.info("chat_history_{user_id}_{session_id} has no data in db")
                return "success"

            response = await self.es_connect.delete_by_query(
                index=self.messages_index,
                body={
                    "query": {
                        "bool": {
                            "filter": [
                                {"term": {"user_id": user_id}},
                                {"term": {"session_id": session_id}}
                            ]
                        }
                    }
                },
                refresh=False  # 消息删除可接受短暂延迟
            )
        except NotFoundError as e:
            logger.error(f"chat_history_{user_id}_{session_id} not in db, can't delete")
            return True
        except Exception as e:
            logger.error(f"Delete messages failed: {str(e)}")
            raise HTTPException(status_code=400, detail=f"Delete messages failed: {str(e)}")
        if response["deleted"] > 0:
            return "success"
        else:
            logger.error(f"Delete messages failed")
            raise HTTPException(status_code=400, detail=f"Delete messages failed")

    