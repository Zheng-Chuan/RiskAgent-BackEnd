"""
任务/步骤状态归一化与时间戳工具 (services 层公共模块).

状态映射是业务核心规则 (stopped→cancelled, blocked→failed 等),
必须单一归属, 禁止在 rest_bff_service / runtime_task_store 等处各自复制.
"""

from __future__ import annotations

import time
from typing import Any


def now_ms() -> int:
    """当前毫秒时间戳."""
    return int(time.time() * 1000)


def normalize_task_status(status: Any) -> str:
    """任务状态归一化到 {pending, running, completed, failed, cancelled}."""
    raw = str(status or "pending").strip().lower()
    if raw in {"pending", "running", "completed", "failed", "cancelled"}:
        return raw
    if raw == "stopped":
        return "cancelled"
    if raw in {"blocked", "pending_approval"}:
        return "failed"
    return "pending"


def normalize_step_status(status: Any) -> str:
    """步骤状态归一化到 {pending, running, completed, failed, cancelled}."""
    raw = str(status or "pending").strip().lower()
    if raw in {"pending", "running", "completed", "failed", "cancelled"}:
        return raw
    if raw == "stopped":
        return "cancelled"
    if raw == "skipped":
        return "cancelled"
    if raw == "blocked":
        return "failed"
    return "pending"
