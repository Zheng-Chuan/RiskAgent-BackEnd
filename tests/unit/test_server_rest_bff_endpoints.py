from __future__ import annotations

import sys
from pathlib import Path


_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SRC_ROOT = _PROJECT_ROOT / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))


def test_rest_bff_endpoints(monkeypatch) -> None:
    from starlette.testclient import TestClient

    from riskmonitor_multiagent import server
    from riskmonitor_multiagent.server import mcp

    class FakeRestBffService:
        async def submit_task(self, *, description: str) -> dict[str, object]:
            assert description == "查询所有 desk 头寸"
            return {
                "task_id": "task_123",
                "status": "pending",
                "created_at": 1234567890,
            }

        async def get_task_detail(self, *, task_id: str) -> dict[str, object]:
            assert task_id == "task_123"
            return {
                "id": "task_123",
                "title": "查询所有 desk 头寸",
                "description": "查询所有 desk 头寸",
                "status": "running",
                "steps": [
                    {
                        "id": "step_1",
                        "title": "delegate system_engineer",
                        "status": "running",
                    }
                ],
                "result": None,
                "error": None,
                "created_at": 1234567890,
                "updated_at": 1234567999,
            }

        async def get_agents_snapshot(self) -> dict[str, object]:
            return {
                "items": [
                    {
                        "id": "system_engineer",
                        "name": "ProactiveSystemEngineerAgent",
                        "role": "engineer",
                        "status": "working",
                        "currentTaskId": "task_123",
                        "capabilities": ["analyze", "monitor", "execute"],
                        "lastActiveAt": 1234567999,
                    }
                ],
                "updated_at": 1234567999,
            }

    monkeypatch.setattr(server, "get_rest_bff_service", lambda: FakeRestBffService())

    app = mcp.streamable_http_app()
    client = TestClient(app)

    resp = client.post("/api/tasks", json={"description": "查询所有 desk 头寸"})
    assert resp.status_code == 202
    assert resp.json()["task_id"] == "task_123"

    resp = client.get("/api/tasks/task_123")
    assert resp.status_code == 200
    assert resp.json()["status"] == "running"

    resp = client.get("/api/agents")
    assert resp.status_code == 200
    assert resp.json()["items"][0]["id"] == "system_engineer"


def test_rest_bff_create_task_validates_payload() -> None:
    from starlette.testclient import TestClient

    from riskmonitor_multiagent.server import mcp

    app = mcp.streamable_http_app()
    client = TestClient(app)

    resp = client.post("/api/tasks", json={})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "BAD_REQUEST"
