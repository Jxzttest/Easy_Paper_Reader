#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Chat API —— 对话接口

POST /chat/send              : SSE 流式对话（主接口）
POST /chat/session/new       : 新建会话
GET  /chat/session/list      : 获取所有会话
GET  /chat/session/{id}      : 获取会话消息历史
DELETE /chat/session/{id}    : 删除会话
PATCH /chat/session/{id}/title : 修改会话标题
"""

import json
import uuid
from typing import List, Optional

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from starlette.responses import JSONResponse

from server.agent.base import AgentContext
from server.agent.orchestrator import orchestrator
from server.db.db_factory import DBFactory
from server.utils.logger import logger

router = APIRouter(prefix="/chat")


# ── 请求模型 ──────────────────────────────────────────────────────────────
class ChatRequest(BaseModel):
    session_id: str
    message: str
    paper_uuids: List[str] = []


class NewSessionRequest(BaseModel):
    paper_uuid: Optional[str] = ""


# ── SSE 流式对话 ──────────────────────────────────────────────────────────
@router.post("/send")
async def chat_send(req: ChatRequest):
    """
    SSE 接口：实时推送 Agent 执行事件。
    """
    sqlite = DBFactory.get_sqlite()

    if not await sqlite.check_session_exist(req.session_id):
        await sqlite.add_session(session_id=req.session_id)

    history = await sqlite.get_session_messages(req.session_id, limit=20)
    ctx = AgentContext(
        session_id=req.session_id,
        paper_uuids=req.paper_uuids,
        messages=[{"role": m["role"], "content": m["content"]} for m in history],
    )

    async def event_stream():
        full_answer = ""
        try:
            async for event_str in orchestrator.run(ctx, req.message):
                yield f"data: {event_str}\n\n"

                try:
                    ev = json.loads(event_str)
                    if ev.get("event") == "answer":
                        full_answer = ev["data"].get("content", "")
                except Exception:
                    pass

        except Exception as e:
            logger.error(f"[chat_api] stream error: {e}", exc_info=True)
            yield f"data: {json.dumps({'event': 'error', 'data': {'message': str(e)}}, ensure_ascii=False)}\n\n"
        finally:
            try:
                await sqlite.add_message(
                    session_id=req.session_id,
                    role="user",
                    content=req.message,
                )
                if full_answer:
                    await sqlite.add_message(
                        session_id=req.session_id,
                        role="assistant",
                        content=full_answer,
                    )
                msgs = await sqlite.get_session_messages(req.session_id, limit=2)
                if len(msgs) <= 2:
                    title = req.message[:40] + ("…" if len(req.message) > 40 else "")
                    await sqlite.update_session_title(req.session_id, title)
            except Exception as e:
                logger.error(f"[chat_api] persist failed: {e}")

            yield f"data: {json.dumps({'event': 'done', 'data': {}}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ── 会话管理 ──────────────────────────────────────────────────────────────
@router.post("/session/new")
async def new_session(req: NewSessionRequest):
    session_id = "sess_" + uuid.uuid4().hex
    sqlite = DBFactory.get_sqlite()
    await sqlite.add_session(
        session_id=session_id,
        paper_uuid=req.paper_uuid or "",
    )
    return JSONResponse(content={"session_id": session_id})


@router.get("/session/list")
async def list_sessions(paper_uuid: str = ""):
    sqlite = DBFactory.get_sqlite()
    sessions = await sqlite.get_all_sessions(paper_uuid=paper_uuid)
    result = []
    for s in sessions:
        msgs = await sqlite.get_session_messages(s["session_id"], limit=1)
        s["last_message"] = msgs[-1]["content"][:60] if msgs else ""
        result.append(s)
    return JSONResponse(content={"sessions": result})


@router.get("/session/{session_id}")
async def get_session_messages(session_id: str, limit: int = 50):
    sqlite = DBFactory.get_sqlite()
    messages = await sqlite.get_session_messages(session_id, limit=limit)
    return JSONResponse(content={"messages": messages})


@router.delete("/session/{session_id}")
async def delete_session(session_id: str):
    sqlite = DBFactory.get_sqlite()
    await sqlite.delete_session(session_id)
    return JSONResponse(content={"status": "deleted", "session_id": session_id})


@router.patch("/session/{session_id}/title")
async def update_session_title(session_id: str, title: str):
    sqlite = DBFactory.get_sqlite()
    await sqlite.update_session_title(session_id, title)
    return JSONResponse(content={"status": "ok", "session_id": session_id, "title": title})
