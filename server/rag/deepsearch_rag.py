#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
DeepSearchRAG —— 多跳深度检索

参考 readme.md 设计：
  1. 初次检索，评估质量
  2. 若质量不足：分解为子问题（query decomposition）
  3. 对每个子问题独立检索，合并结果去重
  4. 对合并结果再做事实一致性验证（fact check）
  5. 最多 MAX_HOPS 轮，确保不无限循环

与 deepsearch.py（SelfReflectiveRAG）的关系：
  - 本类是面向论文库检索的生产实现
  - deepsearch.py 是学习参考，核心的 fact_check / verify_claim 逻辑已移植到此
"""

import json
import re
from dataclasses import dataclass
from typing import Dict, List, Optional

from server.rag.base_rag import BaseRAG, RetrievalResult
from server.utils.logger import logger

MAX_HOPS = 3
QUALITY_OK = 0.65       # 此分以上认为检索充分
FACT_CHECK_OK = 0.75    # 事实一致性通过线


@dataclass
class ClaimVerification:
    claim: str
    verdict: str      # SUPPORTED | CONTRADICTED | UNVERIFIED
    confidence: float


class DeepSearchRAG(BaseRAG):
    """多跳深度检索 RAG，处理需要跨段落推理的复杂问题。"""

    async def retrieve(
        self,
        query: str,
        paper_uuids: Optional[List[str]] = None,
        top_k: int = 8,
    ) -> RetrievalResult:
        """多跳检索：分解 → 子检索 → 合并去重。"""
        paper_id = paper_uuids[0] if paper_uuids and len(paper_uuids) == 1 else None
        all_chunks: List[Dict] = []
        seen_ids = set()
        current_query = query

        for hop in range(MAX_HOPS):
            logger.info(f"[DeepSearchRAG] hop {hop+1}/{MAX_HOPS}, query='{current_query[:60]}'")

            chunks = await self._search_chunks(current_query, paper_id, top_k)
            # 去重
            for c in chunks:
                cid = c.get("chunk_id", c["content"][:50])
                if cid not in seen_ids:
                    seen_ids.add(cid)
                    all_chunks.append(c)

            score = await self._evaluate_quality(query, all_chunks)
            logger.info(f"[DeepSearchRAG] hop {hop+1} quality={score:.2f}, total_chunks={len(all_chunks)}")

            if score >= QUALITY_OK:
                break

            # 质量不足：分解问题，取下一个子问题继续检索
            sub_queries = await self._decompose_query(query, all_chunks, hop)
            if not sub_queries or hop + 1 >= MAX_HOPS:
                break
            current_query = sub_queries[0]

        final_score = await self._evaluate_quality(query, all_chunks)
        return RetrievalResult(chunks=all_chunks[:top_k * 2], query=query, score=final_score)

    async def answer(
        self,
        query: str,
        paper_uuids: Optional[List[str]] = None,
        top_k: int = 8,
    ) -> Dict:
        retrieval = await self.retrieve(query, paper_uuids, top_k)

        if retrieval.is_empty():
            return {
                "answer": "未在论文中检索到相关内容，建议上传更多相关论文后重试。",
                "sources": [],
                "retrieval_attempts": MAX_HOPS,
                "quality_score": 0.0,
                "mode": "deepsearch",
            }

        # 生成初步答案
        draft = await self._generate_answer(query, retrieval)

        # 事实一致性验证
        consistency = await self._fact_check(draft, retrieval.chunks)
        logger.info(f"[DeepSearchRAG] fact_check score={consistency['overall_score']:.2f}")

        # 若事实验证分低，在答案末尾加提示
        answer_text = draft
        if consistency["overall_score"] < FACT_CHECK_OK and consistency["contradictions"]:
            contradictions = "; ".join(
                v["claim"] for v in consistency["contradictions"][:2]
            )
            answer_text += f"\n\n> **注意**：以下声明可能与论文内容存在出入，请核实：{contradictions}"

        sources = [
            {
                "chunk_id":    c.get("chunk_id", ""),
                "content":     c["content"][:300],
                "content_type": c.get("content_type", "text"),
                "page_num":    c.get("page_num"),
                "score":       round(c.get("score", 0.0), 4),
            }
            for c in retrieval.chunks
        ]

        return {
            "answer":             answer_text,
            "sources":            sources,
            "retrieval_attempts": MAX_HOPS,
            "quality_score":      retrieval.quality_score,
            "fact_check_score":   consistency["overall_score"],
            "mode":               "deepsearch",
        }

    # ── 问题分解 ──────────────────────────────────────────────────────
    async def _decompose_query(
        self, original: str, current_chunks: List[Dict], hop: int
    ) -> List[str]:
        """将原始问题分解为更具体的子问题，引导下一跳检索。"""
        context_hint = "\n".join(c["content"][:150] for c in current_chunks[:3])
        prompt = f"""你是一个学术检索专家。
