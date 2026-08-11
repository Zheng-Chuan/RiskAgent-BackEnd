"""hitl_policy 单元测试: 验证 fail-safe 默认语义."""

from __future__ import annotations

import pytest

from riskagent_backend.orchestration.hitl_policy import hitl_auto_approve_enabled


def test_auto_approve_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """未设置环境变量时必须关闭自动审批 (fail-safe)."""
    monkeypatch.delenv("HITL_AUTO_APPROVE", raising=False)
    assert hitl_auto_approve_enabled() is False


@pytest.mark.parametrize("value", ["1", "true", "True", " TRUE ", "yes", "on"])
def test_auto_approve_explicit_enable(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("HITL_AUTO_APPROVE", value)
    assert hitl_auto_approve_enabled() is True


@pytest.mark.parametrize("value", ["0", "false", "False", "no", "off", "random", ""])
def test_auto_approve_other_values_stay_disabled(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("HITL_AUTO_APPROVE", value)
    assert hitl_auto_approve_enabled() is False
