#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Translate API

POST /translate/text   : 翻译文本（非流式，适合选中文本即时翻译）
POST /translate/stream : 翻译文本（SSE 流式，适合长段落）
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from server.model.translation_model.translation_model import get_translation_model
from server.utils.logger import logger

router = APIRouter(prefix="/translate")


class TranslateRequest(BaseModel):
    text: str
    target_lang: str = "auto"   # "zh" | "en" | "auto"


@router.post("/text")
async def translate_text(req: TranslateRequest):
    """
    翻译文本，返回翻译结果。
    适合前端选中文本后即时翻译展示。
    """
    if not req.text or not req.text.strip():
        return JSONResponse(content={"result": "", "target_lang": req.target_lang})

    try:
        model = get_translation_model()
        result = await model.async_invoke(req.text, target_lang=req.target_lang)
        return JSONResponse(content={"result": result, "target_lang": req.target_lang})
    except Exception as e:
        logger.error(f"[translate_api] translate failed: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"error": str(e)},
        )


@router.post("/stream")
async def translate_stream(req: TranslateRequest):
    """
    流式翻译，SSE 格式输出。
    适合长段落翻译，逐步显示翻译结果。
    """
    if not req.text or not req.text.strip():
        async def empty():
            yield "data: \n\n"
        return StreamingResponse(empty(), media_type="text/event-stream")

    async def event_stream():
        try:
            model = get_translation_model()
            async for chunk in model.async_stream(req.text, target_lang=req.target_lang):
                # 转义换行，保持 SSE 格式
                safe = chunk.replace("\n", "\\n")
                yield f"data: {safe}\n\n"
        except Exception as e:
            logger.error(f"[translate_api] stream failed: {e}", exc_info=True)
            yield f"data: [ERROR: {str(e)}]\n\n"
        finally:
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
