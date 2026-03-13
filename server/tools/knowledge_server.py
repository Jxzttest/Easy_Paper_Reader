from .. import app, agent_logger
from server.agent.rag.rag_engine import RAGEngine
from server.db.db_factory import DBFactory

# 初始化 Server 和 RAG 引擎
rag_engine = RAGEngine()

# ==========================================
# 3. Tools: 核心 RAG 工具
# ==========================================

@app.async_tool()
async def search_paper_content(query: str, paper_id: str) -> str:
    """
    [文本检索] 在指定论文中搜索相关文本片段。
    """
    # 可以在 ctx 中记录日志或向 Client 发送进度
    if agent_logger:
        agent_logger.info(f"正在论文 {paper_id} 中检索: {query}")

    results = await rag_engine.search(query, paper_id=paper_id, content_types=['text', 'table'])
    
    if not results:
        return "未找到相关内容。"
    
    response = f"在论文 {paper_id} 中找到以下相关内容:\n"
    for i, res in enumerate(results):
        response += f"--- Fragment {i+1} (Score: {res['score']:.2f}) ---\n{res['content']}\n\n"
    return response


@app.async_tool()
async def search_paper_images(description: str, paper_id: str) -> str:
    """
    [图片检索] 根据描述查找论文中的架构图、结果图或图表。
    Agent: 当用户问“这篇文章的模型图是什么样”时使用此工具。
    """
    # 专门检索 figure 类型
    results = await rag_engine.search(description, paper_id=paper_id, content_types=['figure'])
    
    if not results:
        return "未找到相关图片。"
    
    resp = "找到以下图片资源:\n"
    for res in results:
        # 这里返回 image_path，前端或 Agent 可以据此加载图片
        resp += f"- 图片路径: {res.get('image_path')}\n"
        resp += f"- 图注/OCR内容: {res.get('content')}\n"
        resp += "-" * 20 + "\n"
    return resp


@app.async_tool()
async def search_paper_code(functionality: str, paper_id: str) -> str:
    """
    [代码检索] 查找论文中涉及的具体算法伪代码或代码段。
    """
    results = await rag_engine.search(functionality, paper_id=paper_id, content_types=['code'])
    if not results:
        return "未找到相关代码段。"
    
    return "\n\n".join([f"```python\n{r['content']}\n```" for r in results])