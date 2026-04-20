#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
SupervisorAgent —— 总 Agent

职责：
  1. 分析用户意图，识别任务类型
  2. 制定执行计划（plan），决定调用哪些子 Agent、以什么顺序
  3. 在子 Agent 执行结束后，判断是否需要重规划

意图 → Agent 路由表：
  qa          → RAGAgent → CheckAgent
  innovation  → RAGAgent → WritingAgent(innovation) → CheckAgent
  writing     → RAGAgent → WritingAgent(draft) → CheckAgent
  polish      → WritingAgent(polish) → CheckAgent
  translation → TranslationAgent → CheckAgent
  citation    → CitationAgent
  general     → WritingAgent(general)
"""

import json
from typing import Dict, List

from server.agent.base import AgentBase, AgentContext

# 意图 → 执行计划（Agent 序列）
INTENT_PLAN: Dict[str, List[str]] = {
    "qa":          ["rag_agent", "check_agent"],
    "innovation":  ["rag_agent", "writing_agent", "check_agent"],
    "writing":     ["rag_agent", "writing_agent", "check_agent"],
    "polish":      ["writing_agent", "check_agent"],
    "translation": ["translation_agent", "check_agent"],
    "citation":    ["citation_agent"],
    "general":     ["writing_agent"],
}

INTENT_DESCRIPTIONS = """
- qa:          用户提问，需要检索论文内容来回答（含创新点梳理、论文解读等）
- innovation:  梳理/分析论文创新点
- writing:     撰写新的学术内容（段落、摘要、章节）
- polish:      修改/润色已有文字
- translation: 翻译（中英互译）
- citation:    查找/下载引用文献
- general:     其他通用请求
"""


class SupervisorAgent(AgentBase):
    name = "supervisor_agent"
    description = "分析用户意图，制定任务执行计划"

    async def run(self, ctx: AgentContext, **kwargs) -> Dict:
        user_input = kwargs.get("user_input", "")
        intent, plan = await self._plan(ctx, user_input)
        ctx.shared_memory["intent"] = intent
        ctx.shared_memory["plan"] = plan
        return {
            "summary": f"intent={intent}, plan={plan}",
            "intent": intent,
            "plan": plan,
        }

    async def _plan(self, ctx: AgentContext, user_input: str):
        history = ctx.to_history_text(n=4)
        prompt = f"""你是一个学术论文助手的任务规划专家。
根据用户的输入，从以下意图类型中选择最匹配的一个，并返回 JSON。

意图类型：
{INTENT_DESCRIPTIONS}

对话历史（最近4轮）：
{history}

用户当前输入：
{user_input}

请输出以下格式的 JSON（不要输出任何其他内容）：
{{
  "intent": "<意图类型>",
  "reason": "<简短说明为何选择此意图>",
  "focus": "<用一句话概括用户最核心的需求>"
}}"""

        resp = await self._invoke(
            [{"role": "user", "content": prompt}],
            temperature=0.1,
        )
        try:
            data = json.loads(resp.strip())
        except json.JSONDecodeError:
            # 容错：从文本中提取 JSON
            import re
            m = re.search(r'\{.*\}', resp, re.DOTALL)
            data = json.loads(m.group()) if m else {}

        intent = data.get("intent", "general")
        if intent not in INTENT_PLAN:
            intent = "general"

        ctx.shared_memory["focus"] = data.get("focus", user_input)
        plan = INTENT_PLAN[intent]
        return intent, plan

    async def replan(self, ctx: AgentContext, check_result: Dict) -> List[str]:
        """
        CheckAgent 认为结果不满足要求时，Supervisor 重新规划剩余步骤。
        返回新的 Agent 序列（不含已完成的部分）。
        """
        issue = check_result.get("issue", "")
        intent = ctx.shared_memory.get("intent", "general")

        prompt = f"""当前任务意图：{intent}
CheckAgent 发现的问题：{issue}
已执行的步骤：{ctx.shared_memory.get("completed_agents", [])}

请决定接下来需要重新执行哪些步骤来修正问题。
从以下 Agent 中选择（可多选，按执行顺序排列）：
  rag_agent, writing_agent, translation_agent, check_agent

输出 JSON 数组，例如：["rag_agent", "writing_agent", "check_agent"]
只输出 JSON，不要有任何其他文字。"""

        resp = await self._invoke(
            [{"role": "user", "content": prompt}],
            temperature=0.1,
        )
        try:
            new_plan = json.loads(resp.strip())
            if isinstance(new_plan, list):
                return new_plan
        except Exception:
            pass
        return ["check_agent"]  # 兜底：只做检查
