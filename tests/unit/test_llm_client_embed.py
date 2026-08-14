"""RFC-005 需求二: LLMClient.embed() 方法单元测试.

测试场景:
1. 正常调用返回向量
2. 空文本输入抛出 INVALID_INPUT
3. 非 2xx 状态码抛出 UPSTREAM_BAD_STATUS
4. 响应非合法 JSON 抛出 UPSTREAM_BAD_RESPONSE
5. 响应缺少 data 字段抛出 UPSTREAM_BAD_RESPONSE
6. data[0] 缺少 embedding 字段抛出 UPSTREAM_BAD_RESPONSE
7. 超时重试后成功
8. ClientError 重试后成功
9. 超时 3 次后抛出 UPSTREAM_TIMEOUT
10. token 用量记录正确
11. 默认模型从配置读取
12. 自定义模型覆盖
13. DNS 补丁恢复
14. 成本追踪记录调用 record_token_usage
"""

from __future__ import annotations

import asyncio
import socket
import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest

from riskagent_backend.llm.llm_client import LLMError, LlmClient

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SRC_ROOT = _PROJECT_ROOT / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))


def _mock_response(
    *,
    status: int = 200,
    json_value: Any = None,
    json_exc: Exception | None = None,
    text: str = "",
):
    """构造 mock HTTP 响应."""
    response = MagicMock()
    response.status = status
    response.text = AsyncMock(return_value=text)
    if json_exc is None:
        response.json = AsyncMock(return_value=json_value)
    else:
        response.json = AsyncMock(side_effect=json_exc)
    response.__aenter__ = AsyncMock(return_value=response)
    response.__aexit__ = AsyncMock(return_value=None)
    return response


def _make_embedding_response(dim: int = 1536) -> dict[str, Any]:
    """构造一个标准 embedding API 响应."""
    vector = [0.01 * (i % 100) for i in range(dim)]
    return {
        "data": [{"embedding": vector}],
        "usage": {"prompt_tokens": 5, "total_tokens": 5},
    }


# ------------------------------------------------------------------ #
# 正常调用
# ------------------------------------------------------------------ #
@pytest.mark.asyncio
async def test_embed_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """正常调用返回向量, 维度正确."""
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_EMBEDDING_API_KEY", "test-key")
    monkeypatch.setenv("LLM_EMBEDDING_MODEL", "text-embedding-3-small")

    captured: dict[str, Any] = {}
    mock_resp = _mock_response(status=200, json_value=_make_embedding_response(1536))

    session = MagicMock()
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=None)

    def capture_post(url, **kwargs):
        captured["url"] = url
        captured["headers"] = kwargs.get("headers", {})
        captured["json"] = kwargs.get("json", {})
        return mock_resp

    session.post = capture_post

    client = LlmClient(http_client=session, base_url="https://api.example.com/v1")
    vec = await client.embed(text="hello world", agent_name="test_agent")

    assert isinstance(vec, list)
    assert len(vec) == 1536
    assert all(isinstance(x, float) for x in vec)
    assert captured["url"].endswith("/embeddings")
    assert captured["headers"].get("Authorization") == "Bearer test-key"
    assert captured["json"]["model"] == "text-embedding-3-small"
    assert captured["json"]["input"] == "hello world"


@pytest.mark.asyncio
async def test_embed_custom_model_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """自定义 model 参数覆盖默认配置."""
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_EMBEDDING_MODEL", "text-embedding-3-small")

    captured: dict[str, Any] = {}
    mock_resp = _mock_response(status=200, json_value=_make_embedding_response(128))

    session = MagicMock()
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=None)

    def capture_post(url, **kwargs):
        captured["json"] = kwargs.get("json", {})
        return mock_resp

    session.post = capture_post

    client = LlmClient(http_client=session, base_url="https://api.example.com/v1")
    vec = await client.embed(text="hi", model="custom-embed-model")

    assert len(vec) == 128
    assert captured["json"]["model"] == "custom-embed-model"


@pytest.mark.asyncio
async def test_embed_default_model_from_config(monkeypatch: pytest.MonkeyPatch) -> None:
    """未传 model 时从 config 读取默认值."""
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_EMBEDDING_MODEL", "BAAI/bge-m3")

    captured: dict[str, Any] = {}
    mock_resp = _mock_response(status=200, json_value=_make_embedding_response(8))

    session = MagicMock()
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=None)

    def capture_post(url, **kwargs):
        captured["json"] = kwargs.get("json", {})
        return mock_resp

    session.post = capture_post

    client = LlmClient(http_client=session, base_url="https://api.example.com/v1")
    await client.embed(text="hello")

    assert captured["json"]["model"] == "BAAI/bge-m3"


