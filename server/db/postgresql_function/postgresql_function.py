#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import yaml
import pathlib
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.future import select
from sqlalchemy import update, delete
from contextlib import asynccontextmanager

from server.db.base_storage import BaseStorage
from server.db.postgresql_function.models import Base, User, PaperMetadata
from server.utils.logger import logger

class PostgresStore(BaseStorage):
    storage_name = "postgresql"
    
    def __init__(self):
        config_path = pathlib.Path(__file__).parent.parent.parent.parent / "server/config/db_config.yaml"
        
        try:
            with open(config_path, 'r', encoding='utf-8') as file:
                config = yaml.safe_load(file)
            
            pg_conf = config.get('postgresql', {})
            user = pg_conf.get('user', 'postgres')
            password = pg_conf.get('password', 'password')
            host = pg_conf.get('host', 'localhost')
            port = pg_conf.get('port', 5432)
            db_name = pg_conf.get('db_name', 'mydb')
            
            # 使用 asyncpg 驱动
            dsn = f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{db_name}"
            
            self.engine = create_async_engine(
                dsn, 
                echo=False, 
                pool_size=20, 
                max_overflow=10
            )
            self.SessionLocal = async_sessionmaker(
                bind=self.engine, 
                class_=AsyncSession, 
                expire_on_commit=False
            )
            
        except Exception as e:
            logger.error(f"Postgres init failed: {e}")
            raise

    async def initialize(self):
        """创建表结构 (生产环境建议使用 Alembic 迁移)"""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            logger.info("Postgres tables checked/created.")

    async def close(self):
        await self.engine.dispose()

    @asynccontextmanager
    async def get_session(self):
        """
        提供事务上下文的 Session 生成器
        用法:
        async with pg_store.get_session() as session:
            ...
        """
        session = self.SessionLocal()
        try:
            yield session
            await session.commit()
        except Exception as e:
            await session.rollback()
            logger.error(f"Database transaction error: {e}")
            raise
        finally:
            await session.close()


    async def add_paper_metadata(self, paper_uuid: str, title: str, uploader_uuid: str, file_path: str):
        async with self.get_session() as session:
            new_paper = PaperMetadata(
                paper_uuid=paper_uuid,
                title=title,
                uploader_uuid=uploader_uuid,
                file_path=file_path,
                is_processed=False
            )
            session.add(new_paper)

    async def mark_paper_processed(self, paper_uuid: str):
        async with self.get_session() as session:
            stmt = update(PaperMetadata).where(PaperMetadata.paper_uuid == paper_uuid).values(is_processed=True)
            await session.execute(stmt)

    async def get_paper_metadata(self, paper_uuid: str):
        async with self.get_session() as session:
            stmt = select(PaperMetadata).where(PaperMetadata.paper_uuid == paper_uuid)
            result = await session.execute(stmt)
            return result.scalars().first()