#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import pathlib
import datetime
from typing import List, Dict, Optional, Any
import chromadb
from chromadb.config import Settings
from server.utils.logger import logger

DEFAULT_CHROMA_PATH = pathlib.Path(__file__).parent.parent.parent.parent / "data" / "chroma_db"


class ChromaVectorStore:
    """
    基于 ChromaDB 的本地向量存储，替代 Elasticsearch。
    支持向量检索 + 关键词过滤，无需外部服务。
    """

    PAPER_COLLECTION = "paper_chunks"

    def __init__(self, persist_dir: Optional[str] = None):
        self.persist_dir = str(persist_dir or DEFAULT_CHROMA_PATH)
        self._client: Optional[chromadb.ClientAPI] = None
        self._paper_col = None

    async def initialize(self):
        pathlib.Path(self.persist_dir).mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(
            path=self.persist_dir,
            settings=Settings(anonymized_telemetry=False)
        )
        self._paper_col = self._client.get_or_create_collection(
            name=self.PAPER_COLLECTION,
            metadata={"hnsw:space": "cosine"}
        )
        logger.info(f"[ChromaVectorStore] initialized at {self.persist_dir}")

    async def close(self):
        # ChromaDB PersistentClient 会自动持久化，无需显式关闭
        pass

    # ------------------------------------------------------------------ #
    # Paper Chunks
    # ------------------------------------------------------------------ #
    async def add_paper_chunk(
        self,
        paper_id: str,
        chunk_id: str,
        content: str,
        content_type: str,
        vector: List[float],
        page_num: int = 0,
        image_path: str = "",
        metadata: Optional[Dict] = None,
    ) -> None:
        meta = {
            "paper_id": paper_id,
            "content_type": content_type,
            "page_num": page_num,
            "image_path": image_path,
            "create_time": datetime.datetime.utcnow().isoformat(),
        }
        if metadata:
            # ChromaDB metadata 值只能是 str/int/float/bool
            for k, v in metadata.items():
                meta[f"extra_{k}"] = str(v)

        self._paper_col.upsert(
            ids=[chunk_id],
            embeddings=[vector],
            documents=[content],
            metadatas=[meta],
        )

    async def search_similar(
        self,
        vector: List[float],
        top_k: int = 20,
        paper_id: Optional[str] = None,
    ) -> List[Dict]:
        where = {"paper_id": paper_id} if paper_id else None
        results = self._paper_col.query(
            query_embeddings=[vector],
            n_results=min(top_k, self._paper_col.count() or 1),
            where=where,
            include=["documents", "metadatas", "distances"],
        )
        return self._format_results(results)

    async def search_hybrid(
        self,
        text_query: str,
        vector: List[float],
        top_k: int = 20,
        paper_id: Optional[str] = None,
    ) -> List[Dict]:
        """
        ChromaDB 同时支持 embedding 检索和文档全文过滤。
        此处先做向量检索，再按关键词做二次过滤重排。
        """
        where = {"paper_id": paper_id} if paper_id else None
        count = self._paper_col.count()
        if count == 0:
            return []

        # 多召回一些，方便关键词二次排序
        n = min(top_k * 3, count)
        results = self._paper_col.query(
            query_embeddings=[vector],
            n_results=n,
            where=where,
            include=["documents", "metadatas", "distances"],
        )
        candidates = self._format_results(results)

        # 简单关键词 boost：命中词越多分越高
        keywords = set(text_query.lower().split())
        for item in candidates:
            doc_lower = item["content"].lower()
            hit_count = sum(1 for kw in keywords if kw in doc_lower)
            # distance 越小越相似，用 1-distance 作向量得分
            vector_score = 1.0 - item.get("distance", 1.0)
            item["score"] = 0.6 * vector_score + 0.4 * (hit_count / max(len(keywords), 1))

        candidates.sort(key=lambda x: x["score"], reverse=True)
        return candidates[:top_k]

    async def get_paper_chunks(self, paper_id: str) -> List[Dict]:
        results = self._paper_col.get(
            where={"paper_id": paper_id},
            include=["documents", "metadatas"],
        )
        if not results["ids"]:
            return []
        items = []
        for i, chunk_id in enumerate(results["ids"]):
            items.append({
                "chunk_id": chunk_id,
                "content": results["documents"][i],
                **results["metadatas"][i],
            })
        return items

    async def count_chunks_by_paper(self, paper_id: str) -> int:
        results = self._paper_col.get(where={"paper_id": paper_id}, include=[])
        return len(results["ids"])

    async def delete_paper_chunks(self, paper_id: str) -> None:
        results = self._paper_col.get(where={"paper_id": paper_id}, include=[])
        if results["ids"]:
            self._paper_col.delete(ids=results["ids"])
        logger.info(f"[ChromaVectorStore] deleted {len(results['ids'])} chunks for paper {paper_id}")

    # ------------------------------------------------------------------ #
    # Internal
    # ------------------------------------------------------------------ #
    def _format_results(self, results: Dict) -> List[Dict]:
        ids = results.get("ids", [[]])[0]
        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]

        items = []
        for i, chunk_id in enumerate(ids):
            item = {
                "chunk_id": chunk_id,
                "content": docs[i] if docs else "",
                "distance": distances[i] if distances else 1.0,
            }
            if metas and metas[i]:
                item.update(metas[i])
            items.append(item)
        return items
