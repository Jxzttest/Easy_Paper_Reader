import asyncio
import json
import uuid
import time
import functools
import operator
from typing import Annotated, List, Literal, TypedDict, Dict, Any, Optional
from datetime import datetime

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, BaseMessage, SystemMessage
from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig

from langgraph.graph import StateGraph, END, START
from langchain.agents import create_agent
from langgraph.graph.state import CompiledStateGraph
from langgraph.store.memory import InMemoryStore
from langgraph.checkpoint.memory import MemorySaver

# ==========================================
# 1. 基础配置 & 知识库
# ==========================================
TIME_SCALE = 0.1

# 知识库优化：只记录基本技能，不预判任务类型
COOKING_KB = {
    "cook_rice": {"agent": "RiceChef", "desc": "煮饭", "time": 100},
    "wash_food": {"agent": "PrepChef", "desc": "清洗", "time": 3},
    "cut_food":  {"agent": "PrepChef", "desc": "切配", "time": 5},
    "boil_food": {"agent": "WokChef",  "desc": "焯水", "time": 5},
    "stir_fry":  {"agent": "WokChef",  "desc": "爆炒", "time": 4},
    "stew_food": {"agent": "WokChef",  "desc": "慢炖", "time": 60},
}

# ==========================================
# 2. 工具定义 (增强版)
# ==========================================
@tool
async def wash_tool(item: str, time_use: int, store: InMemoryStore = None, 
                    task_id: str = None, user_id: str = None):
    """清洗食材。输入食材名称。会自动更新任务状态。"""
    print(f"🌊 [PrepChef] 正在清洗: {item}...")
    
    # 如果是后台任务模式，立即标记为running并返回
    if store and task_id and user_id:
        namespace = ("kitchen", user_id, "tasks")
        task_item = await store.aget(namespace, task_id)
        task = task_item.value
        if task.get("is_background", False):
            task["status"] = "running"
            task["start_time"] = time.time()
            await store.aput(namespace, task_id, task)
            print(f"🔌 [PrepChef] 启动后台清洗任务: {task_id}")
            return f"已启动后台清洗 {item}，预计需要{time_use}分钟"
    
    # 正常执行（阻塞模式）
    await asyncio.sleep(2 * time_use)
    result = f"{item} 已清洗干净"
    
    # 更新任务状态
    if store and task_id and user_id:
        task["status"] = "done"
        task["result"] = result
        task["end_time"] = time.time()
        await store.aput(namespace, task_id, task)
    
    return result

@tool
async def cut_tool(item: str, time_use: int, shape: str = "块", 
                   store: InMemoryStore = None, task_id: str = None, user_id: str = None):
    """切配食材。会自动更新任务状态。"""
    print(f"🔪 [PrepChef] 正在切: {item} -> {shape}...")
    
    if store and task_id and user_id:
        namespace = ("kitchen", user_id, "tasks")
        task_item = await store.aget(namespace, task_id)
        task = task_item.value
        if task.get("is_background", False):
            task["status"] = "running"
            task["start_time"] = time.time()
            await store.aput(namespace, task_id, task)
            print(f"🔌 [PrepChef] 启动后台切配任务: {task_id}")
            return f"已启动后台切配 {item}，预计需要{time_use}分钟"
    
    await asyncio.sleep(3 * time_use)
    result = f"{item} 已切成{shape}"
    
    if store and task_id and user_id:
        task["status"] = "done"
        task["result"] = result
        task["end_time"] = time.time()
        await store.aput(namespace, task_id, task)
    
    return result

@tool
async def cook_rice_tool(amount: str, time_use: int, store: InMemoryStore = None,
                        task_id: str = None, user_id: str = None):
    """煮饭。会自动判断为后台任务。"""
    namespace = ("kitchen", user_id, "tasks")
    task_item = await store.aget(namespace, task_id)
    task = task_item.value

    # 1) 立即把状态改成 running 并写回
    task["status"] = "running"
    task["start_time"] = time.time()
    await store.aput(namespace, task_id, task)

    # 2) 启动后台协程去做“长时间”工作
    async def _real_cook() -> None:
        # 真正 sleep 的是这里，但它跑在独立 Task 里
        await asyncio.sleep(time_use * 60)
        # 到点后把状态改 done
        task["status"] = "done"
        task["result"] = f"{amount} 米饭已煮熟"
        await store.aput(namespace, task_id, task)
        print(f"🔔 [RiceChef] 后台任务完成：{task_id}")

    asyncio.create_task(_real_cook())
    
    # 不等待完成，立即返回
    return f"已启动煮{amount}米饭，预计需要{time_use}分钟"

