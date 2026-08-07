"""
BDI 模型和 Proactive Agent 测试.
"""

from __future__ import annotations

import pytest

from riskagent_backend.proactive_agents.base import (
    Belief,
    Desire,
    Intention,
    BaseProactiveAgent,
)


class TestBelief:
    """测试 Belief."""

    def test_create_belief(self) -> None:
        """测试创建信念."""
        belief = Belief(
            content="the sky is blue",
            source="observation",
            confidence=0.9,
        )
        assert belief.belief_id is not None
        assert belief.content == "the sky is blue"
        assert belief.source == "observation"
        assert belief.confidence == 0.9


class TestDesire:
    """测试 Desire."""

    def test_create_desire(self) -> None:
        """测试创建愿望."""
        desire = Desire(
            description="solve the problem",
            priority=100,
        )
        assert desire.desire_id is not None
        assert desire.description == "solve the problem"
        assert desire.priority == 100
        assert desire.active is True


class TestIntention:
    """测试 Intention."""

    def test_create_intention(self) -> None:
        """测试创建意图."""
        intention = Intention(
            description="call the query tool",
            tool_name="query_positions",
            tool_params={"desk": "Equities"},
        )
        assert intention.intention_id is not None
        assert intention.description == "call the query tool"
        assert intention.tool_name == "query_positions"
        assert intention.tool_params == {"desk": "Equities"}
        assert intention.status == "pending"


class TestBaseProactiveAgent:
    """测试 BaseProactiveAgent."""

    def test_add_belief(self) -> None:
        """测试添加信念."""
        agent = BaseProactiveAgent(
            name="test_agent",
            system_prompt="You are a test agent",
            enable_background_monitor=False,
        )
        
        belief = agent.add_belief(
            content="task received",
            source="user_input",
            confidence=1.0,
        )
        
        assert belief is not None
        assert len(agent._beliefs) == 1
        assert agent._beliefs[0].content == "task received"

    def test_get_beliefs(self) -> None:
        """测试获取信念."""
        agent = BaseProactiveAgent(
            name="test_agent",
            system_prompt="You are a test agent",
            enable_background_monitor=False,
        )
        
        agent.add_belief(content="belief1", source="source1")
        agent.add_belief(content="belief2", source="source2")
        
        all_beliefs = agent.get_beliefs()
        assert len(all_beliefs) == 2
        
        source1_beliefs = agent.get_beliefs(source="source1")
        assert len(source1_beliefs) == 1
        assert source1_beliefs[0].content == "belief1"

    def test_add_desire(self) -> None:
        """测试添加愿望."""
        agent = BaseProactiveAgent(
            name="test_agent",
            system_prompt="You are a test agent",
            enable_background_monitor=False,
        )
        
        desire = agent.add_desire(
            description="complete the task",
            priority=100,
        )
        
        assert desire is not None
        assert len(agent._desires) == 1

    def test_get_active_desires(self) -> None:
        """测试获取活跃愿望."""
        agent = BaseProactiveAgent(
            name="test_agent",
            system_prompt="You are a test agent",
            enable_background_monitor=False,
        )
        
        agent.add_desire(description="low priority", priority=10)
        agent.add_desire(description="high priority", priority=100)
        
        active = agent.get_active_desires()
        assert len(active) == 2
        assert active[0].priority == 100
        assert active[1].priority == 10

    def test_add_intention(self) -> None:
        """测试添加意图."""
        agent = BaseProactiveAgent(
            name="test_agent",
            system_prompt="You are a test agent",
            enable_background_monitor=False,
        )
        
        intention = agent.add_intention(
            description="do something",
            tool_name="tool_a",
            tool_params={"param": "value"},
        )
        
        assert intention is not None
        assert len(agent._intentions) == 1

    def test_get_pending_intentions(self) -> None:
        """测试获取待处理意图."""
        agent = BaseProactiveAgent(
            name="test_agent",
            system_prompt="You are a test agent",
            enable_background_monitor=False,
        )
        
        agent.add_intention(description="pending1")
        agent.add_intention(description="pending2")
        
        pending = agent.get_pending_intentions()
        assert len(pending) == 2

    def test_update_intention_status(self) -> None:
        """测试更新意图状态."""
        agent = BaseProactiveAgent(
            name="test_agent",
            system_prompt="You are a test agent",
            enable_background_monitor=False,
        )
        
        intention = agent.add_intention(description="test")
        
        updated = agent.update_intention_status(
            intention_id=intention.intention_id,
            status="in_progress",
        )
        assert updated is True
        assert intention.status == "in_progress"

    def test_get_bdi_state(self) -> None:
        """测试获取 BDI 状态."""
        agent = BaseProactiveAgent(
            name="test_agent",
            system_prompt="You are a test agent",
            enable_background_monitor=False,
        )
        
        agent.add_belief(content="test belief", source="test")
        agent.add_desire(description="test desire")
        agent.add_intention(description="test intention")
        
        state = agent.get_bdi_state()
        
        assert "agent_name" in state
        assert "beliefs" in state
        assert "desires" in state
        assert "intentions" in state
        assert len(state["beliefs"]) == 1
        assert len(state["desires"]) == 1
        assert len(state["intentions"]) == 1

    def test_record_llm_interaction(self) -> None:
        """测试记录 LLM 交互."""
        agent = BaseProactiveAgent(
            name="test_agent",
            system_prompt="You are a test agent",
            enable_background_monitor=False,
        )
        
        agent.record_llm_interaction(
            interaction_type="thought",
            system_prompt="test system",
            user_prompt="test user",
            raw_response="test response",
            parsed_output={"thought": "test"},
            latency_ms=100,
            model="test-model",
            success=True,
        )
        
        interactions = agent.get_llm_interactions()
        assert len(interactions) == 1
        assert interactions[0]["interaction_type"] == "thought"
        assert interactions[0]["latency_ms"] == 100


