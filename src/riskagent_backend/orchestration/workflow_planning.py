"""
工作流阶段 3: 规划 (Orchestrator + Critic + Replan).

从 proactive_workflow._run_internal 提取:
- Orchestrator 上下文构建 (含 Skill 注入与使用跟踪)
- Critic 计划评审调用 (兼容旧签名的逐级降级)
- 首次规划 / resume 占位 / Critic 拒绝后的 replan
"""

from __future__ import annotations

import logging
from typing import Any

from riskagent_backend.contracts.task_graph import append_replan_subgraph
from riskagent_backend.orchestration.workflow_agent_results import (
    ensure_proactive_result,
    extend_orchestrator_context,
    new_placeholder_result,
    normalize_orchestrator_result,
    sync_planned_task_graph,
)
from riskagent_backend.orchestration.workflow_memory import persist_plan_memory
from riskagent_backend.orchestration.workflow_resume import (
    build_replan_reason,
    should_replan,
)
from riskagent_backend.orchestration.workflow_state import WorkflowRunState
from riskagent_backend.skills import SkillInjector

logger = logging.getLogger(__name__)


async def build_orchestrator_context(
    *,
    skill_store: Any,
    skill_usage_tracker: Any,
    phase: str,
    task: dict[str, Any],
    intent: dict[str, Any],
    memory_enabled: bool,
    planning_memory: dict[str, Any],
    run_id: str | None = None,
) -> dict[str, Any]:
    """构建编排上下文: phase/intent + 规划记忆摘要 + Skill 注入."""
    context: dict[str, Any] = {"phase": phase, "intent": intent}
    if memory_enabled:
        context["memory"] = planning_memory.get("summary", {})
    # Skill 注入: 以结构化 few-shot 形式增强规划能力
    try:
        skill_injector = SkillInjector(skill_store)
        intent_str: str | None = None
        if isinstance(intent, dict):
            intent_str = intent.get("primary_intent_type") or intent.get("type")
        skill_payload = await skill_injector.retrieve_applicable_skills(
            task=task,
            intent=intent_str if isinstance(intent_str, str) else None,
            skill_enabled=memory_enabled,
        )
        context["skills"] = skill_payload
        # Skill 使用跟踪: 记录被注入的 skill_id 用于后续置信度更新
        if run_id is not None:
            for skill in skill_payload.get("skills", []):
                skill_id = skill.get("skill_id")
                if skill_id:
                    skill_usage_tracker.track_usage(
                        skill_id, run_id=run_id, phase=phase
                    )
    except Exception as exc:
        logger.warning("Skill injection failed: %s", exc)
        context["skills"] = {
            "skill_enabled": memory_enabled,
            "skills": [],
            "skill_count": 0,
            "injection_summary": f"Skill injection error: {exc}",
        }
    return context


async def call_critic_review(
    *,
    critic_agent: Any,
    task: dict[str, Any],
    orchestrator: dict[str, Any],
    receipts: list[dict[str, Any]] | None = None,
    final_output: dict[str, Any] | None = None,
    phase: str = "plan_review",
) -> Any:
    """兼容旧签名并统一向 critic 透传 receipt 上下文."""
    try:
        return ensure_proactive_result(
            await critic_agent.review(
                task=task,
                orchestrator=orchestrator,
                receipts=receipts,
                final_output=final_output,
                phase=phase,
            ),
            agent_name="critic",
        )
    except TypeError as exc:
        if "unexpected keyword argument" not in str(exc):
            raise
        try:
            return ensure_proactive_result(
                await critic_agent.review(
                    task=task,
                    orchestrator=orchestrator,
                    receipts=receipts,
                ),
                agent_name="critic",
            )
        except TypeError as inner_exc:
            if "unexpected keyword argument" not in str(inner_exc):
                raise
            return ensure_proactive_result(
                await critic_agent.review(
                    task=task,
                    orchestrator=orchestrator,
                ),
                agent_name="critic",
            )


