import operator
import uuid
from typing import Annotated, List, Literal, TypedDict, Union

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, BaseMessage, RemoveMessage, trim_messages
from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig

from langgraph.graph import StateGraph, END, START, MessagesState
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.memory import InMemoryStore # 引入存储

# --- 1. 定义工具 ---

@tool
def search_flights(destination: str):
    """查询航班"""
    return f"查询结果: 去往 {destination} 的航班有 CA123 (¥1000)。"

@tool
def book_ticket(flight_no: str):
    """预订航班"""
    return f"预订成功: {flight_no}"

tools = [search_flights, book_ticket]

# --- 2. 初始化模型 ---

llm = ChatOpenAI(model="Qwen3-30B-A3B", base_url="http://192.168.0.147:8997/v1", api_key="123456",temperature=0)
llm_with_tools = llm.bind_tools(tools)

# --- 3. 核心逻辑：结合 Store 的聊天节点 ---

def call_model(state: MessagesState, config: RunnableConfig, store: InMemoryStore):
    """
    主对话节点：
    1. 从 Store 中提取长期记忆（摘要 + 用户画像）。
    2. 将长期记忆注入 System Prompt。
    3. 结合短期记忆（state['messages']）进行回答。
    """
    user_id = config["configurable"]["thread_id"]
    
    # --- A. 从 Store 获取记忆 ---
    # 我们使用 (namespace, key) 来定位数据
    # namespace 通常用于隔离不同类型的数据，key 是用户ID
    namespace = ("user_memory",) 
    memory_data = store.get(namespace, user_id)
    
    summary = ""
    if memory_data:
        summary = memory_data.value.get("summary", "")
        
    # --- B. 构建 Prompt ---
    system_msg = f"""你是一个智能助手。
    
    【长期记忆/已知信息】
    {summary if summary else "暂无之前的记忆。"}
    
    【当前任务】
    请根据上述记忆和下方的最新对话回复用户。
    """
    
    # 确保 SystemMessage 始终在最前
    messages = [SystemMessage(content=system_msg)] + state["messages"]
    
    # 调用模型
    response = llm_with_tools.invoke(messages)
    return {"messages": [response]}

# --- 4. 核心逻辑：总结与修剪节点 ---

def summarize_conversation(state: MessagesState, config: RunnableConfig, store: InMemoryStore):
    """
    总结节点：
    1. 读取当前所有消息。
    2. 生成新的摘要。
    3. 将摘要存入 Store。
    4. 删除旧消息（释放 Token）。
    """
    user_id = config["configurable"]["thread_id"]
    namespace = ("user_memory",)
    
    # 1. 获取旧摘要
    existing_data = store.get(namespace, user_id)
    existing_summary = existing_data.value.get("summary", "") if existing_data else ""
    
    messages = state["messages"]
    
    # 如果消息太少，就不总结了（防止频繁调用浪费钱）
    if len(messages) < 6:
        return {}

    # 2. 调用 LLM 生成新摘要
    # 我们把旧摘要 + 当前对话发给 LLM，让它合并生成一个新的
    prompt = f"""请将当前的对话内容合并到现有的记忆摘要中。
    保留关键信息（如用户的名字、目的地、偏好、已完成的订单）。
    
    【现有摘要】
    {existing_summary}
    
    【新增对话】
    {messages}
    
    请输出新的摘要：
    """
    response = llm.invoke([HumanMessage(content=prompt)])
    new_summary = response.content
    
    # 3. 存入 Store (持久化)
    store.put(namespace, user_id, {"summary": new_summary})
    print(f"\n💾 [系统] 已更新长期记忆: {new_summary[:50]}...")
    
    # 4. 删除旧消息 (修剪)
    # 我们保留最后 2 条消息（通常是 User query 和当前的 AI response），删除之前的
    # RemoveMessage 是 LangGraph 特有的机制，用于从 State 中物理删除消息
    delete_messages = [RemoveMessage(id=m.id) for m in messages[:-2]]
    
    return {"messages": delete_messages}

# --- 5. 定义条件逻辑：何时触发总结？ ---

def should_summarize(state: MessagesState):
    """
    决定下一步去哪：
    1. 如果有工具调用 -> tools
    2. 如果消息列表太长（比如超过 6 条） -> summarize_conversation
    3. 否则 -> END (等待用户输入)
    """
    messages = state["messages"]
    last_message = messages[-1]
    
    # 优先处理工具调用
    if last_message.tool_calls:
        return "tools"
    
    # 检查是否需要总结（这里设定阈值为 6 条消息）
    # 注意：实际生产中可以使用 token 计数器来判断
    if len(messages) > 6:
        return "summarize_conversation"
    
    return END

# --- 6. 构建图 ---

workflow = StateGraph(MessagesState)

# 添加节点
workflow.add_node("chatbot", call_model)
workflow.add_node("tools", ToolNode(tools))
workflow.add_node("summarize_conversation", summarize_conversation)

# 设置入口
workflow.add_edge(START, "chatbot")

# 设置复杂的条件边
workflow.add_conditional_edges(
    "chatbot",
    should_summarize,
    {
        "tools": "tools",
        "summarize_conversation": "summarize_conversation",
        END: END
    }
)

# 工具执行完回 chatbot
workflow.add_edge("tools", "chatbot")

# 总结执行完结束（等待用户下一轮）
workflow.add_edge("summarize_conversation", END)

# --- 7. 编译 ---

# 既需要 Checkpointer (短期会话状态)，也需要 Store (长期跨会话记忆)
checkpointer = MemorySaver()
in_memory_store = InMemoryStore()

app = workflow.compile(
    checkpointer=checkpointer,
    store=in_memory_store, 
)

# --- 8. 演示运行 ---

def run_long_context_demo():
    print("🧠 具备长短期记忆管理的 Agent 已启动...")
    thread_id = "user_888" # 模拟同一个用户
    config = {"configurable": {"thread_id": thread_id}}
    
    # 模拟一长串对话，观察记忆的变化
    conversations = [
        "你好，我叫张三。",
        "我想查查去北京的航班。", 
        "那去上海的呢？",         
        "我觉得 CA123 还可以。", # 此时应该接近触发总结阈值
        "对了，我比较喜欢靠窗的位置。", # 触发总结，将之前的对话压缩进 Store
        "帮我预订 CA123。",         # Agent 应该能从 Store 里提取出我是张三
        "谢谢，再见。"
    ]
    
    for i, user_input in enumerate(conversations):
        print(f"\n--- 第 {i+1} 轮对话 ---")
        print(f"👤 User: {user_input}")
        
        input_msg = {"messages": [HumanMessage(content=user_input)]}
        
        # 运行
        for event in app.stream(input_msg, config=config):
            if "chatbot" in event:
                print(f"🤖 Agent: {event['chatbot']['messages'][-1].content}")
            if "tools" in event:
                print(f"🛠️ Tool: {event['tools']['messages'][-1].content}")
        
        # 调试：查看当前 Checkpoint 中的实际消息数量（验证修剪是否生效）
        snapshot = app.get_state(config)
        msg_count = len(snapshot.values['messages'])
        print(f"📊 当前上下文消息数: {msg_count} (Store 中是否有记忆: 查看控制台日志)")

if __name__ == "__main__":
    run_long_context_demo()