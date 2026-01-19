import operator
from typing import Annotated, List, Literal, TypedDict, Union

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, BaseMessage
from langchain_core.tools import tool
from langgraph.graph import StateGraph, END, START
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.checkpoint.memory import MemorySaver # 引入内存保存器

# --- 1. 定义工具 (Tools) ---

@tool
def search_flights(destination: str, date: str):
    """
    仅用于查询航班信息。
    需要参数: destination (目的地), date (日期).
    """
    print(f"\n🔍 [系统工具] 正在查询去往 {destination} 在 {date} 的航班...")
    # 模拟返回结果
    return f"""
    查询结果:
    1. CA123: {date} 09:00 起飞, 价格 2000元
    2. MU456: {date} 14:00 起飞, 价格 1800元
    """

@tool
def book_ticket(flight_number: str, passenger_name: str):
    """
    仅在用户明确确认要预订某个具体航班后调用。
    这是敏感操作，会产生费用。
    """
    print(f"\n💳 [系统工具] 正在处理扣款和出票: 航班 {flight_number}, 乘客 {passenger_name}...")
    return f"预订成功！票号: TKT-{flight_number}-8888"

@tool
def book_user_info(location: str, user_name: str, ):
    """
    记录用户信息
    """
    print(f"\n💳 [系统工具] 出发城市 {location}, 乘客名称 {user_name} ...")
    return f"出发信息，记录成功，出发城市 {location}, 乘客名称 {user_name}"

tools = [search_flights, book_ticket]

# --- 2. 初始化模型与状态 ---

llm = ChatOpenAI(model="Qwen3-30B-A3B", base_url="http://192.168.0.147:8997/v1", api_key="123456",temperature=0)
llm_with_tools = llm.bind_tools(tools)

# 定义状态：使用标准的 MessagesState 模式
# Annotated[list, operator.add] 意思是：新的消息会 append 到旧消息列表中，而不是覆盖
class State(TypedDict):
    messages: Annotated[List[BaseMessage], operator.add]

# --- 3. 核心节点逻辑 ---

def chatbot(state: State):
    """主 Agent 节点：负责决策"""
    # 可以在这里动态插入 System Prompt，确保 Agent 知道自己的设定
    system_prompt = SystemMessage(content="""
    你是一个专业的差旅预订助手。
    1. 你的目标是帮助用户查询和预订机票。
    2. 【重要】如果用户提供的查询信息不全（例如只说了地点没说时间），你必须先反问用户，不要调用工具。
    3. 在调用 book_ticket 工具前，必须再次向用户确认航班号。
    """)
    
    # 构造消息列表：System Prompt + 历史消息
    messages = [system_prompt] + state["messages"]
    response = llm_with_tools.invoke(messages)
    return {"messages": [response]}

# --- 4. 构建图 (Graph) ---

workflow = StateGraph(State)

# 添加节点
workflow.add_node("chatbot", chatbot)
workflow.add_node("tools", ToolNode(tools))

# 添加边
workflow.add_edge(START, "chatbot")

# 这里的条件边逻辑：
# chatbot -> (判断是否有工具调用) -> tools 或者 END
workflow.add_conditional_edges(
    "chatbot",
    tools_condition,
)

# 工具执行完，必须回传给 chatbot，让它根据工具结果给用户最终反馈
workflow.add_edge("tools", "chatbot")

# --- 关键点：设置 Checkpointer 和 中断点 ---

# 初始化一个内存记忆保存器
memory = MemorySaver()

# 编译图
# interrupt_before=["tools"]: 意思是，在进入 "tools" 节点之前，暂停！
# 这让我们可以检查它想调用什么工具。如果它想“乱花钱”，我们可以拒绝。
app = workflow.compile(
    checkpointer=memory, 
    interrupt_before=["tools"] 
)

a = app.get_graph().draw_mermaid()
print(a)

# --- 5. 模拟运行 (Simulation) ---

