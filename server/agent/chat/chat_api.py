from fastapi import APIRouter, Depends, HTTPException, UploadFile
from server.parser.pdf_parser import PDFParser
from starlette import status
from starlette.responses import JSONResponse
from server.utils.logger import logger

router = APIRouter(prefix="/chat")


from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict
import random
import time

app = FastAPI(title="论文阅读器多智能体 RAG 后端")

# ==========================================
# 1. 数据模型与内存模拟 (代替 PG 和 ES)
# ==========================================
class ChatRequest(BaseModel):
    user_id: str
    session_id: str
    query: str

class ChatResponse(BaseModel):
    answer: str
    workflow_type: str
    token_usage: Optional[int] = 0

# 【内存模拟：PostgreSQL】存储元数据
MOCK_PG_METADATA = {
    "user_1": {"role": "researcher", "preferred_language": "zh"},
    "paper_1": {"title": "Attention Is All You Need", "year": 2017}
}

# 【内存模拟：Elasticsearch】存储对话历史和文档切片
MOCK_ES_HISTORY = {} # 格式: {session_id: [history_list]}
MOCK_ES_CHUNKS = {
    "transformer": ["Self-attention 机制允许模型关注...", "Transformer 抛弃了传统的 RNN 结构..."]
}

# ==========================================
# 2. 基础 LLM 与工具模拟函数
# ==========================================
def mock_llm_call(prompt: str) -> str:
    """模拟大模型调用"""
    return f"LLM_RESPONSE_FOR: {prompt[:20]}..."

# ==========================================
# 3. 核心节点功能实现 (对应流程图)
# ==========================================

# 节点 B/C: 意图识别
def recognize_intent(query: str, history: List[Dict]) -> str:
    """判断是走 Agent 还是 RAG"""
    # 实际应调用 LLM 分类
    complex_keywords = ["总结", "对比", "查找新论文", "统计"]
    if any(k in query for k in complex_keywords):
        return "AGENT"
    return "RAG"

# ================= subgraph D [智能体工作流] =================
def agent_workflow(query: str, history: List[Dict]) -> str:
    """Agent 工作流：规划、工具调用、整合"""
    print(">>> [Agent] 进入智能体工作流")
    
    # D1: 状态管理 (这里简化为更新历史)
    state = {"query": query, "history": history, "slots": {}}
    
    # D2: 规划与决策
    plan = ["1. 查询PG获取论文元数据", "2. 总结内容"]
    print(f">>> [Agent] 生成规划: {plan}")
    
    # D3: 动态工具调用 (模拟)
    tool_results = f"PG元数据: {MOCK_PG_METADATA.get('paper_1')}"
    
    # D4: 整合回答
    final_answer = f"根据智能体分析：已查找到数据 {tool_results}，并且结合了您的需求进行了解读。"
    return final_answer

# ================= subgraph E [自反思 RAG 工作流] =================
def retrieve_from_es(query: str) -> List[str]:
    """E1: 从 ES 检索文档"""
    print(f">>> [RAG] 正在从 ES 检索: {query}")
    return MOCK_ES_CHUNKS.get("transformer", ["默认论文切片内容"])

def evaluate_retrieval(query: str, docs: List[str]) -> bool:
    """E2: 评估检索质量 (模拟: 80%概率高质量)"""
    quality = random.random() > 0.2
    print(f">>> [RAG] 检索质量评估结果: {'高' if quality else '低'}")
    return quality

def rewrite_query(query: str) -> str:
    """E4: 重写/优化查询"""
    new_query = f"{query} (优化关键词: transformer, NLP)"
    print(f">>> [RAG] 查询重写为: {new_query}")
    return new_query

def evaluate_hallucination(answer: str, docs: List[str]) -> bool:
    """E5: 评估幻觉/支持度 (模拟: 90%概率支持度足够)"""
    supported = random.random() > 0.1
    print(f">>> [RAG] 答案支持度评估: {'足够' if supported else '不足'}")
    return supported

def self_reflective_rag_workflow(query: str) -> str:
    """自反思 RAG 核心控制流 (带最大重试次数以防死循环)"""
    print(">>> [RAG] 进入自反思 RAG 工作流")
    max_retries = 3
    current_query = query
    
    for attempt in range(max_retries):
        # E1: 检索
        docs = retrieve_from_es(current_query)
        
        # E2: 检索质量评估
        if not evaluate_retrieval(current_query, docs):
            # 质量低 -> E4: 重写查询并继续循环
            current_query = rewrite_query(current_query)
            continue
            
        # 质量高 -> E3: 生成初步答案
        draft_answer = "Transformer 是一种基于自注意力的深度学习模型..."
        
        # E5: 评估答案支持度
        if evaluate_hallucination(draft_answer, docs):
            # 支持度足够 -> E6: 最终答案
            return f"【精准回答】: {draft_answer}"
        else:
            # 支持度不足 -> 返回 E1 (这里通过 continue 重新检索)
            print(">>> [RAG] 检测到幻觉，重新检索...")
            current_query = rewrite_query("消除幻觉后的精确查询")
            continue
            
    return "抱歉，由于知识库限制，无法给出确切答案。"

# ==========================================
# 4. FastAPI 主接口
# ==========================================

@app.post("/api/v1/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    # A: 用户输入新问题
    print(f"\n--- 新会话 [{request.session_id}] --- 用户问题: {request.query}")
    
    # 模拟从 ES 加载历史对话
    history = MOCK_ES_HISTORY.get(request.session_id, [])
    
    # B & C: 意图识别与路由分发
    task_type = recognize_intent(request.query, history)
    
    # 分支执行 D 或 E
    if task_type == "AGENT":
        final_answer = agent_workflow(request.query, history)
    else:
        final_answer = self_reflective_rag_workflow(request.query)
        
    # F: 更新对话状态，写入 ES (模拟)
    history.append({"user": request.query, "assistant": final_answer})
    MOCK_ES_HISTORY[request.session_id] = history
    
    # G: 返回给前端，前端判断是否继续对话
    return ChatResponse(
        answer=final_answer,
        workflow_type=task_type
    )

if __name__ == "__main__":
    import uvicorn
    # uvicorn.run(app, host="0.0.0.0", port=8000)