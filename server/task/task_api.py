#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from fastapi import APIRouter
from starlette.responses import JSONResponse

from server.task.task_manager import task_manager
from server.utils.logger import logger

router = APIRouter(prefix="/tasks")


@router.get("/list")
async def get_all_tasks(limit: int = 20):
    """获取所有任务列表。"""
    tasks = await task_manager.get_all_tasks(limit=limit)
    return JSONResponse(content={"tasks": tasks})


@router.get("/{task_id}")
async def get_task(task_id: str):
    """查询任务状态及每个 Step 的执行结果。"""
    task = await task_manager.get_task(task_id)
    if not task:
        return JSONResponse(status_code=404, content={"detail": "task not found"})
    return JSONResponse(content=task)


@router.post("/{task_id}/cancel")
async def cancel_task(task_id: str):
    """取消一个正在运行的任务。"""
    ok = await task_manager.cancel_task(task_id)
    if not ok:
        return JSONResponse(
            status_code=404,
            content={"detail": "task not found or already finished"},
        )
    return JSONResponse(content={"status": "cancelling", "task_id": task_id})


@router.post("/{task_id}/retry")
async def retry_task(task_id: str):
    """从上次失败的 Step 继续重试（断点恢复）。"""
    new_id = await task_manager.retry_task(task_id)
    if not new_id:
        return JSONResponse(
            status_code=400,
            content={"detail": "task cannot be retried (not found, not failed, or already completed)"},
        )
    return JSONResponse(content={"status": "retrying", "new_task_id": new_id})


# ── 任务确认接口 ──────────────────────────────────────────────────────────────

@router.post("/confirm/{token}")
async def confirm_task(token: str):
    """
    用户在前端点击"确认"后调用。
    根据 token 从 pending store 取出 task_meta，提交实际任务执行。
    返回 task_id（即时任务）或 job_id（定时任务）。
    """
    from server.agent.orchestrator import consume_pending_task
    from server.task.task_executor import submit_once_task, submit_periodic_task

    task_meta = consume_pending_task(token)
    if not task_meta:
        return JSONResponse(
            status_code=404,
            content={"detail": "confirm token not found or already used"},
        )

    task_type = task_meta.get("task_type", "once")
    try:
        if task_type == "periodic":
            job_id = await submit_periodic_task(task_meta)
            logger.info(f"[task_api] confirmed periodic job {job_id}")
            return JSONResponse(content={
                "status": "scheduled",
                "job_id": job_id,
                "task_desc": task_meta.get("task_desc", ""),
                "cron_expr": task_meta.get("cron_expr", ""),
            })
        else:
            task_id = await submit_once_task(task_meta)
            logger.info(f"[task_api] confirmed once task {task_id}")
            return JSONResponse(content={
                "status": "running",
                "task_id": task_id,
                "task_desc": task_meta.get("task_desc", ""),
            })
    except Exception as e:
        logger.error(f"[task_api] confirm failed: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"detail": str(e)})


@router.delete("/confirm/{token}")
async def reject_task(token: str):
    """
    用户在前端点击"拒绝/取消"后调用。
    丢弃 pending task，不执行任何操作。
    """
    from server.agent.orchestrator import consume_pending_task

    task_meta = consume_pending_task(token)
    if not task_meta:
        return JSONResponse(
            status_code=404,
            content={"detail": "confirm token not found or already used"},
        )
    logger.info(f"[task_api] user rejected task: {task_meta.get('task_desc', '')[:60]}")
    return JSONResponse(content={"status": "rejected"})
