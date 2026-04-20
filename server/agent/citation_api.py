#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Citation API

POST /citation/run/{paper_uuid}           : 立即执行一次引用检索
POST /citation/schedule                   : 为某篇论文注册定时检索
DELETE /citation/schedule/{job_id}        : 取消定时任务
POST /citation/schedule/{job_id}/run-now  : 立即触发一次（保留定时计划）
GET  /citation/schedule/list              : 查询用户的所有定时任务
GET  /citation/schedule/paper/{paper_uuid}: 查询某篇论文的定时任务
"""

from typing import Optional
from pydantic import BaseModel
from fastapi import APIRouter
from starlette.responses import JSONResponse

from server.agent.citation_agent import CitationAgent
from server.task.scheduler import scheduler
from server.task.task_manager import Task, task_manager
from server.db.db_factory import DBFactory
from server.utils.logger import logger

router = APIRouter(prefix="/citation")

_PRESET_CRONS = {
    "daily":   "0 9 * * *",    # 每天 09:00
    "weekly":  "0 9 * * 1",    # 每周一 09:00
    "6h":      "0 */6 * * *",  # 每 6 小时
}


# ── 请求模型 ──────────────────────────────────────────────────────────────
class ScheduleRequest(BaseModel):
    user_uuid: str
    paper_uuid: str
    cron_expr: Optional[str] = None      # 自定义 cron，优先
    preset: Optional[str] = "daily"      # daily / weekly / 6h（cron_expr 为空时用）


# ── 立即执行一次 ──────────────────────────────────────────────────────────
@router.post("/run/{paper_uuid}")
async def run_citation_now(paper_uuid: str, user_uuid: str):
    """
    立即执行引用检索，通过 TaskManager 异步后台运行。
    立即返回 task_id，前端通过 GET /tasks/{task_id} 轮询结果。
    """
    agent = CitationAgent()

    task = Task("citation_check", user_uuid=user_uuid)

    async def do_citation():
        return await agent.run_for_paper(paper_uuid)

    task.add_step("citation_check", do_citation)
    task_id = await task_manager.submit(task)

    logger.info(f"[citation_api] run_now submitted: task={task_id}, paper={paper_uuid}")
    return JSONResponse(status_code=202, content={
        "status": "accepted",
        "task_id": task_id,
        "message": "引用检索已启动，通过 GET /tasks/{task_id} 查看进度。"
    })


# ── 注册定时任务 ──────────────────────────────────────────────────────────
@router.post("/schedule")
async def create_schedule(req: ScheduleRequest):
    """
    为指定论文注册定时引用检索。
    - cron_expr 优先；未填则使用 preset（daily/weekly/6h）
    - 同一篇论文可以有多个不同频率的 Job
    """
    cron = req.cron_expr or _PRESET_CRONS.get(req.preset or "daily", "0 9 * * *")

    try:
        job_id = await scheduler.create_job(
            user_uuid=req.user_uuid,
            paper_uuid=req.paper_uuid,
            cron_expr=cron,
            job_type="citation_check",
        )
    except ValueError as e:
        return JSONResponse(status_code=400, content={"detail": str(e)})

    return JSONResponse(content={
        "job_id": job_id,
        "paper_uuid": req.paper_uuid,
        "cron_expr": cron,
        "message": f"定时任务已创建，cron={cron}",
    })


# ── 取消定时任务 ──────────────────────────────────────────────────────────
@router.delete("/schedule/{job_id}")
async def cancel_schedule(job_id: str):
    """取消定时任务（不影响历史执行结果）。"""
    ok = await scheduler.cancel_job(job_id)
    if not ok:
        # job 不在内存中，但 DB 里可能有 —— 仍做 deactivate
        sqlite = DBFactory.get_sqlite()
        await sqlite.deactivate_job(job_id)
    return JSONResponse(content={"status": "cancelled", "job_id": job_id})


# ── 立即触发一次（保留定时计划）────────────────────────────────────────────
@router.post("/schedule/{job_id}/run-now")
async def trigger_job_now(job_id: str):
    """不修改定时计划，立即多触发一次。"""
    ok = await scheduler.run_now(job_id)
    if not ok:
        return JSONResponse(
            status_code=404,
            content={"detail": "job not found or not running"}
        )
    return JSONResponse(content={"status": "triggered", "job_id": job_id})


# ── 查询定时任务列表 ──────────────────────────────────────────────────────
@router.get("/schedule/list")
async def list_schedules(user_uuid: str):
    """查询用户的所有定时任务（包含已停用的）。"""
    sqlite = DBFactory.get_sqlite()
    jobs = await sqlite.get_user_jobs(user_uuid)
    # 注入内存中的运行状态
    for j in jobs:
        j["is_running"] = j["job_id"] in scheduler._jobs
    return JSONResponse(content={"jobs": jobs})


@router.get("/schedule/paper/{paper_uuid}")
async def list_paper_schedules(paper_uuid: str):
    """查询某篇论文的所有激活定时任务。"""
    sqlite = DBFactory.get_sqlite()
    jobs = await sqlite.get_paper_jobs(paper_uuid)
    for j in jobs:
        j["is_running"] = j["job_id"] in scheduler._jobs
    return JSONResponse(content={"jobs": jobs})
