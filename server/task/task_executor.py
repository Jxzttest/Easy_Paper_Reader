#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
task_executor.py —— 后台任务执行器

职责：
  接收来自 /tasks/confirm/{token} 的确认请求，
  根据 task_meta 决定：
    - task_type == "once"     → 向 TaskManager 提交一次性后台任务
    - task_type == "periodic" → 向 SchedulerService 注册定时任务

执行路由：
  task_meta 中包含 skill_name 时，优先调用对应 skill 的 executor.execute()；
  skill_name 为 None 或 skill 无 python executor 时，降级为 Orchestrator + LLM Agent 执行。
"""

from typing import Dict, List, Optional

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
    skill_name: Optional[str] = task_meta.get("skill_name")

    task = Task(task_type=f"skill:{skill_name}" if skill_name else "agent_once",
                session_id=session_id)

    execute_fn = _make_skill_fn(skill_name, task_desc, paper_uuids) \
        if skill_name else _make_agent_fn(task_desc, session_id, paper_uuids)

    task.add_step("execute", execute_fn)
    task_id = await task_manager.submit(task)
    logger.info(
        f"[TaskExecutor] submitted once task {task_id}: "
        f"skill={skill_name or 'agent'} | {task_desc[:60]}"
    )
    return task_id


async def submit_periodic_task(task_meta: Dict) -> str:
    """
    注册定时任务到 SchedulerService。
    返回 job_id，前端可用于查看或取消。
    """
    task_desc: str = task_meta.get("task_desc", "定时任务")
    cron_expr: str = task_meta.get("cron_expr", "0 9 * * 0")
    paper_uuids: List[str] = task_meta.get("paper_uuids", [])
    session_id: str = task_meta.get("session_id", "")
    skill_name: Optional[str] = task_meta.get("skill_name")

    paper_uuid = paper_uuids[0] if paper_uuids else ""
    job_type = f"skill:{skill_name}" if skill_name else "agent_periodic"

    job_id = await scheduler.create_job(
        paper_uuid=paper_uuid,
        cron_expr=cron_expr,
        job_type=job_type,
        job_desc=task_desc,
        session_id=session_id,
        paper_uuids=paper_uuids,
        skill_name=skill_name,
    )
    logger.info(
        f"[TaskExecutor] scheduled periodic job {job_id}: "
        f"skill={skill_name or 'agent'} @ {cron_expr} | {task_desc[:60]}"
    )
    return job_id


# ── 执行函数工厂 ──────────────────────────────────────────────────────────────

def _make_skill_fn(skill_name: str, task_desc: str, paper_uuids: List[str]):
    """生成调用指定 skill executor 的协程。"""
    async def _fn():
        from server.skills.skill_registry import skill_registry
        skill_registry.initialize()
        skill = skill_registry.get_skill(skill_name)

        if skill is None:
            logger.warning(f"[TaskExecutor] skill '{skill_name}' not found, falling back to agent")
            return await _make_agent_fn(task_desc, "", paper_uuids)()

        if skill.executor_type == "python":
            # 动态导入 skill 目录下的 executor.py
            import importlib.util
            executor_path = skill.skill_dir / "executor.py"
            spec = importlib.util.spec_from_file_location(
                f"skill_{skill_name}", executor_path
            )
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)

            result = await mod.execute(
                task_desc=task_desc,
                paper_uuids=paper_uuids,
            )
            # 统一转为可读字符串存入任务结果
            if hasattr(result, "to_readable"):
                return result.to_readable()
            return str(result)

        else:
            # llm 模式：将 SKILL.md body 注入 prompt，交给 Orchestrator
            enriched_desc = (
                f"请使用以下技能来完成任务：\n\n"
                f"技能说明：\n{skill.raw_content[:2000]}\n\n"
                f"用户任务：{task_desc}"
            )
            return await _make_agent_fn(enriched_desc, "", paper_uuids)()

    return _fn


def _make_agent_fn(task_desc: str, session_id: str, paper_uuids: List[str]):
    """生成通过 Orchestrator + LLM Agent 执行任务的协程（降级路径）。"""
    async def _fn():
        from server.agent.orchestrator import orchestrator
        from server.agent.base import AgentContext
        import json

        ctx = AgentContext(
            session_id=session_id or "task_executor",
            paper_uuids=paper_uuids,
        )
        result_parts = []
        async for event_str in orchestrator.run(ctx, task_desc):
            try:
                ev = json.loads(event_str)
                if ev.get("event") == "answer":
                    result_parts.append(ev["data"].get("content", ""))
            except Exception:
                pass
        return "\n".join(result_parts) or "任务完成（无输出）"

    return _fn
