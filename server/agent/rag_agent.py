#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
RAGAgent —— 检索增强回答

委托给 RAGEngine，自动根据检索质量决定走 SimpleRAG 还是 DeepSearchRAG。
"""

from typing import Dict
from server.agent.base import AgentBase, AgentContext
from server.rag.rag_engine import RAGEngine


class RAGAgent(AgentBase):
    name = "rag_agent"
    description = "从已入库论文中检索相关内容，自动升级为深度检索处理复杂问题"

    def __init__(self):
        super().__init__()
        self._engine = RAGEngine()

    async def run(self, ctx: AgentContext, **kwargs) -> Dict:
        focus = ctx.shared_memory.get("focus", "")
        if not focus:
            focus = ctx.messages[-1]["content"] if ctx.messages else ""

        result = await self._engine.answer(
            query=focus,
            paper_uuids=ctx.paper_uuids or None,
        )

        ctx.shared_memory["rag_answer"] = result["answer"]
        ctx.shared_memory["rag_sources"] = result["sources"]
        ctx.shared_memory["rag_mode"] = result.get("mode", "simple")

        # 将 RAG 结果写入工作记忆层（供后续轮次复用）
        rag_summary = f"检索结果（模式：{result.get('mode', 'simple')}）：\n{result['answer'][:800]}"
        await ctx.save_working_memory(
            key=f"rag_result",
            content=rag_summary,
            metadata={"query": focus, "mode": result.get("mode", "simple")},
        )

        return {
            "summary": result["answer"][:200],
            "answer":  result["answer"],
            "sources": result["sources"],
            "mode":    result.get("mode", "simple"),
        }