def print_stream(thread_id, user_input):
    """辅助函数：用于打印流式输出并管理对话配置"""
    config = {"configurable": {"thread_id": thread_id}}
    
    print(f"\n👤 用户: {user_input}")
    
    # 将用户输入加入状态
    inputs = {"messages": [HumanMessage(content=user_input)]}
    
    # 运行图
    # stream_mode="values" 会打印状态中 message 的变化
    for event in app.stream(inputs, config=config):
        last_msg = event['chatbot']["messages"][-1]
        if isinstance(last_msg, AIMessage):
            if last_msg.tool_calls:
                print(f"🤖 Agent 意图: 准备调用工具 {last_msg.tool_calls[0]['name']}")
            else:
                print(f"🤖 Agent 回复: {last_msg.content}")
        elif isinstance(last_msg, HumanMessage):
             # 初始输入不重复打印
             pass
        else:
            # 打印工具输出等
            print(f"⚙️ 节点更新: {last_msg.content[:50]}...")
            
    return config

# --- 开始演示场景 ---

if __name__ == "__main__":
    thread_id = "user_session_001"
    print(f"--- 开启会话 (ID: {thread_id}) ---")

    # [第一轮] 用户意图模糊
    # 预期：Agent 应该反问时间，而不是调用工具
    print_stream(thread_id, "帮我查去上海的机票")

    # [第二轮] 用户补充信息
    # 预期：Agent 获取完整信息，决定调用 search_flights
    # 注意：由于设置了 interrupt_before=["tools"]，程序会暂停，工具实际上还没执行！
    config = print_stream(thread_id, "明天上午的")

    # --- 处理中断 (Human-in-the-loop) ---
    # 此时，图的状态停止在 "chatbot" 节点之后，"tools" 节点之前。
    # 我们检查一下现在的状态快照 (Snapshot)
    snapshot = app.get_state(config)
    next_step = snapshot.next
    
    if "tools" in next_step:
        print("\n⚠️  [系统拦截] 检测到 Agent 想要执行工具操作。")
        # 检查它具体想干嘛
        last_message = snapshot.values["messages"][-1]
        tool_call_name = last_message.tool_calls[0]["name"]
        
        print(f"   目标工具: {tool_call_name}")
        
        if tool_call_name == "search_flights":
            print("   ✅ 操作安全，自动批准执行...")
            # resume execution: 传入 None 表示什么都不改，继续往下跑
            for event in app.stream(None, config=config):
                last_msg = event["messages"][-1]
                if last_msg.type == "tool":
                     print(f"🛠️ 工具执行结果: {last_msg.content}")
                elif last_msg.type == "ai":
                     print(f"🤖 Agent 最终回复: {last_msg.content}")


    # [第三轮] 用户决定预订
    # 预期：Agent 决定调用 book_ticket
    config = print_stream(thread_id, "帮我订第一班，CA123，乘客是张三")

    # --- 处理第二次中断 ---
    snapshot = app.get_state(config)
    if "tools" in snapshot.next:
        last_message = snapshot.values["messages"][-1]
        tool_call_name = last_message.tool_calls[0]["name"]
        
        print(f"\n⚠️  [系统拦截] 检测到敏感操作: {tool_call_name}")
        print("   🛑 此操作涉及扣款，需要人工批准 (模拟用户输入 'yes')")
        
        approval = input("   👉 是否批准? (yes/no): ")
        
        if approval.lower() == "yes":
            print("   ✅ 已批准，继续执行...")
            for event in app.stream(None, config=config):
                last_msg = event["messages"][-1]
                if last_msg.type == "tool":
                     print(f"🛠️ 工具执行结果: {last_msg.content}")
                elif last_msg.type == "ai":
                     print(f"🤖 Agent 最终回复: {last_msg.content}")
        else:
            print("   🚫 操作已拒绝。")
            # 在实际应用中，你可以向状态中注入一条 "Tool failed" 或 "User rejected" 的消息来通知 LLM