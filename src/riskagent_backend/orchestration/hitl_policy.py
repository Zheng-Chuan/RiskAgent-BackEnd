"""HITL (Human-In-The-Loop) 审批策略.

统一收敛 HITL_AUTO_APPROVE 环境变量的解析逻辑,
避免多处重复实现导致语义漂移。

安全语义为 fail-safe: 未显式开启时默认要求人工审批。
"""

from __future__ import annotations

import os

_TRUTHY_VALUES = {"1", "true", "yes", "on"}


def hitl_auto_approve_enabled() -> bool:
    """是否自动审批副作用操作.

    仅当 HITL_AUTO_APPROVE 显式设置为 1/true/yes/on 时返回 True;
    未设置或其他取值一律视为关闭 (需要人工审批)。
    生产环境应保持关闭, 仅在本地演示/测试环境显式开启。
    """
    raw = os.getenv("HITL_AUTO_APPROVE")
    if raw is None:
        return False
    return raw.strip().lower() in _TRUTHY_VALUES


__all__ = ["hitl_auto_approve_enabled"]
