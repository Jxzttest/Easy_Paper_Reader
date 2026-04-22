#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
CitationAgent —— 引用检索 + 自动下载

流程：
  1. 从已解析的论文 chunks 中提取参考文献列表（LLM 辅助解析）
  2. 逐条查询 Semantic Scholar API，获取元数据（标题/作者/DOI/PDF链接）
  3. 尝试下载 open-access PDF；若无，记录元数据供用户手动下载
  4. 将新下载的论文入队解析（可选，复用 PDFParser）
  5. 将结果摘要写入 ctx.shared_memory（供 Orchestrator 汇总）

可作为子 Agent 被 Orchestrator 调用，
也可被 SchedulerService 直接调用（不依赖 AgentContext）。
"""

import asyncio
import json
import re
import pathlib
import uuid
from typing import Dict, List, Optional, Tuple

import httpx

from server.agent.base import AgentBase, AgentContext
from server.config.config_loader import get_config
from server.db.db_factory import DBFactory
from server.utils.logger import logger

# Semantic Scholar 免费 API（无需 Key，但有速率限制 100 req/5min）
_S2_SEARCH_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
_S2_FIELDS = "title,authors,year,externalIds,openAccessPdf,abstract"

# 请求超时
_HTTP_TIMEOUT = 20.0
# 单次任务最多处理引用数（避免 API 超限）
_MAX_CITATIONS_PER_RUN = 20


class CitationAgent(AgentBase):
    name = "citation_agent"
    description = "从论文中提取引用，查询元数据，自动下载可获取的 PDF"

    # ── 作为子 Agent 被 Orchestrator 调用 ─────────────────────────────
    async def run(self, ctx: AgentContext, **kwargs) -> Dict:
        paper_uuid = kwargs.get("paper_uuid") or (
            ctx.paper_uuids[0] if ctx.paper_uuids else None
        )
        if not paper_uuid:
            return {"summary": "未指定论文，跳过引用检索", "citations": []}

        result = await self.run_for_paper(paper_uuid)
        ctx.shared_memory["citation_result"] = result
        return {"summary": f"找到 {len(result['found'])} 篇引用，下载 {result['downloaded']} 篇", **result}

    # ── 核心功能（可独立调用，不依赖 AgentContext）────────────────────
    async def run_for_paper(self, paper_uuid: str) -> Dict:
        """
        对单篇论文执行完整的引用检索流程。
        返回结构：
          {found: [...], downloaded: int, skipped: int, errors: [...]}
        """
        logger.info(f"[CitationAgent] start for paper={paper_uuid}")
        vector_store = DBFactory.get_vector_store()
        sqlite = DBFactory.get_sqlite()

        # 1. 从已入库的 chunks 中找参考文献段落
        chunks = await vector_store.get_paper_chunks(paper_uuid)
        ref_chunks = [c for c in chunks if _is_reference_chunk(c)]

        if not ref_chunks:
            logger.info(f"[CitationAgent] no reference chunks found for {paper_uuid}")
            return {"found": [], "downloaded": 0, "skipped": 0, "errors": []}

        # 2. LLM 解析参考文献列表
        ref_text = "\n".join(c["content"] for c in ref_chunks[:10])
        citations = await self._parse_references(ref_text)
        citations = citations[:_MAX_CITATIONS_PER_RUN]
        logger.info(f"[CitationAgent] parsed {len(citations)} citations")

        # 3. 逐条查询 Semantic Scholar
        found, downloaded, skipped, errors = [], 0, 0, []

        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            for cit in citations:
                try:
                    meta = await self._query_semantic_scholar(client, cit)
                    if not meta:
                        skipped += 1
                        continue

                    found.append(meta)

                    # 4. 尝试下载 open-access PDF
                    pdf_url = meta.get("pdf_url", "")
                    if pdf_url:
                        dl_path = await self._download_pdf(client, pdf_url, meta["title"])
                        if dl_path:
                            meta["local_path"] = dl_path
                            downloaded += 1
                            await self._enqueue_parse(dl_path, meta)
                        else:
                            errors.append(f"下载失败: {meta['title'][:40]}")
                    else:
                        meta["local_path"] = ""

                    # Semantic Scholar 速率限制：~1 req/s
                    await asyncio.sleep(1.1)

                except Exception as e:
                    errors.append(str(e)[:100])
                    logger.warning(f"[CitationAgent] citation error: {e}")

        logger.info(f"[CitationAgent] done: found={len(found)}, downloaded={downloaded}")
        return {
            "paper_uuid": paper_uuid,
            "found": found,
            "downloaded": downloaded,
            "skipped": skipped,
            "errors": errors,
        }

    # ── LLM 解析参考文献 ─────────────────────────────────────────────
    async def _parse_references(self, ref_text: str) -> List[Dict]:
        prompt = f"""以下是一篇论文的参考文献部分，请提取每条参考文献的关键信息。

