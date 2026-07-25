import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SRC_ROOT = _PROJECT_ROOT / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

from riskagent_backend.services.runtime_task_store import RuntimeTaskStore


@pytest.mark.asyncio
async def test_sync_task_graph_populates_steps_from_planned_nodes():
    store = RuntimeTaskStore()
    await store.create_task(
        task_id="task-1",
        session_id="session-1",
        description="测试任务",
    )
    await store.mark_running(task_id="task-1", run_id="run-1")
    await store.sync_task_graph(
        task_id="task-1",
        task_graph={
            "plan_steps": [
                {
                    "kind": "delegate",
                    "step_id": "s1",
                    "reason": "先做系统分析",
                    "target_agent": "system_engineer",
                    "instruction": "输出系统结论",
                },
                {
                    "kind": "finalize",
                    "step_id": "s2",
                    "reason": "最后汇总",
                    "instruction": "输出结论",
                },
            ],
        },
    )

    task = await store.get_task(task_id="task-1")

    assert task is not None
    assert [step.get("id") for step in task.get("steps", [])] == ["s1", "s2"]
    assert [step.get("status") for step in task.get("steps", [])] == ["pending", "pending"]
    graph = task.get("graph") or {}
    nodes = graph.get("nodes") or []
    assert len(nodes) == 2
    assert nodes[0].get("id") == "s1"
    assert nodes[1].get("id") == "s2"
