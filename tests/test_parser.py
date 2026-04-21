#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_parser.py — PDF 解析流程测试

测试内容：
  1. PyMuPDF 解析：提取文本块
  2. 元数据提取
  3. 完整 parse_and_save 流程（需要真实 API Key）

运行方式（在项目根目录，需先配置 .env）：
  python tests/test_parser.py

可选参数（环境变量）：
  PDF_PATH=./path/to/test.pdf  指定测试 PDF，默认找项目根目录的第一个 PDF
  SKIP_EMBED=1                 跳过 Embedding API 调用（只测解析，不入向量库）
"""

import sys
import os
import asyncio
import glob

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

def _find_test_pdf() -> str:
    path = os.environ.get("PDF_PATH", "")
    if path and os.path.exists(path):
        return path
    # 自动查找项目根目录的 PDF
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    pdfs = glob.glob(os.path.join(root, "*.pdf"))
    if pdfs:
        return pdfs[0]
    return ""


async def test_metadata_extraction(pdf_path: str):
    print("\n=== 元数据提取 ===")
    from server.rag.parser.pdf_parser import PDFParser
    parser = PDFParser(pdf_path, uploader_uuid="test_user")
    meta = parser._extract_metadata()
    p("title 非空", bool(meta.get("title")))
    p("page_count > 0", meta.get("page_count", 0) > 0)
    print(f"  title     : {meta.get('title', '')[:60]}")
    print(f"  author    : {meta.get('author', '')[:60]}")
    print(f"  page_count: {meta.get('page_count', 0)}")


async def test_pymupdf_parse(pdf_path: str):
    print("\n=== PyMuPDF 解析（不调用 API）===")
    from server.rag.parser.pdf_parser import PDFParser
    parser = PDFParser(pdf_path, uploader_uuid="test_user", parse_mode="pymupdf")
    chunks = await parser._parse_with_pymupdf()
    p("解析出 chunk > 0", len(chunks) > 0)
    p("chunk 包含 content 字段", all("content" in c for c in chunks))
    p("chunk 包含 page_num 字段", all("page_num" in c for c in chunks))
    print(f"  共解析 {len(chunks)} 个文本块")
    if chunks:
        print(f"  示例 chunk (page {chunks[0]['page_num']}): {chunks[0]['content'][:80]}...")

async def test_paddleocr_parse(pdf_path: str):
    print("\n=== PaddleOCR 解析（不调用 API）===")
    from server.rag.parser.pdf_parser import PDFParser
    parser = PDFParser(pdf_path, uploader_uuid="test_user", parse_mode="paddleocr")
    chunks = await parser._parse_with_paddleocr()
    p("解析出 chunk > 0", len(chunks) > 0)
    p("chunk 包含 content 字段", all("content" in c for c in chunks))
    p("chunk 包含 page_num 字段", all("page_num" in c for c in chunks))
    print(f"  共解析 {len(chunks)} 个文本块")
    if chunks:
        print(f"  示例 chunk (page {chunks[0]['page_num']}): {chunks[0]['content'][:80]}...")


async def test_full_pipeline(pdf_path: str):
    """完整流程：需要 API Key + 已初始化 DBFactory。"""
    print("\n=== 完整解析流程（需要 API Key）===")
    if not _need_api():
        return
    from server.db.db_factory import DBFactory
    from server.task.task_manager import task_manager
    await DBFactory.init_all()
    task_manager.initialize()

    from server.rag.parser.pdf_parser import PDFParser
    parser = PDFParser(pdf_path, uploader_uuid="test_user", parse_mode="pymupdf")
    try:
        result = await parser.parse_and_save()
        p("parse_and_save 返回 success", result.get("status") == "success")
        p("paper_uuid 非空", bool(result.get("paper_uuid")))
        p("chunks > 0", result.get("chunks", 0) > 0)
        print(f"  paper_uuid: {result.get('paper_uuid')}")
        print(f"  入库 chunks: {result.get('chunks')}")

        # 验证元数据已写入 SQLite
        sqlite = DBFactory.get_sqlite()
        meta = await sqlite.get_paper_metadata(result["paper_uuid"])
        p("元数据已写入 SQLite", meta is not None and meta["is_processed"] == 1)

        # 验证 chunks 已写入 ChromaDB
        chroma = DBFactory.get_vector_store()
        count = await chroma.count_chunks_by_paper(result["paper_uuid"])
        p("Chunks 已写入 ChromaDB", count > 0)
        print(f"  ChromaDB chunks: {count}")

    except Exception as e:
        print(f"  {FAIL}  parse_and_save 异常: {e}")
    finally:
        await DBFactory.close_all()


async def main():
    pdf_path = _find_test_pdf()
    if not pdf_path:
        print("❌ 未找到测试 PDF，请设置环境变量 PDF_PATH=/path/to/file.pdf")
        return

    print(f"测试 PDF: {pdf_path}")
    await test_metadata_extraction(pdf_path)
    await test_pymupdf_parse(pdf_path)
    await test_paddleocr_parse(pdf_path)
    await test_full_pipeline(pdf_path)
    print("\n=== Parser tests done ===\n")


if __name__ == "__main__":
    asyncio.run(main())
