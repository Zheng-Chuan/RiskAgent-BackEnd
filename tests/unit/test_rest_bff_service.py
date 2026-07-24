from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SRC_ROOT = _PROJECT_ROOT / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))


@pytest.mark.asyncio
async def test_submit_task_exposes_runtime_and_final_state(monkeypatch: pytest.MonkeyPatch) -> None:
    from riskmonitor_multiagent.services.rest_bff_service import RestBffService
    from riskmonitor_multiagent.services.runtime_task_store import RuntimeTaskStore

    runtime_store = RuntimeTaskStore()
    release_execution = asyncio.Event()

    async def fake_run_proactive_workflow(*, task):
        await release_execution.wait()
        return {
            "status": "completed",
            "run_id": task["task_id"],
            "final_output": {"summary": "任务已经完成"},
            "task_graph_execution": {
                "trace": [
                    {
                        "step_id": "step_1",
                        "kind": "delegate",
                        "target_agent": "system_engineer",
                        "status": "completed",
                        "started_at_ms": 100,
                        "finished_at_ms": 200,
                    }
                ]
            },
            "errors": [],
        }

    monkeypatch.setattr(
        "riskmonitor_multiagent.services.rest_bff_service.get_runtime_task_store",
        lambda: runtime_store,
    )
    monkeypatch.setattr(
        "riskmonitor_multiagent.services.rest_bff_service.run_proactive_workflow",
        fake_run_proactive_workflow,
    )

    service = RestBffService()
    created = await service.submit_task(description="查询所有 desk 头寸")
    assert created["status"] == "pending"

    await asyncio.sleep(0)
    running_detail = await service.get_task_detail(task_id=created["task_id"])
    assert running_detail["status"] == "running"
    assert running_detail["description"] == "查询所有 desk 头寸"

    release_execution.set()
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    completed_detail = await service.get_task_detail(task_id=created["task_id"])
    assert completed_detail["status"] == "completed"
    assert completed_detail["result"]["summary"] == "任务已经完成"
    assert completed_detail["steps"][0]["id"] == "step_1"
    assert completed_detail["steps"][0]["status"] == "completed"


@pytest.mark.asyncio
async def test_get_agents_snapshot_derives_working_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    from riskmonitor_multiagent.services.rest_bff_service import RestBffService
    from riskmonitor_multiagent.services.runtime_task_store import RuntimeTaskStore

    runtime_store = RuntimeTaskStore()
    await runtime_store.create_task(
        task_id="task_1",
        session_id="session_1",
        description="检查风险暴露",
    )
    await runtime_store.mark_running(task_id="task_1", run_id="task_1")
    await runtime_store.set_current_agent(task_id="task_1", agent_id="system_engineer")

    fake_workflow = SimpleNamespace(
        _intent_agent=SimpleNamespace(is_running=True),
        _orchestrator_agent=SimpleNamespace(is_running=True),
        _critic_agent=SimpleNamespace(is_running=True),
        _engineer_agent=SimpleNamespace(is_running=True),
        _analyst_agent=SimpleNamespace(is_running=True),
    )

    monkeypatch.setattr(
        "riskmonitor_multiagent.services.rest_bff_service.get_runtime_task_store",
        lambda: runtime_store,
    )
    monkeypatch.setattr(
        "riskmonitor_multiagent.services.rest_bff_service.get_proactive_workflow",
        lambda: fake_workflow,
    )

    service = RestBffService()
    snapshot = await service.get_agents_snapshot()
    agent_map = {item["id"]: item for item in snapshot["items"]}

    assert agent_map["system_engineer"]["status"] == "working"
    assert agent_map["system_engineer"]["currentTaskId"] == "task_1"
    assert agent_map["intent"]["status"] == "idle"
    assert agent_map["risk_analyst"]["status"] == "idle"
