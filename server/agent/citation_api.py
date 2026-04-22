#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Citation API

POST /citation/run/{paper_uuid}           : 立即执行一次引用检索
POST /citation/schedule                   : 为某篇论文注册定时检索
DELETE /citation/schedule/{job_id}        : 取消定时任务
POST /citation/schedule/{job_id}/run-now  : 立即触发一次（保留定时计划）
GET  /citation/schedule/list              : 查询所有定时任务
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
    "daily":   "0 9 * * *",
    "weekly":  "0 9 * * 1",
    "6h":      "0 */6 * * *",
}


class ScheduleRequest(BaseModel):
    paper_uuid: str
    cron_expr: Optional[str] = None
    preset: Optional[str] = "daily"


@router.post("/run/{paper_uuid}")
async def run_citation_now(paper_uuid: str):
    """立即执行引用检索，通过 TaskManager 异步后台运行。"""
    agent = CitationAgent()

    task = Task("citation_check")

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


@router.post("/schedule")
async def create_schedule(req: ScheduleRequest):
    """为指定论文注册定时引用检索。"""
    cron = req.cron_expr or _PRESET_CRONS.get(req.preset or "daily", "0 9 * * *")

    try:
        job_id = await scheduler.create_job(
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


@router.delete("/schedule/{job_id}")
async def cancel_schedule(job_id: str):
    """取消定时任务。"""
    ok = await scheduler.cancel_job(job_id)
    if not ok:
        sqlite = DBFactory.get_sqlite()
        await sqlite.deactivate_job(job_id)
    return JSONResponse(content={"status": "cancelled", "job_id": job_id})


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


@router.get("/schedule/list")
async def list_schedules():
    """查询所有定时任务。"""
    sqlite = DBFactory.get_sqlite()
    jobs = await sqlite.get_all_jobs()
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
