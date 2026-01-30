import time
from typing import List, Dict, Optional
from server.db.db_factory import DBFactory
from server.model.embedding_model.embedding import EmbeddingManager
from server.utils.logger import logger


# deepsearch query规划

# 自循环查询
class SelfReflectiveRAG:
    tool_id = "self relective rag tool"

    def __init__(self):
        self.embedding_manager = EmbeddingManager()
    
    @property
    def es_store(self):
        return DBFactory.get_es_paper_service()
    
    @property
    def processing_store(self):
        return DBFactory.get_es_agent_service()
    
    async def reflective_search(self, query: str, **kwargs) -> Dict:
        """带自反思的检索流程"""
        results = []
        current_query = query
        
        for i in range(3):  # 最大3次尝试
            # 检索
            context_vector = self.embedding_manager.get_embedding(current_query)
            results = await self.es_store.search_hybrid(text_query=current_query, vector=context_vector)
            
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