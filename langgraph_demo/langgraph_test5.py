import operator
import sys
from typing import Annotated, List, TypedDict, Union

# LangChain 相关库
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage, BaseMessage
from langchain_core.tools import tool

# LangGraph 相关库
from langgraph.graph import StateGraph, END, START
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.checkpoint.memory import MemorySaver

# --- 1. 定义丰富的工具集 ---
USER_DB = {}

@tool
def save_user_profile(name: str, phone: str):
    """
    保存或更新用户的基本信息（姓名、手机号）。
    当用户告知其姓名或联系方式时调用此工具。
    """
    USER_DB["name"] = name
    USER_DB["phone"] = phone
    return f"✅ 已更新用户资料: 姓名={name}, 手机={phone}"

@tool
def save_home_address(address: str):
    """
    保存用户的常用出发地址（家庭住址）。
    """
    USER_DB["address"] = address
    return f"✅ 已更新常用地址: {address}"

@tool
def search_flights(destination: str, date: str):
    """
    查询航班信息。
    """
    print(f"\n   ✈️ [API调用] 正在查询去往 {destination} ({date}) 的航班...")
    return f"""
    查询结果:
    1. CA888: {date} 10:00 起飞, 商务舱 5000元
    2. MU666: {date} 15:30 起飞, 经济舱 1200元
    """

@tool
def book_ticket(flight_number: str):
    """
    【敏感操作】执行最终的出票扣款。
    只有在用户明确确认要预订某个航班，且系统中已有用户姓名和手机号时才能调用。
    """
    # 模拟检查数据完整性
    if "name" not in USER_DB or "phone" not in USER_DB:
        return "❌ 预订失败：缺少用户资料。请先询问用户姓名和手机号，并使用 save_user_profile 工具保存。"
    
    print(f"\n   💳 [API调用] 正在调用支付接口: 航班 {flight_number}...")
    return f"🎉 预订成功！\n   乘客: {USER_DB['name']} ({USER_DB['phone']})\n   航班: {flight_number}\n   电子票号: TKT-999-888"

# 工具列表
tools = [save_user_profile, save_home_address, search_flights, book_ticket]

# 敏感工具列表（需要人工确认的）
SENSITIVE_TOOLS = ["book_ticket"]

# --- 2. 构建 Agent 图 ---

# 状态定义
class State(TypedDict):
    messages: Annotated[List[BaseMessage], operator.add]

# 初始化 LLM
llm = ChatOpenAI(model="Qwen3-30B-A3B", base_url="http://192.168.0.147:8997/v1", api_key="123456",temperature=0)
llm_with_tools = llm.bind_tools(tools)

# 核心节点逻辑
def chatbot(state: State):
    # 动态构建 System Prompt，让 Agent 知道当前的数据库状态
    current_profile = str(USER_DB) if USER_DB else "暂无资料"
    
    sys_msg = SystemMessage(content=f"""
    你是一个智能差旅管家。
    当前时间"2026/1/13"
    【当前已知用户资料】
    {current_profile}
    
    【你的行为准则】
    1. 你的首要任务是帮助用户管理行程。
    2. 如果用户让你订票，但【当前已知用户资料】中缺少姓名或手机号，你必须先询问用户，并调用 save_user_profile 保存。
    3. 保存完资料后，再进行订票操作。
    4. 对于记录地址、记录姓名等操作，你可以直接执行。
    5. 对于 book_ticket 操作，必须非常谨慎。
    """)
    
    return {"messages": [llm_with_tools.invoke([sys_msg] + state["messages"])]}

# 构建图
workflow = StateGraph(State)
workflow.add_node("chatbot", chatbot)
workflow.add_node("tools", ToolNode(tools))

workflow.add_edge(START, "chatbot")
workflow.add_conditional_edges("chatbot", tools_condition)
workflow.add_edge("tools", "chatbot")

# 内存记忆
memory = MemorySaver()

# ★★★ 关键：设置中断点 ★★★
app = workflow.compile(
    checkpointer=memory,
    interrupt_before=["tools"] # 在执行任何工具前，先暂停，交由主循环判断
)

# --- 3. 辅助函数：打印漂亮的日志 ---

