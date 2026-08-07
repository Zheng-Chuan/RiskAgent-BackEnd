"""SkillInjector 单测."""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SRC_ROOT = _PROJECT_ROOT / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))


# ==================== 测试数据构造 ====================


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
    }
    base.update(kwargs)
    return base


def _make_task(**kwargs) -> dict:
    """构造测试用 task."""
    base = {
        "task_id": "task-001",
        "intent": "query_positions",
        "content": {
            "category": "risk",
            "description": "查询交易台持仓并核对限额",
        },
    }
    base.update(kwargs)
    return base


# ==================== 1. skill_on 时检索到匹配 Skill ====================


@pytest.mark.asyncio
async def test_skill_on_retrieves_matching_skills():
    """skill_enabled=True 时检索到匹配 Skill, 返回非空 skills 列表."""
    from riskagent_backend.skills import SkillInjector, SkillStore

    store = SkillStore()
    await store.create(
        _make_skill(
            name="交易台风险排查",
            applicable_conditions=["延迟异常", "告警触发"],
            steps=[
                {"description": "查询持仓数据", "expected_outcome": "获取持仓"},
            ],
            confidence=0.85,
        )
    )

    injector = SkillInjector(store, min_confidence=0.3, max_skills=3)
    result = await injector.retrieve_applicable_skills(
        task=_make_task(),
        intent="query_positions",
        skill_enabled=True,
    )

    assert result["skill_enabled"] is True
    assert result["skill_count"] >= 1
    assert len(result["skills"]) >= 1
    assert result["skills"][0]["name"] == "交易台风险排查"


# ==================== 2. skill_off 时无 Skill 注入 ====================


@pytest.mark.asyncio
async def test_skill_off_no_injection():
    """skill_enabled=False 时 skills 列表为空."""
    from riskagent_backend.skills import SkillInjector, SkillStore

    store = SkillStore()
    await store.create(_make_skill(confidence=0.9))

    injector = SkillInjector(store)
    result = await injector.retrieve_applicable_skills(
        task=_make_task(),
        skill_enabled=False,
    )

    assert result["skill_enabled"] is False
    assert result["skills"] == []
    assert result["skill_count"] == 0


# ==================== 3. 低置信度 Skill 不参与注入 ====================


@pytest.mark.asyncio
async def test_low_confidence_filtered():
    """confidence < min_confidence 的 Skill 被过滤."""
    from riskagent_backend.skills import SkillInjector, SkillStore

    store = SkillStore()
    # 创建低置信度 Skill (低于默认 min_confidence=0.3)
    await store.create(_make_skill(name="低置信度技能", confidence=0.2))
    # 创建高置信度 Skill
    await store.create(_make_skill(name="高置信度技能", confidence=0.9))

    injector = SkillInjector(store, min_confidence=0.5, max_skills=5)
    result = await injector.retrieve_applicable_skills(
        task=_make_task(),
        skill_enabled=True,
    )

    names = [s["name"] for s in result["skills"]]
    assert "高置信度技能" in names
    assert "低置信度技能" not in names


# ==================== 4. deprecated/archived Skill 不参与注入 ====================


@pytest.mark.asyncio
async def test_non_active_status_filtered():
    """status != 'active' 的 Skill 不参与注入."""
    from riskagent_backend.skills import SkillInjector, SkillStore

    store = SkillStore()
    await store.create(_make_skill(name="活跃技能", status="active", confidence=0.9))
    await store.create(_make_skill(name="废弃技能", status="deprecated", confidence=0.9))
    await store.create(_make_skill(name="归档技能", status="archived", confidence=0.9))

    injector = SkillInjector(store, min_confidence=0.0, max_skills=10)
    result = await injector.retrieve_applicable_skills(
        task=_make_task(),
        skill_enabled=True,
    )

    names = [s["name"] for s in result["skills"]]
    assert "活跃技能" in names
    assert "废弃技能" not in names
    assert "归档技能" not in names


