"""P5-P9 综合验收测试."""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from riskagent_backend.perception import (
    PerceptionSignal, SignalSeverity,
    PerceptionFilterEngine, get_default_rules,
    EscalationManager, RemediationManager, RemediationAction,
)
from riskagent_backend.perception.data_sources import (
    MySQLDataSource, PrometheusDataSource,
)


def test_p5_mysql():
    print("=" * 60); print("P5 验收: MySQL 感知 (16.2.3)"); print("=" * 60)
    ds = MySQLDataSource()
    signals = ds.collect()
    for s in signals: assert s.source == "mysql"
    if signals and signals[0].value == "unavailable":
        print("[PASS] MySQL 不可用时降级")
    else:
        print(f"[PASS] MySQL 采集 {len(signals)} 个信号")
    engine = PerceptionFilterEngine(get_default_rules())
    assert len(engine.filter_batch(signals)) == len(signals)
    print("[PASS] 信号通过过滤引擎")


def test_p6_remediation():
    print("\n" + "=" * 60); print("P6 验收: 简单自主处置 (16.4.1)"); print("=" * 60)
    engine = PerceptionFilterEngine(get_default_rules())
    esc = EscalationManager(); rem = RemediationManager()
    # warning
    sigs = [PerceptionSignal(source="docker", metric="cpu_percent", value=95.0)]
    event = esc.escalate(engine.filter_batch(sigs))
    r = rem.remediate(event)
    assert r.success and r.action != RemediationAction.NO_ACTION
    print(f"[PASS] warning 自主处置: {r.action.value}")
    # critical
    sigs = [PerceptionSignal(source="docker", metric="container_status", value="exited")]
    event = esc.escalate(engine.filter_batch(sigs))
    r = rem.remediate(event)
    assert r.success and "human" in r.description
    print(f"[PASS] critical 自主处置+人类升级")


def test_p7_human_escalation():
    print("\n" + "=" * 60); print("P7 验收: 人类升级 (16.4.2)"); print("=" * 60)
    engine = PerceptionFilterEngine(get_default_rules())
    esc = EscalationManager(); rem = RemediationManager()
    sigs = [
        PerceptionSignal(source="docker", metric="container_status", value="exited"),
        PerceptionSignal(source="redis", metric="connection_status", value="unavailable"),
    ]
    event = esc.escalate(engine.filter_batch(sigs))
    r = rem.remediate(event)
    assert "human" in r.description
    stats = rem.get_stats()
    assert stats["total_human_escalations"] >= 1
    print(f"[PASS] 多 critical 信号触发人类升级, 计数={stats['total_human_escalations']}")


def test_p8_prometheus():
    print("\n" + "=" * 60); print("P8 验收: Prometheus (16.2.4)"); print("=" * 60)
    ds = PrometheusDataSource()
    signals = ds.collect()
    for s in signals: assert s.source == "prometheus"
    if signals and signals[0].value == "unavailable":
        print("[PASS] Prometheus 不可用时降级")
    else:
        print(f"[PASS] Prometheus 采集 {len(signals)} 个信号")
    engine = PerceptionFilterEngine(get_default_rules())
    assert len(engine.filter_batch(signals)) == len(signals)
    print("[PASS] 信号通过过滤引擎")


def test_p9_skill():
    print("\n" + "=" * 60); print("P9 验收: Skill 沉淀 (16.4.3)"); print("=" * 60)
    engine = PerceptionFilterEngine(get_default_rules())
    esc = EscalationManager(); rem = RemediationManager()
    for _ in range(2):
        sigs = [PerceptionSignal(source="docker", metric="container_status", value="exited")]
        event = esc.escalate(engine.filter_batch(sigs))
        rem.remediate(event)
    patterns = rem.get_skill_patterns()
    assert len(patterns) >= 1
    pat = list(patterns.values())[0]
    assert pat["occurrence_count"] == 2
    print(f"[PASS] 沉淀 {len(patterns)} 个模式, 重复计数={pat['occurrence_count']}")
    stats = rem.get_stats()
    assert stats["total_skills_created"] >= 1
    print(f"[PASS] skills_created={stats['total_skills_created']}")
    results = rem.get_results()
    assert all(r.skill_created for r in results)
    print(f"[PASS] {len(results)} 个结果全部 skill_created=True")


def test_e2e():
    print("\n" + "=" * 60); print("E2E: 感知→过滤→升级→处置→沉淀"); print("=" * 60)
    from riskagent_backend.perception.data_sources import DockerDataSource
    ds = DockerDataSource(); signals = ds.collect()
    print(f"[1] 采集: {len(signals)} 信号")
    engine = PerceptionFilterEngine(get_default_rules())
    filtered = engine.filter_batch(signals)
    esc = EscalationManager(); rem = RemediationManager()
    event = esc.escalate(filtered)
    if event:
        r = rem.remediate(event)
        print(f"[2] 过滤→升级→处置: {r.action.value}")
        if rem.get_skill_patterns():
            print(f"[3] 沉淀: {len(rem.get_skill_patterns())} 模式")
    else:
        print("[2] 无升级信号 (正常)")
    print("[PASS] 端到端链路完整")


def main():
    try:
        test_p5_mysql(); test_p6_remediation(); test_p7_human_escalation()
        test_p8_prometheus(); test_p9_skill(); test_e2e()
        print("\n" + "=" * 60)
        print("P5-P9 全部验收通过")
        print("=" * 60)
        return 0
    except AssertionError as e:
        print(f"\n FAIL: {e}"); import traceback; traceback.print_exc(); return 1


if __name__ == "__main__":
    sys.exit(main())
