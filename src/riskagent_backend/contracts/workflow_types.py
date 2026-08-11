"""
编排层核心数据结构的 TypedDict 契约.

定位: 为 orchestration 阶段管道间流转的 dict 提供静态类型契约.
- 全部使用 ``total=False`` (宽容标注): 运行时不强制字段存在,
  与既有 normalize/validate 运行时校验函数互补而非替代.
- 新增编排层纯函数时, 参数/返回值应优先引用本模块类型,
  而不是裸 ``dict[str, Any]``.
"""

from __future__ import annotations

from typing import Any, TypedDict


class SystemEvent(TypedDict, total=False):
    """系统事件 (感知升级 / moderator 派发 / 事件入口)."""

    event_id: str | None
    event_type: str | None
    source_agent: str | None
    severity: str | None
    payload: dict[str, Any]
    timestamp: Any


class EventTaskPayload(TypedDict, total=False):
    """任务 payload (事件构建任务与用户任务共用)."""

    content: str | None
    event_payload: dict[str, Any]
    trigger_event_id: str | None
    trigger_reason: str | None
    trigger_evidence: dict[str, Any]


class WorkflowTask(TypedDict, total=False):
    """工作流任务 (build_task_from_event 产物 / run 入口任务)."""

    task_id: str | None
    session_id: str | None
    source: str | None
    payload: dict[str, Any]
    trigger_event_id: str | None
    trigger_reason: str | None
    trigger_evidence: dict[str, Any]


class RouteDecision(TypedDict, total=False):
    """事件路由决策."""

    routed: bool
    reason: str
    candidate_agents: list[str]
    event_id: str


class CriticIssue(TypedDict, total=False):
    """Critic 评审问题项."""

    code: str
    message: str
    severity: str


class CriticReviewOutput(TypedDict, total=False):
    """Critic 评审输出 (与 contracts.agent_outputs 验证规则一致)."""

    schema_version: str
    ok: bool
    risk_level: str  # LOW / MEDIUM / HIGH
    issues: list[CriticIssue]
    require_human_approval: bool
    suggested_fixes: list[str]
    evidence: dict[str, Any]
    run_summary: dict[str, Any]


class ApprovalTraceItem(TypedDict, total=False):
    """审批轨迹项 (build_approval_trace_items 产物)."""

    approval_id: str | None
    level: str | None
    step_id: str | None
    command_id: str | None
    tool_name: str | None
    approval_state: str | None
    required: bool | None
    reason: str | None
    risk_level: str | None
    impact_scope: list[Any]
    recommended_action: str | None
    actor: str | None
    note: str | None
    approval_trace: dict[str, Any] | None


class WorkflowTrigger(TypedDict, total=False):
    """结果中的事件触发信息."""

    event_id: str | None
    reason: str | None
    evidence: dict[str, Any]


class WorkflowResult(TypedDict, total=False):
    """工作流运行结果 (build_workflow_result 产物, 宽容标注)."""

    status: str | None
    run_id: str | None
    entry_type: str | None
    run_context: dict[str, Any]
    task_id: str | None
    # 宽容为裸 dict: build_workflow_result 等通用构建器接收未类型化的任务/路由输入
    task: dict[str, Any]
    route_decision: dict[str, Any]
    intent: dict[str, Any]
    task_graph: dict[str, Any]
    task_graph_execution: dict[str, Any]
    orchestrator_plan: dict[str, Any]
    critic_plan: dict[str, Any]
    critic_final: dict[str, Any]
    replan: dict[str, Any]
    receipts: list[dict[str, Any]]
    approval_trace: list[ApprovalTraceItem]
    engineer: dict[str, Any]
    analyst: dict[str, Any]
    final_output: dict[str, Any]
    react_steps: list[dict[str, Any]]
    bdi_states: dict[str, Any]
    llm_interactions: list[dict[str, Any]]
    latency_ms: float
    errors: list[Any]
    # memory_enabled=True 时附加
    memory_hits: list[Any]
    planning_memory: dict[str, Any]
    resume_memory_state: list[Any]
    shared_memory_board: list[Any]
    private_memory_state: dict[str, Any]
    run_summary: dict[str, Any]
    approval_memory: list[Any]
    # 事件触发时附加
    trigger: WorkflowTrigger
    # 预算阻断时附加
    governance: dict[str, Any]
