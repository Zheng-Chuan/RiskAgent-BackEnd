"""P3 Redis 感知数据源验收测试 (Checkpoint 16.2.2)."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from riskmonitor_multiagent.perception.data_sources.redis_source import RedisDataSource
from riskmonitor_multiagent.perception.signals import PerceptionSignal
from riskmonitor_multiagent.perception import PerceptionFilterEngine, get_default_rules


def test_redis_data_source_collect():
    """验收: Redis 数据源能采集指标并产出 PerceptionSignal."""
    print("=" * 60)
    print("P3 验收测试: Redis 数据源采集")
    print("=" * 60)

    ds = RedisDataSource(host="localhost", port=6379)
    signals = ds.collect()

    assert isinstance(signals, list)
    for s in signals:
        assert isinstance(s, PerceptionSignal)
        assert s.source == "redis"

    print(f"[PASS] Redis 数据源返回 {len(signals)} 个 PerceptionSignal")
    for s in signals:
        print(f"  - {s.metric}={s.value}")

    return signals


def test_redis_unavailable_graceful():
    """验收: Redis 不可用时降级为 unavailable 信号，不抛异常."""
    print("\n" + "=" * 60)
    print("P3 验收测试: Redis 不可用时降级处理")
    print("=" * 60)

    # 连接一个不存在的 Redis
    ds = RedisDataSource(host="localhost", port=16379)
    signals = ds.collect()

    assert len(signals) >= 1
    found_unavailable = any(
        s.metric == "connection_status" and s.value == "unavailable"
        for s in signals
    )
    assert found_unavailable, "应返回 unavailable 信号"
    print("[PASS] Redis 不可用时返回 unavailable 信号 (降级成功)")
    print("[PASS] Redis 不可用时不抛异常，协程不中断")


def test_redis_signals_pass_filter():
    """验收: Redis 信号能被过滤引擎正确处理."""
    print("\n" + "=" * 60)
    print("P3 验收测试: Redis 信号经过滤引擎处理")
    print("=" * 60)

    ds = RedisDataSource()
    signals = ds.collect()
    engine = PerceptionFilterEngine(get_default_rules())

    filtered = engine.filter_batch(signals)
    assert len(filtered) == len(signals)
    print(f"[PASS] {len(signals)} 个 Redis 信号全部通过过滤引擎")

    escalations = [s for s in filtered if s.should_escalate()]
    if escalations:
        print(f"[INFO] 发现 {len(escalations)} 个升级信号:")
        for s in escalations:
            print(f"  - {s.metric}={s.value} -> {s.severity.value}")
    else:
        print("[INFO] 无升级信号 (Redis 状态正常)")


def test_redis_info_comparison():
    """验收: 感知快照与 redis-cli INFO 一致."""
    print("\n" + "=" * 60)
    print("P3 验收测试: 感知快照与 redis-cli INFO 一致性")
    print("=" * 60)

    try:
        import redis
        client = redis.Redis(host="localhost", port=6379, socket_timeout=5)
        redis_info = client.info()
    except Exception:
        print("[SKIP] Redis 不可用，跳过一致性对比")
        return

    ds = RedisDataSource()
    signals = ds.collect()

    # 检查 connection_status
    status_signal = next((s for s in signals if s.metric == "connection_status"), None)
    if status_signal:
        assert status_signal.value == "available"
        print("[PASS] Redis 连接状态为 available")

    # 检查内存使用率
    mem_signal = next((s for s in signals if s.metric == "memory_usage_percent"), None)
    if mem_signal:
        used = redis_info.get("used_memory", 0)
        maxm = redis_info.get("maxmemory", 0)
        if maxm > 0:
            expected = round((used / maxm) * 100, 2)
        else:
            expected = 0.0
        assert abs(mem_signal.value - expected) < 1.0, (
            f"内存使用率偏差过大: perceived={mem_signal.value}, expected={expected}"
        )
        print(f"[PASS] 内存使用率一致: {mem_signal.value}%")

    # 检查键空间命中率
    hit_signal = next((s for s in signals if s.metric == "keyspace_hit_rate"), None)
    if hit_signal:
        hits = redis_info.get("keyspace_hits", 0)
        misses = redis_info.get("keyspace_misses", 0)
        total = hits + misses
        expected = round(hits / total, 4) if total > 0 else 1.0
        assert abs(hit_signal.value - expected) < 0.01, (
            f"命中率偏差过大: perceived={hit_signal.value}, expected={expected}"
        )
        print(f"[PASS] 键空间命中率一致: {hit_signal.value}")

    # 检查连接数
    clients_signal = next((s for s in signals if s.metric == "connected_clients"), None)
    if clients_signal:
        assert clients_signal.value == redis_info.get("connected_clients", 0)
        print(f"[PASS] 连接客户端数一致: {clients_signal.value}")


def main():
    try:
        test_redis_data_source_collect()
        test_redis_unavailable_graceful()
        test_redis_signals_pass_filter()
        test_redis_info_comparison()

        print("\n" + "=" * 60)
        print("P3 Checkpoint 16.2.2 验收: 全部通过")
        print("=" * 60)
        print("\n P3 全部验收通过!")
        return 0
    except AssertionError as e:
        print(f"\n FAIL 验收失败: {e}")
        import traceback
        traceback.print_exc()
        return 1
    except Exception as e:
        print(f"\n ERROR 测试异常: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
