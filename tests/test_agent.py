#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_agent.py — Agent 系统联调测试

测试内容：
  1. SupervisorAgent  : 意图识别 + 计划生成
  2. RAGAgent         : 检索（用预置 chunk 数据）
  3. WritingAgent     : 各模式写作
  4. TranslationAgent : 中英互译
  5. CheckAgent       : 质量评估
  6. AgentOrchestrator: 完整对话流程（收集所有 SSE 事件）

运行方式（在项目根目录，需先配置 .env）：
  python tests/test_agent.py
"""

import sys
import os
import asyncio

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


def _make_ctx(paper_uuids=None):
    from server.agent.base import AgentContext
    return AgentContext(
        session_id="test_sess",
        user_uuid="test_user",
        paper_uuids=paper_uuids or [],
    )


# ── 1. SupervisorAgent ────────────────────────────────────────────────────
async def test_supervisor():
    print("\n=== SupervisorAgent ===")
    if not _need_api():
        return

    from server.agent.supervisor_agent import SupervisorAgent, INTENT_PLAN
    agent = SupervisorAgent()

    cases = [
        ("这篇论文的创新点是什么？", "innovation"),
        ("帮我把这段话翻译成英文", "translation"),
        ("请帮我润色一下这段摘要", "polish"),
        ("请检索引用文献", "citation"),
    ]

    for query, expected_intent in cases:
        ctx = _make_ctx()
        ctx.add_message("user", query)
        try:
            result = await agent.run(ctx, user_input=query)
            intent = result.get("intent", "")
            plan   = result.get("plan", [])
            ok = intent == expected_intent and len(plan) > 0
            p(f"'{query[:25]}' → intent={intent}", ok)
        except Exception as e:
            print(f"  {FAIL}  '{query[:25]}' 异常: {e}")


# ── 2. RAGAgent（用预置 chunks）──────────────────────────────────────────
async def test_rag_agent():
    print("\n=== RAGAgent ===")
    if not _need_api():
        return

    from server.db.db_factory import DBFactory
    from server.task.task_manager import task_manager

    await DBFactory.init_all()
    task_manager.initialize()

    # 预置测试数据
    chroma = DBFactory.get_vector_store()
    embedding_mgr = __import__("server.model.embedding_model.embedding", fromlist=["EmbeddingManager"]).EmbeddingManager()

    test_pid = "test_paper_rag"
    test_content = (
        "The main contribution of this paper is a novel attention mechanism "
        "called Multi-Head Self-Attention, which allows the model to jointly attend "
        "to information from different representation subspaces at different positions."
    )
    vec = await embedding_mgr.get_embedding(test_content)
    await chroma.add_paper_chunk(
        paper_id=test_pid, chunk_id=f"{test_pid}_c0",
        content=test_content, content_type="text", vector=vec, page_num=1,
    )

    from server.agent.rag_agent import RAGAgent
    ctx = _make_ctx(paper_uuids=[test_pid])
    ctx.shared_memory["focus"] = "What is the main contribution of this paper?"

    try:
        agent = RAGAgent()
        result = await agent.run(ctx)
        p("返回 answer", bool(result.get("answer")))
        p("返回 sources", isinstance(result.get("sources"), list))
        p("mode 字段存在", "mode" in result)
        print(f"  mode  : {result.get('mode')}")
        print(f"  answer: {result.get('answer', '')[:100]}...")
    except Exception as e:
        print(f"  {FAIL}  RAGAgent 异常: {e}")
    finally:
        await chroma.delete_paper_chunks(test_pid)
        await DBFactory.close_all()


# ── 3. WritingAgent ───────────────────────────────────────────────────────
async def test_writing_agent():
    print("\n=== WritingAgent ===")
    if not _need_api():
        return

    from server.agent.writing_agent import WritingAgent
    agent = WritingAgent()

    cases = [
        ("innovation", "分析一下这篇论文的创新点"),
        ("polish",     "请润色：The model is good and has many advantages."),
        ("general",    "什么是 Transformer？"),
    ]
    for intent, query in cases:
        ctx = _make_ctx()
        ctx.shared_memory["intent"] = intent
        ctx.shared_memory["focus"] = query
        ctx.add_message("user", query)
        try:
            result = await agent.run(ctx)
            p(f"intent={intent} 返回结果", bool(result.get("result")))
            print(f"  [{intent}] {result.get('result','')[:80]}...")
        except Exception as e:
            print(f"  {FAIL}  intent={intent} 异常: {e}")


# ── 4. TranslationAgent ───────────────────────────────────────────────────
async def test_translation_agent():
    print("\n=== TranslationAgent ===")
    if not _need_api():
        return

    from server.agent.translation_agent import TranslationAgent
    agent = TranslationAgent()

    for query in ["请翻译：The quick brown fox", "请将以下内容翻译成英文：注意力机制是深度学习的核心"]:
        ctx = _make_ctx()
        ctx.add_message("user", query)
        ctx.shared_memory["focus"] = query
        try:
            result = await agent.run(ctx)
            p(f"翻译返回结果", bool(result.get("result")))
            print(f"  {result.get('result','')[:80]}...")
        except Exception as e:
            print(f"  {FAIL}  翻译异常: {e}")


# ── 5. CheckAgent ─────────────────────────────────────────────────────────
async def test_check_agent():
    print("\n=== CheckAgent ===")
    if not _need_api():
        return

    from server.agent.check_agent import CheckAgent
    agent = CheckAgent()

    ctx = _make_ctx()
    ctx.shared_memory["focus"] = "Transformer 的创新点是什么？"
    ctx.shared_memory["rag_answer"] = (
        "Transformer 的核心创新是 Multi-Head Self-Attention 机制，"
        "完全抛弃了 RNN 结构，并行计算能力大幅提升。"
    )
    try:
        result = await agent.run(ctx)
        p("返回 passed 字段", "passed" in result)
        p("返回 score 字段", "score" in result)
        print(f"  passed={result.get('passed')}, score={result.get('score'):.2f}")
        if result.get("suggestion"):
            print(f"  suggestion: {result['suggestion'][:80]}")
    except Exception as e:
        print(f"  {FAIL}  CheckAgent 异常: {e}")


# ── 6. 完整 Orchestrator 流程 ──────────────────────────────────────────────
async def test_orchestrator():
    print("\n=== AgentOrchestrator（完整对话流）===")
    if not _need_api():
        return

    from server.db.db_factory import DBFactory
    from server.task.task_manager import task_manager
    await DBFactory.init_all()
    task_manager.initialize()

    from server.agent.orchestrator import orchestrator
    ctx = _make_ctx()

    events = []
    try:
        async for ev_str in orchestrator.run(ctx, "Transformer 模型的主要创新点是什么？"):
            import json
            ev = json.loads(ev_str)
            events.append(ev)
            print(f"  event: {ev['event']:10s} | {str(ev.get('data',''))[:60]}")
    except Exception as e:
        print(f"  {FAIL}  Orchestrator 异常: {e}")
        return
    finally:
        await DBFactory.close_all()

    event_types = {e["event"] for e in events}
    p("收到 plan 事件",   "plan"   in event_types)
    p("收到 agent 事件",  "agent"  in event_types)
    p("收到 answer 事件", "answer" in event_types)
    p("收到 done 事件",   "done"   in event_types)


async def main():
    await test_supervisor()
    await test_rag_agent()
    await test_writing_agent()
    await test_translation_agent()
    await test_check_agent()
    await test_orchestrator()
    print("\n=== Agent tests done ===\n")


if __name__ == "__main__":
    asyncio.run(main())
