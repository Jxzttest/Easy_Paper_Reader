#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
TranslationAgent —— 论文翻译（中英互译）

自动检测语言，保留学术术语，提供术语对照表。
"""

from typing import Dict
from server.agent.base import AgentBase, AgentContext


class TranslationAgent(AgentBase):
    name = "translation_agent"
    description = "中英互译，保留学术术语，提供术语对照"

    async def run(self, ctx: AgentContext, **kwargs) -> Dict:
        user_input = ctx.messages[-1]["content"] if ctx.messages else ""
        focus = ctx.shared_memory.get("focus", user_input)

        # 从用户消息中提取待翻译内容（简单策略：取引号内或最后一段）
        text_to_translate = self._extract_text(focus, user_input)

        messages = [
            {
                "role": "system",
                "content": (
                    "你是一位专业的学术翻译专家，擅长中英文学术论文互译。\n"
                    "翻译要求：\n"
                    "1. 自动检测源语言，翻译为另一种语言\n"
                    "2. 保持学术严谨性，专业术语翻译准确\n"
                    "3. 翻译结果后，附上重要术语对照表（格式：原文 → 译文）\n"
                    "4. 如有多义词，说明选择理由"
                ),
            },
            {
                "role": "user",
                "content": f"请翻译以下内容：\n\n{text_to_translate}",
            },
        ]

        result = await self._invoke(messages, temperature=0.2)
        ctx.shared_memory["translation_result"] = result

        return {
            "summary": result[:200],
            "result": result,
            "source_text": text_to_translate,
        }

    def _extract_text(self, focus: str, user_input: str) -> str:
        """从用户输入中提取待翻译的文本。"""
        import re
        # 优先提取引号内内容
        quoted = re.findall(r'["""](.*?)["""]', user_input, re.DOTALL)
        if quoted:
            return "\n".join(quoted)
        # 去除"翻译"等指令词后返回剩余内容
        cleaned = re.sub(r'^(请?翻译|translate|帮我翻译)[：:，,\s]*', '', user_input, flags=re.IGNORECASE).strip()
        return cleaned or focus
