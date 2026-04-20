#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import uuid
import asyncio
import hashlib
import pathlib
import time
import re
from typing import Dict, Any, List, Optional

import fitz  # PyMuPDF
from fastapi import HTTPException

from server.config.config_loader import get_config
from server.model.embedding_model.embedding import EmbeddingManager
from server.db.db_factory import DBFactory
from server.utils.logger import logger


class PDFParser:
    """
    PDF 解析器，支持两种模式：
      - pymupdf  : 快速文字提取（默认，无额外依赖）
      - paddleocr: 高精度 OCR（需安装 paddleocr/paddlepaddle）

    解析流程：
      1. 提取 PDF 元数据，写入 SQLite
      2. 按模式解析文本块（PyMuPDF 直接抽文字；PaddleOCR 先转图再识别）
      3. 对每个文本块调用 Embedding API，写入 ChromaDB
      4. 标记论文处理完成
    """

    def __init__(self, file_path: str, uploader_uuid: str, parse_mode: Optional[str] = None):
        self.file_path = file_path
        self.uploader_uuid = uploader_uuid
        self.paper_uuid = uuid.uuid4().hex

        cfg = get_config()
        self.parse_mode = parse_mode or cfg.get("parser", {}).get("default_mode", "pymupdf")

        # 资源目录
        storage_cfg = cfg.get("storage", {})
        assets_root = pathlib.Path(storage_cfg.get("assets_dir", "./data/assets"))
        self.assets_dir = assets_root / self.paper_uuid
        self.assets_dir.mkdir(parents=True, exist_ok=True)

        self.embedding_manager = EmbeddingManager()

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    async def parse_and_save(self) -> Dict[str, Any]:
        """主流程：解析 → 向量化 → 入库"""
        logger.info(f"[PDFParser] start parse: {self.file_path}, mode={self.parse_mode}")

        sqlite = DBFactory.get_sqlite()
        vector_store = DBFactory.get_vector_store()

        # 1. 提取元数据
        metadata = self._extract_metadata()
        await sqlite.add_paper_metadata(
            paper_uuid=self.paper_uuid,
            title=metadata.get("title", "Untitled"),
            uploader_uuid=self.uploader_uuid,
            file_path=self.file_path,
            authors=metadata.get("author", ""),
            parse_mode=self.parse_mode,
        )

        try:
            # 2. 解析文本块
            if self.parse_mode == "paddleocr":
                chunks = await self._parse_with_paddleocr()
            else:
                chunks = await self._parse_with_pymupdf()

            logger.info(f"[PDFParser] got {len(chunks)} chunks")

            # 3. 批量向量化并写入 ChromaDB
            await self._embed_and_store(chunks, vector_store)

            # 4. 标记完成
            await sqlite.mark_paper_processed(self.paper_uuid)
            logger.info(f"[PDFParser] done: paper_uuid={self.paper_uuid}")
            return {"status": "success", "paper_uuid": self.paper_uuid, "chunks": len(chunks)}

        except Exception as e:
            logger.error(f"[PDFParser] failed: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    # ------------------------------------------------------------------ #
    # PyMuPDF 解析（默认，无额外依赖）
    # ------------------------------------------------------------------ #
    async def _parse_with_pymupdf(self) -> List[Dict]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._pymupdf_sync)

    def _pymupdf_sync(self) -> List[Dict]:
        chunks = []
        with fitz.open(self.file_path) as doc:
            for page_num, page in enumerate(doc, start=1):
                blocks = page.get_text("blocks")  # (x0, y0, x1, y1, text, block_no, block_type)
                for block in blocks:
                    text = block[4].strip()
                    block_type = block[6]  # 0=text, 1=image
                    if not text or block_type != 0:
                        continue
                    if len(text) < 10:  # 过滤噪声短文本
                        continue
                    chunks.append({
                        "content": text,
                        "content_type": "text",
                        "page_num": page_num,
                        "image_path": "",
                    })
        return chunks

    # ------------------------------------------------------------------ #
    # PaddleOCR 解析（可选，按需安装）
    # ------------------------------------------------------------------ #
    async def _parse_with_paddleocr(self) -> List[Dict]:
        try:
            from server.model.ocr_model.paddle_ocr import PaddleOCRPipeline
        except ImportError:
            logger.warning("[PDFParser] PaddleOCR not installed, falling back to pymupdf")
            return await self._parse_with_pymupdf()

        # PDF → 图片（在线程池中执行，避免阻塞）
        loop = asyncio.get_running_loop()
        image_paths = await loop.run_in_executor(None, self._convert_pdf_to_images)

        ocr = PaddleOCRPipeline(use_gpu=False)
        chunks = []
        for page_idx, img_path in enumerate(image_paths):
            page_num = page_idx + 1
            try:
                page_structure = await ocr.invoke_single_img(img_path, str(self.assets_dir))
                for item in page_structure:
                    for res in item.get("parsing_res_list", []):
                        label = res.get("block_label", "")
                        if label not in {"text", "formula", "figure", "table", "figure_title"}:
                            continue
                        content = res.get("block_content", "").strip()
                        if not content:
                            continue
                        chunks.append({
                            "content": content,
                            "content_type": label,
                            "page_num": page_num,
                            "image_path": res.get("image_path", ""),
                        })
            except Exception as e:
                logger.error(f"[PDFParser] OCR page {page_num} failed: {e}")
            finally:
                # 清理整页临时图
                if os.path.exists(img_path):
                    os.remove(img_path)

        return chunks

    def _convert_pdf_to_images(self, dpi: int = 200) -> List[str]:
        temp_dir = self.assets_dir / "_pages"
        temp_dir.mkdir(exist_ok=True)
        paths = []
        with fitz.open(self.file_path) as doc:
            for i, page in enumerate(doc):
                pix = page.get_pixmap(matrix=fitz.Matrix(dpi / 72, dpi / 72))
                out = str(temp_dir / f"page_{i + 1}.png")
                pix.save(out)
                paths.append(out)
        return paths

    # ------------------------------------------------------------------ #
    # Embedding + ChromaDB
    # ------------------------------------------------------------------ #
    async def _embed_and_store(self, chunks: List[Dict], vector_store) -> None:
        BATCH = 20  # 每批最多 20 条，控制 API 并发
        for i in range(0, len(chunks), BATCH):
            batch = chunks[i: i + BATCH]
            texts = [c["content"] for c in batch]
            vectors = await self.embedding_manager.get_embeddings_batch(texts)

            tasks = []
            for j, (chunk, vec) in enumerate(zip(batch, vectors)):
                chunk_id = f"{self.paper_uuid}_p{chunk['page_num']}_{chunk['content_type']}_{i + j}"
                tasks.append(
                    vector_store.add_paper_chunk(
                        paper_id=self.paper_uuid,
                        chunk_id=chunk_id,
                        content=chunk["content"],
                        content_type=chunk["content_type"],
                        vector=vec,
                        page_num=chunk["page_num"],
                        image_path=chunk.get("image_path", ""),
                    )
                )
            await asyncio.gather(*tasks)

    # ------------------------------------------------------------------ #
    # Metadata
    # ------------------------------------------------------------------ #
    def _extract_metadata(self) -> Dict[str, Any]:
        meta = {"title": os.path.basename(self.file_path), "author": ""}
        try:
            with fitz.open(self.file_path) as doc:
                m = doc.metadata
                meta["title"] = m.get("title") or os.path.basename(self.file_path)
                meta["author"] = m.get("author", "")
                meta["page_count"] = len(doc)
        except Exception as e:
            logger.error(f"[PDFParser] extract metadata failed: {e}")
        return meta