# ------------------------------------------------------------------ #
# RFC-006 BDI 信念去重 - 新增测试
# ------------------------------------------------------------------ #

class TestBeliefDedupFields:
    """测试 Belief 的 processed/processed_at 新字段 (RFC-006)."""

    def test_belief_processed_default_false(self) -> None:
        """Belief 默认 processed=False."""
        belief = Belief(content="test", source="test")
        assert belief.processed is False

    def test_belief_processed_at_default_none(self) -> None:
        """Belief 默认 processed_at=None."""
        belief = Belief(content="test", source="test")
        assert belief.processed_at is None

    def test_belief_processed_can_be_set(self) -> None:
        """Belief 的 processed/processed_at 可被设置."""
        import time
        belief = Belief(content="test", source="test")
        belief.processed = True
        belief.processed_at = time.time()
        assert belief.processed is True
        assert belief.processed_at is not None


class TestIntentionSourceBeliefId:
    """测试 Intention 的 source_belief_id 新字段 (RFC-006)."""

    def test_intention_source_belief_id_default_none(self) -> None:
        """Intention 默认 source_belief_id=None."""
        intention = Intention(description="test")
        assert intention.source_belief_id is None

    def test_intention_source_belief_id_can_be_set(self) -> None:
        """Intention 的 source_belief_id 可被设置."""
        intention = Intention(description="test", source_belief_id="belief_abc123")
        assert intention.source_belief_id == "belief_abc123"


class TestAddIntentionDedup:
    """测试 add_intention() 内容去重 (RFC-006 Checkpoint 4)."""

    def test_duplicate_intention_not_created(self) -> None:
        """相同内容的 pending 意图不重复创建."""
        agent = BaseProactiveAgent(
            name="test_agent",
            system_prompt="test",
            enable_background_monitor=False,
        )
        first = agent.add_intention(
            description="do something",
            tool_name="tool_a",
            tool_params={"param": "value"},
        )
        second = agent.add_intention(
            description="do something",
            tool_name="tool_a",
            tool_params={"param": "value"},
        )
        # 应返回同一个意图,不创建新的
        assert first.intention_id == second.intention_id
        assert len(agent._intentions) == 1

    def test_different_intention_created(self) -> None:
        """不同内容的意图各自创建."""
        agent = BaseProactiveAgent(
            name="test_agent",
            system_prompt="test",
            enable_background_monitor=False,
        )
        agent.add_intention(description="do A", tool_name="tool_a")
        agent.add_intention(description="do B", tool_name="tool_b")
        assert len(agent._intentions) == 2

    def test_completed_intention_allows_new_duplicate(self) -> None:
        """已完成的意图不被去重 (get_pending_intentions 只返回 pending)."""
        agent = BaseProactiveAgent(
            name="test_agent",
            system_prompt="test",
            enable_background_monitor=False,
        )
        first = agent.add_intention(
            description="do something",
            tool_name="tool_a",
            tool_params={"param": "value"},
        )
        # 将第一个意图标记为 completed
        agent.update_intention_status(first.intention_id, "completed")
        # 再次添加相同内容,因为第一个已不是 pending,应创建新的
        second = agent.add_intention(
            description="do something",
            tool_name="tool_a",
            tool_params={"param": "value"},
        )
        assert first.intention_id != second.intention_id
        assert len(agent._intentions) == 2

    def test_add_intention_with_source_belief_id(self) -> None:
        """add_intention 传入 source_belief_id 被正确记录."""
        agent = BaseProactiveAgent(
            name="test_agent",
            system_prompt="test",
            enable_background_monitor=False,
        )
        intention = agent.add_intention(
            description="test",
            source_belief_id="belief_abc123",
        )
        assert intention.source_belief_id == "belief_abc123"


