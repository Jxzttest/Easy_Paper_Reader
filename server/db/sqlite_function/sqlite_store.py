#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import uuid
import datetime
import aiosqlite
import json
import pathlib
from typing import Optional, List, Dict, Any
from server.utils.logger import logger

# 默认数据库文件放在项目根目录的 data/ 下
DEFAULT_DB_PATH = pathlib.Path(__file__).parent.parent.parent.parent / "data" / "paper_reader.db"


class SQLiteStore:
    """
    轻量化本地存储，替代 PostgreSQL + ES chat 索引。
    负责：论文元数据、对话 session、对话消息、任务状态。
    """

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = pathlib.Path(db_path) if db_path else DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[aiosqlite.Connection] = None

    async def initialize(self):
        self._conn = await aiosqlite.connect(str(self.db_path))
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.execute("PRAGMA foreign_keys=ON")
        await self._create_tables()
        await self._conn.commit()
        logger.info(f"[SQLiteStore] initialized at {self.db_path}")

    async def close(self):
        if self._conn:
            await self._conn.close()
            self._conn = None

    # ------------------------------------------------------------------ #
    # DDL
    # ------------------------------------------------------------------ #
    async def _create_tables(self):
        await self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                user_uuid   TEXT PRIMARY KEY,
                username    TEXT NOT NULL,
                created_at  TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS paper_metadata (
                paper_uuid      TEXT PRIMARY KEY,
                title           TEXT NOT NULL,
                authors         TEXT,
                publish_year    INTEGER,
                abstract        TEXT,
                doi             TEXT,
                arxiv_id        TEXT,
                file_path       TEXT,
                is_processed    INTEGER NOT NULL DEFAULT 0,
                parse_mode      TEXT DEFAULT 'pymupdf',
                uploader_uuid   TEXT,
                created_at      TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS conversations (
                session_id  TEXT PRIMARY KEY,
                user_uuid   TEXT NOT NULL,
                title       TEXT DEFAULT '',
                paper_uuid  TEXT,
                created_at  TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS messages (
                message_id          TEXT PRIMARY KEY,
                session_id          TEXT NOT NULL,
                user_uuid           TEXT NOT NULL,
                parent_message_id   TEXT,
                role                TEXT NOT NULL,
                content             TEXT NOT NULL,
                files_info          TEXT DEFAULT '[]',
                timestamp           TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES conversations(session_id)
            );

            CREATE TABLE IF NOT EXISTS tasks (
                task_id         TEXT PRIMARY KEY,
                user_uuid       TEXT NOT NULL,
                session_id      TEXT,
                task_type       TEXT NOT NULL,
                status          TEXT NOT NULL DEFAULT 'pending',
                steps           TEXT DEFAULT '[]',
                error           TEXT,
                resume_from     INTEGER DEFAULT 0,
                created_at      TEXT NOT NULL,
                updated_at      TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS scheduled_jobs (
                job_id          TEXT PRIMARY KEY,
                user_uuid       TEXT NOT NULL,
                paper_uuid      TEXT NOT NULL,
                job_type        TEXT NOT NULL DEFAULT 'citation_check',
                cron_expr       TEXT NOT NULL,          -- cron 表达式，如 '0 9 * * *'
                is_active       INTEGER NOT NULL DEFAULT 1,
                last_run_at     TEXT,
                next_run_at     TEXT,
                run_count       INTEGER NOT NULL DEFAULT 0,
                created_at      TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
            CREATE INDEX IF NOT EXISTS idx_messages_user ON messages(user_uuid);
            CREATE INDEX IF NOT EXISTS idx_tasks_user ON tasks(user_uuid);
            CREATE INDEX IF NOT EXISTS idx_paper_uploader ON paper_metadata(uploader_uuid);
            CREATE INDEX IF NOT EXISTS idx_jobs_user ON scheduled_jobs(user_uuid);
            CREATE INDEX IF NOT EXISTS idx_jobs_active ON scheduled_jobs(is_active);
        """)

    # ------------------------------------------------------------------ #
    # Users
    # ------------------------------------------------------------------ #
    async def create_user(self, user_uuid: str, username: str) -> None:
        now = datetime.datetime.utcnow().isoformat()
        await self._conn.execute(
            "INSERT OR IGNORE INTO users (user_uuid, username, created_at) VALUES (?, ?, ?)",
            (user_uuid, username, now)
        )
        await self._conn.commit()

    async def get_user(self, user_uuid: str) -> Optional[Dict]:
        async with self._conn.execute(
            "SELECT * FROM users WHERE user_uuid = ?", (user_uuid,)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None

    # ------------------------------------------------------------------ #
    # Papers
    # ------------------------------------------------------------------ #
    async def add_paper_metadata(
        self,
        paper_uuid: str,
        title: str,
        uploader_uuid: str,
        file_path: str,
        authors: str = "",
        abstract: str = "",
        doi: str = "",
        arxiv_id: str = "",
        publish_year: Optional[int] = None,
        parse_mode: str = "pymupdf",
    ) -> None:
        now = datetime.datetime.utcnow().isoformat()
        await self._conn.execute(
            """INSERT OR IGNORE INTO paper_metadata
               (paper_uuid, title, authors, publish_year, abstract, doi, arxiv_id,
                file_path, is_processed, parse_mode, uploader_uuid, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?)""",
            (paper_uuid, title, authors, publish_year, abstract, doi, arxiv_id,
             file_path, parse_mode, uploader_uuid, now)
        )
        await self._conn.commit()

    async def mark_paper_processed(self, paper_uuid: str) -> None:
        await self._conn.execute(
            "UPDATE paper_metadata SET is_processed = 1 WHERE paper_uuid = ?",
            (paper_uuid,)
        )
        await self._conn.commit()

    async def get_paper_metadata(self, paper_uuid: str) -> Optional[Dict]:
        async with self._conn.execute(
            "SELECT * FROM paper_metadata WHERE paper_uuid = ?", (paper_uuid,)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None

    async def get_all_papers(self, uploader_uuid: Optional[str] = None) -> List[Dict]:
        if uploader_uuid:
            sql = "SELECT * FROM paper_metadata WHERE uploader_uuid = ? ORDER BY created_at DESC"
            args = (uploader_uuid,)
        else:
            sql = "SELECT * FROM paper_metadata ORDER BY created_at DESC"
            args = ()
        async with self._conn.execute(sql, args) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]

    async def delete_paper_metadata(self, paper_uuid: str) -> None:
        await self._conn.execute(
            "DELETE FROM paper_metadata WHERE paper_uuid = ?", (paper_uuid,)
        )
        await self._conn.commit()

    async def update_paper_fields(self, paper_uuid: str, **fields) -> None:
        allowed = {"title", "authors", "abstract", "doi", "arxiv_id", "publish_year", "parse_mode"}
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            return
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [paper_uuid]
        await self._conn.execute(
            f"UPDATE paper_metadata SET {set_clause} WHERE paper_uuid = ?", values
        )
        await self._conn.commit()

    # ------------------------------------------------------------------ #
    # Conversations
    # ------------------------------------------------------------------ #
    async def add_session(self, user_uuid: str, session_id: str, paper_uuid: str = "") -> None:
        now = datetime.datetime.utcnow().isoformat()
        await self._conn.execute(
            "INSERT OR IGNORE INTO conversations (session_id, user_uuid, paper_uuid, created_at) VALUES (?, ?, ?, ?)",
            (session_id, user_uuid, paper_uuid, now)
        )
        await self._conn.commit()

    async def get_user_sessions(self, user_uuid: str) -> List[Dict]:
        async with self._conn.execute(
            "SELECT * FROM conversations WHERE user_uuid = ? ORDER BY created_at DESC",
            (user_uuid,)
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]

    async def update_session_title(self, session_id: str, title: str) -> None:
        await self._conn.execute(
            "UPDATE conversations SET title = ? WHERE session_id = ?", (title, session_id)
        )
        await self._conn.commit()

    async def delete_session(self, user_uuid: str, session_id: str) -> None:
        await self._conn.execute(
            "DELETE FROM conversations WHERE user_uuid = ? AND session_id = ?",
            (user_uuid, session_id)
        )
        await self._conn.execute(
            "DELETE FROM messages WHERE user_uuid = ? AND session_id = ?",
            (user_uuid, session_id)
        )
        await self._conn.commit()

    async def check_session_exist(self, session_id: str) -> bool:
        async with self._conn.execute(
            "SELECT 1 FROM conversations WHERE session_id = ?", (session_id,)
        ) as cur:
            return await cur.fetchone() is not None

    # ------------------------------------------------------------------ #
    # Messages
    # ------------------------------------------------------------------ #
    async def add_message(
        self,
        user_uuid: str,
        session_id: str,
        role: str,
        content: str,
        parent_message_id: Optional[str] = None,
        files_info: Optional[List] = None,
    ) -> str:
        message_id = "msg_" + uuid.uuid4().hex
        timestamp = datetime.datetime.utcnow().isoformat()
        files_json = json.dumps(files_info or [], ensure_ascii=False)
        await self._conn.execute(
            """INSERT INTO messages
               (message_id, session_id, user_uuid, parent_message_id, role, content, files_info, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (message_id, session_id, user_uuid, parent_message_id, role, content, files_json, timestamp)
        )
        await self._conn.commit()
        return message_id

    async def get_session_messages(self, session_id: str, limit: int = 100) -> List[Dict]:
        async with self._conn.execute(
            "SELECT * FROM messages WHERE session_id = ? ORDER BY timestamp ASC LIMIT ?",
            (session_id, limit)
        ) as cur:
            rows = await cur.fetchall()
            result = []
            for r in rows:
                d = dict(r)
                d["files_info"] = json.loads(d.get("files_info") or "[]")
                result.append(d)
            return result

    async def delete_message(self, user_uuid: str, session_id: str) -> None:
        await self._conn.execute(
            "DELETE FROM messages WHERE user_uuid = ? AND session_id = ?",
            (user_uuid, session_id)
        )
        await self._conn.commit()

    # ------------------------------------------------------------------ #
    # Tasks  （并发任务状态追踪）
    # ------------------------------------------------------------------ #
    async def create_task(
        self,
        task_id: str,
        user_uuid: str,
        task_type: str,
        session_id: str = "",
    ) -> None:
        now = datetime.datetime.utcnow().isoformat()
        await self._conn.execute(
            """INSERT INTO tasks
               (task_id, user_uuid, session_id, task_type, status, steps, created_at, updated_at)
               VALUES (?, ?, ?, ?, 'pending', '[]', ?, ?)""",
            (task_id, user_uuid, session_id, task_type, now, now)
        )
        await self._conn.commit()

    async def update_task_status(
        self,
        task_id: str,
        status: str,
        steps: Optional[List[Dict]] = None,
        error: Optional[str] = None,
        resume_from: Optional[int] = None,
    ) -> None:
        now = datetime.datetime.utcnow().isoformat()
        fields: Dict[str, Any] = {"status": status, "updated_at": now}
        if steps is not None:
            fields["steps"] = json.dumps(steps, ensure_ascii=False)
        if error is not None:
            fields["error"] = error
        if resume_from is not None:
            fields["resume_from"] = resume_from
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [task_id]
        await self._conn.execute(
            f"UPDATE tasks SET {set_clause} WHERE task_id = ?", values
        )
        await self._conn.commit()

    async def get_task(self, task_id: str) -> Optional[Dict]:
        async with self._conn.execute(
            "SELECT * FROM tasks WHERE task_id = ?", (task_id,)
        ) as cur:
            row = await cur.fetchone()
            if not row:
                return None
            d = dict(row)
            d["steps"] = json.loads(d.get("steps") or "[]")
            return d

    async def get_user_tasks(self, user_uuid: str, limit: int = 20) -> List[Dict]:
        async with self._conn.execute(
            "SELECT * FROM tasks WHERE user_uuid = ? ORDER BY created_at DESC LIMIT ?",
            (user_uuid, limit)
        ) as cur:
            rows = await cur.fetchall()
            result = []
            for r in rows:
                d = dict(r)
                d["steps"] = json.loads(d.get("steps") or "[]")
                result.append(d)
            return result

    # ------------------------------------------------------------------ #
    # Scheduled Jobs
    # ------------------------------------------------------------------ #
    async def create_scheduled_job(
        self,
        job_id: str,
        user_uuid: str,
        paper_uuid: str,
        cron_expr: str,
        job_type: str = "citation_check",
        next_run_at: str = "",
    ) -> None:
        now = datetime.datetime.utcnow().isoformat()
        await self._conn.execute(
            """INSERT OR REPLACE INTO scheduled_jobs
               (job_id, user_uuid, paper_uuid, job_type, cron_expr, is_active,
                next_run_at, run_count, created_at)
               VALUES (?, ?, ?, ?, ?, 1, ?, 0, ?)""",
            (job_id, user_uuid, paper_uuid, job_type, cron_expr, next_run_at, now)
        )
        await self._conn.commit()

    async def get_active_jobs(self) -> List[Dict]:
        """获取所有激活的定时任务，用于服务启动时恢复调度。"""
        async with self._conn.execute(
            "SELECT * FROM scheduled_jobs WHERE is_active = 1 ORDER BY created_at ASC"
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]

    async def get_user_jobs(self, user_uuid: str) -> List[Dict]:
        async with self._conn.execute(
            "SELECT * FROM scheduled_jobs WHERE user_uuid = ? ORDER BY created_at DESC",
            (user_uuid,)
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]

    async def get_paper_jobs(self, paper_uuid: str) -> List[Dict]:
        async with self._conn.execute(
            "SELECT * FROM scheduled_jobs WHERE paper_uuid = ? AND is_active = 1",
            (paper_uuid,)
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]

    async def update_job_run(self, job_id: str, next_run_at: str) -> None:
        now = datetime.datetime.utcnow().isoformat()
        await self._conn.execute(
            """UPDATE scheduled_jobs
               SET last_run_at = ?, next_run_at = ?, run_count = run_count + 1
               WHERE job_id = ?""",
            (now, next_run_at, job_id)
        )
        await self._conn.commit()

    async def deactivate_job(self, job_id: str) -> None:
        await self._conn.execute(
            "UPDATE scheduled_jobs SET is_active = 0 WHERE job_id = ?", (job_id,)
        )
        await self._conn.commit()

    async def delete_job(self, job_id: str) -> None:
        await self._conn.execute(
            "DELETE FROM scheduled_jobs WHERE job_id = ?", (job_id,)
        )
        await self._conn.commit()
