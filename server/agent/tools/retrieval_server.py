from mcp.server.fastmcp import FastMCP
from server.db.db_factory import DBFactory

# 创建 MCP 服务
mcp = FastMCP("PaperRetrieval")

@mcp.tool()
async def search_paper_id(query: str) -> str:
    """
    根据论文标题、作者或关键词搜索论文，返回最匹配的 paper_id 和 标题。
    如果找不到，返回空。
    """
    # 连接 ES 或 PG
    es_service = DBFactory.get_es_paper_service()
    
    # 简单的 ES 搜索 title 或 metadata
    # 这里假设你实现了 search_metadata 方法
    results = await es_service.search_metadata(query, limit=5)
    
    if not results:
        return "未找到相关论文。"
    
    # 返回格式化列表供 Agent 选择，或者如果置信度高直接返回第一个
    # 为了节省 Token，我们返回简短列表
    resp = "找到以下论文:\n"
    for r in results:
        resp += f"- ID: {r['paper_id']} | Title: {r['title']}\n"
    return resp

@mcp.tool()
async def list_available_papers() -> str:
    """列出数据库中最近入库的论文列表"""
    pg_service = DBFactory.get_pg_service()
    papers = await pg_service.get_recent_papers(limit=10)
    return "\n".join([f"ID: {p.paper_uuid} | Title: {p.title}" for p in papers])

if __name__ == "__main__":
    mcp.run()