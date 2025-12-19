#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from abc import ABC, abstractmethod

class BaseStorage(ABC):
    """
    所有数据库交互类的抽象基类
    """
    storage_name: str = ""

    @abstractmethod
    async def initialize(self):
        """用于初始化连接池或加载配置"""
        pass

    @abstractmethod
    async def close(self):
        """用于关闭连接"""
        pass