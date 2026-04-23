#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
SkillRegistry —— 本地 Skill 插件注册中心

扫描 server/skills/ 下的所有子目录，读取 SKILL.md 的 YAML frontmatter，
将其作为可用 skill 的元信息缓存，供 SupervisorAgent 在规划任务时注入 prompt。

Skill 目录结构（约定）：
  server/skills/
  └── <skill-name>/
      ├── SKILL.md        必须，含 YAML frontmatter（name/description/triggers/executor）
      └── executor.py     可选，Python 执行入口（直接调用，不经 LLM Agent）

SKILL.md frontmatter 字段：
  name:        技能唯一标识（建议与目录名一致）
  description: 一句话描述功能（供 LLM 路由时判断）
  triggers:    触发关键词列表（辅助路由决策）
  executor:    执行方式 python | llm（默认 llm）
               python = 调用同目录的 executor.py 中的 execute() 函数
               llm    = 将 SKILL.md 内容注入 prompt，由 LLM Agent 执行
"""

import os
import re
from pathlib import Path
from typing import Dict, List, Optional

from server.utils.logger import logger

# skills 根目录（相对于本文件所在位置）
_SKILLS_ROOT = Path(__file__).parent


class SkillInfo:
    """单个 skill 的元信息。"""

    def __init__(
        self,
        name: str,
        description: str,
        triggers: List[str],
        executor_type: str,       # "python" | "llm"
        skill_dir: Path,
        raw_content: str,         # SKILL.md 完整内容（body 部分），供 LLM 使用
    ):
        self.name = name
        self.description = description
        self.triggers = triggers
        self.executor_type = executor_type
        self.skill_dir = skill_dir
        self.raw_content = raw_content

    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "description": self.description,
            "triggers": self.triggers,
            "executor_type": self.executor_type,
        }

    def __repr__(self):
        return f"<Skill name={self.name} executor={self.executor_type}>"


class SkillRegistry:
    """
    全局 Skill 注册中心（单例）。
    启动时自动扫描，也可调用 reload() 热重载。
    """

    _instance: Optional["SkillRegistry"] = None

    def __new__(cls) -> "SkillRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._loaded = False
        return cls._instance

    def initialize(self):
        """在 FastAPI lifespan 中调用，完成首次扫描。"""
        if self._loaded:
            return
        self._skills: Dict[str, SkillInfo] = {}
        self._scan()
        self._loaded = True

    def reload(self):
        """热重载（不重启服务的情况下刷新 skill 列表）。"""
        self._skills = {}
        self._scan()
        logger.info(f"[SkillRegistry] reloaded, {len(self._skills)} skills")

    # ── 查询接口 ──────────────────────────────────────────────────────────────

    def list_skills(self) -> List[SkillInfo]:
        self._ensure_loaded()
        return list(self._skills.values())

    def get_skill(self, name: str) -> Optional[SkillInfo]:
        self._ensure_loaded()
        return self._skills.get(name)

    def skills_prompt_block(self) -> str:
        """
        返回可直接注入 Supervisor prompt 的 skill 列表文本。
        格式：每行 `- <name>: <description>（触发词：...）`
        """
        self._ensure_loaded()
        if not self._skills:
            return "（暂无可用 skill）"
        lines = []
        for s in self._skills.values():
            trigger_hint = f"（触发词：{', '.join(s.triggers[:4])}）" if s.triggers else ""
            lines.append(f"- {s.name}: {s.description}{trigger_hint}")
        return "\n".join(lines)

    # ── 内部扫描 ──────────────────────────────────────────────────────────────

    def _scan(self):
        for item in _SKILLS_ROOT.iterdir():
            if not item.is_dir():
                continue
            skill_md = item / "SKILL.md"
            if not skill_md.exists():
                continue
            try:
                skill = _parse_skill_md(skill_md, item)
                self._skills[skill.name] = skill
                logger.info(f"[SkillRegistry] loaded skill: {skill.name} ({skill.executor_type})")
            except Exception as e:
                logger.warning(f"[SkillRegistry] failed to parse {skill_md}: {e}")

        logger.info(f"[SkillRegistry] total {len(self._skills)} skills available")

    def _ensure_loaded(self):
        if not self._loaded:
            self._skills = {}
            self._scan()
            self._loaded = True


# ── 解析 SKILL.md ────────────────────────────────────────────────────────────

def _parse_skill_md(skill_md: Path, skill_dir: Path) -> SkillInfo:
    raw = skill_md.read_text(encoding="utf-8")

    # 解析 YAML frontmatter（--- 块）
    frontmatter: Dict = {}
    body = raw
    if raw.startswith("---"):
        parts = raw.split("---", 2)
        if len(parts) >= 3:
            import yaml
            try:
                frontmatter = yaml.safe_load(parts[1]) or {}
            except Exception:
                frontmatter = _parse_frontmatter_simple(parts[1])
            body = parts[2].strip()

    name = frontmatter.get("name") or skill_dir.name
    raw_desc = frontmatter.get("description") or ""
    # description 字段可能是 "# Title — 副标题" 格式，提取纯文字
    description = re.sub(r"^#\s*", "", str(raw_desc)).split("—")[0].strip()

    triggers = frontmatter.get("triggers") or []
    if isinstance(triggers, str):
        triggers = [t.strip() for t in triggers.split(",") if t.strip()]

    executor_type = str(frontmatter.get("executor", "llm")).lower()
    # 自动探测：如果存在 executor.py，默认 python 模式
    if executor_type == "llm" and (skill_dir / "executor.py").exists():
        executor_type = "python"

    return SkillInfo(
        name=name,
        description=description,
        triggers=triggers,
        executor_type=executor_type,
        skill_dir=skill_dir,
        raw_content=body,
    )


def _parse_frontmatter_simple(text: str) -> Dict:
    """yaml 未安装时的简单降级解析（key: value 格式）。"""
    result = {}
    for line in text.splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            result[k.strip()] = v.strip()
    return result


# ── 全局单例 ──────────────────────────────────────────────────────────────────
skill_registry = SkillRegistry()
