#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
SupervisorAgent —— 总 Agent

职责：
  1. 分析用户意图，识别任务类型
  2. 区分「即时对话」和「后台任务」（即时任务/定时任务）
  3. 制定执行计划（plan），决定调用哪些子 Agent、以什么顺序
  4. 在子 Agent 执行结束后，判断是否需要重规划

意图 → Agent 路由表（即时对话部分）：
  qa          → RAGAgent → CheckAgent
  innovation  → RAGAgent → WritingAgent(innovation) → CheckAgent
  writing     → RAGAgent → WritingAgent(draft) → CheckAgent
  polish      → WritingAgent(polish) → CheckAgent
  translation → TranslationAgent → CheckAgent
  citation    → CitationAgent
  general     → WritingAgent(general)

后台任务（不进入 Agent 流，转交 TaskManager/Scheduler）：
  task_once     → 即时后台任务（复杂、耗时，但不周期性）
  task_periodic → 定时/周期后台任务

判断为"任务"的核心标准（必须满足以下至少一条）：
  - 需要跨论文、外部检索或网络获取数据
  - 执行耗时较长，不适合在对话中同步等待
  - 具有周期性或定时触发的需求
  - 需要生成较大体量的内容（完整段落/章节）
"""

import json
from typing import Dict, List, Tuple

from server.agent.base import AgentBase, AgentContext

# ── 即时对话意图路由 ──────────────────────────────────────────────────────────
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
即时对话意图（直接在对话中同步回答，不需要用户确认）：
- qa:          用户提问，需要检索当前论文内容来回答（含创新点梳理、论文解读、数据解释等）
- innovation:  梳理/分析论文创新点
- writing:     撰写短小的学术内容片段（一两句话、简短段落）
- polish:      修改/润色已有文字
- translation: 翻译（中英互译）
- citation:    在当前数据库中查找/确认引用文献关系
- general:     其他简单通用请求（不涉及复杂计算或长时间等待）

后台任务意图（复杂、耗时或周期性，需要提示用户确认后再后台执行）：
- task_once:     即时后台任务——用户要求做某件复杂的事，但可以异步执行，不需要等结果
                 例：搜索同领域其他论文、根据某观点生成一个完整论文段落、分析多篇文献对比
- task_periodic: 定时任务——用户希望周期性自动执行某操作
                 例：每周收集最新相关论文、定期检查某作者的新论文

判断为后台任务的关键标志：
  ✓ 需要联网或跨越当前数据库的检索
  ✓ 需要生成体量较大的内容（完整段落、完整章节）
  ✓ 用到了"每天/每周/定期/自动/持续"等周期性关键词
  ✓ 执行时间预计超过30秒，用户明显不需要立刻看到结果
  ✗ 直接回答"这篇论文的..."、"数据库里哪篇..."等当前数据可回答的问题 → 不是任务
"""


