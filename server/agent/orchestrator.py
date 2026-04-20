#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
AgentOrchestrator —— 多 Agent 协同编排引擎

流程：
  1. SupervisorAgent 识别意图 → 生成执行计划（Agent 列表）
  2. 按顺序执行各子 Agent，共享同一个 AgentContext
  3. CheckAgent 评估结果：
       - passed → 流程结束，汇总答案
       - failed + 重试次数未超限 → SupervisorAgent 重规划 → 继续执行
  4. 整个过程通过 AsyncGenerator 流式向外推送事件，
     供 SSE 接口实时推送给前端

事件格式（JSON Lines）：
  {"event": "plan",    "data": {"intent": "...", "plan": [...]}}
  {"event": "agent",   "data": {"name": "...", "status": "running"}}
  {"event": "result",  "data": {"name": "...", "summary": "..."}}
  {"event": "check",   "data": {"passed": true, "score": 0.9}}
  {"event": "replan",  "data": {"new_plan": [...]}}
  {"event": "answer",  "data": {"content": "...", "sources": [...]}}
  {"event": "error",   "data": {"message": "..."}}
"""

import asyncio
import json
from typing import AsyncGenerator, Dict, List, Optional

from server.agent.base import AgentContext
from server.agent.supervisor_agent import SupervisorAgent
from server.agent.rag_agent import RAGAgent
from server.agent.writing_agent import WritingAgent
from server.agent.translation_agent import TranslationAgent
from server.agent.check_agent import CheckAgent
from server.utils.logger import logger

MAX_RETRY = 2   # CheckAgent 失败后最多重规划次数

# Agent 注册表
_AGENT_REGISTRY = {
    "rag_agent":         RAGAgent,
    "writing_agent":     WritingAgent,
    "translation_agent": TranslationAgent,
    "check_agent":       CheckAgent,
}


def _event(name: str, data: Dict) -> str:
    return json.dumps({"event": name, "data": data}, ensure_ascii=False)


class AgentOrchestrator:
    """
    AgentOrchestrator 是无状态的，每次对话调用 run() 创建新的执行流。
    Agent 实例在 Orchestrator 内部按需创建（轻量，无连接资源）。
    """

    def __init__(self):
        self.supervisor = SupervisorAgent()

    async def run(
        self,
        ctx: AgentContext,
        user_input: str,
    ) -> AsyncGenerator[str, None]:
        """
        流式执行 Agent 流程，通过 AsyncGenerator 推送事件。
        调用方 async for event in orchestrator.run(ctx, input) 即可。
        """
        ctx.add_message("user", user_input)

        # ── Step 1: Supervisor 规划 ────────────────────────────────────
        try:
            sup_result = await self.supervisor.execute(ctx, user_input=user_input)
        except Exception as e:
            yield _event("error", {"message": f"Supervisor 规划失败：{e}"})
            return

        plan: List[str] = sup_result["plan"]
        intent: str = sup_result["intent"]
        yield _event("plan", {"intent": intent, "plan": plan})

        # ── Step 2: 按计划执行子 Agent（支持重规划）───────────────────
        retry_count = 0
        remaining_plan = list(plan)
        ctx.shared_memory["completed_agents"] = []

        while remaining_plan:
            agent_name = remaining_plan.pop(0)

            # 跳过不认识的 Agent 名（防御性处理）
            if agent_name not in _AGENT_REGISTRY and agent_name != "supervisor_agent":
                logger.warning(f"[Orchestrator] unknown agent: {agent_name}, skip")
                continue

            yield _event("agent", {"name": agent_name, "status": "running"})

            try:
                agent = _AGENT_REGISTRY[agent_name]()
                result = await agent.execute(ctx)
            except Exception as e:
                yield _event("error", {"message": f"{agent_name} 执行失败：{e}"})
                # 非 CheckAgent 失败直接中止
                if agent_name != "check_agent":
                    return
                result = {"passed": False, "score": 0.0, "issue": str(e), "summary": ""}

            ctx.shared_memory["completed_agents"].append(agent_name)
            yield _event("result", {"name": agent_name, "summary": result.get("summary", "")})

            # ── CheckAgent 后处理 ──────────────────────────────────
            if agent_name == "check_agent":
                passed = result.get("passed", True)
                score = result.get("score", 1.0)
                yield _event("check", {"passed": passed, "score": score, "issue": result.get("issue", "")})

                if not passed and retry_count < MAX_RETRY:
                    retry_count += 1
                    logger.info(f"[Orchestrator] check failed (retry {retry_count}/{MAX_RETRY}), replanning...")
                    new_plan = await self.supervisor.replan(ctx, result)
                    remaining_plan = new_plan
                    yield _event("replan", {"new_plan": new_plan, "retry": retry_count})
                # passed 或超限：继续到流程结束

        # ── Step 3: 汇总最终答案 ──────────────────────────────────────
        answer = self._compose_answer(ctx)
        ctx.final_answer = answer
        ctx.add_message("assistant", answer)

        sources = ctx.shared_memory.get("rag_sources", [])
        yield _event("answer", {"content": answer, "sources": sources})

    def _compose_answer(self, ctx: AgentContext) -> str:
        """
        按优先级取各 Agent 的输出，拼成最终回答。
        优先级：writing > translation > rag_answer
        """
        writing = ctx.shared_memory.get("writing_result", "")
        translation = ctx.shared_memory.get("translation_result", "")
        rag = ctx.shared_memory.get("rag_answer", "")

        # CheckAgent 有改进建议时附在末尾
        check = ctx.shared_memory.get("check_result", {})
        suggestion = check.get("suggestion", "")

        main = writing or translation or rag or "抱歉，未能生成有效回答。"

        if suggestion and not check.get("passed", True):
            main += f"\n\n> **注意**：{suggestion}"

        return main


# 全局单例（无状态，可共享）
orchestrator = AgentOrchestrator()
