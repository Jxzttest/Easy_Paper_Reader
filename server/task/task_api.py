#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from fastapi import APIRouter
from starlette.responses import JSONResponse

from server.task.task_manager import task_manager
from server.utils.logger import logger

router = APIRouter(prefix="/tasks")


@router.get("/{task_id}")
async def get_task(task_id: str):
    """查询任务状态及每个 Step 的执行结果。"""
    task = await task_manager.get_task(task_id)
    if not task:
        return JSONResponse(status_code=404, content={"detail": "task not found"})
    return JSONResponse(content=task)


@router.get("/user/{user_uuid}")
async def get_user_tasks(user_uuid: str, limit: int = 20):
    """获取用户的任务列表。"""
    tasks = await task_manager.get_user_tasks(user_uuid, limit=limit)
    return JSONResponse(content={"tasks": tasks})


@router.post("/{task_id}/cancel")
async def cancel_task(task_id: str):
    """取消一个正在运行的任务。"""
    ok = await task_manager.cancel_task(task_id)
    if not ok:
        return JSONResponse(
            status_code=404,
            content={"detail": "task not found or already finished"}
        )
    return JSONResponse(content={"status": "cancelling", "task_id": task_id})


@router.post("/{task_id}/retry")
async def retry_task(task_id: str):
    """
    从上次失败的 Step 继续重试（断点恢复）。
    已成功的 Step 不会重新执行。
    """
    new_id = await task_manager.retry_task(task_id)
    if not new_id:
        return JSONResponse(
            status_code=400,
            content={"detail": "task cannot be retried (not found, not failed, or already completed)"}
        )
    return JSONResponse(content={"status": "retrying", "new_task_id": new_id})
