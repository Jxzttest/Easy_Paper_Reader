#! /usr/bin/python3
#!*--coding:utf-8--*

from pydantic import BaseModel, Field
from typing import List, Dict


class QueryItem(BaseModel):
    query: str = Field("", description="user question")
    user_name: str = Field("", description="user name")
    user_id: str = Field("123456789", description="用户唯一id")
    session_id: str = Field("123456", description="chat session")