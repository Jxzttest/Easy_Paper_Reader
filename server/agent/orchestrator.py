#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
AgentOrchestrator —— 多 Agent 协同编排引擎

流程：
  1. SupervisorAgent 识别意图 → 生成执行计划（Agent 列表）
  2a. 即时对话意图 → 按顺序执行各子 Agent，共享同一个 AgentContext
  2b. 后台任务意图 → 不执行 Agent，推送 confirm 事件，等待前端用户确认
      用户确认后通过 POST /tasks/confirm/{token} 触发实际执行
  3. CheckAgent 评估结果（仅即时对话）：
       - passed → 流程结束，汇总答案
       - failed + 重试次数未超限 → SupervisorAgent 重规划 → 继续执行
  4. 整个过程通过 AsyncGenerator 流式向外推送事件，
     供 SSE 接口实时推送给前端

事件格式（JSON Lines）：
  {"event": "plan",    "data": {"intent": "...", "plan": [...]}}
  {"event": "confirm", "data": {"token": "...", "task_type": "once"|"periodic",
                                 "task_desc": "...", "cron_expr": "..."}}
  {"event": "agent",   "data": {"name": "...", "status": "running"}}
  {"event": "result",  "data": {"name": "...", "summary": "..."}}
  {"event": "check",   "data": {"passed": true, "score": 0.9}}
  {"event": "replan",  "data": {"new_plan": [...]}}
  {"event": "answer",  "data": {"content": "...", "sources": [...]}}
  {"event": "error",   "data": {"message": "..."}}
"""

import asyncio
import json
import uuid
from typing import AsyncGenerator, Dict, List

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
        task_meta: Dict = sup_result.get("task_meta", {})
        yield _event("plan", {"intent": intent, "plan": plan})

        # ── Step 2a: 后台任务 → 发出 confirm 事件，不立即执行 ─────────
        if intent in ("task_once", "task_periodic"):
            token = "confirm_" + uuid.uuid4().hex
            # 将 task_meta 暂存在全局 pending store，等待确认
            _pending_tasks[token] = {
                **task_meta,
                "session_id": ctx.session_id,
                "paper_uuids": ctx.paper_uuids,
            }
            confirm_msg = _build_confirm_message(task_meta)
            yield _event("confirm", {
                "token": token,
                "task_type": task_meta.get("task_type", "once"),
                "task_desc": task_meta.get("task_desc", ""),
                "cron_expr": task_meta.get("cron_expr", ""),
                "message": confirm_msg,
            })
            # 将确认提示作为 assistant 消息保存到历史（让用户在对话界面看到）
            ctx.add_message("assistant", confirm_msg)
            yield _event("answer", {"content": confirm_msg, "sources": []})
            return

        # ── Step 2b: 即时对话 → 按计划执行子 Agent ────────────────────
        retry_count = 0
        remaining_plan = list(plan)
        ctx.shared_memory["completed_agents"] = []

        while remaining_plan:
            agent_name = remaining_plan.pop(0)

            if agent_name not in _AGENT_REGISTRY and agent_name != "supervisor_agent":
                logger.warning(f"[Orchestrator] unknown agent: {agent_name}, skip")
                continue

            yield _event("agent", {"name": agent_name, "status": "running"})

            try:
                agent = _AGENT_REGISTRY[agent_name]()
                result = await agent.execute(ctx)
            except Exception as e:
                yield _event("error", {"message": f"{agent_name} 执行失败：{e}"})
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

        # ── Step 3: 汇总最终答案 ──────────────────────────────────────
        answer = self._compose_answer(ctx)
        ctx.final_answer = answer
        ctx.add_message("assistant", answer)

        sources = ctx.shared_memory.get("rag_sources", [])
        yield _event("answer", {"content": answer, "sources": sources})

    def _compose_answer(self, ctx: AgentContext) -> str:
        writing = ctx.shared_memory.get("writing_result", "")
        translation = ctx.shared_memory.get("translation_result", "")
        rag = ctx.shared_memory.get("rag_answer", "")

        check = ctx.shared_memory.get("check_result", {})
        suggestion = check.get("suggestion", "")

        main = writing or translation or rag or "抱歉，未能生成有效回答。"

        if suggestion and not check.get("passed", True):
            main += f"\n\n> **注意**：{suggestion}"

        return main


# ── 全局 pending task 暂存区 ──────────────────────────────────────────────────
# token → task_meta dict，等待前端用户点击"确认"后执行
_pending_tasks: Dict[str, Dict] = {}


def get_pending_task(token: str) -> Dict | None:
    return _pending_tasks.get(token)


def consume_pending_task(token: str) -> Dict | None:
    """取出并删除（一次性消费，防止重复触发）。"""
    return _pending_tasks.pop(token, None)


def _build_confirm_message(task_meta: Dict) -> str:
    task_type = task_meta.get("task_type", "once")
    task_desc = task_meta.get("task_desc", "执行后台任务")
    cron_expr = task_meta.get("cron_expr", "")

    if task_type == "periodic":
        cron_hint = f"（执行周期：`{cron_expr}`）" if cron_expr else ""
        return (
            f"我将为您设置一个**定时任务**{cron_hint}：\n\n"
            f"> {task_desc}\n\n"
            f"任务将在后台定期自动执行，您可随时在任务面板中查看进度或取消。\n\n"
            f"**请确认是否执行？**"
        )
    else:
        return (
            f"我将为您在后台执行以下任务：\n\n"
            f"> {task_desc}\n\n"
            f"任务执行完成后会通知您，期间您可以继续对话。\n\n"
            f"**请确认是否执行？**"
        )


# 全局单例（无状态，可共享）
orchestrator = AgentOrchestrator()
