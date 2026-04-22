#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
TaskManager —— 并发任务调度 + 状态追踪 + 断点恢复

设计思路：
  - 每个"长任务"（论文解析、Agent 对话流）都注册为一个 Task。
  - Task 内部有多个 Step，每步记录 status / result / error。
  - 任务失败后可从最后一个成功 Step 继续，不必从头重跑。
  - 并发靠 asyncio，不依赖外部队列（Celery/Redis）。
  - 状态持久化到 SQLite，重启后仍可查询历史任务。
"""

import asyncio
import uuid
import datetime
from typing import Any, Callable, Coroutine, Dict, List, Optional

from server.db.db_factory import DBFactory
from server.utils.logger import logger

# ── 常量 ────────────────────────────────────────────────────────────────
MAX_CONCURRENT = 10   # 全局最大并发任务数


# ── 数据模型 ─────────────────────────────────────────────────────────────
class StepStatus:
    PENDING  = "pending"
    RUNNING  = "running"
    SUCCESS  = "success"
    FAILED   = "failed"
    SKIPPED  = "skipped"


class TaskStatus:
    PENDING  = "pending"
    RUNNING  = "running"
    SUCCESS  = "success"
    FAILED   = "failed"
    CANCELLED = "cancelled"


class Step:
    """描述任务内一个可执行步骤。"""

    def __init__(
        self,
        name: str,
        fn: Callable[..., Coroutine],
        *,
        depends_on: Optional[str] = None,   # 依赖哪个 step 的 result
    ):
        self.name = name
        self.fn = fn
        self.depends_on = depends_on

        # 运行时状态
        self.status: str = StepStatus.PENDING
        self.result: Any = None
        self.error: Optional[str] = None
        self.started_at: Optional[str] = None
        self.finished_at: Optional[str] = None

    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "status": self.status,
            "result": self.result if _is_serializable(self.result) else str(self.result),
            "error": self.error,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }


class Task:
    """
    一次完整的任务执行单元，包含若干有序 Step。

    用法：
        task = Task("parse_pdf", user_uuid="xxx")
        task.add_step("extract_meta", fn=extract_meta_fn)
        task.add_step("embed_chunks", fn=embed_fn, depends_on="extract_meta")
        await task_manager.submit(task)
    """

    def __init__(self, task_type: str, session_id: str = ""):
        self.task_id = "task_" + uuid.uuid4().hex
        self.task_type = task_type
        self.session_id = session_id
        self.status: str = TaskStatus.PENDING
        self.steps: List[Step] = []
        self.error: Optional[str] = None
        self.created_at = datetime.datetime.utcnow().isoformat()
        self._cancel_event = asyncio.Event()

    def add_step(
        self,
        name: str,
        fn: Callable[..., Coroutine],
        depends_on: Optional[str] = None,
    ) -> "Task":
        self.steps.append(Step(name, fn, depends_on=depends_on))
        return self  # 链式调用

    def cancel(self):
        self._cancel_event.set()

    def to_dict(self) -> Dict:
        return {
            "task_id": self.task_id,
            "task_type": self.task_type,
            "session_id": self.session_id,
            "status": self.status,
            "steps": [s.to_dict() for s in self.steps],
            "error": self.error,
            "created_at": self.created_at,
        }


# ── TaskManager ───────────────────────────────────────────────────────────
class TaskManager:
    """
    全局任务管理器（应用级单例）。

    生命周期：在 FastAPI lifespan 中初始化，关闭时优雅等待。
    """

    _instance: Optional["TaskManager"] = None

    def __new__(cls) -> "TaskManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def initialize(self):
        if self._initialized:
            return
        self._semaphore = asyncio.Semaphore(MAX_CONCURRENT)
        self._running: Dict[str, Task] = {}   # task_id → Task（内存中的运行时对象）
        self._initialized = True
        logger.info("[TaskManager] initialized")

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    async def submit(self, task: Task) -> str:
        """提交任务，立即返回 task_id，在后台异步执行。"""
        sqlite = DBFactory.get_sqlite()
        await sqlite.create_task(
            task_id=task.task_id,
            task_type=task.task_type,
            session_id=task.session_id,
        )
        self._running[task.task_id] = task
        asyncio.create_task(self._run(task))
        logger.info(f"[TaskManager] submitted {task.task_id} ({task.task_type})")
        return task.task_id

    async def get_task(self, task_id: str) -> Optional[Dict]:
        """优先从内存取（运行中），否则从 SQLite 取历史。"""
        if task_id in self._running:
            return self._running[task_id].to_dict()
        sqlite = DBFactory.get_sqlite()
        return await sqlite.get_task(task_id)

    async def get_all_tasks(self, limit: int = 20) -> List[Dict]:
        sqlite = DBFactory.get_sqlite()
        db_tasks = await sqlite.get_all_tasks(limit)
        running = [t.to_dict() for t in self._running.values()]
        running_ids = {t["task_id"] for t in running}
        merged = running + [t for t in db_tasks if t["task_id"] not in running_ids]
        return merged[:limit]

    async def cancel_task(self, task_id: str) -> bool:
        task = self._running.get(task_id)
        if not task:
            return False
        task.cancel()
        return True

    async def retry_task(self, task_id: str) -> Optional[str]:
        """
        从失败点重试：找到最后一个成功 Step，跳过已成功的，重新执行后续步骤。
        返回新任务 id（复用同一 Task 对象重新提交）。
        """
        task = self._running.get(task_id)
        if not task:
            # 历史任务无法重试（Step 的 fn 没法从 DB 恢复）
            return None
        if task.status not in (TaskStatus.FAILED, TaskStatus.CANCELLED):
            return None

        # 重置失败和 pending 的 Step
        for step in task.steps:
            if step.status in (StepStatus.FAILED, StepStatus.PENDING):
                step.status = StepStatus.PENDING
                step.error = None
                step.result = None

        task.status = TaskStatus.PENDING
        task.error = None
        task._cancel_event.clear()

        # 生成新 task_id 避免混淆
        task.task_id = "task_" + uuid.uuid4().hex
        self._running[task.task_id] = task
        await self.submit.__wrapped__(self, task)   # 绕过 submit 里的重复 create_task
        return task.task_id

    async def shutdown(self):
        """应用关闭时等待所有任务完成（最多等 30 秒）。"""
        if not self._running:
            return
        logger.info(f"[TaskManager] waiting for {len(self._running)} tasks...")
        try:
            await asyncio.wait_for(
                asyncio.gather(*[
                    self._wait_done(t) for t in self._running.values()
                ]),
                timeout=30,
            )
        except asyncio.TimeoutError:
            logger.warning("[TaskManager] shutdown timeout, some tasks may be incomplete")

    # ------------------------------------------------------------------ #
    # Internal execution engine
    # ------------------------------------------------------------------ #
    async def _run(self, task: Task):
        async with self._semaphore:
            task.status = TaskStatus.RUNNING
            await self._persist(task)

            # 构建 step 名称 → result 的映射，供 depends_on 使用
            step_results: Dict[str, Any] = {}

            for step in task.steps:
                # 已成功的步骤跳过（断点续跑）
                if step.status == StepStatus.SUCCESS:
                    if step.result is not None:
                        step_results[step.name] = step.result
                    continue

                # 取消检查
                if task._cancel_event.is_set():
                    step.status = StepStatus.SKIPPED
                    continue

                step.status = StepStatus.RUNNING
                step.started_at = datetime.datetime.utcnow().isoformat()
                await self._persist(task)

                try:
                    # 如果该步骤依赖上一步的结果，把它作为参数传入
                    dep_result = step_results.get(step.depends_on) if step.depends_on else None
                    if dep_result is not None:
                        result = await step.fn(dep_result)
                    else:
                        result = await step.fn()

                    step.status = StepStatus.SUCCESS
                    step.result = result
                    step.finished_at = datetime.datetime.utcnow().isoformat()
                    step_results[step.name] = result
                    logger.info(f"[TaskManager] {task.task_id} step '{step.name}' OK")

                except Exception as e:
                    step.status = StepStatus.FAILED
                    step.error = str(e)
                    step.finished_at = datetime.datetime.utcnow().isoformat()
                    task.status = TaskStatus.FAILED
                    task.error = f"Step '{step.name}' failed: {e}"
                    logger.error(
                        f"[TaskManager] {task.task_id} step '{step.name}' FAILED: {e}",
                        exc_info=True,
                    )
                    await self._persist(task)
                    self._running.pop(task.task_id, None)
                    return

                await self._persist(task)

            if task.status != TaskStatus.FAILED:
                task.status = (
                    TaskStatus.CANCELLED if task._cancel_event.is_set()
                    else TaskStatus.SUCCESS
                )
            await self._persist(task)
            self._running.pop(task.task_id, None)
            logger.info(f"[TaskManager] {task.task_id} finished → {task.status}")

    async def _persist(self, task: Task):
        """将任务状态同步到 SQLite。"""
        sqlite = DBFactory.get_sqlite()
        await sqlite.update_task_status(
            task_id=task.task_id,
            status=task.status,
            steps=[s.to_dict() for s in task.steps],
            error=task.error,
        )

    @staticmethod
    async def _wait_done(task: Task):
        while task.status in (TaskStatus.PENDING, TaskStatus.RUNNING):
            await asyncio.sleep(0.5)


# ── 辅助 ──────────────────────────────────────────────────────────────────
def _is_serializable(val: Any) -> bool:
    import json
    try:
        json.dumps(val)
        return True
    except (TypeError, ValueError):
        return False


# ── 全局单例 ──────────────────────────────────────────────────────────────
task_manager = TaskManager()
