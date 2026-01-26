from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_openai import ChatOpenAI
from server.agent.graph.state import AgentState
from server.agent.graph.tools_adapter import query_paper_rag, query_journal_impact_factor, database_query_tool
from server.config import config # 假设你有配置加载

# 初始化 LLM
llm = ChatOpenAI(model="gpt-4o", temperature=0) # 或使用 server/model/llm_model 中的封装

# --- 1. Supervisor Node (路由器) ---
members = ["Researcher", "DataAnalyst", "Coder"]
system_prompt = (
    "你是一个论文阅读助手的主管。"
    "根据用户的输入，决定下一步应该由谁来处理。"
    " - Researcher: 负责论文内容问答、翻译、多篇论文创新点对比、查询影响因子。"
    " - DataAnalyst: 负责查询数据库统计信息（如某作者发文数量、按年份筛选）。"
    " - Coder: 负责将论文中的算法描述转化为 Python 代码。"
    "如果是简单闲聊，直接返回 FINISH。"
    "现有 worker: {members}"
    "请输出下一步的 worker 名字，或者 'FINISH'。"
)

options = ["FINISH"] + members

# 使用 function calling 或 structured output 来做路由选择
class RouteResponse(TypedDict):
    next: str

def supervisor_node(state: AgentState):
    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        MessagesPlaceholder(variable_name="messages"),
        ("system", "根据上面的对话，下一步应该由谁处理？从 {options} 中选择。"),
    ]).partial(options=str(options), members=", ".join(members))
    
    supervisor_chain = prompt | llm.with_structured_output(RouteResponse)
    result = supervisor_chain.invoke(state)
    return {"next": result["next"]}

# --- 2. Researcher Node (处理 RAG、对比、翻译) ---
# Researcher 可以使用 RAG 工具和 影响因子工具
researcher_tools = [query_paper_rag, query_journal_impact_factor]
researcher_agent = llm.bind_tools(researcher_tools)

def researcher_node(state: AgentState):
    result = researcher_agent.invoke(state["messages"])
    return {"messages": [result]}

# --- 3. Data Analyst Node (N2SQL) ---
def data_analyst_node(state: AgentState):
    """
    Text-to-SQL 的 Agent。
    1. 获取 Schema (提示词中写死或动态获取)
    2. 生成 SQL
    3. 调用 database_query_tool
    """
    # 简化的 N2SQL 逻辑
    schema_info = "Table: papers (id, title, author, year, journal, abstract)"
    prompt = f"你是一个数据分析师。根据以下 Schema 生成 SQL 并查询工具。\nSchema: {schema_info}"
    
    analyst_agent = llm.bind_tools([database_query_tool])
    chain = ChatPromptTemplate.from_messages([
        ("system", prompt),
        MessagesPlaceholder("messages")
    ]) | analyst_agent
    
    result = chain.invoke(state)
    return {"messages": [result]}

# --- 4. Coder Node (算法转代码) ---
def coder_node(state: AgentState):
    """
    专注于代码生成。
    如果需要论文细节，Coder 应该能够请求 RAG 工具的信息（这里简化为由 LLM 上下文处理或同样绑定 RAG 工具）。
    """
    prompt = (
        "你是一个算法工程师。你的任务是将用户提供的论文片段或之前的 RAG 检索结果中的算法逻辑，"
        "转换为高质量的 Python 代码。请给出完整的代码实现和注释。"
    )
    # 绑定 RAG 工具，因为写代码可能需要查细节
    coder_agent = llm.bind_tools([query_paper_rag])
    
    chain = ChatPromptTemplate.from_messages([
        ("system", prompt),
        MessagesPlaceholder("messages")
    ]) | coder_agent
    
    result = chain.invoke(state)
    return {"messages": [result]}



# 增强型Supervisor Node - 支持动态技能发现
def enhanced_supervisor_node(state: AgentState):
    # 从技能注册中心获取可用技能
    available_skills = SkillRegistry.get_all_skills()
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", f"""你是论文阅读助手的主管。根据对话历史和用户问题，决定下一步操作。
可用的技能: {available_skills}
如果是精确事实查询，返回 'RAG'
如果是多步骤任务，选择最合适的技能名称
如果是简单对话，返回 'FINISH'"""),
        MessagesPlaceholder(variable_name="messages")
    ])
    
    # 使用结构化输出确保路由准确性
    class RouteDecision(TypedDict):
        next: str
        confidence: float
        needed_skills: List[str]
    
    chain = prompt | llm.with_structured_output(RouteDecision)
    decision = chain.invoke(state)
    
    return {
        "next": decision["next"],
        "confidence": decision["confidence"],
        "needed_skills": decision["needed_skills"]
    }