#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Agent 系统公共基础层

AgentContext : 一次对话中所有 Agent 共享的状态载体
AgentBase    : 所有子 Agent 的抽象基类
"""

import datetime
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Dict, List, Optional

from server.utils.logger import logger


# ── 共享上下文 ────────────────────────────────────────────────────────────
@dataclass
class AgentContext:
    """
    一次对话/任务中所有 Agent 共享的上下文。

    设计原则：
      - 只读字段（session_id、user_uuid 等）在构造时确定。
      - 可写字段（messages、memory、results）由各 Agent 追加，不覆盖。
      - paper_uuids 是本次对话关联的论文列表，用于 RAG 检索时过滤。
    """
    session_id: str
    user_uuid: str
    paper_uuids: List[str] = field(default_factory=list)   # 关联论文

    # 对话历史（OpenAI message 格式）
    messages: List[Dict] = field(default_factory=list)

    # Agent 执行记录：[{agent, step, status, output, timestamp}]
    agent_trace: List[Dict] = field(default_factory=list)

    # 共享知识库：各 Agent 可向此写入中间结论，供后续 Agent 读取
    shared_memory: Dict[str, Any] = field(default_factory=dict)

    # 最终聚合结果（由 Orchestrator 填充）
    final_answer: str = ""

    def add_message(self, role: str, content: str) -> None:
        self.messages.append({"role": role, "content": content})

    def record_trace(self, agent_name: str, step: str, status: str, output: Any = None) -> None:
        self.agent_trace.append({
            "agent": agent_name,
            "step": step,
            "status": status,
            "output": str(output)[:500] if output else "",   # 截断，只存摘要
            "timestamp": datetime.datetime.utcnow().isoformat(),
        })

    def get_recent_messages(self, n: int = 10) -> List[Dict]:
        return self.messages[-n:]

    def to_history_text(self, n: int = 6) -> str:
        """将最近 n 条消息转成纯文本，便于拼入 prompt。"""
        lines = []
        for m in self.get_recent_messages(n):
            role = "用户" if m["role"] == "user" else "助手"
            lines.append(f"{role}：{m['content']}")
        return "\n".join(lines)


# ── Agent 基类 ────────────────────────────────────────────────────────────
class AgentBase(ABC):
    """
    所有子 Agent 的抽象基类。

    子类只需实现：
      - name        : Agent 唯一名称
      - description : 功能描述（供 Supervisor 路由时参考）
      - run(ctx)    : 核心执行逻辑，读写 ctx，返回执行结果
    """

    name: str = "base_agent"
    description: str = ""

    def __init__(self):
        from server.model.llm_model.llm_function import LLMManager
        self.llm = LLMManager()

    async def execute(self, ctx: AgentContext, **kwargs) -> Dict:
        """统一入口：记录 trace + 调用 run()。"""
        logger.info(f"[{self.name}] execute start")
        ctx.record_trace(self.name, "start", "running")
        try:
            result = await self.run(ctx, **kwargs)
            ctx.record_trace(self.name, "end", "success", result.get("summary", ""))
            logger.info(f"[{self.name}] execute success")
            return result
        except Exception as e:
            ctx.record_trace(self.name, "end", "failed", str(e))
            logger.error(f"[{self.name}] execute failed: {e}", exc_info=True)
            raise

    @abstractmethod
    async def run(self, ctx: AgentContext, **kwargs) -> Dict:
        """子类实现核心逻辑，返回 dict，必须包含 'summary' 键（供 CheckAgent 评估）。"""
        ...

    async def _invoke(self, messages: List[Dict], temperature: float = 0.7) -> str:
        return await self.llm.invoke(messages, temperature=temperature)

    async def _stream(self, messages: List[Dict]) -> AsyncGenerator[str, None]:
        async for chunk in self.llm.stream(messages):
            yield chunk
