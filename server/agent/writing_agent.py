#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
WritingAgent —— 论文写作 / 润色

支持多种写作模式（由 Supervisor 的 intent 决定）：
  innovation : 梳理创新点
  draft      : 撰写新内容（摘要、段落、章节）
  polish     : 修改润色
  general    : 通用学术写作
"""

from typing import Dict
from server.agent.base import AgentBase, AgentContext

# 各模式的任务前缀（注入到 agent_task 中，由 ContextBuilder 合并系统提示）
_MODE_PROMPTS = {
    "innovation": (
        "【任务模式：创新点梳理】\n"
        "请基于以下论文检索内容，系统地梳理该论文的核心创新点。\n"
        "要求：结构清晰（用序号列出），指出每个创新点相比已有工作的突破，"
        "语言严谨、客观。"
    ),
    "draft": (
        "【任务模式：学术写作】\n"
        "请根据用户要求和提供的参考内容，撰写高质量的学术文字。\n"
        "要求：语言正式、逻辑严密、符合学术规范，避免口语化表达。"
    ),
    "polish": (
        "【任务模式：润色修改】\n"
        "请对用户提供的文字进行修改润色。\n"
        "要求：保留原意，提升语言表达的准确性和流畅性，修正语法错误，"
        "使其符合顶级期刊写作标准。请先给出修改后版本，再简要说明主要改动。"
    ),
    "general": (
        "【任务模式：通用学术助手】\n"
        "请根据用户的需求提供高质量的学术帮助。"
    ),
}


class WritingAgent(AgentBase):
    name = "writing_agent"
    description = "负责论文写作、创新点梳理、内容润色等写作任务"

    async def run(self, ctx: AgentContext, **kwargs) -> Dict:
        intent = ctx.shared_memory.get("intent", "general")
        focus = ctx.shared_memory.get("focus", "")
        user_input = ctx.messages[-1]["content"] if ctx.messages else focus

        # 写作模式
        mode = "general"
        if intent == "innovation":
            mode = "innovation"
        elif intent == "writing":
            mode = "draft"
        elif intent == "polish":
            mode = "polish"

        # 把 RAGAgent 的检索结果作为参考内容（如果有）
        rag_answer = ctx.shared_memory.get("rag_answer", "")
        rag_sources = ctx.shared_memory.get("rag_sources", [])
        reference_text = ""
        if rag_sources:
            reference_text = "\n\n参考论文内容：\n" + "\n".join(
                f"[{i+1}] {s['content']}" for i, s in enumerate(rag_sources[:5])
            )
        elif rag_answer:
            reference_text = f"\n\n参考内容：\n{rag_answer}"

        mode_prompt = _MODE_PROMPTS.get(mode, _MODE_PROMPTS["general"])
        agent_task = (
            f"{mode_prompt}\n"
            f"{reference_text}\n\n"
            f"用户请求：{user_input}"
        )

        # 携带四层记忆上下文（working 层包含 RAG 结果，history 层包含对话历史）
        result = await self._invoke_with_context(
            ctx, agent_task=agent_task, temperature=0.6, n_history=4
        )
        ctx.shared_memory["writing_result"] = result

        # 将写作结果写入工作记忆层
        await ctx.save_working_memory(
            key="writing_result",
            content=f"【写作结果（{mode}模式）】\n{result[:600]}",
            metadata={"mode": mode, "intent": intent},
        )

        return {
            "summary": result[:200],
            "mode": mode,
            "result": result,
        }
