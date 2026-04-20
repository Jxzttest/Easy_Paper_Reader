#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
RAGAgent —— 检索增强回答

流程：
  1. 用用户问题 + focus 生成 embedding
  2. 在 ChromaDB 中混合检索（向量 + 关键词）
  3. 用检索到的上下文生成回答
  4. 将回答和来源写入 ctx.shared_memory
"""

from typing import Dict, List
from server.agent.base import AgentBase, AgentContext
from server.db.db_factory import DBFactory
from server.model.embedding_model.embedding import EmbeddingManager


class RAGAgent(AgentBase):
    name = "rag_agent"
    description = "从已入库论文中检索相关内容，生成带来源的回答"

    def __init__(self):
        super().__init__()
        self.embedding = EmbeddingManager()

    async def run(self, ctx: AgentContext, **kwargs) -> Dict:
        focus = ctx.shared_memory.get("focus", "")
        if not focus:
            focus = ctx.messages[-1]["content"] if ctx.messages else ""

        # 检索
        vector = await self.embedding.get_embedding(focus)
        vector_store = DBFactory.get_vector_store()

        paper_id = ctx.paper_uuids[0] if len(ctx.paper_uuids) == 1 else None
        chunks = await vector_store.search_hybrid(
            text_query=focus,
            vector=vector,
            top_k=8,
            paper_id=paper_id,
        )

        if not chunks:
            answer = "未在已入库的论文中检索到相关内容。"
            ctx.shared_memory["rag_answer"] = answer
            ctx.shared_memory["rag_sources"] = []
            return {"summary": "无检索结果", "answer": answer, "sources": []}

        # 构建 prompt
        context_text = "\n\n".join(
            f"[来源 {i+1}，第{c.get('page_num', '?')}页]\n{c['content']}"
            for i, c in enumerate(chunks)
        )
        history = ctx.to_history_text(n=4)

        messages = [
            {
                "role": "system",
                "content": (
                    "你是一个专业的学术论文助手。请根据提供的论文片段，"
                    "精准、严谨地回答用户的问题。"
                    "如果论文中没有相关信息，请明确说明。"
                    "回答时注明内容来自哪个来源（用[来源N]标注）。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"对话历史：\n{history}\n\n"
                    f"论文内容片段：\n{context_text}\n\n"
                    f"用户问题：{focus}"
                ),
            },
        ]

        answer = await self._invoke(messages, temperature=0.3)
        ctx.shared_memory["rag_answer"] = answer
        ctx.shared_memory["rag_sources"] = [
            {"chunk_id": c.get("chunk_id"), "page_num": c.get("page_num"), "content": c["content"][:200]}
            for c in chunks
        ]

        return {
            "summary": answer[:200],
            "answer": answer,
            "sources": ctx.shared_memory["rag_sources"],
        }
