#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Agent 系统公共基础层

AgentContext : 一次对话中所有 Agent 共享的状态载体
               集成 MemoryManager（四层记忆）和 ContextBuilder（消息组装）
AgentBase    : 所有子 Agent 的抽象基类
"""

import datetime
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Dict, List, Optional

from server.utils.logger import logger


# ── 共享上下文 ────────────────────────────────────────────────────────────────
@dataclass
class AgentContext:
    """
    一次对话/任务中所有 Agent 共享的上下文。

    内部通过 MemoryManager 管理四层记忆；
    对外提供向后兼容的 messages / add_message / to_history_text 接口。
    """
    session_id: str
    paper_uuids: List[str] = field(default_factory=list)

    # ── 向后兼容：messages 仍可直接使用（由 ContextBuilder 组装时合并）──────
    messages: List[Dict] = field(default_factory=list)

    # Agent 执行记录
    agent_trace: List[Dict] = field(default_factory=list)

    # 共享知识库：各 Agent 可向此写入中间结论
    shared_memory: Dict[str, Any] = field(default_factory=dict)

    # 最终聚合结果
    final_answer: str = ""

    # MemoryManager 实例（在 chat_api 中初始化后赋值）
    memory: Optional[Any] = field(default=None, repr=False)

    # ── 向后兼容接口 ──────────────────────────────────────────────────────────

    def add_message(self, role: str, content: str) -> None:
        """添加消息到运行时 messages 列表（向后兼容）。"""
        self.messages.append({"role": role, "content": content})

    def get_recent_messages(self, n: int = 10) -> List[Dict]:
        return self.messages[-n:]

    def to_history_text(self, n: int = 6) -> str:
        """生成历史文本，优先从 MemoryManager 取，否则降级到 messages 列表。"""
        if self.memory is not None:
            from server.agent.memory.context_builder import ContextBuilder
            return ContextBuilder.to_history_text(self.memory, n=n)
        # 降级
        lines = []
        for m in self.get_recent_messages(n):
            role = "用户" if m["role"] == "user" else "助手"
            lines.append(f"{role}：{m['content']}")
        return "\n".join(lines)

    def build_messages_for_llm(
        self,
        current_input: str = "",
        include_working: bool = True,
    ) -> List[Dict]:
        """
        组装完整的 LLM messages。
        如果 memory 已初始化，走四层记忆路径；否则返回原始 messages。
        """
        if self.memory is not None:
            from server.agent.memory.context_builder import ContextBuilder
            return ContextBuilder.build(
                self.memory,
                current_input=current_input or (self.messages[-1]["content"] if self.messages else ""),
                include_working=include_working,
            )
        return self.messages

    def build_messages_for_subagent(self, agent_task: str, n_history: int = 4) -> List[Dict]:
        """为子 Agent 组装精简上下文。"""
        if self.memory is not None:
            from server.agent.memory.context_builder import ContextBuilder
            return ContextBuilder.build_for_subagent(self.memory, agent_task, n_history)
        return self.messages[-n_history:] + [{"role": "user", "content": agent_task}]

    async def save_working_memory(self, key: str, content: str, metadata: Dict = None) -> None:
        """将 Agent 的执行结果写入工作记忆层。"""
        if self.memory is not None:
            await self.memory.add_working_memory(content, key=key, metadata=metadata)

    async def save_history_turn(self, role: str, content: str) -> None:
        """将一条消息写入历史记忆层（同时触发自动压缩检查）。"""
        if self.memory is not None:
            await self.memory.add_history_turn(role, content)

    def record_trace(self, agent_name: str, step: str, status: str, output: Any = None) -> None:
        self.agent_trace.append({
            "agent": agent_name,
            "step": step,
            "status": status,
            "output": str(output)[:500] if output else "",
            "timestamp": datetime.datetime.utcnow().isoformat(),
        })


# ── Agent 基类 ────────────────────────────────────────────────────────────────
class AgentBase(ABC):
    """
    所有子 Agent 的抽象基类。

    子类只需实现：
      - name        : Agent 唯一名称
      - description : 功能描述
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
        """子类实现核心逻辑，返回 dict，必须包含 'summary' 键。"""
        ...

    async def _invoke(self, messages: List[Dict], temperature: float = 0.7) -> str:
        """直接传入 messages 调用 LLM（子 Agent 内部使用）。"""
        return await self.llm.invoke(messages, temperature=temperature)

    async def _invoke_with_context(
        self,
        ctx: AgentContext,
        agent_task: str,
        temperature: float = 0.7,
        n_history: int = 4,
    ) -> str:
        """
        携带四层记忆上下文调用 LLM。
        子 Agent 应优先使用此方法，而非直接拼接 messages。
        """
        messages = ctx.build_messages_for_subagent(agent_task, n_history=n_history)
        return await self.llm.invoke(messages, temperature=temperature)

    async def _stream(self, messages: List[Dict]) -> AsyncGenerator[str, None]:
        async for chunk in self.llm.stream(messages):
            yield chunk
