"""
工作流阶段 5-7: 终审 / 记忆与 Skill 生命周期 / 结果构建与保存.

从 proactive_workflow._run_internal 提取:
- Step 5: 汇总 delegate 结果 + Critic 终审 (receipt 归一化)
- Step 6: 运行产物记忆持久化 + Skill 置信度更新 / 修订 / 提议
- Step 7: 构建最终结果 + 审批记忆 / run context 保存
"""

from __future__ import annotations

import logging
from typing import Any

from riskagent_backend.orchestration.workflow_agent_results import replace_output
from riskagent_backend.orchestration.workflow_events import requires_manual_approval
from riskagent_backend.orchestration.workflow_planning import call_critic_review
from riskagent_backend.orchestration.workflow_result_builder import (
    build_workflow_result,
    normalize_critic_final_output,
)
from riskagent_backend.orchestration.workflow_state import WorkflowRunState
from riskagent_backend.proactive_agents import ProactiveAgentResult
from riskagent_backend.skills import SkillProposer, SkillReviser

logger = logging.getLogger(__name__)


async def run_finalization_stage(
    *,
    state: WorkflowRunState,
    runtime_task_store: Any,
    memory_store: Any,
    critic_agent: Any,
    skill_store: Any,
    skill_usage_tracker: Any,
) -> dict[str, Any]:
    """Step 5-7: 终审 + 记忆/Skill 生命周期 + 结果构建与保存."""
    task = state.task
    run_id = state.run_id
    task_id = state.task_id
    memory_enabled = state.memory_enabled
    execution_result = state.execution_result
    orchestrator_result = state.orchestrator_result
    critic_result = state.critic_result

    # ===== Step 5: Results Aggregation & Final Review =====
    delegate_results = execution_result.get("delegate_results", {})
    state.engineer_result = delegate_results.get("system_engineer") or delegate_results.get("engineer") or ProactiveAgentResult(
        ok=True,
        output={},
    )
    state.analyst_result = delegate_results.get("risk_analyst") or delegate_results.get("analyst") or ProactiveAgentResult(
        ok=True,
        output={},
    )
    await runtime_task_store.set_current_agent(task_id=task_id, agent_id="critic")
    critic_final_result = await call_critic_review(
        critic_agent=critic_agent,
        task=task,
        orchestrator=orchestrator_result.output if isinstance(orchestrator_result.output, dict) else {},
        receipts=execution_result.get("receipts", []),
        final_output=execution_result.get("final_output", {}),
        phase="final_review",
    )
    critic_final_output = normalize_critic_final_output(
        critic_output=critic_final_result.output,
        receipts=execution_result.get("receipts", []),
    )
    critic_final_result = replace_output(
        critic_final_result,
        output=critic_final_output,
    )
    state.critic_final_result = critic_final_result

    # ===== Step 6: Memory Persistence & Skill Lifecycle =====
    persisted_memory = {
        "run_summary": {},
        "summary_entry": None,
    }
    if memory_enabled and not requires_manual_approval(
        critic_output=critic_result.output,
        receipts=execution_result.get("receipts", []),
        approval_records=execution_result.get("approval_records", []),
    ):
        try:
            persisted_memory = await memory_store.persist_run_artifacts(
                run_id=run_id,
                task=task,
                final_output=execution_result.get("final_output", {}),
                critic_final=critic_final_result.output,
            )
        except Exception as exc:
            logger.warning("[ProactiveWorkflow] Persist run artifacts degraded: %s", exc)
    state.persisted_memory = persisted_memory

    # Skill 置信度更新: 基于执行结果和 Critic 评审更新被注入 Skill 的置信度
    tracked_skill_ids = skill_usage_tracker.get_tracked_skills(run_id)
    try:
        execution_had_failures = execution_result.get("status") != "completed"
        skill_updates = await skill_usage_tracker.update_after_execution(
            run_id=run_id,
            execution_success=not execution_had_failures,
            critic_ok=critic_final_result.output.get("ok", False),
        )
        for update in skill_updates:
            logger.info(
                "Skill %s confidence updated: %.2f -> %.2f (status: %s -> %s)",
                update["skill_id"],
                update["old_confidence"],
                update["new_confidence"],
                update["old_status"],
                update["new_status"],
            )
    except Exception as exc:
        logger.warning("Skill confidence update failed: %s", exc)
    finally:
        skill_usage_tracker.clear_tracking(run_id)

    # Skill 改进闭环: 当 Skill 被使用但产生次优结果时, 提议修订
    try:
        reviser = SkillReviser(skill_store)
        for skill_id in tracked_skill_ids:
            proposal = await reviser.check_and_propose_revision(
                skill_id=skill_id,
                run_id=run_id,
                execution_result=execution_result.get("final_output", {}),
                critic_final=critic_final_result.output,
            )
            if proposal:
                await reviser.apply_revision(skill_id=skill_id, proposal=proposal)
                logger.info("Skill %s revised: %s", skill_id, proposal.reason)
    except Exception as exc:
        logger.warning("Skill revision failed: %s", exc)

    # SkillProposer: 从高质量完成的 run 中提取可复用模式
    try:
        skill_proposer = SkillProposer(skill_store)
        skill_proposal = await skill_proposer.propose(
            run_id=run_id,
            task=task,
            critic_final=critic_final_result.output,
            orchestrator_output=(
                orchestrator_result.output
                if isinstance(orchestrator_result.output, dict)
                else {}
            ),
            receipts=execution_result.get("receipts", []),
        )
        logger.info("skill_proposal: %s", skill_proposal)
    except Exception as exc:
        logger.warning("Skill proposal failed: %s", exc)

    # ===== Step 7: Result Building & Context Save =====
    result = build_workflow_result(
        run_id=run_id,
        task=task,
        memory_enabled=memory_enabled,
        private_memory_enabled=state.private_memory_enabled,
        planning_memory=state.planning_memory,
        resume_request=state.resume_request,
        persisted_memory=persisted_memory,
        run_context=state.run_context,
        intent_result=state.intent_result,
        orchestrator_result=orchestrator_result,
        critic_result=critic_result,
        critic_final_result=critic_final_result,
        engineer_result=state.engineer_result,
        analyst_result=state.analyst_result,
        execution_result=execution_result,
        replan_details=state.replan_details,
        route_decision=state.route_decision,
        start_time=state.start_time,
    )
    if memory_enabled and isinstance(result.get("approval_trace"), list) and result.get("approval_trace"):
        try:
            result["approval_memory"] = await memory_store.persist_approval_memory(
                run_id=run_id,
                task=task,
                approval_records=result.get("approval_trace", []),
            )
        except Exception as exc:
            logger.warning("[ProactiveWorkflow] Persist approval memory degraded: %s", exc)
    if memory_enabled:
        try:
            source_event = state.source_event
            await memory_store.save_run_context(
                run_id=run_id,
                event_id=str(
                    (source_event or {}).get("event_id")
                    or task.get("task_id")
                    or run_id
                ),
                data={
                    "status": result.get("status"),
                    "entry_type": result.get("entry_type"),
                    "run_context": result.get("run_context", {}),
                    "task": task,
                    "source_event": source_event or {},
                    "route_decision": state.route_decision or {},
                    "intent": result.get("intent", {}),
                    "task_graph": result.get("task_graph", {}),
                    "task_graph_execution": result.get("task_graph_execution", {}),
                    "receipts": result.get("receipts", []),
                    "approval_trace": result.get("approval_trace", []),
                    "memory_hits": result.get("memory_hits", []),
                    "planning_memory": result.get("planning_memory", {}),
                    "shared_memory_board": result.get("shared_memory_board", []),
                    "private_memory_state": result.get("private_memory_state", {}),
                    "run_summary": result.get("run_summary", {}),
                    "final_output": result.get("final_output", {}),
                },
            )
        except Exception as exc:
            logger.warning("[ProactiveWorkflow] Save run context degraded: %s", exc)
    await runtime_task_store.set_current_agent(task_id=task_id, agent_id=None)

    return result
