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

            # 3.
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


class SelfReflectiveRAG(RAGEngine):
    async def reflective_search(self, query: str, **kwargs) -> Dict:
        """带自反思的检索流程"""
        results = []
        current_query = query
        
        for i in range(3):  # 最大3次尝试
            # 检索
            results = await self.search(current_query, **kwargs)
            
            # 评估检索质量
            quality_score = self.evaluate_retrieval_quality(current_query, results)
            
            if quality_score >= 0.7:  # 高质量阈值
                # 生成答案
                answer = await self.generate_answer(current_query, results)
                
                # 事实一致性检查
                if await self.fact_check(answer, results):
                    return {
                        "answer": answer,
                        "sources": results,
                        "retrieval_attempts": i + 1,
                        "quality_score": quality_score
                    }
            
            # 质量不足，优化查询
            current_query = await self.optimize_query(current_query, results)
            
        return {"answer": "抱歉，无法找到足够可靠的信息", "sources": []}
    
    async def evaluate_retrieval_quality(self, query: str, results: List) -> float:
        """评估检索结果质量"""
        if not results:
            return 0.0
        
        # 使用LLM评估相关性
        evaluation_prompt = f"""评估以下检索结果与查询的相关性:
        查询: {query}
        结果: {results[:3]}
        请给出0-1的相关性评分，只返回数字:"""
        
        try:
            response = await mock_llm_call(evaluation_prompt)  # 替换为真实LLM调用
            return float(response.strip())
        except:
            # 回退到基于分数的评估
            avg_score = sum(r.get('score', 0) for r in results) / len(results)
            return avg_score / 100  # 假设分数是0-100