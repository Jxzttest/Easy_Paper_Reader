import operator
from typing import Annotated, List, Literal, TypedDict, Union, Optional

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, BaseMessage, ToolMessage
from langchain_core.tools import tool
from langchain_core.utils.pydantic import BaseModel, Field

from langgraph.graph import StateGraph, END, START
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.memory import InMemoryStore

USER_DB = {}

# ==========================================
# 1. 基础工具定义 (Tools)
# ==========================================

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

# ==========================================
# 2. 定义全局状态 (Global State)
# ==========================================

class AgentState(TypedDict):
    # messages 是所有节点共享的“黑板”
    messages: Annotated[List[BaseMessage], operator.add]
    # next 用于 Supervisor 决定下一步去哪个子图
    next: str

llm = ChatOpenAI(model="Qwen3-30B-A3B", base_url="http://192.168.0.147:8997/v1", api_key="123456",temperature=0)

# ==========================================
# 3. 构建子图 A：查询专家 (Search Specialist)
# ==========================================
# 职责：负责澄清需求，直到完成查询，然后把结果交还给 Supervisor

def search_agent(state: AgentState):
    """查询专家的思考节点"""
    msg = [
        SystemMessage(content="你是航班查询专家。你的任务是获取出发地和目的地并调用工具查询。查到结果后停止。")
    ] + state["messages"]
    return {"messages": [llm.bind_tools([search_flights]).invoke(msg)]}

search_builder = StateGraph(AgentState)
search_builder.add_node("search_node", search_agent)
search_builder.add_node("search_tools", ToolNode([search_flights]))

search_builder.add_edge(START, "search_node")
search_builder.add_conditional_edges(
    "search_node",
    tools_condition, 
    # 如果有工具调用 -> 去工具节点，否则 -> 结束子图，返回主图
    {"tools": "search_tools", "__end__": END}
)
search_builder.add_edge("search_tools", "search_node")

# 编译子图
search_graph = search_builder.compile()


# ==========================================
# 4. 构建子图 B：订票专家 (Booking Specialist)
# ==========================================
# 职责：负责敏感的订票流程。先查证件，再支付。

def booking_agent(state: AgentState):
    """订票专家的思考节点"""
    msg = [
        SystemMessage(content="""
        你是订票交易专家。
        流程：
        【你的行为准则】
        1. 你的首要任务是帮助用户管理行程。
        2. 如果用户让你订票，但【当前已知用户资料】中缺少姓名或手机号，你必须先询问用户，并调用 save_user_profile 保存。
        3. 保存完资料后，再进行订票操作。
        4. 对于记录地址、记录姓名等操作，你可以直接执行。
        5. 对于 book_ticket 操作，必须非常谨慎。
        """)
    ] + state["messages"]
    # 绑定订票专属工具
    booking_tools = [save_user_profile, save_home_address, book_ticket]
    return {"messages": [llm.bind_tools(booking_tools).invoke(msg)]}

booking_builder = StateGraph(AgentState)
booking_builder.add_node("booking_node", booking_agent)
booking_builder.add_node("booking_tools", ToolNode([save_user_profile, save_home_address, book_ticket]))

booking_builder.add_edge(START, "booking_node")
booking_builder.add_conditional_edges(
    "booking_node",
    tools_condition,
    {"tools": "booking_tools", "__end__": END}
)
booking_builder.add_edge("booking_tools", "booking_node")

# 编译子图
booking_graph = booking_builder.compile()




def chat_node(state: AgentState, store: InMemoryStore):
    """闲聊节点：负责非业务类的对话"""
    system_prompt = SystemMessage(content="""
    你是一个幽默风趣的差旅助手“小飞”。
    1. 你的任务是陪用户闲聊，或者回答一些通用的知识性问题（如天气常识、城市介绍）。
    2. 你不需要处理具体的订单查询或预订（那些会有其他同事处理）。
    3. 你的语气要轻松活泼，适当使用 Emoji。
    4. 聊完后，可以礼貌地询问用户是否需要查询机票。
    """)
    
    # 将 System Prompt 和历史消息组合
    messages = [system_prompt] + state["messages"]
    response = llm.invoke(messages)
    return {"messages": [response]}



# ==========================================
# 5. 构建主图：Supervisor (Router)
# ==========================================

