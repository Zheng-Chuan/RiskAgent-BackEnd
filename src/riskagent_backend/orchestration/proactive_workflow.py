"""
主动多 Agent 协作工作流.

使用具备 BDI + ReAct + 后台监控的主动 Agent.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Optional

from riskagent_backend.proactive_agents import (
    ModeratorAgent,
    ProactiveAgentResult,
    ProactiveIntentAgent,
    ProactiveOrchestratorAgent,
    ProactiveCriticAgent,
    ProactiveSystemEngineerAgent,
    ProactiveRiskAnalystAgent,
)
from riskagent_backend.contracts.event import normalize_event, validate_event
from riskagent_backend.contracts.run_context import (
    new_run_context,
    normalize_run_context,
    validate_run_context,
)
from riskagent_backend.governance.proactive_budget import get_proactive_budget_manager
from riskagent_backend.memory import get_memory_store, SessionSegmenter
from riskagent_backend.orchestration.message_bus import get_message_bus
from riskagent_backend.observability.run_trace import (
    build_run_trace_snapshot,
    get_run_trace_store,
)
from riskagent_backend.orchestration.workflow_planning import (
    build_orchestrator_context,
    call_critic_review,
    run_planning_stage,
)
from riskagent_backend.observability.metrics import inc_counter, observe_ms
from riskagent_backend.utils.ids import new_run_id
from riskagent_backend.orchestration.workflow_execution import run_execution_stage
from riskagent_backend.orchestration.workflow_finalization import run_finalization_stage
from riskagent_backend.orchestration.workflow_intent import (
    recognize_intent_and_retrieve_memory,
)
from riskagent_backend.orchestration.workflow_setup import setup_run_and_load_resume
from riskagent_backend.orchestration.workflow_state import WorkflowRunState
from riskagent_backend.orchestration.workflow_agent_results import (
    build_orchestrator_failure_reason,
    ensure_proactive_result,
    extend_orchestrator_context,
    new_placeholder_result,
    normalize_orchestrator_result,
    replace_output,
    require_successful_agent_result,
    sync_planned_task_graph,
)
from riskagent_backend.orchestration.workflow_result_builder import (
    build_blocked_event_result,
    build_invalid_event_result,
    build_workflow_output,
)
from riskagent_backend.orchestration.workflow_events import (
    default_candidate_agents_for_event,
    build_task_from_event,
)
from riskagent_backend.scheduling.cron_manager import CronTask
from riskagent_backend.skills import (
    SkillStore,
    SkillUsageTracker,
)
from riskagent_backend.services.runtime_task_store import RuntimeTaskStore, get_runtime_task_store
from riskagent_backend.tools.skill_view_tool import set_skill_store

logger = logging.getLogger(__name__)


class ProactiveBackEndWorkflow:
    """
    主动多 Agent 协作工作流.
    
    核心特点:
    1. 每个 Agent 都具备 BDI 模型
    2. 每个 Agent 都使用 ReAct 循环
    3. 每个 Agent 都有后台监控线程
    4. 动态协作,非固定流程
    """
    
    def __init__(self) -> None:
        self._intent_agent = ProactiveIntentAgent()
        self._orchestrator_agent = ProactiveOrchestratorAgent()
        self._critic_agent = ProactiveCriticAgent()
        self._engineer_agent = ProactiveSystemEngineerAgent()
        self._analyst_agent = ProactiveRiskAnalystAgent()
        self._message_bus = get_message_bus()
        self._moderator = ModeratorAgent(message_bus=self._message_bus)
        self._proactive_budget = get_proactive_budget_manager()
        self._run_trace_store = get_run_trace_store()
        self._skill_store = SkillStore()
        self._skill_usage_tracker = SkillUsageTracker(self._skill_store)
        # 注入 SkillStore 到 skill_view 工具, 供 Orchestrator 在 ReAct 循环中按需调用
        set_skill_store(self._skill_store)
        self._session_segmenter = SessionSegmenter()

        self._agents_started = False
    
    async def start_agents(self) -> None:
        """启动所有 Agent 的后台监控."""
        if self._agents_started:
            return
        
        await asyncio.gather(
            self._intent_agent.start_background_monitor(),
            self._orchestrator_agent.start_background_monitor(),
            self._critic_agent.start_background_monitor(),
            self._engineer_agent.start_background_monitor(),
            self._analyst_agent.start_background_monitor(),
        )
        
        self._agents_started = True
        logger.info("All proactive agents started with background monitoring")
    
    async def stop_agents(self) -> None:
        """停止所有 Agent 的后台监控."""
        if not self._agents_started:
            return
        
        await asyncio.gather(
            self._intent_agent.stop_background_monitor(),
            self._orchestrator_agent.stop_background_monitor(),
            self._critic_agent.stop_background_monitor(),
            self._engineer_agent.stop_background_monitor(),
            self._analyst_agent.stop_background_monitor(),
        )
        
        self._agents_started = False
        logger.info("All proactive agents stopped")
    
    async def run(self, task: dict[str, Any]) -> dict[str, Any]:
        """
        运行主动多 Agent 协作.
        
        流程:
        1. Intent Agent 识别意图(使用 ReAct)
        2. Orchestrator Agent 制定计划(使用 ReAct)
        3. Critic Agent 评审计划(使用 ReAct)
        4. Engineer 和 Analyst 并行执行(使用 ReAct)
        5. 汇总结果
        
        Args:
            task: 任务定义
            
        Returns:
            协作结果
        """
        run_context = self._resolve_run_context(task=task)
        task_with_context = dict(task)
        task_with_context["run_context"] = run_context
        result = await self._run_internal(task=task_with_context, run_context=run_context)
        self._record_run_trace_snapshot(
            result=result,
            source_event=None,
        )
        return result

    async def start_from_event(
        self,
        *,
        event: dict[str, Any],
        candidate_agents: list[str] | None = None,
    ) -> dict[str, Any]:
        """从系统事件启动统一工作流."""
        normalized_event = normalize_event(event)
        accepted_event, event_error = await self._accept_system_event(normalized_event)
        if event_error is not None:
            run_context = new_run_context(
                entry_type="system_event",
                task_id=str((normalized_event.get("payload") or {}).get("task_id") or normalized_event.get("event_id") or "") or None,
                trigger_event_id=str(normalized_event.get("event_id") or ""),
                trigger_reason="invalid_event",
                trigger_evidence={"validation_errors": [event_error]},
                metadata={
                    "source_agent": normalized_event.get("source_agent"),
                    "event_type": normalized_event.get("event_type"),
                },
            )
            failed = build_invalid_event_result(
                event=normalized_event,
                run_context=run_context,
                reason=event_error,
            )
            self._record_run_trace_snapshot(result=failed, source_event=normalized_event)
            return failed
        normalized_event = accepted_event
        task_payload = normalized_event.get("payload") if isinstance(normalized_event.get("payload"), dict) else {}
        provisional_task_id = str(task_payload.get("task_id") or normalized_event.get("event_id") or "")
        run_context = new_run_context(
            entry_type="system_event",
            task_id=provisional_task_id or None,
            trigger_event_id=str(normalized_event.get("event_id") or ""),
            trigger_reason="pending_moderation",
            trigger_evidence={
                "event_type": normalized_event.get("event_type"),
                "source_agent": normalized_event.get("source_agent"),
                "payload": task_payload,
            },
            metadata={
                "source_agent": normalized_event.get("source_agent"),
                "event_type": normalized_event.get("event_type"),
            },
        )
        budget_decision = self._proactive_budget.evaluate_and_reserve(
            run_id=str(run_context.get("run_id") or ""),
            event=normalized_event,
        )
        if not budget_decision.allowed:
            blocked = build_blocked_event_result(
                event=normalized_event,
                run_context=run_context,
                reason=budget_decision.reason,
                budget_evidence=budget_decision.evidence,
            )
            self._record_run_trace_snapshot(
                result=blocked,
                source_event=normalized_event,
            )
            self._proactive_budget.release_run(
                run_id=str(run_context.get("run_id") or ""),
                status="blocked",
            )
            return blocked

        decision = await self._moderator.moderate(
            event=normalized_event,
            candidate_agents=candidate_agents or default_candidate_agents_for_event(normalized_event),
            context={
                "run_id": run_context.get("run_id"),
                "entry_type": run_context.get("entry_type"),
                "task": {"task_id": provisional_task_id or normalized_event.get("event_id")},
            },
        )
        task = build_task_from_event(
            event=normalized_event,
            route_decision=decision,
        )
        run_context["task_id"] = str(task.get("task_id") or "")
        run_context["trigger_reason"] = str(decision.get("reason") or "")
        run_context["route_decision"] = dict(decision)
        task["run_context"] = run_context
        task["event_context"] = {
            "event": normalized_event,
            "route_decision": decision,
        }
        result = await self._run_internal(
            task=task,
            run_context=run_context,
            route_decision=decision,
            source_event=normalized_event,
        )
        self._record_run_trace_snapshot(
            result=result,
            source_event=normalized_event,
        )
        self._proactive_budget.release_run(
            run_id=str(run_context.get("run_id") or ""),
            status=str(result.get("status") or "failed"),
        )
        return result

    async def run_cron_triggered_workflow(self, cron_task: CronTask) -> dict[str, Any]:
        """Cron 触发的任务统一走 system_event → ModeratorAgent → TaskGraphExecutor 主链.

        不允许调度任务绕过治理体系.

        Args:
            cron_task: Cron 定时任务定义.

        Returns:
            工作流执行结果.
        """
        # 1. 构建 system_event
        event = {
            "event_id": f"cron_{cron_task.task_id}_{int(time.time() * 1000)}",
            "event_type": "cron_triggered",
            "source_agent": "cron_manager",
            "payload": {
                **cron_task.task_template,
                "task_id": cron_task.task_id,
            },
            "priority": str((cron_task.trigger_config or {}).get("priority", "normal")),
        }
        trigger_reason = f"Cron task: {cron_task.name}"
        event["payload"]["trigger_reason"] = trigger_reason

        logger.info(
            "[ProactiveWorkflow] Cron triggered: task_id=%s name=%s expr=%s",
            cron_task.task_id,
            cron_task.name,
            cron_task.cron_expression,
        )

        # 2. 调用现有的 start_from_event (system_event 入口)
        try:
            result = await self.start_from_event(event=event)
        except Exception as exc:
            logger.exception(
                "[ProactiveWorkflow] Cron workflow failed: task_id=%s err=%s",
                cron_task.task_id,
                exc,
            )
            result = {
                "status": "failed",
                "entry_type": "system_event",
                "task_id": cron_task.task_id,
                "errors": [str(exc)],
                "cron_task_id": cron_task.task_id,
                "cron_task_name": cron_task.name,
            }

        # 3. 补充 cron 上下文信息
        if isinstance(result, dict):
            result.setdefault("cron_task_id", cron_task.task_id)
            result.setdefault("cron_task_name", cron_task.name)
            result.setdefault("cron_expression", cron_task.cron_expression)
            result.setdefault("trigger_count", cron_task.trigger_count)

        return result

    async def _run_internal(
        self,
        *,
        task: dict[str, Any],
        run_context: dict[str, Any],
        route_decision: dict[str, Any] | None = None,
        source_event: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        start_time = time.time()
        run_id = str(run_context.get("run_id") or "")
        task_id = str(task.get("task_id") or "")
        runtime_task_store = get_runtime_task_store()
        
        logger.info(f"[ProactiveWorkflow] Starting for task: {task.get('task_id') or run_id}")
        
        try:
            memory_store = get_memory_store()
            state = WorkflowRunState(
                task=task,
                run_context=run_context,
                route_decision=route_decision,
                source_event=source_event,
                start_time=start_time,
                run_id=run_id,
                task_id=task_id,
                memory_enabled=task.get("memory_enabled", True) is not False,
            )
            state.private_memory_enabled = (
                state.memory_enabled and task.get("private_memory_enabled", True) is not False
            )

            # ===== Step 1: Setup & Resume Handling =====
            early_result = await setup_run_and_load_resume(
                state=state,
                runtime_task_store=runtime_task_store,
                memory_store=memory_store,
                start_agents=self.start_agents,
            )
            if early_result is not None:
                return early_result
            # ===== Step 2: Intent Recognition & Memory Retrieval =====
            await recognize_intent_and_retrieve_memory(
                state=state,
                intent_agent=self._intent_agent,
                runtime_task_store=runtime_task_store,
                memory_store=memory_store,
            )
            task = state.task

            # ===== Step 3: Planning (Orchestrator + Critic + Replan) =====
            await run_planning_stage(
                state=state,
                orchestrator_agent=self._orchestrator_agent,
                critic_agent=self._critic_agent,
                runtime_task_store=runtime_task_store,
                skill_store=self._skill_store,
                skill_usage_tracker=self._skill_usage_tracker,
                memory_store=memory_store,
            )
            # ===== Step 4: TaskGraph Execution =====
            await run_execution_stage(
                state=state,
                runtime_task_store=runtime_task_store,
                memory_store=memory_store,
                session_segmenter=self._session_segmenter,
                engineer_agent=self._engineer_agent,
                analyst_agent=self._analyst_agent,
                orchestrator_agent=self._orchestrator_agent,
                skill_store=self._skill_store,
                skill_usage_tracker=self._skill_usage_tracker,
            )

            # ===== Step 5-7: Final Review, Memory/Skill Lifecycle, Result Building =====
            return await run_finalization_stage(
                state=state,
                runtime_task_store=runtime_task_store,
                memory_store=memory_store,
                critic_agent=self._critic_agent,
                skill_store=self._skill_store,
                skill_usage_tracker=self._skill_usage_tracker,
            )

        except Exception as e:
            logger.exception(f"[ProactiveWorkflow] Failed: {e}")
            await runtime_task_store.fail_task(
                task_id=task_id,
                error_message=str(e),
            )
            return {
                "status": "failed",
                "run_id": run_id,
                "entry_type": run_context.get("entry_type"),
                "run_context": run_context,
                "task_id": task.get("task_id"),
                "errors": [str(e)],
            }

    def _new_placeholder_result(self, *, output: dict[str, Any], agent_name: str) -> ProactiveAgentResult:
        """构造恢复执行时的占位结果."""
        return new_placeholder_result(output=output, agent_name=agent_name)

    async def _call_critic_review(
        self,
        *,
        task: dict[str, Any],
        orchestrator: dict[str, Any],
        receipts: list[dict[str, Any]] | None = None,
        final_output: dict[str, Any] | None = None,
        phase: str = "plan_review",
    ) -> ProactiveAgentResult:
        """兼容旧签名并统一向 critic 透传 receipt 上下文."""
        return await call_critic_review(
            critic_agent=self._critic_agent,
            task=task,
            orchestrator=orchestrator,
            receipts=receipts,
            final_output=final_output,
            phase=phase,
        )

    async def _build_orchestrator_context(
        self,
        *,
        phase: str,
        task: dict[str, Any],
        intent: dict[str, Any],
        memory_enabled: bool,
        planning_memory: dict[str, Any],
        run_id: str | None = None,
    ) -> dict[str, Any]:
        return await build_orchestrator_context(
            skill_store=self._skill_store,
            skill_usage_tracker=self._skill_usage_tracker,
            phase=phase,
            task=task,
            intent=intent,
            memory_enabled=memory_enabled,
            planning_memory=planning_memory,
            run_id=run_id,
        )

    def _extend_orchestrator_context(
        self,
        *,
        task: dict[str, Any],
        base_context: dict[str, Any],
    ) -> dict[str, Any]:
        return extend_orchestrator_context(task=task, base_context=base_context)

    def _resolve_run_context(self, *, task: dict[str, Any]) -> dict[str, Any]:
        existing = task.get("run_context") if isinstance(task.get("run_context"), dict) else {}
        if existing:
            normalized = normalize_run_context(existing)
            is_valid, _errors = validate_run_context(normalized)
            if is_valid:
                return normalized
        return new_run_context(
            entry_type="user_task",
            task_id=str(task.get("task_id") or "") or None,
            metadata={
                "source": task.get("source"),
            },
        )

    def _record_run_trace_snapshot(
        self,
        *,
        result: dict[str, Any],
        source_event: dict[str, Any] | None,
    ) -> None:
        run_id = result.get("run_id")
        if not isinstance(run_id, str) or not run_id:
            return
        root_event_id = None
        if isinstance(source_event, dict):
            root_event_id = str(source_event.get("event_id") or "") or None
        snapshot = build_run_trace_snapshot(
            result=result,
            source_event=source_event,
            related_events=self._message_bus.get_related_event_history(
                root_event_id=root_event_id,
                run_id=run_id,
            ),
            related_event_trace=self._message_bus.get_related_event_trace(
                root_event_id=root_event_id,
                run_id=run_id,
            ),
        )
        self._run_trace_store.save_snapshot(snapshot)
        result["run_trace"] = snapshot.to_dict()

    async def _accept_system_event(
        self,
        event: dict[str, Any],
    ) -> tuple[dict[str, Any], str | None]:
        is_valid, errors = validate_event(event)
        if not is_valid:
            return dict(event), f"invalid_event:{','.join(errors)}"
        existing = self._message_bus.get_event_history()
        if any(isinstance(item, dict) and item.get("event_id") == event.get("event_id") for item in existing):
            return dict(event), None
        accepted = await self._message_bus.publish_event(event)
        return accepted, None

    def _ensure_proactive_result(
        self,
        result: Any,
        *,
        agent_name: str,
    ) -> ProactiveAgentResult:
        return ensure_proactive_result(result, agent_name=agent_name)

    def _replace_output(
        self,
        result: ProactiveAgentResult,
        *,
        output: dict[str, Any],
    ) -> ProactiveAgentResult:
        return replace_output(result, output=output)

    def _normalize_orchestrator_result(
        self,
        result: ProactiveAgentResult,
    ) -> ProactiveAgentResult:
        """严格校验编排结果, 禁止 fallback 或隐式降级."""
        return normalize_orchestrator_result(result)

    def _require_successful_agent_result(
        self,
        result: ProactiveAgentResult,
        *,
        agent_name: str,
    ) -> ProactiveAgentResult:
        return require_successful_agent_result(result, agent_name=agent_name)

    def _build_orchestrator_failure_reason(
        self,
        *,
        result: ProactiveAgentResult,
    ) -> str:
        return build_orchestrator_failure_reason(result=result)

    async def _sync_planned_task_graph(
        self,
        *,
        runtime_task_store: RuntimeTaskStore,
        task_id: str,
        task_graph: dict[str, Any],
        execution_state: dict[str, Any] | None = None,
    ) -> None:
        """写入规划图后立即回读校验, 一旦错位直接失败."""
        await sync_planned_task_graph(
            runtime_task_store=runtime_task_store,
            task_id=task_id,
            task_graph=task_graph,
            execution_state=execution_state,
        )


_proactive_workflow: Optional[ProactiveBackEndWorkflow] = None


async def run_proactive_workflow(*, task: dict[str, Any]) -> dict[str, Any]:
    """运行统一主动工作流并补充最小观测字段."""
    inc_counter("orchestrator_runs_total")
    start_time = time.time()

    run_id = new_run_id("proactive")
    logger.info(f"Starting proactive multi-agent orchestration for task: {task.get('task_id') or run_id}")

    try:
        reset_proactive_workflow()
        workflow = get_proactive_workflow()
        result = await workflow.run(task)

        out = build_workflow_output(
            task=task,
            run_id=run_id,
            result=result,
            start_time=start_time,
        )

        latency_ms = (time.time() - start_time) * 1000
        observe_ms("orchestrator_latency_ms", latency_ms)
        inc_counter("orchestrator_runs_success")
        return out
    except Exception as e:
        latency_ms = (time.time() - start_time) * 1000
        observe_ms("orchestrator_latency_ms", latency_ms)
        inc_counter("orchestrator_runs_error")
        logger.exception(f"Proactive orchestration failed for task {task.get('task_id') or run_id}")
        return {
            "ok": False,
            "latency_ms": latency_ms,
            "result": {
                "run_id": run_id,
                "task_id": task.get("task_id"),
                "errors": [str(e)],
                "tokens_total": 0,
            },
        }


def get_proactive_workflow() -> ProactiveBackEndWorkflow:
    """获取主动工作流单例."""
    global _proactive_workflow
    if _proactive_workflow is None:
        _proactive_workflow = ProactiveBackEndWorkflow()
    return _proactive_workflow


def reset_proactive_workflow() -> None:
    """重置主动工作流."""
    global _proactive_workflow
    _proactive_workflow = None


__all__ = [
    "ProactiveBackEndWorkflow",
    "run_proactive_workflow",
    "get_proactive_workflow",
    "reset_proactive_workflow",
]
