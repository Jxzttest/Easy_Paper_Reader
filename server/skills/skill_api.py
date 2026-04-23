#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Skills API

GET  /skills/list       : 列出所有已注册的 skill 元信息
GET  /skills/{name}     : 获取单个 skill 详情（含 SKILL.md body）
POST /skills/reload     : 热重载（不重启服务，重新扫描 skills 目录）
POST /skills/{name}/run : 直接测试执行一个 skill（仅 python 类型支持）
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Optional

from server.skills.skill_registry import skill_registry
from server.utils.logger import logger

router = APIRouter(prefix="/skills")


@router.get("/list")
async def list_skills():
    """列出所有已注册的 skill，返回元信息列表。"""
    skill_registry.initialize()
    skills = skill_registry.list_skills()
    return JSONResponse(content={
        "skills": [s.to_dict() for s in skills],
        "total": len(skills),
    })


@router.get("/{name}")
async def get_skill(name: str):
    """获取单个 skill 详情，含 SKILL.md 内容。"""
    skill_registry.initialize()
    skill = skill_registry.get_skill(name)
    if not skill:
        return JSONResponse(status_code=404, content={"detail": f"skill '{name}' not found"})
    data = skill.to_dict()
    data["content"] = skill.raw_content   # 完整 SKILL.md body
    return JSONResponse(content=data)


@router.post("/reload")
async def reload_skills():
    """热重载 skills 目录，无需重启服务。"""
    skill_registry.reload()
    skills = skill_registry.list_skills()
    logger.info(f"[skill_api] reloaded, {len(skills)} skills")
    return JSONResponse(content={
        "status": "reloaded",
        "skills": [s.to_dict() for s in skills],
        "total": len(skills),
    })


class RunSkillRequest(BaseModel):
    task_desc: str
    paper_uuids: List[str] = []
    max_results: int = 5


@router.post("/{name}/run")
async def run_skill(name: str, req: RunSkillRequest):
    """
    直接测试执行一个 python 类型的 skill。
    仅用于开发测试，不会创建 Task 记录。
    """
    skill_registry.initialize()
    skill = skill_registry.get_skill(name)
    if not skill:
        return JSONResponse(status_code=404, content={"detail": f"skill '{name}' not found"})

    if skill.executor_type != "python":
        return JSONResponse(
            status_code=400,
            content={"detail": f"skill '{name}' is type '{skill.executor_type}', only python type supports direct run"}
        )

    try:
        import importlib.util
        executor_path = skill.skill_dir / "executor.py"
        spec = importlib.util.spec_from_file_location(f"skill_{name}", executor_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        result = await mod.execute(
            task_desc=req.task_desc,
            paper_uuids=req.paper_uuids,
            max_results=req.max_results,
        )

        if hasattr(result, "to_dict"):
            return JSONResponse(content=result.to_dict())
        return JSONResponse(content={"result": str(result)})

    except Exception as e:
        logger.error(f"[skill_api] run skill '{name}' failed: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"detail": str(e)})
