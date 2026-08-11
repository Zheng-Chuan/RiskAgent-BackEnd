"""background_tasks 单元测试: 验证引用保持与异常收集."""

from __future__ import annotations

import asyncio
import logging

import pytest

from riskagent_backend.utils.background_tasks import (
    pending_background_task_count,
    spawn_background_task,
)


async def test_spawn_keeps_reference_until_done() -> None:
    """任务完成后应从强引用集合中移除."""
    started = asyncio.Event()
    release = asyncio.Event()

    async def work() -> str:
        started.set()
        await release.wait()
        return "done"

    before = pending_background_task_count()
    task = spawn_background_task(work(), name="test-bg-task")
    assert pending_background_task_count() == before + 1

    await started.wait()
    release.set()
    await task
    # done_callback 在任务完成后调度, 让出一次事件循环使其执行
    await asyncio.sleep(0)
    assert pending_background_task_count() == before


async def test_spawn_collects_exception_without_raising(caplog: pytest.LogCaptureFixture) -> None:
    """后台任务抛异常时不应传播, 但必须记录日志 (不再静默丢失)."""

    async def failing() -> None:
        raise RuntimeError("persist failed")

    with caplog.at_level(logging.ERROR, logger="riskagent_backend.utils.background_tasks"):
        task = spawn_background_task(failing(), name="test-bg-failing")
        await asyncio.gather(task, return_exceptions=True)
        await asyncio.sleep(0)

    assert any("persist failed" in record.message or "test-bg-failing" in record.message for record in caplog.records)