参考文献原文：
{ref_text[:3000]}

请输出 JSON 数组，每条格式如下（没有信息则留空字符串）：
[
  {{"title": "论文标题", "authors": "作者列表", "year": "年份", "doi": "DOI号"}},
  ...
]
只输出 JSON 数组，不要有任何其他文字。"""

        resp = await self._invoke([{"role": "user", "content": prompt}], temperature=0.1)
        try:
            m = re.search(r'\[.*\]', resp, re.DOTALL)
            return json.loads(m.group()) if m else []
        except Exception:
            return []

    # ── Semantic Scholar 查询 ─────────────────────────────────────────
    async def _query_semantic_scholar(
        self, client: httpx.AsyncClient, cit: Dict
    ) -> Optional[Dict]:
        title = cit.get("title", "").strip()
        if not title:
            return None

        try:
            r = await client.get(
                _S2_SEARCH_URL,
                params={"query": title, "fields": _S2_FIELDS, "limit": 1},
                headers={"User-Agent": "EasyPaperReader/1.0"},
            )
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            logger.warning(f"[CitationAgent] S2 query failed: {e}")
            return None

        papers = data.get("data", [])
        if not papers:
            return None

        p = papers[0]
        pdf_url = (p.get("openAccessPdf") or {}).get("url", "")
        ext_ids = p.get("externalIds") or {}

        return {
            "title": p.get("title", title),
            "authors": ", ".join(a.get("name", "") for a in (p.get("authors") or [])),
            "year": p.get("year", cit.get("year", "")),
            "doi": ext_ids.get("DOI", cit.get("doi", "")),
            "arxiv_id": ext_ids.get("ArXiv", ""),
            "s2_paper_id": p.get("paperId", ""),
            "abstract": (p.get("abstract") or "")[:500],
            "pdf_url": pdf_url,
        }

    # ── 下载 PDF ─────────────────────────────────────────────────────
    async def _download_pdf(
        self, client: httpx.AsyncClient, url: str, title: str
    ) -> Optional[str]:
        cfg = get_config()
        papers_dir = pathlib.Path(cfg.get("storage", {}).get("papers_dir", "./data/papers"))
        papers_dir.mkdir(parents=True, exist_ok=True)

        safe_name = re.sub(r'[^\w\s-]', '', title)[:60].strip().replace(' ', '_')
        file_path = papers_dir / f"{uuid.uuid4().hex[:8]}_{safe_name}.pdf"

        try:
            async with client.stream("GET", url, follow_redirects=True) as r:
                r.raise_for_status()
                content_type = r.headers.get("content-type", "")
                if "pdf" not in content_type and "octet-stream" not in content_type:
                    return None
                with open(file_path, "wb") as f:
                    async for chunk in r.aiter_bytes(8192):
                        f.write(chunk)
            logger.info(f"[CitationAgent] downloaded: {file_path.name}")
            return str(file_path)
        except Exception as e:
            logger.warning(f"[CitationAgent] download failed ({url}): {e}")
            if file_path.exists():
                file_path.unlink()
            return None

    # ── 将下载的论文加入解析队列 ──────────────────────────────────────
    async def _enqueue_parse(self, file_path: str, meta: Dict) -> None:
        from server.task.task_manager import Task, task_manager

        async def parse_fn():
            from server.rag.parser.pdf_parser import PDFParser
            parser = PDFParser(file_path)
            result = await parser.parse_and_save()
            sqlite = DBFactory.get_sqlite()
            await sqlite.update_paper_fields(
                result["paper_uuid"],
                authors=meta.get("authors", ""),
                doi=meta.get("doi", ""),
                arxiv_id=meta.get("arxiv_id", ""),
                publish_year=int(meta["year"]) if str(meta.get("year", "")).isdigit() else None,
                abstract=meta.get("abstract", ""),
            )
            return result

        task = Task("parse_citation_pdf")
        task.add_step("parse_pdf", parse_fn)
        await task_manager.submit(task)


# ── 工具函数 ──────────────────────────────────────────────────────────────
def _is_reference_chunk(chunk: Dict) -> bool:
    content = chunk.get("content", "").lower()
    content_type = chunk.get("content_type", "")
    # 常见参考文献段特征
    return (
        content_type in ("text",) and
        any(kw in content for kw in ["references", "参考文献", "bibliography", "[1]", "[2]"])
    )
