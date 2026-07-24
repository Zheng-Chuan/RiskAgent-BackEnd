"""
REST BFF 服务层.

负责任务提交 任务详情聚合 和智能体状态派生.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from riskmonitor_multiagent.contracts.run_context import new_run_context
from riskmonitor_multiagent.memory import get_memory_store
from riskmonitor_multiagent.observability.run_trace import get_run_trace_store
from riskmonitor_multiagent.orchestration.proactive_workflow import (
    get_proactive_workflow,
    run_proactive_workflow,
)
from riskmonitor_multiagent.services.runtime_task_store import get_runtime_task_store
from riskmonitor_multiagent.utils.ids import new_run_id

logger = logging.getLogger(__name__)

_AGENT_SPECS = (
    {
        "id": "intent",
        "name": "ProactiveIntentAgent",
        "role": "lead",
        "workflow_attr": "_intent_agent",
        "capabilities": ["recognize", "monitor"],
    },
    {
        "id": "orchestrator",
        "name": "ProactiveOrchestratorAgent",
        "role": "lead",
        "workflow_attr": "_orchestrator_agent",
        "capabilities": ["plan", "coordinate", "monitor"],
    },
    {
        "id": "critic",
        "name": "ProactiveCriticAgent",
        "role": "reviewer",
        "workflow_attr": "_critic_agent",
        "capabilities": ["review", "governance", "validate"],
    },
    {
        "id": "system_engineer",
        "name": "ProactiveSystemEngineerAgent",
        "role": "engineer",
        "workflow_attr": "_engineer_agent",
        "capabilities": ["analyze", "monitor", "execute"],
    },
    {
        "id": "risk_analyst",
        "name": "ProactiveRiskAnalystAgent",
        "role": "analyst",
        "workflow_attr": "_analyst_agent",
        "capabilities": ["analyze", "monitor", "report"],
    },
)


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
            "result": _build_result_payload(
                data.get("final_output") if isinstance(data.get("final_output"), dict) else None
            ),
            "error": _extract_error_payload(data),
            "created_at": created_at,
            "updated_at": updated_at,
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
