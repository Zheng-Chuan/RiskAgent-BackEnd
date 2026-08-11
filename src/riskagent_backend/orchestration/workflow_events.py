"""
工作流事件处理模块.

从 proactive_workflow.py 提取的纯函数，负责事件路由/构建任务/审批判断.
"""

from __future__ import annotations

from typing import Any

from riskagent_backend.agents.registry import candidate_agents_for_event
from riskagent_backend.orchestration.hitl_policy import hitl_auto_approve_enabled


def default_candidate_agents_for_event(event: dict[str, Any]) -> list[str]:
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    event_type = str(event.get("event_type") or "")
    return candidate_agents_for_event(event_type, payload=payload)


def build_task_from_event(
    *,
    event: dict[str, Any],
    route_decision: dict[str, Any],
) -> dict[str, Any]:
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    base_task = payload.get("task") if isinstance(payload.get("task"), dict) else {}
    task = dict(base_task)
    task.setdefault("task_id", str(payload.get("task_id") or event.get("event_id") or "event_task"))
    task.setdefault("session_id", str(payload.get("session_id") or f"event_{event.get('source_agent') or 'system'}"))
    task.setdefault("source", "system_event")
    task.setdefault("payload", {})
    if not isinstance(task.get("payload"), dict):
        task["payload"] = {}
    content = (
        payload.get("content")
        or payload.get("summary")
        or payload.get("reason")
        or f"处理系统事件 {event.get('event_type')}"
    )
    task["payload"].setdefault("content", str(content))
    task["payload"].setdefault("event_payload", payload)
    task["payload"].setdefault("trigger_event_id", event.get("event_id"))
    task["payload"].setdefault("trigger_reason", route_decision.get("reason"))
    task["payload"].setdefault(
        "trigger_evidence",
        {
            "event_type": event.get("event_type"),
            "source_agent": event.get("source_agent"),
            "payload": payload,
        },
    )
    task["trigger_event_id"] = event.get("event_id")
    task["trigger_reason"] = route_decision.get("reason")
    task["trigger_evidence"] = {
        "event_type": event.get("event_type"),
        "source_agent": event.get("source_agent"),
        "payload": payload,
    }
    return task


def requires_manual_approval(
    *,
    critic_output: dict[str, Any],
    receipts: list[dict[str, Any]] | None,
    approval_records: list[dict[str, Any]] | None,
) -> bool:
    auto_approve = hitl_auto_approve_enabled()
    if isinstance(approval_records, list):
        for record in approval_records:
            if not isinstance(record, dict):
                continue
            state = record.get("approval_state") or record.get("state")
            if state in {"resumed", "approved", "approved_but_failed"}:
                continue
            if state in {"pending", "rejected", "expired"}:
                return True
    if isinstance(receipts, list):
        for receipt in receipts:
            if not isinstance(receipt, dict):
                continue
            if receipt.get("approval_state") in {"approved", "approved_but_failed", "resumed"}:
                return False
            if receipt.get("approval_state") in {"pending", "rejected", "expired"}:
                return True
    if isinstance(critic_output, dict) and critic_output.get("require_human_approval"):
        return not auto_approve
    return False
