from langchain_core.tools import tool
from langchain_core.messages import RemoveMessage
from langgraph.graph.message import REMOVE_ALL_MESSAGES
from langgraph.checkpoint.memory import InMemorySaver
from langchain.agents import create_agent, AgentState
from langchain_openai import ChatOpenAI
from langchain_qwq import ChatQwen
from langchain.agents.middleware import before_model, after_model
from langgraph.runtime import Runtime
from langchain_core.runnables import RunnableConfig
from typing import Any


@after_model
def _messages(state: AgentState, runtime: Runtime):
    messages = state["messages"]
    if "<think>" in messages:
        think_index = messages.index("<think>")
        message_length = len(messages)
        print(f"{think_index}, len: {message_length}")
        

@before_model
def trim_messages(state: AgentState, runtime: Runtime) -> dict[str, Any] | None:
    """Keep only the last few messages to fit context window."""
    messages = state["messages"]
    print("in middle function....")
    first_msg = messages[0]
    recent_messages = messages[-3:] if len(messages) % 2 == 0 else messages[-4:]
    new_messages = [first_msg] + recent_messages

    return {
        "messages": [
            RemoveMessage(id=REMOVE_ALL_MESSAGES),
            *new_messages
        ]
    }

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

# llm = ChatOpenAI(model="Qwen3-30B-A3B", base_url="http://192.168.0.147:8997/v1", api_key="123456",temperature=0)
llm = ChatQwen(model="Qwen3-30B-A3B", api_base="http://192.168.0.147:8997/v1", api_key="123456", temperature=0, enable_thinking=False)
# llm_with_tools = llm.bind_tools(tools)
agent = create_agent(
    llm,
    tools=tools,
    middleware=[trim_messages, _messages],
    checkpointer=InMemorySaver(),
)

config: RunnableConfig = {"configurable": {"thread_id": "1", "chat_template_kwargs": {"enable_thinking": False}}}

agent.invoke({"messages": "hi, my name is bob"}, config)
agent.invoke({"messages": "write a short poem about cats"}, config)
agent.invoke({"messages": "now do the same but for dogs"}, config)
final_response = agent.invoke({"messages": "what's my name?"}, config)

final_response["messages"][-1].pretty_print()
"""
================================== Ai Message ==================================

Your name is Bob. You told me that earlier.
If you'd like me to call you a nickname or use a different name, just say the word.
"""