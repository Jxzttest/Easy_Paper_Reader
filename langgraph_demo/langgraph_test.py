import os
from typing import Annotated, Literal, TypedDict

from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
from langgraph.graph import END, START, StateGraph, MessagesState
from langgraph.prebuilt import ToolNode, tools_condition

# 1. 定义工具 (Tools)
# 这里我们定义一个简单的模拟天气查询工具
@tool
def get_weather(city: str):
    """查询指定城市的天气信息。"""
    # 实际场景中这里可以调用外部 API
    if "北京" in city:
        return "北京今天是晴天，气温 25 度。"
    elif "上海" in city:
        return "上海今天是阴天，有小雨，气温 22 度。"
    else:
        return f"暂时无法获取 {city} 的天气数据。"

tools = [get_weather]

# 2. 初始化模型 (Model) 并绑定工具
# 只有绑定了工具，模型才知道它有能力调用函数
llm = ChatOpenAI(model="Qwen3-30B-A3B", base_url="http://192.168.0.147:8997/v1", api_key="123456",temperature=0)
llm_with_tools = llm.bind_tools(tools)

# 3. 定义图的状态 (State)
# LangGraph 中的数据流转是基于 State 的。
# MessagesState 是官方预置的包含 messages 列表的 State，它会自动处理消息追加
class AgentState(MessagesState):
    # 你可以在这里添加额外的自定义状态字段
    pass

# 4. 定义节点 (Nodes)
# 节点是图执行的具体逻辑

def agent_node(state: AgentState):
    """
    Agent 节点：负责调用大模型，生成回复或工具调用请求
    """
    messages = state["messages"]
    response = llm_with_tools.invoke(messages)
    # 返回的内容会通过 add_messages 机制追加到 state["messages"] 中
    return {"messages": [response]}

# 5. 构建图 (Graph)
workflow = StateGraph(AgentState)

# 添加节点
workflow.add_node("agent", agent_node)
# ToolNode 是 LangGraph 预置的节点，专门用于执行工具调用
workflow.add_node("tools", ToolNode(tools))

# 添加边 (Edges)
# 定义流程的入口
workflow.add_edge(START, "agent")

# 定义条件边 (Conditional Edges)
# 从 agent 节点出来后，决定下一步去哪：
# 如果模型决定调用工具 -> 去 "tools" 节点
# 如果模型直接回答 -> 结束 (END)
workflow.add_conditional_edges(
    "agent",
    tools_condition, # LangGraph 预置的逻辑，判断 message 中是否有 tool_calls
)

# 定义普通边
# 工具执行完后，必须把结果返回给 agent，让 agent 继续思考
workflow.add_edge("tools", "agent")

# 6. 编译图 (Compile)
# 编译后生成可执行的 Runnable
app = workflow.compile()

# --- 可选：生成图的结构图 (需要安装 graphviz) ---
try:
    print(app.get_graph().draw_mermaid())
except:
    pass

# 7. 运行 Demo
if __name__ == "__main__":
    print("Agent 已启动...")
    
    # 测试案例 1：不需要工具
    print("\n--- 测试 1: 普通对话 ---")
    inputs = {"messages": [HumanMessage(content="你好，请做一个自我介绍。")]}
    for chunk in app.stream(inputs, stream_mode="values"):
        message = chunk["messages"][-1]
        print(f"[{message.type}]: {message.content}")

    # 测试案例 2：需要调用工具
    print("\n--- 测试 2: 工具调用 ---")
    inputs = {"messages": [HumanMessage(content="成都今天天气怎么样？")]}
    # stream 方法会逐步输出图的执行状态
    for chunk in app.stream(inputs, stream_mode="values"):
        message = chunk["messages"][-1]
        
        if message.type == "ai":
            # 检查是否有工具调用
            tool_calls = getattr(message, "tool_calls", [])
            if tool_calls:
                print(f"🤖 Agent 决定调用工具: {tool_calls[0]['name']}")
            else:
                print(f"🤖 Agent 回复: {message.content}")
        elif message.type == "tool":
            print(f"🛠️ 工具返回结果: {message.content}")