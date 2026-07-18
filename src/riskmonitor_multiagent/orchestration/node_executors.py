"""
节点执行器 — 从 task_graph_executor.py 提取的节点执行逻辑.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Awaitable, Callable

from riskmonitor_multiagent.contracts.agent_messages import validate_agent_receipt
from riskmonitor_multiagent.contracts.approval import (
    build_approval_summary_text,
    normalize_approval_record,
    normalize_approval_request,
)
from riskmonitor_multiagent.orchestration.tool_executor import execute_agent_command, new_agent_command
from riskmonitor_multiagent.orchestration.tool_registry import get_tool_meta
from riskmonitor_multiagent.proactive_agents import ProactiveAgentResult
from riskmonitor_multiagent.utils.ids import new_command_id, new_run_id

DelegateHandler = Callable[..., Awaitable[ProactiveAgentResult]]

logger = logging.getLogger(__name__)

_DELEGATE_TARGET_ALIASES = {
    "engineer_agent": "system_engineer",
    "system_engineer_agent": "system_engineer",
    "orchestrator_agent": "orchestrator",
    "critic_agent": "critic",
    "manager_agent": "manager",
}


class NodeExecutor:
    """执行单个 TaskGraph 节点."""

    def __init__(self, *, delegate_handlers: dict[str, DelegateHandler]) -> None:
        self._delegate_handlers = dict(delegate_handlers)

    @staticmethod
    def resolve_delegate_target(target_agent: str) -> str:
        normalized_target = target_agent.strip()
        return _DELEGATE_TARGET_ALIASES.get(normalized_target, normalized_target)

    async def execute_with_retry(
        self,
        *,
        task: dict[str, Any],
        node: dict[str, Any],
        node_outputs: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        retry_budget = self._resolve_retry_budget(task=task, node=node)
        retry_records: list[dict[str, Any]] = []
        last_result: dict[str, Any] | None = None
        for attempt in range(retry_budget + 1):
            result = await self.execute_once(task=task, node=node, node_outputs=node_outputs)
            result["attempt_count"] = attempt + 1
            last_result = result
            if result["status"] in {"completed", "stopped"}:
                result["retry_records"] = retry_records
                return result
            failure_classification = str(result.get("failure_classification") or "")
            retryable = failure_classification in {"timeout", "dependency", "runtime"}
            retry_records.append({
                "step_id": str(node.get("step_id") or ""),
                "attempt": attempt + 1,
                "failure_classification": failure_classification or "runtime",
                "error": result.get("error"),
                "retry_scheduled": retryable and attempt < retry_budget,
            })
            if not retryable or attempt >= retry_budget:
                result["retry_records"] = retry_records
                return result
        assert last_result is not None
        last_result["retry_records"] = retry_records
        return last_result

    async def execute_once(
        self,
        *,
        task: dict[str, Any],
        node: dict[str, Any],
        node_outputs: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        timeout_seconds = self._resolve_timeout_seconds(task=task, node=node)
        started_at_ms = time.time() * 1000
        try:
            if timeout_seconds is not None:
                result = await asyncio.wait_for(
                    self.execute_node(task=task, node=node, node_outputs=node_outputs),
                    timeout=timeout_seconds,
                )
            else:
                result = await self.execute_node(task=task, node=node, node_outputs=node_outputs)
            finished_at_ms = time.time() * 1000
            result["started_at_ms"] = started_at_ms
            result["finished_at_ms"] = finished_at_ms
            result["latency_ms"] = finished_at_ms - started_at_ms
            return result
        except asyncio.TimeoutError:
            finished_at_ms = time.time() * 1000
            return {"status": "failed", "error": f"step_timeout:{str(node.get('step_id') or '')}", "failure_classification": "timeout", "started_at_ms": started_at_ms, "finished_at_ms": finished_at_ms, "latency_ms": finished_at_ms - started_at_ms}
        except Exception as exc:
            finished_at_ms = time.time() * 1000
            return {"status": "failed", "error": str(exc) or exc.__class__.__name__, "failure_classification": self._classify_exception(exc), "started_at_ms": started_at_ms, "finished_at_ms": finished_at_ms, "latency_ms": finished_at_ms - started_at_ms}

    async def execute_node(
        self,
        *,
        task: dict[str, Any],
        node: dict[str, Any],
        node_outputs: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        kind = str(node.get("kind") or "")
        step_id = str(node.get("step_id") or "")
        step_approval_result = self._check_step_approval(node=node)
        if step_approval_result is not None:
            return step_approval_result
        if kind == "delegate":
            return await self._execute_delegate_like_node(task=task, node=node, node_outputs=node_outputs, mode="delegate")
        if kind == "tool_call":
            return self._execute_tool_call_node(task=task, node=node, step_id=step_id)
        if kind == "finalize":
            final_output = self._build_finalize_output(task=task, node=node, node_outputs=node_outputs)
            return {"status": "completed", "output": final_output, "final_output": final_output, "output_ref": "final_output", "evidence": {"task_graph_step_id": step_id, "fields": ["delegate_outputs"]}, "input_sources": list(final_output.get("sources") or [])}
        if kind == "analyze":
            return await self._execute_analyze_node(task=task, node=node, node_outputs=node_outputs)
        if kind == "ask_human":
            return self._execute_ask_human_node(node=node, node_outputs=node_outputs)
        if kind == "replan":
            return {"status": "completed", "output": {"replan": True, "reason": node.get("reason"), "replan_from_step_id": node.get("replan_from_step_id")}, "output_ref": "replan", "evidence": {"task_graph_step_id": step_id, "fields": ["critic_plan.issues"]}}
        if kind == "stop":
            final_output = {"summary": str(node.get("instruction") or "\u4efb\u52a1\u5df2\u505c\u6b62"), "stopped": True, "stop_step_id": step_id}
            return {"status": "stopped", "output": final_output, "final_output": final_output, "output_ref": "stop_output", "evidence": {"task_graph_step_id": step_id}}
        return {"status": "failed", "error": f"unknown_step_kind:{kind or 'unknown'}"}

    def _resolve_retry_budget(self, *, task: dict[str, Any], node: dict[str, Any]) -> int:
        retry_budget = node.get("retry_budget")
        if isinstance(retry_budget, int) and retry_budget >= 0:
            return retry_budget
        policy = task.get("execution_policy") if isinstance(task.get("execution_policy"), dict) else {}
        default_retry_budget = policy.get("default_retry_budget")
        if isinstance(default_retry_budget, int) and default_retry_budget >= 0:
            return default_retry_budget
        return 0

    def _resolve_timeout_seconds(self, *, task: dict[str, Any], node: dict[str, Any]) -> float | None:
        timeout_ms = node.get("timeout_ms")
        if not isinstance(timeout_ms, int) or timeout_ms <= 0:
            policy = task.get("execution_policy") if isinstance(task.get("execution_policy"), dict) else {}
            timeout_ms = policy.get("default_timeout_ms")
        if isinstance(timeout_ms, int) and timeout_ms > 0:
            return timeout_ms / 1000.0
        return None

    def _classify_exception(self, exc: Exception) -> str:
        if isinstance(exc, (ValueError, TypeError)):
            return "validation"
        if isinstance(exc, (ImportError, LookupError, ConnectionError, OSError)):
            return "dependency"
        msg = str(exc).lower()
        if any(token in msg for token in ("invalid", "validation", "missing param", "bad param", "参数")):
            return "validation"
        if any(token in msg for token in ("dependency", "service unavailable", "connection", "unreachable")):
            return "dependency"
        return "runtime"

    def _execute_tool_call_node(self, *, task: dict[str, Any], node: dict[str, Any], step_id: str) -> dict[str, Any]:
        tool_name = str(node.get("tool_name") or "").strip()
        if not tool_name:
            return {"status": "failed", "error": "missing_tool_name", "failure_classification": "validation"}
        meta = get_tool_meta(tool_name)
        if meta is None:
            return {"status": "failed", "error": f"unknown_tool:{tool_name}", "failure_classification": "dependency"}
        params = dict(node.get("params")) if isinstance(node.get("params"), dict) else {}
        task_budget = task.get("tool_budget") if isinstance(task.get("tool_budget"), dict) else {}
        if task_budget and "_budget" not in params:
            params["_budget"] = dict(task_budget)
        target_agent = str(node.get("target_agent") or meta.owner or "").strip()
        if not target_agent:
            return {"status": "failed", "error": f"missing_target_agent_for_tool:{tool_name}", "failure_classification": "validation"}
        command_id = str(node.get("command_id") or new_command_id())
        run_id = task.get("run_id") if isinstance(task.get("run_id"), str) and task.get("run_id") else None
        if not run_id:
            run_id = task.get("task_id") if isinstance(task.get("task_id"), str) and task.get("task_id") else new_run_id("task_graph")
        timeout_ms = node.get("timeout_ms") if isinstance(node.get("timeout_ms"), int) and node.get("timeout_ms") > 0 else meta.default_timeout_ms
        retry_budget = node.get("retry_budget") if isinstance(node.get("retry_budget"), int) and node.get("retry_budget") >= 0 else 0
        expected_output_schema = str(node.get("expected_output_schema")) if isinstance(node.get("expected_output_schema"), str) and node.get("expected_output_schema") else "tool_result.v1"
        command = new_agent_command(run_id=str(run_id), command_id=command_id, target_agent=target_agent, action=tool_name, params=params, timeout_ms=int(timeout_ms), expected_output_schema=expected_output_schema, retry_budget=int(retry_budget))
        receipt = execute_agent_command(command)
        ok_receipt, receipt_errors = validate_agent_receipt(receipt)
        if not ok_receipt:
            return {"status": "failed", "error": "invalid_tool_receipt", "failure_classification": "runtime", "command_id": command_id, "tool_name": tool_name, "receipt": {"schema_version": receipt.get("schema_version"), "run_id": receipt.get("run_id"), "command_id": receipt.get("command_id"), "tool_name": tool_name, "status": "failed", "ok": False, "latency_ms": float(receipt.get("latency_ms") or 0.0), "error": "invalid_tool_receipt", "inputs": params, "outputs": None, "output": None, "evidence": {"receipt_errors": receipt_errors}, "artifacts": [], "target_agent": target_agent, "side_effect": bool(meta.capability == "side_effect"), "approval_state": "unknown", "approval_trace": {"required": bool(meta.capability == "side_effect"), "current_state": "unknown", "history": []}, "failure_classification": "runtime", "retry_count": 0, "retry_budget": int(retry_budget), "timeout_ms": int(timeout_ms)}}
        receipt_command_id = str(receipt.get("command_id")) if isinstance(receipt.get("command_id"), str) and receipt.get("command_id") else command_id
        output_payload = {"tool_name": tool_name, "command_id": receipt_command_id, "summary": f"tool {tool_name} completed cmd:{receipt_command_id}", "receipt_command_ids": [receipt_command_id], "result": receipt.get("outputs"), "approval_state": receipt.get("approval_state"), "approval_trace": receipt.get("approval_trace")}
        error = receipt.get("error")
        status = "completed" if receipt.get("ok") is True else ("blocked" if receipt.get("status") == "blocked" else "failed")
        failure_classification = None if status == "completed" else self._classify_receipt_error(receipt)
        approval_record = self._build_command_approval_record(step_id=step_id, receipt=receipt)
        return {"status": status, "output": output_payload, "output_ref": command_id, "evidence": {"task_graph_step_id": step_id, "receipt_command_ids": [receipt_command_id], "tool_name": tool_name, "approval_state": receipt.get("approval_state")}, "error": error, "failure_classification": failure_classification, "command_id": receipt_command_id, "tool_name": tool_name, "receipt": receipt, "approval_record": approval_record, "receipt_command_ids": [receipt_command_id]}

    async def _execute_delegate_like_node(self, *, task: dict[str, Any], node: dict[str, Any], node_outputs: dict[str, dict[str, Any]], mode: str) -> dict[str, Any]:
        step_id = str(node.get("step_id") or "")
        raw_target_agent = str(node.get("target_agent") or "").strip()
        target_agent = self.resolve_delegate_target(raw_target_agent)
        if target_agent not in self._delegate_handlers:
            logger.warning("Delegate node %s targets unknown agent '%s' (raw: '%s'), degrading to finalize. Available agents: %s", step_id, target_agent, raw_target_agent, list(self._delegate_handlers.keys()))
            return {"status": "completed", "output": {"summary": f"Delegate to '{target_agent}' degraded: agent not found", "degraded": True, "original_target": raw_target_agent or target_agent}}
        handler = self._delegate_handlers[target_agent]
        result = await handler(task=task, context={"task_graph_node": node, "step_id": step_id, "upstream_outputs": dict(node_outputs), "resume_context": (dict(task.get("resume_context", {})) if isinstance(task.get("resume_context"), dict) else {})})
        result.meta = dict(result.meta or {})
        result.meta["agent_name"] = target_agent
        return {"status": "completed" if result.ok else "failed", "output": result.output if isinstance(result.output, dict) else {}, "delegate_result": result, "output_ref": target_agent, "evidence": {"task_graph_step_id": step_id, f"{mode}_agent": target_agent, "requested_delegate_agent": raw_target_agent}, "error": None if result.ok else f"{mode}_failed:{target_agent}"}

    async def _execute_analyze_node(self, *, task: dict[str, Any], node: dict[str, Any], node_outputs: dict[str, dict[str, Any]]) -> dict[str, Any]:
        target_agent = str(node.get("target_agent") or "").strip()
        if target_agent:
            handler = self._delegate_handlers.get(self.resolve_delegate_target(target_agent))
            if handler is not None:
                return await self._execute_delegate_like_node(task=task, node=node, node_outputs=node_outputs, mode="analyze")
        instruction = str(node.get("instruction") or node.get("reason") or "\u6267\u884c\u5206\u6790").strip()
        upstream_summaries: list[str] = []
        for step_id, payload in node_outputs.items():
            if not isinstance(payload, dict):
                continue
            summary = payload.get("summary") or payload.get("report")
            if isinstance(summary, str) and summary.strip():
                upstream_summaries.append(f"{step_id}:{summary.strip()}")
        report_lines = [instruction]
        if upstream_summaries:
            report_lines.append("\u53c2\u8003\u4e0a\u6e38\u8f93\u51fa: " + " ; ".join(upstream_summaries))
        return {"status": "completed", "output": {"summary": instruction, "report": "\n".join(report_lines), "input_sources": sorted(node_outputs.keys())}, "output_ref": "analysis_output", "evidence": {"task_graph_step_id": str(node.get("step_id") or ""), "analysis_mode": "internal"}, "input_sources": sorted(node_outputs.keys())}

    def _execute_ask_human_node(self, *, node: dict[str, Any], node_outputs: dict[str, dict[str, Any]]) -> dict[str, Any]:
        params = dict(node.get("params")) if isinstance(node.get("params"), dict) else {}
        approval = dict(node.get("approval")) if isinstance(node.get("approval"), dict) else {}
        response = params.get("human_response")
        if not isinstance(response, str) or not response.strip():
            response = approval.get("response")
        if isinstance(response, str) and response.strip():
            clean_response = response.strip()
            return {"status": "completed", "output": {"summary": f"\u4eba\u5de5\u8f93\u5165\u5df2\u786e\u8ba4: {clean_response}", "human_response": clean_response, "input_sources": sorted(node_outputs.keys())}, "output_ref": "human_response", "evidence": {"task_graph_step_id": str(node.get("step_id") or ""), "question": node.get("instruction") or node.get("reason")}, "input_sources": sorted(node_outputs.keys())}
        request = normalize_approval_request({"level": "step", "approval_id": approval.get("approval_id") or f"human:{node.get('step_id')}", "step_id": node.get("step_id"), "reason": node.get("instruction") or node.get("reason") or "\u9700\u8981\u4eba\u5de5\u8f93\u5165", "risk_level": approval.get("risk_level") or "MEDIUM", "impact_scope": approval.get("impact_scope") or ["human_input"], "recommended_action": approval.get("recommended_action") or "collect_human_input_and_resume"})
        record = normalize_approval_record({"request": request, "state": "pending", "actor": approval.get("actor"), "note": approval.get("note"), "error": "human_input_required"})
        return {"status": "blocked", "output": {"summary": build_approval_summary_text(record), "approval_request": request, "question": node.get("instruction") or node.get("reason")}, "approval_record": record, "error": "human_input_required", "failure_classification": "permission"}

    def _build_finalize_output(self, *, task: dict[str, Any], node: dict[str, Any], node_outputs: dict[str, dict[str, Any]]) -> dict[str, Any]:
        sections: list[str] = []
        sources: list[str] = []
        receipt_command_ids: list[str] = []
        for output_ref, payload in node_outputs.items():
            if not isinstance(payload, dict):
                continue
            summary = payload.get("summary")
            report = payload.get("report")
            ids = payload.get("receipt_command_ids")
            if isinstance(ids, list):
                for receipt_id in ids:
                    if isinstance(receipt_id, str) and receipt_id and receipt_id not in receipt_command_ids:
                        receipt_command_ids.append(receipt_id)
            if isinstance(summary, str) and summary.strip():
                sections.append(summary.strip())
                sources.append(output_ref)
            elif isinstance(report, str) and report.strip():
                sections.append(report.strip())
                sources.append(output_ref)
        if not sections:
            payload = task.get("payload") if isinstance(task.get("payload"), dict) else {}
            default_summary = payload.get("content") if isinstance(payload.get("content"), str) else "\u4efb\u52a1\u5df2\u6267\u884c"
            sections.append(default_summary)
        return {"summary": "\n".join(sections), "sources": sources, "receipt_command_ids": receipt_command_ids, "finalize_reason": node.get("reason"), "task_graph_completed": True}

    def _classify_receipt_error(self, receipt: dict[str, Any]) -> str:
        classification = receipt.get("failure_classification")
        if isinstance(classification, str) and classification:
            return classification
        error = str(receipt.get("error") or "")
        if error in {"approval_required", "approval_reason_required", "rbac_denied", "policy_denied"}:
            return "permission"
        if error in {"approval_rejected", "approval_expired"}:
            return "permission"
        if error == "invalid_command":
            return "validation"
        if error in {"unknown_action", "handler_missing"}:
            return "dependency"
        if error == "tool_timeout":
            return "timeout"
        return "runtime"

    def _check_step_approval(self, *, node: dict[str, Any]) -> dict[str, Any] | None:
        approval = node.get("approval")
        if not isinstance(approval, dict) or approval.get("required") is not True:
            return None
        request = normalize_approval_request({"level": "step", "approval_id": approval.get("approval_id") or f"step:{node.get('step_id')}", "step_id": node.get("step_id"), "reason": approval.get("reason") or node.get("reason"), "risk_level": approval.get("risk_level") or "HIGH", "impact_scope": approval.get("impact_scope") or [str(node.get("target_agent") or node.get("kind") or "system")], "recommended_action": approval.get("recommended_action") or "review_and_resume_step"})
        explicit_state = str(approval.get("state") or "pending").strip().lower()
        actor = approval.get("actor") if isinstance(approval.get("actor"), str) and approval.get("actor") else None
        note = approval.get("note") if isinstance(approval.get("note"), str) and approval.get("note") else None
        if explicit_state in {"approved", "resumed"}:
            return None
        if explicit_state == "rejected":
            record = normalize_approval_record({"request": request, "state": "rejected", "actor": actor, "note": note, "error": "approval_rejected"})
            return {"status": "blocked", "output": {"summary": build_approval_summary_text(record), "approval_request": request}, "approval_record": record, "error": "approval_rejected", "failure_classification": "permission"}
        if explicit_state == "expired":
            record = normalize_approval_record({"request": request, "state": "expired", "actor": actor, "note": note, "error": "approval_expired"})
            return {"status": "blocked", "output": {"summary": build_approval_summary_text(record), "approval_request": request}, "approval_record": record, "error": "approval_expired", "failure_classification": "permission"}
        record = normalize_approval_record({"request": request, "state": "pending", "actor": actor, "note": note, "error": "approval_required"})
        return {"status": "blocked", "output": {"summary": build_approval_summary_text(record), "approval_request": request}, "approval_record": record, "error": "approval_required", "failure_classification": "permission"}

    def _build_command_approval_record(self, *, step_id: str, receipt: dict[str, Any]) -> dict[str, Any] | None:
        approval_trace = receipt.get("approval_trace")
        if not isinstance(approval_trace, dict) or not approval_trace.get("required"):
            return None
        request = receipt.get("approval_request")
        if not isinstance(request, dict):
            request = {"level": "command", "approval_id": f"command:{receipt.get('command_id')}", "step_id": step_id, "command_id": receipt.get("command_id"), "tool_name": receipt.get("tool_name"), "reason": ((receipt.get("evidence") or {}).get("reason") if isinstance(receipt.get("evidence"), dict) else None) or "approval_required", "risk_level": ((((receipt.get("inputs") or {}).get("_event") or {}).get("severity")) if isinstance((receipt.get("inputs") or {}).get("_event"), dict) else None) or "HIGH", "impact_scope": ["system"], "recommended_action": "review_and_confirm_command_execution"}
        record = normalize_approval_record({"request": request, "state": receipt.get("approval_state") or approval_trace.get("current_state") or "pending", "actor": ((receipt.get("inputs") or {}).get("approval") or {}).get("actor") if isinstance((receipt.get("inputs") or {}).get("approval"), dict) else None, "note": ((receipt.get("inputs") or {}).get("approval") or {}).get("note") if isinstance((receipt.get("inputs") or {}).get("approval"), dict) else None, "error": receipt.get("error")})
        record["step_id"] = step_id
        record["command_id"] = receipt.get("command_id")
        record["tool_name"] = receipt.get("tool_name")
        return record