class TestCleanupBeliefs:
    """测试 _cleanup_beliefs() 清理逻辑 (RFC-006 Checkpoint 3)."""

    def test_cleanup_removes_old_processed_beliefs(self) -> None:
        """已处理且超过保留时长的信念被清理."""
        import time
        agent = BaseProactiveAgent(
            name="test_agent",
            system_prompt="test",
            enable_background_monitor=False,
        )
        # 添加一个信念并标记为已处理
        old_belief = agent.add_belief(content="old", source="test")
        old_belief.processed = True
        old_belief.processed_at = time.time() - 400  # 超过 300s 保留时长

        # 添加一个未处理的信念
        agent.add_belief(content="fresh", source="test")

        removed = agent._cleanup_beliefs(max_age_seconds=300)
        assert removed == 1
        assert len(agent._beliefs) == 1
        assert agent._beliefs[0].content == "fresh"

    def test_cleanup_keeps_recent_processed_beliefs(self) -> None:
        """已处理但未超过保留时长的信念不被清理."""
        import time
        agent = BaseProactiveAgent(
            name="test_agent",
            system_prompt="test",
            enable_background_monitor=False,
        )
        recent_belief = agent.add_belief(content="recent", source="test")
        recent_belief.processed = True
        recent_belief.processed_at = time.time() - 100  # 未超过 300s

        removed = agent._cleanup_beliefs(max_age_seconds=300)
        assert removed == 0
        assert len(agent._beliefs) == 1

    def test_cleanup_keeps_unprocessed_beliefs(self) -> None:
        """未处理的信念不被清理."""
        agent = BaseProactiveAgent(
            name="test_agent",
            system_prompt="test",
            enable_background_monitor=False,
        )
        agent.add_belief(content="unprocessed", source="test")

        removed = agent._cleanup_beliefs(max_age_seconds=300)
        assert removed == 0
        assert len(agent._beliefs) == 1

    def test_cleanup_returns_count(self) -> None:
        """_cleanup_beliefs 返回被清理的数量."""
        import time
        agent = BaseProactiveAgent(
            name="test_agent",
            system_prompt="test",
            enable_background_monitor=False,
        )
        for i in range(3):
            b = agent.add_belief(content=f"old_{i}", source="test")
            b.processed = True
            b.processed_at = time.time() - 400

        removed = agent._cleanup_beliefs(max_age_seconds=300)
        assert removed == 3
        assert len(agent._beliefs) == 0


class TestBdiStateExport:
    """测试 get_bdi_state() 导出新字段 (RFC-006 Checkpoint 6)."""

    def test_bdi_state_belief_exports_processed_fields(self) -> None:
        """get_bdi_state 导出 belief 的 processed/processed_at."""
        agent = BaseProactiveAgent(
            name="test_agent",
            system_prompt="test",
            enable_background_monitor=False,
        )
        agent.add_belief(content="test", source="test")

        state = agent.get_bdi_state()
        assert len(state["beliefs"]) == 1
        belief_dict = state["beliefs"][0]
        assert "processed" in belief_dict
        assert "processed_at" in belief_dict
        assert belief_dict["processed"] is False
        assert belief_dict["processed_at"] is None

    def test_bdi_state_intention_exports_source_belief_id(self) -> None:
        """get_bdi_state 导出 intention 的 source_belief_id."""
        agent = BaseProactiveAgent(
            name="test_agent",
            system_prompt="test",
            enable_background_monitor=False,
        )
        agent.add_intention(
            description="test",
            source_belief_id="belief_abc123",
        )

        state = agent.get_bdi_state()
        assert len(state["intentions"]) == 1
        intention_dict = state["intentions"][0]
        assert "source_belief_id" in intention_dict
        assert intention_dict["source_belief_id"] == "belief_abc123"

    def test_bdi_state_intention_source_belief_id_default_none(self) -> None:
        """未设置 source_belief_id 时导出为 None."""
        agent = BaseProactiveAgent(
            name="test_agent",
            system_prompt="test",
            enable_background_monitor=False,
        )
        agent.add_intention(description="test")

        state = agent.get_bdi_state()
        assert state["intentions"][0]["source_belief_id"] is None
