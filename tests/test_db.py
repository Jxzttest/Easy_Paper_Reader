#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_db.py — 数据库层联调测试

测试内容：
  1. SQLiteStore  : 论文元数据 CRUD、会话/消息、任务状态、定时任务
  2. ChromaVectorStore : 写入 chunk → 向量检索 → 删除

运行方式（在项目根目录）：
  python tests/test_db.py
"""

import sys
import os
import asyncio
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server.db.sqlite_function.sqlite_store import SQLiteStore
from server.db.chroma_function.chroma_store import ChromaVectorStore

# 使用临时路径，避免污染真实数据
_TMP_DB   = "./data/test_paper_reader.db"
_TMP_CHROMA = "./data/test_chroma_db"

PASS = "✅ PASS"
FAIL = "❌ FAIL"


def p(label: str, ok: bool):
    print(f"  {PASS if ok else FAIL}  {label}")


async def test_sqlite():
    print("\n=== SQLiteStore ===")
    store = SQLiteStore(db_path=_TMP_DB)
    await store.initialize()

    uid = "user_" + uuid.uuid4().hex[:8]
    pid = "paper_" + uuid.uuid4().hex[:8]
    sid = "sess_" + uuid.uuid4().hex[:8]
    tid = "task_" + uuid.uuid4().hex[:8]
    jid = "job_"  + uuid.uuid4().hex[:8]

    # --- 用户 ---
    await store.create_user(uid, "test_user")
    user = await store.get_user(uid)
    p("create_user / get_user", user is not None and user["username"] == "test_user")

    # --- 论文元数据 ---
    await store.add_paper_metadata(pid, "Test Paper", uid, "/tmp/test.pdf", authors="A, B")
    paper = await store.get_paper_metadata(pid)
    p("add_paper_metadata / get_paper_metadata", paper is not None and paper["title"] == "Test Paper")

    await store.update_paper_fields(pid, abstract="This is an abstract.")
    paper2 = await store.get_paper_metadata(pid)
    p("update_paper_fields", paper2["abstract"] == "This is an abstract.")

    await store.mark_paper_processed(pid)
    paper3 = await store.get_paper_metadata(pid)
    p("mark_paper_processed", paper3["is_processed"] == 1)

    papers = await store.get_all_papers(uploader_uuid=uid)
    p("get_all_papers", len(papers) >= 1)

    # --- 会话 / 消息 ---
    await store.add_session(uid, sid)
    p("add_session / check_session_exist", await store.check_session_exist(sid))

    await store.update_session_title(sid, "My Chat")
    sessions = await store.get_user_sessions(uid)
    p("update_session_title / get_user_sessions", any(s["title"] == "My Chat" for s in sessions))

    msg_id = await store.add_message(uid, sid, "user", "Hello!")
    msgs = await store.get_session_messages(sid)
    p("add_message / get_session_messages", len(msgs) == 1 and msgs[0]["content"] == "Hello!")

    # --- 任务 ---
    await store.create_task(tid, uid, "parse_pdf")
    task = await store.get_task(tid)
    p("create_task / get_task", task is not None and task["status"] == "pending")

    await store.update_task_status(tid, "success", steps=[{"step": "s1", "status": "success"}])
    task2 = await store.get_task(tid)
    p("update_task_status", task2["status"] == "success" and len(task2["steps"]) == 1)

    user_tasks = await store.get_user_tasks(uid)
    p("get_user_tasks", len(user_tasks) >= 1)

    # --- 定时任务 ---
    await store.create_scheduled_job(jid, uid, pid, "0 9 * * *")
    active = await store.get_active_jobs()
    p("create_scheduled_job / get_active_jobs", any(j["job_id"] == jid for j in active))

    await store.update_job_run(jid, "2026-01-02T09:00:00")
    jobs = await store.get_user_jobs(uid)
    p("update_job_run / get_user_jobs", any(j["job_id"] == jid and j["run_count"] == 1 for j in jobs))

    await store.deactivate_job(jid)
    active2 = await store.get_active_jobs()
    p("deactivate_job", all(j["job_id"] != jid for j in active2))

    # --- 清理 ---
    await store.delete_session(uid, sid)
    await store.delete_paper_metadata(pid)
    await store.close()
    if os.path.exists(_TMP_DB):
        os.remove(_TMP_DB)
    print("  (temp db cleaned up)")


async def test_chroma():
    print("\n=== ChromaVectorStore ===")
    store = ChromaVectorStore(persist_dir=_TMP_CHROMA)
    await store.initialize()

    pid = "paper_" + uuid.uuid4().hex[:8]
    fake_vector = [0.1] * 1536   # text-embedding-3-small 维度

    # 写入 3 个 chunk
    for i in range(3):
        await store.add_paper_chunk(
            paper_id=pid,
            chunk_id=f"{pid}_chunk_{i}",
            content=f"This is chunk {i} about attention mechanism in transformer.",
            content_type="text",
            vector=fake_vector,
            page_num=i + 1,
        )
    count = await store.count_chunks_by_paper(pid)
    p("add_paper_chunk / count_chunks_by_paper", count == 3)

    # 向量检索
    results = await store.search_similar(fake_vector, top_k=5, paper_id=pid)
    p("search_similar", len(results) == 3)

    # 混合检索
    results2 = await store.search_hybrid("attention mechanism", fake_vector, top_k=5, paper_id=pid)
    p("search_hybrid", len(results2) > 0)

    # 获取所有 chunk
    chunks = await store.get_paper_chunks(pid)
    p("get_paper_chunks", len(chunks) == 3)

    # 删除
    await store.delete_paper_chunks(pid)
    count2 = await store.count_chunks_by_paper(pid)
    p("delete_paper_chunks", count2 == 0)

    await store.close()
    import shutil
    if os.path.exists(_TMP_CHROMA):
        shutil.rmtree(_TMP_CHROMA)
    print("  (temp chroma cleaned up)")


async def main():
    await test_sqlite()
    await test_chroma()
    print("\n=== DB tests done ===\n")


if __name__ == "__main__":
    asyncio.run(main())
