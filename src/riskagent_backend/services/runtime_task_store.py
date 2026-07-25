"""
REST BFF 运行时任务注册表.

为浏览器轮询和 TaskGraph 实时渲染提供最小任务状态快照.
"""

from __future__ import annotations

import asyncio
import copy
import logging
import time
from typing import Any

from riskagent_backend.contracts.task_graph import normalize_task_graph

logger = logging.getLogger(__name__)

_GRAPH_STATUSES = {
    "pending",
    "ready",
    "running",
    "completed",
    "failed",
    "blocked",
    "skipped",
}


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


def _normalize_graph_status(status: Any) -> str:
    raw = str(status or "pending").strip().lower()
    if raw in _GRAPH_STATUSES:
        return raw
    if raw == "cancelled":
        return "skipped"
    if raw == "stopped":
        return "blocked"
    if raw in {"pending_approval"}:
        return "blocked"
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


def _build_trace_map(execution_state: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    trace_items = execution_state.get("trace") if isinstance(execution_state, dict) else None
    if not isinstance(trace_items, list):
        return {}
    trace_map: dict[str, dict[str, Any]] = {}
    for item in trace_items:
        if not isinstance(item, dict):
            continue
        step_id = str(item.get("step_id") or "").strip()
        if not step_id:
            continue
        trace_map[step_id] = dict(item)
    return trace_map


def _derive_edge_status(*, source_status: str, target_status: str) -> str:
    if target_status in {"failed", "blocked", "skipped"}:
        return target_status
    if target_status == "completed":
        return "completed"
    if target_status == "running":
        return "running"
    if target_status == "ready":
        return "ready"
    if source_status == "completed":
        return "ready"
    if source_status == "running":
        return "running"
    return "pending"


def _build_graph_summary(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "nodeCount": len(nodes),
        "edgeCount": len(edges),
        "completedCount": sum(1 for node in nodes if node.get("status") == "completed"),
        "runningCount": sum(1 for node in nodes if node.get("status") == "running"),
        "failedCount": sum(1 for node in nodes if node.get("status") == "failed"),
        "blockedCount": sum(1 for node in nodes if node.get("status") == "blocked"),
    }


def build_empty_task_graph_snapshot(
    *,
    task_id: str,
    session_id: str | None,
    task_status: str,
    updated_at: int | None = None,
) -> dict[str, Any]:
    snapshot_updated_at = int(updated_at or _now_ms())
    return {
        "task_id": task_id,
        "session_id": session_id,
        "status": _normalize_task_status(task_status),
        "schema_version": "task_graph.v1",
        "nodes": [],
        "edges": [],
        "summary": _build_graph_summary([], []),
        "updated_at": snapshot_updated_at,
    }


def build_task_graph_snapshot(
    *,
    task_id: str,
    session_id: str | None,
    task_status: str,
    task_graph: dict[str, Any],
    execution_state: dict[str, Any] | None = None,
    updated_at: int | None = None,
) -> dict[str, Any]:
    normalized_graph = normalize_task_graph(
        task_graph,
        plan_steps=task_graph.get("plan_steps") if isinstance(task_graph, dict) and isinstance(task_graph.get("plan_steps"), list) else [],
    )
    trace_map = _build_trace_map(execution_state)
    nodes: list[dict[str, Any]] = []
    node_status_map: dict[str, str] = {}

    for raw_node in normalized_graph.get("nodes", []):
        if not isinstance(raw_node, dict):
            continue
        node = copy.deepcopy(raw_node)
        step_id = str(node.get("step_id") or "")
        trace_entry = trace_map.get(step_id, {})
        status = _normalize_graph_status(trace_entry.get("status") or node.get("status"))
        started_at = trace_entry.get("started_at_ms")
        finished_at = trace_entry.get("finished_at_ms")
        started_at_ms = int(started_at) if isinstance(started_at, (int, float)) and int(started_at) > 0 else None
        finished_at_ms = int(finished_at) if isinstance(finished_at, (int, float)) and int(finished_at) > 0 else None
        duration_ms = finished_at_ms - started_at_ms if started_at_ms and finished_at_ms and finished_at_ms >= started_at_ms else None
        label = _build_step_title(
            step_id=step_id,
            kind=node.get("kind"),
            target_agent=trace_entry.get("target_agent") or node.get("target_agent"),
            tool_name=trace_entry.get("tool_name") or node.get("tool_name"),
        )
        node["status"] = status
        if started_at_ms is not None:
            node["started_at_ms"] = started_at_ms
        if finished_at_ms is not None:
            node["finished_at_ms"] = finished_at_ms
        if duration_ms is not None:
            node["duration_ms"] = duration_ms
        node_status_map[step_id] = status
        nodes.append(
            {
                "id": step_id,
                "label": label,
                "kind": str(node.get("kind") or "analyze"),
                "status": status,
                "parentId": str(node.get("parent_id") or "") or None,
                "targetAgent": str(trace_entry.get("target_agent") or node.get("target_agent") or "") or None,
                "toolName": str(trace_entry.get("tool_name") or node.get("tool_name") or "") or None,
                "reason": str(node.get("reason") or "") or None,
                "instruction": str(node.get("instruction") or "") or None,
                "condition": str(node.get("condition") or "") or None,
                "startedAt": started_at_ms,
                "finishedAt": finished_at_ms,
                "durationMs": duration_ms,
                "data": node,
            }
        )

    edges: list[dict[str, Any]] = []
    for raw_edge in normalized_graph.get("edges", []):
        if not isinstance(raw_edge, dict):
            continue
        source = str(raw_edge.get("from_step_id") or "").strip()
        target = str(raw_edge.get("to_step_id") or "").strip()
        if not source or not target:
            continue
        edge_status = _derive_edge_status(
            source_status=node_status_map.get(source, "pending"),
            target_status=node_status_map.get(target, "pending"),
        )
        edge_data = copy.deepcopy(raw_edge)
        edge_data["status"] = edge_status
        edges.append(
            {
                "id": f"{source}__{target}",
                "source": source,
                "target": target,
                "status": edge_status,
                "condition": str(raw_edge.get("condition") or "always"),
                "data": edge_data,
            }
        )

    snapshot_updated_at = int(updated_at or _now_ms())
    return {
        "task_id": task_id,
        "session_id": session_id,
        "status": _normalize_task_status(task_status),
        "schema_version": str(normalized_graph.get("schema_version") or "task_graph.v1"),
        "nodes": nodes,
        "edges": edges,
        "summary": _build_graph_summary(nodes, edges),
        "updated_at": snapshot_updated_at,
    }


def _update_graph_snapshot(
    *,
    graph_snapshot: dict[str, Any],
    step_id: str,
    status: str,
    started_at_ms: int | None = None,
    finished_at_ms: int | None = None,
) -> None:
    normalized_status = _normalize_graph_status(status)
    node_status_map: dict[str, str] = {}
    for node in graph_snapshot.get("nodes", []):
        if not isinstance(node, dict):
            continue
        node_id = str(node.get("id") or "")
        if node_id == step_id:
            node["status"] = normalized_status
            node_data = node.get("data") if isinstance(node.get("data"), dict) else {}
            node_data["status"] = normalized_status
            node["data"] = node_data
            if started_at_ms is not None and not node.get("startedAt"):
                node["startedAt"] = started_at_ms
                node_data["started_at_ms"] = started_at_ms
            if finished_at_ms is not None:
                node["finishedAt"] = finished_at_ms
                node_data["finished_at_ms"] = finished_at_ms
            if node.get("startedAt") and node.get("finishedAt"):
                duration_ms = int(node["finishedAt"]) - int(node["startedAt"])
                if duration_ms >= 0:
                    node["durationMs"] = duration_ms
                    node_data["duration_ms"] = duration_ms
        node_status_map[node_id] = str(node.get("status") or "pending")

    for edge in graph_snapshot.get("edges", []):
        if not isinstance(edge, dict):
            continue
        source = str(edge.get("source") or "")
        target = str(edge.get("target") or "")
        edge_status = _derive_edge_status(
            source_status=node_status_map.get(source, "pending"),
            target_status=node_status_map.get(target, "pending"),
        )
        edge["status"] = edge_status
        edge_data = edge.get("data") if isinstance(edge.get("data"), dict) else {}
        edge_data["status"] = edge_status
        edge["data"] = edge_data

    graph_snapshot["summary"] = _build_graph_summary(
        [node for node in graph_snapshot.get("nodes", []) if isinstance(node, dict)],
        [edge for edge in graph_snapshot.get("edges", []) if isinstance(edge, dict)],
    )
    graph_snapshot["updated_at"] = _now_ms()


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
            "graph": build_empty_task_graph_snapshot(
                task_id=task_id,
                session_id=session_id,
                task_status="pending",
                updated_at=created_at,
            ),
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
            updated_at = _now_ms()
            if isinstance(record.get("graph"), dict):
                record["graph"]["status"] = "running"
                record["graph"]["updated_at"] = updated_at
            else:
                record["graph"] = build_empty_task_graph_snapshot(
                    task_id=str(record.get("task_id") or task_id),
                    session_id=str(record.get("session_id") or "") or None,
                    task_status="running",
                    updated_at=updated_at,
                )
            record["updated_at"] = updated_at

    async def set_current_agent(self, *, task_id: str, agent_id: str | None) -> None:
        async with self._lock:
            record = self._tasks.get(task_id)
            if record is None:
                return
            record["current_agent_id"] = agent_id.strip() if isinstance(agent_id, str) and agent_id.strip() else None
            record["updated_at"] = _now_ms()

    async def sync_task_graph(
        self,
        *,
        task_id: str,
        task_graph: dict[str, Any],
        execution_state: dict[str, Any] | None = None,
    ) -> None:
        async with self._lock:
            record = self._tasks.get(task_id)
            if record is None:
                return
            updated_at = _now_ms()
            record["graph"] = build_task_graph_snapshot(
                task_id=task_id,
                session_id=str(record.get("session_id") or "") or None,
                task_status=str(record.get("status") or "pending"),
                task_graph=task_graph,
                execution_state=execution_state,
                updated_at=updated_at,
            )
            self._replace_steps_from_graph(record=record)
            record["updated_at"] = updated_at

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
            step_id = str(node.get("step_id") or "")
            step = self._upsert_step(
                record=record,
                step_id=step_id,
                title=_build_step_title(
                    step_id=step_id,
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
            if isinstance(record.get("graph"), dict):
                _update_graph_snapshot(
                    graph_snapshot=record["graph"],
                    step_id=step_id,
                    status="running",
                    started_at_ms=_now_ms(),
                )
                record["graph"]["status"] = "running"
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
            step_id = str(trace_entry.get("step_id") or node.get("step_id") or "")
            step = self._upsert_step(
                record=record,
                step_id=step_id,
                title=_build_step_title(
                    step_id=step_id,
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
            if isinstance(record.get("graph"), dict):
                _update_graph_snapshot(
                    graph_snapshot=record["graph"],
                    step_id=step_id,
                    status=str(node_result.get("status") or trace_entry.get("status") or node.get("status") or "completed"),
                    started_at_ms=(
                        int(trace_entry.get("started_at_ms"))
                        if isinstance(trace_entry.get("started_at_ms"), (int, float)) and int(trace_entry.get("started_at_ms")) > 0
                        else None
                    ),
                    finished_at_ms=(
                        int(trace_entry.get("finished_at_ms"))
                        if isinstance(trace_entry.get("finished_at_ms"), (int, float)) and int(trace_entry.get("finished_at_ms")) > 0
                        else _now_ms()
                    ),
                )
                record["graph"]["status"] = record["status"]
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
            if isinstance(result.get("task_graph"), dict):
                record["graph"] = build_task_graph_snapshot(
                    task_id=task_id,
                    session_id=str(record.get("session_id") or "") or None,
                    task_status=str(record.get("status") or "completed"),
                    task_graph=result.get("task_graph"),
                    execution_state=result.get("task_graph_execution") if isinstance(result.get("task_graph_execution"), dict) else None,
                    updated_at=_now_ms(),
                )
                trace = result.get("task_graph_execution") if isinstance(result.get("task_graph_execution"), dict) else {}
                if not isinstance(trace.get("trace"), list) or not trace.get("trace"):
                    self._replace_steps_from_graph(record=record)
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
                if isinstance(result.get("task_graph"), dict):
                    record["graph"] = build_task_graph_snapshot(
                        task_id=task_id,
                        session_id=str(record.get("session_id") or "") or None,
                        task_status="failed",
                        task_graph=result.get("task_graph"),
                        execution_state=result.get("task_graph_execution") if isinstance(result.get("task_graph_execution"), dict) else None,
                        updated_at=_now_ms(),
                    )
                    trace = result.get("task_graph_execution") if isinstance(result.get("task_graph_execution"), dict) else {}
                    if not isinstance(trace.get("trace"), list) or not trace.get("trace"):
                        self._replace_steps_from_graph(record=record)
            elif isinstance(record.get("graph"), dict):
                record["graph"]["status"] = "failed"
                record["graph"]["updated_at"] = _now_ms()
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

    def _replace_steps_from_graph(self, *, record: dict[str, Any]) -> None:
        graph = record.get("graph") if isinstance(record.get("graph"), dict) else {}
        nodes = graph.get("nodes") if isinstance(graph.get("nodes"), list) else []
        if not nodes:
            return
        mapped_steps: list[dict[str, Any]] = []
        for item in nodes:
            if not isinstance(item, dict):
                continue
            step_id = str(item.get("id") or item.get("step_id") or "")
            if not step_id:
                continue
            node_data = item.get("data") if isinstance(item.get("data"), dict) else {}
            mapped_steps.append(
                {
                    "id": step_id,
                    "title": str(item.get("label") or "") or _build_step_title(
                        step_id=step_id,
                        kind=item.get("kind") or node_data.get("kind"),
                        target_agent=item.get("targetAgent") or node_data.get("target_agent"),
                        tool_name=item.get("toolName") or node_data.get("tool_name"),
                    ),
                    "status": _normalize_step_status(item.get("status") or node_data.get("status")),
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


__all__ = [
    "RuntimeTaskStore",
    "build_empty_task_graph_snapshot",
    "build_task_graph_snapshot",
    "get_runtime_task_store",
]
