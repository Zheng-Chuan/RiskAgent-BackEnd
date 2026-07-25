from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SRC_ROOT = _PROJECT_ROOT / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

from riskagent_backend.agents.base import BaseAgent
from riskagent_backend.llm.llm_client import LLMError


class _Governor:
    def allow(self, **kwargs):
        del kwargs
        return True, {}


@pytest.mark.asyncio
async def test_ask_json_raises_when_fallback_is_not_provided(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("riskagent_backend.agents.base.config.get_llm_api_key", lambda: "test-key")
    monkeypatch.setattr("riskagent_backend.agents.base.get_llm_cost_governor", lambda: _Governor())

    agent = BaseAgent(name="intent", system_prompt="system", client=MagicMock())

    async def _fake_call_with_retry(**kwargs):
        del kwargs
        raise LLMError(code="BAD_LLM_OUTPUT", message="response is not valid JSON")

    monkeypatch.setattr(agent, "_call_with_retry", _fake_call_with_retry)

    with pytest.raises(LLMError) as exc:
        await agent.ask_json(user_prompt="return json")

    assert exc.value.code == "BAD_LLM_OUTPUT"


@pytest.mark.asyncio
async def test_ask_json_uses_fallback_only_when_explicitly_provided(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("riskagent_backend.agents.base.config.get_llm_api_key", lambda: "test-key")
    monkeypatch.setattr("riskagent_backend.agents.base.get_llm_cost_governor", lambda: _Governor())

    agent = BaseAgent(name="intent", system_prompt="system", client=MagicMock())

    async def _fake_call_with_retry(**kwargs):
        del kwargs
        raise LLMError(code="BAD_LLM_OUTPUT", message="response is not valid JSON")

    monkeypatch.setattr(agent, "_call_with_retry", _fake_call_with_retry)

    result = await agent.ask_json(
        user_prompt="return json",
        fallback={"intent": "unknown"},
    )

    assert result.ok is True
    assert result.output == {"intent": "unknown"}
    assert result.meta["fallback_used"] is True
    assert result.meta["fallback_reason"] == "BAD_LLM_OUTPUT"
