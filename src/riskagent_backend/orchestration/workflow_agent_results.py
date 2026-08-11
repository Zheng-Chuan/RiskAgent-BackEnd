"""
工作流 Agent 结果处理纯函数.

从 proactive_workflow.py 提取, 负责 Agent 结果的归一化/校验/占位构造,
不依赖任何工作流实例状态.
"""

from __future__ import annotations

from typing import Any

from riskagent_backend.contracts.agent_outputs import (
    normalize_orchestrator_output,
    validate_orchestrator_output,
)
from riskagent_backend.contracts.task_graph import validate_task_graph
from riskagent_backend.proactive_agents import ProactiveAgentResult


def ensure_proactive_result(
    result: Any,
    *,
    agent_name: str,
) -> ProactiveAgentResult:
    """将任意 Agent 返回值适配为 ProactiveAgentResult."""
    if isinstance(result, ProactiveAgentResult):
        return result
    output = result.output if isinstance(getattr(result, "output", None), dict) else {}
    usage = result.usage if isinstance(getattr(result, "usage", None), dict) else None
    meta = result.meta if isinstance(getattr(result, "meta", None), dict) else {}
    meta = dict(meta or {})
    meta.setdefault("agent_name", agent_name)
    return ProactiveAgentResult(
        ok=bool(getattr(result, "ok", False)),
        output=output,
        usage=usage,
        meta=meta,
        react_steps=list(getattr(result, "react_steps", []) or []),
        bdi_state=dict(getattr(result, "bdi_state", {}) or {}),
        llm_interactions=list(getattr(result, "llm_interactions", []) or []),
    )


def replace_output(
    result: ProactiveAgentResult,
    *,
    output: dict[str, Any],
) -> ProactiveAgentResult:
    """保留其余字段, 仅替换 output."""
    return ProactiveAgentResult(
        ok=result.ok,
        output=output,
        usage=result.usage,
        meta=result.meta,
        react_steps=result.react_steps,
        bdi_state=result.bdi_state,
        llm_interactions=result.llm_interactions,
    )


def require_successful_agent_result(
    result: ProactiveAgentResult,
    *,
    agent_name: str,
) -> ProactiveAgentResult:
    """要求 Agent 结果成功, 否则抛出带错误原因的 RuntimeError."""
    if result.ok:
        return result
    output = result.output if isinstance(result.output, dict) else {}
    if isinstance(output.get("error"), str) and output.get("error"):
        raise RuntimeError(f"{agent_name.upper()}_FAILED: {output.get('error')}")
    meta = result.meta if isinstance(result.meta, dict) else {}
    if isinstance(meta.get("error"), str) and meta.get("error"):
        raise RuntimeError(f"{agent_name.upper()}_FAILED: {meta.get('error')}")
    raise RuntimeError(f"{agent_name.upper()}_FAILED: unknown_error")


def new_placeholder_result(*, output: dict[str, Any], agent_name: str) -> ProactiveAgentResult:
    """构造恢复执行时的占位结果."""
    return ProactiveAgentResult(
        ok=True,
        output=output if isinstance(output, dict) else {},
        meta={"agent_name": agent_name, "placeholder": True},
    )


def build_orchestrator_failure_reason(
    *,
    result: ProactiveAgentResult,
) -> str:
    """从编排结果中提取失败原因."""
    output = result.output if isinstance(result.output, dict) else {}
    if isinstance(output.get("error"), str) and output.get("error"):
        return f"ORCHESTRATOR_FAILED: {output.get('error')}"
    meta = result.meta if isinstance(result.meta, dict) else {}
    if isinstance(meta.get("error"), str) and meta.get("error"):
        return f"ORCHESTRATOR_FAILED: {meta.get('error')}"
    return "ORCHESTRATOR_FAILED: unknown_error"


