import asyncio
import json
import uuid
import time
import functools
import operator
from typing import Annotated, List, Literal, TypedDict, Dict, Any, Optional
from enum import Enum

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, BaseMessage, AIMessage
from langchain_core.tools import tool, BaseTool
from langchain_core.runnables import RunnableConfig
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from langgraph.graph import StateGraph, END, START
from langgraph.prebuilt import create_react_agent
from langgraph.store.memory import InMemoryStore
from langgraph.checkpoint.memory import MemorySaver

# ==========================================
# 1. 基础配置与工具定义
# ==========================================
TIME_SCALE = 0.1 # 加速模拟

COOKING_KB = {
    "cook_rice": {
        "desc": "电饭煲煮饭",
        "time_guide": "20-30分钟", 
        "agent": "RiceChef"
    },
    "wash_food": {
        "desc": "清洗食材",
        "time_guide": "1-3分钟",
        "agent": "PrepChef"
    },
    "cut_food": {
        "desc": "切配",
        "time_guide": "2-5分钟",
        "agent": "PrepChef"
    },
    "stir_fry_food": {
        "desc": "爆炒",
        "time_guide": "3-5分钟 (需等食材和主食准备好)",
        "agent": "WokChef"
    },
    "stew_food": {
        "desc": "慢炖",
        "time_guide": "60-120分钟",
        "agent": "WokChef"
    }
}


# --- 蔬菜/备菜 Agent 的工具 ---
@tool
async def wash_tool(item: str, time_use: int):
    """清洗食材。输入食材名称。"""
    print(f"🌊 [PrepChef] 正在清洗: {item}...")
    await asyncio.sleep(2 * time_use)
    return f"{item} 已清洗干净"

@tool
async def cut_tool(item: str,  time_use: int, shape: str = "块"):
    """切配食材。输入食材名称和形状(片/丝/块)。"""
    print(f"🔪 [PrepChef] 正在切: {item} -> {shape}...")
    await asyncio.sleep(3 * time_use)
    return f"{item} 已切成{shape}"

# --- 肉菜/灶台 Agent 的工具 ---
@tool
async def boil_tool(item: str, time_use: int):
    """焯水/水煮。用于去除血水或煮熟。"""
    print(f"🔥 [WokChef] 正在焯水/水煮: {item}...")
    await asyncio.sleep(4 * time_use)
    return f"{item} 焯水完成"

@tool
async def fry_tool(item: str, time_use: int):
    """煎/炒。用于煸炒出油或煎至金黄。"""
    print(f"🔥 [WokChef] 正在煎炒: {item}...")
    await asyncio.sleep(4 * time_use)
    return f"{item} 煎炒完成"

@tool
async def stew_tool(item: str, time_use: int):
    """炖/焖。耗时较长，用于软烂入味。"""
    print(f"🥘 [WokChef] 正在慢炖: {item} (耗时操作)...")
    await asyncio.sleep(10 * time_use) # 模拟长耗时
    return f"{item} 炖煮完成，软烂入味"

@tool
async def seasoning_tool(action: str, time_use: int):
    """调味/勾芡/收汁。"""
    print(f"🧂 [WokChef] 正在{action}...")
    await asyncio.sleep(1 * time_use)
    return f"{action} 完成"

# --- 主食 Agent 的工具 ---
@tool
async def cook_rice_tool(amount: str, time_use: int):
    """煮饭。输入分量。"""
    print(f"🍚 [RiceChef] 电饭煲启动: 煮 {amount} 米饭...")
    await asyncio.sleep(100 * time_use) # 启动
    # 模拟异步等待（实际场景这里可能只是发指令）
    await asyncio.sleep(300 * time_use) 
    print(f"🔔 [RiceChef] 米饭煮好了！")
    return f"{amount} 米饭已煮熟"

# ==========================================
# 2. Store 管理与状态定义
# ==========================================

class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], operator.add]

# 细粒度的 Task 结构
class TaskInfo(TypedDict):
    id: str
    assignee: str # RiceChef, PrepChef, WokChef
    instruction: str # 具体的任务指令，如 "制作红烧肉"
    dependencies: List[str] # 依赖的 task_id
    status: Literal["pending", "processing", "done"]
    result: Optional[str]

# ==========================================
# 3. 初始化 LLM
# ==========================================
llm = ChatOpenAI(model="Qwen3-30B-A3B", base_url="http://192.168.0.147:8997/v1", api_key="123456", temperature=0)

# ==========================================
# 4. 构建子 Agent (Specialists)
# ==========================================
# 使用 LangGraph prebuilt 的 create_react_agent，它们自带 ReAct 循环

