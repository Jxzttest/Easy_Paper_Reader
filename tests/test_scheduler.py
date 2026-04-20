#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_scheduler.py — SchedulerService & CitationAgent 测试

测试内容：
  1. SchedulerService : 创建/取消/立即执行定时任务
  2. 持久化恢复         : SQLite 写入后 restore_from_db() 能加载
  3. CitationAgent     : 引用解析逻辑（用 mock chunk，不调 S2 API）
  4. 完整 Citation 流程: run_for_paper（需要 OPENAI_API_KEY）

运行方式（在项目根目录，需先配置 .env）：
  python tests/test_scheduler.py
"""

import sys
import os
import asyncio
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

PASS = "✅ PASS"
FAIL = "❌ FAIL"
SKIP = "⏭  SKIP"


def p(label: str, ok: bool):
    print(f"  {PASS if ok else FAIL}  {label}")


def _need_api():
    if not os.environ.get("OPENAI_API_KEY"):
        print(f"  {SKIP}  未设置 OPENAI_API_KEY，跳过此测试")
        return False
    return True


# ── 1. SchedulerService 基础功能 ──────────────────────────────────────────
async def test_scheduler_basic():
    print("\n=== SchedulerService 基础功能 ===")

    from server.db.db_factory import DBFactory
    from server.task.scheduler import SchedulerService

    await DBFactory.init_all()
    sqlite = DBFactory.get_sqlite()

    scheduler = SchedulerService()
    scheduler.initialize()

    uid = "sched_user_" + uuid.uuid4().hex[:6]
    pid = "sched_paper_" + uuid.uuid4().hex[:6]
    job_id = None

    try:
        await sqlite.create_user(uid, "sched_tester")
        await sqlite.add_paper_metadata(pid, "Sched Test Paper", uid, "/tmp/sched.pdf")
        await sqlite.mark_paper_processed(pid)

        # 创建定时任务（每分钟，只用于测试）
        job_id = await scheduler.create_job(
            user_uuid=uid,
            paper_uuid=pid,
            cron_expr="* * * * *",
        )
        p("create_job 返回 job_id", bool(job_id))

        # 检查 SQLite 中已写入
        active = await sqlite.get_active_jobs()
        p("job 已写入 SQLite", any(j["job_id"] == job_id for j in active))

        # 用户的 job 列表（通过 SQLite 验证）
        user_jobs = await sqlite.get_user_jobs(uid)
        p("SQLite get_user_jobs 返回此 job", any(j["job_id"] == job_id for j in user_jobs))

        # 验证 in-memory jobs 中存在
        paper_jobs = scheduler.get_job_ids_for_paper(pid)
        p("内存中包含此 job", job_id in paper_jobs)

        # 立即执行一次（函数会调用 CitationAgent，但 paper 没有 chunks 会直接返回）
        ok_trigger = await scheduler.run_now(job_id)
        p("run_now 触发成功", ok_trigger)
        await asyncio.sleep(0.3)

        # 取消任务
        ok = await scheduler.cancel_job(job_id)
        p("cancel_job 返回 True", ok)

        active2 = await sqlite.get_active_jobs()
        p("取消后不在 active_jobs", all(j["job_id"] != job_id for j in active2))

    except Exception as e:
        print(f"  {FAIL}  SchedulerService 基础测试异常: {e}")
    finally:
        if job_id:
            try:
                await scheduler.cancel_job(job_id)
            except Exception:
                pass
        await scheduler.shutdown()
        await sqlite.delete_paper_metadata(pid)
        await DBFactory.close_all()


# ── 2. 持久化恢复 ─────────────────────────────────────────────────────────
async def test_scheduler_restore():
    print("\n=== SchedulerService 持久化恢复 ===")

    from server.db.db_factory import DBFactory
    from server.task.scheduler import SchedulerService

    await DBFactory.init_all()
    sqlite = DBFactory.get_sqlite()

    uid = "restore_user_" + uuid.uuid4().hex[:6]
    pid = "restore_paper_" + uuid.uuid4().hex[:6]

    try:
        await sqlite.create_user(uid, "restore_tester")
        await sqlite.add_paper_metadata(pid, "Restore Test Paper", uid, "/tmp/restore.pdf")
        await sqlite.mark_paper_processed(pid)

        # 直接写入 SQLite（模拟上次运行留下的 job）
        job_id = "restore_job_" + uuid.uuid4().hex[:6]
        await sqlite.create_scheduled_job(job_id, uid, pid, "0 9 * * *")

        active = await sqlite.get_active_jobs()
        p("模拟 job 已写入 SQLite", any(j["job_id"] == job_id for j in active))

        # 重置 singleton 状态，模拟重启后的 restore
        scheduler = SchedulerService()
        # 清空 in-memory jobs（模拟重启）
        if hasattr(scheduler, '_jobs'):
            for j in scheduler._jobs.values():
                j.stop()
            scheduler._jobs.clear()

        await scheduler.restore_from_db()

        restored = scheduler.get_job_ids_for_paper(pid)
        p("restore_from_db 加载了 job", job_id in restored)

        await scheduler.cancel_job(job_id)

    except Exception as e:
        print(f"  {FAIL}  持久化恢复测试异常: {e}")
    finally:
        await sqlite.delete_paper_metadata(pid)
        await DBFactory.close_all()


# ── 3. CitationAgent 引用解析（mock chunk，不调 S2）─────────────────────
async def test_citation_parse():
    print("\n=== CitationAgent 引用解析（需要 API Key）===")
    if not _need_api():
        return

    from server.db.db_factory import DBFactory
    from server.task.task_manager import task_manager
    await DBFactory.init_all()
    task_manager.initialize()

    from server.agent.citation_agent import CitationAgent

    agent = CitationAgent()

    # 模拟参考文献文本块
    mock_ref_text = """
    References
    [1] Vaswani, A., et al. (2017). Attention is all you need. Advances in neural information processing systems, 30.
    [2] Devlin, J., et al. (2019). BERT: Pre-training of deep bidirectional transformers for language understanding. NAACL.
    [3] Brown, T., et al. (2020). Language models are few-shot learners. NeurIPS, 33, 1877-1901.
    """

    try:
        refs = await agent._parse_references(mock_ref_text)
        p("_parse_references 返回列表", isinstance(refs, list))
        p("解析出 >= 1 条引用", len(refs) >= 1)
        if refs:
            p("引用包含 title 字段", all("title" in r for r in refs))
            print(f"  解析出 {len(refs)} 条引用:")
            for r in refs[:3]:
                print(f"    - {r.get('title', '')[:60]}")
    except Exception as e:
        print(f"  {FAIL}  CitationAgent 解析异常: {e}")
    finally:
        await task_manager.shutdown()
        await DBFactory.close_all()


# ── 4. Semantic Scholar 查询（网络测试，可选）─────────────────────────────
async def test_semantic_scholar():
    print("\n=== Semantic Scholar API 查询（网络测试）===")

    from server.agent.citation_agent import CitationAgent
    agent = CitationAgent()

    try:
        result = await agent._query_semantic_scholar("Attention is all you need Vaswani 2017")
        if result is None:
            print(f"  {SKIP}  未找到结果（网络不通或无匹配）")
        else:
            p("返回论文信息", "title" in result or "paperId" in result)
            print(f"  找到: {result.get('title', 'N/A')[:60]}")
            print(f"  open_access: {result.get('isOpenAccess', False)}")
    except Exception as e:
        print(f"  {SKIP}  S2 API 请求失败（可能无网络）: {e}")


# ── 5. 完整 CitationAgent.run_for_paper（需要 API Key + 真实论文）────────
async def test_citation_full():
    print("\n=== CitationAgent 完整流程（需要 API Key）===")
    if not _need_api():
        return

    from server.db.db_factory import DBFactory
    from server.task.task_manager import task_manager
    await DBFactory.init_all()
    task_manager.initialize()

    uid = "cite_user_" + uuid.uuid4().hex[:6]
    pid = "cite_paper_" + uuid.uuid4().hex[:6]
    sqlite = DBFactory.get_sqlite()
    chroma = DBFactory.get_vector_store()

    try:
        await sqlite.create_user(uid, "cite_tester")
        await sqlite.add_paper_metadata(pid, "Citation Test Paper", uid, "/tmp/cite.pdf")
        await sqlite.mark_paper_processed(pid)

        # 预置一个包含参考文献文本的 chunk
        from server.model.embedding_model.embedding import EmbeddingManager
        emb = EmbeddingManager()
        ref_text = (
            "References\n"
            "[1] Vaswani, A., et al. (2017). Attention is all you need. NeurIPS, 30.\n"
            "[2] LeCun, Y., Bengio, Y., & Hinton, G. (2015). Deep learning. Nature, 521, 436-444.\n"
        )
        vec = await emb.get_embedding(ref_text)
        await chroma.add_paper_chunk(
            paper_id=pid,
            chunk_id=f"{pid}_ref_0",
            content=ref_text,
            content_type="text",
            vector=vec,
            page_num=10,
        )

        from server.agent.citation_agent import CitationAgent
        agent = CitationAgent()

        result = await agent.run_for_paper(paper_uuid=pid)
        p("run_for_paper 返回结果", isinstance(result, dict))
        p("结果包含 found 字段", "found" in result)
        print(f"  found      : {len(result.get('found', []))}")
        print(f"  downloaded : {result.get('downloaded', 0)}")
        print(f"  skipped    : {result.get('skipped', 0)}")

    except Exception as e:
        print(f"  {FAIL}  CitationAgent 完整流程异常: {e}")
    finally:
        await chroma.delete_paper_chunks(pid)
        await sqlite.delete_paper_metadata(pid)
        await task_manager.shutdown()
        await DBFactory.close_all()


async def main():
    await test_scheduler_basic()
    await test_scheduler_restore()
    await test_citation_parse()
    await test_semantic_scholar()
    await test_citation_full()
    print("\n=== Scheduler tests done ===\n")


if __name__ == "__main__":
    asyncio.run(main())
