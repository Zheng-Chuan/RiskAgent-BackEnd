"""P1 阈值规则引擎验收测试 (Checkpoint 16.3.1)."""

import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from riskagent_backend.perception import (
    PerceptionSignal,
    SignalSeverity,
    FilterRule,
    PerceptionFilterEngine,
    get_default_rules,
)


def test_normal_signals_not_escalated():
    """验收: 正常信号不升级到 LLM."""
    print("=" * 60)
    print("P1 验收测试: 正常信号不升级")
    print("=" * 60)

    engine = PerceptionFilterEngine(get_default_rules())

    normal_signals = [
        PerceptionSignal(source="docker", metric="container_status", value="running"),
        PerceptionSignal(source="docker", metric="cpu_percent", value=45.0),
        PerceptionSignal(source="docker", metric="memory_percent", value=30.0),
        PerceptionSignal(source="redis", metric="memory_usage_percent", value=35.0),
        PerceptionSignal(source="redis", metric="connection_status", value="available"),
        PerceptionSignal(source="redis", metric="keyspace_hit_rate", value=0.95),
        PerceptionSignal(source="mysql", metric="slow_queries", value=2),
        PerceptionSignal(source="mysql", metric="connection_status", value="available"),
        PerceptionSignal(source="prometheus", metric="error_rate", value=0.01),
    ]

    for signal in normal_signals:
        filtered = engine.filter(signal)
        assert filtered.severity == SignalSeverity.INFO, (
            f"正常信号不应升级: {signal.source}.{signal.metric}={signal.value} "
            f"-> severity={filtered.severity}"
        )
        assert not filtered.should_escalate()

    print(f"[PASS] {len(normal_signals)} 个正常信号全部保持 INFO 级别 (不升级)")
    return normal_signals


def test_abnormal_signals_escalated():
    """验收: 异常信号正确命中规则并产出标准化信号."""
    print("\n" + "=" * 60)
    print("P1 验收测试: 异常信号正确升级")
    print("=" * 60)

    engine = PerceptionFilterEngine(get_default_rules())

    abnormal_signals = [
        PerceptionSignal(source="docker", metric="container_status", value="exited"),
        PerceptionSignal(source="docker", metric="cpu_percent", value=95.0),
        PerceptionSignal(source="redis", metric="memory_usage_percent", value=85.0),
        PerceptionSignal(source="redis", metric="connection_status", value="unavailable"),
        PerceptionSignal(source="mysql", metric="slow_queries", value=25),
        PerceptionSignal(source="prometheus", metric="error_rate", value=0.15),
    ]

    expected_severities = [
        SignalSeverity.CRITICAL,
        SignalSeverity.WARNING,
        SignalSeverity.CRITICAL,
        SignalSeverity.CRITICAL,
        SignalSeverity.WARNING,
        SignalSeverity.CRITICAL,
    ]

    for signal, expected in zip(abnormal_signals, expected_severities):
        filtered = engine.filter(signal)
        assert filtered.severity == expected, (
            f"异常信号应升级到 {expected.value}: {signal.source}.{signal.metric}={signal.value} "
            f"-> severity={filtered.severity.value}"
        )
        assert filtered.should_escalate()
        assert filtered.threshold is not None
        assert filtered.message != ""
        assert "rule" in filtered.context

    print(f"[PASS] {len(abnormal_signals)} 个异常信号全部正确命中规则并升级")
    return abnormal_signals


def test_rules_configurable():
    """验收: 规则可配置，不硬编码."""
    print("\n" + "=" * 60)
    print("P1 验收测试: 规则可配置")
    print("=" * 60)

    default_rules = get_default_rules()
    assert len(default_rules) > 0
    print(f"[PASS] 默认规则集包含 {len(default_rules)} 条规则")

    custom_rule = FilterRule(
        name="custom_disk_full",
        source="docker",
        metric="disk_percent",
        predicate=lambda v: v > 95.0,
        severity=SignalSeverity.CRITICAL,
        threshold=95.0,
        message="磁盘使用率超过 95%",
    )
    engine = PerceptionFilterEngine([custom_rule])
    signal = PerceptionSignal(source="docker", metric="disk_percent", value=98.0)
    filtered = engine.filter(signal)
    assert filtered.severity == SignalSeverity.CRITICAL
    print("[PASS] 自定义规则正确生效")

    engine.add_rule(FilterRule(
        name="custom_temp_high",
        source="docker",
        metric="temperature",
        predicate=lambda v: v > 80,
        severity=SignalSeverity.WARNING,
        threshold=80,
        message="温度过高",
    ))
    signal2 = PerceptionSignal(source="docker", metric="temperature", value=90)
    filtered2 = engine.filter(signal2)
    assert filtered2.severity == SignalSeverity.WARNING
    print("[PASS] 动态添加规则正确生效")

    engine.set_rules(get_default_rules())
    assert len(engine._rules) == len(get_default_rules())
    print("[PASS] set_rules 正确替换全部规则")


def test_batch_filter_and_escalation():
    """验收: 批量过滤和升级筛选."""
    print("\n" + "=" * 60)
    print("P1 验收测试: 批量过滤与升级筛选")
    print("=" * 60)

    engine = PerceptionFilterEngine(get_default_rules())

    batch = [
        PerceptionSignal(source="docker", metric="container_status", value="running"),
        PerceptionSignal(source="docker", metric="container_status", value="exited"),
        PerceptionSignal(source="redis", metric="memory_usage_percent", value=30.0),
        PerceptionSignal(source="redis", metric="memory_usage_percent", value=85.0),
        PerceptionSignal(source="mysql", metric="slow_queries", value=2),
        PerceptionSignal(source="prometheus", metric="error_rate", value=0.15),
    ]

    filtered = engine.filter_batch(batch)
    assert len(filtered) == len(batch)
    print(f"[PASS] 批量过滤 {len(batch)} 个信号完成")

    escalations = engine.get_escalation_signals(batch)
    assert len(escalations) == 3, f"应有 3 个升级信号, 实际 {len(escalations)}"
    print(f"[PASS] 从 {len(batch)} 个信号中筛选出 {len(escalations)} 个升级信号")

    for sig in escalations:
        assert sig.should_escalate()
        print(f"  - {sig.source}.{sig.metric}={sig.value} -> {sig.severity.value}")


def test_perception_signal_structure():
    """验收: PerceptionSignal 结构完整性."""
    print("\n" + "=" * 60)
    print("P1 验收测试: PerceptionSignal 结构完整性")
    print("=" * 60)

    signal = PerceptionSignal(
        source="docker",
        metric="container_status",
        value="exited",
        severity=SignalSeverity.CRITICAL,
        message="容器退出",
        context={"container_name": "riskagent-mysql"},
    )

    d = signal.to_log_dict()
    for key in ("source", "metric", "value", "threshold", "severity", "message", "timestamp"):
        assert key in d, f"序列化缺少字段: {key}"
    print("[PASS] PerceptionSignal 序列化字段完整")

    assert signal.should_escalate() is True
    info_signal = PerceptionSignal(source="docker", metric="cpu", value=50.0)
    assert info_signal.should_escalate() is False
    print("[PASS] should_escalate() 正确判断")


def main():
    try:
        test_normal_signals_not_escalated()
        test_abnormal_signals_escalated()
        test_rules_configurable()
        test_batch_filter_and_escalation()
        test_perception_signal_structure()

        print("\n" + "=" * 60)
        print("P1 Checkpoint 16.3.1 验收: 全部通过")
        print("=" * 60)
        print("\n P1 全部验收通过!")
        return 0
    except AssertionError as e:
        print(f"\n FAIL 验收失败: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
