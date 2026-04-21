#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_chat.py — Chat API & 会话管理测试

测试内容：
  1. 会话 CRUD（创建、列表、重命名、删除）
  2. 消息持久化（发送消息后查询历史）
  3. SSE 流式响应（收集所有 event 并验证格式）
  4. 多轮对话上下文（前一条消息在历史中可见）

运行方式（在项目根目录，需先配置 .env）：
  python tests/test_chat.py

注意：
  - SSE 测试需要 OPENAI_API_KEY
  - 其余会话 CRUD 测试不需要 LLM，但需要已初始化的 DB
"""

import sys
import os
import asyncio
import uuid
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from server.config.config_loader import get_config
load_dotenv()

PASS = "✅ PASS"
FAIL = "❌ FAIL"
SKIP = "⏭  SKIP"


def p(label: str, ok: bool):
    print(f"  {PASS if ok else FAIL}  {label}")


def _need_api():
    config = get_config()
    if not config.get("llm", {}).get("api_key"):
        print(f"  {SKIP}  配置文件中未设置 llm.api_key，跳过此测试")
        return False
    return True


# ── 1. 会话 CRUD ──────────────────────────────────────────────────────────
async def test_session_crud():
    print("\n=== 会话 CRUD ===")

    from server.db.db_factory import DBFactory
    await DBFactory.init_all()
    sqlite = DBFactory.get_sqlite()

    uid = "test_user_" + uuid.uuid4().hex[:6]
    sid = "test_sess_" + uuid.uuid4().hex[:6]

    try:
        # 创建用户
        await sqlite.create_user(uid, "chat_tester")

        # 创建会话
        await sqlite.add_session(uid, sid)
        exists = await sqlite.check_session_exist(sid)
        p("add_session / check_session_exist", exists)

        # 会话列表
        sessions = await sqlite.get_user_sessions(uid)
        p("get_user_sessions 包含新会话", any(s["session_id"] == sid for s in sessions))

        # 重命名会话
        await sqlite.update_session_title(sid, "测试对话标题")
        sessions2 = await sqlite.get_user_sessions(uid)
        p("update_session_title", any(s["title"] == "测试对话标题" for s in sessions2))

        # 写入消息
        await sqlite.add_message(uid, sid, "user", "你好！")
        await sqlite.add_message(uid, sid, "assistant", "你好，有什么可以帮您？")
        msgs = await sqlite.get_session_messages(sid)
        p("add_message 写入 2 条", len(msgs) == 2)
        p("消息顺序正确", msgs[0]["role"] == "user" and msgs[1]["role"] == "assistant")

        # 删除会话（同时删消息）
        await sqlite.delete_session(uid, sid)
        exists2 = await sqlite.check_session_exist(sid)
        p("delete_session", not exists2)

    except Exception as e:
        print(f"  {FAIL}  会话 CRUD 异常: {e}")
    finally:
        await DBFactory.close_all()


# ── 2. 消息历史持久化 ─────────────────────────────────────────────────────
async def test_message_history():
    print("\n=== 消息历史持久化 ===")

    from server.db.db_factory import DBFactory
    await DBFactory.init_all()
    sqlite = DBFactory.get_sqlite()

    uid = "test_user_" + uuid.uuid4().hex[:6]
    sid = "test_sess_" + uuid.uuid4().hex[:6]

    try:
        await sqlite.create_user(uid, "history_tester")
        await sqlite.add_session(uid, sid)

        # 写入多轮对话
        rounds = [
            ("user", "什么是 Transformer？"),
            ("assistant", "Transformer 是一种基于注意力机制的序列模型架构。"),
            ("user", "它的主要组件有哪些？"),
            ("assistant", "主要包括多头自注意力层和前馈网络层。"),
        ]
        for role, content in rounds:
            await sqlite.add_message(uid, sid, role, content)

        msgs = await sqlite.get_session_messages(sid)
        p("写入 4 条消息", len(msgs) == 4)
        p("内容完整", msgs[0]["content"] == "什么是 Transformer？")
        p("角色交替", [m["role"] for m in msgs] == ["user", "assistant", "user", "assistant"])

        # 验证消息时间戳存在
        p("消息包含 created_at", all("created_at" in m for m in msgs))

    except Exception as e:
        print(f"  {FAIL}  消息历史测试异常: {e}")
    finally:
        await sqlite.delete_session(uid, sid)
        await DBFactory.close_all()


# ── 3. AgentOrchestrator SSE 事件流 ──────────────────────────────────────
async def test_sse_stream():
    print("\n=== SSE 事件流（需要 API Key）===")
    if not _need_api():
        return

    from server.db.db_factory import DBFactory
    from server.task.task_manager import task_manager
    await DBFactory.init_all()
    task_manager.initialize()

    from server.agent.base import AgentContext
    from server.agent.orchestrator import orchestrator

    ctx = AgentContext(
        session_id="sse_test_sess",
        user_uuid="sse_test_user",
        paper_uuids=[],
    )

    events = []
    try:
        async for ev_str in orchestrator.run(ctx, "什么是注意力机制？请简短回答。"):
            try:
                ev = json.loads(ev_str)
                events.append(ev)
                print(f"  event: {ev.get('event', '?'):10s} | {str(ev.get('data', ''))[:50]}")
            except json.JSONDecodeError:
                pass
    except Exception as e:
        print(f"  {FAIL}  SSE 流异常: {e}")
        return
    finally:
        await task_manager.shutdown()
        await DBFactory.close_all()

    event_types = {e.get("event") for e in events}
    p("收到至少 1 个 agent 事件", "agent" in event_types)
    p("收到 answer 事件", "answer" in event_types)
    p("收到 done 事件", "done" in event_types)

    # 验证 answer 内容非空
    answer_events = [e for e in events if e.get("event") == "answer"]
    if answer_events:
        answer_data = answer_events[-1].get("data", "")
        p("answer 内容非空", bool(answer_data))
        print(f"  answer: {str(answer_data)[:100]}...")


# ── 4. 多轮对话上下文传递 ─────────────────────────────────────────────────
async def test_multi_turn_context():
    print("\n=== 多轮对话上下文（需要 API Key）===")
    if not _need_api():
        return

    from server.db.db_factory import DBFactory
    from server.task.task_manager import task_manager
    await DBFactory.init_all()
    task_manager.initialize()

    from server.agent.base import AgentContext
    from server.agent.orchestrator import orchestrator

    ctx = AgentContext(
        session_id="multiturn_test",
        user_uuid="multiturn_user",
        paper_uuids=[],
    )

    # 第一轮
    ctx.add_message("user", "请记住：关键词是「苹果」。")
    events1 = []
    try:
        async for ev_str in orchestrator.run(ctx, "请记住：关键词是「苹果」。"):
            try:
                ev = json.loads(ev_str)
                events1.append(ev)
            except Exception:
                pass
        p("第一轮完成", any(e.get("event") == "done" for e in events1))
    except Exception as e:
        print(f"  {FAIL}  第一轮异常: {e}")

    # 第二轮：验证上下文中能看到历史
    ctx.add_message("user", "我刚才说的关键词是什么？")
    events2 = []
    try:
        async for ev_str in orchestrator.run(ctx, "我刚才说的关键词是什么？"):
            try:
                ev = json.loads(ev_str)
                events2.append(ev)
            except Exception:
                pass

        answer_events = [e for e in events2 if e.get("event") == "answer"]
        answer_text = str(answer_events[-1].get("data", "")) if answer_events else ""
        has_keyword = "苹果" in answer_text
        p("第二轮答案包含历史关键词「苹果」", has_keyword)
        print(f"  answer: {answer_text[:100]}")
    except Exception as e:
        print(f"  {FAIL}  第二轮异常: {e}")
    finally:
        await task_manager.shutdown()
        await DBFactory.close_all()


async def main():
    await test_session_crud()
    await test_message_history()
    await test_sse_stream()
    await test_multi_turn_context()
    print("\n=== Chat tests done ===\n")


if __name__ == "__main__":
    asyncio.run(main())
