"""
工作流阶段 4: TaskGraph 执行与运行时 Replan.

从 proactive_workflow._run_internal 提取:
- TaskGraphExecutor 构造与节点回调 (进度同步 / 工作记忆记录 / 会话分段)
- 执行失败后的运行时 replan (重新规划 + 重新执行)
"""

from __future__ import annotations

import logging
from typing import Any

from riskagent_backend.orchestration.task_graph_executor import TaskGraphExecutor
from riskagent_backend.orchestration.workflow_agent_results import (
    ensure_proactive_result,
    extend_orchestrator_context,
    normalize_orchestrator_result,
    sync_planned_task_graph,
)
from riskagent_backend.orchestration.workflow_planning import (
    build_orchestrator_context,
)
from riskagent_backend.orchestration.workflow_resume import (
    build_runtime_replan_reason,
    extract_execution_failure,
    should_runtime_replan,
)
from riskagent_backend.orchestration.workflow_state import WorkflowRunState

logger = logging.getLogger(__name__)


async def run_execution_stage(
    *,
    state: WorkflowRunState,
    runtime_task_store: Any,
    memory_store: Any,
    session_segmenter: Any,
    engineer_agent: Any,
    analyst_agent: Any,
    orchestrator_agent: Any,
    skill_store: Any,
    skill_usage_tracker: Any,
) -> None:
    """Step 4: TaskGraph Execution."""
    task = state.task
    run_id = state.run_id
    task_id = state.task_id
    intent_result = state.intent_result
    critic_result = state.critic_result
    completed_step_records: list[dict[str, Any]] = []
    current_segment_id: str | None = None

    await runtime_task_store.set_current_agent(task_id=task_id, agent_id=None)
    await runtime_task_store.sync_task_graph(
        task_id=task_id,
        task_graph=state.active_task_graph,
        execution_state=state.execution_state if isinstance(state.execution_state, dict) else None,
    )

    async def _on_node_started(*, node, trace_entry, node_result) -> None:
        del trace_entry
        del node_result
        await runtime_task_store.mark_step_started(
            task_id=task_id,
            node=node,
        )

    async def _on_node_completed(*, node, trace_entry, node_result) -> None:
        nonlocal current_segment_id
        await runtime_task_store.mark_step_completed(
            task_id=task_id,
            node=node,
            trace_entry=trace_entry,
            node_result=node_result,
        )
        # Memory recording
        if state.memory_enabled:
            try:
                await memory_store.record_working_memory(
                    run_id=run_id,
                    task=task,
                    trace_entry=trace_entry,
                    node=node,
                    node_result=node_result,
                    private_memory_enabled=state.private_memory_enabled,
                )
            except Exception as exc:
                logger.warning("[ProactiveWorkflow] Record working memory degraded: %s", exc)
        # Session segmentation
        try:
            completed_step_records.append({
                "step_id": str(node.get("step_id") or ""),
                "kind": node.get("kind"),
                "status": trace_entry.get("status"),
                "tool_name": trace_entry.get("tool_name"),
                "target_agent": trace_entry.get("target_agent"),
            })
            step_count = len(completed_step_records)
            if session_segmenter.should_segment(step_count):
                checkpoint = await session_segmenter.create_checkpoint(
                    run_id=run_id,
                    step_count=step_count,
                    steps=list(completed_step_records),
                    parent_segment_id=current_segment_id,
                    context={
                        "intent": intent_result.output,
                        "task": {
                            k: v
                            for k, v in task.items()
                            if k in ("task_id", "content", "source")
                        },
                    },
                )
                current_segment_id = checkpoint.segment_id
                completed_step_records.clear()
                logger.info(
                    "Session segmented at step %d: segment %d",
                    step_count,
                    checkpoint.segment_index,
                )
        except Exception as seg_exc:
            logger.warning("Session segmentation failed, continuing: %s", seg_exc)

    executor = TaskGraphExecutor(
        delegate_handlers={
            "system_engineer": engineer_agent.analyze_task,
            "engineer": engineer_agent.analyze_task,
            "risk_analyst": analyst_agent.analyze_task,
            "analyst": analyst_agent.analyze_task,
        },
        on_node_started=_on_node_started,
        on_node_completed=_on_node_completed,
    )
    execution_result = await executor.execute(
        task=task,
        task_graph=state.active_task_graph,
        execution_state=state.execution_state,
        resume_from_step_id=state.resume_from_step_id if isinstance(state.resume_from_step_id, str) else None,
    )
    runtime_replan = await _maybe_runtime_replan(
        state=state,
        runtime_task_store=runtime_task_store,
        orchestrator_agent=orchestrator_agent,
        skill_store=skill_store,
        skill_usage_tracker=skill_usage_tracker,
        execution_result=execution_result,
        executor=executor,
    )
    if runtime_replan is not None:
        state.active_task_graph = runtime_replan["task_graph"]
        execution_result = runtime_replan["execution_result"]
        state.replan_details = runtime_replan["replan_details"]
        await runtime_task_store.sync_task_graph(
            task_id=task_id,
            task_graph=state.active_task_graph,
            execution_state=execution_result.get("task_graph_execution") if isinstance(execution_result.get("task_graph_execution"), dict) else None,
        )
    logger.info(
        "[ProactiveWorkflow] TaskGraph execution completed with status=%s",
        execution_result.get("status"),
    )
    state.execution_result = execution_result


async def _maybe_runtime_replan(
    *,
    state: WorkflowRunState,
    runtime_task_store: Any,
    orchestrator_agent: Any,
    skill_store: Any,
    skill_usage_tracker: Any,
    execution_result: dict[str, Any],
    executor: TaskGraphExecutor,
) -> dict[str, Any] | None:
    """执行失败时触发运行时 replan: 重新规划 + 重新执行."""
    task = state.task
    if state.is_resume:
        return None
    if not should_runtime_replan(execution_result):
        return None

    reason = build_runtime_replan_reason(execution_result)
    runtime_replan_base = await build_orchestrator_context(
        skill_store=skill_store,
        skill_usage_tracker=skill_usage_tracker,
        phase="runtime_replan",
        task=task,
        intent=state.intent_result.output,
        memory_enabled=state.memory_enabled,
        planning_memory=state.planning_memory,
        run_id=state.run_id,
    )
    replan_result = normalize_orchestrator_result(
        ensure_proactive_result(
            await orchestrator_agent.orchestrate(
                task=task,
                context=extend_orchestrator_context(
                    task=task,
                    base_context={
                        "phase": "runtime_replan",
                        **runtime_replan_base,
                        "critic": state.critic_result.output,
                        "prior_task_graph": state.active_task_graph,
                        "execution_failure": extract_execution_failure(execution_result),
                    },
                ),
            ),
            agent_name="orchestrator",
        )
    )
    await sync_planned_task_graph(
        runtime_task_store=runtime_task_store,
        task_id=state.task_id,
        task_graph=dict(replan_result.output.get("task_graph") or {}),
        execution_state=execution_result.get("task_graph_execution") if isinstance(execution_result.get("task_graph_execution"), dict) else None,
    )
    runtime_execution = await executor.execute(
        task=task,
        task_graph=replan_result.output,
    )
    return {
        "task_graph": replan_result.output,
        "execution_result": runtime_execution,
        "replan_details": {
            "trigger": "execution_failed",
            "reason": reason,
            "orchestrator_plan": replan_result.output,
            "prior_execution": extract_execution_failure(execution_result),
        },
    }