# ==================== 5. max_skills 限制 ====================


@pytest.mark.asyncio
async def test_max_skills_limit():
    """创建 5 个 Skill, 只返回 max_skills 个."""
    from riskagent_backend.skills import SkillInjector, SkillStore

    store = SkillStore()
    for i in range(5):
        await store.create(
            _make_skill(
                name=f"交易台风险排查{i}",
                confidence=0.9,
            )
        )

    injector = SkillInjector(store, min_confidence=0.3, max_skills=2)
    result = await injector.retrieve_applicable_skills(
        task=_make_task(),
        skill_enabled=True,
    )

    assert result["skill_count"] <= 2
    assert len(result["skills"]) <= 2


# ==================== 6. 空查询安全处理 ====================


@pytest.mark.asyncio
async def test_empty_query_safe_handling():
    """无匹配 Skill 时返回空列表."""
    from riskagent_backend.skills import SkillInjector, SkillStore

    store = SkillStore()
    # 不创建任何 Skill

    injector = SkillInjector(store)
    result = await injector.retrieve_applicable_skills(
        task=_make_task(),
        skill_enabled=True,
    )

    assert result["skill_enabled"] is True
    assert result["skills"] == []
    assert result["skill_count"] == 0


@pytest.mark.asyncio
async def test_empty_task_returns_empty():
    """task 无可提取关键词时安全返回空列表."""
    from riskagent_backend.skills import SkillInjector, SkillStore

    store = SkillStore()
    await store.create(_make_skill(confidence=0.9))

    injector = SkillInjector(store)
    result = await injector.retrieve_applicable_skills(
        task={},
        skill_enabled=True,
    )

    assert result["skill_enabled"] is True
    assert result["skills"] == []
    assert result["skill_count"] == 0
    assert "No query keywords" in result["injection_summary"]


# ==================== 7. 注入结构正确性 ====================


@pytest.mark.asyncio
async def test_injection_structure_correctness():
    """检查返回结构含 skill_id, name, steps, applicable_conditions, failure_boundary, confidence."""
    from riskagent_backend.skills import SkillInjector, SkillStore

    store = SkillStore()
    await store.create(
        _make_skill(
            name="结构验证技能",
            applicable_conditions=["条件A", "条件B"],
            steps=[
                {"description": "步骤1", "expected_outcome": "结果1"},
                {"description": "步骤2", "expected_outcome": "结果2"},
            ],
            failure_boundary="边界条件X",
            confidence=0.75,
        )
    )

    injector = SkillInjector(store, min_confidence=0.3, max_skills=3)
    result = await injector.retrieve_applicable_skills(
        task=_make_task(),
        skill_enabled=True,
        summary_only=False,
    )

    assert result["skill_count"] >= 1
    item = result["skills"][0]

    # 必须包含所有注入字段
    assert "skill_id" in item
    assert item["skill_id"].startswith("skill_")
    assert item["name"] == "结构验证技能"
    assert item["applicable_conditions"] == ["条件A", "条件B"]
    assert len(item["steps"]) == 2
    assert item["steps"][0]["description"] == "步骤1"
    assert item["steps"][0]["expected_outcome"] == "结果1"
    assert item["failure_boundary"] == "边界条件X"
    assert item["confidence"] == pytest.approx(0.75)


# ==================== 8. injection_summary 生成 ====================


@pytest.mark.asyncio
async def test_injection_summary_with_skills():
    """有匹配 Skill 时 injection_summary 包含正确数量."""
    from riskagent_backend.skills import SkillInjector, SkillStore

    store = SkillStore()
    await store.create(_make_skill(name="技能A", confidence=0.9))
    await store.create(_make_skill(name="技能B", confidence=0.9))

    injector = SkillInjector(store, min_confidence=0.3, max_skills=5)
    result = await injector.retrieve_applicable_skills(
        task=_make_task(),
        skill_enabled=True,
    )

    count = result["skill_count"]
    assert "injection_summary" in result
    assert str(count) in result["injection_summary"]
    assert "skill" in result["injection_summary"].lower()


