#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import Optional
from server.db.sqlite_function.sqlite_store import SQLiteStore
from server.db.chroma_function.chroma_store import ChromaVectorStore
from server.utils.logger import logger


class DBFactory:
    """
    数据库工厂（单例）。
    存储方案：SQLite（元数据+对话+任务）+ ChromaDB（向量检索）。
    无需 Redis / PostgreSQL / Elasticsearch 外部服务。
    """
    _sqlite: Optional[SQLiteStore] = None
    _chroma: Optional[ChromaVectorStore] = None

    @classmethod
    async def init_all(cls):
        logger.info("[DBFactory] Initializing lightweight storage...")

        if not cls._sqlite:
            cls._sqlite = SQLiteStore()
            await cls._sqlite.initialize()

        if not cls._chroma:
            cls._chroma = ChromaVectorStore()
            await cls._chroma.initialize()

        logger.info("[DBFactory] All storage initialized.")

    @classmethod
    async def close_all(cls):
        if cls._sqlite:
            await cls._sqlite.close()
            cls._sqlite = None
        if cls._chroma:
            await cls._chroma.close()
            cls._chroma = None
        logger.info("[DBFactory] All storage closed.")

    @classmethod
    def get_sqlite(cls) -> SQLiteStore:
        if not cls._sqlite:
            raise RuntimeError("DBFactory not initialized. Call await DBFactory.init_all() first.")
        return cls._sqlite

    @classmethod
    def get_vector_store(cls) -> ChromaVectorStore:
        if not cls._chroma:
            raise RuntimeError("DBFactory not initialized. Call await DBFactory.init_all() first.")
        return cls._chroma

    # ── 向下兼容旧调用名（逐步迁移期间使用） ──────────────────────────── #
    @classmethod
    def get_es_paper_service(cls) -> ChromaVectorStore:
        return cls.get_vector_store()

    @classmethod
    def get_pg_service(cls) -> SQLiteStore:
        return cls.get_sqlite()