# 4.1 PrepChef: 负责洗切
prep_agent = create_react_agent(
    llm, 
    tools=[wash_tool, cut_tool],
    prompt=f"""你是备菜厨师。根据任务指令，自行决定是先洗后切，还是直接切。
    需要根据经验，输入对应的时间
    经验：
    {COOKING_KB}
    完成后简要汇报。"""
)

# 4.2 WokChef: 负责烹饪
wok_agent = create_react_agent(
    llm,
    tools=[boil_tool, fry_tool, stew_tool, seasoning_tool],
    prompt=f"""
    你是灶台大厨。擅长制作各种复杂的肉菜和蔬菜。
    接到菜名后，请自行拆解步骤。
    例如做红烧肉：可能需要先 boil(焯水)，再 fry(煸炒)，最后 stew(炖)。
    需要根据经验，输入对应的时间
    经验：
    {COOKING_KB}
    完成后简要汇报。
    """
)

# 4.3 RiceChef: 负责主食
rice_agent = create_react_agent(
    llm,
    tools=[cook_rice_tool],
    prompt="你是主食厨师。只负责煮饭。"
)

# ==========================================
# 5. 核心节点逻辑
# ==========================================

# --- 总厨 (Planner) ---
async def head_chef_node(state: AgentState, config: RunnableConfig, store: InMemoryStore):
    user_input = state["messages"][-1].content
    user_id = config["configurable"]["thread_id"]
    
    print(f"👨‍🍳 [总厨] 接单: {user_input}。正在拆解宏观任务...")
    kb_text = json.dumps(COOKING_KB, indent=2, ensure_ascii=False)

    prompt = f"""
    你是一个行政总厨。请将用户需求拆解为 3 个 Agent 的**宏观任务**。
    参考知识库：
    {kb_text}
    
    Agents:
    1. RiceChef: 煮饭。
    2. PrepChef: 准备食材（洗、切）。
    3. WokChef: 烹饪（焯、炒、炖）。
    
    【规则】
    1. 即使是做一道菜，也需要拆分：PrepChef 先备料，WokChef 后烹饪。
    2. 必须生成 JSON，包含 tasks 列表。每个 task 有 id, assignee, instruction, dependencies。
    3. 需要列清楚 各个工序的依赖，不可以省略。
    
    示例输出：
    {{
        "tasks": [
            {{ "id": "t1", "assignee": "RiceChef", "instruction": "煮2碗饭", "dependencies": [] }},
            {{ "id": "t2", "assignee": "PrepChef", "instruction": "准备红烧肉用的五花肉(切块)和姜片", "dependencies": [] }},
            {{ "id": "t3", "assignee": "WokChef", "instruction": "制作红烧肉", "dependencies": ["t2"] }}
        ]
    }}
    """
    
    response = await llm.ainvoke([SystemMessage(content=prompt), HumanMessage(content=user_input)])
    content = response.content
    if "</think>" in content: content = content.split("</think>")[-1]
    content = content.replace("```json", "").replace("```", "").strip()
    
    try:
        plan_data = json.loads(content)
        tasks = plan_data.get("tasks", [])
        
        print(f"📝 [总厨] 宏观计划已生成，派发 {len(tasks)} 个任务到 Store (细粒度Key)...")
        
        # ★★★ 优化：使用细粒度 Key 存储 Task ★★★
        # Namespace: ("kitchen", user_id, "tasks")
        # Key: task_id
        for task in tasks:
            task["status"] = "pending"
            task["result"] = None
            # 存入 Store
            await store.aput(
                ("kitchen", user_id, "tasks"), 
                task["id"], 
                task
            )
            
            # 打印依赖关系
            dep_str = f"依赖 {task['dependencies']}" if task['dependencies'] else "无依赖"
            print(f"   -> Task[{task['id']}] -> {task['assignee']}: {task['instruction']} ({dep_str})")
            
    except Exception as e:
        print(f"❌ 规划失败: {e}")
        return {"messages": []}

    return {"messages": [BaseMessage(content="Tasks Dispatched", type="ai")]}

