"""
工作流阶段 2: 意图识别与规划记忆检索.

从 proactive_workflow._run_internal 提取:
- Intent Agent 意图识别 (隔离记忆上下文, 防止误判 continue 意图)
- 意图记忆持久化与规划记忆检索 (记忆后端降级时不阻断主链路)
"""

from __future__ import annotations

import logging
from typing import Any

from riskagent_backend.orchestration.workflow_agent_results import (
    ensure_proactive_result,
    require_successful_agent_result,
)
from riskagent_backend.orchestration.workflow_memory import persist_intent_memory
from riskagent_backend.orchestration.workflow_resume import (
    merge_resume_memory_into_planning_memory,
)
from riskagent_backend.orchestration.workflow_state import WorkflowRunState

logger = logging.getLogger(__name__)


async def recognize_intent_and_retrieve_memory(
    *,
    state: WorkflowRunState,
    intent_agent: Any,
    runtime_task_store: Any,
    memory_store: Any,
) -> None:
    """Step 2: Intent Recognition & Memory Retrieval."""
    task = state.task
    # 意图识别阶段不应受预注入记忆影响
    # 剥离 memory 相关字段,防止 LLM 将 memory 上下文误判为 continue 意图
    intent_task = dict(task)
    for _key in ("benchmark_config", "memory_enabled", "private_memory_enabled", "baseline_mode"):
        intent_task.pop(_key, None)
    intent_result = require_successful_agent_result(
        ensure_proactive_result(
            await intent_agent.recognize(
                task=intent_task,
                metadata={"intent_isolation": True, "instruction": "你的任务是识别用户意图,不要参考历史记忆或 shared memory 中的内容."},
            ),
            agent_name="intent",
        ),
        agent_name="intent",
    )
    logger.info(f"[ProactiveWorkflow] Intent recognized: {intent_result.output.get('primary_intent_type')}")
    await runtime_task_store.set_current_agent(task_id=state.task_id, agent_id="orchestrator")

    state.intent_result = intent_result
    planning_memory = {"hits": [], "summary": {}}
    if state.memory_enabled:
        try:
            await persist_intent_memory(
                memory_store=memory_store,
                run_id=state.run_id,
                task=task,
                intent_output=intent_result.output,
            )
            planning_memory = await memory_store.retrieve_for_planning(
                task=task,
                intent=intent_result.output,
                limit=5,
            )
        except Exception as exc:
            # 记忆后端降级时不应阻断主执行链路.
            logger.warning("[ProactiveWorkflow] Planning memory degraded: %s", exc)
            planning_memory = {"hits": [], "summary": {}}
        planning_memory = merge_resume_memory_into_planning_memory(
            planning_memory=planning_memory,
            resume_request=state.resume_request,
            private_memory_enabled=state.private_memory_enabled,
        )
    state.planning_memory = planning_memory
    state.is_resume = bool(state.resume_request)
