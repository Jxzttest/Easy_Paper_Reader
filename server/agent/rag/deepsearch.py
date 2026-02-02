import time
import json
from dataclasses import dataclass
from langchain.messages import SystemMessage, HumanMessage
from typing import List, Dict, Optional
from server.db.db_factory import DBFactory
from server.model.llm_model.llm_function import _internal_llm_process
from server.model.embedding_model.embedding import EmbeddingManager
from server.model.ranker_model.ranker import RankerManager
from server.utils.logger import logger


"""验证结果清单"""
@dataclass
class VerificationResult:
    claim: str
    evidence: List[str]
    verdict: str  # "SUPPORTED", "CONTRADICTED", "UNVERIFIED", "UNKNOWN"
    confidence: float
    explanation: str


# deepsearch query规划

# 自循环查询
class SelfReflectiveRAG:
    agent_id = "self relective rag agent"

    def __init__(self):
        self.embedding_manager = EmbeddingManager()
        self.ranker_manager = RankerManager()
    
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
                verification_result = await self.fact_check(answer, results)
                if verification_result.get("is_consistent"):
                    return {
                        "answer": answer,
                        "sources": results,
                        "retrieval_attempts": i + 1,
                        "quality_score": quality_score
                    }
            
            # 质量不足，优化查询
            current_query = await self.optimize_query(current_query, results)
            
        return {"answer": "抱歉，无法找到足够可靠的信息", "sources": []}
    
    async def fact_check(self, answer, sources):
        """完整的事实一致性检查流程"""
        # 1. 拆解声明
        claims = await self.extract_claims(answer)
        
        # 2. 逐一验证
        verification_results = []
        for claim in claims:
            evidence = self.retrieve_evidence(claim, sources)
            result: VerificationResult = self.verify_claim(claim, evidence)
            verification_results.append(result)
        
        # 3. 聚合评估
        supported = sum(1 for r in verification_results if r.verdict == "SUPPORTED")
        contradicted = sum(1 for r in verification_results if r.verdict == "CONTRADICTED")
        total = len(verification_results)
        
        consistency_score = supported / total if total > 0 else 0
        
        return {
            "overall_score": consistency_score,
            "is_consistent": consistency_score >= 0.8 and contradicted == 0,
            "claims": [
                {
                    "claim": r.claim,
                    "verdict": r.verdict,
                    "confidence": r.confidence,
                    "explanation": r.explanation
                }
                for r in verification_results
            ],
            "contradictions": [
                r for r in verification_results 
                if r.verdict == "CONTRADICTED"
            ],
            "unverified": [
                r for r in verification_results 
                if r.verdict in ["UNVERIFIED", "UNKNOWN"]
            ]
        }
    
    async def extract_claims(self, answer: str) -> List[str]:
        """步骤1: 将答案拆解为原子事实声明"""
        prompt = f"""将以下答案拆解为最小的原子事实声明（claims）。每个声明应是一个可验证的事实性陈述。

        答案: {answer}

        要求:
        - 每个声明只包含一个事实
        - 去除主观观点、推测性内容
        - 保留数值、时间、实体等关键信息
        - 输出 JSON 数组格式

        示例:
        答案: "巴黎是法国首都，人口约210万，建于公元前3世纪"
        输出: [
            "巴黎是法国的首都",
            "巴黎人口约为210万",
            "巴黎建于公元前3世纪"
        ]"""
        
        response = await _internal_llm_process([HumanMessage(prompt)])
        return json.loads(response)
    
    def retrieve_evidence(self, claim: str, sources: List[Dict]) -> List[str]:
        """步骤2: 为每个声明检索最相关的证据片段"""
        
        scores = self.ranker_manager.get_ranker(claim, sources)
        
        # 取 Top-3 相关证据
        ranked = sorted(zip(sources, scores), key=lambda x: x[1], reverse=True)
        return [src["content"] for src, score in ranked[:3]]

    async def generate_answer(self, current_query, results):
        # 使用LLM评估相关性
        evaluation_prompt = f"""根据系统检索到的内容，根据用户的问题生成对应的答案:
        用户问题: {current_query}
        检索内容: {results[:3]}
        答案："""
        
        message = [HumanMessage(evaluation_prompt)]
        try:
            response = await _internal_llm_process(message)  # 替换为真实LLM调用
            return float(response.strip())
        except Exception as e:
            logger.error(f"错误 生成答案时报错， 错误内容为：{str(e)}")
            return ""


    async def verify_claim(self, claim: str, evidence: List[str]) -> VerificationResult:
        """步骤3: NLI（自然语言推断）验证"""
        evidence_text = "\n".join([f"[{i+1}] {e}" for i, e in enumerate(evidence)])
        
        prompt = f"""你是一个事实验证专家。请判断以下声明是否被提供的证据支持。

        声明: {claim}

        证据:
        {evidence_text}

        请分析:
        1. 声明中的关键事实是什么？
        2. 证据是否支持、反驳，或没有相关信息？
        3. 置信度如何？

        输出 JSON 格式:
        {{
            "verdict": "SUPPORTED|CONTRADICTED|UNVERIFIED|UNKNOWN",
            "confidence": 0.0-1.0,
            "explanation": "详细解释原因"
        }}"""
        
        response = await _internal_llm_process(HumanMessage(prompt))
        result = json.loads(response)
        
        return VerificationResult(
            claim=claim,
            evidence=evidence,
            verdict=result["verdict"],
            confidence=result["confidence"],
            explanation=result["explanation"]
        )
    
    async def optimize_query(self, current_query, results):
        """优化查询"""
        prompt = f"""
        你是一个问题优化专家，当前系统检索的内容无法进行问题回答，现在需要你对当前问题进行修改进行优化
        你只需要当前问题的修改后的内容即可，不需要你输出其他任何内容

        检索到的内容：
        {results}
        用户问题：
        {current_query}
        
        开始任务
        """
        message = [HumanMessage(prompt)]
        response = await _internal_llm_process(message)  # 替换为真实LLM调用
        return float(response.strip())
    
    async def evaluate_retrieval_quality(self, query: str, results: List) -> float:
        """评估检索结果质量"""
        if not results:
            return 0.0
        
        # 使用LLM评估相关性
        evaluation_prompt = f"""评估以下检索结果与查询的相关性:
        查询: {query}
        结果: {results[:3]}
        请给出0-1的相关性评分，只返回数字:"""
        
        message = [HumanMessage(evaluation_prompt)]
        try:
            response = await _internal_llm_process(message)  # 替换为真实LLM调用
            return float(response.strip())
        except:
            # 回退到基于分数的评估
            avg_score = sum(r.get('score', 0) for r in results) / len(results)
            return avg_score / 100  # 假设分数是0-100