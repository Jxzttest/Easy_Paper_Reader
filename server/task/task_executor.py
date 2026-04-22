#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
task_executor.py —— 后台任务执行器

职责：
  接收来自 /tasks/confirm/{token} 的确认请求，
  根据 task_meta 决定：
    - task_type == "once"     → 向 TaskManager 提交一次性后台任务
    - task_type == "periodic" → 向 SchedulerService 注册定时任务

所有任务都通过 LLM Agent 执行，将 task_desc 作为指令下发给 AgentOrchestrator。
执行结果异步写回到 SQLite，前端可轮询 /tasks/{task_id} 查看状态。
"""

import asyncio
from typing import Dict, List

from server.agent.base import AgentContext
from server.task.task_manager import Task, task_manager
from server.task.scheduler import scheduler
from server.utils.logger import logger


async def submit_once_task(task_meta: Dict) -> str:
    """
    提交一次性后台任务。
    返回 task_id，前端可用于轮询状态。
    """
    task_desc: str = task_meta.get("task_desc", "后台任务")
    session_id: str = task_meta.get("session_id", "")
    paper_uuids: List[str] = task_meta.get("paper_uuids", [])

    task = Task(task_type="agent_once", session_id=session_id)

    async def _execute_agent():
        from server.agent.orchestrator import orchestrator
        ctx = AgentContext(
            session_id=session_id,
            paper_uuids=paper_uuids,
        )
        result_parts = []
        async for event_str in orchestrator.run(ctx, task_desc):
            import json
            try:
                ev = json.loads(event_str)
                if ev.get("event") == "answer":
                    result_parts.append(ev["data"].get("content", ""))
            except Exception:
                pass
        return "\n".join(result_parts) or "任务完成（无输出）"

    task.add_step("execute", _execute_agent)
    task_id = await task_manager.submit(task)
    logger.info(f"[TaskExecutor] submitted once task {task_id}: {task_desc[:60]}")
    return task_id


async def submit_periodic_task(task_meta: Dict) -> str:
    """
    注册定时任务到 SchedulerService。
    返回 job_id，前端可用于查看或取消。
    """
    task_desc: str = task_meta.get("task_desc", "定时任务")
    cron_expr: str = task_meta.get("cron_expr", "0 9 * * 0")  # 默认每周日9点
    paper_uuids: List[str] = task_meta.get("paper_uuids", [])
    session_id: str = task_meta.get("session_id", "")

    # 定时任务以 paper_uuids[0] 作为关联 paper，无论文时用空字符串
    paper_uuid = paper_uuids[0] if paper_uuids else ""

    job_id = await scheduler.create_job(
        paper_uuid=paper_uuid,
        cron_expr=cron_expr,
        job_type="agent_periodic",
        job_desc=task_desc,
        session_id=session_id,
        paper_uuids=paper_uuids,
    )
    logger.info(f"[TaskExecutor] scheduled periodic job {job_id}: {task_desc[:60]} @ {cron_expr}")
    return job_id
