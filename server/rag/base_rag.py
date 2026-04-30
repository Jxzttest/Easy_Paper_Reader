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

# 元数据问题关键词（命中任意一个则走元数据检索）
_METADATA_KEYWORDS = [
    # 标题相关
    "论文名", "标题", "题目", "论文题目", "paper title", "title",
    # 作者相关
    "作者", "authors", "author", "谁写的", "谁发表",
    # 页数相关
    "多少页", "几页", "页数", "页码", "page count", "pages", "how many pages",
    # 摘要相关
    "摘要", "abstract", "概要",
    # 年份相关
    "发表年", "发表时间", "年份", "年代", "publish year", "publication year", "when published",
    # doi/arxiv
    "doi", "arxiv",
]


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
        """基于检索分数估算相关性（不调 LLM，消除串行延迟）。"""
        if not chunks:
            return 0.0
        # chunks 已按 score 降序排列，取前 top_k 的均值
        scores = [c.get("score", 0.0) for c in chunks[:8]]
        if not scores:
            return 0.0
        avg = sum(scores) / len(scores)
        top = scores[0]
        # 加权：top 分权重 0.6，均值权重 0.4
        return min(1.0, 0.6 * top + 0.4 * avg)

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

    # ── 元数据检索 ────────────────────────────────────────────────────────

    def _is_metadata_query(self, query: str) -> bool:
        """判断问题是否主要关心论文元数据（标题/作者/页数/摘要等）。"""
        q_lower = query.lower()
        return any(kw in q_lower for kw in _METADATA_KEYWORDS)

    async def _answer_from_metadata(
        self,
        query: str,
        paper_uuids: Optional[List[str]],
    ) -> Optional[Dict]:
        """
        从 SQLite 元数据直接生成答案。
        若无法找到对应论文返回 None，让调用方降级到向量检索。
        """
        sqlite = DBFactory.get_sqlite()

        if paper_uuids:
            metas = []
            for uid in paper_uuids:
                m = await sqlite.get_paper_metadata(uid)
                if m:
                    metas.append(m)
        else:
            metas = await sqlite.get_all_papers()

        if not metas:
            return None

        # 构造元数据描述文本
        meta_lines = []
        for m in metas:
            parts = [f"标题：{m.get('title', '未知')}"]
            if m.get("authors"):
                parts.append(f"作者：{m['authors']}")
            if m.get("publish_year"):
                parts.append(f"发表年份：{m['publish_year']}")
            if m.get("page_count"):
                parts.append(f"总页数：{m['page_count']} 页")
            if m.get("abstract"):
                parts.append(f"摘要：{m['abstract'][:300]}")
            if m.get("doi"):
                parts.append(f"DOI：{m['doi']}")
            if m.get("arxiv_id"):
                parts.append(f"arXiv ID：{m['arxiv_id']}")
            meta_lines.append("\n".join(parts))

        meta_text = "\n\n---\n\n".join(meta_lines)

        messages = [
            {
                "role": "system",
                "content": (
                    "你是一位学术论文助手。根据以下论文元数据精准回答用户问题。"
                    "如果元数据中没有相关信息，请明确说明。"
                ),
            },
            {
                "role": "user",
                "content": f"论文元数据：\n{meta_text}\n\n问题：{query}",
            },
        ]
        answer = await self._llm_invoke(messages)
        return {
            "answer": answer,
            "sources": [],
            "retrieval_attempts": 1,
            "quality_score": 1.0,
            "mode": "metadata",
        }
