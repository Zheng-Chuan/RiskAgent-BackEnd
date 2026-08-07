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

from riskagent_backend.contracts.event import EventType
from riskagent_backend.proactive_agents.base import BaseProactiveAgent


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
        "riskagent_backend.orchestration.proactive_workflow.get_proactive_workflow",
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


# ------------------------------------------------------------------ #
# RFC-006 BDI 信念去重 - 集成测试
# ------------------------------------------------------------------ #

class _DedupTestAgent(BaseProactiveAgent):
    """测试信念去重的 Agent, 每轮注入相同异常信号.

    _act 重写为 no-op (不改变意图状态), 保持 pending 以验证内容去重.
    """

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

    async def _act(self) -> None:
        """重写 _act: 不改变意图状态, 保持 pending 以验证内容去重."""
        pass


@pytest.mark.asyncio
async def test_dedup_5_rounds_same_signal() -> None:
    """RFC-006: 5 轮相同异常信号只创建 1 个 Intention, 信念均标记 processed.

    验证:
    1. 只投递一次事件 (只有一个 Intention 被创建)
    2. 后续 4 轮不重复创建 Intention
    3. 信念被标记为 processed
    """
    agent = _DedupTestAgent(
        name="dedup_agent",
        system_prompt="test",
        enable_background_monitor=False,
    )

    for _ in range(5):
        await agent._perceive_environment()
        await agent._deliberate()
        await agent._act()
        agent._cleanup_beliefs()

    # 1. 只创建了一个 Intention (内容去重 + 信念 processed 跳过)
    assert len(agent._intentions) == 1

    # 2. 后续 4 轮不重复创建 Intention (已由 len==1 证明)
    intention = agent._intentions[0]
    assert intention.source_belief_id is not None
    assert intention.source_belief_id.startswith("belief_")
    assert intention.tool_name == "submit_alerts"
    assert intention.tool_params["severity"] == "critical"

    # 3. 所有信念被标记为 processed
    all_beliefs = agent.get_beliefs()
    assert len(all_beliefs) == 5
    for belief in all_beliefs:
        assert belief.processed is True
        assert belief.processed_at is not None


@pytest.mark.asyncio
async def test_deliberate_skips_processed_belief() -> None:
    """RFC-006: 已处理的信念在 _deliberate 中被跳过."""
    import time

    agent = _make_agent()
    belief = agent.add_belief(
        content={
            "source": "prometheus",
            "metric": "error_rate",
            "value": 0.5,
            "severity": "critical",
        },
        source="intent_perception",
        confidence=0.7,
    )
    # 手动标记为已处理
    belief.processed = True
    belief.processed_at = time.time()

    await agent._deliberate()

    # 已处理的信念不应产生新意图
    pending = agent.get_pending_intentions()
    assert len(pending) == 0


@pytest.mark.asyncio
async def test_deliberate_marks_belief_processed() -> None:
    """RFC-006: _deliberate 处理信念后标记 processed=True."""
    agent = _make_agent()
    agent.add_belief(
        content={
            "source": "prometheus",
            "metric": "error_rate",
            "value": 0.5,
            "severity": "critical",
        },
        source="intent_perception",
        confidence=0.7,
    )

    # 处理前: processed=False
    assert agent._beliefs[0].processed is False
    assert agent._beliefs[0].processed_at is None

    await agent._deliberate()

    # 处理后: processed=True, processed_at 已设置
    assert agent._beliefs[0].processed is True
    assert agent._beliefs[0].processed_at is not None

    # 意图的 source_belief_id 指向该信念
    intention = agent.get_pending_intentions()[0]
    assert intention.source_belief_id == agent._beliefs[0].belief_id
