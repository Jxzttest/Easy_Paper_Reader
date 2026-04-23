#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ContextBuilder —— 将四层记忆组装为 LLM messages 列表

组装顺序（对应优先级从高到低）：
  1. system message  ← Layer 0 (system) + Layer 2 (working) 注入
  2. history messages ← Layer 3 (history)，摘要块以 system 消息插入
  3. user_intent     ← Layer 1 (user_intent) 作为最新 user 消息的前缀

最终结构：
  [
    {"role": "system", "content": "<系统提示> + <工作记忆>"},
    {"role": "system", "content": "[历史摘要] ..."},   # 如有压缩摘要
    {"role": "user",   "content": "..."},               # 历史用户消息
    {"role": "assistant", "content": "..."},            # 历史助手回复
    ...
    {"role": "user", "content": "[当前意图] ...\n\n<user_input>"},  # 最新输入
  ]
"""

from typing import Dict, List

from server.agent.memory.memory_manager import MemoryManager


class ContextBuilder:
    """
    无状态工具类，将 MemoryManager 的内容转换为 LLM API 需要的 messages 格式。
    """

    @staticmethod
    def build(
        memory: MemoryManager,
        current_input: str,
        include_working: bool = True,
    ) -> List[Dict]:
        """
        组装完整的 messages 列表。

        Args:
            memory:          已 load() 的 MemoryManager
            current_input:   用户当前输入（将作为最后一条 user 消息）
            include_working: 是否将工作记忆注入 system prompt（默认 True）
        """
        messages: List[Dict] = []

        # ── 1. System 消息（系统提示 + 工作记忆）────────────────────────────
        system_content = memory.get_system_content()
        if include_working:
            working = memory.get_working_context()
            if working:
                system_content += f"\n\n## 当前工作记忆\n{working}"

        if system_content.strip():
            messages.append({"role": "system", "content": system_content})

        # ── 2. 历史对话（含摘要块）──────────────────────────────────────────
        history = memory.get_history_messages()
        messages.extend(history)

        # ── 3. 当前用户输入（附加意图前缀）─────────────────────────────────
        intent = memory.get_user_intent_content()
        if intent and intent.strip():
            user_content = f"[当前任务意图]\n{intent}\n\n---\n\n{current_input}"
        else:
            user_content = current_input

        messages.append({"role": "user", "content": user_content})
        return messages

    @staticmethod
    def build_for_subagent(
        memory: MemoryManager,
        agent_task: str,
        n_history: int = 4,
    ) -> List[Dict]:
        """
        为子 Agent（RAGAgent / WritingAgent 等）构建精简上下文。
        只包含：系统提示 + 最近 N 条历史 + 当前子任务描述。
        减少 token 消耗，适合子 Agent 内部调用。

        Args:
            agent_task: 当前子 Agent 的具体任务描述（由 Orchestrator 传入）
            n_history:  最多携带多少条历史消息
        """
        messages: List[Dict] = []

        # System
        system_content = memory.get_system_content()
        working = memory.get_working_context()
        if working:
            system_content += f"\n\n## 当前工作记忆\n{working}"
        if system_content.strip():
            messages.append({"role": "system", "content": system_content})

        # 最近 N 条历史（只取普通对话，跳过摘要）
        all_hist = memory.get_history_messages()
        recent = [m for m in all_hist if m["role"] != "system"][-n_history:]
        messages.extend(recent)

        # 当前子任务
        messages.append({"role": "user", "content": agent_task})
        return messages

    @staticmethod
    def to_history_text(memory: MemoryManager, n: int = 6) -> str:
        """
        生成纯文本历史摘要，供 SupervisorAgent prompt 注入。
        替代原来的 ctx.to_history_text()。
        """
        history = memory.get_history_messages()
        lines = []
        for m in history[-n:]:
            role_label = "用户" if m["role"] == "user" else ("系统" if m["role"] == "system" else "助手")
            content_preview = m["content"][:200] + ("..." if len(m["content"]) > 200 else "")
            lines.append(f"{role_label}：{content_preview}")
        return "\n".join(lines)
