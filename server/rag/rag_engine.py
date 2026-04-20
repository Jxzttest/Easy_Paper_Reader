#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
RAGEngine (SimpleRAG) —— 标准单次检索

流程：
  1. 向量化 query → ChromaDB 混合检索
  2. 评估检索质量
  3. 质量足够 → 生成答案
  4. 质量不足 → 触发 DeepSearchRAG（多跳）
"""

from typing import Dict, List, Optional

from server.rag.base_rag import BaseRAG, RetrievalResult
from server.utils.logger import logger

QUALITY_THRESHOLD = 0.55   # 低于此分触发 DeepSearch


class RAGEngine(BaseRAG):
    """
    对外统一入口。
    简单问题走 SimpleRAG；复杂/低质量问题自动升级 DeepSearchRAG。
    """

    async def retrieve(
        self,
        query: str,
        paper_uuids: Optional[List[str]] = None,
        top_k: int = 8,
    ) -> RetrievalResult:
        paper_id = paper_uuids[0] if paper_uuids and len(paper_uuids) == 1 else None
        chunks = await self._search_chunks(query, paper_id, top_k)
        score = await self._evaluate_quality(query, chunks)
        return RetrievalResult(chunks=chunks, query=query, score=score)

    async def answer(
        self,
        query: str,
        paper_uuids: Optional[List[str]] = None,
        content_types: Optional[List[str]] = None,
        top_k: int = 8,
    ) -> Dict:
        """
        自适应检索入口：
          - 先做简单检索
          - 质量低 → 自动切换 DeepSearchRAG
        """
        logger.info(f"[RAGEngine] query='{query[:50]}...'")

        retrieval = await self.retrieve(query, paper_uuids, top_k)
        logger.info(f"[RAGEngine] quality_score={retrieval.quality_score:.2f}, chunks={len(retrieval.chunks)}")

        # 质量不足，升级到 DeepSearch
        if retrieval.quality_score < QUALITY_THRESHOLD or retrieval.is_empty():
            logger.info("[RAGEngine] low quality → escalate to DeepSearchRAG")
            from server.rag.deepsearch_rag import DeepSearchRAG
            deep = DeepSearchRAG()
            return await deep.answer(query, paper_uuids=paper_uuids, top_k=top_k)

        answer_text = await self._generate_answer(query, retrieval)

        # 整理来源（过滤 content_types）
        sources = []
        for c in retrieval.chunks:
            if content_types and c.get("content_type") not in content_types:
                continue
            sources.append({
                "chunk_id":    c.get("chunk_id", ""),
                "content":     c["content"][:300],
                "content_type": c.get("content_type", "text"),
                "page_num":    c.get("page_num"),
                "image_path":  c.get("image_path", ""),
                "score":       round(c.get("score", 0.0), 4),
            })

        return {
            "answer":             answer_text,
            "sources":            sources,
            "retrieval_attempts": 1,
            "quality_score":      retrieval.quality_score,
            "mode":               "simple",
        }
