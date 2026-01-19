import asyncio
import json
import uuid
import time
import functools 
import operator
from typing import Annotated, List, Literal, TypedDict, Dict, Any, Optional
from enum import Enum

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, BaseMessage
from langchain_core.tools import tool, BaseTool
from langchain_core.runnables import RunnableConfig

from langgraph.graph import StateGraph, END, START
from langgraph.store.memory import InMemoryStore
from langgraph.checkpoint.memory import MemorySaver

# ==========================================
# 0. 领域知识库
# ==========================================
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

# ==========================================
# 1. 基础设置
# ==========================================
# 1秒模拟现实 10分钟
TIME_SCALE = 0.1 

class CookingMethod(str, Enum):
    COOK_RICE = "煮饭"
    PREP_WASH = "洗"
    PREP_CUT = "切"
    STIR_FRY = "爆炒"
    STEW = "慢炖"

# ==========================================
# 2. 定义工具
# ==========================================

class BaseCookingTool(BaseTool):
    name: str
    description: str
    method: CookingMethod

    def _run(self, *args, **kwargs): raise NotImplementedError()

    async def _arun(self, item_name: str, duration_mins: int):
        simulated_time = duration_mins * TIME_SCALE
        print(f"\n⏳ [{self.method.value}] 执行中: {item_name} (模拟 {simulated_time:.2f}s)...")
        await asyncio.sleep(simulated_time)
        return f"✅ [{self.method.value}] 完成: {item_name}"

class RiceCookerTool(BaseCookingTool):
    name: str = "cook_rice"
    description: str = "智能电饭煲"
    method: CookingMethod = CookingMethod.COOK_RICE
    
    async def _arun(self, item_name: str, duration_mins: int):
        print(f"\n🔌 [电饭煲] 启动: {item_name} (后台运行中)")
        await asyncio.sleep(0.2 * TIME_SCALE) # 启动操作
        
        simulated_time = duration_mins * TIME_SCALE
        await asyncio.sleep(simulated_time) # 运行
        
        print(f"\n🔔 [电饭煲] 叮！{item_name} 熟了！")
        return f"✅ {item_name} 煮好了"

tools_map = {
    "cook_rice": RiceCookerTool(),
    "wash_food": BaseCookingTool(name="wash_food", description="洗", method=CookingMethod.PREP_WASH),
    "cut_food":  BaseCookingTool(name="cut_food", description="切", method=CookingMethod.PREP_CUT),
    "stir_fry_food": BaseCookingTool(name="stir_fry_food", description="炒", method=CookingMethod.STIR_FRY),
    "stew_food":     BaseCookingTool(name="stew_food", description="炖", method=CookingMethod.STEW),
}

# ==========================================
# 3. 状态与 Store 结构
# ==========================================

class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], operator.add]

# ==========================================
# 4. 初始化
# ==========================================
llm = ChatOpenAI(model="Qwen3-30B-A3B", base_url="http://192.168.0.147:8997/v1", api_key="123456", temperature=0)

# ==========================================
# 5. 核心节点逻辑
# ==========================================

# --- 节点 1: 总厨 (Planner) ---
async def head_chef_node(state: AgentState, config: RunnableConfig, store: InMemoryStore):
    user_input = state["messages"][-1].content
    user_id = config["configurable"]["thread_id"]
    
    print(f"👨‍🍳 [总厨] 接单: {user_input}。开始构建依赖关系图...")

    kb_text = json.dumps(COOKING_KB, indent=2, ensure_ascii=False)

    prompt = f"""
    你是一个精通统筹的总厨。请生成详细的烹饪计划 JSON。
    参考知识库：
    {kb_text}
    
    【关键要求】
    1. **依赖管理**：非常重要！每个步骤必须包含 `dependencies` 字段（即前置步骤的 id 列表）。
       - 如果是炒饭，【炒】必须依赖【煮饭】和【切配】。
       - 如果是炒菜，【炒】必须依赖【洗】和【切】。
       - 【煮饭】通常没有依赖（dependencies: []）。
       - 【洗】通常没有依赖。
    2. **时间预估**：根据菜品实际情况填写 `duration`。
    
    例子输出格式：
    {{
        "steps": [
            {{ "id": 1, "agent": "RiceChef", "tool": "cook_rice", "item": "米饭", "duration": 20, "dependencies": [] }},
            {{ "id": 2, "agent": "PrepChef", "tool": "wash_food", "item": "葱花鸡蛋", "duration": 2, "dependencies": [] }},
            {{ "id": 3, "agent": "WokChef", "tool": "stir_fry_food", "item": "蛋炒饭", "duration": 4, "dependencies": [1, 2] }}
        ]
    }}
    """
    
    response = await llm.ainvoke([SystemMessage(content=prompt), HumanMessage(content=user_input)])
    content = response.content
    if "</think>" in content: content = content.split("</think>")[-1]
    content = content.replace("```json", "").replace("```", "").strip()
    
    try:
        plan_data = json.loads(content)
        await store.aput(("kitchen",), user_id, {"plan": plan_data})
        
        print(f"📝 [总厨] 计划发布。依赖关系如下:")
        for s in plan_data['steps']:
            dep_str = f" 依赖: {s['dependencies']}" if s['dependencies'] else " (无依赖)"
            print(f"   Step {s['id']}: [{s['agent']}] {s['tool']} -> {s['item']}{dep_str}")
            
    except Exception as e:
        print(f"❌ 规划失败: {e}")
        return {"messages": []}

    return {"messages": [BaseMessage(content="Plan Created", type="ai")]}