def normalize_orchestrator_result(
    result: ProactiveAgentResult,
) -> ProactiveAgentResult:
    """严格校验编排结果, 禁止 fallback 或隐式降级.

    归一化优先: 先通过 normalize 补全缺失字段 (evidence refs,
    tool_call tool_name 等), 再对归一化后的输出做验证.
    这样主动监控场景下 LLM 未输出 tool_name / evidence.fields
    时不会直接失败.
    """
    if not result.ok:
        raise RuntimeError(build_orchestrator_failure_reason(result=result))

    raw_output = result.output if isinstance(result.output, dict) else {}
    if not isinstance(raw_output.get("plan_steps"), list) or not raw_output.get("plan_steps"):
        raise RuntimeError("ORCHESTRATOR_PLAN_STEPS_MISSING")

    # 先归一化, 再验证 — normalize 会补全 evidence refs 和 tool_call tool_name
    normalized_output = normalize_orchestrator_output(raw_output)

    is_valid_output, output_errors = validate_orchestrator_output(normalized_output)
    if not is_valid_output:
        raise RuntimeError(
            "ORCHESTRATOR_OUTPUT_INVALID: " + "; ".join(output_errors)
        )

    task_graph = normalized_output.get("task_graph") if isinstance(normalized_output.get("task_graph"), dict) else {}
    nodes = task_graph.get("nodes") if isinstance(task_graph.get("nodes"), list) else []
    if not nodes:
        raise RuntimeError("ORCHESTRATOR_TASK_GRAPH_EMPTY")

    is_valid_graph, graph_errors = validate_task_graph(task_graph)
    if not is_valid_graph:
        raise RuntimeError(
            "ORCHESTRATOR_TASK_GRAPH_INVALID: " + "; ".join(graph_errors)
        )

    plan_step_ids = [
        str(step.get("step_id") or "")
        for step in raw_output.get("plan_steps", [])
        if isinstance(step, dict) and str(step.get("step_id") or "")
    ]
    graph_node_ids = [
        str(node.get("step_id") or node.get("id") or "")
        for node in nodes
        if isinstance(node, dict) and str(node.get("step_id") or node.get("id") or "")
    ]
    if plan_step_ids != graph_node_ids:
        raise RuntimeError(
            "ORCHESTRATOR_PLAN_GRAPH_MISMATCH: "
            f"plan_steps={plan_step_ids}, graph_nodes={graph_node_ids}"
        )

    return replace_output(result, output=normalized_output)


def extend_orchestrator_context(
    *,
    task: dict[str, Any],
    base_context: dict[str, Any],
) -> dict[str, Any]:
    """向编排上下文追加 run/event/resume 上下文."""
    context = dict(base_context)
    if isinstance(task.get("run_context"), dict):
        context["run_context"] = dict(task.get("run_context", {}))
    if isinstance(task.get("event_context"), dict):
        context["event_context"] = dict(task.get("event_context", {}))
    if isinstance(task.get("resume_context"), dict):
        context["resume_context"] = dict(task.get("resume_context", {}))
    return context


async def sync_planned_task_graph(
    *,
    runtime_task_store: Any,
    task_id: str,
    task_graph: dict[str, Any],
    execution_state: dict[str, Any] | None = None,
) -> None:
    """写入规划图后立即回读校验, 一旦错位直接失败."""
    if not isinstance(task_graph, dict):
        raise RuntimeError("TASK_GRAPH_SYNC_INPUT_INVALID")

    expected_nodes = task_graph.get("nodes") if isinstance(task_graph.get("nodes"), list) else []
    expected_edges = task_graph.get("edges") if isinstance(task_graph.get("edges"), list) else []
    if not expected_nodes:
        raise RuntimeError("TASK_GRAPH_SYNC_EMPTY_GRAPH")

    await runtime_task_store.sync_task_graph(
        task_id=task_id,
        task_graph=task_graph,
        execution_state=execution_state,
    )

    runtime_snapshot = await runtime_task_store.get_task(task_id=task_id)
    if not isinstance(runtime_snapshot, dict):
        raise RuntimeError(f"TASK_GRAPH_RUNTIME_MISSING: task_id={task_id}")
    runtime_graph = runtime_snapshot.get("graph") if isinstance(runtime_snapshot.get("graph"), dict) else {}
    actual_nodes = runtime_graph.get("nodes") if isinstance(runtime_graph.get("nodes"), list) else []
    actual_edges = runtime_graph.get("edges") if isinstance(runtime_graph.get("edges"), list) else []

    expected_node_ids = [
        str(node.get("step_id") or node.get("id") or "")
        for node in expected_nodes
        if isinstance(node, dict) and str(node.get("step_id") or node.get("id") or "")
    ]
    actual_node_ids = [
        str(node.get("id") or node.get("step_id") or "")
        for node in actual_nodes
        if isinstance(node, dict) and str(node.get("id") or node.get("step_id") or "")
    ]
    expected_edge_ids = [
        f"{edge.get('from_step_id')}->{edge.get('to_step_id')}"
        for edge in expected_edges
        if isinstance(edge, dict)
        and str(edge.get("from_step_id") or "")
        and str(edge.get("to_step_id") or "")
    ]
    actual_edge_ids = [
        f"{edge.get('source') or edge.get('from_step_id')}->{edge.get('target') or edge.get('to_step_id')}"
        for edge in actual_edges
        if isinstance(edge, dict)
        and str(edge.get("source") or edge.get("from_step_id") or "")
        and str(edge.get("target") or edge.get("to_step_id") or "")
    ]
    if expected_node_ids != actual_node_ids or expected_edge_ids != actual_edge_ids:
        raise RuntimeError(
            "TASK_GRAPH_RUNTIME_MISMATCH: "
            f"expected_nodes={expected_node_ids}, actual_nodes={actual_node_ids}, "
            f"expected_edges={expected_edge_ids}, actual_edges={actual_edge_ids}"
        )
