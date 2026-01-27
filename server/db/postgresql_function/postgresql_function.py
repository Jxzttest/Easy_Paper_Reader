#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import yaml
import pathlib
import asyncpg
from typing import Dict, Optional, Any
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker, AsyncEngine
from sqlalchemy.future import select
from sqlalchemy import update, delete
from contextlib import asynccontextmanager

from server.db.base_storage import BaseStorage
from server.db.postgresql_function.models import Base, User, PaperMetadata, Conversation
from server.utils.logger import logger

class PostgresStore(BaseStorage):
    storage_name = "postgresql"
    
    def __init__(self, config_path: Optional[str] = None):
        if config_path is None:
            config_path = pathlib.Path(__file__).parent.parent.parent.parent / "server/config/db_config.yaml"
        
        self._engines: Dict[str, AsyncEngine] = {}
        self._session_makers: Dict[str, async_sessionmaker] = {}
        
        try:
            with open(config_path, 'r', encoding='utf-8') as file:
                config = yaml.safe_load(file)
            
            # 读取所有数据库配置
            databases = config.get('postgresql', {})
            
            # 如果没有配置多个数据库，使用默认配置
            if not databases:
                self._setup_default_database(config.get('database', {}))
            else:
                # 为每个数据库创建引擎
                for db_name, db_config in databases.items():
                    self._create_engine_for_db(db_name, db_config)
            
        except Exception as e:
            logger.error(f"Postgres init failed: {e}")
            raise

    def _setup_default_database(self, pg_conf: Dict[str, Any]):
        """设置默认数据库"""
        user = pg_conf.get('user', 'postgres')
        password = pg_conf.get('password', 'password')
        host = pg_conf.get('host', 'localhost')
        port = pg_conf.get('port', 5432)
        db_name = pg_conf.get('db_name', 'mydb')
        
        dsn = f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{db_name}"
        self._create_engine_for_db('default', dsn)

    def _create_engine_for_db(self, db_name: str, db_config: Dict[str, Any] | str):
        """为指定数据库创建引擎"""
        if isinstance(db_config, dict):
            user = db_config.get('user', 'postgres')
            password = db_config.get('password', 'password')
            host = db_config.get('host', 'localhost')
            port = db_config.get('port', 5432)
            db = db_config.get('db_name', db_name)
            
            dsn = f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{db}"
        else:
            # 如果是DSN字符串，直接使用
            dsn = db_config
        
        engine = create_async_engine(
            dsn, 
            echo=False, 
            pool_size=20, 
            max_overflow=10
        )
        
        session_maker = async_sessionmaker(
            bind=engine, 
            class_=AsyncSession, 
            expire_on_commit=False
        )
        
        self._engines[db_name] = engine
        self._session_makers[db_name] = session_maker
        
        logger.info(f"Created engine for database: {db_name}")

    async def initialize(self, db_name: str = 'default'):
        """初始化指定数据库的表结构；若数据库不存在则自动创建。"""
        if db_name not in self._engines:
            raise ValueError(f"Database '{db_name}' not configured")

        engine: AsyncEngine = self._engines[db_name]
        # 从引擎 DSN 里解析出连接要素
        dsn = str(engine.url)          # 形如 postgresql+asyncpg://user:pwd@host:port/dbname
        raw = dsn.replace("postgresql+asyncpg", "postgresql")  # asyncpg 裸连用
        db = engine.url.database

        # 1. 裸连维护库 postgres
        conn = await asyncpg.connect(raw.replace(f"/{db}", "/postgres"))
        try:
            # 2. 检查数据库是否存在
            row = await conn.fetchrow(
                "SELECT 1 FROM pg_database WHERE datname = $1", db
            )
            if row is None:
                # 3. 不存在则创建
                await conn.execute(f'CREATE DATABASE "{db}"')
                logger.info(f"Auto-created database: {db}")
        finally:
            await conn.close()

        # 4. 继续原有逻辑：建表
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            logger.info(f"Postgres tables checked/created for database: {db_name}")

    async def initialize_all(self):
        """初始化所有数据库的表结构"""
        for db_name in self._engines.keys():
            await self.initialize(db_name)

    async def close(self, db_name: Optional[str] = None):
        """关闭指定数据库的连接，如果未指定则关闭所有"""
        if db_name:
            if db_name in self._engines:
                await self._engines[db_name].dispose()
                del self._engines[db_name]
                del self._session_makers[db_name]
                logger.info(f"Closed connection for database: {db_name}")
        else:
            for engine in self._engines.values():
                await engine.dispose()
            self._engines.clear()
            self._session_makers.clear()
            logger.info("Closed all database connections")

    @asynccontextmanager
    async def get_session(self, db_name: str = 'default'):
        """
        获取指定数据库的Session
        用法:
        async with pg_store.get_session('db1') as session:
            ...
        """
        if db_name not in self._session_makers:
            raise ValueError(f"Database '{db_name}' not configured")
        
        session = self._session_makers[db_name]()
        try:
            yield session
            await session.commit()
        except Exception as e:
            await session.rollback()
            logger.error(f"Database transaction error in {db_name}: {e}")
            raise
        finally:
            await session.close()

    # 以下是针对不同数据库的CRUD操作方法
    async def add_paper_metadata(self, paper_uuid: str, title: str, uploader_uuid: str, 
                                file_path: str, db_name: str = 'paper_metadata'):
        async with self.get_session(db_name) as session:
            new_paper = PaperMetadata(
                paper_uuid=paper_uuid,
                title=title,
                uploader_uuid=uploader_uuid,
                file_path=file_path,
                is_processed=False
            )
            session.add(new_paper)
            return new_paper

    async def mark_paper_processed(self, paper_uuid: str, db_name: str = 'db_name'):
        async with self.get_session(db_name) as session:
            stmt = update(PaperMetadata).where(PaperMetadata.paper_uuid == paper_uuid).values(is_processed=True)
            await session.execute(stmt)

    async def get_paper_metadata(self, paper_uuid: str, db_name: str = 'db_name'):
        async with self.get_session(db_name) as session:
            stmt = select(PaperMetadata).where(PaperMetadata.paper_uuid == paper_uuid)
            result = await session.execute(stmt)
            return result.scalars().first()
    
    async def get_papers_by_uploader(self, uploader_uuid: str, db_name: str = 'db_name'):
        async with self.get_session(db_name) as session:
            stmt = select(PaperMetadata).where(PaperMetadata.uploader_uuid == uploader_uuid)
            result = await session.execute(stmt)
            return result.scalars().all()

    async def get_recent_papers(self, limit: int = 10, db_name: str = 'db_name'):
        async with self.get_session(db_name) as session:
            stmt = select(PaperMetadata).order_by(PaperMetadata.created_at.desc()).limit(limit)
            result = await session.execute(stmt)
            return result.scalars().all()

    # User相关操作
    async def create_user(self, user_uuid: str, username: str, db_name: str = 'users'):
        async with self.get_session(db_name) as session:
            user = User(user_uuid=user_uuid, username=username)
            session.add(user)
            return user

    async def get_user_by_uuid(self, user_uuid: str, db_name: str = 'users'):
        async with self.get_session(db_name) as session:
            stmt = select(User).where(User.user_uuid == user_uuid)
            result = await session.execute(stmt)
            return result.scalars().first()

    # Conversation相关操作
    async def create_conversation(self, session_id: str, user_uuid: str, title: str, 
                                 db_name: str = 'conversations'):
        async with self.get_session(db_name) as session:
            conv = Conversation(
                session_id=session_id,
                user_uuid=user_uuid,
                title=title
            )
            session.add(conv)
            return conv

    async def get_conversations_by_user(self, user_uuid: str, db_name: str = 'conversations'):
        async with self.get_session(db_name) as session:
            stmt = select(Conversation).where(Conversation.user_uuid == user_uuid)
            result = await session.execute(stmt)
            return result.scalars().all()

    # 跨数据库查询的通用方法
    async def execute_query(self, query_func, db_name: str = 'default', **kwargs):
        """
        通用查询方法，允许传入自定义查询函数
        用法:
        async def custom_query(session):
            stmt = select(User).where(User.username.like('%john%'))
            result = await session.execute(stmt)
            return result.scalars().all()
        
        users = await store.execute_query(custom_query, 'db1')
        """
        async with self.get_session(db_name) as session:
            return await query_func(session, **kwargs)

    async def switch_database(self, db_name: str, **kwargs):
        """
        动态切换数据库连接
        用于需要在运行时根据条件选择数据库的场景
        """
        if db_name not in self._engines:
            # 如果数据库配置不存在，尝试动态创建
            await self._add_database_connection(db_name, **kwargs)
        
        return self.get_session(db_name)

    async def _add_database_connection(self, db_name: str, **kwargs):
        """动态添加数据库连接"""
        # 可以从配置文件或传入参数创建连接
        dsn = kwargs.get('dsn')
        if not dsn:
            # 根据传入参数构建DSN
            user = kwargs.get('user', 'postgres')
            password = kwargs.get('password', 'password')
            host = kwargs.get('host', 'localhost')
            port = kwargs.get('port', 5432)
            db = kwargs.get('db', db_name)
            
            dsn = f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{db}"
        
        self._create_engine_for_db(db_name, dsn)