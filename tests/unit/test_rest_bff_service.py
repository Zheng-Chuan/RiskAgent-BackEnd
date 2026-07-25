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


@pytest.mark.asyncio
async def test_get_memory_snapshot_returns_structured_sanitized_items(monkeypatch: pytest.MonkeyPatch) -> None:
    from riskmonitor_multiagent.services.rest_bff_service import RestBffService

    class FakeMemoryStore:
        async def list_recent(
            self,
            *,
            agent_id: str,
            scope: str,
            session_id: str | None = None,
            run_id: str | None = None,
            limit: int = 50,
        ) -> list[dict[str, object]]:
            assert agent_id == "orchestrator"
            assert scope == "shared"
            assert session_id is None
            assert run_id is None
            assert limit == 5
            return [
                {
                    "entry_id": "mem_shared_1",
                    "agent_id": "system_engineer",
                    "scope": "shared",
                    "kind": "working_memory",
                    "memory_type": "episodic",
                    "source": "task_graph_execution",
                    "tags": ["delegate", "sk-secret-123456789012"],
                    "confidence": 0.956,
                    "ts_ms": 300,
                    "run_id": "run_1",
                    "session_id": "session_1",
                    "content": {
                        "text": "调用 sk-secret-123456789012 后完成分析",
                        "task_id": "run_1",
                        "current_progress": "已拿到结果",
                        "next_intended_action": "生成报告",
                    },
                }
            ]

        async def get_private_memory_state(
            self,
            *,
            agent_ids: tuple[str, ...] | list[str] | None = None,
            session_id: str | None = None,
            run_id: str | None = None,
            limit: int = 5,
        ) -> dict[str, list[dict[str, object]]]:
            assert session_id is None
            assert run_id is None
            assert limit == 5
            assert agent_ids is None or len(agent_ids) > 0
            return {
                "risk_analyst": [
                    {
                        "entry_id": "mem_private_1",
                        "agent_id": "risk_analyst",
                        "scope": "private",
                        "kind": "private_task_state",
                        "memory_type": "episodic",
                        "source": "orchestrator_plan",
                        "tags": ["plan"],
                        "confidence": 1.0,
                        "ts_ms": 320,
                        "run_id": "run_1",
                        "session_id": "session_1",
                        "content": {
                            "task_id": "run_1",
                            "current_progress": "正在复核暴露",
                            "next_intended_action": "继续聚合结果",
                        },
                    }
                ]
            }

    monkeypatch.setattr(
        "riskmonitor_multiagent.services.rest_bff_service.get_memory_store",
        lambda: FakeMemoryStore(),
    )

    service = RestBffService()
    snapshot = await service.get_memory_snapshot(limit=5)

    assert snapshot["summary"] == {
        "sharedCount": 1,
        "privateCount": 1,
        "agentCount": 2,
    }
    assert snapshot["updated_at"] == 320
    assert [item["id"] for item in snapshot["items"]] == ["mem_private_1", "mem_shared_1"]

    shared_item = snapshot["items"][1]
    assert shared_item["summary"] == "调用 sk-*** 后完成分析"
    assert shared_item["details"] == [
        "来源 task_graph_execution",
        "任务 run_1",
        "已拿到结果",
        "下一步 生成报告",
    ]

    private_item = snapshot["items"][0]
    assert private_item["scope"] == "private"
    assert private_item["changeType"] == "updated"
    assert private_item["summary"] == "正在复核暴露. 下一步 继续聚合结果"


@pytest.mark.asyncio
async def test_get_task_memory_raises_when_task_scope_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    from riskmonitor_multiagent.services.rest_bff_service import RestBffService
    from riskmonitor_multiagent.services.runtime_task_store import RuntimeTaskStore

    runtime_store = RuntimeTaskStore()

    monkeypatch.setattr(
        "riskmonitor_multiagent.services.rest_bff_service.get_runtime_task_store",
        lambda: runtime_store,
    )
    monkeypatch.setattr(
        "riskmonitor_multiagent.services.rest_bff_service.get_memory_store",
        lambda: None,
    )

    service = RestBffService()

    with pytest.raises(KeyError):
        await service.get_task_memory(task_id="missing_task")