# ------------------------------------------------------------------ #
# 输入校验
# ------------------------------------------------------------------ #
@pytest.mark.asyncio
async def test_embed_rejects_empty_text(monkeypatch: pytest.MonkeyPatch) -> None:
    """空文本抛出 INVALID_INPUT."""
    monkeypatch.setenv("LLM_API_KEY", "test-key")

    session = MagicMock()
    client = LlmClient(http_client=session, base_url="https://api.example.com/v1")

    with pytest.raises(LLMError, match="text 不能为空"):
        await client.embed(text="")

    with pytest.raises(LLMError, match="text 不能为空"):
        await client.embed(text="   ")


# ------------------------------------------------------------------ #
# 非 2xx 状态码
# ------------------------------------------------------------------ #
@pytest.mark.asyncio
async def test_embed_non_2xx_raises_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """429 状态码重试 3 次后抛出 UPSTREAM_BAD_STATUS."""
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setattr("riskagent_backend.llm.llm_client.asyncio.sleep", AsyncMock())

    mock_resp = _mock_response(status=429, text="rate limited")
    session = MagicMock()
    session.post = MagicMock(return_value=mock_resp)

    client = LlmClient(http_client=session, base_url="https://api.example.com/v1")
    with pytest.raises(LLMError) as exc:
        await client.embed(text="hello")

    assert exc.value.code == "UPSTREAM_BAD_STATUS"
    assert exc.value.status_code == 429


@pytest.mark.asyncio
async def test_embed_5xx_retries_then_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    """500 状态码重试 3 次后抛出."""
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setattr("riskagent_backend.llm.llm_client.asyncio.sleep", AsyncMock())

    mock_resp = _mock_response(status=500, text="server error")
    session = MagicMock()
    session.post = MagicMock(return_value=mock_resp)

    client = LlmClient(http_client=session, base_url="https://api.example.com/v1")
    with pytest.raises(LLMError) as exc:
        await client.embed(text="hello")

    assert exc.value.code == "UPSTREAM_BAD_STATUS"
    assert exc.value.status_code == 500
    assert session.post.call_count == 3


# ------------------------------------------------------------------ #
# 响应格式错误
# ------------------------------------------------------------------ #
@pytest.mark.asyncio
async def test_embed_bad_json_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """响应非合法 JSON 抛出 UPSTREAM_BAD_RESPONSE."""
    monkeypatch.setenv("LLM_API_KEY", "test-key")

    mock_resp = _mock_response(status=200, json_exc=ValueError("bad json"))
    session = MagicMock()
    session.post = MagicMock(return_value=mock_resp)

    client = LlmClient(http_client=session, base_url="https://api.example.com/v1")
    with pytest.raises(LLMError) as exc:
        await client.embed(text="hello")

    assert exc.value.code == "UPSTREAM_BAD_RESPONSE"


@pytest.mark.asyncio
async def test_embed_non_dict_response_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """响应 JSON 不是对象抛出 UPSTREAM_BAD_RESPONSE."""
    monkeypatch.setenv("LLM_API_KEY", "test-key")

    mock_resp = _mock_response(status=200, json_value=["bad"])
    session = MagicMock()
    session.post = MagicMock(return_value=mock_resp)

    client = LlmClient(http_client=session, base_url="https://api.example.com/v1")
    with pytest.raises(LLMError, match="响应 JSON 不是对象"):
        await client.embed(text="hello")


@pytest.mark.asyncio
async def test_embed_missing_data_field_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """响应缺少 data 字段抛出 UPSTREAM_BAD_RESPONSE."""
    monkeypatch.setenv("LLM_API_KEY", "test-key")

    mock_resp = _mock_response(status=200, json_value={"usage": {}})
    session = MagicMock()
    session.post = MagicMock(return_value=mock_resp)

    client = LlmClient(http_client=session, base_url="https://api.example.com/v1")
    with pytest.raises(LLMError, match="缺少 data 字段"):
        await client.embed(text="hello")


@pytest.mark.asyncio
async def test_embed_empty_data_list_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """data 列表为空抛出 UPSTREAM_BAD_RESPONSE."""
    monkeypatch.setenv("LLM_API_KEY", "test-key")

    mock_resp = _mock_response(status=200, json_value={"data": []})
    session = MagicMock()
    session.post = MagicMock(return_value=mock_resp)

    client = LlmClient(http_client=session, base_url="https://api.example.com/v1")
    with pytest.raises(LLMError, match="缺少 data 字段"):
        await client.embed(text="hello")