@tool
async def boil_tool(item: str, time_use: int,
                    store: InMemoryStore = None, task_id: str = None, user_id: str = None):
    """焯水/水煮。用于去除血水或煮熟。"""
    print(f"🔥 [WokChef] 正在焯水/水煮: {item}...")
    if store and task_id and user_id:
        namespace = ("kitchen", user_id, "tasks")
        task_item = await store.aget(namespace, task_id)
        task = task_item.value
        if task.get("is_background", False):
            task["status"] = "running"
            task["start_time"] = time.time()
            await store.aput(namespace, task_id, task)
            print(f"🔌 [PrepChef] 启动后台切配任务: {task_id}")
            return f"已启动后台切配 {result}，预计需要{time_use}分钟"
    
    await asyncio.sleep(4 * time_use)
    result = f"{item} 收汁完成"
    if store and task_id and user_id:
        task["status"] = "done"
        task["result"] = result
        task["end_time"] = time.time()
        await store.aput(namespace, task_id, task)
    await asyncio.sleep(4 * time_use)
    return result

@tool
async def fry_tool(item: str, time_use: int,
                   store: InMemoryStore = None, task_id: str = None, user_id: str = None):
    """煎/炒。用于煸炒出油或煎至金黄。"""
    print(f"🔥 [WokChef] 正在煎炒: {item}...")
    
    if store and task_id and user_id:
        namespace = ("kitchen", user_id, "tasks")
        task_item = await store.aget(namespace, task_id)
        task = task_item.value
        if task.get("is_background", False):
            task["status"] = "running"
            task["start_time"] = time.time()
            await store.aput(namespace, task_id, task)
            print(f"🔌 [PrepChef] 启动后台切配任务: {task_id}")
            return f"已启动后台切配 {item}，预计需要{time_use}分钟"
    
    await asyncio.sleep(3 * time_use)
    result = f"{item} 煎炒完成"
    
    if store and task_id and user_id:
        task["status"] = "done"
        task["result"] = result
        task["end_time"] = time.time()
        await store.aput(namespace, task_id, task)
    
    return result

@tool
async def stew_tool(item: str, time_use: int,
                    store: InMemoryStore = None, task_id: str = None, user_id: str = None):
    """炖/焖。耗时较长，用于软烂入味。"""
    print(f"🥘 [WokChef] 正在慢炖: {item} (耗时操作)...")
    if store and task_id and user_id:
        namespace = ("kitchen", user_id, "tasks")
        task_item = await store.aget(namespace, task_id)
        task = task_item.value
        if task.get("is_background", False):
            task["status"] = "running"
            task["start_time"] = time.time()
            await store.aput(namespace, task_id, task)
            print(f"🔌 [PrepChef] 启动后台切配任务: {task_id}")
            return f"已启动后台切配 {item}，预计需要{time_use}分钟"
    
    await asyncio.sleep(10 * time_use)
    result = f"{item} 炖煮完成，软烂入味"
    
    if store and task_id and user_id:
        task["status"] = "done"
        task["result"] = result
        task["end_time"] = time.time()
        await store.aput(namespace, task_id, task)
    return result

@tool
async def seasoning_tool(action: str, time_use: int,
                         store: InMemoryStore = None, task_id: str = None, user_id: str = None):
    """调味/勾芡/收汁。"""
    print(f"🧂 [WokChef] 正在{action}...")
    if store and task_id and user_id:
        namespace = ("kitchen", user_id, "tasks")
        task_item = await store.aget(namespace, task_id)
        task = task_item.value
        if task.get("is_background", False):
            task["status"] = "running"
            task["start_time"] = time.time()
            await store.aput(namespace, task_id, task)
            print(f"🔌 [PrepChef] 启动后台切配任务: {task_id}")
            return f"已启动后台切配 {action}，预计需要{time_use}分钟"
    
    await asyncio.sleep(10 * time_use)
    result = f"{action} 收汁完成"
    if store and task_id and user_id:
        task["status"] = "done"
        task["result"] = result
        task["end_time"] = time.time()
        await store.aput(namespace, task_id, task)
    return f"{action} 完成"

# ==========================================
# 3. 初始化 Agents (优化版)
# ==========================================
llm = ChatOpenAI(model="Qwen3-30B-A3B", base_url="http://192.168.0.147:8997/v1", 
                api_key="123456", temperature=0)


prep_agent = create_agent(
    llm, 
    tools=[wash_tool, cut_tool],
    system_prompt=f"""你是备菜厨师。根据任务指令，自行决定是先洗后切，还是直接切。
    需要根据经验，输入对应的时间
    经验：
    {COOKING_KB}
    完成后简要汇报。"""
)

