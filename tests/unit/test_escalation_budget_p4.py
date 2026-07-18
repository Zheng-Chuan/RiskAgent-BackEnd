"""P4 异常升级触发 + LLM 频率控制验收测试 (Checkpoint 16.3.2 + 16.3.3)."""

import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from riskmonitor_multiagent.perception import (
    PerceptionSignal, SignalSeverity,
    PerceptionFilterEngine, get_default_rules,
    EscalationManager, SystemEvent,
    PerceptionBudgetManager,
)


def test_escalation_critical():
    """验收 16.3.2: critical 信号生成 system_event."""
    print("=" * 60)
    print("P4 验收测试: 异常升级触发 (16.3.2)")
    print("=" * 60)

    engine = PerceptionFilterEngine(get_default_rules())
    esc = EscalationManager()

    signals = [
        PerceptionSignal(source="docker", metric="container_status", value="exited"),
        PerceptionSignal(source="redis", metric="connection_status", value="unavailable"),
        PerceptionSignal(source="docker", metric="cpu_percent", value=45.0),  # 正常
    ]

    filtered = engine.filter_batch(signals)
    event = esc.escalate(filtered)

    assert event is not None, "应生成升级事件"
    assert isinstance(event, SystemEvent)
    assert event.severity == "critical"
    assert len(event.signals) == 2  # 2 个升级信号
    assert event.source == "perception_filter"
    print("[PASS] critical 信号正确生成 system_event")
    print(f"  event_id={event.event_id}")
    print(f"  severity={event.severity}")
    print(f"  signals={len(event.signals)}")
    print(f"  description={event.description}")


def test_escalation_warning():
    """验收 16.3.2: warning 信号生成 system_event."""
    print("\n--- warning 级别升级 ---")

    engine = PerceptionFilterEngine(get_default_rules())
    esc = EscalationManager()

    signals = [
        PerceptionSignal(source="docker", metric="cpu_percent", value=95.0),
        PerceptionSignal(source="mysql", metric="slow_queries", value=25),
        PerceptionSignal(source="docker", metric="container_status", value="running"),  # 正常
    ]

    filtered = engine.filter_batch(signals)
    event = esc.escalate(filtered)

    assert event is not None
    assert event.severity == "warning"
    assert len(event.signals) == 2
    print(f"[PASS] warning 信号正确生成 system_event (severity={event.severity})")


def test_no_escalation_for_normal():
    """验收 16.3.2: 正常信号不生成升级事件."""
    print("\n--- 正常信号不升级 ---")

    engine = PerceptionFilterEngine(get_default_rules())
    esc = EscalationManager()

    signals = [
        PerceptionSignal(source="docker", metric="container_status", value="running"),
        PerceptionSignal(source="redis", metric="memory_usage_percent", value=35.0),
    ]

    filtered = engine.filter_batch(signals)
    event = esc.escalate(filtered)

    assert event is None, "正常信号不应生成升级事件"
    print("[PASS] 正常信号未生成升级事件 (None)")


def test_escalation_stats():
    """验收: 升级统计正确."""
    print("\n--- 升级统计 ---")
    esc = EscalationManager()
    engine = PerceptionFilterEngine(get_default_rules())

    # 生成 2 个 critical + 1 个 warning
    for _ in range(2):
        signals = [PerceptionSignal(source="docker", metric="container_status", value="exited")]
        esc.escalate(engine.filter_batch(signals))

    signals = [PerceptionSignal(source="docker", metric="cpu_percent", value=95.0)]
    esc.escalate(engine.filter_batch(signals))

    stats = esc.get_stats()
    assert stats["total_escalated"] == 3
    assert stats["total_critical"] == 2
    assert stats["total_warning"] == 1
    print(f"[PASS] 统计正确: escalated={stats['total_escalated']} critical={stats['total_critical']} warning={stats['total_warning']}")


def test_budget_frequency_control():
    """验收 16.3.3: LLM 频率控制."""
    print("\n" + "=" * 60)
    print("P4 验收测试: LLM 频率控制 (16.3.3)")
    print("=" * 60)

    budget = PerceptionBudgetManager(max_calls_per_minute=3)

    # 前 3 次允许
    for i in range(3):
        assert budget.can_call_llm(), f"第 {i+1} 次应允许"
        budget.record_call(tokens_used=1000, success=True)
    print("[PASS] 前 3 次调用全部允许 (频控上限=3/分钟)")

    # 第 4 次应被拒绝
    assert not budget.can_call_llm(), "第 4 次应被频控拒绝"
    print("[PASS] 第 4 次调用被频控拒绝")


def test_budget_token_limit():
    """验收 16.3.3: token 预算控制."""
    print("\n--- token 预算控制 ---")

    budget = PerceptionBudgetManager(max_tokens_per_hour=5000)

    # 消耗 5000 tokens
    budget.record_call(tokens_used=5000, success=True)
    assert budget.can_call_llm() is False, "预算耗尽应拒绝"
    print("[PASS] token 预算耗尽后拒绝 LLM 调用")
    assert budget.is_circuit_broken(), "应触发熔断"
    print("[PASS] 预算耗尽触发熔断")


def test_circuit_breaker_failures():
    """验收 16.3.3: 连续失败触发熔断."""
    print("\n--- 连续失败熔断 ---")

    budget = PerceptionBudgetManager(circuit_breaker_threshold=3)

    for i in range(3):
        budget.record_call(tokens_used=100, success=False)

    assert budget.is_circuit_broken(), "3 次连续失败应触发熔断"
    assert not budget.can_call_llm(), "熔断后应拒绝 LLM 调用"
    print("[PASS] 3 次连续失败触发熔断，降级为纯规则处置")

    # 手动重置
    budget.reset_circuit_breaker()
    assert budget.can_call_llm(), "重置后应允许调用"
    print("[PASS] 手动重置熔断器后恢复正常")


def test_budget_stats():
    """验收: 预算统计正确."""
    print("\n--- 预算统计 ---")

    budget = PerceptionBudgetManager(max_tokens_per_hour=10000, max_calls_per_minute=10)
    budget.record_call(tokens_used=500, success=True)
    budget.record_call(tokens_used=300, success=True)
    budget.record_call(tokens_used=200, success=False)

    stats = budget.get_stats()
    assert stats["total_calls"] == 3
    assert stats["total_tokens_used"] == 1000
    assert stats["consecutive_failures"] == 1
    print(f"[PASS] 统计正确: calls={stats['total_calls']} tokens={stats['total_tokens_used']} failures={stats['consecutive_failures']}")


def main():
    try:
        test_escalation_critical()
        test_escalation_warning()
        test_no_escalation_for_normal()
        test_escalation_stats()
        test_budget_frequency_control()
        test_budget_token_limit()
        test_circuit_breaker_failures()
        test_budget_stats()

        print("\n" + "=" * 60)
        print("P4 Checkpoint 16.3.2 + 16.3.3 验收: 全部通过")
        print("=" * 60)
        print("\n P4 全部验收通过!")
        return 0
    except AssertionError as e:
        print(f"\n FAIL 验收失败: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