原始问题：{original}
已检索到但不充分的内容摘要：
{context_hint}

已检索 {hop+1} 次，内容仍不足以完整回答。
请将原始问题分解为1-2个更具体、更聚焦的子问题，用于下一步精准检索。
输出 JSON 数组，每个元素是一个子问题字符串。只输出 JSON，不要其他文字。"""

        resp = await self._llm_invoke(
            [{"role": "user", "content": prompt}], temperature=0.2
        )
        try:
            m = re.search(r'\[.*?\]', resp, re.DOTALL)
            return json.loads(m.group()) if m else []
        except Exception:
            return []

    # ── 事实一致性验证（移植自 deepsearch.py）────────────────────────
    async def _fact_check(self, answer: str, sources: List[Dict]) -> Dict:
        claims = await self._extract_claims(answer)
        verifications = []
        for claim in claims[:5]:   # 最多验证 5 条，控制 LLM 调用量
            evidence = [s["content"] for s in sources[:3]]
            v = await self._verify_claim(claim, evidence)
            verifications.append(v)

        if not verifications:
            return {"overall_score": 1.0, "contradictions": []}

        supported = sum(1 for v in verifications if v.verdict == "SUPPORTED")
        contradicted = sum(1 for v in verifications if v.verdict == "CONTRADICTED")
        score = supported / len(verifications)

        return {
            "overall_score": score,
            "is_consistent": score >= FACT_CHECK_OK and contradicted == 0,
            "contradictions": [
                {"claim": v.claim, "confidence": v.confidence}
                for v in verifications if v.verdict == "CONTRADICTED"
            ],
        }

    async def _extract_claims(self, answer: str) -> List[str]:
        prompt = f"""将以下答案拆解为最小的原子事实声明（每条只含一个可验证事实）。
答案：{answer[:1500]}
输出 JSON 数组，每个元素是一个声明字符串。只输出 JSON。"""
        resp = await self._llm_invoke(
            [{"role": "user", "content": prompt}], temperature=0.1
        )
        try:
            m = re.search(r'\[.*?\]', resp, re.DOTALL)
            return json.loads(m.group()) if m else []
        except Exception:
            return []

    async def _verify_claim(self, claim: str, evidence: List[str]) -> ClaimVerification:
        evidence_text = "\n".join(f"[{i+1}] {e[:300]}" for i, e in enumerate(evidence))
        prompt = f"""判断以下声明是否被证据支持。
声明：{claim}
证据：
{evidence_text}
输出 JSON：{{"verdict":"SUPPORTED|CONTRADICTED|UNVERIFIED","confidence":0.0-1.0}}
只输出 JSON。"""
        resp = await self._llm_invoke(
            [{"role": "user", "content": prompt}], temperature=0.0
        )
        try:
            m = re.search(r'\{.*?\}', resp, re.DOTALL)
            d = json.loads(m.group()) if m else {}
            return ClaimVerification(
                claim=claim,
                verdict=d.get("verdict", "UNVERIFIED"),
                confidence=float(d.get("confidence", 0.5)),
            )
        except Exception:
            return ClaimVerification(claim=claim, verdict="UNVERIFIED", confidence=0.5)