# 4.2 WokChef: 负责烹饪
wok_agent = create_agent(
    llm,
    tools=[boil_tool, fry_tool, stew_tool, seasoning_tool],
    system_prompt=f"""
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
rice_agent = create_agent(
    llm,
    tools=[cook_rice_tool],
    system_prompt="你是主食厨师。只负责煮饭。"
)

class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], operator.add]
    assignments: Annotated[Dict[str, str], lambda a, b: b]
    current_task_id: Annotated[str, lambda a, b: b]  # 新增：当前处理的任务ID

class Task(TypedDict):
    id: str
    assignee: str
    instruction: str
    duration: int
    dependencies: List[str]
    status: Literal["pending", "processing", "running", "done"] # 等待、 制作中、 后台运行、完成
    is_background: bool  # 由Agent决定
    start_time: float
    end_time: float
    result: Optional[str]

# ==========================================
# 4. 节点逻辑 (优化版)
# ==========================================

# --- Node 1: 总厨 (规划器) ---
async def head_chef_node(state: AgentState, config: RunnableConfig, store: InMemoryStore):
    user_input = state["messages"][-1].content
    user_id = config["configurable"]["thread_id"]
    namespace = ("kitchen", user_id, "tasks")
    kb_text = json.dumps(COOKING_KB, indent=2, ensure_ascii=False)
    
    print(f"👨‍🍳 [总厨] 接单: {user_input}。正在规划...")

    prompt = f"""
    你是一个行政总厨。请将用户需求拆解为 3 个 Agent 的**宏观任务**。
    参考知识库：
    {kb_text}
    
    Agents:
    1. RiceChef: 煮饭。
    2. PrepChef: 准备食材（洗、切）。
    3. WokChef: 烹饪（焯、炒、炖、调味/勾芡/收汁）。
    
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
    
    response = await llm.ainvoke([SystemMessage(content=prompt), 
                                 HumanMessage(content=user_input)])
    content = response.content
    if "</think>" in content: 
        content = content.split("</think>")[-1]
    content = content.replace("```json", "").replace("```", "").strip()
    
    try:
        plan_data = json.loads(content)
        tasks = plan_data.get("tasks", [])
        
        for t in tasks:
            t["status"] = "pending"
            t["is_background"] = False  # 默认不是后台任务
            t["start_time"] = 0.0
            t["end_time"] = 0.0
            t["result"] = None
            await store.aput(namespace, t["id"], t)
            
            print(f"   📋 [Plan] {t['id']} ({t['assignee']}): {t['instruction']}")
            
    except Exception as e:
        print(f"❌ 规划失败: {e}")
        return {"messages": []}

    return {"messages": [BaseMessage(content="Plan Created", type="ai")]}

# --- Node 2: 厨房经理 (优化版) ---
async def manager_node(state: AgentState, config: RunnableConfig, store: InMemoryStore):
    user_id = config["configurable"]["thread_id"]
    namespace = ("kitchen", user_id, "tasks")
    
    # 1. 获取所有任务
    items = await store.asearch(namespace, limit=100)
    all_tasks = {item.key: item.value for item in items}
    
    # 2. 寻找可分配的任务
    busy_agents = set()
    for t in all_tasks.values():
        if t["status"] in ["processing", "running"]:
            busy_agents.add(t["assignee"])
    
    pending_tasks = [t for t in all_tasks.values() if t["status"] == "pending"]
    new_assignments = {}
    
    for t in pending_tasks:
        assignee = t["assignee"]
        
        # 检查Agent是否空闲
        if assignee in busy_agents or assignee in new_assignments:
            continue
        
        # 检查依赖是否满足
        deps_met = True
        for dep_id in t.get("dependencies", []):
            dep_task = all_tasks.get(dep_id)
            if not dep_task or dep_task["status"] != "done":
                deps_met = False
                break
        
        if deps_met:
            new_assignments[assignee] = t["id"]
            t["status"] = "processing"
            await store.aput(namespace, t["id"], t)
            print(f"📣 [Manager] 指派: {assignee} -> {t['id']}")
    
    # 4. 完结判断
    not_done = [t for t in all_tasks.values() if t["status"] != "done"]
    if not not_done:
        return {"assignments": {}, "messages": [BaseMessage(content="ALL_DONE", type="ai")]}
    
    # 5. 如果有后台任务在运行，等待结束
    while True:
        background_running = [t for t in all_tasks.values() 
                            if t["status"] == "running" or t.get("is_background", True)]
        if any(background_running):
            await asyncio.sleep(1 * TIME_SCALE)  # 时间流逝
        else:
            # 任务都结束了
            break

    return {"assignments": new_assignments, "current_task_id": None}

# --- Node 3: 通用 Worker (优化版) ---
async def worker_node(role: str, agent_app: CompiledStateGraph, 
                     state: AgentState, config: RunnableConfig, store: InMemoryStore):
    assignments = state.get("assignments", {})
    my_task_id = assignments.get(role)
    
    if not my_task_id:
        return {}
    
    user_id = config["configurable"]["thread_id"]
    namespace = ("kitchen", user_id, "tasks")
    task_item = await store.aget(namespace, my_task_id)
    task = task_item.value
    
    print(f"🚀 [{role}] 开始执行: {task['instruction']}")
    
    # 这里假设agent_app可以接受带上下文的工具
    try:
        # 更新状态为进行中
        task["status"] = "processing"
        await store.aput(namespace, my_task_id, task)
        
        # 调用Agent
        agent_response = await agent_app.ainvoke(
            {"messages": [HumanMessage(content=task["instruction"])]}
        )
        
        result = agent_response["messages"][-1].content
        
        # 如果任务还未完成（比如后台任务），保持running状态
        if task["status"] != "running" and task["status"] != "done":
            task["status"] = "done"
            task["result"] = result
            task["end_time"] = time.time()
            await store.aput(namespace, my_task_id, task)
            print(f"✅ [{role}] 任务完成: {task['instruction']}")
        
    except Exception as e:
        print(f"❌ [{role}] 执行失败: {e}")
        task["status"] = "pending"  # 失败后重新排队
        task["result"] = f"执行失败: {str(e)}"
        await store.aput(namespace, my_task_id, task)
    
    return {"current_task_id": my_task_id}

# 包装函数
async def rice_wrapper(state, config, store): 
    return await worker_node("RiceChef", rice_agent, state, config, store)

async def prep_wrapper(state, config, store): 
    return await worker_node("PrepChef", prep_agent, state, config, store)

async def wok_wrapper(state, config, store):
    return await worker_node("WokChef", wok_agent, state, config, store)

# 路由函数
def router(state: AgentState):
    msgs = state.get("messages", [])
    if msgs and msgs[-1].content == "ALL_DONE":
        return END
    
    # 根据当前任务状态决定下一步
    assignments = state.get("assignments", {})
    if assignments:
        return list(assignments.keys())
    
    return ["Manager"]  # 没有任务时回到Manager检查

# ==========================================
# 5. 构建图
# ==========================================
in_memory_store = InMemoryStore()
memory_saver = MemorySaver()
workflow = StateGraph(AgentState)

workflow.add_node("HeadChef", functools.partial(head_chef_node, store=in_memory_store))
workflow.add_node("Manager", functools.partial(manager_node, store=in_memory_store))
workflow.add_node("RiceChef", functools.partial(rice_wrapper, store=in_memory_store))
workflow.add_node("PrepChef", functools.partial(prep_wrapper, store=in_memory_store))
workflow.add_node("WokChef", functools.partial(wok_wrapper, store=in_memory_store))

workflow.add_edge(START, "HeadChef")
workflow.add_edge("HeadChef", "Manager")

# 条件路由
workflow.add_conditional_edges("Manager", router, 
                               ["RiceChef", "PrepChef", "WokChef", END])

# 所有Worker完成后回到Manager
workflow.add_edge("RiceChef", "Manager")
workflow.add_edge("PrepChef", "Manager")
workflow.add_edge("WokChef", "Manager")

app = workflow.compile(checkpointer=memory_saver, store=in_memory_store)

# ==========================================
# 6. 运行
# ==========================================
async def main():
    print("🍳 优化版规划器-执行器模式")
    thread_id = uuid.uuid4().hex
    config = {"configurable": {"thread_id": thread_id}, "recursion_limit": 200}
    
    user_input = "做一份蛋炒饭，需要煮2碗米饭，洗切胡萝卜和鸡蛋"
    inputs = {"messages": [HumanMessage(content=user_input)]}
    
    print(f"\n👤 用户: {user_input}\n" + "="*50)
    
    try:
        async for event in app.astream(inputs, config=config):
            for node, value in event.items():
                if node != "__end__":
                    pass  # 可以在这里添加事件处理
    
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n🔍 最终任务状态:")
    items = await in_memory_store.asearch(("kitchen", thread_id, "tasks"), limit=100)
    for item in items:
        t = item.value
        status_icon = "✅" if t['status'] == 'done' else "⏳"
        bg_marker = "🔌" if t.get('is_background', False) else "⚡"
        print(f"  {status_icon} {bg_marker} {t['id']} [{t['assignee']}]: {t['instruction']} -> {t['status']}")

if __name__ == "__main__":
    asyncio.run(main())