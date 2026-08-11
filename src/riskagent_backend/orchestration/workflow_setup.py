"""
工作流阶段 1: 运行初始化与 Resume 加载.

从 proactive_workflow._run_internal 提取:
- RuntimeTaskStore 任务创建/状态标记
- resume 请求加载 (memory_store.build_resume_payload) 与审批决定合并
- resume 请求字段归一化与完整性校验 (不完整则提前失败返回)
"""

from __future__ import annotations

import logging
import time
from typing import Any, Awaitable, Callable

from riskagent_backend.orchestration.workflow_resume import (
    apply_approval_decision_to_resume_request,
    apply_resume_context,
    validate_resume_request_completeness,
)
from riskagent_backend.orchestration.workflow_state import WorkflowRunState

logger = logging.getLogger(__name__)


async def setup_run_and_load_resume(
    *,
    state: WorkflowRunState,
    runtime_task_store: Any,
    memory_store: Any,
    start_agents: Callable[[], Awaitable[None]],
) -> dict[str, Any] | None:
    """Step 1: Setup & Resume Handling.

    Returns:
        resume 上下文不完整时返回提前失败结果; 正常情况返回 None.
    """
    task = state.task
    run_id = state.run_id
    task_id = state.task_id

    if not await runtime_task_store.get_task(task_id=task_id):
        task_payload = task.get("payload") if isinstance(task.get("payload"), dict) else {}
        description = str(
            task.get("description")
            or task_payload.get("content")
            or task_payload.get("text")
            or task_id
        )
        await runtime_task_store.create_task(
            task_id=task_id,
            session_id=str(task.get("session_id") or "") or None,
            description=description,
        )
    await runtime_task_store.mark_running(task_id=task_id, run_id=run_id)
    await runtime_task_store.set_current_agent(task_id=task_id, agent_id="intent")
    await start_agents()

    resume_request = task.get("resume") if isinstance(task.get("resume"), dict) else {}
    if state.memory_enabled and isinstance(resume_request.get("run_id"), str) and not isinstance(resume_request.get("task_graph"), dict):
        loaded_resume = await memory_store.build_resume_payload(
            run_id=resume_request["run_id"],
            resume_from_step_id=resume_request.get("resume_from_step_id"),
        )
        if isinstance(loaded_resume, dict):
            merged_resume = dict(loaded_resume)
            merged_resume.update(resume_request)
            resume_request = merged_resume
    resume_request = apply_approval_decision_to_resume_request(
        resume_request=resume_request,
    )
    if resume_request:
        normalized_resume_request = dict(resume_request)
        normalized_resume_request["memory_state"] = (
            list(normalized_resume_request.get("memory_state"))
            if isinstance(normalized_resume_request.get("memory_state"), list)
            else []
        )
        normalized_resume_request["shared_memory_board"] = (
            list(normalized_resume_request.get("shared_memory_board"))
            if isinstance(normalized_resume_request.get("shared_memory_board"), list)
            else []
        )
        normalized_resume_request["private_memory_state"] = (
            dict(normalized_resume_request.get("private_memory_state"))
            if isinstance(normalized_resume_request.get("private_memory_state"), dict)
            else {}
        )
        normalized_resume_request["run_summary"] = (
            dict(normalized_resume_request.get("run_summary"))
            if isinstance(normalized_resume_request.get("run_summary"), dict)
            else {}
        )
        normalized_resume_request["approval_decision"] = (
            dict(normalized_resume_request.get("approval_decision"))
            if isinstance(normalized_resume_request.get("approval_decision"), dict)
            else {}
        )
        resume_request = normalized_resume_request
    resume_validation = validate_resume_request_completeness(
        resume_request=resume_request,
    )
    if resume_request and not resume_validation["is_complete"]:
        logger.warning(
            "[ProactiveWorkflow] Resume request incomplete: missing=%s invalid=%s",
            resume_validation.get("missing_fields"),
            resume_validation.get("invalid_fields"),
        )
        return _build_resume_incomplete_result(
            state=state,
            resume_request=resume_request,
            resume_validation=resume_validation,
        )
    state.task = apply_resume_context(
        task=task,
        resume_request=resume_request,
    )
    state.resume_request = resume_request
    return None


def _build_resume_incomplete_result(
    *,
    state: WorkflowRunState,
    resume_request: dict[str, Any],
    resume_validation: dict[str, Any],
) -> dict[str, Any]:
    """resume 上下文不完整时的提前失败结果."""
    task = state.task
    return {
        "status": "failed",
        "run_id": state.run_id,
        "entry_type": state.run_context.get("entry_type"),
        "run_context": state.run_context,
        "task_id": task.get("task_id"),
        "task": task,
        "route_decision": state.route_decision or {},
        "intent": {},
        "task_graph": (
            dict(resume_request.get("task_graph"))
            if isinstance(resume_request.get("task_graph"), dict)
            else {}
        ),
        "task_graph_execution": {
            "status": "failed",
            "completed_steps": [],
            "skipped_steps": [],
            "failed_step_id": None,
            "blocked_step_id": None,
            "trace": [],
            "errors": ["resume_context_incomplete"],
            "resume_history": [
                {
                    "resume_from_step_id": resume_request.get("resume_from_step_id"),
                    "mode": "step_resume",
                    "validation": resume_validation,
                }
            ],
            "resume_ready": False,
            "failure_classification": resume_validation.get("failure_classification"),
            "resume_validation": resume_validation,
        },
        "orchestrator_plan": {},
        "critic_plan": {},
        "critic_final": {},
        "replan": {},
        "receipts": [],
        "approval_trace": [],
        "engineer": {},
        "analyst": {},
        "final_output": {},
        "react_steps": [],
        "bdi_states": {},
        "llm_interactions": [],
        "latency_ms": (time.time() - state.start_time) * 1000,
        "errors": ["resume_context_incomplete"],
        "memory_hits": [],
        "planning_memory": {"resume_validation": resume_validation},
        "resume_memory_state": (
            list(resume_request.get("memory_state"))
            if isinstance(resume_request.get("memory_state"), list)
            else []
        ),
        "shared_memory_board": (
            list(resume_request.get("shared_memory_board"))
            if isinstance(resume_request.get("shared_memory_board"), list)
            else []
        ),
        "private_memory_state": (
            dict(resume_request.get("private_memory_state"))
            if isinstance(resume_request.get("private_memory_state"), dict)
            else {}
        ),
        "run_summary": {},
        "approval_memory": [],
    }
