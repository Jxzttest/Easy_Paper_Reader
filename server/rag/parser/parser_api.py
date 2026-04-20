#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import uuid
import pathlib

from fastapi import APIRouter, UploadFile, File, Form
from starlette.responses import JSONResponse

from server.config.config_loader import get_config
from server.task.task_manager import Task, task_manager
from server.db.db_factory import DBFactory
from server.utils.logger import logger

router = APIRouter(prefix="/papers")


def _get_papers_dir() -> pathlib.Path:
    cfg = get_config()
    d = pathlib.Path(cfg.get("storage", {}).get("papers_dir", "./data/papers"))
    d.mkdir(parents=True, exist_ok=True)
    return d


@router.post("/upload")
async def upload_paper(
    pdf_file: UploadFile = File(...),
    uploader_uuid: str = Form(...),
    parse_mode: str = Form("pymupdf"),  # pymupdf | paddleocr
):
    """
    上传 PDF 论文，构建多步 Task 并提交到 TaskManager。
    立即返回 task_id，前端通过 GET /tasks/{task_id} 轮询进度。

    Steps:
      1. save_file    — 保存 PDF 到本地
      2. parse_pdf    — 解析文本块 + 写入向量库
    """
    logger.info(f"[parser_api] upload: {pdf_file.filename}, mode={parse_mode}")

    # 先把文件内容读到内存（UploadFile 不能跨 async 边界）
    content = await pdf_file.read()
    original_name = pdf_file.filename

    # ── 构建 Task ──────────────────────────────────────────────────────
    task = Task("parse_pdf", user_uuid=uploader_uuid)

    # Step 1: 保存文件
    async def save_file():
        papers_dir = _get_papers_dir()
        safe_name = f"{uuid.uuid4().hex}_{original_name}"
        file_path = str(papers_dir / safe_name)
        with open(file_path, "wb") as f:
            f.write(content)
        logger.info(f"[parser_api] saved to {file_path}")
        return file_path          # 返回值会传给下一步

    # Step 2: 解析 PDF（接收 Step 1 的 file_path）
    async def parse_pdf(file_path: str):
        from server.rag.parser.pdf_parser import PDFParser
        parser = PDFParser(file_path, uploader_uuid, parse_mode=parse_mode)
        result = await parser.parse_and_save()
        return result

    task.add_step("save_file", save_file)
    task.add_step("parse_pdf", parse_pdf, depends_on="save_file")

    task_id = await task_manager.submit(task)

    return JSONResponse(status_code=202, content={
        "status": "accepted",
        "task_id": task_id,
        "message": "PDF 已上传，正在后台解析，通过 GET /tasks/{task_id} 查看进度。"
    })


@router.get("/list")
async def list_papers(uploader_uuid: str = ""):
    """列出论文（可按 uploader_uuid 过滤）。"""
    sqlite = DBFactory.get_sqlite()
    papers = await sqlite.get_all_papers(uploader_uuid=uploader_uuid or None)
    return JSONResponse(content={"papers": papers})


@router.get("/{paper_uuid}")
async def get_paper(paper_uuid: str):
    """获取单篇论文元数据。"""
    sqlite = DBFactory.get_sqlite()
    paper = await sqlite.get_paper_metadata(paper_uuid)
    if not paper:
        return JSONResponse(status_code=404, content={"detail": "paper not found"})
    return JSONResponse(content=paper)


@router.delete("/{paper_uuid}")
async def delete_paper(paper_uuid: str):
    """删除论文元数据 + 向量数据。"""
    sqlite = DBFactory.get_sqlite()
    vector_store = DBFactory.get_vector_store()
    await sqlite.delete_paper_metadata(paper_uuid)
    await vector_store.delete_paper_chunks(paper_uuid)
    return JSONResponse(content={"status": "deleted", "paper_uuid": paper_uuid})
