from __future__ import annotations

import types

from riskmonitor_multiagent.perception.data_sources.redis_source import RedisDataSource


def test_redis_data_source_prefers_redis_url(monkeypatch):
    captured: dict[str, object] = {}

    def fake_from_url(url, **kwargs):
        captured["url"] = url
        captured["kwargs"] = kwargs
        return object()

    fake_redis_module = types.SimpleNamespace(from_url=fake_from_url, Redis=None)

    monkeypatch.setenv("REDIS_URL", "redis://redis:6379/0")
    monkeypatch.setitem(__import__("sys").modules, "redis", fake_redis_module)

    data_source = RedisDataSource()
    client = data_source._get_client()

    assert client is data_source._client
    assert captured["url"] == "redis://redis:6379/0"
    assert captured["kwargs"] == {
        "decode_responses": True,
        "socket_timeout": 5,
        "socket_connect_timeout": 5,
    }


def test_redis_data_source_falls_back_to_env_host_port_db(monkeypatch):
    captured: dict[str, object] = {}

    def fake_redis(**kwargs):
        captured.update(kwargs)
        return object()

    fake_redis_module = types.SimpleNamespace(from_url=None, Redis=fake_redis)

    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.setenv("REDIS_HOST", "redis")
    monkeypatch.setenv("REDIS_PORT", "6380")
    monkeypatch.setenv("REDIS_DB", "2")
    monkeypatch.setenv("REDIS_PASSWORD", "secret")
    monkeypatch.setitem(__import__("sys").modules, "redis", fake_redis_module)

    data_source = RedisDataSource()
    client = data_source._get_client()

    assert client is data_source._client
    assert captured == {
        "host": "redis",
        "port": 6380,
        "db": 2,
        "password": "secret",
        "decode_responses": True,
        "socket_timeout": 5,
        "socket_connect_timeout": 5,
    }
