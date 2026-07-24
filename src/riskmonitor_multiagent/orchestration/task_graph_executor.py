"""
最小 TaskGraph 执行器.

当前阶段只让 TaskGraph 真正接管 specialist 执行路径.
先支持:
- delegate
- finalize
- stop

其余节点类型先显式报错, 不再静默忽略.
"""

from __future__ import annotations

import asyncio
import logging
import time
from ast import literal_eval
from collections.abc import Mapping
from typing import Any, Awaitable, Callable

from riskmonitor_multiagent.contracts.task_graph import normalize_task_graph
from riskmonitor_multiagent.orchestration.node_executors import NodeExecutor
from riskmonitor_multiagent.orchestration.tool_executor import execute_agent_command  # noqa: F401
from riskmonitor_multiagent.proactive_agents import ProactiveAgentResult

DelegateHandler = Callable[..., Awaitable[ProactiveAgentResult]]
NodeLifecycleHandler = Callable[..., Awaitable[None]]

logger = logging.getLogger(__name__)

# 仅保留合法的历史角色别名,移除会静默回退到 risk_analyst 的别名
# (analysis_agent / risk_assessment_agent / memory_agent 不应委托给 risk_analyst)
_DELEGATE_TARGET_ALIASES = {
    "engineer_agent": "system_engineer",
    "system_engineer_agent": "system_engineer",
    "orchestrator_agent": "orchestrator",
    "critic_agent": "critic",
    "manager_agent": "manager",
}


