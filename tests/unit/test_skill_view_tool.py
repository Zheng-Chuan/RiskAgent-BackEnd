"""skill_view 工具单测 (RFC-005 需求六)."""

import asyncio
import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SRC_ROOT = _PROJECT_ROOT / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))


def _make_skill(**kwargs) -> dict:
    """构造测试用 Skill dict."""
    base = {
        "name": "交易台风险排查",
        "summary": "从持仓查询到限额核对的完整风险排查工作流",
        "tags": ["risk", "trading"],
        "applicable_conditions": ["延迟异常", "告警触发"],
        "steps": [
            {"description": "查询持仓数据", "expected_outcome": "获取当前持仓"},
            {"description": "核对限额", "expected_outcome": "确认是否超限"},
        ],
        "failure_boundary": "禁止伪造数据",
        "confidence": 0.85,
    }
    base.update(kwargs)
    return base


# ==================== 1. 根据 skill_id 获取完整 Skill ====================


def test_skill_view_by_skill_id():
    """根据 skill_id 获取完整 Skill 内容."""
    from riskagent_backend.skills import SkillStore
    from riskagent_backend.tools.skill_view_tool import (
        set_skill_store,
        skill_view_handler,
    )

    store = SkillStore()
    created = asyncio.run(store.create(_make_skill(confidence=0.85)))
    skill_id = created["skill_id"]
    set_skill_store(store)

    result = skill_view_handler({"skill_id": skill_id})

    assert result["skill_id"] == skill_id
    assert result["name"] == "交易台风险排查"
    assert result["summary"] == "从持仓查询到限额核对的完整风险排查工作流"
    assert result["confidence"] == pytest.approx(0.85)
    assert len(result["steps"]) == 2
    assert result["steps"][0]["description"] == "查询持仓数据"
    assert result["applicable_conditions"] == ["延迟异常", "告警触发"]
    assert result["failure_boundary"] == "禁止伪造数据"
    assert result["tags"] == ["risk", "trading"]


# ==================== 2. 根据 skill_name 获取完整 Skill ====================


def test_skill_view_by_skill_name():
    """根据 skill_name 获取完整 Skill 内容."""
    from riskagent_backend.skills import SkillStore
    from riskagent_backend.tools.skill_view_tool import (
        set_skill_store,
        skill_view_handler,
    )

    store = SkillStore()
    asyncio.run(store.create(_make_skill(name="专属风险排查", confidence=0.9)))
    set_skill_store(store)

    result = skill_view_handler({"skill_name": "专属风险排查"})

    assert result["name"] == "专属风险排查"
    assert result["confidence"] == pytest.approx(0.9)
    assert len(result["steps"]) == 2


# ==================== 3. 优先使用 skill_id ====================


def test_skill_view_prefers_skill_id_over_name():
    """同时提供 skill_id 和 skill_name 时, 优先使用 skill_id."""
    from riskagent_backend.skills import SkillStore
    from riskagent_backend.tools.skill_view_tool import (
        set_skill_store,
        skill_view_handler,
    )

    store = SkillStore()
    skill_a = asyncio.run(store.create(_make_skill(name="技能A", confidence=0.8)))
    asyncio.run(store.create(_make_skill(name="技能B", confidence=0.9)))
    set_skill_store(store)

    result = skill_view_handler({
        "skill_id": skill_a["skill_id"],
        "skill_name": "技能B",
    })

    assert result["skill_id"] == skill_a["skill_id"]
    assert result["name"] == "技能A"


# ==================== 4. 缺少参数时抛 ValueError ====================


def test_skill_view_missing_params_raises():
    """skill_id 和 skill_name 都未提供时抛 ValueError."""
    from riskagent_backend.skills import SkillStore
    from riskagent_backend.tools.skill_view_tool import (
        set_skill_store,
        skill_view_handler,
    )

    store = SkillStore()
    set_skill_store(store)

    with pytest.raises(ValueError, match="skill_id or skill_name required"):
        skill_view_handler({})


def test_skill_view_empty_params_raises():
    """skill_id 和 skill_name 为空字符串时抛 ValueError."""
    from riskagent_backend.skills import SkillStore
    from riskagent_backend.tools.skill_view_tool import (
        set_skill_store,
        skill_view_handler,
    )

    store = SkillStore()
    set_skill_store(store)

    with pytest.raises(ValueError, match="skill_id or skill_name required"):
        skill_view_handler({"skill_id": "", "skill_name": "  "})


# ==================== 5. Skill 未找到时抛 KeyError ====================


def test_skill_view_not_found_by_id():
    """根据不存在的 skill_id 查询时抛 KeyError."""
    from riskagent_backend.skills import SkillStore
    from riskagent_backend.tools.skill_view_tool import (
        set_skill_store,
        skill_view_handler,
    )

    store = SkillStore()
    asyncio.run(store.create(_make_skill(confidence=0.9)))
    set_skill_store(store)

    with pytest.raises(KeyError, match="Skill not found"):
        skill_view_handler({"skill_id": "skill_nonexistent"})


