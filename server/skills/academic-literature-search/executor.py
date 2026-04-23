#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
academic-literature-search executor

对外暴露统一入口：execute(task_desc, paper_uuids, **kwargs) -> SkillResult

执行策略：
  1. 从 task_desc 中提取搜索关键词（LLM 提取）
  2. 调用 arXiv API 搜索（stdlib，无额外依赖）
  3. 返回结构化结果（title/authors/abstract/url/year）

扩展点（待集成 MCP 时启用）：
  - PubMed: pubmed_search_articles MCP tool
  - bioRxiv/medRxiv: pubmed_search_articles + journal filter
"""

import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from server.utils.logger import logger


# ── 结果数据结构 ──────────────────────────────────────────────────────────────

@dataclass
class Article:
    title: str
    authors: List[str]
    abstract: str
    url: str
    year: str
    source: str          # "arxiv" | "pubmed" | ...
    arxiv_id: str = ""
    doi: str = ""
    journal: str = ""


@dataclass
class SkillResult:
    success: bool
    articles: List[Article] = field(default_factory=list)
    query: str = ""
    summary: str = ""
    error: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "query": self.query,
            "count": len(self.articles),
            "articles": [
                {
                    "title": a.title,
                    "authors": a.authors,
                    "abstract": a.abstract[:300] + "..." if len(a.abstract) > 300 else a.abstract,
                    "url": a.url,
                    "year": a.year,
                    "source": a.source,
                    "doi": a.doi,
                    "journal": a.journal,
                }
                for a in self.articles
            ],
            "summary": self.summary,
            "error": self.error,
        }

    def to_readable(self) -> str:
        """生成供 LLM 或用户阅读的文本摘要。"""
        if not self.success:
            return f"检索失败：{self.error}"
        if not self.articles:
            return f"未找到与「{self.query}」相关的论文。"

        lines = [f"共检索到 {len(self.articles)} 篇相关论文（关键词：{self.query}）：\n"]
        for i, a in enumerate(self.articles, 1):
            authors_str = ", ".join(a.authors[:3]) + (" et al." if len(a.authors) > 3 else "")
            lines.append(
                f"[{i}] **{a.title}**\n"
                f"    作者：{authors_str}（{a.year}）\n"
                f"    来源：{a.source.upper()}  {a.url}\n"
                f"    摘要：{a.abstract[:200]}{'...' if len(a.abstract) > 200 else ''}\n"
            )
        return "\n".join(lines)


# ── 主执行入口 ────────────────────────────────────────────────────────────────

async def execute(
    task_desc: str,
    paper_uuids: List[str] = None,
    max_results: int = 10,
    **kwargs,
) -> SkillResult:
    """
    统一执行入口，由 TaskExecutor 调用。

    Args:
        task_desc:    用户下达的自然语言任务描述
        paper_uuids:  当前关联的论文 UUID 列表（可用于提取关键词上下文）
        max_results:  最大返回条数
    """
    logger.info(f"[academic-literature-search] task_desc={task_desc[:80]}")

    # Step 1: 提取搜索关键词
    query = await _extract_query(task_desc)
    if not query:
        return SkillResult(success=False, error="无法从任务描述中提取有效的搜索关键词", query=task_desc)

    logger.info(f"[academic-literature-search] extracted query: {query}")

    # Step 2: 执行搜索（当前支持 arXiv，后续可加 PubMed）
    articles: List[Article] = []

    arxiv_results = await _search_arxiv(query, max_results=max_results)
    articles.extend(arxiv_results)

    if not articles:
        return SkillResult(success=True, articles=[], query=query,
                           summary=f"未找到与「{query}」相关的论文")

    result = SkillResult(
        success=True,
        articles=articles,
        query=query,
        summary=f"检索到 {len(articles)} 篇与「{query}」相关的论文",
    )
    logger.info(f"[academic-literature-search] found {len(articles)} articles for query: {query}")
    return result


# ── 关键词提取（LLM 辅助）────────────────────────────────────────────────────

async def _extract_query(task_desc: str) -> str:
    """
    从任务描述中提取适合学术数据库检索的英文关键词。
    先尝试用规则提取，失败则调用 LLM。
    """
    # 简单规则：清理"帮我搜索/检索/找"等前缀，直接用剩余内容
    cleaned = re.sub(
        r'^(帮(我)?|请|麻烦)?(搜索?|检索|查找?|找到?)(一下|一些|相关)?[的地]?',
        '',
        task_desc.strip(),
        flags=re.IGNORECASE,
    ).strip()
    cleaned = re.sub(r'(论文|文献|paper|papers|文章)$', '', cleaned, flags=re.IGNORECASE).strip()

    if cleaned and len(cleaned) > 3:
        # 若包含中文，调用 LLM 翻译为英文关键词
        if re.search(r'[一-鿿]', cleaned):
            return await _translate_to_en_keywords(cleaned)
        return cleaned

    # 兜底：用完整描述让 LLM 提取
    return await _translate_to_en_keywords(task_desc)


async def _translate_to_en_keywords(text: str) -> str:
    """调用 LLM 将中文描述转为英文检索关键词。"""
    try:
        from server.model.llm_model.llm_function import LLMManager
        llm = LLMManager()
        resp = await llm.invoke(
            [
                {
                    "role": "user",
                    "content": (
                        "请从以下学术检索需求中提取3-5个核心英文关键词，"
                        "用空格分隔，直接输出关键词，不要任何解释：\n\n"
                        + text
                    ),
                }
            ],
            temperature=0.1,
        )
        return resp.strip().split("\n")[0].strip()
    except Exception as e:
        logger.warning(f"[academic-literature-search] LLM keyword extraction failed: {e}")
        # 降级：直接返回原文
        return text


# ── arXiv 搜索 ────────────────────────────────────────────────────────────────

async def _search_arxiv(query: str, max_results: int = 10) -> List[Article]:
    """异步包装 arXiv 搜索（使用 asyncio executor 避免阻塞事件循环）。"""
    import asyncio
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _sync_search_arxiv, query, max_results)


def _sync_search_arxiv(query: str, max_results: int = 10) -> List[Article]:
    """同步 arXiv 搜索，仅用 stdlib。"""
    try:
        params = urllib.parse.urlencode({
            "search_query": f"all:{query}",
            "start": 0,
            "max_results": max_results,
            "sortBy": "relevance",
            "sortOrder": "descending",
        })
        url = f"https://export.arxiv.org/api/query?{params}"
        with urllib.request.urlopen(url, timeout=30) as resp:
            xml_text = resp.read().decode("utf-8")
    except Exception as e:
        logger.error(f"[academic-literature-search] arXiv request failed: {e}")
        return []

    ns = {
        "atom": "http://www.w3.org/2005/Atom",
        "arxiv": "http://arxiv.org/schemas/atom",
    }
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        logger.error(f"[academic-literature-search] arXiv XML parse error: {e}")
        return []

    articles = []
    for entry in root.findall("atom:entry", ns):
        title = (entry.findtext("atom:title", "", ns) or "").replace("\n", " ").strip()
        abstract = (entry.findtext("atom:summary", "", ns) or "").replace("\n", " ").strip()

        raw_authors = [
            a.findtext("atom:name", "", ns).strip()
            for a in entry.findall("atom:author", ns)
        ]
        authors = [_format_author(a) for a in raw_authors if a]

        published = entry.findtext("atom:published", "", ns)[:10]
        id_url = entry.findtext("atom:id", "", ns) or ""
        arxiv_id = id_url.split("/abs/")[-1] if "/abs/" in id_url else ""

        doi_elem = entry.find("arxiv:doi", ns)
        doi = doi_elem.text.strip() if doi_elem is not None and doi_elem.text else ""

        articles.append(Article(
            title=title,
            authors=authors,
            abstract=abstract,
            url=f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else id_url,
            year=published[:4] if published else "",
            source="arxiv",
            arxiv_id=arxiv_id,
            doi=doi,
            journal=f"arXiv:{arxiv_id}",
        ))

    return articles


def _format_author(full_name: str) -> str:
    """'Shunyu Yao' → 'Yao S'（GB/T 7714 格式）。"""
    parts = full_name.strip().split()
    if not parts:
        return full_name
    if len(parts) == 1:
        return parts[0]
    surname = parts[-1]
    initials = "".join(p[0].upper() for p in parts[:-1])
    return f"{surname} {initials}"