def print_agent_response(messages):
    """从消息列表中提取并打印 Agent 的回复"""
    if not messages: return
    last_msg = messages[-1]
    
    if isinstance(last_msg, AIMessage):
        # 如果有工具调用
        if last_msg.tool_calls:
            for tool_call in last_msg.tool_calls:
                print(f"🤖 Agent 想要操作: \033[93m{tool_call['name']}\033[0m")
                print(f"   参数: {tool_call['args']}")
        # 如果是普通回复
        elif last_msg.content:
            print(f"🤖 Agent: {last_msg.content}")
            
    elif isinstance(last_msg, ToolMessage):
        print(f"🛠️ 工具返回: {last_msg.content}")

# --- 4. 交互式主循环 (CLI) ---

def main_loop():
    thread_id = "user_interaction_002"
    config = {"configurable": {"thread_id": thread_id}}
    
    print("="*50)
    print("🤵 智能差旅管家已上线 (输入 'q' 退出)")
    print("您可以试着说：'我叫张三，电话13800000000' 或 '帮我查明天去北京的票'")
    print("="*50)

    while True:
        try:
            # 1. 获取用户输入
            user_input = input("\n👤 User: ").strip()
            if user_input.lower() in ["q", "quit", "exit"]:
                print("👋 再见！")
                break
            if not user_input: continue

            # 2. 将用户消息送入图
            # 这里的 stream 模式设置为 values，方便我们拿到最新的状态消息
            inputs = {"messages": [HumanMessage(content=user_input)]}
            
            # 使用一个标志位来处理“多步执行”（因为可能连续调用工具）
            # 我们用 snapshot 来检测执行状态
            
            # 先运行第一步（直到遇到中断或结束）
            for event in app.stream(inputs, config=config):
                # 打印流式过程中的消息
                if "chatbot" in event:
                    print_agent_response(event["chatbot"]["messages"])
                if "tools" in event: # 只有工具真正执行了才会走到这里
                    print_agent_response(event["tools"]["messages"])

            # 3. 处理中断 (Human-in-the-loop)
            # 循环检查，直到图执行完毕（不再有后续步骤）
            while True:
                snapshot = app.get_state(config)
                
                # 如果没有下一步了，说明这轮对话结束，跳出内层循环，等待用户新输入
                if not snapshot.next:
                    break
                
                # 如果下一步是 'tools'，说明遇到了 interrupt_before=["tools"]
                if "tools" in snapshot.next:
                    # 获取 Agent 想要调用的工具详情
                    last_message = snapshot.values["messages"][-1]
                    if not last_message.tool_calls:
                        break # 异常保护
                        
                    tool_call = last_message.tool_calls[0]
                    tool_name = tool_call["name"]
                    
                    # --- 鉴权逻辑 ---
                    approved = False
                    
                    if tool_name in SENSITIVE_TOOLS:
                        # 敏感操作：询问用户
                        print(f"\n⚠️  [安全拦截] Agent 请求执行敏感操作: {tool_name}")
                        print(f"   详情: {tool_call['args']}")
                        user_confirm = input("   👉 是否批准？(y/n): ").strip().lower()
                        if user_confirm == 'y':
                            approved = True
                            print("   ✅ 已批准，继续执行...")
                        else:
                            print("   🚫 操作被拒绝。")
                            # 这里我们可以选择直接结束，或者给 Agent 注入一条拒绝的消息
                            # 简单起见，我们直接 break，等待用户下一轮说话
                            # 为了不让 Agent 卡死，通常做法是注入一条 ToolMessage 只有 error
                            # 但为了 Demo 简单，我们直接不 resume，让用户重新输入指令
                            break 
                    else:
                        # 非敏感操作（如存资料、查天气）：自动批准
                        print(f"   (自动批准低风险操作: {tool_name})")
                        approved = True

                    # --- 恢复执行 ---
                    if approved:
                        # 传入 None，表示继续执行下一步
                        for event in app.stream(None, config=config):
                            if "tools" in event:
                                print_agent_response(event["tools"]["messages"])
                            if "chatbot" in event:
                                print_agent_response(event["chatbot"]["messages"])
                    else:
                        # 如果没批准，必须跳出内层检查循环，等待用户新输入
                        break

        except Exception as e:
            print(f"❌ 发生错误: {e}")
            break

if __name__ == "__main__":
    main_loop()