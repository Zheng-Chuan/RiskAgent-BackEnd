"""后台任务管理工具.

asyncio.create_task / asyncio.ensure_future 创建的 Task 若未被强引用,
可能被 GC 回收 (官方文档明确警告), 导致后台工作静默丢失且异常无人收集。
本模块提供统一的引用保持 + 异常日志收集机制。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Coroutine

logger = logging.getLogger(__name__)

# 全局强引用集合: 保存所有进行中的后台任务, 完成后由 done_callback 移除
_BACKGROUND_TASKS: set[asyncio.Task] = set()


def _on_background_task_done(task: asyncio.Task) -> None:
    """后台任务完成回调: 移除强引用并记录未捕获异常."""
    _BACKGROUND_TASKS.discard(task)
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        logger.exception(
            "后台任务 %s 执行失败",
            task.get_name(),
            exc_info=exc,
        )


def spawn_background_task(coro: Coroutine[Any, Any, Any], *, name: str | None = None) -> asyncio.Task:
    """创建后台任务并保持强引用, 防止被 GC 回收.

    Args:
        coro: 要后台执行的协程
        name: 任务名称 (用于日志定位)

    Returns:
        创建的 Task (已在内部集合中保持强引用)
    """
    task = asyncio.create_task(coro, name=name)
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_on_background_task_done)
    return task


def pending_background_task_count() -> int:
    """当前进行中的后台任务数量 (用于测试和监控)."""
    return len(_BACKGROUND_TASKS)


__all__ = ["spawn_background_task", "pending_background_task_count"]
