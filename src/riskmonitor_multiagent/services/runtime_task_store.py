"""
REST BFF 运行时任务注册表.

为浏览器轮询提供最小任务状态快照.
"""

from __future__ import annotations

import asyncio
import copy
import logging
import time
from typing import Any

logger = logging.getLogger(__name__)


def _now_ms() -> int:
    return int(time.time() * 1000)


def _normalize_task_status(status: Any) -> str:
    raw = str(status or "pending").strip().lower()
    if raw in {"pending", "running", "completed", "failed", "cancelled"}:
        return raw
    if raw == "stopped":
        return "cancelled"
    if raw in {"blocked", "pending_approval"}:
        return "failed"
    return "pending"


def _normalize_step_status(status: Any) -> str:
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


def _build_step_title(
    *,
    step_id: str,
    kind: Any,
    target_agent: Any,
    tool_name: Any,
) -> str:
    kind_text = str(kind or "").strip()
    target_text = str(target_agent or "").strip()
    tool_text = str(tool_name or "").strip()
    if kind_text == "delegate" and target_text:
        return f"delegate {target_text}"
    if kind_text == "tool_call" and tool_text:
        return f"tool {tool_text}"
    if kind_text == "finalize":
        return "finalize result"
    if kind_text == "stop":
        return "stop workflow"
    if kind_text:
        return f"{kind_text} {target_text}".strip()
    return step_id or "unknown_step"


def _extract_error_message(result: dict[str, Any] | None) -> str | None:
    if not isinstance(result, dict):
        return None
    errors = result.get("errors")
    if isinstance(errors, list):
        for item in errors:
            if isinstance(item, str) and item.strip():
                return item.strip()
    error_payload = result.get("error")
    if isinstance(error_payload, dict):
        message = error_payload.get("message")
        if isinstance(message, str) and message.strip():
            return message.strip()
    if isinstance(error_payload, str) and error_payload.strip():
        return error_payload.strip()
    return None