class SupervisorAgent(AgentBase):
    name = "supervisor_agent"
    description = "分析用户意图，区分即时对话与后台任务，制定执行计划"

    async def run(self, ctx: AgentContext, **kwargs) -> Dict:
        user_input = kwargs.get("user_input", "")
        intent, plan, task_meta = await self._plan(ctx, user_input)
        ctx.shared_memory["intent"] = intent
        ctx.shared_memory["plan"] = plan
        ctx.shared_memory["task_meta"] = task_meta
        return {
            "summary": f"intent={intent}, plan={plan}",
            "intent": intent,
            "plan": plan,
            "task_meta": task_meta,
        }

    async def _plan(
        self,
        ctx: AgentContext,
        user_input: str,
    ) -> Tuple[str, List[str], Dict]:
        """
        返回 (intent, plan, task_meta)
        task_meta 仅在 intent 为 task_once / task_periodic 时有内容：
          {
            "task_type": "once" | "periodic",
            "task_desc": "...",       # 给用户看的任务描述
            "cron_expr": "...",       # 仅 periodic，如 "0 9 * * 0" 每周日9点
            "paper_uuids": [...],     # 关联的论文
          }
        """
        agent_task = f"""你是一个学术论文助手的任务规划专家。
根据用户输入，从以下意图类型中选择最匹配的一个，并返回 JSON。

意图类型及判断规则：
{INTENT_DESCRIPTIONS}

用户当前输入：
{user_input}

请输出以下格式的 JSON（不要输出任何其他内容）：
{{
  "intent": "<意图类型>",
  "reason": "<简短说明为何选择此意图>",
  "focus": "<用一句话概括用户最核心的需求>",
  "task_desc": "<仅当 intent 为 task_once 或 task_periodic 时填写：给用户展示的任务说明，如'搜索与本文同领域的最新5篇论文'。否则填空字符串>",
  "cron_expr": "<仅当 intent 为 task_periodic 时填写 cron 表达式（5字段），否则填空字符串。例：'0 9 * * 0' 表示每周日9点>"
}}"""

        resp = await self._invoke_with_context(
            ctx, agent_task=agent_task, temperature=0.1, n_history=4
        )
        try:
            data = json.loads(resp.strip())
        except json.JSONDecodeError:
            import re
            m = re.search(r'\{.*\}', resp, re.DOTALL)
            data = json.loads(m.group()) if m else {}

        intent = data.get("intent", "general")
        if intent not in {**INTENT_PLAN, "task_once": None, "task_periodic": None}:
            intent = "general"

        ctx.shared_memory["focus"] = data.get("focus", user_input)

        # 后台任务：不走 Agent 链，由 Orchestrator 发出 confirm 事件
        if intent in ("task_once", "task_periodic"):
            skill_name = await self._select_skill(user_input, data.get("task_desc", user_input))
            task_meta = {
                "task_type": "periodic" if intent == "task_periodic" else "once",
                "task_desc": data.get("task_desc", user_input),
                "cron_expr": data.get("cron_expr", ""),
                "paper_uuids": ctx.paper_uuids,
                "skill_name": skill_name,   # None 表示无匹配 skill，降级到 Orchestrator
            }
            return intent, [], task_meta

        plan = INTENT_PLAN.get(intent, INTENT_PLAN["general"])
        return intent, plan, {}

    async def _select_skill(self, user_input: str, task_desc: str) -> str | None:
        """
        从已注册的 skills 中选择最匹配的一个。
        返回 skill name（如 "academic-literature-search"）或 None（无匹配）。
        优先用触发词快速匹配，无匹配时调用 LLM 判断。
        """
        from server.skills.skill_registry import skill_registry
        skill_registry.initialize()
        skills = skill_registry.list_skills()
        if not skills:
            return None

        combined = (user_input + " " + task_desc).lower()

        # 快速触发词匹配
        for skill in skills:
            for trigger in skill.triggers:
                if trigger.lower() in combined:
                    return skill.name

        # 无触发词命中时，用 LLM 决策
        skill_list = "\n".join(f"- {s.name}: {s.description}" for s in skills)
        prompt = f"""你是一个技能路由专家。根据用户任务，从以下可用 skills 中选择最匹配的一个。
如果没有合适的 skill，输出 null。

可用 skills：
{skill_list}

用户任务：{task_desc}

只输出 skill 的 name 字符串或 null，不要任何其他内容。"""
        resp = await self._invoke([{"role": "user", "content": prompt}], temperature=0.1)
        resp = resp.strip().strip('"').strip("'")
        if resp.lower() in ("null", "none", "", "无"):
            return None
        # 验证返回的 name 确实存在
        skill_names = {s.name for s in skills}
        return resp if resp in skill_names else None

    async def replan(self, ctx: AgentContext, check_result: Dict) -> List[str]:
        """
        CheckAgent 认为结果不满足要求时，Supervisor 重新规划剩余步骤。
        返回新的 Agent 序列（不含已完成的部分）。
        """
        issue = check_result.get("issue", "")
        intent = ctx.shared_memory.get("intent", "general")

        agent_task = f"""当前任务意图：{intent}
CheckAgent 发现的问题：{issue}
已执行的步骤：{ctx.shared_memory.get("completed_agents", [])}

请决定接下来需要重新执行哪些步骤来修正问题。
从以下 Agent 中选择（可多选，按执行顺序排列）：
  rag_agent, writing_agent, translation_agent, check_agent

输出 JSON 数组，例如：["rag_agent", "writing_agent", "check_agent"]
只输出 JSON，不要有任何其他文字。"""

        resp = await self._invoke_with_context(
            ctx, agent_task=agent_task, temperature=0.1, n_history=2
        )
        try:
            new_plan = json.loads(resp.strip())
            if isinstance(new_plan, list):
                return new_plan
        except Exception:
            pass
        return ["check_agent"]
