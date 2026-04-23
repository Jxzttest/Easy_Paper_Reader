#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
MemoryManager —— 四层智能分块记忆管理器

四层结构：
┌─────────────────────────────────────────────────────────────────┐
│ Layer 0: system        系统提示（角色定义、工具描述、安全策略）    永久 🔴 │
│ Layer 1: user_intent   用户当前任务意图、最新明确指令             永久 🔴 │
│ Layer 2: working       工作记忆（RAG结果、执行输出、论文摘要）    动态 🟡 │
│ Layer 3: history       历史对话（超限后自动压缩为摘要）           压缩 🟢 │
└─────────────────────────────────────────────────────────────────┘

Token 预算管理（默认配置）：
  - 总预算:    128,000 tokens（claude-sonnet 上下文窗口可用部分）
  - system:    固定保留，约 2,000
  - user_intent: 固定保留，约 1,000
  - working:   动态，最多 30,000
  - history:   剩余空间，超限触发压缩

压缩策略：
  - 历史对话超过 HISTORY_COMPRESS_THRESHOLD 轮时，
    取最旧的 COMPRESS_BATCH 轮调用 LLM 生成摘要，
    用一个 history_summary 块替换被压缩的消息。
"""

import uuid
from typing import Any, Dict, List, Optional

from server.utils.logger import logger

# ── 层级常量 ──────────────────────────────────────────────────────────────────
LAYER_SYSTEM = "system"
LAYER_USER_INTENT = "user_intent"
LAYER_WORKING = "working"
LAYER_HISTORY = "history"

LAYER_PRIORITY = {
    LAYER_SYSTEM: 0,
    LAYER_USER_INTENT: 1,
    LAYER_WORKING: 2,
    LAYER_HISTORY: 3,
}

# ── Token 预算（粗估：1 token ≈ 2 字符）──────────────────────────────────────
BUDGET_WORKING_MAX = 30_000      # working 层最大 token
HISTORY_COMPRESS_THRESHOLD = 12  # 超过多少轮（user+assistant 各算一轮）触发压缩
COMPRESS_BATCH = 6               # 每次压缩最旧的 N 轮


class MemoryManager:
    """
    四层记忆管理器。
    每个 session 对应一组 memory_blocks 记录（持久化到 SQLite）。
    提供 load / save / compress / build_messages 四个核心操作。
    """

    def __init__(self, session_id: str, paper_uuids: List[str] = None):
        self.session_id = session_id
        self.paper_uuids = paper_uuids or []

        # 运行时缓存：layer → List[block_dict]
        self._cache: Dict[str, List[Dict]] = {
            LAYER_SYSTEM: [],
            LAYER_USER_INTENT: [],
            LAYER_WORKING: [],
            LAYER_HISTORY: [],
        }
        self._loaded = False

    # ── 初始化加载 ────────────────────────────────────────────────────────────

    async def load(self) -> None:
        """从 SQLite 加载所有记忆块到内存缓存。"""
        from server.db.db_factory import DBFactory
        sqlite = DBFactory.get_sqlite()
        blocks = await sqlite.get_memory_blocks(self.session_id)

        self._cache = {LAYER_SYSTEM: [], LAYER_USER_INTENT: [], LAYER_WORKING: [], LAYER_HISTORY: []}
        for b in blocks:
            layer = b.get("layer", LAYER_HISTORY)
            if layer in self._cache:
                self._cache[layer].append(b)

        # 首次加载时注入系统提示
        if not self._cache[LAYER_SYSTEM]:
            await self._init_system_prompt()

        self._loaded = True
        logger.debug(
            f"[MemoryManager] session={self.session_id} loaded "
            f"sys={len(self._cache[LAYER_SYSTEM])} "
            f"intent={len(self._cache[LAYER_USER_INTENT])} "
            f"working={len(self._cache[LAYER_WORKING])} "
            f"history={len(self._cache[LAYER_HISTORY])}"
        )

    # ── 写入记忆 ──────────────────────────────────────────────────────────────

    async def set_system_prompt(self, content: str, block_id: str = None) -> str:
        """写入/更新系统提示（永久保留，通常只有一个块）。"""
        bid = block_id or f"sys_{self.session_id}"
        await self._upsert(bid, LAYER_SYSTEM, content, priority=0)
        return bid

    async def set_user_intent(self, content: str, block_id: str = None) -> str:
        """写入/更新用户意图（每轮对话更新）。"""
        bid = block_id or f"intent_{self.session_id}"
        await self._upsert(bid, LAYER_USER_INTENT, content, priority=1)
        return bid

    async def add_working_memory(
        self,
        content: str,
        key: str = None,
        metadata: Dict = None,
    ) -> str:
        """
        添加/更新工作记忆块（RAG 结果、Agent 输出、论文摘要等）。
        key 相同时覆盖旧块，key 为 None 时追加新块。
        自动检查 token 预算，超限时驱逐最旧的工作记忆。
        """
        bid = key or f"work_{uuid.uuid4().hex[:8]}"
        await self._upsert(bid, LAYER_WORKING, content, priority=2, metadata=metadata)
        await self._evict_working_if_needed()
        return bid

    async def add_history_turn(self, role: str, content: str) -> str:
        """
        添加一条历史对话记录。
        超过阈值时自动触发压缩。
        """
        bid = f"hist_{uuid.uuid4().hex[:8]}"
        meta = {"role": role}
        await self._upsert(bid, LAYER_HISTORY, content, priority=3, metadata=meta)
        self._cache[LAYER_HISTORY].append({
            "block_id": bid, "layer": LAYER_HISTORY, "priority": 3,
            "content": content, "metadata": meta,
        })
        # 检查是否需要压缩
        if len(self._cache[LAYER_HISTORY]) >= HISTORY_COMPRESS_THRESHOLD:
            await self._compress_history()
        return bid

    async def clear_working_memory(self) -> None:
        """清空工作记忆（新轮对话开始时可选调用）。"""
        from server.db.db_factory import DBFactory
        sqlite = DBFactory.get_sqlite()
        await sqlite.delete_memory_blocks_by_layer(self.session_id, LAYER_WORKING)
        self._cache[LAYER_WORKING] = []

    # ── 读取 ──────────────────────────────────────────────────────────────────

    def get_history_messages(self) -> List[Dict]:
        """返回 OpenAI messages 格式的历史对话列表（含摘要块）。"""
        messages = []
        for b in self._cache[LAYER_HISTORY]:
            role = b.get("metadata", {}).get("role", "user")
            # history_summary 块作为 system 消息插入
            if b.get("metadata", {}).get("is_summary"):
                messages.append({"role": "system", "content": f"[历史摘要] {b['content']}"})
            else:
                messages.append({"role": role, "content": b["content"]})
        return messages

    def get_working_context(self) -> str:
        """返回所有工作记忆内容的拼接文本，供注入 system prompt。"""
        parts = []
        for b in self._cache[LAYER_WORKING]:
            key = b.get("metadata", {}).get("key", "")
            prefix = f"[{key}] " if key else ""
            parts.append(f"{prefix}{b['content']}")
        return "\n\n".join(parts)

    def get_system_content(self) -> str:
        """返回系统提示内容（合并所有 system 块）。"""
        return "\n\n".join(b["content"] for b in self._cache[LAYER_SYSTEM])

    def get_user_intent_content(self) -> str:
        """返回用户意图内容。"""
        return "\n\n".join(b["content"] for b in self._cache[LAYER_USER_INTENT])

    # ── 压缩 ──────────────────────────────────────────────────────────────────

    async def _compress_history(self) -> None:
        """
        将最旧的 COMPRESS_BATCH 条历史压缩为摘要。
        被压缩的消息从 DB 删除，摘要作为新块插入。
        """
        to_compress = self._cache[LAYER_HISTORY][:COMPRESS_BATCH]
        if len(to_compress) < 2:
            return

        logger.info(
            f"[MemoryManager] compressing {len(to_compress)} history turns "
            f"for session={self.session_id}"
        )

        # 组装待压缩的对话文本
        turns_text = "\n".join(
            f"{'用户' if b.get('metadata', {}).get('role') == 'user' else '助手'}：{b['content']}"
            for b in to_compress
        )
        summary = await self._llm_summarize(turns_text)

        # 删除被压缩的块
        from server.db.db_factory import DBFactory
        sqlite = DBFactory.get_sqlite()
        for b in to_compress:
            await sqlite.delete_memory_block(b["block_id"])

        # 插入摘要块
        summary_id = f"summary_{uuid.uuid4().hex[:8]}"
        await self._upsert(
            summary_id, LAYER_HISTORY, summary, priority=3,
            metadata={"is_summary": True, "compressed_count": len(to_compress)},
        )

        # 更新缓存
        summary_block = {
            "block_id": summary_id, "layer": LAYER_HISTORY, "priority": 3,
            "content": summary, "metadata": {"is_summary": True},
        }
        self._cache[LAYER_HISTORY] = [summary_block] + self._cache[LAYER_HISTORY][COMPRESS_BATCH:]
        logger.info(f"[MemoryManager] compressed → summary block {summary_id}")

    async def _llm_summarize(self, turns_text: str) -> str:
        """调用 LLM 生成对话摘要。"""
        try:
            from server.model.llm_model.llm_function import LLMManager
            llm = LLMManager()
            resp = await llm.invoke(
                [
                    {
                        "role": "system",
                        "content": (
                            "你是一个对话摘要专家。请用简洁的中文对以下对话进行摘要，"
                            "保留关键信息（用户意图、重要结论、提到的论文/概念），"
                            "删除冗余内容。摘要不超过200字。"
                        ),
                    },
                    {"role": "user", "content": f"请摘要以下对话：\n\n{turns_text}"},
                ],
                temperature=0.1,
            )
            return resp.strip()
        except Exception as e:
            logger.warning(f"[MemoryManager] LLM summarize failed: {e}, using truncation")
            return f"[摘要（自动截断）] {turns_text[:500]}..."

    # ── 工作记忆驱逐 ──────────────────────────────────────────────────────────

    async def _evict_working_if_needed(self) -> None:
        """工作记忆超出 token 预算时，删除最旧的块。"""
        from server.db.db_factory import DBFactory
        sqlite = DBFactory.get_sqlite()
        total = await sqlite.count_memory_tokens(self.session_id, LAYER_WORKING)
        if total <= BUDGET_WORKING_MAX:
            return

        # 按 updated_at 升序（最旧的最先删）
        working = sorted(
            self._cache[LAYER_WORKING],
            key=lambda b: b.get("updated_at", ""),
        )
        while total > BUDGET_WORKING_MAX and working:
            oldest = working.pop(0)
            await sqlite.delete_memory_block(oldest["block_id"])
            total -= oldest.get("token_estimate", 0)
            logger.info(f"[MemoryManager] evicted working block {oldest['block_id']}")

        self._cache[LAYER_WORKING] = working

    # ── 内部写入 ──────────────────────────────────────────────────────────────

    async def _upsert(
        self,
        block_id: str,
        layer: str,
        content: str,
        priority: int = 2,
        metadata: Dict = None,
    ) -> None:
        from server.db.db_factory import DBFactory
        sqlite = DBFactory.get_sqlite()
        await sqlite.upsert_memory_block(
            block_id=block_id,
            session_id=self.session_id,
            layer=layer,
            content=content,
            priority=priority,
            metadata=metadata or {},
        )
        # 同步更新缓存
        block = {
            "block_id": block_id,
            "session_id": self.session_id,
            "layer": layer,
            "priority": priority,
            "content": content,
            "metadata": metadata or {},
            "token_estimate": len(content) // 2,
        }
        cache_list = self._cache.get(layer, [])
        existing = next((i for i, b in enumerate(cache_list) if b["block_id"] == block_id), None)
        if existing is not None:
            cache_list[existing] = block
        else:
            cache_list.append(block)
        self._cache[layer] = cache_list

    # ── 系统提示初始化 ────────────────────────────────────────────────────────

    async def _init_system_prompt(self) -> None:
        """首次创建 session 时，写入默认系统提示。"""
        papers_hint = ""
        if self.paper_uuids:
            papers_hint = f"\n当前关联论文（UUID）：{', '.join(self.paper_uuids)}"

        content = SYSTEM_PROMPT_TEMPLATE.format(papers_hint=papers_hint)
        await self.set_system_prompt(content)


# ── 系统提示模板 ──────────────────────────────────────────────────────────────
SYSTEM_PROMPT_TEMPLATE = """你是 Easy Paper Reader 的 AI 学术助手，专为科研人员设计。

## 角色定义
- 你是一位深度学习学术领域的专家助手
- 你能够解读论文内容、提炼核心观点、辅助学术写作
- 你会主动引用论文中的具体内容来支撑回答，而不是凭空生成

## 能力范围
- **论文理解**：解析研究问题、方法、实验、结论
- **智能问答**：基于论文内容精准回答，来源可溯
- **学术写作**：润色摘要、撰写段落、提炼创新点
- **翻译**：中英文学术互译，保留专业术语准确性
- **文献检索**：搜索同领域相关论文（通过后台任务）

## 行为准则
1. **诚实**：不确定时主动说明，不捏造引用或数据
2. **精准**：回答尽量具体，引用原文片段时注明位置
3. **简洁**：默认输出简洁，用户要求详细时再展开
4. **中文优先**：除非用户用英文提问，否则用中文回答{papers_hint}
"""
