#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
context_manager.py —— 已迁移到 server/agent/memory/ 模块

新架构：
  MemoryManager  → server/agent/memory/memory_manager.py   四层记忆管理
  ContextBuilder → server/agent/memory/context_builder.py  消息组装

本文件保留为向后兼容入口，直接重导出新模块。
"""

from server.agent.memory.memory_manager import (  # noqa: F401
    MemoryManager,
    LAYER_SYSTEM,
    LAYER_USER_INTENT,
    LAYER_WORKING,
    LAYER_HISTORY,
)
from server.agent.memory.context_builder import ContextBuilder  # noqa: F401
