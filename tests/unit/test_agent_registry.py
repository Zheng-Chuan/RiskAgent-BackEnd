"""Agent 注册表与事件路由语义测试."""

from __future__ import annotations

import pytest

from riskagent_backend.agents.registry import (
    AgentSpec,
    all_agents,
    candidate_agents_for_event,
    get_agent_by_role,
    register_agent,
)
from riskagent_backend.orchestration.workflow_events import (
    default_candidate_agents_for_event,
)


class TestRegistryLookup:
    def test_get_agent_by_role_returns_spec(self):
        spec = get_agent_by_role("risk_analyst")
        assert spec is not None
        assert spec.display_name == "ProactiveRiskAnalystAgent"
        assert spec.role == "analyst"
        assert spec.workflow_attr == "_analyst_agent"

    def test_get_agent_by_role_unknown_returns_none(self):
        assert get_agent_by_role("not_registered") is None

    def test_all_agents_excludes_virtual_by_default(self):
        names = [spec.name for spec in all_agents()]
        assert names == ["intent", "orchestrator", "critic", "system_engineer", "risk_analyst"]
        assert "human" not in names

    def test_all_agents_include_virtual(self):
        names = [spec.name for spec in all_agents(include_virtual=True)]
        assert "human" in names

    def test_duplicate_registration_rejected(self):
        with pytest.raises(ValueError):
            register_agent(AgentSpec(name="critic", display_name="Dup", role="reviewer"))

    def test_display_dict_keeps_legacy_fields(self):
        spec = get_agent_by_role("system_engineer")
        assert spec.to_display_dict() == {
            "id": "system_engineer",
            "name": "ProactiveSystemEngineerAgent",
            "role": "engineer",
            "workflow_attr": "_engineer_agent",
            "capabilities": ["analyze", "monitor", "execute"],
        }


class TestEventRouting:
    def test_risk_breach_routes_to_analyst_first(self):
        assert candidate_agents_for_event("risk_breach_detected") == [
            "risk_analyst",
            "critic",
            "orchestrator",
        ]

    def test_approval_required_routes_to_human_first(self):
        assert candidate_agents_for_event("approval_required") == [
            "human",
            "critic",
            "orchestrator",
        ]

    def test_failed_tool_routes_to_engineer_first(self):
        assert candidate_agents_for_event(
            "tool_finished", payload={"success": False}
        ) == ["system_engineer", "critic", "orchestrator"]

    def test_successful_tool_falls_back_to_full_pool(self):
        assert candidate_agents_for_event(
            "tool_finished", payload={"success": True}
        ) == ["orchestrator", "critic", "risk_analyst", "system_engineer"]

    def test_unknown_event_falls_back_to_full_pool(self):
        assert candidate_agents_for_event("task_created") == [
            "orchestrator",
            "critic",
            "risk_analyst",
            "system_engineer",
        ]

    def test_workflow_events_wrapper_matches_registry(self):
        event = {"event_type": "risk_breach_detected", "payload": {}}
        assert default_candidate_agents_for_event(event) == [
            "risk_analyst",
            "critic",
            "orchestrator",
        ]

    def test_workflow_events_wrapper_handles_missing_payload(self):
        event = {"event_type": "tool_finished"}
        assert default_candidate_agents_for_event(event) == [
            "orchestrator",
            "critic",
            "risk_analyst",
            "system_engineer",
        ]
