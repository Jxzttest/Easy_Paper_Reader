#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
BaseRAG —— RAG 抽象基类

定义检索 → 质量评估 → 生成 的标准接口。
子类可覆盖任意一步：
  - SimpleRAG    : 单次检索 + 直接生成（默认）
  - DeepSearchRAG: 多跳检索 + 自反思（复杂问题）
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from server.model.embedding_model.embedding import EmbeddingManager
from server.model.llm_model.llm_function import LLMManager
from server.db.db_factory import DBFactory
from server.utils.logger import logger


class RetrievalResult:
    """检索结果的统一包装。"""
    def __init__(self, chunks: List[Dict], query: str, score: float = 0.0):
        self.chunks = chunks          # 原始 chunk 列表
        self.query = query            # 实际使用的查询（可能被改写过）
        self.quality_score = score    # 0~1，检索质量评估分

    @property
    def context_text(self) -> str:
        return "\n\n".join(
            f"[来源{i+1} 第{c.get('page_num','?')}页]\n{c['content']}"
            for i, c in enumerate(self.chunks)
        )

    def is_empty(self) -> bool:
        return len(self.chunks) == 0


class BaseRAG(ABC):
    """
    RAG 基类，持有共享的模型和存储引用。
    子类实现 retrieve() 和 answer()。
    """

    def __init__(self):
        self.embedding = EmbeddingManager()
        self.llm = LLMManager()

    @property
    def vector_store(self):
        return DBFactory.get_vector_store()

    # ── 必须实现 ──────────────────────────────────────────────────────
    @abstractmethod
    async def retrieve(
        self,
        query: str,
        paper_uuids: Optional[List[str]] = None,
        top_k: int = 8,
    ) -> RetrievalResult:
        """执行检索，返回 RetrievalResult。"""
        ...

    @abstractmethod
    async def answer(
        self,
        query: str,
        paper_uuids: Optional[List[str]] = None,
        **kwargs,
    ) -> Dict:
        """
        完整 RAG 流程，返回：
          {answer, sources, retrieval_attempts, quality_score}
        """
        ...

    # ── 公共工具方法（子类可复用）────────────────────────────────────
    async def _embed(self, text: str) -> List[float]:
        return await self.embedding.get_embedding(text)

    async def _search_chunks(
        self,
        query: str,
        paper_id: Optional[str],
        top_k: int,
    ) -> List[Dict]:
        vector = await self._embed(query)
        return await self.vector_store.search_hybrid(
            text_query=query,
            vector=vector,
            top_k=top_k,
            paper_id=paper_id,
        )

    async def _llm_invoke(self, messages: List[Dict], temperature: float = 0.3) -> str:
        return await self.llm.invoke(messages, temperature=temperature)

    async def _evaluate_quality(self, query: str, chunks: List[Dict]) -> float:
        """用 LLM 给检索结果的相关性打分（0~1）。"""
        if not chunks:
            return 0.0
        sample = "\n".join(c["content"][:200] for c in chunks[:3])
        prompt = (
            f"请评估以下检索内容与问题的相关程度，只返回0到1之间的小数。\n"
            f"问题：{query}\n检索内容摘要：{sample}\n相关性分数："
        )
        try:
            resp = await self._llm_invoke(
                [{"role": "user", "content": prompt}], temperature=0.0
            )
            return min(1.0, max(0.0, float(resp.strip().split()[0])))
        except Exception:
            # 降级：用 chunk 数量估算
            return min(1.0, len(chunks) / 8)

    async def _generate_answer(self, query: str, retrieval: RetrievalResult) -> str:
        """通用答案生成（子类可覆盖）。"""
        messages = [
            {
                "role": "system",
                "content": (
                    "你是一位专业的学术论文助手。根据提供的论文片段，"
                    "精准回答用户问题。用[来源N]标注引用。"
                    "若论文中没有相关信息，请明确说明。"
                ),
            },
            {
                "role": "user",
                "content": f"论文片段：\n{retrieval.context_text}\n\n问题：{query}",
            },
        ]
        return await self._llm_invoke(messages)