@pytest.mark.asyncio
async def test_injection_summary_no_skills():
    """无匹配 Skill 时 injection_summary 仍生成."""
    from riskagent_backend.skills import SkillInjector, SkillStore

    store = SkillStore()
    injector = SkillInjector(store)
    result = await injector.retrieve_applicable_skills(
        task=_make_task(),
        skill_enabled=True,
    )

    assert result["skill_count"] == 0
    assert "injection_summary" in result
    # 空结果时应该有 0 的描述
    assert "0" in result["injection_summary"] or "No query" in result["injection_summary"]


@pytest.mark.asyncio
async def test_injection_summary_skill_off():
    """skill_off 时 injection_summary 提示 disabled."""
    from riskagent_backend.skills import SkillInjector, SkillStore

    store = SkillStore()
    injector = SkillInjector(store)
    result = await injector.retrieve_applicable_skills(
        task=_make_task(),
        skill_enabled=False,
    )

    assert "injection_summary" in result
    assert "disabled" in result["injection_summary"].lower()


# ==================== 额外: 异常隔离 ====================


@pytest.mark.asyncio
async def test_search_exception_returns_safe_structure():
    """skill_store.search 抛异常时返回安全结构, 不崩溃."""
    from riskagent_backend.skills import SkillInjector, SkillStore

    store = SkillStore()
    await store.create(_make_skill(confidence=0.9))

    injector = SkillInjector(store)

    with patch.object(
        store, "search", new_callable=AsyncMock, side_effect=RuntimeError("db error")
    ):
        result = await injector.retrieve_applicable_skills(
            task=_make_task(),
            skill_enabled=True,
        )

    assert result["skill_enabled"] is True
    assert result["skills"] == []
    assert result["skill_count"] == 0
    assert "error" in result["injection_summary"].lower()


# ==================== 额外: intent 从 dict 提取 ====================


# ==================== 9. summary_only 模式注入 ====================


@pytest.mark.asyncio
async def test_summary_only_default_returns_summary_fields():
    """默认 summary_only=True 时只返回 skill_id, name, summary."""
    from riskagent_backend.skills import SkillInjector, SkillStore

    store = SkillStore()
    await store.create(
        _make_skill(
            name="Summary测试技能",
            summary="这是一个摘要",
            confidence=0.85,
        )
    )

    injector = SkillInjector(store, min_confidence=0.3, max_skills=3)
    result = await injector.retrieve_applicable_skills(
        task=_make_task(),
        skill_enabled=True,
    )

    assert result["skill_count"] >= 1
    item = result["skills"][0]

    # summary_only 模式只应包含这三个字段
    assert set(item.keys()) == {"skill_id", "name", "summary"}
    assert item["name"] == "Summary测试技能"
    assert item["summary"] == "这是一个摘要"


@pytest.mark.asyncio
async def test_summary_only_false_returns_full_fields():
    """summary_only=False 时返回完整 Skill 结构."""
    from riskagent_backend.skills import SkillInjector, SkillStore

    store = SkillStore()
    await store.create(
        _make_skill(
            name="完整模式测试",
            applicable_conditions=["条件1"],
            steps=[{"description": "步骤1", "expected_outcome": "结果1"}],
            failure_boundary="边界X",
            confidence=0.8,
        )
    )

    injector = SkillInjector(store, min_confidence=0.3, max_skills=3)
    result = await injector.retrieve_applicable_skills(
        task=_make_task(),
        skill_enabled=True,
        summary_only=False,
    )

    assert result["skill_count"] >= 1
    item = result["skills"][0]

    # 完整模式应包含所有字段
    assert "skill_id" in item
    assert "name" in item
    assert "summary" in item
    assert "applicable_conditions" in item
    assert "steps" in item
    assert "failure_boundary" in item
    assert "confidence" in item
    assert item["name"] == "完整模式测试"
    assert item["applicable_conditions"] == ["条件1"]
    assert len(item["steps"]) == 1
    assert item["failure_boundary"] == "边界X"