def test_skill_view_not_found_by_name():
    """根据不存在的 skill_name 查询时抛 KeyError."""
    from riskagent_backend.skills import SkillStore
    from riskagent_backend.tools.skill_view_tool import (
        set_skill_store,
        skill_view_handler,
    )

    store = SkillStore()
    asyncio.run(store.create(_make_skill(confidence=0.9)))
    set_skill_store(store)

    with pytest.raises(KeyError, match="Skill not found"):
        skill_view_handler({"skill_name": "不存在的技能"})


# ==================== 6. 工具定义结构正确性 ====================


def test_skill_view_tool_definition():
    """检查工具定义结构正确."""
    from riskagent_backend.tools.skill_view_tool import SKILL_VIEW_TOOL_DEFINITION

    assert SKILL_VIEW_TOOL_DEFINITION["name"] == "skill_view"
    assert SKILL_VIEW_TOOL_DEFINITION["owner"] == "orchestrator"
    assert "description" in SKILL_VIEW_TOOL_DEFINITION
    assert "input_schema" in SKILL_VIEW_TOOL_DEFINITION
    props = SKILL_VIEW_TOOL_DEFINITION["input_schema"]["properties"]
    assert "skill_id" in props
    assert "skill_name" in props
    assert SKILL_VIEW_TOOL_DEFINITION["output"] == "完整 Skill 内容（JSON）"


# ==================== 7. 工具元数据注册正确性 ====================


def test_skill_view_registered_in_tool_registry():
    """检查 skill_view 在 tool_registry 中注册正确."""
    from riskagent_backend.orchestration.tool_registry import get_tool_meta

    meta = get_tool_meta("skill_view")
    assert meta is not None
    assert meta.action == "skill_view"
    assert meta.capability == "read_only"
    assert meta.owner == "orchestrator"
    assert meta.risk_level == "low"
    assert meta.allowed_targets == ("orchestrator",)


# ==================== 8. tool_executor 中 orchestrator 路由正确性 ====================


def test_tool_executor_skill_view_orchestrator():
    """通过 execute_agent_command 调用 skill_view, target_agent=orchestrator."""
    from riskagent_backend.orchestration.tool_executor import (
        execute_agent_command,
        new_agent_command,
    )
    from riskagent_backend.skills import SkillStore
    from riskagent_backend.tools.skill_view_tool import set_skill_store

    store = SkillStore()
    created = asyncio.run(store.create(_make_skill(confidence=0.85)))
    set_skill_store(store)

    cmd = new_agent_command(
        run_id="run-skill-view",
        command_id="cmd-skill-view",
        target_agent="orchestrator",
        action="skill_view",
        params={"skill_id": created["skill_id"]},
        timeout_ms=2000,
        expected_output_schema="tool_result.v1",
    )
    receipt = execute_agent_command(cmd)

    assert receipt["ok"] is True
    assert receipt["status"] == "completed"
    assert receipt["target_agent"] == "orchestrator"
    outputs = receipt["outputs"]
    result = outputs["result"]
    assert result["skill_id"] == created["skill_id"]
    assert result["name"] == "交易台风险排查"
    assert len(result["steps"]) == 2


def test_tool_executor_skill_view_unknown_action():
    """orchestrator 调用未注册工具时返回 unknown_action."""
    from riskagent_backend.orchestration.tool_executor import (
        execute_agent_command,
        new_agent_command,
    )

    cmd = new_agent_command(
        run_id="run-unknown",
        command_id="cmd-unknown",
        target_agent="orchestrator",
        action="nonexistent_tool",
        params={},
        timeout_ms=1000,
        expected_output_schema="tool_result.v1",
    )
    receipt = execute_agent_command(cmd)

    assert receipt["ok"] is False
    assert receipt["error"] == "unknown_action"


def test_tool_executor_skill_view_handler_missing():
    """orchestrator 调用已注册但无 handler 的工具时返回 handler_missing."""
    from riskagent_backend.orchestration.tool_executor import (
        _ORCHESTRATOR_ALLOWLIST,
        execute_agent_command,
        new_agent_command,
    )
    from riskagent_backend.orchestration.tool_registry import (
        ToolMeta,
        SideEffectPolicy,
        _TOOL_REGISTRY,
    )

    # 临时注册一个有 meta 但无 handler 的工具
    test_meta = ToolMeta(
        action="test_orphan",
        capability="read_only",
        owner="orchestrator",
        description="test orphan tool",
        risk_level="low",
        default_timeout_ms=1000,
        allowed_targets=("orchestrator",),
    )
    _TOOL_REGISTRY["test_orphan"] = test_meta
    try:
        cmd = new_agent_command(
            run_id="run-orphan",
            command_id="cmd-orphan",
            target_agent="orchestrator",
            action="test_orphan",
            params={},
            timeout_ms=1000,
            expected_output_schema="tool_result.v1",
        )
        receipt = execute_agent_command(cmd)

        assert receipt["ok"] is False
        assert receipt["error"] == "handler_missing"
    finally:
        _TOOL_REGISTRY.pop("test_orphan", None)
        _ORCHESTRATOR_ALLOWLIST.pop("test_orphan", None)
