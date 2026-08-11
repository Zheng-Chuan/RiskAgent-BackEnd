"""
REST BFF 服务层.

负责任务提交 任务详情聚合 和智能体状态派生.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from riskagent_backend.agents.registry import all_agents
from riskagent_backend.contracts.run_context import new_run_context
from riskagent_backend.memory import get_memory_store
from riskagent_backend.memory.memory_helpers import canonical_agent_id, compact_output_text
from riskagent_backend.observability.run_trace import get_run_trace_store
from riskagent_backend.orchestration.proactive_workflow import (
    get_proactive_workflow,
    run_proactive_workflow,
)
from riskagent_backend.services.runtime_task_store import (
    build_empty_task_graph_snapshot,
    build_task_graph_snapshot,
    get_runtime_task_store,
)
from riskagent_backend.services.task_status import (
    normalize_step_status as _normalize_step_status,
    normalize_task_status as _normalize_task_status,
    now_ms as _now_ms,
)
from riskagent_backend.utils.ids import new_run_id

logger = logging.getLogger(__name__)

_SECRET_PATTERN = re.compile(r"sk-[A-Za-z0-9_-]{12,}")

_AGENT_SPECS = tuple(spec.to_display_dict() for spec in all_agents())


def _build_step_title(trace_item: dict[str, Any]) -> str:
    step_id = str(trace_item.get("step_id") or "")
    kind = str(trace_item.get("kind") or "").strip()
    target_agent = str(trace_item.get("target_agent") or "").strip()
    tool_name = str(trace_item.get("tool_name") or "").strip()
    if kind == "delegate" and target_agent:
        return f"delegate {target_agent}"
    if kind == "tool_call" and tool_name:
        return f"tool {tool_name}"
    if kind == "finalize":
        return "finalize result"
    if kind == "stop":
        return "stop workflow"
    return f"{kind} {target_agent}".strip() or step_id or "unknown_step"


def _extract_description(task_payload: dict[str, Any] | None) -> str:
    if not isinstance(task_payload, dict):
        return ""
    payload = task_payload.get("payload") if isinstance(task_payload.get("payload"), dict) else {}
    content = payload.get("content")
    return content.strip() if isinstance(content, str) else ""


def _extract_error_payload(result: dict[str, Any] | None) -> dict[str, str] | None:
    if not isinstance(result, dict):
        return None
    errors = result.get("errors")
    if isinstance(errors, list):
        for item in errors:
            if isinstance(item, str) and item.strip():
                return {"code": "TASK_FAILED", "message": item.strip()}
    error_payload = result.get("error")
    if isinstance(error_payload, dict):
        message = error_payload.get("message")
        if isinstance(message, str) and message.strip():
            code = str(error_payload.get("code") or "TASK_FAILED")
            return {"code": code, "message": message.strip()}
    if isinstance(error_payload, str) and error_payload.strip():
        return {"code": "TASK_FAILED", "message": error_payload.strip()}
    return None


def _build_result_payload(final_output: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(final_output, dict) or not final_output:
        return None
    summary = final_output.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        summary = final_output.get("report")
    if not isinstance(summary, str) or not summary.strip():
        summary = str(final_output.get("reason") or "").strip() or "任务已完成"

    artifacts: list[dict[str, Any]] = []
    raw_artifacts = final_output.get("artifacts")
    if isinstance(raw_artifacts, list):
        for item in raw_artifacts:
            if not isinstance(item, dict):
                continue
            title = item.get("title")
            content = item.get("content")
            if isinstance(title, str) and isinstance(content, str):
                artifacts.append(
                    {
                        "id": str(item.get("id") or ""),
                        "type": str(item.get("type") or "document"),
                        "title": title,
                        "content": content,
                    }
                )
    payload: dict[str, Any] = {"summary": summary}
    if artifacts:
        payload["artifacts"] = artifacts
    return payload


def _mask_secret_text(value: str) -> str:
    return _SECRET_PATTERN.sub("sk-***", value)


def _sanitize_public_text(value: Any, *, limit: int = 220) -> str:
    if not isinstance(value, str):
        return ""
    normalized = " ".join(value.split())
    if not normalized:
        return ""
    sanitized = _mask_secret_text(normalized)
    return sanitized[:limit]


class RestBffService:
    """REST BFF facade."""

    async def submit_task(self, *, description: str) -> dict[str, Any]:
        normalized = description.strip()
        if not normalized:
            raise ValueError("description is required")

        task_id = new_run_id("run")
        session_id = new_run_id("session")
        runtime_store = get_runtime_task_store()
        created = await runtime_store.create_task(
            task_id=task_id,
            session_id=session_id,
            description=normalized,
            run_id=task_id,
        )

        task_payload = {
            "task_id": task_id,
            "session_id": session_id,
            "source": "human",
            "payload": {"content": normalized},
            "run_context": new_run_context(
                entry_type="user_task",
                task_id=task_id,
                run_id=task_id,
                metadata={"source": "rest_bff"},
            ),
        }

        execution_task = asyncio.create_task(
            self._execute_task(task_id=task_id, task_payload=task_payload),
            name=f"rest_bff_{task_id}",
        )
        await runtime_store.attach_execution_task(
            task_id=task_id,
            execution_task=execution_task,
        )

        return {
            "task_id": task_id,
            "status": str(created.get("status") or "pending"),
            "created_at": int(created.get("created_at") or _now_ms()),
        }

    async def get_task_detail(self, *, task_id: str) -> dict[str, Any]:
        normalized_task_id = task_id.strip()
        if not normalized_task_id:
            raise ValueError("task_id is required")

        runtime_store = get_runtime_task_store()
        runtime_snapshot = await runtime_store.get_task(task_id=normalized_task_id)
        if isinstance(runtime_snapshot, dict):
            return self._map_runtime_task_detail(runtime_snapshot)

        persisted = await self._load_persisted_task(task_id=normalized_task_id)
        if isinstance(persisted, dict):
            return persisted

        raise KeyError(normalized_task_id)

    async def get_task_graph(self, *, task_id: str) -> dict[str, Any]:
        normalized_task_id = task_id.strip()
        if not normalized_task_id:
            raise ValueError("task_id is required")

        runtime_store = get_runtime_task_store()
        runtime_snapshot = await runtime_store.get_task(task_id=normalized_task_id)
        if isinstance(runtime_snapshot, dict):
            if isinstance(runtime_snapshot.get("graph"), dict):
                return dict(runtime_snapshot["graph"])
            return build_empty_task_graph_snapshot(
                task_id=normalized_task_id,
                session_id=(
                    str(runtime_snapshot.get("session_id"))
                    if isinstance(runtime_snapshot.get("session_id"), str) and str(runtime_snapshot.get("session_id")).strip()
                    else None
                ),
                task_status=str(runtime_snapshot.get("status") or "pending"),
                updated_at=int(runtime_snapshot.get("updated_at") or _now_ms()),
            )

        persisted_context = await self._load_persisted_run_context(task_id=normalized_task_id)
        if not isinstance(persisted_context, dict):
            raise KeyError(normalized_task_id)

        task_payload = persisted_context.get("task") if isinstance(persisted_context.get("task"), dict) else {}
        session_id = (
            str(task_payload.get("session_id"))
            if isinstance(task_payload.get("session_id"), str) and str(task_payload.get("session_id")).strip()
            else None
        )
        task_graph = persisted_context.get("task_graph") if isinstance(persisted_context.get("task_graph"), dict) else None
        if not isinstance(task_graph, dict):
            raise KeyError(normalized_task_id)
        execution = persisted_context.get("task_graph_execution") if isinstance(persisted_context.get("task_graph_execution"), dict) else None
        return build_task_graph_snapshot(
            task_id=normalized_task_id,
            session_id=session_id,
            task_status=str(persisted_context.get("status") or "completed"),
            task_graph=task_graph,
            execution_state=execution,
            updated_at=self._infer_updated_at(
                trace_items=execution.get("trace") if isinstance(execution, dict) and isinstance(execution.get("trace"), list) else [],
                trace_entries=[],
            ),
        )

    async def get_agents_snapshot(self) -> dict[str, Any]:
        runtime_store = get_runtime_task_store()
        active_task = await runtime_store.get_active_task()
        workflow = get_proactive_workflow()
        updated_at = int(active_task.get("updated_at") or _now_ms()) if isinstance(active_task, dict) else _now_ms()
        current_agent_id = active_task.get("current_agent_id") if isinstance(active_task, dict) else None
        current_task_id = active_task.get("task_id") if isinstance(active_task, dict) else None

        items: list[dict[str, Any]] = []
        for spec in _AGENT_SPECS:
            agent = getattr(workflow, spec["workflow_attr"], None)
            base_status = "offline"
            if agent is not None and bool(getattr(agent, "is_running", False)):
                base_status = "idle"
            if current_agent_id == spec["id"] and current_task_id:
                base_status = "working"
            items.append(
                {
                    "id": spec["id"],
                    "name": spec["name"],
                    "role": spec["role"],
                    "status": base_status,
                    "currentTaskId": current_task_id if current_agent_id == spec["id"] else None,
                    "capabilities": list(spec["capabilities"]),
                    "lastActiveAt": updated_at if current_agent_id == spec["id"] else updated_at,
                }
            )
        return {"items": items, "updated_at": updated_at}

    async def get_task_memory(
        self,
        *,
        task_id: str,
        limit: int = 30,
    ) -> dict[str, Any]:
        normalized_task_id = task_id.strip()
        if not normalized_task_id:
            raise ValueError("task_id is required")

        task_scope = await self._resolve_task_scope(task_id=normalized_task_id)
        if task_scope is None:
            raise KeyError(normalized_task_id)

        memory_items = await self._collect_memory_items(
            session_id=task_scope.get("session_id"),
            run_id=str(task_scope.get("run_id") or normalized_task_id),
            limit=limit,
        )

        return {
            "task_id": normalized_task_id,
            "session_id": task_scope.get("session_id"),
            "items": memory_items,
            "summary": self._build_memory_summary(memory_items),
            "updated_at": max((int(item.get("createdAt") or 0) for item in memory_items), default=_now_ms()),
        }

    async def get_memory_snapshot(self, *, limit: int = 20) -> dict[str, Any]:
        memory_items = await self._collect_memory_items(session_id=None, run_id=None, limit=limit)
        return {
            "items": memory_items,
            "summary": self._build_memory_summary(memory_items),
            "updated_at": max((int(item.get("createdAt") or 0) for item in memory_items), default=_now_ms()),
        }

    async def _execute_task(
        self,
        *,
        task_id: str,
        task_payload: dict[str, Any],
    ) -> None:
        runtime_store = get_runtime_task_store()
        try:
            await runtime_store.mark_running(task_id=task_id, run_id=task_id)
            await runtime_store.set_current_agent(task_id=task_id, agent_id="intent")
            result = await run_proactive_workflow(task=task_payload)
            await runtime_store.finalize_task(task_id=task_id, result=result)
        except Exception as exc:
            logger.exception("REST BFF task execution failed: %s", exc)
            await runtime_store.fail_task(
                task_id=task_id,
                error_message=str(exc),
            )
        finally:
            await runtime_store.clear_execution_task(task_id=task_id)

    async def _load_persisted_task(self, *, task_id: str) -> dict[str, Any] | None:
        data: dict[str, Any] = {}
        try:
            memory_store = get_memory_store()
            context = await memory_store.get_run_context(task_id)
            if isinstance(context, dict):
                data = context.get("data") if isinstance(context.get("data"), dict) else {}
        except Exception as exc:
            logger.warning("Load run context failed for %s: %s", task_id, exc)

        if not data:
            return None

        trace = []
        try:
            trace_store = get_run_trace_store()
            snapshot = trace_store.get_snapshot(task_id)
            if snapshot is not None:
                trace = [dict(item) for item in snapshot.entries if isinstance(item, dict)]
        except Exception as exc:
            logger.warning("Load run trace failed for %s: %s", task_id, exc)

        task_payload = data.get("task") if isinstance(data.get("task"), dict) else {}
        description = _extract_description(task_payload)
        execution = data.get("task_graph_execution") if isinstance(data.get("task_graph_execution"), dict) else {}
        trace_items = execution.get("trace") if isinstance(execution.get("trace"), list) else []
        created_at = self._infer_created_at(trace_items=trace_items, trace_entries=trace)
        updated_at = self._infer_updated_at(trace_items=trace_items, trace_entries=trace)

        return {
            "id": task_id,
            "title": description[:48] or "untitled_task",
            "description": description,
            "status": _normalize_task_status(data.get("status")),
            "steps": self._map_trace_steps(trace_items=trace_items),
            "graph": (
                build_task_graph_snapshot(
                    task_id=task_id,
                    session_id=(
                        str(task_payload.get("session_id"))
                        if isinstance(task_payload.get("session_id"), str) and str(task_payload.get("session_id")).strip()
                        else None
                    ),
                    task_status=str(data.get("status") or "completed"),
                    task_graph=data.get("task_graph"),
                    execution_state=execution,
                    updated_at=updated_at,
                )
                if isinstance(data.get("task_graph"), dict)
                else None
            ),
            "result": _build_result_payload(
                data.get("final_output") if isinstance(data.get("final_output"), dict) else None
            ),
            "error": _extract_error_payload(data),
            "created_at": created_at,
            "updated_at": updated_at,
        }

    async def _resolve_task_scope(self, *, task_id: str) -> dict[str, str | None] | None:
        runtime_store = get_runtime_task_store()
        runtime_snapshot = await runtime_store.get_task(task_id=task_id)
        if isinstance(runtime_snapshot, dict):
            return {
                "run_id": str(runtime_snapshot.get("run_id") or task_id),
                "session_id": (
                    str(runtime_snapshot.get("session_id"))
                    if isinstance(runtime_snapshot.get("session_id"), str)
                    and str(runtime_snapshot.get("session_id")).strip()
                    else None
                ),
            }

        persisted_context = await self._load_persisted_run_context(task_id=task_id)
        if not isinstance(persisted_context, dict):
            return None

        task_payload = persisted_context.get("task") if isinstance(persisted_context.get("task"), dict) else {}
        session_id = (
            str(task_payload.get("session_id"))
            if isinstance(task_payload.get("session_id"), str) and str(task_payload.get("session_id")).strip()
            else None
        )
        return {
            "run_id": str(task_id),
            "session_id": session_id,
        }

    async def _load_persisted_run_context(self, *, task_id: str) -> dict[str, Any] | None:
        try:
            memory_store = get_memory_store()
            context = await memory_store.get_run_context(task_id)
        except Exception as exc:
            logger.warning("Load persisted memory context failed for %s: %s", task_id, exc)
            return None

        if not isinstance(context, dict):
            return None
        return context.get("data") if isinstance(context.get("data"), dict) else None

    async def _collect_memory_items(
        self,
        *,
        session_id: str | None,
        run_id: str | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        memory_store = get_memory_store()
        safe_limit = max(1, min(limit, 100))
        shared_entries = await memory_store.list_recent(
            agent_id="orchestrator",
            scope="shared",
            session_id=session_id,
            run_id=run_id,
            limit=safe_limit,
        )
        private_memory_state = await memory_store.get_private_memory_state(
            session_id=session_id,
            run_id=run_id,
            limit=max(2, min(6, safe_limit)),
        )

        combined: list[dict[str, Any]] = []
        seen_entry_ids: set[str] = set()
        for entry in shared_entries:
            mapped = self._map_memory_entry(entry)
            if mapped is None or mapped["id"] in seen_entry_ids:
                continue
            seen_entry_ids.add(mapped["id"])
            combined.append(mapped)

        for entries in private_memory_state.values():
            for entry in entries:
                mapped = self._map_memory_entry(entry)
                if mapped is None or mapped["id"] in seen_entry_ids:
                    continue
                seen_entry_ids.add(mapped["id"])
                combined.append(mapped)

        combined.sort(key=lambda item: int(item.get("createdAt") or 0), reverse=True)
        return combined[:safe_limit]

    def _map_memory_entry(self, entry: dict[str, Any]) -> dict[str, Any] | None:
        if not isinstance(entry, dict):
            return None

        entry_id = entry.get("entry_id")
        if not isinstance(entry_id, str) or not entry_id.strip():
            return None

        content = entry.get("content") if isinstance(entry.get("content"), dict) else {}
        summary = self._build_memory_entry_summary(entry=entry, content=content)
        if not summary:
            return None

        task_id = content.get("task_id") if isinstance(content.get("task_id"), str) else entry.get("run_id")
        session_id = entry.get("session_id") if isinstance(entry.get("session_id"), str) else None
        agent_id = canonical_agent_id(entry.get("agent_id")) or str(entry.get("agent_id") or "shared")

        return {
            "id": entry_id,
            "taskId": str(task_id) if isinstance(task_id, str) and task_id.strip() else None,
            "sessionId": session_id,
            "agentId": agent_id,
            "scope": str(entry.get("scope") or "shared"),
            "kind": str(entry.get("kind") or "unknown"),
            "memoryType": str(entry.get("memory_type") or "episodic"),
            "changeType": self._map_memory_change_type(entry),
            "summary": summary,
            "details": self._build_memory_entry_details(entry=entry, content=content),
            "tags": [
                _sanitize_public_text(tag, limit=24)
                for tag in entry.get("tags", [])
                if isinstance(tag, str) and _sanitize_public_text(tag, limit=24)
            ],
            "confidence": round(float(entry.get("confidence") or 0.0), 2),
            "createdAt": int(entry.get("ts_ms") or _now_ms()),
        }

    def _build_memory_entry_summary(
        self,
        *,
        entry: dict[str, Any],
        content: dict[str, Any],
    ) -> str:
        preferred_text = content.get("text")
        if isinstance(preferred_text, str) and preferred_text.strip():
            return _sanitize_public_text(preferred_text, limit=180)

        if str(entry.get("kind") or "") == "private_task_state":
            progress = _sanitize_public_text(content.get("current_progress"), limit=90)
            next_action = _sanitize_public_text(content.get("next_intended_action"), limit=90)
            if progress and next_action:
                return f"{progress}. 下一步 {next_action}"
            if progress:
                return progress
            if next_action:
                return next_action

        if isinstance(content.get("plan_steps"), list) and content.get("plan_steps"):
            return _sanitize_public_text(" ; ".join(
                str(step.get("reason") or step.get("instruction") or step.get("kind") or "")
                for step in content["plan_steps"]
                if isinstance(step, dict)
            ), limit=180)

        return _sanitize_public_text(compact_output_text(content), limit=180)

    def _build_memory_entry_details(
        self,
        *,
        entry: dict[str, Any],
        content: dict[str, Any],
    ) -> list[str]:
        details: list[str] = []
        source = _sanitize_public_text(entry.get("source"), limit=60)
        if source:
            details.append(f"来源 {source}")

        task_id = content.get("task_id") if isinstance(content.get("task_id"), str) else entry.get("run_id")
        if isinstance(task_id, str) and task_id.strip():
            details.append(f"任务 {task_id.strip()}")

        if str(entry.get("scope") or "shared") == "private":
            details.append("私有记忆")

        primary_intent = _sanitize_public_text(content.get("primary_intent_type"), limit=40)
        if primary_intent:
            details.append(f"意图 {primary_intent}")

        current_progress = _sanitize_public_text(content.get("current_progress"), limit=60)
        if current_progress and current_progress not in details:
            details.append(current_progress)

        next_action = _sanitize_public_text(content.get("next_intended_action"), limit=60)
        if next_action:
            details.append(f"下一步 {next_action}")

        tags = [
            _sanitize_public_text(tag, limit=24)
            for tag in entry.get("tags", [])
            if isinstance(tag, str) and _sanitize_public_text(tag, limit=24)
        ]
        if tags:
            details.append(f"标签 {', '.join(tags[:3])}")

        deduped_details: list[str] = []
        for item in details:
            if item not in deduped_details:
                deduped_details.append(item)

        return deduped_details[:4]

    def _map_memory_change_type(self, entry: dict[str, Any]) -> str:
        kind = str(entry.get("kind") or "")
        if kind in {"working_memory", "private_task_state"}:
            return "updated"
        return "created"

    def _build_memory_summary(self, items: list[dict[str, Any]]) -> dict[str, Any]:
        shared_count = sum(1 for item in items if item.get("scope") == "shared")
        private_count = sum(1 for item in items if item.get("scope") == "private")
        agent_ids = {
            str(item.get("agentId"))
            for item in items
            if isinstance(item.get("agentId"), str) and str(item.get("agentId")).strip()
        }
        return {
            "sharedCount": shared_count,
            "privateCount": private_count,
            "agentCount": len(agent_ids),
        }

    def _map_runtime_task_detail(self, runtime_snapshot: dict[str, Any]) -> dict[str, Any]:
        description = str(runtime_snapshot.get("description") or "")
        error_message = runtime_snapshot.get("error")
        return {
            "id": str(runtime_snapshot.get("task_id") or ""),
            "title": str(runtime_snapshot.get("title") or description[:48] or "untitled_task"),
            "description": description,
            "status": _normalize_task_status(runtime_snapshot.get("status")),
            "steps": [
                {
                    "id": str(step.get("id") or ""),
                    "title": str(step.get("title") or step.get("id") or "unknown_step"),
                    "status": _normalize_step_status(step.get("status")),
                }
                for step in runtime_snapshot.get("steps", [])
                if isinstance(step, dict)
            ],
            "graph": dict(runtime_snapshot.get("graph")) if isinstance(runtime_snapshot.get("graph"), dict) else None,
            "result": _build_result_payload(
                runtime_snapshot.get("result") if isinstance(runtime_snapshot.get("result"), dict) else None
            ),
            "error": (
                {
                    "code": "TASK_FAILED",
                    "message": str(error_message).strip(),
                }
                if isinstance(error_message, str) and error_message.strip()
                else None
            ),
            "created_at": int(runtime_snapshot.get("created_at") or _now_ms()),
            "updated_at": int(runtime_snapshot.get("updated_at") or _now_ms()),
        }

    def _map_trace_steps(self, *, trace_items: list[Any]) -> list[dict[str, Any]]:
        steps: list[dict[str, Any]] = []
        for item in trace_items:
            if not isinstance(item, dict):
                continue
            steps.append(
                {
                    "id": str(item.get("step_id") or ""),
                    "title": _build_step_title(item),
                    "status": _normalize_step_status(item.get("status")),
                }
            )
        return steps

    def _infer_created_at(self, *, trace_items: list[Any], trace_entries: list[Any]) -> int:
        timestamps: list[int] = []
        for item in trace_items:
            if not isinstance(item, dict):
                continue
            for key in ("started_at_ms", "finished_at_ms"):
                value = item.get(key)
                if isinstance(value, (int, float)) and int(value) > 0:
                    timestamps.append(int(value))
        for entry in trace_entries:
            if not isinstance(entry, dict):
                continue
            value = entry.get("timestamp_ms")
            if isinstance(value, (int, float)) and int(value) > 0:
                timestamps.append(int(value))
        return min(timestamps) if timestamps else _now_ms()

    def _infer_updated_at(self, *, trace_items: list[Any], trace_entries: list[Any]) -> int:
        timestamps: list[int] = []
        for item in trace_items:
            if not isinstance(item, dict):
                continue
            for key in ("finished_at_ms", "started_at_ms"):
                value = item.get(key)
                if isinstance(value, (int, float)) and int(value) > 0:
                    timestamps.append(int(value))
        for entry in trace_entries:
            if not isinstance(entry, dict):
                continue
            value = entry.get("timestamp_ms")
            if isinstance(value, (int, float)) and int(value) > 0:
                timestamps.append(int(value))
        return max(timestamps) if timestamps else _now_ms()


_rest_bff_service: RestBffService | None = None


def get_rest_bff_service() -> RestBffService:
    global _rest_bff_service
    if _rest_bff_service is None:
        _rest_bff_service = RestBffService()
    return _rest_bff_service


__all__ = ["RestBffService", "get_rest_bff_service"]
