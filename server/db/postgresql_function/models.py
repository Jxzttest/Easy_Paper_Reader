#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean, ForeignKey
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.sql import func
import datetime

Base = declarative_base()

class User(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_uuid = Column(String(64), unique=True, index=True, nullable=False)
    username = Column(String(100), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # 关系
    papers = relationship("PaperMetadata", back_populates="uploader")

class PaperMetadata(Base):
    """
    论文元数据表，不存全文，全文在ES
    """
    __tablename__ = 'paper_metadata'

    id = Column(Integer, primary_key=True, autoincrement=True)
    paper_uuid = Column(String(64), unique=True, index=True, nullable=False) # 对应 ES 中的 paper_id
    title = Column(String(512), nullable=False)
    authors = Column(Text, nullable=True)     # JSON string or comma separated
    publish_year = Column(Integer, nullable=True)
    file_path = Column(String(1024), nullable=True) # 原始PDF存储路径
    is_processed = Column(Boolean, default=False)   # OCR/ES入库状态
    
    uploader_uuid = Column(String(64), ForeignKey('users.user_uuid'))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    uploader = relationship("User", back_populates="papers")

class Conversation(Base):
    """
    结构化对话记录 (用于PG中的统计或快速列表查询，详细日志在ES)
    """
    __tablename__ = 'conversations'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(64), unique=True, index=True)
    user_uuid = Column(String(64), index=True)
    title = Column(String(256))
    start_time = Column(DateTime(timezone=True), server_default=func.now())