# 定义 Supervisor 的输出结构，用于结构化路由
class RouterOutput(BaseModel):
    """决定下一个工序是谁"""
    next: Literal["search_flow", "booking_flow", "chat_flow", "FINISH"] = Field(
        ..., description="根据用户意图选择：查询去 search_flow，订票去 booking_flow，闲聊/问候/无关话题去 chat_flow"
    )

def supervisor_node(state: AgentState):
    """总控节点：分析历史消息，决定路由"""
    system_prompt = SystemMessage(content="""
    你是差旅总管。你有三个下属：
    1. search_flow: 负责查询航班信息。
    2. booking_flow: 负责处理订票和支付。                                  
    3. chat_flow: 当用户只是打招呼、闲聊、询问你是谁、或者说一些与订票无关的话题时。
    
    根据用户最后的输入和当前的对话状态，决定下一步交给谁。
    如果用户任务已全部完成，选择 FINISH。
    """)
    
    # 使用 structured_output 强制输出 JSON 格式的决策
    messages = [system_prompt] + state["messages"]
    response = llm.with_structured_output(RouterOutput).invoke(messages)
    
    # 我们并不一定要把 Supervisor 的决策作为一条 AIMessage 存入历史，
    # 只需要更新 state["next"] 字段即可控制流向
    return {"next": response.next}

# --- 组装主图 ---
workflow = StateGraph(AgentState)

# 1. 添加 Supervisor 节点
workflow.add_node("supervisor", supervisor_node)

# 2. 添加子图节点 (这一步是精华)
# 我们直接把编译好的 search_graph 和 booking_graph 当作节点放入！
# 当流程走到这里时，会进入子图运行，直到子图返回 END，才会回到主图
workflow.add_node("search_flow", search_graph)
workflow.add_node("booking_flow", booking_graph)
workflow.add_node("chat_flow", chat_node)

# 3. 定义入口
workflow.add_edge(START, "supervisor")

# 4. 定义路由逻辑
# 根据 supervisor 输出的 state["next"] 决定去哪
workflow.add_conditional_edges(
    "supervisor",
    lambda state: state["next"], # 读取状态中的 next 字段
    {
        "search_flow": "search_flow",
        "booking_flow": "booking_flow",
        "chat_flow": "chat_flow",
        "FINISH": END
    }
)

# 5. 定义子图返回后的流向
# 子图执行完后，必须回到 Supervisor，由 Supervisor 决定下一步（比如查询完了，也许用户马上就要订票）
workflow.add_edge("search_flow", END)
workflow.add_edge("booking_flow", END)
workflow.add_edge("chat_flow", END)

# 6. 编译主图
memory = MemorySaver()
memory_store = InMemoryStore()
app = workflow.compile(checkpointer=memory, store=memory_store)

# ==========================================
# 6. 运行演示
# ==========================================

def run_demo():
    print("🤖 差旅总管系统启动...")
    thread_id = "complex_flow_001"
    config = {"configurable": {"thread_id": thread_id}}
    
    # # 模拟多轮对话脚本
    # user_inputs = [
    #     "你好，帮我查一下北京去上海的航班",  # 预期：Supervisor -> SearchGraph
    #     "就订那个 CA123 的吧",             # 预期：Supervisor -> BookingGraph
    #     "谢谢，没别的事了"                  # 预期：Supervisor -> END
    # ]
    while True:
        user_input = input("\n👤 User: ").strip()
        if user_input.lower() in ["q", "quit", "exit"]:
            print("👋 再见！")
            break
        if not user_input: continue

        print(f"\n👤 User: {user_input}")
        print("-" * 30)
        
        # 发送消息
        inputs = {"messages": [HumanMessage(content=user_input)]}
        
        # 运行图
        # 注意：因为内部有子图，输出的步骤会比较多
        for event in app.stream(inputs, config=config):
            if "supervisor" in event:
                next_step = event["supervisor"]["next"]
                print(f"🚦 总管分发 -> \033[94m{next_step}\033[0m")
            
            if "chat_flow" in event:
                print(f"💬 [小飞陪聊]: {event['chat_flow']['messages'][-1].content}")
            
            if "search_flow" in event:
                print(f"✈️ [查询专家]: {event['search_flow']['messages'][-1].content}")
                
            if "booking_flow" in event:
                print(f"💳 [订票专家]: {event['booking_flow']['messages'][-1].content}")
        while True:
                snapshot = app.get_state(config)
                
                # 如果没有下一步了，说明这轮对话结束，跳出内层循环，等待用户新输入
                if not snapshot.next:
                    break

if __name__ == "__main__":
    run_demo()