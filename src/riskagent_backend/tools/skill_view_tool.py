"""
skill_view 工具 — 在 ReAct 循环中按需获取 Skill 完整内容.

设计约束 (RFC-005 需求六):
- plan 生成前注入 summary 列表 (name + summary), 约 0.5-1K tokens
- Orchestrator 在 ReAct 循环中按需调用 skill_view 获取完整 Skill 内容
- 纯读工具, 无副作用, 不需审批链 (遵循 ADR-004 零信任工具治理)
- owner=orchestrator
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from riskagent_backend.skills.skill_store import SkillStore

logger = logging.getLogger(__name__)

# 模块级 SkillStore 引用, 由 ProactiveBackEndWorkflow 初始化时注入
_skill_store: SkillStore | None = None


def set_skill_store(store: SkillStore) -> None:
    """注入 SkillStore 实例, 供 skill_view 工具使用.

    由 ProactiveBackEndWorkflow.__init__ 调用.
    """
    global _skill_store
    _skill_store = store


def get_skill_store() -> SkillStore | None:
    """获取当前注入的 SkillStore 实例 (测试用)."""
    return _skill_store


# 工具定义 (供 LLM 工具列表使用)
SKILL_VIEW_TOOL_DEFINITION: dict[str, Any] = {
    "name": "skill_view",
    "description": (
        "查看指定 Skill 的完整内容（steps, applicable_conditions, failure_boundary）。"
        "在 plan 生成前你已收到 Skill summary 列表, "
        "需要详细参考某个 Skill 时调用此工具。"
    ),
    "owner": "orchestrator",
    "input_schema": {
        "type": "object",
        "properties": {
            "skill_id": {
                "type": "string",
                "description": "Skill ID",
            },
            "skill_name": {
                "type": "string",
                "description": "Skill 名称（与 skill_id 二选一）",
            },
        },
    },
    "output": "完整 Skill 内容（JSON）",
}


def _run_async(coro: Any) -> Any:
    """在同步上下文中运行异步协程.

    tool_executor 的 handler 运行在 ThreadPoolExecutor 中,
    该线程无运行中的事件循环, 可安全使用 asyncio.run().
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is not None:
        # 极端情况: 主线程已有事件循环, 新建线程执行
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result()
    return asyncio.run(coro)


async def _fetch_skill(skill_id: str | None, skill_name: str | None) -> dict[str, Any] | None:
    """从 SkillStore 获取完整 Skill 内容."""
    if _skill_store is None:
        raise RuntimeError("SkillStore not initialized; call set_skill_store() first")

    if skill_id and isinstance(skill_id, str) and skill_id.strip():
        return await _skill_store.get(skill_id.strip())

    if skill_name and isinstance(skill_name, str) and skill_name.strip():
        all_skills = await _skill_store.list_all(status="active")
        for skill in all_skills:
            if str(skill.get("name") or "") == skill_name.strip():
                return skill
        return None

    return None


def skill_view_handler(params: dict[str, Any]) -> dict[str, Any]:
    """skill_view 工具执行函数.

    根据 skill_id 或 skill_name 从 SkillStore 获取完整 Skill 内容.

    Args:
        params: 包含 skill_id 或 skill_name 的参数字典

    Returns:
        包含完整 Skill 内容的字典

    Raises:
        ValueError: skill_id 和 skill_name 都未提供
        RuntimeError: SkillStore 未初始化
        KeyError: Skill 未找到
    """
    skill_id = params.get("skill_id")
    skill_name = params.get("skill_name")

    if (not isinstance(skill_id, str) or not skill_id.strip()) and (
        not isinstance(skill_name, str) or not skill_name.strip()
    ):
        raise ValueError("skill_id or skill_name required")

    skill = _run_async(_fetch_skill(
        skill_id if isinstance(skill_id, str) else None,
        skill_name if isinstance(skill_name, str) else None,
    ))

    if skill is None:
        raise KeyError(
            f"Skill not found: skill_id={skill_id!r}, skill_name={skill_name!r}"
        )

    # 返回完整 Skill 内容 (steps, applicable_conditions, failure_boundary, confidence 等)
    return {
        "skill_id": str(skill.get("skill_id") or ""),
        "name": str(skill.get("name") or ""),
        "summary": str(skill.get("summary") or ""),
        "tags": list(skill.get("tags") or []),
        "applicable_conditions": list(skill.get("applicable_conditions") or []),
        "steps": [dict(s) if isinstance(s, dict) else {} for s in (skill.get("steps") or [])],
        "failure_boundary": str(skill.get("failure_boundary") or ""),
        "confidence": float(skill.get("confidence", 0.0)),
        "status": str(skill.get("status") or ""),
        "usage_count": int(skill.get("usage_count", 0)),
        "success_rate": float(skill.get("success_rate", 0.0)),
    }
