from mcp_agent.app import MCPApp
from mcp_agent.logging.logger import get_logger

app = MCPApp(name="test")
agent_logger = get_logger("llm_selector.interactive")