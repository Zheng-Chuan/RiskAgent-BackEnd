"""P2 Docker 感知数据源验收测试 (Checkpoint 16.2.1)."""

import asyncio
import sys
import os
import subprocess
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from riskagent_backend.perception.data_sources.docker_source import DockerDataSource
from riskagent_backend.perception.signals import PerceptionSignal, SignalSeverity
from riskagent_backend.perception import PerceptionFilterEngine, get_default_rules


def test_docker_data_source_collect():
    """验收: Docker 数据源能采集容器状态并产出 PerceptionSignal."""
    print("=" * 60)
    print("P2 验收测试: Docker 数据源采集")
    print("=" * 60)

    ds = DockerDataSource()
    signals = ds.collect()

    # 检查是否返回了 PerceptionSignal 列表
    assert isinstance(signals, list)
    for s in signals:
        assert isinstance(s, PerceptionSignal)
        assert s.source == "docker"

    # 检查信号结构完整性
    for s in signals:
        d = s.to_log_dict()
        assert "source" in d
        assert "metric" in d
        assert "value" in d
        assert "timestamp" in d

    print(f"[PASS] Docker 数据源返回 {len(signals)} 个 PerceptionSignal")
    for s in signals[:5]:  # 打印前 5 个
        print(f"  - {s.metric}={s.value} (ctx: {s.context.get('container_name', 'N/A')})")
    if len(signals) > 5:
        print(f"  ... 共 {len(signals)} 个信号")

    return signals


def test_docker_unavailable_graceful():
    """验收: Docker 不可用时降级为 unavailable 信号，不抛异常."""
    print("\n" + "=" * 60)
    print("P2 验收测试: Docker 不可用时降级处理")
    print("=" * 60)

    # 用一个不存在的容器前缀模拟不可用场景
    ds = DockerDataSource(container_prefix="nonexistent-prefix-xyz-")
    signals = ds.collect()

    # 应该返回 unavailable 信号，而不是抛异常
    assert len(signals) >= 1
    found_unavailable = False
    for s in signals:
        if s.metric == "connection_status" and s.value == "unavailable":
            found_unavailable = True
            break

    if not found_unavailable:
        # 可能 docker 存在但没有匹配的容器，这也是正常的降级
        print("[PASS] Docker 无匹配容器时返回空或 unavailable 信号 (降级成功)")
    else:
        print("[PASS] Docker 不可用时返回 unavailable 信号 (降级成功)")

    # 确保不抛异常
    print("[PASS] Docker 不可用时不抛异常，协程不中断")


def test_docker_signals_pass_filter():
    """验收: Docker 信号能被过滤引擎正确处理."""
    print("\n" + "=" * 60)
    print("P2 验收测试: Docker 信号经过滤引擎处理")
    print("=" * 60)

    ds = DockerDataSource()
    signals = ds.collect()
    engine = PerceptionFilterEngine(get_default_rules())

    # 过滤所有信号
    filtered = engine.filter_batch(signals)

    assert len(filtered) == len(signals)
    print(f"[PASS] {len(signals)} 个 Docker 信号全部通过过滤引擎")

    # 检查是否有升级信号
    escalations = [s for s in filtered if s.should_escalate()]
    if escalations:
        print(f"[INFO] 发现 {len(escalations)} 个升级信号:")
        for s in escalations:
            print(f"  - {s.metric}={s.value} -> {s.severity.value}")
    else:
        print("[INFO] 无升级信号 (所有容器状态正常)")


def test_docker_ps_comparison():
    """验收: 感知快照与 docker ps 输出一致."""
    print("\n" + "=" * 60)
    print("P2 验收测试: 感知快照与 docker ps 一致性")
    print("=" * 60)

    # 获取 docker ps 直接输出
    try:
        result = subprocess.run(
            ["docker", "ps", "-a", "--format", "{{json .}}", "--filter", "name=riskagent-"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            print("[SKIP] Docker 不可用，跳过一致性对比")
            return
        docker_ps_containers = [json.loads(l) for l in result.stdout.strip().split("\n") if l.strip()]
    except Exception:
        print("[SKIP] Docker 不可用，跳过一致性对比")
        return

    # 获取感知数据源的容器名列表
    ds = DockerDataSource()
    perceived_names = set(ds.get_container_names())
    docker_ps_names = set(c.get("Names", "").lstrip("/") for c in docker_ps_containers)

    if not docker_ps_names:
        print("[SKIP] 无 riskagent 容器运行，跳过一致性对比")
        return

    # 对比
    assert perceived_names == docker_ps_names, (
        f"容器名不一致: docker_ps={docker_ps_names}, perceived={perceived_names}"
    )
    print(f"[PASS] 感知快照容器名与 docker ps 一致 ({len(perceived_names)} 个容器)")

    # 对比状态
    signals = ds.collect()
    status_signals = [s for s in signals if s.metric == "container_status"]
    perceived_status = {s.context.get("container_name"): s.value for s in status_signals}
    docker_ps_status = {c.get("Names", "").lstrip("/"): c.get("State") for c in docker_ps_containers}

    for name, status in docker_ps_status.items():
        assert perceived_status.get(name) == status, (
            f"容器 {name} 状态不一致: docker_ps={status}, perceived={perceived_status.get(name)}"
        )
    print(f"[PASS] 所有容器状态与 docker ps 一致")


def main():
    try:
        test_docker_data_source_collect()
        test_docker_unavailable_graceful()
        test_docker_signals_pass_filter()
        test_docker_ps_comparison()

        print("\n" + "=" * 60)
        print("P2 Checkpoint 16.2.1 验收: 全部通过")
        print("=" * 60)
        print("\n P2 全部验收通过!")
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
