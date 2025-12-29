# 文件位置: src/rag_manager/rag_engine.py

import time
from typing import List, Dict
from server.db.db_factory import DBFactory
from server.model.embedding_model.embedding import EmbeddingManager
from server.utils.logger import logger

class RAGEngine:
    def __init__(self):
        self.embedding_manager = EmbeddingManager()
    
    @property
    def es_store(self):
        return DBFactory.get_es_paper_service()

    async def search(self, query: str, top_k: int = 5, alpha: float = 0.7) -> List[Dict]:
        """
        执行 RAG 检索
        :param query: 用户问题
        :param top_k: 返回片段数量
        :param alpha: 混合检索权重，0.7 偏向向量，0.3 偏向关键词
        """
        start_time = time.time()
        
        try:
            # 1. 将 Query 转为 Vector
            query_vector = await self.embedding_manager.get_embedding(query)
            
            # 2. 调用 ES 进行混合检索
            results = await self.es_store.search_hybrid(
                text_query=query,
                vector=query_vector,
                top_k=top_k,
                alpha=alpha
            )
            
            cost = (time.time() - start_time) * 1000
            logger.info(f"RAG Search completed. Query: '{query[:20]}...', Found: {len(results)}, Time: {cost:.2f}ms")
            
            return results
            
        except Exception as e:
            logger.error(f"RAG search error: {e}")
            return []

    async def get_context_string(self, query: str, top_k: int = 3) -> str:
        """
        辅助函数：直接获取拼接好的 Context 字符串，用于给 LLM Prompt
        """
        results = await self.search(query, top_k=top_k)
        
        context_parts = []
        for i, res in enumerate(results):
            # 可以在这里加入 Source 信息
            source = res.get('title', 'Unknown Source')
            text = res.get('content', '').strip()
            context_parts.append(f"[{i+1}] (Source: {source}):\n{text}")
            
        return "\n\n".join(context_parts)