"""
Agent 注册表 - Agent 元数据与事件订阅的单一事实来源.

新增 Agent 时只需在本模块注册一条 ``AgentSpec``:
- 事件路由 (``workflow_events.candidate_agents_for_event``) 自动生效;
- REST BFF 展示 (``get_agents_snapshot``) 自动生效.

本模块不导入任何业务模块 (纯数据), 避免循环依赖.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AgentSpec:
    """单个 Agent 的注册信息."""

    name: str
    display_name: str
    role: str
    capabilities: tuple[str, ...] = ()
    handled_events: tuple[str, ...] = ()
    workflow_attr: str | None = None
    universal: bool = False
    virtual: bool = False
    # 回退候选顺序 (越小越靠前); 不订阅任何事件的 Agent 不参与回退
    candidate_order: int = 100
    # 命中分支中 universal Agent 的追加顺序 (保持历史语义: critic 先于 orchestrator)
    follow_order: int = 100

    def to_display_dict(self) -> dict:
        """转换为 REST BFF 展示结构 (历史字段名保持不变)."""
        return {
            "id": self.name,
            "name": self.display_name,
            "role": self.role,
            "workflow_attr": self.workflow_attr,
            "capabilities": list(self.capabilities),
        }


_REGISTRY: dict[str, AgentSpec] = {}
_REGISTRATION_ORDER: list[str] = []


def register_agent(spec: AgentSpec) -> AgentSpec:
    """注册 Agent (重复注册同名 Agent 视为编程错误)."""
    if spec.name in _REGISTRY:
        raise ValueError(f"agent already registered: {spec.name}")
    _REGISTRY[spec.name] = spec
    _REGISTRATION_ORDER.append(spec.name)
    return spec


def get_agent_by_role(name: str) -> AgentSpec | None:
    """按注册名查询 Agent 元数据, 未注册返回 None."""
    return _REGISTRY.get(name)


def all_agents(*, include_virtual: bool = False) -> list[AgentSpec]:
    """按注册顺序返回全部 Agent."""
    return [
        _REGISTRY[name]
        for name in _REGISTRATION_ORDER
        if include_virtual or not _REGISTRY[name].virtual
    ]


def candidate_agents_for_event(
    event_type: str, *, payload: dict | None = None
) -> list[str]:
    """事件 → 候选 Agent 列表 (注册表查询, 保持历史路由语义).

    - 命中订阅该事件的 Agent 作为主候选;
    - universal Agent (orchestrator/critic) 追加其后;
    - 无命中时回退到全量列表 (orchestrator 优先).
    """
    payload = payload or {}
    matched: list[str] = []

    if event_type == "approval_required":
        matched.append("human")
    else:
        if event_type == "tool_finished" and payload.get("success") is not False:
            event_type = ""
        for name in _REGISTRATION_ORDER:
            spec = _REGISTRY[name]
            if spec.virtual or spec.universal:
                continue
            if event_type and event_type in spec.handled_events:
                matched.append(name)

    if matched:
        candidates = list(matched)
        universal_specs = sorted(
            (_REGISTRY[name] for name in _REGISTRATION_ORDER if _REGISTRY[name].universal),
            key=lambda spec: spec.follow_order,
        )
        for spec in universal_specs:
            if spec.name not in candidates:
                candidates.append(spec.name)
        return candidates

    # 回退: universal 优先 (按注册序), 其余取订阅过事件的 Agent 按 candidate_order
    fallback: list[str] = [name for name in _REGISTRATION_ORDER if _REGISTRY[name].universal]
    subscribers = sorted(
        (
            _REGISTRY[name]
            for name in _REGISTRATION_ORDER
            if not _REGISTRY[name].virtual
            and not _REGISTRY[name].universal
            and _REGISTRY[name].handled_events
        ),
        key=lambda spec: spec.candidate_order,
    )
    fallback.extend(spec.name for spec in subscribers)
    return fallback


# ---- 注册表内容 (新增 Agent 在此追加) ----

register_agent(AgentSpec(
    name="intent",
    display_name="ProactiveIntentAgent",
    role="lead",
    capabilities=("recognize", "monitor"),
    workflow_attr="_intent_agent",
))

register_agent(AgentSpec(
    name="orchestrator",
    display_name="ProactiveOrchestratorAgent",
    role="lead",
    capabilities=("plan", "coordinate", "monitor"),
    workflow_attr="_orchestrator_agent",
    universal=True,
    follow_order=2,
))

register_agent(AgentSpec(
    name="critic",
    display_name="ProactiveCriticAgent",
    role="reviewer",
    capabilities=("review", "governance", "validate"),
    workflow_attr="_critic_agent",
    universal=True,
    follow_order=1,
))

register_agent(AgentSpec(
    name="system_engineer",
    display_name="ProactiveSystemEngineerAgent",
    role="engineer",
    capabilities=("analyze", "monitor", "execute"),
    handled_events=("tool_finished",),
    workflow_attr="_engineer_agent",
    candidate_order=2,
))

register_agent(AgentSpec(
    name="risk_analyst",
    display_name="ProactiveRiskAnalystAgent",
    role="analyst",
    capabilities=("analyze", "monitor", "report"),
    handled_events=("risk_breach_detected",),
    workflow_attr="_analyst_agent",
    candidate_order=1,
))

register_agent(AgentSpec(
    name="human",
    display_name="Human",
    role="approver",
    virtual=True,
))
