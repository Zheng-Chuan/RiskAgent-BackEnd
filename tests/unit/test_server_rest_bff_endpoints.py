from __future__ import annotations

import sys
from pathlib import Path

import pytest


_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SRC_ROOT = _PROJECT_ROOT / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))


def test_rest_bff_endpoints(monkeypatch) -> None:
    from starlette.testclient import TestClient

    from riskagent_backend import server
    from riskagent_backend.server import mcp

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
                "graph": {
                    "task_id": "task_123",
                    "status": "running",
                    "schema_version": "task_graph.v1",
                    "nodes": [
                        {
                            "id": "step_1",
                            "label": "delegate system_engineer",
                            "kind": "delegate",
                            "status": "running",
                            "data": {"step_id": "step_1"},
                        }
                    ],
                    "edges": [],
                    "updated_at": 1234567999,
                },
                "result": None,
                "error": None,
                "created_at": 1234567890,
                "updated_at": 1234567999,
            }

        async def get_task_graph(self, *, task_id: str) -> dict[str, object]:
            assert task_id == "task_123"
            return {
                "task_id": "task_123",
                "status": "running",
                "schema_version": "task_graph.v1",
                "nodes": [
                    {
                        "id": "step_1",
                        "label": "delegate system_engineer",
                        "kind": "delegate",
                        "status": "running",
                        "data": {"step_id": "step_1"},
                    }
                ],
                "edges": [],
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

        async def get_memory_snapshot(self, *, limit: int) -> dict[str, object]:
            assert limit == 20
            return {
                "items": [
                    {
                        "id": "mem_1",
                        "taskId": "task_123",
                        "sessionId": "session_123",
                        "agentId": "system_engineer",
                        "scope": "shared",
                        "kind": "working_memory",
                        "memoryType": "episodic",
                        "changeType": "updated",
                        "summary": "已同步最近任务状态",
                        "details": ["来源 task_graph_execution"],
                        "tags": ["delegate"],
                        "confidence": 1.0,
                        "createdAt": 1234567999,
                    }
                ],
                "summary": {
                    "sharedCount": 1,
                    "privateCount": 0,
                    "agentCount": 1,
                },
                "updated_at": 1234567999,
            }

        async def get_task_memory(self, *, task_id: str, limit: int) -> dict[str, object]:
            assert task_id == "task_123"
            assert limit == 30
            return {
                "task_id": "task_123",
                "session_id": "session_123",
                "items": [
                    {
                        "id": "mem_task_1",
                        "taskId": "task_123",
                        "sessionId": "session_123",
                        "agentId": "risk_analyst",
                        "scope": "private",
                        "kind": "private_task_state",
                        "memoryType": "episodic",
                        "changeType": "updated",
                        "summary": "正在复核风险暴露",
                        "details": ["任务 task_123"],
                        "tags": ["review"],
                        "confidence": 1.0,
                        "createdAt": 1234568001,
                    }
                ],
                "summary": {
                    "sharedCount": 0,
                    "privateCount": 1,
                    "agentCount": 1,
                },
                "updated_at": 1234568001,
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
    assert resp.json()["graph"]["nodes"][0]["id"] == "step_1"

    resp = client.get("/api/tasks/task_123/graph")
    assert resp.status_code == 200
    assert resp.json()["nodes"][0]["label"] == "delegate system_engineer"

    resp = client.get("/api/agents")
    assert resp.status_code == 200
    assert resp.json()["items"][0]["id"] == "system_engineer"

    resp = client.get("/api/memory")
    assert resp.status_code == 200
    assert resp.json()["summary"]["sharedCount"] == 1

    resp = client.get("/api/tasks/task_123/memory")
    assert resp.status_code == 200
    assert resp.json()["task_id"] == "task_123"
    assert resp.json()["summary"]["privateCount"] == 1


def test_rest_bff_create_task_validates_payload() -> None:
    from starlette.testclient import TestClient

    from riskagent_backend.server import mcp

    app = mcp.streamable_http_app()
    client = TestClient(app)

    resp = client.post("/api/tasks", json={})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "BAD_REQUEST"


def test_rest_bff_memory_endpoints_validate_query_params(monkeypatch) -> None:
    from starlette.testclient import TestClient

    from riskagent_backend import server
    from riskagent_backend.server import mcp

    class FakeRestBffService:
        async def get_memory_snapshot(self, *, limit: int) -> dict[str, object]:
            assert limit == 20
            return {"items": [], "summary": {"sharedCount": 0, "privateCount": 0, "agentCount": 0}, "updated_at": 1}

        async def get_task_memory(self, *, task_id: str, limit: int) -> dict[str, object]:
            raise KeyError(task_id)

    monkeypatch.setattr(server, "get_rest_bff_service", lambda: FakeRestBffService())

    app = mcp.streamable_http_app()
    client = TestClient(app)

    resp = client.get("/api/memory?limit=abc")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "BAD_REQUEST"

    resp = client.get("/api/tasks/task_missing/memory")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"


def test_rest_bff_memory_endpoint_masks_sensitive_content(monkeypatch) -> None:
    from starlette.testclient import TestClient

    from riskagent_backend import server
    from riskagent_backend.server import mcp
    from riskagent_backend.services.rest_bff_service import RestBffService

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
            del agent_id, scope, session_id, run_id, limit
            return [
                {
                    "entry_id": "mem_secret_1",
                    "agent_id": "system_engineer",
                    "scope": "shared",
                    "kind": "working_memory",
                    "memory_type": "episodic",
                    "source": "task_graph_execution",
                    "tags": ["delegate", "sk-or-v1-sensitive-token-123456"],
                    "confidence": 1.0,
                    "ts_ms": 1234567999,
                    "run_id": "task_123",
                    "session_id": "session_123",
                    "content": {
                        "text": "调用 sk-or-v1-sensitive-token-123456 后完成分析",
                        "task_id": "task_123",
                    },
                }
            ]

        async def get_private_memory_state(
            self,
            *,
            agent_ids=None,
            session_id: str | None = None,
            run_id: str | None = None,
            limit: int = 5,
        ) -> dict[str, list[dict[str, object]]]:
            del agent_ids, session_id, run_id, limit
            return {}

    monkeypatch.setattr(
        "riskagent_backend.services.rest_bff_service.get_memory_store",
        lambda: FakeMemoryStore(),
    )
    monkeypatch.setattr(server, "get_rest_bff_service", lambda: RestBffService())

    app = mcp.streamable_http_app()
    client = TestClient(app)

    resp = client.get("/api/memory")
    assert resp.status_code == 200
    body = resp.json()
    assert body["items"][0]["summary"] == "调用 sk-*** 后完成分析"
    assert "sk-or-v1-sensitive-token-123456" not in str(body)


class _FakeStreamRequest:
    def __init__(
        self,
        *,
        query_params: dict[str, str] | None = None,
        disconnected_after: int = 1,
    ) -> None:
        self.query_params = query_params or {}
        self.path_params: dict[str, str] = {}
        self._disconnect_checks = 0
        self._disconnected_after = disconnected_after

    async def is_disconnected(self) -> bool:
        is_done = self._disconnect_checks >= self._disconnected_after
        self._disconnect_checks += 1
        return is_done


@pytest.mark.asyncio
async def test_rest_bff_stream_emits_agent_snapshot(monkeypatch) -> None:
    from riskagent_backend import server

    class FakeRestBffService:
        async def get_agents_snapshot(self) -> dict[str, object]:
            return {
                "items": [
                    {
                        "id": "system_engineer",
                        "name": "ProactiveSystemEngineerAgent",
                        "role": "engineer",
                        "status": "working",
                        "currentTaskId": "task_123",
                        "capabilities": ["analyze"],
                        "lastActiveAt": 1234567999,
                    }
                ],
                "updated_at": 1234567999,
            }

        async def get_memory_snapshot(self, *, limit: int) -> dict[str, object]:
            del limit
            return {"items": [], "summary": {"sharedCount": 0, "privateCount": 0, "agentCount": 0}, "updated_at": 1234567999}

        async def get_task_graph(self, *, task_id: str) -> dict[str, object]:
            assert task_id == "task_123"
            return {
                "task_id": "task_123",
                "status": "running",
                "schema_version": "task_graph.v1",
                "nodes": [
                    {
                        "id": "step_1",
                        "label": "delegate system_engineer",
                        "kind": "delegate",
                        "status": "running",
                        "data": {"step_id": "step_1"},
                    }
                ],
                "edges": [],
                "updated_at": 1234567999,
            }

    async def fake_sleep(_: float) -> None:
        return None

    monkeypatch.setattr(server, "get_rest_bff_service", lambda: FakeRestBffService())
    monkeypatch.setattr(server.asyncio, "sleep", fake_sleep)

    request = _FakeStreamRequest(query_params={"memory": "0", "task_id": "task_123"}, disconnected_after=2)
    response = await server.get_stream_endpoint(request)

    first_chunk = await response.body_iterator.__anext__()
    second_chunk = await response.body_iterator.__anext__()
    await response.body_iterator.aclose()

    assert response.media_type == "text/event-stream"
    assert first_chunk == b"retry: 1500\n\n"
    assert b"event: agent_snapshot" in second_chunk
    assert b'"type": "agent_snapshot"' in second_chunk


@pytest.mark.asyncio
async def test_rest_bff_stream_deduplicates_same_snapshot(monkeypatch) -> None:
    from riskagent_backend import server

    class FakeRestBffService:
        async def get_agents_snapshot(self) -> dict[str, object]:
            return {
                "items": [
                    {
                        "id": "system_engineer",
                        "name": "ProactiveSystemEngineerAgent",
                        "role": "engineer",
                        "status": "working",
                        "currentTaskId": "task_123",
                        "capabilities": ["analyze"],
                        "lastActiveAt": 1234567999,
                    }
                ],
                "updated_at": 1234567999,
            }

    async def fake_sleep(_: float) -> None:
        return None

    monkeypatch.setattr(server, "get_rest_bff_service", lambda: FakeRestBffService())
    monkeypatch.setattr(server.asyncio, "sleep", fake_sleep)

    request = _FakeStreamRequest(query_params={"memory": "0"}, disconnected_after=2)
    response = await server.get_stream_endpoint(request)

    retry_chunk = await response.body_iterator.__anext__()
    event_chunk = await response.body_iterator.__anext__()

    with pytest.raises(StopAsyncIteration):
        await response.body_iterator.__anext__()

    assert retry_chunk == b"retry: 1500\n\n"
    assert b"event: agent_snapshot" in event_chunk


@pytest.mark.asyncio
async def test_rest_bff_stream_returns_task_not_found_event(monkeypatch) -> None:
    from riskagent_backend import server

    class FakeRestBffService:
        async def get_task_memory(self, *, task_id: str, limit: int) -> dict[str, object]:
            del limit
            raise KeyError(task_id)

    async def fake_sleep(_: float) -> None:
        return None

    monkeypatch.setattr(server, "get_rest_bff_service", lambda: FakeRestBffService())
    monkeypatch.setattr(server.asyncio, "sleep", fake_sleep)

    request = _FakeStreamRequest(
        query_params={"agents": "0", "memory": "1", "task_id": "task_missing"},
        disconnected_after=1,
    )
    response = await server.get_stream_endpoint(request)

    retry_chunk = await response.body_iterator.__anext__()
    error_chunk = await response.body_iterator.__anext__()

    with pytest.raises(StopAsyncIteration):
        await response.body_iterator.__anext__()

    assert retry_chunk == b"retry: 1500\n\n"
    assert b"event: error" in error_chunk
    assert b'"code": "NOT_FOUND"' in error_chunk
