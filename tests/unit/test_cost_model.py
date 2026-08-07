"""Phase 14 LLM 成本模型测试.

测试场景:
1. TokenUsageRecord 新增字段默认值
2. TokenTracker.record() 带 agent_name/stage 参数
3. TokenTracker.summary() 包含 by_agent_stage 维度
4. calculate_call_cost() 成本计算正确
5. generate_cost_estimate_table() 四窗口预估表正确
6. CostCircuitBreaker 超限熔断
7. CostCircuitBreaker 冷却后恢复
8. /api/llm/cost-model 端点返回正确结构
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SRC_ROOT = _PROJECT_ROOT / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))


@pytest.fixture(autouse=True)
def _reset_trackers(monkeypatch: pytest.MonkeyPatch):
    """每个测试前重置 TokenTracker 和 CostCircuitBreaker 全局状态."""
    monkeypatch.delenv("LLM_COST_PROMPT_PER_1K", raising=False)
    monkeypatch.delenv("LLM_COST_COMPLETION_PER_1K", raising=False)

    from riskagent_backend.llm.token_tracker import get_token_tracker, reset_token_tracker
    from riskagent_backend.governance.cost_circuit_breaker import (
        get_cost_circuit_breaker,
        reset_cost_circuit_breaker,
    )

    reset_token_tracker()
    get_token_tracker().reset()

    reset_cost_circuit_breaker()
    breaker = get_cost_circuit_breaker()
    breaker.reset()

    yield

    reset_token_tracker()
    reset_cost_circuit_breaker()


# ------------------------------------------------------------------ #
# Checkpoint 20.1.1: TokenUsageRecord 新增字段
# ------------------------------------------------------------------ #
def test_token_usage_record_default_fields() -> None:
    """TokenUsageRecord 的 agent_name 和 stage 默认为空字符串."""
    from riskagent_backend.llm.token_tracker import TokenUsageRecord

    record = TokenUsageRecord(
        timestamp=0.0,
        model="test",
        prompt_tokens=100,
        completion_tokens=50,
        total_tokens=150,
    )
    assert record.agent_name == ""
    assert record.stage == ""


def test_token_usage_record_with_agent_stage() -> None:
    """TokenUsageRecord 可以设置 agent_name 和 stage."""
    from riskagent_backend.llm.token_tracker import TokenUsageRecord

    record = TokenUsageRecord(
        timestamp=0.0,
        model="test",
        prompt_tokens=100,
        completion_tokens=50,
        total_tokens=150,
        agent_name="orchestrator",
        stage="thought",
    )
    assert record.agent_name == "orchestrator"
    assert record.stage == "thought"


# ------------------------------------------------------------------ #
# Checkpoint 20.1.1: TokenTracker.record() 带 agent_name/stage
# ------------------------------------------------------------------ #
def test_token_tracker_record_with_agent_stage() -> None:
    """TokenTracker.record() 接受 agent_name 和 stage 参数."""
    from riskagent_backend.llm.token_tracker import get_token_tracker

    tracker = get_token_tracker()
    tracker.reset()
    tracker.record(
        model="deepseek/deepseek-chat",
        prompt_tokens=100,
        completion_tokens=50,
        total_tokens=150,
        agent_name="orchestrator",
        stage="thought",
    )
    assert tracker.total_in_window() == 150


def test_token_tracker_record_without_agent_stage() -> None:
    """不传 agent_name/stage 时仍正常工作（向后兼容）."""
    from riskagent_backend.llm.token_tracker import get_token_tracker

    tracker = get_token_tracker()
    tracker.reset()
    tracker.record(
        model="test",
        prompt_tokens=100,
        completion_tokens=50,
        total_tokens=150,
    )
    assert tracker.total_in_window() == 150


# ------------------------------------------------------------------ #
# Checkpoint 20.1.1: summary() 包含 by_agent_stage
# ------------------------------------------------------------------ #
def test_summary_contains_by_agent_stage() -> None:
    """summary() 返回值包含 by_agent_stage 维度."""
    from riskagent_backend.llm.token_tracker import get_token_tracker

    tracker = get_token_tracker()
    tracker.reset()
    tracker.record(
        model="test", prompt_tokens=100, completion_tokens=50, total_tokens=150,
        agent_name="orchestrator", stage="thought",
    )
    tracker.record(
        model="test", prompt_tokens=200, completion_tokens=100, total_tokens=300,
        agent_name="critic", stage="evidence",
    )
    tracker.record(
        model="test", prompt_tokens=50, completion_tokens=25, total_tokens=75,
        agent_name="orchestrator", stage="thought",
    )

    summary = tracker.summary()
    assert "by_agent_stage" in summary

    by_agent_stage = summary["by_agent_stage"]
    key = "orchestrator:thought"
    assert key in by_agent_stage
    assert by_agent_stage[key]["calls"] == 2
    assert by_agent_stage[key]["total_tokens"] == 225

    key2 = "critic:evidence"
    assert key2 in by_agent_stage
    assert by_agent_stage[key2]["calls"] == 1
    assert by_agent_stage[key2]["total_tokens"] == 300


def test_summary_by_agent_stage_without_labels() -> None:
    """未标注 agent_name/stage 的记录归入 unknown:unknown."""
    from riskagent_backend.llm.token_tracker import get_token_tracker

    tracker = get_token_tracker()
    tracker.reset()
    tracker.record(
        model="test", prompt_tokens=100, completion_tokens=50, total_tokens=150,
    )
    summary = tracker.summary()
    assert "unknown:unknown" in summary["by_agent_stage"]


# ------------------------------------------------------------------ #
# Checkpoint 20.1.2: calculate_call_cost
# ------------------------------------------------------------------ #
def test_calculate_call_cost_deepseek() -> None:
    """deepseek/deepseek-chat 成本计算正确."""
    from riskagent_backend.llm.cost_model import calculate_call_cost

    cost = calculate_call_cost(1000, 500, "deepseek/deepseek-chat")
    assert cost == round(0.00014 + 0.00014, 6)
    assert cost == 0.00028


def test_calculate_call_cost_unknown_model_uses_default() -> None:
    """未知模型使用 default 定价."""
    from riskagent_backend.llm.cost_model import calculate_call_cost, get_pricing

    cost = calculate_call_cost(1000, 500, "unknown/model")
    default_pricing = get_pricing("default")
    expected = round(
        (1000 / 1000) * default_pricing["prompt"]
        + (500 / 1000) * default_pricing["completion"],
        6,
    )
    assert cost == expected


def test_calculate_chain_cost() -> None:
    """calculate_chain_cost 按 stage 分组统计."""
    from riskagent_backend.llm.cost_model import calculate_chain_cost

    records = [
        {"prompt_tokens": 1000, "completion_tokens": 500, "model": "deepseek/deepseek-chat", "stage": "thought"},
        {"prompt_tokens": 2000, "completion_tokens": 1000, "model": "deepseek/deepseek-chat", "stage": "evidence"},
        {"prompt_tokens": 500, "completion_tokens": 200, "model": "deepseek/deepseek-chat", "stage": "thought"},
    ]
    result = calculate_chain_cost(records)
    assert result["call_count"] == 3
    assert "thought" in result["by_stage"]
    assert "evidence" in result["by_stage"]
    assert result["by_stage"]["thought"]["calls"] == 2
    assert result["by_stage"]["evidence"]["calls"] == 1
    assert result["total_cost"] > 0


# ------------------------------------------------------------------ #
# Checkpoint 20.1.3: generate_cost_estimate_table
# ------------------------------------------------------------------ #
def test_generate_cost_estimate_table_four_windows() -> None:
    """预估表包含 5min / 1h / 24h / 7d 四个窗口."""
    from riskagent_backend.llm.cost_model import generate_cost_estimate_table

    summary = {
        "calls": 10,
        "total_tokens": 5000,
        "cost_estimate": 0.001,
    }
    table = generate_cost_estimate_table(summary, dedup_enabled=False)
    assert "5min" in table
    assert "1h" in table
    assert "24h" in table
    assert "7d" in table


def test_generate_cost_estimate_table_multipliers() -> None:
    """各窗口的倍率正确（1x / 12x / 288x / 2016x）."""
    from riskagent_backend.llm.cost_model import generate_cost_estimate_table

    summary = {"calls": 10, "total_tokens": 5000, "cost_estimate": 0.001}
    table = generate_cost_estimate_table(summary, dedup_enabled=False)

    assert table["5min"]["estimated_calls"] == 10
    assert table["1h"]["estimated_calls"] == 120
    assert table["24h"]["estimated_calls"] == 2880
    assert table["7d"]["estimated_calls"] == 20160

    assert table["5min"]["estimated_cost_usd"] == round(0.001, 4)
    assert table["1h"]["estimated_cost_usd"] == round(0.001 * 12, 4)
    assert table["24h"]["estimated_cost_usd"] == round(0.001 * 288, 4)
    assert table["7d"]["estimated_cost_usd"] == round(0.001 * 2016, 4)


def test_generate_cost_estimate_table_dedup() -> None:
    """去重模式下调用数和成本降低 80%."""
    from riskagent_backend.llm.cost_model import generate_cost_estimate_table

    summary = {"calls": 100, "total_tokens": 50000, "cost_estimate": 0.01}
    table_no_dedup = generate_cost_estimate_table(summary, dedup_enabled=False)
    table_dedup = generate_cost_estimate_table(summary, dedup_enabled=True)

    assert table_dedup["5min"]["estimated_calls"] == 20
    assert table_no_dedup["5min"]["estimated_calls"] == 100
    assert table_dedup["5min"]["dedup_enabled"] is True
    assert table_no_dedup["5min"]["dedup_enabled"] is False


def test_generate_cost_estimate_table_empty_uses_baseline() -> None:
    """空数据时使用 Phase 10 实测基线."""
    from riskagent_backend.llm.cost_model import (
        calculate_call_cost,
        generate_cost_estimate_table,
    )

    summary = {"calls": 0, "total_tokens": 0, "cost_estimate": 0.0}
    table = generate_cost_estimate_table(summary, dedup_enabled=False)

    baseline_cost = calculate_call_cost(580000, 200000, "deepseek/deepseek-chat")
    assert table["5min"]["estimated_calls"] == 133
    assert table["5min"]["estimated_cost_usd"] == round(baseline_cost, 4)


# ------------------------------------------------------------------ #
# Checkpoint 20.1.2: _estimate_cost 使用 cost_model
# ------------------------------------------------------------------ #
def test_token_tracker_estimate_cost_uses_pricing_table() -> None:
    """TokenTracker._estimate_cost 使用内置定价表计算非零成本."""
    from riskagent_backend.llm.token_tracker import TokenTracker

    cost = TokenTracker._estimate_cost(
        prompt_tokens=1000,
        completion_tokens=500,
        model="deepseek/deepseek-chat",
    )
    assert cost == 0.00028


def test_token_tracker_estimate_cost_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """环境变量可以覆盖内置定价表."""
    from riskagent_backend.llm.token_tracker import TokenTracker

    monkeypatch.setenv("LLM_COST_PROMPT_PER_1K", "0.001")
    monkeypatch.setenv("LLM_COST_COMPLETION_PER_1K", "0.002")

    cost = TokenTracker._estimate_cost(
        prompt_tokens=1000,
        completion_tokens=500,
        model="deepseek/deepseek-chat",
    )
    assert cost == 0.002


def test_summary_cost_estimate_nonzero() -> None:
    """summary() 的 cost_estimate 在有记录时应非零."""
    from riskagent_backend.llm.token_tracker import get_token_tracker

    tracker = get_token_tracker()
    tracker.reset()
    tracker.record(
        model="deepseek/deepseek-chat",
        prompt_tokens=10000,
        completion_tokens=5000,
        total_tokens=15000,
    )
    summary = tracker.summary()
    assert summary["cost_estimate"] > 0
    assert summary["cost_estimate"] == round(0.0014 + 0.0014, 6)


# ------------------------------------------------------------------ #
# Checkpoint 20.1.4: CostCircuitBreaker
# ------------------------------------------------------------------ #
def test_cost_circuit_breaker_not_tripped_on_empty() -> None:
    """空数据时不应熔断."""
    from riskagent_backend.governance.cost_circuit_breaker import CostCircuitBreaker

    breaker = CostCircuitBreaker()
    result = breaker.check()
    assert result["should_block"] is False


def test_cost_circuit_breaker_trips_on_token_limit() -> None:
    """超过 token 限制时触发熔断."""
    from riskagent_backend.governance.cost_circuit_breaker import CostCircuitBreaker
    from riskagent_backend.llm.token_tracker import get_token_tracker

    tracker = get_token_tracker()
    tracker.reset()
    tracker.record(
        model="test", prompt_tokens=40000, completion_tokens=20000, total_tokens=60000,
    )

    breaker = CostCircuitBreaker()
    result = breaker.check()
    assert result["should_block"] is True
    assert "token_limit_exceeded" in result["reason"]
    assert result["level"] == "5min"
    assert breaker.is_tripped() is True


def test_cost_circuit_breaker_trips_on_cost_limit() -> None:
    """超过成本限制时触发熔断.

    summary() 的整体 cost_estimate 使用 default 定价(deepseek)。
    default: prompt 0.00014/1K, completion 0.00028/1K
    5min cost_limit = 0.01
    prompt=20000 + completion=30000 => cost = 0.0028 + 0.0084 = 0.0112 > 0.01
    total=50000 不超过 token_limit(50000) => 不触发 token 限制
    """
    from riskagent_backend.governance.cost_circuit_breaker import CostCircuitBreaker
    from riskagent_backend.llm.token_tracker import get_token_tracker

    tracker = get_token_tracker()
    tracker.reset()
    tracker.record(
        model="deepseek/deepseek-chat",
        prompt_tokens=20000,
        completion_tokens=30000,
        total_tokens=50000,
    )

    breaker = CostCircuitBreaker()
    result = breaker.check()
    assert result["should_block"] is True
    assert "cost_limit_exceeded" in result["reason"]
    assert result["level"] == "5min"


def test_cost_circuit_breaker_cooldown_recovery() -> None:
    """熔断后冷却结束自动恢复."""
    from riskagent_backend.governance.cost_circuit_breaker import CostCircuitBreaker
    from riskagent_backend.llm.token_tracker import get_token_tracker

    tracker = get_token_tracker()
    tracker.reset()
    tracker.record(
        model="test", prompt_tokens=40000, completion_tokens=20000, total_tokens=60000,
    )

    breaker = CostCircuitBreaker(cooldown_s=0)
    result1 = breaker.check()
    assert result1["should_block"] is True

    tracker.reset()
    result2 = breaker.check()
    assert result2["should_block"] is False


def test_cost_circuit_breaker_reset() -> None:
    """reset() 清除所有熔断状态."""
    from riskagent_backend.governance.cost_circuit_breaker import CostCircuitBreaker
    from riskagent_backend.llm.token_tracker import get_token_tracker

    tracker = get_token_tracker()
    tracker.reset()
    tracker.record(
        model="test", prompt_tokens=40000, completion_tokens=20000, total_tokens=60000,
    )

    breaker = CostCircuitBreaker()
    result = breaker.check()
    assert result["should_block"] is True
    assert breaker.is_tripped() is True

    breaker.reset()
    assert breaker.is_tripped() is False


def test_cost_circuit_breaker_thread_safe() -> None:
    """CostCircuitBreaker 是线程安全的."""
    import threading

    from riskagent_backend.governance.cost_circuit_breaker import CostCircuitBreaker

    breaker = CostCircuitBreaker()
    errors: list = []

    def _check_multiple():
        try:
            for _ in range(100):
                breaker.check()
                breaker.is_tripped()
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=_check_multiple) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(errors) == 0


# ------------------------------------------------------------------ #
# Checkpoint 20.1.4: ProactiveBudgetManager 集成
# ------------------------------------------------------------------ #
def test_proactive_budget_blocks_on_cost_circuit_breaker() -> None:
    """ProactiveBudgetManager 在成本熔断时拒绝请求."""
    from riskagent_backend.governance.proactive_budget import (
        ProactiveBudgetManager,
        reset_proactive_budget_manager,
    )
    from riskagent_backend.governance.cost_circuit_breaker import (
        get_cost_circuit_breaker,
        reset_cost_circuit_breaker,
    )
    from riskagent_backend.llm.token_tracker import get_token_tracker

    tracker = get_token_tracker()
    tracker.reset()
    tracker.record(
        model="test", prompt_tokens=40000, completion_tokens=20000, total_tokens=60000,
    )

    reset_proactive_budget_manager()
    reset_cost_circuit_breaker()
    breaker = get_cost_circuit_breaker()
    breaker.reset()

    manager = ProactiveBudgetManager()
    event = {
        "payload": {
            "content": "test event",
        },
    }
    decision = manager.evaluate_and_reserve(run_id="test-run-1", event=event)
    assert decision.allowed is False
    assert "token_limit_exceeded" in decision.reason or "cost_limit_exceeded" in decision.reason


# ------------------------------------------------------------------ #
# Checkpoint 20.1.3: /api/llm/cost-model 端点结构
# ------------------------------------------------------------------ #
def test_cost_model_endpoint_structure() -> None:
    """cost_model 端点返回正确的结构."""
    from riskagent_backend.llm.cost_model import (
        generate_cost_estimate_table,
        get_pricing,
    )
    from riskagent_backend.llm.token_tracker import get_token_tracker

    tracker = get_token_tracker()
    tracker.reset()
    tracker.record(
        model="deepseek/deepseek-chat",
        prompt_tokens=1000,
        completion_tokens=500,
        total_tokens=1500,
        agent_name="orchestrator",
        stage="thought",
    )

    summary = tracker.summary()
    table_no_dedup = generate_cost_estimate_table(summary, dedup_enabled=False)
    table_with_dedup = generate_cost_estimate_table(summary, dedup_enabled=True)

    result = {
        "baseline_5min": summary,
        "cost_estimate_no_dedup": table_no_dedup,
        "cost_estimate_with_dedup": table_with_dedup,
        "pricing": get_pricing("deepseek/deepseek-chat"),
    }

    assert "baseline_5min" in result
    assert "cost_estimate_no_dedup" in result
    assert "cost_estimate_with_dedup" in result
    assert "pricing" in result

    pricing = result["pricing"]
    assert "prompt" in pricing
    assert "completion" in pricing

    for table_key in ("cost_estimate_no_dedup", "cost_estimate_with_dedup"):
        table = result[table_key]
        for window in ("5min", "1h", "24h", "7d"):
            assert window in table
            assert "estimated_calls" in table[window]
            assert "estimated_cost_usd" in table[window]
            assert "dedup_enabled" in table[window]

    assert "by_agent_stage" in result["baseline_5min"]
    assert "orchestrator:thought" in result["baseline_5min"]["by_agent_stage"]
