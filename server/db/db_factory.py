#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import Optional

# 导入具体的服务类
from server.db.elasticsearch_function.es_chat import ESChatStore
from server.db.elasticsearch_function.es_paper import ESPaperStore
from server.db.elasticsearch_function.es_agent import ESAgentStore
from server.db.redis_function.redis_function import RedisMiddleware
from server.db.postgresql_function.postgresql_function import PostgresStore
from server.utils.logger import logger

class DBFactory:
    """
    数据库工厂类 (Singleton Pattern)
    负责统一管理数据库服务的实例，避免重复创建连接。
    """
    _es_agent: Optional[ESAgentStore] = None
    _es_chat: Optional[ESChatStore] = None
    _es_paper: Optional[ESPaperStore] = None
    _redis: Optional[RedisMiddleware] = None
    _pg: Optional[PostgresStore] = None

    @classmethod
    async def init_all(cls):
        """
        应用启动时调用，初始化所有连接和索引
        """
        logger.info("Initializing Database Factory...")
        
        # 实例化并初始化 ES Chat
        if not cls._es_chat:
            cls._es_chat = ESChatStore()
            await cls._es_chat.initialize()
            
        # 实例化并初始化 ES Paper
        if not cls._es_paper:
            cls._es_paper = ESPaperStore()
            await cls._es_paper.initialize()

        # 实例化 Redis
        if not cls._redis:
            cls._redis = RedisMiddleware()
            await cls._redis.initialize()
            
        # 实例化 PG
        if not cls._pg:
            cls._pg = PostgresStore()
            await cls._pg.initialize()
            
        logger.info("Database Factory initialized successfully.")

    @classmethod
    async def close_all(cls):
        """应用关闭时调用，清理资源"""
        if cls._es_chat: await cls._es_chat.close()
        if cls._es_paper: await cls._es_paper.close()
        if cls._redis: await cls._redis.close()
        if cls._pg: await cls._pg.close()

    @classmethod
    def get_es_chat_service(cls) -> ESChatStore:
        if not cls._es_chat:
            # 懒加载兜底，但推荐在 main.py startup 中显式调用 init_all
            cls._es_chat = ESChatStore() 
        return cls._es_chat

    @classmethod
    def get_es_agent_service(cls) -> ESAgentStore:
        if not cls._es_agent:
            cls._es_agent = ESAgentStore()
        return cls._es_agent

    @classmethod
    def get_es_paper_service(cls) -> ESPaperStore:
        if not cls._es_paper:
            cls._es_paper = ESPaperStore()
        return cls._es_paper

    @classmethod
    def get_redis_service(cls) -> RedisMiddleware:
        if not cls._redis:
            cls._redis = RedisMiddleware()
        return cls._redis

    @classmethod
    def get_pg_service(cls) -> PostgresStore:
        if not cls._pg:
            cls._pg = PostgresStore()
        return cls._pg