from mcp.server.fastmcp import FastMCP

mcp = FastMCP("ExternalTools")

@mcp.tool()
async def get_impact_factor(journal_name: str) -> str:
    """(工具 7) 查询期刊的影响因子"""
    # 这里可以接入真实 API，或者模拟数据
    mock_db = {"Nature": "64.8", "Science": "56.9", "CVPR": "45.1"}
    score = mock_db.get(journal_name, "未查询到数据")
    return f"{journal_name} 的影响因子约为: {score}"

if __name__ == "__main__":
    mcp.run()