class TaskGraphExecutor:
    """执行最小 TaskGraph."""

    def __init__(
        self,
        *,
        delegate_handlers: dict[str, DelegateHandler],
        on_node_started: NodeLifecycleHandler | None = None,
        on_node_completed: NodeLifecycleHandler | None = None,
    ) -> None:
        self._delegate_handlers = dict(delegate_handlers)
        self._on_node_started = on_node_started
        self._on_node_completed = on_node_completed
        self._node_executor = NodeExecutor(delegate_handlers=self._delegate_handlers)

    @staticmethod
    def _resolve_delegate_target(target_agent: str) -> str:
        """兼容编排阶段产出的历史角色别名."""
        return NodeExecutor.resolve_delegate_target(target_agent)

    async def execute(
        self,
        *,
        task: dict[str, Any],
        task_graph: dict[str, Any],
        execution_state: dict[str, Any] | None = None,
        resume_from_step_id: str | None = None,
    ) -> dict[str, Any]:
        graph = normalize_task_graph(
            task_graph,
            plan_steps=task_graph.get("plan_steps") if isinstance(task_graph, dict) and isinstance(task_graph.get("plan_steps"), list) else [],
        )
        nodes = [dict(node) for node in graph.get("nodes", []) if isinstance(node, dict)]
        edges = [dict(edge) for edge in graph.get("edges", []) if isinstance(edge, dict)]
        prior_state = dict(execution_state) if isinstance(execution_state, dict) else {}
        completed = self._extract_completed_steps(prior_state)
        skipped = self._extract_skipped_steps(prior_state)
        node_outputs = self._extract_node_outputs(prior_state)
        delegate_results = self._restore_delegate_results(prior_state)
        receipts = self._extract_receipts(prior_state)
        approval_records = self._extract_approval_records(prior_state)
        execution_trace = list(prior_state.get("trace", [])) if isinstance(prior_state.get("trace"), list) else []
        retry_records = list(prior_state.get("retry_records", [])) if isinstance(prior_state.get("retry_records"), list) else []
        errors = list(prior_state.get("errors", [])) if isinstance(prior_state.get("errors"), list) else []
        resume_history = list(prior_state.get("resume_history", [])) if isinstance(prior_state.get("resume_history"), list) else []
        if resume_from_step_id:
            # 最新一次恢复放在最前面 便于调用方直接读取当前恢复入口.
            resume_history.insert(
                0,
                {
                    "resume_from_step_id": resume_from_step_id,
                    "mode": "step_resume",
                }
            )

        dependency_map: dict[str, set[str]] = {str(node["step_id"]): set() for node in nodes}
        incoming_edges_map: dict[str, list[dict[str, Any]]] = {str(node["step_id"]): [] for node in nodes}
        for node in nodes:
            step_id = str(node["step_id"])
            parent_id = node.get("parent_id")
            if isinstance(parent_id, str) and parent_id.strip():
                dependency_map[step_id].add(parent_id.strip())

        for edge in edges:
            from_step_id = edge.get("from_step_id")
            to_step_id = edge.get("to_step_id")
            if isinstance(from_step_id, str) and from_step_id.strip() and isinstance(to_step_id, str) and to_step_id.strip():
                dependency_map.setdefault(to_step_id.strip(), set()).add(from_step_id.strip())
                incoming_edges_map.setdefault(to_step_id.strip(), []).append(dict(edge))

        remaining = {str(node["step_id"]): node for node in nodes}
        node_statuses = self._build_node_statuses(nodes=nodes, completed=completed, skipped=skipped)
        final_output: dict[str, Any] = {}
        status = "completed"
        failed_step_id: str | None = None
        blocked_step_id: str | None = None

        for node in nodes:
            step_id = str(node["step_id"])
            if step_id in completed and not self._should_resume_node(step_id=step_id, resume_from_step_id=resume_from_step_id, dependency_map=dependency_map):
                node["status"] = "completed"
                node_statuses[step_id] = "completed"
                remaining.pop(step_id, None)
            elif step_id in skipped and not self._should_resume_node(step_id=step_id, resume_from_step_id=resume_from_step_id, dependency_map=dependency_map):
                node["status"] = "skipped"
                node_statuses[step_id] = "skipped"
                remaining.pop(step_id, None)
            elif self._should_resume_node(step_id=step_id, resume_from_step_id=resume_from_step_id, dependency_map=dependency_map):
                node["status"] = "pending"
                completed.discard(step_id)
                skipped.discard(step_id)
                node_outputs.pop(step_id, None)
                node_statuses[step_id] = "pending"

        # 清理需要从失败点之后重新执行的派生节点状态
        if resume_from_step_id:
            for step_id in list(node_outputs.keys()):
                if self._should_resume_node(step_id=step_id, resume_from_step_id=resume_from_step_id, dependency_map=dependency_map):
                    node_outputs.pop(step_id, None)
                    completed.discard(step_id)
                    skipped.discard(step_id)
                    node_statuses[step_id] = "pending"

        while remaining:
            terminal_steps = completed | skipped
            ready_nodes = [
                node
                for step_id, node in remaining.items()
                if dependency_map.get(step_id, set()).issubset(terminal_steps)
            ]
            executable_nodes: list[dict[str, Any]] = []
            skipped_nodes: list[tuple[dict[str, Any], dict[str, Any]]] = []
            for node in ready_nodes:
                readiness = self._evaluate_node_readiness(
                    task=task,
                    node=node,
                    incoming_edges=incoming_edges_map.get(str(node.get("step_id") or ""), []),
                    node_outputs=node_outputs,
                    node_statuses=node_statuses,
                )
                if readiness.get("status") == "skipped":
                    skipped_nodes.append((node, readiness))
                else:
                    executable_nodes.append(node)
            if not executable_nodes and not skipped_nodes:
                status = "failed"
                for node in remaining.values():
                    node["status"] = "blocked"
                errors.append("task_graph_stalled")
                break

            if self._on_node_started is not None:
                for node in executable_nodes:
                    await self._on_node_started(
                        node=dict(node),
                        trace_entry={},
                        node_result={},
                    )

            results = await asyncio.gather(
                *(
                    self._node_executor.execute_with_retry(
                        task=task,
                        node=node,
                        node_outputs=node_outputs,
                    )
                    for node in executable_nodes
                )
            )
            processed_nodes: list[dict[str, Any]] = list(executable_nodes)
            processed_results: list[dict[str, Any]] = list(results)
            for node, readiness in skipped_nodes:
                processed_nodes.append(node)
                processed_results.append(self._build_skipped_result(node=node, readiness=readiness))

            should_stop = False
            for node, node_result in zip(processed_nodes, processed_results):
                step_id = str(node["step_id"])
                node["status"] = node_result["status"]
                node_statuses[step_id] = node_result["status"]
                node["attempt_count"] = node_result.get("attempt_count", 1)
                if isinstance(node_result.get("evidence"), dict):
                    node["evidence"] = node_result["evidence"]
                if "output_ref" in node_result:
                    node["output_ref"] = node_result["output_ref"]
                if isinstance(node_result.get("command_id"), str) and node_result.get("command_id"):
                    node["command_id"] = node_result["command_id"]
                if isinstance(node_result.get("error"), str) and node_result.get("error"):
                    node["last_error"] = node_result["error"]
                if isinstance(node_result.get("failure_classification"), str) and node_result.get("failure_classification"):
                    node["failure_classification"] = node_result["failure_classification"]
                if isinstance(node_result.get("retry_records"), list):
                    retry_records.extend(node_result["retry_records"])
                if isinstance(node_result.get("receipt"), dict):
                    receipt = dict(node_result["receipt"])
                    receipts = [
                        existing
                        for existing in receipts
                        if not (
                            isinstance(existing, dict)
                            and (
                                str(existing.get("command_id") or "") == str(receipt.get("command_id") or "")
                                or str(existing.get("step_id") or "") == step_id
                            )
                        )
                    ]
                    receipt["step_id"] = step_id
                    receipts.append(receipt)
                if isinstance(node_result.get("approval_record"), dict):
                    approval_record = dict(node_result["approval_record"])
                    approval_records = [
                        existing
                        for existing in approval_records
                        if not (
                            isinstance(existing, dict)
                            and str(existing.get("approval_id") or "") == str(approval_record.get("approval_id") or "")
                        )
                    ]
                    approval_records.append(approval_record)

                execution_trace.append(
                    {
                        "step_id": step_id,
                        "kind": node.get("kind"),
                        "status": node_result["status"],
                        "target_agent": (
                            self._resolve_delegate_target(str(node.get("target_agent") or ""))
                            if node.get("kind") == "delegate"
                            else node.get("target_agent")
                        ),
                        "requested_target_agent": node.get("target_agent") if node.get("kind") == "delegate" else None,
                        "tool_name": node_result.get("tool_name") or node.get("tool_name"),
                        "command_id": node_result.get("command_id"),
                        "error": node_result.get("error"),
                        "attempt_count": node_result.get("attempt_count", 1),
                        "failure_classification": node_result.get("failure_classification"),
                        "started_at_ms": node_result.get("started_at_ms"),
                        "finished_at_ms": node_result.get("finished_at_ms"),
                        "latency_ms": node_result.get("latency_ms"),
                        "input_sources": node_result.get("input_sources", []),
                        "receipt_command_ids": node_result.get("receipt_command_ids", []),
                        "approval_record": node_result.get("approval_record"),
                    }
                )
                if self._on_node_completed is not None:
                    await self._on_node_completed(
                        node=dict(node),
                        trace_entry=dict(execution_trace[-1]),
                        node_result=dict(node_result),
                    )

                if node_result["status"] == "completed":
                    completed.add(step_id)
                    if isinstance(node_result.get("output"), dict):
                        node_outputs[step_id] = node_result["output"]
                    if isinstance(node_result.get("delegate_result"), ProactiveAgentResult):
                        delegate_results[node_result["delegate_result"].meta["agent_name"]] = node_result["delegate_result"]
                    if isinstance(node_result.get("final_output"), dict):
                        final_output = node_result["final_output"]
                elif node_result["status"] == "skipped":
                    skipped.add(step_id)
                elif node_result["status"] == "stopped":
                    completed.add(step_id)
                    should_stop = True
                    status = "stopped"
                    final_output = node_result.get("final_output") or {}
                elif node_result["status"] == "blocked":
                    should_stop = True
                    status = "blocked"
                    blocked_step_id = step_id
                    if isinstance(node_result.get("output"), dict):
                        node_outputs[step_id] = node_result["output"]
                    err = node_result.get("error")
                    if isinstance(err, str) and err:
                        errors.append(err)
                else:
                    status = "failed"
                    err = node_result.get("error")
                    if isinstance(err, str) and err:
                        errors.append(err)
                    failed_step_id = step_id

                remaining.pop(step_id, None)

            if should_stop or status == "failed":
                break

        if not final_output:
            final_output = self._build_fallback_final_output(task=task, delegate_results=delegate_results, receipts=receipts)

        return {
            "status": status,
            "task_graph": {
                "schema_version": graph.get("schema_version"),
                "nodes": nodes,
                "edges": edges,
            },
            "task_graph_execution": {
                "status": status,
                "completed_steps": sorted(completed),
                "skipped_steps": sorted(skipped),
                "failed_step_id": failed_step_id,
                "blocked_step_id": blocked_step_id,
                "errors": errors,
                "node_outputs": node_outputs,
                "delegate_outputs": {
                    agent_name: result.output
                    for agent_name, result in delegate_results.items()
                    if isinstance(result.output, dict)
                },
                "retry_records": retry_records,
                "resume_history": resume_history,
                "resume_ready": failed_step_id is not None,
                "receipts": receipts,
                "approval_records": approval_records,
                "trace": execution_trace,
            },
            "delegate_results": delegate_results,
            "receipts": receipts,
            "approval_records": approval_records,
            "final_output": final_output,
        }

    def _extract_completed_steps(self, state: dict[str, Any]) -> set[str]:
        raw = state.get("completed_steps")
        if not isinstance(raw, list):
            return set()
        return {str(step_id) for step_id in raw if isinstance(step_id, str) and step_id.strip()}

    def _extract_skipped_steps(self, state: dict[str, Any]) -> set[str]:
        raw = state.get("skipped_steps")
        if not isinstance(raw, list):
            return set()
        return {str(step_id) for step_id in raw if isinstance(step_id, str) and step_id.strip()}

    def _extract_node_outputs(self, state: dict[str, Any]) -> dict[str, dict[str, Any]]:
        raw = state.get("node_outputs")
        if not isinstance(raw, Mapping):
            return {}
        return {
            str(step_id): dict(payload)
            for step_id, payload in raw.items()
            if isinstance(step_id, str) and isinstance(payload, dict)
        }

    def _extract_receipts(self, state: dict[str, Any]) -> list[dict[str, Any]]:
        raw = state.get("receipts")
        if not isinstance(raw, list):
            return []
        return [dict(receipt) for receipt in raw if isinstance(receipt, dict)]

    def _extract_approval_records(self, state: dict[str, Any]) -> list[dict[str, Any]]:
        raw = state.get("approval_records")
        if not isinstance(raw, list):
            return []
        return [dict(record) for record in raw if isinstance(record, dict)]

    def _restore_delegate_results(self, state: dict[str, Any]) -> dict[str, ProactiveAgentResult]:
        raw = state.get("delegate_outputs")
        if not isinstance(raw, Mapping):
            return {}
        restored: dict[str, ProactiveAgentResult] = {}
        for agent_name, payload in raw.items():
            if isinstance(agent_name, str) and isinstance(payload, dict):
                restored[agent_name] = ProactiveAgentResult(
                    ok=True,
                    output=dict(payload),
                    meta={"agent_name": agent_name, "resumed": True},
                )
        return restored

    def _build_node_statuses(
        self,
        *,
        nodes: list[dict[str, Any]],
        completed: set[str],
        skipped: set[str],
    ) -> dict[str, str]:
        statuses: dict[str, str] = {}
        for node in nodes:
            if not isinstance(node, dict):
                continue
            step_id = str(node.get("step_id") or "")
            if not step_id:
                continue
            if step_id in completed:
                statuses[step_id] = "completed"
            elif step_id in skipped:
                statuses[step_id] = "skipped"
            else:
                statuses[step_id] = str(node.get("status") or "pending")
        return statuses

    def _should_resume_node(
        self,
        *,
        step_id: str,
        resume_from_step_id: str | None,
        dependency_map: dict[str, set[str]],
    ) -> bool:
        if not isinstance(resume_from_step_id, str) or not resume_from_step_id.strip():
            return False
        target = resume_from_step_id.strip()
        if step_id == target:
            return True
        return self._depends_on(step_id=step_id, target_step_id=target, dependency_map=dependency_map)

    def _depends_on(
        self,
        *,
        step_id: str,
        target_step_id: str,
        dependency_map: dict[str, set[str]],
    ) -> bool:
        stack = list(dependency_map.get(step_id, set()))
        visited: set[str] = set()
        while stack:
            current = stack.pop()
            if current in visited:
                continue
            visited.add(current)
            if current == target_step_id:
                return True
            stack.extend(dependency_map.get(current, set()))
        return False

    def _evaluate_node_readiness(
        self,
        *,
        task: dict[str, Any],
        node: dict[str, Any],
        incoming_edges: list[dict[str, Any]],
        node_outputs: dict[str, dict[str, Any]],
        node_statuses: dict[str, str],
    ) -> dict[str, Any]:
        node_condition = node.get("condition")
        if node_condition is not None:
            passed = self._evaluate_condition(
                condition=node_condition,
                context={
                    "task": task,
                    "upstream_outputs": node_outputs,
                    "upstream_statuses": node_statuses,
                },
                parent_step_id=None,
                node_statuses=node_statuses,
            )
            if not passed:
                return {
                    "status": "skipped",
                    "reason": f"node_condition_false:{str(node.get('step_id') or '')}",
                }

        for edge in incoming_edges:
            parent_step_id = str(edge.get("from_step_id") or "").strip()
            if not parent_step_id:
                continue
            passed = self._evaluate_condition(
                condition=edge.get("condition"),
                context=self._build_condition_context(
                    parent_step_id=parent_step_id,
                    node_outputs=node_outputs,
                    node_statuses=node_statuses,
                ),
                parent_step_id=parent_step_id,
                node_statuses=node_statuses,
            )
            if not passed:
                return {
                    "status": "skipped",
                    "reason": f"edge_condition_false:{parent_step_id}->{str(node.get('step_id') or '')}",
                }
        return {"status": "ready"}

    def _evaluate_condition(
        self,
        *,
        condition: Any,
        context: dict[str, Any],
        parent_step_id: str | None,
        node_statuses: dict[str, str],
    ) -> bool:
        if condition in (None, "", True):
            return True
        if condition is False:
            return False
        if isinstance(condition, dict):
            op = str(condition.get("op") or "always").strip().lower()
            if op == "always":
                return True
            if op == "status_in":
                values = condition.get("value") or condition.get("values") or []
                allowed = {str(item).strip().lower() for item in values if isinstance(item, str)}
                current = str(context.get("status") or "").strip().lower()
                return current in allowed
            path = str(condition.get("path") or "").strip()
            actual = self._resolve_condition_value(context=context, path=path)
            if op == "truthy":
                return bool(actual)
            if op == "falsy":
                return not bool(actual)
            expected = condition.get("value")
            if op == "equals":
                return actual == expected
            if op == "not_equals":
                return actual != expected
            return bool(actual)

        raw = str(condition).strip()
        if not raw:
            return True
        lowered = raw.lower()
        if lowered == "always":
            return True
        if lowered in {"critic_rejected", "manual_resume", "new_evidence"}:
            return True
        if lowered in {"on_success", "success", "completed"}:
            if parent_step_id is None:
                return True
            return str(node_statuses.get(parent_step_id) or "").lower() == "completed"
        if lowered in {"on_skipped", "skipped"}:
            if parent_step_id is None:
                return False
            return str(node_statuses.get(parent_step_id) or "").lower() == "skipped"
        if lowered in {"on_failure", "failure", "failed"}:
            if parent_step_id is None:
                return False
            return str(node_statuses.get(parent_step_id) or "").lower() == "failed"
        if lowered.startswith("truthy:"):
            return bool(self._resolve_condition_value(context=context, path=raw.split(":", 1)[1]))
        if lowered.startswith("falsy:"):
            return not bool(self._resolve_condition_value(context=context, path=raw.split(":", 1)[1]))
        if lowered.startswith("equals:"):
            path, expected = self._split_condition_path_and_value(raw[len("equals:") :])
            return self._resolve_condition_value(context=context, path=path) == self._parse_condition_value(expected)
        if lowered.startswith("not_equals:"):
            path, expected = self._split_condition_path_and_value(raw[len("not_equals:") :])
            return self._resolve_condition_value(context=context, path=path) != self._parse_condition_value(expected)
        return bool(self._resolve_condition_value(context=context, path=raw))

    def _build_condition_context(
        self,
        *,
        parent_step_id: str,
        node_outputs: dict[str, dict[str, Any]],
        node_statuses: dict[str, str],
    ) -> dict[str, Any]:
        payload = dict(node_outputs.get(parent_step_id) or {})
        return {
            "status": node_statuses.get(parent_step_id),
            "step_id": parent_step_id,
            "output": payload,
            **payload,
        }

    @staticmethod
    def _split_condition_path_and_value(raw: str) -> tuple[str, str]:
        path, _, expected = raw.partition(":")
        return path.strip(), expected.strip()

    @staticmethod
    def _parse_condition_value(raw: str) -> Any:
        lowered = raw.lower()
        if lowered in {"true", "false", "none", "null"}:
            return {"true": True, "false": False, "none": None, "null": None}[lowered]
        try:
            return literal_eval(raw)
        except (ValueError, SyntaxError):
            return raw

    @staticmethod
    def _resolve_condition_value(*, context: dict[str, Any], path: str) -> Any:
        if not path:
            return context
        current: Any = context
        for part in path.split("."):
            key = part.strip()
            if not key:
                continue
            if isinstance(current, Mapping) and key in current:
                current = current[key]
                continue
            return None
        return current

    def _build_skipped_result(
        self,
        *,
        node: dict[str, Any],
        readiness: dict[str, Any],
    ) -> dict[str, Any]:
        now_ms = time.time() * 1000
        reason = str(readiness.get("reason") or "condition_false")
        summary = str(node.get("reason") or node.get("instruction") or "条件不满足 已跳过")
        return {
            "status": "skipped",
            "output": {
                "summary": f"{summary} | skipped:{reason}",
            },
            "error": None,
            "failure_classification": None,
            "started_at_ms": now_ms,
            "finished_at_ms": now_ms,
            "latency_ms": 0.0,
            "input_sources": [str(edge.get("from_step_id") or "") for edge in readiness.get("incoming_edges", []) if isinstance(edge, dict)],
            "evidence": {
                "task_graph_step_id": str(node.get("step_id") or ""),
                "skip_reason": reason,
            },
        }

    def _build_fallback_final_output(
        self,
        *,
        task: dict[str, Any],
        delegate_results: dict[str, ProactiveAgentResult],
        receipts: list[dict[str, Any]],
    ) -> dict[str, Any]:
        node_outputs = {
            name: result.output
            for name, result in delegate_results.items()
            if isinstance(result.output, dict)
        }
        for receipt in receipts:
            if not isinstance(receipt, dict):
                continue
            command_id = receipt.get("command_id")
            if isinstance(command_id, str) and command_id:
                node_outputs[command_id] = {
                    "summary": f"tool {receipt.get('tool_name')} completed cmd:{command_id}",
                    "receipt_command_ids": [command_id],
                }
        return self._node_executor._build_finalize_output(
            task=task,
            node={"reason": "自动生成最终结论"},
            node_outputs=node_outputs,
        )

__all__ = ["TaskGraphExecutor"]
