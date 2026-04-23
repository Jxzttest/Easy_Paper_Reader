#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
SchedulerService —— 轻量定时任务执行器

设计原则：
  - 纯 asyncio，零外部依赖（不用 APScheduler/Celery）
  - 任务配置持久化到 SQLite，服务重启后自动恢复
  - 支持两种 job_type：
      citation_check  : 原有引用检查任务
      agent_periodic  : 由用户通过对话下达的、LLM Agent 执行的周期任务
  - 支持 cron 表达式（精确到分钟）解析

Job 生命周期：
  create_job(paper_uuid, cron_expr, job_type, ...) → 持久化 + 注册到内存
  cancel_job(job_id)                               → 标记 inactive + 停止循环
  服务重启                                          → 从 SQLite 加载 active jobs，恢复调度

cron 表达式格式（5字段）：分 时 日 月 周
  "0 9 * * *"   每天 09:00
  "0 9 * * 0"   每周日 09:00
  "0 */6 * * *" 每 6 小时
"""

import asyncio
import datetime
import uuid
from typing import Callable, Coroutine, Dict, List, Optional

from server.utils.logger import logger


class ScheduledJob:
    """单个定时任务的运行时状态。"""

    def __init__(
        self,
        job_id: str,
        paper_uuid: str,
        cron_expr: str,
        job_type: str,
        fn: Callable[[], Coroutine],
        job_desc: str = "",
    ):
        self.job_id = job_id
        self.paper_uuid = paper_uuid
        self.cron_expr = cron_expr
        self.job_type = job_type
        self.job_desc = job_desc
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
        logger.info(f"[Scheduler] job {self.job_id} started (cron={self.cron_expr}, desc={self.job_desc[:40]})")
        while not self._stop_event.is_set():
            now = datetime.datetime.now()
            delay = _seconds_until_next(self.cron_expr, now)
            if delay < 0:
                delay = 3600

            logger.info(f"[Scheduler] job {self.job_id} next run in {delay:.0f}s")
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=delay)
                break
            except asyncio.TimeoutError:
                pass

            if self._stop_event.is_set():
                break

            logger.info(f"[Scheduler] job {self.job_id} firing ({self.job_type})")
            try:
                await self.fn()
            except Exception as e:
                logger.error(f"[Scheduler] job {self.job_id} execution error: {e}", exc_info=True)

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
                cron_expr=row["cron_expr"],
                job_type=row["job_type"],
                job_desc=row.get("job_desc", ""),
                paper_uuids=row.get("paper_uuids_json", []),
                session_id=row.get("session_id", ""),
            )
        logger.info(f"[SchedulerService] restored {len(active_jobs)} jobs from DB")

    # ── 公开 API ─────────────────────────────────────────────────────────
    async def create_job(
        self,
        paper_uuid: str,
        cron_expr: str,
        job_type: str = "citation_check",
        job_desc: str = "",
        session_id: str = "",
        paper_uuids: List[str] = None,
        skill_name: str = None,
    ) -> str:
        """新建定时任务，持久化到 DB 并立即开始调度。"""
        if not _validate_cron(cron_expr):
            raise ValueError(f"无效的 cron 表达式: {cron_expr}")

        job_id = "job_" + uuid.uuid4().hex
        next_run = _next_run_str(cron_expr)
        _paper_uuids = paper_uuids or ([paper_uuid] if paper_uuid else [])

        from server.db.db_factory import DBFactory
        sqlite = DBFactory.get_sqlite()
        await sqlite.create_scheduled_job(
            job_id=job_id,
            paper_uuid=paper_uuid,
            cron_expr=cron_expr,
            job_type=job_type,
            next_run_at=next_run,
        )

        self._register_job(
            job_id, paper_uuid, cron_expr, job_type,
            job_desc=job_desc,
            session_id=session_id,
            paper_uuids=_paper_uuids,
            skill_name=skill_name,
        )
        logger.info(f"[SchedulerService] created job {job_id} ({job_type}) @ {cron_expr}")
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

    def list_jobs(self) -> List[Dict]:
        return [
            {
                "job_id": j.job_id,
                "paper_uuid": j.paper_uuid,
                "cron_expr": j.cron_expr,
                "job_type": j.job_type,
                "job_desc": j.job_desc,
            }
            for j in self._jobs.values()
        ]

    def get_job_ids_for_paper(self, paper_uuid: str) -> List[str]:
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
        cron_expr: str,
        job_type: str,
        job_desc: str = "",
        session_id: str = "",
        paper_uuids: List[str] = None,
        skill_name: str = None,
    ):
        fn = _make_job_fn(
            paper_uuid=paper_uuid,
            job_type=job_type,
            job_desc=job_desc,
            session_id=session_id,
            paper_uuids=paper_uuids or [],
            skill_name=skill_name,
        )
        job = ScheduledJob(job_id, paper_uuid, cron_expr, job_type, fn, job_desc=job_desc)
        self._jobs[job_id] = job
        job.start()

    @staticmethod
    async def _run_job_once(job: ScheduledJob):
        try:
            await job.fn()
            await _update_run_record(job.job_id, job.cron_expr)
        except Exception as e:
            logger.error(f"[SchedulerService] run_now failed for {job.job_id}: {e}", exc_info=True)


# ── 工厂函数：根据 job_type 生成对应执行协程 ─────────────────────────────
def _make_job_fn(
    paper_uuid: str,
    job_type: str,
    job_desc: str = "",
    session_id: str = "",
    paper_uuids: List[str] = None,
    skill_name: str = None,
) -> Callable:
    _paper_uuids = paper_uuids or ([paper_uuid] if paper_uuid else [])

    async def _fn():
        if job_type == "citation_check":
            from server.agent.citation_agent import CitationAgent
            agent = CitationAgent()
            result = await agent.run_for_paper(paper_uuid)
            logger.info(
                f"[SchedulerService] citation_check done for {paper_uuid}: "
                f"found={len(result['found'])}, downloaded={result['downloaded']}"
            )

        elif job_type.startswith("skill:") or job_type == "agent_periodic":
            # 通过 skill executor 或 Orchestrator 执行
            from server.task.task_executor import _make_skill_fn, _make_agent_fn
            if skill_name:
                fn = _make_skill_fn(skill_name, job_desc, _paper_uuids)
            else:
                fn = _make_agent_fn(job_desc, session_id or "scheduler", _paper_uuids)
            result = await fn()
            logger.info(
                f"[SchedulerService] {job_type} done: "
                f"{str(result)[:200]}"
            )
        else:
            logger.warning(f"[SchedulerService] unknown job_type: {job_type}")

    return _fn


async def _update_run_record(job_id: str, cron_expr: str):
    from server.db.db_factory import DBFactory
    sqlite = DBFactory.get_sqlite()
    await sqlite.update_job_run(job_id, _next_run_str(cron_expr))


# ── cron 解析工具（精确到分钟）──────────────────────────────────────────
def _validate_cron(expr: str) -> bool:
    parts = expr.strip().split()
    return len(parts) == 5


def _seconds_until_next(cron_expr: str, now: datetime.datetime) -> float:
    """计算距下次触发的秒数。优先使用 croniter，否则降级到内置实现。"""
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
    croniter 未安装时的降级实现，支持：
      "0 H * * *"   每天 H 时整
      "0 H * * W"   每周 W(0=Sun) 的 H 时整
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

    if hour_s.startswith("*/"):
        n = int(hour_s[2:])
        candidate = now.replace(minute=minute, second=0, microsecond=0)
        while True:
            candidate += datetime.timedelta(hours=n)
            if candidate > now:
                return (candidate - now).total_seconds()

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
