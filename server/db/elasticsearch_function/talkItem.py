#! /usr/bin/python3
#!*--coding:utf-8--*

from pydantic import BaseModel, Field


class TalkItem(BaseModel):
    user_id: str = Field("123456789", description="用户唯一id")
    session_id: str = Field("123456", description="chat session")
    new_title: str = Field("", description="新标题，大部分情况不会使用")
    # chat_message: str = Field("", description="待删除的chat message字段，大部分情况不会使用")