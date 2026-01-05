import asyncio
from mcp.server.fastmcp import FastMCP, Context
from server.agent.rag.rag_engine import RAGEngine
from server.db.db_factory import DBFactory

# 初始化 Server 和 RAG 引擎
mcp = FastMCP("AcademicKnowledgeBase")
rag_engine = RAGEngine()

# ==========================================
# 1. Resources: 静态资源的直接访问
# ==========================================

@mcp.resource("paper://{paper_id}/metadata")
async def get_paper_metadata(paper_id: str) -> str:
    """
    获取指定论文的元数据（标题、作者、年份、文件路径）。
    Agent 可以直接读取此资源来确认论文信息，通过 URI 访问。
    """
    pg_store = DBFactory.get_pg_service()
    paper = await pg_store.get_paper_by_uuid(paper_id)
    if not paper:
        return "Error: Paper not found."
    
    return f"""
    Title: {paper.title}
    Authors: {paper.authors}
    Year: {paper.publish_year}
    Status: {'Processed' if paper.is_processed else 'Processing'}
    UUID: {paper.paper_uuid}
    """

@mcp.resource("paper://{paper_id}/abstract")
async def get_paper_abstract(paper_id: str) -> str:
    """直接读取论文摘要（假设摘要存储在特定的 chunk 或 metadata 中）"""
    # 模拟从 ES 获取摘要
    results = await rag_engine.search("Abstract", paper_id=paper_id, top_k=1)
    if results:
        return results[0]['content']
    return "Abstract not found in chunks."

# ==========================================
# 2. Prompts: 动态 Prompt 模板
# ==========================================

@mcp.prompt("analyze_paper_innovation")
def prompt_analyze_innovation(paper_id: str, specific_focus: str = "general") -> list:
    """
    生成一个标准的“创新点分析” Prompt 模板。
    UI 或 Agent 可以调用这个 API 获取预设的 Prompt，确保提问质量。
    """
    base_instruction = f"请作为同行评审专家，分析论文 ({paper_id}) 的创新点。"
    
    if specific_focus == "methodology":
        detail = "重点关注其算法流程和数学推导的创新。"
    elif specific_focus == "experiment":
        detail = "重点关注其实验设计、数据集构建和对比结果的SOTA程度。"
    else:
        detail = "请从方法、实验和应用价值三个维度进行综合评估。"

    return [
        {
            "role": "user",
            "content": f"{base_instruction}\n{detail}\n请调用 search_paper_content 工具获取原文支撑你的观点。"
        }
    ]

# ==========================================
# 3. Tools: 核心 RAG 工具
# ==========================================

@mcp.tool()
async def search_paper_content(query: str, paper_id: str, ctx: Context = None) -> str:
    """
    [文本检索] 在指定论文中搜索相关文本片段。
    """
    # 可以在 ctx 中记录日志或向 Client 发送进度
    if ctx:
        await ctx.info(f"正在论文 {paper_id} 中检索: {query}")

    results = await rag_engine.search(query, paper_id=paper_id, content_types=['text', 'table'])
    
    if not results:
        return "未找到相关内容。"
    
    response = f"在论文 {paper_id} 中找到以下相关内容:\n"
    for i, res in enumerate(results):
        response += f"--- Fragment {i+1} (Score: {res['score']:.2f}) ---\n{res['content']}\n\n"
    return response

@mcp.tool()
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

@mcp.tool()
async def search_paper_code(functionality: str, paper_id: str) -> str:
    """
    [代码检索] 查找论文中涉及的具体算法伪代码或代码段。
    """
    results = await rag_engine.search(functionality, paper_id=paper_id, content_types=['code'])
    if not results:
        return "未找到相关代码段。"
    
    return "\n\n".join([f"```python\n{r['content']}\n```" for r in results])

if __name__ == "__main__":
    mcp.run()