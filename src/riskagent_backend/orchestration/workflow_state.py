"""
工作流运行状态载体.

_run_internal 拆分为多个阶段模块后, 各阶段通过 WorkflowRunState
共享运行上下文, 避免超长参数列表.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from riskagent_backend.proactive_agents import ProactiveAgentResult


@dataclass
class WorkflowRunState:
    """单次工作流运行的共享状态 (由 setup 阶段创建, 后续阶段读写)."""

    # ---- 输入 ----
    task: dict[str, Any]
    run_context: dict[str, Any]
    route_decision: dict[str, Any] | None = None
    source_event: dict[str, Any] | None = None

    # ---- 标识与时序 ----
    start_time: float = 0.0
    run_id: str = ""
    task_id: str = ""

    # ---- 记忆开关 ----
    memory_enabled: bool = True
    private_memory_enabled: bool = True

    # ---- Step 1: resume 处理结果 ----
    resume_request: dict[str, Any] = field(default_factory=dict)
    is_resume: bool = False
    resume_from_step_id: str | None = None
    execution_state: dict[str, Any] | None = None

    # ---- Step 2: 意图与规划记忆 ----
    intent_result: ProactiveAgentResult | None = None
    planning_memory: dict[str, Any] = field(default_factory=lambda: {"hits": [], "summary": {}})

    # ---- Step 3: 规划结果 ----
    orchestrator_result: ProactiveAgentResult | None = None
    critic_result: ProactiveAgentResult | None = None
    active_task_graph: dict[str, Any] = field(default_factory=dict)
    replan_details: dict[str, Any] | None = None

    # ---- Step 4: 执行结果 ----
    execution_result: dict[str, Any] | None = None

    # ---- Step 5: 终审与子代理结果 ----
    critic_final_result: ProactiveAgentResult | None = None
    engineer_result: ProactiveAgentResult | None = None
    analyst_result: ProactiveAgentResult | None = None

    # ---- Step 6: 记忆持久化产物 ----
    persisted_memory: dict[str, Any] = field(
        default_factory=lambda: {"run_summary": {}, "summary_entry": None}
    )