@pytest.mark.asyncio
async def test_embed_missing_embedding_field_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """data[0] 缺少 embedding 字段抛出 UPSTREAM_BAD_RESPONSE."""
    monkeypatch.setenv("LLM_API_KEY", "test-key")

    mock_resp = _mock_response(status=200, json_value={"data": [{"object": "embedding", "index": 0}]})
    session = MagicMock()
    session.post = MagicMock(return_value=mock_resp)

    client = LlmClient(http_client=session, base_url="https://api.example.com/v1")
    with pytest.raises(LLMError, match="缺少 embedding 字段"):
        await client.embed(text="hello")


@pytest.mark.asyncio
async def test_embed_data_entry_not_dict_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """data[0] 不是对象抛出 UPSTREAM_BAD_RESPONSE."""
    monkeypatch.setenv("LLM_API_KEY", "test-key")

    mock_resp = _mock_response(status=200, json_value={"data": ["bad"]})
    session = MagicMock()
    session.post = MagicMock(return_value=mock_resp)

    client = LlmClient(http_client=session, base_url="https://api.example.com/v1")
    with pytest.raises(LLMError, match="data\\[0\\] 不是对象"):
        await client.embed(text="hello")


# ------------------------------------------------------------------ #
# 重试逻辑
# ------------------------------------------------------------------ #
@pytest.mark.asyncio
async def test_embed_retries_on_client_error_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    """ClientError 重试后成功."""
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_EMBEDDING_MODEL", "text-embedding-3-small")
    monkeypatch.setattr("riskagent_backend.llm.llm_client.asyncio.sleep", AsyncMock())

    mock_resp = _mock_response(status=200, json_value=_make_embedding_response(4))
    session = MagicMock()
    session.post = MagicMock(
        side_effect=[
            aiohttp.ClientError("network down"),
            mock_resp,
        ]
    )

    client = LlmClient(http_client=session, base_url="https://api.example.com/v1")
    vec = await client.embed(text="hello")

    assert len(vec) == 4
    assert session.post.call_count == 2


@pytest.mark.asyncio
async def test_embed_timeout_retries_then_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """超时 3 次后抛出 UPSTREAM_TIMEOUT."""
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setattr("riskagent_backend.llm.llm_client.asyncio.sleep", AsyncMock())

    session = MagicMock()
    session.post = MagicMock(side_effect=asyncio.TimeoutError())

    client = LlmClient(http_client=session, base_url="https://api.example.com/v1")
    with pytest.raises(LLMError) as exc:
        await client.embed(text="hello")

    assert exc.value.code == "UPSTREAM_TIMEOUT"
    assert session.post.call_count == 3


@pytest.mark.asyncio
async def test_embed_timeout_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    """超时一次后重试成功."""
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_EMBEDDING_MODEL", "text-embedding-3-small")
    monkeypatch.setattr("riskagent_backend.llm.llm_client.asyncio.sleep", AsyncMock())

    mock_resp = _mock_response(status=200, json_value=_make_embedding_response(2))
    session = MagicMock()
    session.post = MagicMock(
        side_effect=[
            asyncio.TimeoutError(),
            mock_resp,
        ]
    )

    client = LlmClient(http_client=session, base_url="https://api.example.com/v1")
    vec = await client.embed(text="hello")

    assert len(vec) == 2
    assert session.post.call_count == 2


# ------------------------------------------------------------------ #
# 成本追踪
# ------------------------------------------------------------------ #
@pytest.mark.asyncio
async def test_embed_records_token_usage(monkeypatch: pytest.MonkeyPatch) -> None:
    """embed() 调用后记录 token 用量, stage 默认为 'embedding'."""
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_EMBEDDING_MODEL", "text-embedding-3-small")

    embed_response = _make_embedding_response(4)
    embed_response["usage"] = {"prompt_tokens": 10, "total_tokens": 10}

    mock_resp = _mock_response(status=200, json_value=embed_response)
    session = MagicMock()
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=None)
    session.post = MagicMock(return_value=mock_resp)

    record_usage = MagicMock()
    monkeypatch.setattr("riskagent_backend.llm.token_tracker.record_token_usage", record_usage)

    client = LlmClient(http_client=session, base_url="https://api.example.com/v1")
    await client.embed(text="hello", agent_name="skill_proposer")

    assert record_usage.called
    call_kwargs = record_usage.call_args.kwargs
    assert call_kwargs["model"] == "text-embedding-3-small"
    assert call_kwargs["prompt_tokens"] == 10
    assert call_kwargs["completion_tokens"] == 0
    assert call_kwargs["total_tokens"] == 10
    assert call_kwargs["agent_name"] == "skill_proposer"
    assert call_kwargs["stage"] == "embedding"


