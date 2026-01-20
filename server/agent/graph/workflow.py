from langgraph.graph import StateGraph, START, END
from server.agent.graph.state import AgentState
from server.agent.graph.nodes import (
    supervisor_node, 
    researcher_node, 
    data_analyst_node, 
    coder_node, 
    researcher_tools,
    database_query_tool
)
from langgraph.prebuilt import ToolNode

# 创建 ToolNode (用于执行工具调用的通用节点)
# 注意：不同 Agent 可能使用不同的工具集，这里为了演示简化处理
# 在实际 A2A 中，通常 Agent 节点如果返回 tool_calls，流向专门的 tool_node
tools_node = ToolNode(researcher_tools + [database_query_tool])

workflow = StateGraph(AgentState)

# 添加节点
workflow.add_node("Supervisor", supervisor_node)
workflow.add_node("Researcher", researcher_node)
workflow.add_node("DataAnalyst", data_analyst_node)
workflow.add_node("Coder", coder_node)
workflow.add_node("tools", tools_node)

# 设置入口
workflow.add_edge(START, "Supervisor")

# 添加 Supervisor 的条件边 (路由逻辑)
workflow.add_conditional_edges(
    "Supervisor",
    lambda x: x["next"],
    {
        "Researcher": "Researcher",
        "DataAnalyst": "DataAnalyst",
        "Coder": "Coder",
        "FINISH": END
    }
)

# 添加 Workers 到 Tools 的边
# 逻辑：Worker -> (决定调用工具) -> Tools -> (工具结果) -> Worker
# 这里简化为：如果 Worker 生成了 tool_calls，LangGraph 会自动根据 conditional_edges 路由
# 通常我们需要为每个 Worker 定义是否去 tools 节点

def should_continue(state: AgentState):
    last_message = state["messages"][-1]
    if last_message.tool_calls:
        return "tools"
    return "Supervisor" # 工具执行完通常回到 Supervisor 让其决定是否结束，或者回到 Worker

for member in ["Researcher", "DataAnalyst", "Coder"]:
    workflow.add_conditional_edges(
        member,
        should_continue,
        {
            "tools": "tools",
            "Supervisor": "Supervisor"
        }
    )

# Tool 执行完，返回给 Supervisor (或者返回给原来的 Agent，这取决于你想怎么设计回路)
# 这里设计为：工具执行完，把结果扔回给 Supervisor，让大脑重新评估现状
workflow.add_edge("tools", "Supervisor")

# 编译图
app = workflow.compile()