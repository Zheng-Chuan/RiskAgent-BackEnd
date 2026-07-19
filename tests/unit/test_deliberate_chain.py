"""_deliberate 链路单元测试 + 集成测试.

测试场景:
1. test_deliberate_critical_perception_source:
   belief.source=intent_perception, severity=critical → 形成 1 个 intention
2. test_deliberate_non_perception_source:
   belief.source=user_input → 不形成 intention
3. test_deliberate_warning_severity:
   severity=warning → 形成 intention (priority=normal)
4. test_chain_perceive_to_act:
   mock start_from_event, 验证 _perceive → _deliberate → _act 完整链路
5. test_deliberate_legacy_system_metrics_ignored:
   belief.source=system_metrics → 不形成 intention (回归保护)
"""

from __future__ import annotations

import pytest

from riskmonitor_multiagent.contracts.event import EventType
from riskmonitor_multiagent.proactive_agents.base import BaseProactiveAgent


def _make_agent() -> BaseProactiveAgent:
    """构造测试用 BaseProactiveAgent 实例 (关闭后台监控)."""
    return BaseProactiveAgent(
        name="test_agent",
        system_prompt="test prompt",
        enable_background_monitor=False,
    )


# --- 场景 1: perception source + critical severity → 形成 intention ---
@pytest.mark.asyncio
async def test_deliberate_critical_perception_source() -> None:
    agent = _make_agent()
    agent.add_belief(
        content={
            "source": "prometheus",
            "metric": "error_rate",
            "value": 0.35,
            "severity": "critical",
        },
        source="intent_perception",
        confidence=0.7,
    )

    await agent._deliberate()

    pending = agent.get_pending_intentions()
    assert len(pending) == 1
    intention = pending[0]
    assert intention.target_agent == "orchestrator"
    assert intention.tool_name == "submit_alerts"
    assert intention.tool_params["severity"] == "critical"
    assert intention.tool_params["priority"] == "high"


# --- 场景 2: 非 perception source → 不形成 intention ---
@pytest.mark.asyncio
async def test_deliberate_non_perception_source() -> None:
    agent = _make_agent()
    agent.add_belief(
        content={"task_id": "task_001", "content": "hello"},
        source="user_input",
    )

    await agent._deliberate()

    pending = agent.get_pending_intentions()
    assert len(pending) == 0


# --- 场景 3: warning severity → 形成 intention (priority=normal) ---
@pytest.mark.asyncio
async def test_deliberate_warning_severity() -> None:
    agent = _make_agent()
    agent.add_belief(
        content={
            "event_id": "evt_001",
            "severity": "warning",
            "source": "perception_filter",
            "description": "redis slow query",
        },
        source="perception_escalation",
        confidence=0.9,
    )

    await agent._deliberate()

    pending = agent.get_pending_intentions()
    assert len(pending) == 1
    intention = pending[0]
    assert intention.target_agent == "orchestrator"
    assert intention.tool_name == "submit_alerts"
    assert intention.tool_params["severity"] == "warning"
    assert intention.tool_params["priority"] == "normal"


# --- 场景 4: 完整 _perceive → _deliberate → _act 链路, mock start_from_event ---
class _ChainTestAgent(BaseProactiveAgent):
    """测试链路的 Agent, _perceive_environment 直接注入 belief (绕过数据源)."""

    async def _perceive_environment(self) -> None:
        self.add_belief(
            content={
                "source": "prometheus",
                "metric": "error_rate",
                "value": 0.5,
                "severity": "critical",
            },
            source="intent_perception",
            confidence=0.7,
        )


@pytest.mark.asyncio
async def test_chain_perceive_to_act(monkeypatch: pytest.MonkeyPatch) -> None:
    agent = _ChainTestAgent(
        name="chain_agent",
        system_prompt="test",
        enable_background_monitor=False,
    )

    called: dict[str, object] = {}

    class _FakeWorkflow:
        async def start_from_event(self, *, event, candidate_agents=None):
            called["event"] = event
            called["candidate_agents"] = list(candidate_agents or [])
            called["source_agent"] = event.get("source_agent")
            called["event_type"] = event.get("event_type")
            called["priority"] = event.get("priority")
            return {"status": "completed"}

    monkeypatch.setattr(
        "riskmonitor_multiagent.orchestration.proactive_workflow.get_proactive_workflow",
        lambda: _FakeWorkflow(),
    )

    # 完整链路: _perceive → _deliberate → _act
    await agent._perceive_environment()
    await agent._deliberate()
    await agent._act()

    # 验证 start_from_event 被调用
    assert "event" in called, "start_from_event 未被调用"
    assert called.get("source_agent") == "chain_agent"
    # severity=critical → event_type=RISK_BREACH_DETECTED
    assert called.get("event_type") == EventType.RISK_BREACH_DETECTED.value
    # severity=critical → priority=high
    assert called.get("priority") == "high"
    # candidate_agents 包含 orchestrator
    assert "orchestrator" in called.get("candidate_agents", [])


# --- 场景 5: 旧版 system_metrics source → 不形成 intention (回归保护) ---
@pytest.mark.asyncio
async def test_deliberate_legacy_system_metrics_ignored() -> None:
    agent = _make_agent()
    agent.add_belief(
        content={
            "metric": "error_rate",
            "value": 0.35,
        },
        source="system_metrics",
    )

    await agent._deliberate()

    pending = agent.get_pending_intentions()
    assert len(pending) == 0
