"""P0 常驻感知守护进程验收测试 (Checkpoint 16.1.1 + 16.1.2)."""

import asyncio
import sys
import os
import time

# 确保 src 在路径中
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from riskagent_backend.server import (
    start_proactive_monitors,
    stop_proactive_monitors,
    get_proactive_monitors,
)


async def test_p0_monitors_start_and_stop():
    """验收 16.1.1: 常驻协程能启动和停止."""
    print("=" * 60)
    print("P0 验收测试: 常驻感知守护进程")
    print("=" * 60)

    # 1. 启动前检查
    assert len(get_proactive_monitors()) == 0, "启动前应为空"
    print("[PASS] 启动前 proactive agents 列表为空")

    # 2. 启动 monitors
    await start_proactive_monitors()
    agents = get_proactive_monitors()
    assert len(agents) == 5, f"应启动 5 个 agents, 实际 {len(agents)}"
    print(f"[PASS] 成功启动 {len(agents)} 个 proactive background monitors")

    # 3. 检查每个 agent 的 monitor task 状态
    for agent in agents:
        assert agent._monitor_task is not None, f"{agent._name} 的 monitor task 应为 None"
        assert agent._is_running is True, f"{agent._name} 的 _is_running 应为 True"
        assert not agent._monitor_task.done(), f"{agent._name} 的 monitor task 不应已完成"
    print("[PASS] 所有 5 个 agents 的 monitor task 正在运行 (task.done() == False)")

    # 4. 等待几秒确认协程持续运行
    await asyncio.sleep(3)
    for agent in agents:
        assert not agent._monitor_task.done(), f"{agent._name} 的 monitor task 在 3 秒后仍应运行"
    print("[PASS] 3 秒后所有 monitor task 仍在运行 (心跳存活)")

    # 5. 重复启动应被忽略
    await start_proactive_monitors()
    assert len(get_proactive_monitors()) == 5, "重复启动不应增加 agents"
    print("[PASS] 重复调用 start_proactive_monitors() 被正确忽略")

    # 6. 停止 monitors
    await stop_proactive_monitors()
    assert len(get_proactive_monitors()) == 0, "停止后列表应为空"
    print("[PASS] stop_proactive_monitors() 成功停止所有 monitors")

    print("\n" + "=" * 60)
    print("P0 Checkpoint 16.1.1 验收: 全部通过 ✓")
    print("=" * 60)


async def test_p0_exception_self_healing():
    """验收 16.1.2: 异常自愈 - 注入异常后协程仍存活."""
    print("\n" + "=" * 60)
    print("P0 验收测试: 异常自愈 (Checkpoint 16.1.2)")
    print("=" * 60)

    from riskagent_backend.proactive_agents import ProactiveIntentAgent

    # 使用 ProactiveIntentAgent 但覆盖监控间隔为 1 秒，加速测试
    agent = ProactiveIntentAgent()
    agent._monitor_interval = 1  # 覆盖为 1 秒，加快测试节奏

    # 注入异常到 _perceive_environment
    original_perceive = agent._perceive_environment
    call_count = 0

    async def failing_perceive():
        nonlocal call_count
        call_count += 1
        if call_count <= 2:
            raise RuntimeError("Injected test error")
        # 第 3 次调用恢复正常

    agent._perceive_environment = failing_perceive

    # 启动 monitor
    await agent.start_background_monitor()
    assert agent._monitor_task is not None
    print("[PASS] Monitor task 已启动")

    # 等待异常发生和恢复
    await asyncio.sleep(8)  # 等待至少 2 次失败 + 1 次恢复

    # 验证协程仍在运行
    assert not agent._monitor_task.done(), "异常后 monitor task 应仍在运行"
    assert agent._is_running is True, "_is_running 应为 True"
    print("[PASS] 注入 2 次 RuntimeError 后, monitor task 仍在运行 (自愈成功)")

    # 验证 call_count >= 3 (至少恢复了)
    assert call_count >= 3, f"应至少调用 3 次, 实际 {call_count}"
    print(f"[PASS] _perceive_environment 被调用 {call_count} 次 (异常后继续执行)")

    # 停止
    await agent.stop_background_monitor()
    print("[PASS] Monitor 正常停止")

    print("\n" + "=" * 60)
    print("P0 Checkpoint 16.1.2 验收: 全部通过 ✓")
    print("=" * 60)


async def main():
    try:
        await test_p0_monitors_start_and_stop()
        await test_p0_exception_self_healing()
        print("\n P0 全部验收通过!")
        return 0
    except AssertionError as e:
        print(f"\n❌ 验收失败: {e}")
        return 1
    except Exception as e:
        print(f"\n❌ 测试异常: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
