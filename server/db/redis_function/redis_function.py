#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import redis.asyncio as redis
import yaml
import pathlib
import json
from typing import Optional, Any
from server.db.base_storage import BaseStorage
from server.utils.logger import logger

class RedisMiddleware(BaseStorage):
    storage_name = "redis"
    redis_pool: redis.ConnectionPool = None
    client: redis.Redis = None

    def __init__(self, db: int = 0):
        self.db_index = db
        config_path = pathlib.Path(__file__).parent.parent.parent.parent / "src/config/db_config.yaml"
        
        try:
            with open(config_path, 'r', encoding='utf-8') as file:
                config = yaml.safe_load(file)
            
            redis_conf = config.get('redis', {})
            host = redis_conf.get('host', 'localhost')
            port = redis_conf.get('port', 6379)
            password = redis_conf.get('password', None)
            
            # 创建连接池
            self.redis_pool = redis.ConnectionPool(
                host=host,
                port=port,
                password=password,
                db=self.db_index,
                decode_responses=True # 自动解码为字符串
            )
            self.client = redis.Redis(connection_pool=self.redis_pool)
            
        except Exception as e:
            logger.error(f"Redis init failed: {e}")

    async def initialize(self):
        """测试连接"""
        try:
            await self.client.ping()
            logger.info(f"Redis (DB {self.db_index}) connected.")
        except Exception as e:
            logger.error(f"Redis connection failed: {e}")

    async def close(self):
        if self.client:
            await self.client.close()
        if self.redis_pool:
            await self.redis_pool.disconnect()

    async def save_context(self, session_id: str, context: list | dict, expire: int = 3600):
        """
        保存对话上下文
        :param expire: 过期时间，默认1小时
        """
        key = f"context:{session_id}"
        value = json.dumps(context, ensure_ascii=False)
        try:
            await self.client.set(key, value, ex=expire)
        except Exception as e:
            logger.error(f"Redis set error: {e}")

    async def get_context(self, session_id: str) -> Optional[list | dict]:
        """获取对话上下文"""
        key = f"context:{session_id}"
        try:
            data = await self.client.get(key)
            if data:
                return json.loads(data)
            return None
        except Exception as e:
            logger.error(f"Redis get error: {e}")
            return None

    async def delete_context(self, session_id: str):
        key = f"context:{session_id}"
        await self.client.delete(key)