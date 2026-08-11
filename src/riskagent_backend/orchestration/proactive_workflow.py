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
    build_workflow_result,
    build_blocked_event_result,
    build_invalid_event_result,
    normalize_critic_final_output,
    build_workflow_output,
)
from riskagent_backend.orchestration.workflow_events import (
    default_candidate_agents_for_event,
    build_task_from_event,
    requires_manual_approval,
)
from riskagent_backend.scheduling.cron_manager import CronTask
from riskagent_backend.skills import (
    SkillProposer,
    SkillReviser,
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
            intent_result = state.intent_result
            planning_memory = state.planning_memory
            resume_request = state.resume_request
            memory_enabled = state.memory_enabled
            private_memory_enabled = state.private_memory_enabled

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
            orchestrator_result = state.orchestrator_result
            critic_result = state.critic_result

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
            replan_details = state.replan_details
            execution_result = state.execution_result

            # ===== Step 5: Results Aggregation & Final Review =====
            delegate_results = execution_result.get("delegate_results", {})
            engineer_result = delegate_results.get("system_engineer") or delegate_results.get("engineer") or ProactiveAgentResult(
                ok=True,
                output={},
            )
            analyst_result = delegate_results.get("risk_analyst") or delegate_results.get("analyst") or ProactiveAgentResult(
                ok=True,
                output={},
            )
            await runtime_task_store.set_current_agent(task_id=task_id, agent_id="critic")
            critic_final_result = await self._call_critic_review(
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
            critic_final_result = self._replace_output(
                critic_final_result,
                output=critic_final_output,
            )
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
            
            # Skill 置信度更新: 基于执行结果和 Critic 评审更新被注入 Skill 的置信度
            tracked_skill_ids = self._skill_usage_tracker.get_tracked_skills(run_id)
            try:
                execution_had_failures = execution_result.get("status") != "completed"
                skill_updates = await self._skill_usage_tracker.update_after_execution(
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
                self._skill_usage_tracker.clear_tracking(run_id)

            # Skill 改进闭环: 当 Skill 被使用但产生次优结果时, 提议修订
            try:
                reviser = SkillReviser(self._skill_store)
                for skill_id in tracked_skill_ids:
                    proposal = await reviser.check_and_propose_revision(
                        skill_id=skill_id,
                        run_id=run_id,
                        execution_result=execution_result.get("final_output", {}),
                        critic_final=critic_final_result.output,
                    )
                    if proposal:
                        result = await reviser.apply_revision(skill_id=skill_id, proposal=proposal)
                        logger.info("Skill %s revised: %s", skill_id, proposal.reason)
            except Exception as exc:
                logger.warning("Skill revision failed: %s", exc)

            # SkillProposer: 从高质量完成的 run 中提取可复用模式
            try:
                skill_proposer = SkillProposer(self._skill_store)
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
                skill_proposal = {"action": "skipped", "reason": f"error: {exc}"}
            
            # ===== Step 7: Result Building & Context Save =====
            result = build_workflow_result(
                run_id=run_id,
                task=task,
                memory_enabled=memory_enabled,
                private_memory_enabled=private_memory_enabled,
                planning_memory=planning_memory,
                resume_request=resume_request,
                persisted_memory=persisted_memory,
                run_context=run_context,
                intent_result=intent_result,
                orchestrator_result=orchestrator_result,
                critic_result=critic_result,
                critic_final_result=critic_final_result,
                engineer_result=engineer_result,
                analyst_result=analyst_result,
                execution_result=execution_result,
                replan_details=replan_details,
                route_decision=route_decision,
                start_time=start_time,
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
                            "route_decision": route_decision or {},
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
