#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import pathlib
import yaml
import asyncio
from typing import Dict
from collections import defaultdict
from elasticsearch import AsyncElasticsearch
from server.db.base_storage import BaseStorage
from server.utils.logger import logger

# 共享锁，防止多个服务实例同时创建同一个索引
index_locks: Dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

class ElasticsearchBase(BaseStorage):
    """
    ES 基础类：负责建立连接、加载配置、基础索引创建
    """
    es_connect: AsyncElasticsearch = None
    config_dict: dict = {}

    def __init__(self):
        self._load_config()
        self._init_client()

    def _load_config(self):
        config_path = pathlib.Path(__file__).parent.parent.parent.parent / "server/config/db_config.yaml"
        try:
            with open(config_path, 'r', encoding='utf-8') as file:
                self.config_dict = yaml.safe_load(file)['elasticsearch']
        except Exception as e:
            logger.error(f"ES Config load failed: {e}")
            raise

    def _init_client(self):
        try:
            ip = self.config_dict['ip']
            passwd = self.config_dict['password']
            user = self.config_dict['user']
            verify_certs = self.config_dict.get('verify_certs', False)

            self.es_connect = AsyncElasticsearch(
                hosts=ip, 
                verify_certs=verify_certs, 
                basic_auth=(user, passwd),
                request_timeout=30
            )
        except Exception as e:
            logger.error(f"ES Connection failed: {e}")
            raise

    async def initialize(self):
        """子类需调用或重写此方法以初始化特定索引"""
        pass

    async def close(self):
        if self.es_connect:
            await self.es_connect.close()

    async def _create_index_if_not_exists(self, index_name: str, body: dict):
        """通用创建索引方法"""
        if not self.es_connect: return
        
        async with index_locks[index_name]:
            if await self.es_connect.indices.exists(index=index_name):
                return
            try:
                await self.es_connect.indices.create(index=index_name, body=body)
                logger.info(f"Index {index_name} created.")
            except Exception as e:
                logger.error(f"Create index {index_name} error: {e}")