class RuntimeTaskStore:
    """进程内最小运行时任务注册表."""

    def __init__(self) -> None:
        self._tasks: dict[str, dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    async def create_task(
        self,
        *,
        task_id: str,
        session_id: str,
        description: str,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        created_at = _now_ms()
        record = {
            "task_id": task_id,
            "session_id": session_id,
            "run_id": run_id or task_id,
            "title": description[:48] or "untitled_task",
            "description": description,
            "status": "pending",
            "created_at": created_at,
            "updated_at": created_at,
            "steps": [],
            "result": None,
            "error": None,
            "current_agent_id": None,
            "execution_task": None,
        }
        async with self._lock:
            self._tasks[task_id] = record
        return copy.deepcopy(record)

    async def attach_execution_task(
        self,
        *,
        task_id: str,
        execution_task: asyncio.Task[Any],
    ) -> None:
        async with self._lock:
            record = self._tasks.get(task_id)
            if record is None:
                return
            record["execution_task"] = execution_task
            record["updated_at"] = _now_ms()

    async def clear_execution_task(self, *, task_id: str) -> None:
        async with self._lock:
            record = self._tasks.get(task_id)
            if record is None:
                return
            record["execution_task"] = None
            record["updated_at"] = _now_ms()

    async def mark_running(self, *, task_id: str, run_id: str | None = None) -> None:
        async with self._lock:
            record = self._tasks.get(task_id)
            if record is None:
                return
            record["status"] = "running"
            if isinstance(run_id, str) and run_id.strip():
                record["run_id"] = run_id.strip()
            record["updated_at"] = _now_ms()

    async def set_current_agent(self, *, task_id: str, agent_id: str | None) -> None:
        async with self._lock:
            record = self._tasks.get(task_id)
            if record is None:
                return
            record["current_agent_id"] = agent_id.strip() if isinstance(agent_id, str) and agent_id.strip() else None
            record["updated_at"] = _now_ms()

    async def mark_step_started(
        self,
        *,
        task_id: str,
        node: dict[str, Any],
    ) -> None:
        async with self._lock:
            record = self._tasks.get(task_id)
            if record is None:
                return
            step = self._upsert_step(
                record=record,
                step_id=str(node.get("step_id") or ""),
                title=_build_step_title(
                    step_id=str(node.get("step_id") or ""),
                    kind=node.get("kind"),
                    target_agent=node.get("target_agent"),
                    tool_name=node.get("tool_name"),
                ),
            )
            step["status"] = "running"
            record["status"] = "running"
            record["current_agent_id"] = (
                str(node.get("target_agent")).strip()
                if isinstance(node.get("target_agent"), str) and str(node.get("target_agent")).strip()
                else record.get("current_agent_id")
            )
            record["updated_at"] = _now_ms()

    async def mark_step_completed(
        self,
        *,
        task_id: str,
        node: dict[str, Any],
        trace_entry: dict[str, Any],
        node_result: dict[str, Any],
    ) -> None:
        async with self._lock:
            record = self._tasks.get(task_id)
            if record is None:
                return
            step = self._upsert_step(
                record=record,
                step_id=str(trace_entry.get("step_id") or node.get("step_id") or ""),
                title=_build_step_title(
                    step_id=str(trace_entry.get("step_id") or node.get("step_id") or ""),
                    kind=trace_entry.get("kind") or node.get("kind"),
                    target_agent=trace_entry.get("target_agent") or node.get("target_agent"),
                    tool_name=trace_entry.get("tool_name") or node.get("tool_name"),
                ),
            )
            step["status"] = _normalize_step_status(node_result.get("status"))
            if step["status"] == "failed":
                record["status"] = "failed"
            elif record.get("status") != "failed":
                record["status"] = "running"
            record["current_agent_id"] = None
            record["updated_at"] = _now_ms()

    async def finalize_task(
        self,
        *,
        task_id: str,
        result: dict[str, Any],
    ) -> None:
        async with self._lock:
            record = self._tasks.get(task_id)
            if record is None:
                return
            record["run_id"] = str(result.get("run_id") or record.get("run_id") or task_id)
            record["status"] = _normalize_task_status(result.get("status"))
            record["current_agent_id"] = None
            record["result"] = result.get("final_output") if isinstance(result.get("final_output"), dict) else None
            record["error"] = _extract_error_message(result)
            self._replace_steps_from_trace(record=record, result=result)
            record["updated_at"] = _now_ms()

    async def fail_task(
        self,
        *,
        task_id: str,
        error_message: str,
        result: dict[str, Any] | None = None,
    ) -> None:
        async with self._lock:
            record = self._tasks.get(task_id)
            if record is None:
                return
            record["status"] = "failed"
            record["error"] = error_message
            record["current_agent_id"] = None
            if isinstance(result, dict):
                record["result"] = result.get("final_output") if isinstance(result.get("final_output"), dict) else record.get("result")
                self._replace_steps_from_trace(record=record, result=result)
            record["updated_at"] = _now_ms()

    async def get_task(self, *, task_id: str) -> dict[str, Any] | None:
        async with self._lock:
            record = self._tasks.get(task_id)
            return self._clone_record(record) if isinstance(record, dict) else None

    async def get_active_task(self) -> dict[str, Any] | None:
        async with self._lock:
            active = [
                record
                for record in self._tasks.values()
                if record.get("status") in {"pending", "running"}
            ]
            if not active:
                return None
            active.sort(key=lambda item: int(item.get("updated_at") or 0), reverse=True)
            return self._clone_record(active[0])

    def _replace_steps_from_trace(self, *, record: dict[str, Any], result: dict[str, Any]) -> None:
        execution = result.get("task_graph_execution") if isinstance(result.get("task_graph_execution"), dict) else {}
        trace = execution.get("trace") if isinstance(execution.get("trace"), list) else []
        if not trace:
            return
        mapped_steps: list[dict[str, Any]] = []
        for item in trace:
            if not isinstance(item, dict):
                continue
            step_id = str(item.get("step_id") or "")
            mapped_steps.append(
                {
                    "id": step_id,
                    "title": _build_step_title(
                        step_id=step_id,
                        kind=item.get("kind"),
                        target_agent=item.get("target_agent"),
                        tool_name=item.get("tool_name"),
                    ),
                    "status": _normalize_step_status(item.get("status")),
                }
            )
        if mapped_steps:
            record["steps"] = mapped_steps

    def _upsert_step(
        self,
        *,
        record: dict[str, Any],
        step_id: str,
        title: str,
    ) -> dict[str, Any]:
        steps = record.setdefault("steps", [])
        for step in steps:
            if isinstance(step, dict) and step.get("id") == step_id:
                if title:
                    step["title"] = title
                return step
        step = {
            "id": step_id or f"step_{len(steps) + 1}",
            "title": title or step_id or "unknown_step",
            "status": "pending",
        }
        steps.append(step)
        return step

    def _clone_record(self, record: dict[str, Any]) -> dict[str, Any]:
        cloned = {
            key: value
            for key, value in record.items()
            if key != "execution_task"
        }
        return copy.deepcopy(cloned)


_runtime_task_store: RuntimeTaskStore | None = None


def get_runtime_task_store() -> RuntimeTaskStore:
    global _runtime_task_store
    if _runtime_task_store is None:
        _runtime_task_store = RuntimeTaskStore()
    return _runtime_task_store


__all__ = ["RuntimeTaskStore", "get_runtime_task_store"]
