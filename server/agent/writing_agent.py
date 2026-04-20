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

# 各模式的 system prompt
_SYSTEM_PROMPTS = {
    "innovation": (
        "你是一位顶级学术论文分析专家。请基于提供的论文内容，"
        "系统地梳理该论文的核心创新点。"
        "要求：结构清晰（可用序号列出），指出每个创新点相比已有工作的突破，"
        "语言严谨、客观。"
    ),
    "draft": (
        "你是一位专业的学术写作助手。请根据用户的要求和提供的参考内容，"
        "撰写高质量的学术文字。"
        "要求：语言正式、逻辑严密、符合学术规范，避免口语化表达。"
    ),
    "polish": (
        "你是一位资深学术编辑。请对用户提供的文字进行修改润色。"
        "要求：保留原意，提升语言表达的准确性和流畅性，"
        "修正语法错误，使其符合顶级期刊的写作标准。"
        "请先给出修改后的版本，再简要说明主要改动。"
    ),
    "general": (
        "你是一位专业的学术论文助手，擅长学术写作和论文分析。"
        "请根据用户的需求提供高质量的帮助。"
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

        system_prompt = _SYSTEM_PROMPTS.get(mode, _SYSTEM_PROMPTS["general"])

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

        history = ctx.to_history_text(n=4)

        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": (
                    f"对话历史：\n{history}\n"
                    f"{reference_text}\n\n"
                    f"用户请求：{user_input}"
                ),
            },
        ]

        result = await self._invoke(messages, temperature=0.6)
        ctx.shared_memory["writing_result"] = result

        return {
            "summary": result[:200],
            "mode": mode,
            "result": result,
        }