# --- 智能 Worker (带依赖检查) ---
async def worker_node(role: str, state: AgentState, config: RunnableConfig, store: InMemoryStore):
    user_id = config["configurable"]["thread_id"]
    
    # 循环检查，直到所有属于我的任务都完成
    while True:
        # 1. 每次循环都从 Store 拉取最新计划 (Sync)
        memory = await store.aget(("kitchen",), user_id)
        if not memory: break
        
        plan = memory.value.get("plan")
        steps = plan.get("steps", [])
        
        # 2. 找到我的下一个 Pending 任务
        # 我们假设 Agent 是串行执行自己的任务的 (做完一个做一个)
        my_next_task = None
        for step in steps:
            if step["agent"] == role and step.get("status") != "done":
                my_next_task = step
                break # 找到第一个没做的，准备处理
        
        # 如果没有任务了，下班
        if not my_next_task:
            break
            
        # 3. ★★★ 检查依赖 (Check Dependencies) ★★★
        dependencies = my_next_task.get("dependencies", [])
        all_deps_met = True
        missing_dep_names = []
        
        if dependencies:
            # 检查 plan 中对应 ID 的 step 状态
            for step in steps:
                if step["id"] in dependencies:
                    if step.get("status") != "done":
                        all_deps_met = False
                        missing_dep_names.append(f"{step['item']}(Step {step['id']})")
        
        if not all_deps_met:
            # 依赖未满足：等待并重试
            print(f"✋ [{role}] 就绪，但正在等待前置任务: {', '.join(missing_dep_names)}...")
            await asyncio.sleep(1.0 * TIME_SCALE) # 等待一会再轮询 Store
            continue # 重新开始循环，去 Store 拉最新的状态
            
        # 4. 执行任务
        tool_name = my_next_task["tool"]
        item = my_next_task["item"]
        duration = my_next_task["duration"]
        
        tool_instance = tools_map.get(tool_name)
        if tool_instance:
            # 执行
            await tool_instance.ainvoke({"item_name": item, "duration_mins": duration})
            
            # 5. 更新状态 (Critical Section)
            # 重新拉取一次防止覆盖 (简单的乐观锁逻辑)
            # 在 Demo 中简单处理，实际应加锁
            current_mem = await store.aget(("kitchen",), user_id)
            current_plan = current_mem.value.get("plan")
            
            # 找到对应的 step 更新
            for s in current_plan["steps"]:
                if s["id"] == my_next_task["id"]:
                    s["status"] = "done"
                    break
            
            await store.aput(("kitchen",), user_id, {"plan": current_plan})
        
        # 任务完成，继续循环处理下一个任务

    return {"messages": [BaseMessage(content=f"{role} finished", type="ai")]}

# --- Agent Wrappers ---
async def rice_chef_node(state, config, store):
    print("🍚 [RiceChef] 上班")
    return await worker_node("RiceChef", state, config, store)

async def prep_chef_node(state, config, store):
    print("🔪 [PrepChef] 上班")
    return await worker_node("PrepChef", state, config, store)

async def wok_chef_node(state, config, store):
    print("🔥 [WokChef] 上班")
    return await worker_node("WokChef", state, config, store)

async def monitor_node(state, config, store):
    user_id = config["configurable"]["thread_id"]
    memory = await store.aget(("kitchen",), user_id)
    if not memory: return {}
    steps = memory.value.get("plan", {}).get("steps", [])
    if all(s.get("status") == "done" for s in steps):
        return {"messages": [BaseMessage(content="🔔 所有菜品制作完成！", type="ai")]}
    return {}

# ==========================================
# 6. 构建图
# ==========================================

in_memory_store = InMemoryStore()
memory_saver = MemorySaver()
workflow = StateGraph(AgentState)

# 注入 Store
workflow.add_node("HeadChef", functools.partial(head_chef_node, store=in_memory_store))
workflow.add_node("RiceChef", functools.partial(rice_chef_node, store=in_memory_store))
workflow.add_node("PrepChef", functools.partial(prep_chef_node, store=in_memory_store))
workflow.add_node("WokChef", functools.partial(wok_chef_node, store=in_memory_store))
workflow.add_node("Monitor", functools.partial(monitor_node, store=in_memory_store))

workflow.add_edge(START, "HeadChef")
# 并行启动
workflow.add_edge("HeadChef", "RiceChef")
workflow.add_edge("HeadChef", "PrepChef")
workflow.add_edge("HeadChef", "WokChef")
# 汇聚
workflow.add_edge("RiceChef", "Monitor")
workflow.add_edge("PrepChef", "Monitor")
workflow.add_edge("WokChef", "Monitor")
workflow.add_edge("Monitor", END)

app = workflow.compile(checkpointer=memory_saver, store=in_memory_store)

# ==========================================
# 7. 运行
# ==========================================

async def main():
    print("🍳 智能烹饪系统 (带依赖同步)...")
    thread_id = uuid.uuid4().hex
    config = {"configurable": {"thread_id": thread_id}}
    
    # 这里的关键是：炒饭需要饭和蛋都好了才能炒
    user_input = "我要做一个四人饭菜，有水煮肉片，炒菠菜，烤鸭和卤牛肉。其中烤鸭已经买好了整只,你只需要切，但卤牛肉需要从新鲜牛肉开始做；需要煮饭"
    inputs = {"messages": [HumanMessage(content=user_input)]}
    
    print(f"\n👤 用户: {user_input}\n" + "="*50)
    
    try:
        async for event in app.astream(inputs, config=config):
            pass
    except Exception as e:
        print(f"Error: {e}")

    # 最终审计
    final_store = await in_memory_store.aget(("kitchen",), thread_id)
    if final_store:
        print("\n🔍 最终状态:")
        steps = final_store.value["plan"]["steps"]
        for s in steps:
            print(f"  ✅ Step {s['id']}: {s['item']} (Status: {s.get('status', 'pending')})")

if __name__ == "__main__":
    asyncio.run(main())