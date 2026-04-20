#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
CheckAgent —— 结果质量校验

对上一个 Agent 的输出进行评估：
  - 是否回答了用户的核心问题
  - 是否存在明显错误或幻觉
  - 是否需要重新执行

返回：
  passed: bool       — 是否通过
  score:  0.0~1.0    — 质量分
  issue:  str        — 问题描述（passed=False 时）
  suggestion: str    — 改进建议
"""

import json
import re
from typing import Dict
from server.agent.base import AgentBase, AgentContext


class CheckAgent(AgentBase):
    name = "check_agent"
    description = "评估上一步执行结果的质量，决定是否需要重做"

    async def run(self, ctx: AgentContext, **kwargs) -> Dict:
        focus = ctx.shared_memory.get("focus", "")
        completed = ctx.shared_memory.get("completed_agents", [])

        # 取最新的执行结果（优先 writing > rag > translation）
        latest_result = (
            ctx.shared_memory.get("writing_result")
            or ctx.shared_memory.get("translation_result")
            or ctx.shared_memory.get("rag_answer")
            or ""
        )

        if not latest_result:
            return {
                "summary": "无内容可检查",
                "passed": True,
                "score": 1.0,
                "issue": "",
                "suggestion": "",
            }

        messages = [
            {
                "role": "system",
                "content": (
                    "你是一个严格的学术内容质量评审专家。"
                    "你的任务是评估 AI 助手的回答是否满足用户需求。"
                ),
            },
            {
                "role": "user",
                "content": f"""请评估以下 AI 回答的质量。

用户核心需求：{focus}

AI 回答：
{latest_result[:2000]}

请从以下维度评估，输出 JSON（不要输出其他内容）：
{{
  "passed": true/false,
  "score": 0.0到1.0之间的小数,
  "issue": "若 passed=false，描述主要问题；若 passed=true，填空字符串",
  "suggestion": "改进建议（1-2句话）"
}}

评估标准：
- score >= 0.75 时 passed=true
- 是否准确回答了用户的核心问题
- 内容是否有明显事实错误或逻辑漏洞
- 学术表达是否规范""",
            },
        ]

        resp = await self._invoke(messages, temperature=0.1)

        try:
            m = re.search(r'\{.*\}', resp, re.DOTALL)
            data = json.loads(m.group()) if m else {}
        except Exception:
            data = {}

        passed = data.get("passed", True)
        score = float(data.get("score", 0.8))
        issue = data.get("issue", "")
        suggestion = data.get("suggestion", "")

        ctx.shared_memory["check_result"] = {
            "passed": passed,
            "score": score,
            "issue": issue,
            "suggestion": suggestion,
        }

        return {
            "summary": f"passed={passed}, score={score:.2f}",
            "passed": passed,
            "score": score,
            "issue": issue,
            "suggestion": suggestion,
        }
