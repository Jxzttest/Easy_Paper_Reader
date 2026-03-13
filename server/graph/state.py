import operator
from typing import Annotated, List, TypedDict, Union
from langchain_core.messages import BaseMessage

class AgentState(TypedDict):
    # 消息历史，使用 add_messages reducer 来追加消息而不是覆盖
    messages: Annotated[List[BaseMessage], operator.add]
    # 下一步由谁执行
    next: str
    # 当前上下文中的 paper_ids (用于 RAG 或 对比)
    current_paper_ids: List[str]