@pytest.mark.asyncio
async def test_embed_custom_stage(monkeypatch: pytest.MonkeyPatch) -> None:
    """自定义 stage 参数传入 token 追踪."""
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_EMBEDDING_MODEL", "text-embedding-3-small")

    embed_response = _make_embedding_response(2)
    embed_response["usage"] = {"prompt_tokens": 3, "total_tokens": 3}

    mock_resp = _mock_response(status=200, json_value=embed_response)
    session = MagicMock()
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=None)
    session.post = MagicMock(return_value=mock_resp)

    record_usage = MagicMock()
    monkeypatch.setattr("riskagent_backend.llm.token_tracker.record_token_usage", record_usage)

    client = LlmClient(http_client=session, base_url="https://api.example.com/v1")
    await client.embed(text="hello", stage="skill_embedding")

    assert record_usage.called
    assert record_usage.call_args.kwargs["stage"] == "skill_embedding"


@pytest.mark.asyncio
async def test_embed_missing_usage_logs_warning(monkeypatch: pytest.MonkeyPatch) -> None:
    """响应缺少 usage 字段时记录 warning 但不抛异常."""
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_EMBEDDING_MODEL", "text-embedding-3-small")

    embed_response = _make_embedding_response(2)
    del embed_response["usage"]

    mock_resp = _mock_response(status=200, json_value=embed_response)
    session = MagicMock()
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=None)
    session.post = MagicMock(return_value=mock_resp)

    record_usage = MagicMock()
    monkeypatch.setattr("riskagent_backend.llm.token_tracker.record_token_usage", record_usage)

    client = LlmClient(http_client=session, base_url="https://api.example.com/v1")
    vec = await client.embed(text="hello")

    assert len(vec) == 2
    assert not record_usage.called


# ------------------------------------------------------------------ #
# DNS 补丁
# ------------------------------------------------------------------ #
@pytest.mark.asyncio
async def test_embed_dns_patch_restored(monkeypatch: pytest.MonkeyPatch) -> None:
    """DNS 补丁在调用后正确恢复."""
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_EMBEDDING_MODEL", "text-embedding-3-small")
    monkeypatch.setenv("LLM_RESOLVE_IP", "1.1.1.1")
    monkeypatch.setattr("riskagent_backend.llm.llm_client.asyncio.sleep", AsyncMock())

    mock_resp = _mock_response(status=200, json_value=_make_embedding_response(2))
    session = MagicMock()
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=None)
    session.post = MagicMock(return_value=mock_resp)

    original_getaddrinfo = socket.getaddrinfo
    client = LlmClient(http_client=session, base_url="https://api.example.com/v1")
    await client.embed(text="hello")

    assert socket.getaddrinfo is original_getaddrinfo


# ------------------------------------------------------------------ #
# 成本模型定价
# ------------------------------------------------------------------ #
def test_cost_model_embedding_pricing() -> None:
    """text-embedding-3-small 定价正确."""
    from riskagent_backend.llm.cost_model import get_pricing, calculate_call_cost

    pricing = get_pricing("text-embedding-3-small")
    assert pricing["prompt"] == 0.00002
    assert pricing["completion"] == 0.0

    # 10K prompt tokens -> 0.00002 * 10 = 0.0002
    cost = calculate_call_cost(10_000, 0, "text-embedding-3-small")
    assert abs(cost - 0.0002) < 1e-9


def test_cost_model_embedding_in_chain_cost() -> None:
    """embedding 调用链路成本计算正确."""
    from riskagent_backend.llm.cost_model import calculate_chain_cost

    records = [
        {
            "model": "text-embedding-3-small",
            "prompt_tokens": 5000,
            "completion_tokens": 0,
            "stage": "embedding",
        },
        {
            "model": "deepseek/deepseek-chat",
            "prompt_tokens": 1000,
            "completion_tokens": 500,
            "stage": "thought",
        },
    ]
    result = calculate_chain_cost(records)
    assert result["call_count"] == 2
    assert "embedding" in result["by_stage"]
    assert "thought" in result["by_stage"]
    # embedding: 0.00002 * 5 = 0.0001
    assert abs(result["by_stage"]["embedding"]["cost"] - 0.0001) < 1e-9


# ------------------------------------------------------------------ #
# 配置 getter
# ------------------------------------------------------------------ #
def test_config_get_llm_embedding_model_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """默认值为 BAAI/bge-m3 (硅基流动)."""
    monkeypatch.delenv("LLM_EMBEDDING_MODEL", raising=False)
    from riskagent_backend.config import get_llm_embedding_model

    assert get_llm_embedding_model() == "BAAI/bge-m3"


def test_config_get_llm_embedding_model_custom(monkeypatch: pytest.MonkeyPatch) -> None:
    """自定义环境变量覆盖默认值."""
    monkeypatch.setenv("LLM_EMBEDDING_MODEL", "custom-embed")
    from riskagent_backend.config import get_llm_embedding_model

    assert get_llm_embedding_model() == "custom-embed"