def test_build_injection_item_summary_only_true():
    """_build_injection_item(summary_only=True) 只输出 skill_id, name, summary."""
    from riskagent_backend.skills import SkillInjector

    skill = {
        "skill_id": "skill_abc123",
        "name": "测试技能",
        "summary": "摘要内容",
        "steps": [{"description": "步骤1"}],
        "applicable_conditions": ["条件1"],
        "failure_boundary": "边界",
        "confidence": 0.9,
    }

    item = SkillInjector._build_injection_item(skill, summary_only=True)

    assert set(item.keys()) == {"skill_id", "name", "summary"}
    assert item["skill_id"] == "skill_abc123"
    assert item["name"] == "测试技能"
    assert item["summary"] == "摘要内容"


def test_build_injection_item_summary_only_false():
    """_build_injection_item(summary_only=False) 输出完整结构."""
    from riskagent_backend.skills import SkillInjector

    skill = {
        "skill_id": "skill_def456",
        "name": "完整测试",
        "summary": "完整摘要",
        "steps": [{"description": "步骤A", "expected_outcome": "结果A"}],
        "applicable_conditions": ["条件A"],
        "failure_boundary": "边界A",
        "confidence": 0.7,
    }

    item = SkillInjector._build_injection_item(skill, summary_only=False)

    assert item["skill_id"] == "skill_def456"
    assert item["name"] == "完整测试"
    assert item["summary"] == "完整摘要"
    assert item["applicable_conditions"] == ["条件A"]
    assert len(item["steps"]) == 1
    assert item["steps"][0]["description"] == "步骤A"
    assert item["failure_boundary"] == "边界A"
    assert item["confidence"] == pytest.approx(0.7)


def test_build_injection_item_default_is_summary_only():
    """_build_injection_item 默认参数为 summary_only=True."""
    from riskagent_backend.skills import SkillInjector

    skill = {
        "skill_id": "skill_default",
        "name": "默认测试",
        "summary": "默认摘要",
        "steps": [{"description": "步骤1"}],
    }

    item = SkillInjector._build_injection_item(skill)

    assert set(item.keys()) == {"skill_id", "name", "summary"}


@pytest.mark.asyncio
async def test_intent_from_dict_primary_intent_type():
    """task.intent 为 dict 时从 primary_intent_type 提取."""
    from riskagent_backend.skills import SkillInjector, SkillStore

    store = SkillStore()
    await store.create(
        _make_skill(
            name="query_positions 持仓查询",
            applicable_conditions=["持仓", "查询"],
            confidence=0.9,
        )
    )

    injector = SkillInjector(store, min_confidence=0.3, max_skills=3)
    task = {
        "task_id": "task-dict",
        "intent": {"primary_intent_type": "query_positions", "confidence": 0.95},
    }
    result = await injector.retrieve_applicable_skills(
        task=task,
        skill_enabled=True,
    )

    assert result["skill_count"] >= 1


@pytest.mark.asyncio
async def test_payload_style_task():
    """兼容 payload.content 风格的 task."""
    from riskagent_backend.skills import SkillInjector, SkillStore

    store = SkillStore()
    await store.create(
        _make_skill(
            name="交易台排查",
            applicable_conditions=["交易台", "排查"],
            confidence=0.9,
        )
    )

    injector = SkillInjector(store, min_confidence=0.3, max_skills=3)
    task = {
        "task_id": "task-payload",
        "payload": {"content": "查询交易台TRADER-001的持仓数据"},
    }
    result = await injector.retrieve_applicable_skills(
        task=task,
        skill_enabled=True,
    )

    assert result["skill_count"] >= 1