async def run_planning_stage(
    *,
    state: WorkflowRunState,
    orchestrator_agent: Any,
    critic_agent: Any,
    runtime_task_store: Any,
    skill_store: Any,
    skill_usage_tracker: Any,
    memory_store: Any,
) -> None:
    """Step 3: Planning (Orchestrator + Critic + Replan)."""
    task = state.task
    run_id = state.run_id
    task_id = state.task_id
    replan_details: dict[str, Any] | None = None
    state.execution_state = state.resume_request.get("execution_state") if state.is_resume else None
    state.resume_from_step_id = (
        state.resume_request.get("resume_from_step_id")
        or (state.execution_state.get("failed_step_id") if isinstance(state.execution_state, dict) else None)
    ) if state.is_resume else None

    if state.is_resume:
        state.orchestrator_result = new_placeholder_result(
            output=state.resume_request.get("task_graph") if isinstance(state.resume_request.get("task_graph"), dict) else {},
            agent_name="orchestrator",
        )
        state.critic_result = new_placeholder_result(
            output={"ok": True, "resumed": True},
            agent_name="critic",
        )
        state.active_task_graph = state.resume_request.get("task_graph") if isinstance(state.resume_request.get("task_graph"), dict) else {}
        replan_details = {
            "trigger": "manual_resume",
            "reason": f"resume_from_step:{state.resume_from_step_id or 'unknown'}",
        }
    else:
        plan_context = await build_orchestrator_context(
            skill_store=skill_store,
            skill_usage_tracker=skill_usage_tracker,
            phase="plan",
            task=task,
            intent=state.intent_result.output,
            memory_enabled=state.memory_enabled,
            planning_memory=state.planning_memory,
            run_id=run_id,
        )
        state.orchestrator_result = normalize_orchestrator_result(
            ensure_proactive_result(
                await orchestrator_agent.orchestrate(
                    task=task,
                    context=extend_orchestrator_context(
                        task=task,
                        base_context=plan_context,
                    ),
                ),
                agent_name="orchestrator",
            )
        )
        await sync_planned_task_graph(
            runtime_task_store=runtime_task_store,
            task_id=task_id,
            task_graph=dict(state.orchestrator_result.output.get("task_graph") or {}),
        )
        logger.info(
            "[ProactiveWorkflow] Plan created with %s steps and %s graph nodes",
            len(state.orchestrator_result.output.get("plan_steps", [])),
            len((state.orchestrator_result.output.get("task_graph") or {}).get("nodes", [])),
        )
        if state.memory_enabled:
            try:
                await persist_plan_memory(
                    memory_store=memory_store,
                    run_id=run_id,
                    task=task,
                    orchestrator_output=state.orchestrator_result.output,
                )
            except Exception as exc:
                logger.warning("[ProactiveWorkflow] Persist plan memory degraded: %s", exc)

        state.critic_result = await call_critic_review(
            critic_agent=critic_agent,
            task=task,
            orchestrator=state.orchestrator_result.output,
        )
        logger.info(f"[ProactiveWorkflow] Review completed: ok={state.critic_result.output.get('ok')}")
        await runtime_task_store.set_current_agent(task_id=task_id, agent_id="critic")

        state.active_task_graph = state.orchestrator_result.output
        if should_replan(state.critic_result.output):
            logger.info("[ProactiveWorkflow] Critic rejected plan. Starting replan")
            replan_base = await build_orchestrator_context(
                skill_store=skill_store,
                skill_usage_tracker=skill_usage_tracker,
                phase="replan",
                task=task,
                intent=state.intent_result.output,
                memory_enabled=state.memory_enabled,
                planning_memory=state.planning_memory,
                run_id=run_id,
            )
            replan_result = normalize_orchestrator_result(
                ensure_proactive_result(
                    await orchestrator_agent.orchestrate(
                        task=task,
                        context=extend_orchestrator_context(
                            task=task,
                            base_context={
                                "phase": "replan",
                                **replan_base,
                                "critic": state.critic_result.output,
                                "prior_orchestrator_plan": state.orchestrator_result.output,
                                "prior_task_graph": state.active_task_graph,
                            },
                        ),
                    ),
                    agent_name="orchestrator",
                )
            )
            state.active_task_graph = append_replan_subgraph(
                state.active_task_graph,
                replan_result.output,
                reason=build_replan_reason(state.critic_result.output),
            )
            await sync_planned_task_graph(
                runtime_task_store=runtime_task_store,
                task_id=task_id,
                task_graph=dict(state.active_task_graph),
            )
            replan_details = {
                "trigger": "critic_rejected",
                "reason": build_replan_reason(state.critic_result.output),
                "orchestrator_plan": replan_result.output,
            }
            logger.info(
                "[ProactiveWorkflow] Replan completed with %s nodes",
                len(state.active_task_graph.get("nodes", [])) if isinstance(state.active_task_graph, dict) else 0,
            )
    state.replan_details = replan_details
