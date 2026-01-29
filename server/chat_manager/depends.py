#! /usr/bin/python3
# -*- coding: utf-8 -*-

from fastapi import Depends
from server.db.elasticsearch_function.es_chat import ESChatStore
from server.db.elasticsearch_function.es_paper import ESPaperStore
from server.db.postgresql_function.postgresql_function import PostgresStore
from server.db.db_factory import DBFactory

# 获取postgresql 数据库
def get_postgresql_service()-> PostgresStore:
    return DBFactory.get_pg_service()

# 获取 ES Chat 实例的依赖函数
def get_es_chat_service() -> ESChatStore:
    return DBFactory.get_es_chat_service()

# 获取 ES Paper 实例的依赖函数 (如果 Controller 需要直接搜论文)
def get_es_paper_service() -> ESPaperStore:
    return DBFactory.get_es_paper_service()