# --- 通用 Worker Wrapper (负责与 Store 交互 + 调用子 Agent) ---
async def worker_bridge(role: str, agent_app, state: AgentState, config: RunnableConfig, store: InMemoryStore):
    user_id = config["configurable"]["thread_id"]
    namespace = ("kitchen", user_id, "tasks")
    
    while True:
        # 1. 扫描 Store，寻找分给我的、状态为 pending 的任务
        # list 方法返回 Item 对象列表
        all_items = await store.asearch(namespace) 
        
        my_task = None
        for item in all_items:
            task_data = item.value
            if task_data["assignee"] == role and task_data["status"] == "pending":
                my_task = task_data
                break
        
        if not my_task:
            # 没有我的任务了，下班
            break
            
        task_id = my_task["id"]
        
        # 2. 检查依赖
        dependencies = my_task.get("dependencies", [])
        all_deps_met = True
        
        if dependencies:
            # 再次查询依赖任务的状态
            for dep_id in dependencies:
                dep_item = await store.aget(namespace, dep_id)
                if not dep_item or dep_item.value["status"] != "done":
                    all_deps_met = False
                    break
        
        if not all_deps_met:
            # print(f"✋ [{role}] 等待依赖中... (Task {task_id})")
            await asyncio.sleep(1.0 * TIME_SCALE)
            continue # 继续轮询
            
        # 3. 依赖满足，开始执行
        print(f"🚀 [{role}] 开始执行 Task {task_id}: {my_task['instruction']}")
        
        # 更新状态为 processing (原子操作优化点：CAS，这里简化直接写)
        my_task["status"] = "processing"
        await store.aput(namespace, task_id, my_task)
        
        # ★★★ 调用子 Agent (ReAct) ★★★
        # 我们把任务指令作为 User Message 发给子 Agent
        # 子 Agent 会自己 Loop 调用工具，直到给出 Final Answer
        agent_response = await agent_app.ainvoke(
            {"messages": [HumanMessage(content=my_task["instruction"])]}
        )
        
        final_answer = agent_response["messages"][-1].content
        print(f"✅ [{role}] Task {task_id} 完成汇报: {final_answer}")
        
        # 4. 更新状态为 done
        my_task["status"] = "done"
        my_task["result"] = final_answer
        await store.aput(namespace, task_id, my_task)
        
        # 继续循环，看还有没有下一个任务

    return {"messages": [BaseMessage(content=f"{role} work finished", type="ai")]}

# --- 具体节点的包装 ---
async def rice_node(state, config, store):
    return await worker_bridge("RiceChef", rice_agent, state, config, store)

async def prep_node(state, config, store):
    return await worker_bridge("PrepChef", prep_agent, state, config, store)

async def wok_node(state, config, store):
    return await worker_bridge("WokChef", wok_agent, state, config, store)

async def monitor_node(state, config, store):
    # 检查所有任务是否完成
    user_id = config["configurable"]["thread_id"]
    namespace = ("kitchen", user_id, "tasks")
    items = await store.asearch(namespace)
    
    if items and all(item.value["status"] == "done" for item in items):
        return {"messages": [BaseMessage(content="🔔 所有工序全部完成！", type="ai")]}
    return {}

# ==========================================
# 6. 构建主图
# ==========================================

in_memory_store = InMemoryStore()
memory_saver = MemorySaver()
workflow = StateGraph(AgentState)

# 注入
workflow.add_node("HeadChef", functools.partial(head_chef_node, store=in_memory_store))
workflow.add_node("RiceChef", functools.partial(rice_node, store=in_memory_store))
workflow.add_node("PrepChef", functools.partial(prep_node, store=in_memory_store))
workflow.add_node("WokChef", functools.partial(wok_node, store=in_memory_store))
workflow.add_node("Monitor", functools.partial(monitor_node, store=in_memory_store))

# 流程
workflow.add_edge(START, "HeadChef")
workflow.add_edge("HeadChef", "RiceChef")
workflow.add_edge("HeadChef", "PrepChef")
workflow.add_edge("HeadChef", "WokChef")
workflow.add_edge("RiceChef", "Monitor")
workflow.add_edge("PrepChef", "Monitor")
workflow.add_edge("WokChef", "Monitor")
workflow.add_edge("Monitor", END)

app = workflow.compile(checkpointer=memory_saver, store=in_memory_store)

# ==========================================
# 7. 运行
# ==========================================

async def main():
    print("🍳 分层多智能体烹饪系统启动...")
    thread_id = uuid.uuid4().hex
    config = {"configurable": {"thread_id": thread_id}}
    
    # 复杂任务：红烧肉需要复杂的工序，WokChef 需要自我规划
    user_input = "我想吃蛋炒饭"
    inputs = {"messages": [HumanMessage(content=user_input)]}
    
    print(f"\n👤 用户: {user_input}\n" + "="*50)
    
    try:
        async for event in app.astream(inputs, config=config):
            pass
    except Exception as e:
        print(f"Error: {e}")

    # 最终审计 (使用 asearch 扫描所有任务)
    print("\n🔍 最终任务状态审计:")
    items = await in_memory_store.asearch(("kitchen", thread_id, "tasks"))
    # 按 ID 排序
    items.sort(key=lambda x: x.value["id"])
    
    for item in items:
        t = item.value
        print(f"  ✅ Task {t['id']} [{t['assignee']}]: {t['instruction']} -> {t.get('result')[:30]}...")

if __name__ == "__main__":
    asyncio.run(main())