#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
SchedulerService —— 轻量定时任务执行器

设计原则：
  - 纯 asyncio，零外部依赖（不用 APScheduler/Celery）
  - 任务配置持久化到 SQLite，服务重启后自动恢复
  - 每篇论文独立一个 Job，互不干扰
  - 支持 cron 表达式（精确到分钟）解析

Job 生命周期：
  create_job(paper_uuid, cron_expr) → 持久化 + 注册到内存
  cancel_job(job_id)                → 标记 inactive + 停止循环
  服务重启                           → 从 SQLite 加载 active jobs，恢复调度

cron 表达式格式（5字段）：分 时 日 月 周
  "0 9 * * *"   每天 09:00
  "0 9 * * 1"   每周一 09:00
  "0 */6 * * *" 每 6 小时
"""

import asyncio
import datetime
import uuid
from typing import Callable, Coroutine, Dict, Optional

from server.utils.logger import logger

# 避免循环导入，DBFactory 在方法内部懒加载


class ScheduledJob:
    """单个定时任务的运行时状态。"""

    def __init__(
        self,
        job_id: str,
        paper_uuid: str,
        user_uuid: str,
        cron_expr: str,
        job_type: str,
        fn: Callable[[], Coroutine],
    ):
        self.job_id = job_id
        self.paper_uuid = paper_uuid
        self.user_uuid = user_uuid
        self.cron_expr = cron_expr
        self.job_type = job_type
        self.fn = fn
        self._task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()

    def start(self):
        self._task = asyncio.create_task(self._loop(), name=f"job_{self.job_id}")

    def stop(self):
        self._stop_event.set()
        if self._task and not self._task.done():
            self._task.cancel()

    async def _loop(self):
        logger.info(f"[Scheduler] job {self.job_id} started (cron={self.cron_expr})")
        while not self._stop_event.is_set():
            now = datetime.datetime.now()
            delay = _seconds_until_next(self.cron_expr, now)
            if delay < 0:
                # cron 解析失败，每小时重试
                delay = 3600

            logger.info(f"[Scheduler] job {self.job_id} next run in {delay:.0f}s")
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=delay,
                )
                # stop_event 被设置
                break
            except asyncio.TimeoutError:
                pass  # 正常超时，开始执行

            if self._stop_event.is_set():
                break

            logger.info(f"[Scheduler] job {self.job_id} firing ({self.job_type})")
            try:
                await self.fn()
            except Exception as e:
                logger.error(f"[Scheduler] job {self.job_id} execution error: {e}", exc_info=True)

            # 更新 DB 记录
            await _update_run_record(self.job_id, self.cron_expr)

        logger.info(f"[Scheduler] job {self.job_id} stopped")


# ── SchedulerService ──────────────────────────────────────────────────────
class SchedulerService:
    """
    全局定时任务管理器（应用级单例）。
    在 FastAPI lifespan 中初始化，关闭时停止所有 Job。
    """

    _instance: Optional["SchedulerService"] = None

    def __new__(cls) -> "SchedulerService":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def initialize(self):
        if self._initialized:
            return
        self._jobs: Dict[str, ScheduledJob] = {}
        self._initialized = True
        logger.info("[SchedulerService] initialized")

    async def restore_from_db(self):
        """服务启动时从 SQLite 恢复所有激活的定时任务。"""
        from server.db.db_factory import DBFactory
        sqlite = DBFactory.get_sqlite()
        active_jobs = await sqlite.get_active_jobs()
        for row in active_jobs:
            self._register_job(
                job_id=row["job_id"],
                paper_uuid=row["paper_uuid"],
                user_uuid=row["user_uuid"],
                cron_expr=row["cron_expr"],
                job_type=row["job_type"],
            )
        logger.info(f"[SchedulerService] restored {len(active_jobs)} jobs from DB")

    # ── 公开 API ─────────────────────────────────────────────────────────
    async def create_job(
        self,
        user_uuid: str,
        paper_uuid: str,
        cron_expr: str,
        job_type: str = "citation_check",
    ) -> str:
        """新建定时任务，持久化到 DB 并立即开始调度。"""
        if not _validate_cron(cron_expr):
            raise ValueError(f"无效的 cron 表达式: {cron_expr}")

        job_id = "job_" + uuid.uuid4().hex
        next_run = _next_run_str(cron_expr)

        from server.db.db_factory import DBFactory
        sqlite = DBFactory.get_sqlite()
        await sqlite.create_scheduled_job(
            job_id=job_id,
            user_uuid=user_uuid,
            paper_uuid=paper_uuid,
            cron_expr=cron_expr,
            job_type=job_type,
            next_run_at=next_run,
        )

        self._register_job(job_id, paper_uuid, user_uuid, cron_expr, job_type)
        logger.info(f"[SchedulerService] created job {job_id} for paper {paper_uuid}")
        return job_id

    async def cancel_job(self, job_id: str) -> bool:
        """取消定时任务（停止调度 + DB 标记 inactive）。"""
        job = self._jobs.pop(job_id, None)
        if job:
            job.stop()

        from server.db.db_factory import DBFactory
        sqlite = DBFactory.get_sqlite()
        await sqlite.deactivate_job(job_id)
        logger.info(f"[SchedulerService] cancelled job {job_id}")
        return job is not None

    async def run_now(self, job_id: str) -> bool:
        """立即触发一次（不影响定时计划）。"""
        job = self._jobs.get(job_id)
        if not job:
            return False
        asyncio.create_task(self._run_job_once(job))
        return True

    def get_job_ids_for_paper(self, paper_uuid: str):
        return [jid for jid, j in self._jobs.items() if j.paper_uuid == paper_uuid]

    async def shutdown(self):
        for job in self._jobs.values():
            job.stop()
        self._jobs.clear()
        logger.info("[SchedulerService] all jobs stopped")

    # ── 内部 ─────────────────────────────────────────────────────────────
    def _register_job(
        self,
        job_id: str,
        paper_uuid: str,
        user_uuid: str,
        cron_expr: str,
        job_type: str,
    ):
        fn = _make_job_fn(paper_uuid, user_uuid, job_type)
        job = ScheduledJob(job_id, paper_uuid, user_uuid, cron_expr, job_type, fn)
        self._jobs[job_id] = job
        job.start()

    @staticmethod
    async def _run_job_once(job: ScheduledJob):
        try:
            await job.fn()
            await _update_run_record(job.job_id, job.cron_expr)
        except Exception as e:
            logger.error(f"[SchedulerService] run_now failed for {job.job_id}: {e}", exc_info=True)


# ── 工厂函数：生成 Job 执行的协程 ─────────────────────────────────────────
def _make_job_fn(paper_uuid: str, user_uuid: str, job_type: str) -> Callable:
    async def _fn():
        if job_type == "citation_check":
            from server.agent.citation_agent import CitationAgent
            agent = CitationAgent()
            result = await agent.run_for_paper(paper_uuid)
            logger.info(
                f"[SchedulerService] citation_check done for {paper_uuid}: "
                f"found={len(result['found'])}, downloaded={result['downloaded']}"
            )
        else:
            logger.warning(f"[SchedulerService] unknown job_type: {job_type}")
    return _fn


async def _update_run_record(job_id: str, cron_expr: str):
    from server.db.db_factory import DBFactory
    sqlite = DBFactory.get_sqlite()
    await sqlite.update_job_run(job_id, _next_run_str(cron_expr))


# ── cron 解析工具（最小实现，精确到分钟）────────────────────────────────
def _validate_cron(expr: str) -> bool:
    parts = expr.strip().split()
    return len(parts) == 5


def _seconds_until_next(cron_expr: str, now: datetime.datetime) -> float:
    """计算距下次触发的秒数。使用 croniter（如已安装）或内置简单实现。"""
    try:
        from croniter import croniter
        it = croniter(cron_expr, now)
        nxt = it.get_next(datetime.datetime)
        return (nxt - now).total_seconds()
    except ImportError:
        return _simple_cron_seconds(cron_expr, now)


def _next_run_str(cron_expr: str) -> str:
    now = datetime.datetime.now()
    secs = _seconds_until_next(cron_expr, now)
    if secs < 0:
        return ""
    nxt = now + datetime.timedelta(seconds=secs)
    return nxt.isoformat()


def _simple_cron_seconds(cron_expr: str, now: datetime.datetime) -> float:
    """
    croniter 未安装时的降级实现，只支持：
      "0 H * * *"  每天 H 时整
      "0 H * * W"  每周 W(0=Mon) 的 H 时整
      "0 */N * * *" 每 N 小时
    """
    parts = cron_expr.strip().split()
    if len(parts) != 5:
        return 3600.0

    minute_s, hour_s = parts[0], parts[1]

    try:
        minute = int(minute_s)
    except ValueError:
        minute = 0

    # 每 N 小时
    if hour_s.startswith("*/"):
        n = int(hour_s[2:])
        candidate = now.replace(minute=minute, second=0, microsecond=0)
        while True:
            candidate += datetime.timedelta(hours=n)
            if candidate > now:
                return (candidate - now).total_seconds()

    # 固定小时
    try:
        hour = int(hour_s)
    except ValueError:
        return 3600.0

    candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= now:
        candidate += datetime.timedelta(days=1)
    return (candidate - now).total_seconds()


# ── 全局单例 ──────────────────────────────────────────────────────────────
scheduler = SchedulerService()
