import time
from typing import List, Dict, Optional
from server.db.db_factory import DBFactory
from server.model.embedding_model.embedding import EmbeddingManager
from server.utils.logger import logger

class RAGEngine:
    def __init__(self):
        self.embedding_manager = EmbeddingManager()
    
    @property
    def es_store(self):
        return DBFactory.get_es_paper_service()

    async def search(
        self, 
        query: str, 
        paper_id: Optional[str] = None,
        content_types: Optional[List[str]] = None, # e.g. ['figure', 'table']
        top_k: int = 5, 
        alpha: float = 0.7
    ) -> List[Dict]:
        """
        升级版混合检索
        :param paper_id: 如果提供，则限定在该论文内搜索
        :param content_types: 限定搜索内容类型 (text, code, figure, table)
        """
        start_time = time.time()
        try:
            # 1. 向量化 Query
            query_vector = await self.embedding_manager.get_embedding(query)
            
            # 2. 构造过滤条件
            filters = {}
            if paper_id:
                filters["paper_id"] = paper_id
            if content_types:
                filters["content_type"] = content_types # ES层需支持 terms 查询

            # 3. 调用 ES (假设 es_store.search_hybrid 已经支持 filter 参数)
            # 你需要在 db_service 里透传 filter 到 ES 的 bool query 中
            results = await self.es_store.search_hybrid(
                text_query=query,
                vector=query_vector,
                filter_dict=filters, 
                top_k=top_k,
                alpha=alpha
            )
            
            # 4. 后处理：如果是图片，确保 image_path 存在
            final_results = []
            for res in results:
                item = {
                    "content": res.get("content"),
                    "score": res.get("score"),
                    "type": res.get("content_type"),
                    "metadata": res.get("metadata", {})
                }
                # 如果是图片或表格，带上路径
                if res.get("content_type") in ["figure", "table"]:
                    item["image_path"] = res.get("image_path")
                    # 对于图片，content 主要是 OCR 的文字，可能需要提示 Agent
                    item["content"] = f"[Figure/Table Content]: {res.get('content')}"
                
                final_results.append(item)

            logger.info(f"RAG Search: '{query}' | Types: {content_types} | Found: {len(final_results)}")
            return final_results
            
        except Exception as e:
            logger.error(f"RAG search error: {e}", exc_info=True)
            return []