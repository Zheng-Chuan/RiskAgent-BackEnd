"""SkillInjector 单测."""

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

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
    """默认 summary_only=True 时只返回轻量字段 + 治理元数据."""
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

    # summary_only 模式只应包含这些字段 (confidence/status 供治理过滤, 不注入 prompt 正文)
    assert set(item.keys()) == {"skill_id", "name", "summary", "confidence", "status"}
    assert item["name"] == "Summary测试技能"
    assert item["summary"] == "这是一个摘要"
    assert item["confidence"] == pytest.approx(0.85)


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
    """_build_injection_item(summary_only=True) 只输出轻量字段 + 治理元数据."""
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

    assert set(item.keys()) == {"skill_id", "name", "summary", "confidence", "status"}
    assert item["skill_id"] == "skill_abc123"
    assert item["name"] == "测试技能"
    assert item["summary"] == "摘要内容"
    assert item["confidence"] == pytest.approx(0.9)
    assert item["status"] == "active"


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

    assert set(item.keys()) == {"skill_id", "name", "summary", "confidence", "status"}


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


# ==================== RFC-005 需求五: Query Rewriting 测试 ====================


def _make_mock_llm_client(response_text: str = "") -> MagicMock:
    """构造 mock LlmClient, chat_completions 返回指定文本."""
    mock = MagicMock()
    mock.chat_completions = AsyncMock(
        return_value={
            "choices": [{"message": {"content": response_text}}]
        }
    )
    return mock


@pytest.mark.asyncio
async def test_rewrite_query_normal():
    """_rewrite_query 正常改写: LLM 返回扩展后的 query."""
    from riskagent_backend.skills import SkillInjector, SkillStore

    store = SkillStore()
    mock_client = _make_mock_llm_client("监控交易台敞口风险 检测持仓超限 风险指标异常")

    injector = SkillInjector(store, llm_client=mock_client)
    rewritten = await injector._rewrite_query("监控敞口")

    assert rewritten == "监控交易台敞口风险 检测持仓超限 风险指标异常"
    assert mock_client.chat_completions.call_count == 1


@pytest.mark.asyncio
async def test_rewrite_query_cache_hit():
    """LRU 缓存命中: 相同 query 不重复调用 LLM."""
    from riskagent_backend.skills import SkillInjector, SkillStore

    store = SkillStore()
    mock_client = _make_mock_llm_client("扩展后的检索查询")

    injector = SkillInjector(store, llm_client=mock_client)

    # 第一次调用 - LLM 被调用
    result1 = await injector._rewrite_query("测试查询")
    assert result1 == "扩展后的检索查询"
    assert mock_client.chat_completions.call_count == 1

    # 第二次调用相同 query - 缓存命中, LLM 不被调用
    result2 = await injector._rewrite_query("测试查询")
    assert result2 == "扩展后的检索查询"
    assert mock_client.chat_completions.call_count == 1  # 仍然为 1


@pytest.mark.asyncio
async def test_rewrite_query_llm_timeout_fallback(monkeypatch):
    """LLM 超时 → fallback 到原始 query."""
    from riskagent_backend.skills import SkillInjector, SkillStore

    # 设置极短超时
    monkeypatch.setenv("SKILL_QUERY_REWRITE_TIMEOUT", "0.1")

    store = SkillStore()

    # 构造一个会 sleep 1 秒的 mock (超过 0.1s 超时)
    async def slow_chat(*args, **kwargs):
        await asyncio.sleep(1.0)
        return {"choices": [{"message": {"content": "不应到达"}}]}

    mock_client = MagicMock()
    mock_client.chat_completions = slow_chat

    injector = SkillInjector(store, llm_client=mock_client)
    rewritten = await injector._rewrite_query("原始查询")

    assert rewritten == "原始查询"  # fallback 到原始 query


@pytest.mark.asyncio
async def test_rewrite_query_llm_empty_fallback():
    """LLM 返回空 → fallback 到原始 query."""
    from riskagent_backend.skills import SkillInjector, SkillStore

    store = SkillStore()
    mock_client = _make_mock_llm_client("")  # 空响应

    injector = SkillInjector(store, llm_client=mock_client)
    rewritten = await injector._rewrite_query("原始查询")

    assert rewritten == "原始查询"  # fallback 到原始 query
    assert mock_client.chat_completions.call_count == 1  # LLM 被调用了


@pytest.mark.asyncio
async def test_rewrite_query_disabled(monkeypatch):
    """SKILL_QUERY_REWRITE_ENABLED=false → 跳过改写."""
    from riskagent_backend.skills import SkillInjector, SkillStore

    monkeypatch.setenv("SKILL_QUERY_REWRITE_ENABLED", "false")

    store = SkillStore()
    mock_client = _make_mock_llm_client("不应被调用")

    injector = SkillInjector(store, llm_client=mock_client)
    rewritten = await injector._rewrite_query("原始查询")

    assert rewritten == "原始查询"  # 原样返回
    assert mock_client.chat_completions.call_count == 0  # LLM 未被调用


@pytest.mark.asyncio
async def test_rewrite_query_llm_exception_fallback():
    """LLM 抛异常 → fallback 到原始 query."""
    from riskagent_backend.skills import SkillInjector, SkillStore

    store = SkillStore()

    async def error_chat(*args, **kwargs):
        raise RuntimeError("LLM 服务不可用")

    mock_client = MagicMock()
    mock_client.chat_completions = error_chat

    injector = SkillInjector(store, llm_client=mock_client)
    rewritten = await injector._rewrite_query("原始查询")

    assert rewritten == "原始查询"  # fallback 到原始 query


@pytest.mark.asyncio
async def test_rewrite_query_same_as_original_no_warning():
    """LLM 返回与原始 query 相同时, 正常缓存返回 (不视为 fallback)."""
    from riskagent_backend.skills import SkillInjector, SkillStore

    store = SkillStore()
    mock_client = _make_mock_llm_client("原始查询")  # 返回相同的 query

    injector = SkillInjector(store, llm_client=mock_client)
    rewritten = await injector._rewrite_query("原始查询")

    assert rewritten == "原始查询"
    assert mock_client.chat_completions.call_count == 1  # LLM 被调用了

    # 缓存命中: 第二次不调用 LLM
    rewritten2 = await injector._rewrite_query("原始查询")
    assert rewritten2 == "原始查询"
    assert mock_client.chat_completions.call_count == 1  # 仍然为 1


@pytest.mark.asyncio
async def test_retrieve_skills_uses_rewritten_query():
    """retrieve_applicable_skills() 使用改写后的 query 调用 search."""
    from riskagent_backend.skills import SkillInjector, SkillStore

    store = SkillStore()
    mock_client = _make_mock_llm_client("扩展后的检索查询")

    # 捕获传给 search 的 query
    captured_query = []
    mock_hits = [{
        "skill_id": "skill_test",
        "name": "测试",
        "summary": "测试摘要",
        "confidence": 0.9,
    }]

    async def capture_search(query, *args, **kwargs):
        captured_query.append(query)
        return mock_hits

    injector = SkillInjector(
        store, min_confidence=0.3, max_skills=3, llm_client=mock_client
    )

    with patch.object(store, "search", new=capture_search):
        result = await injector.retrieve_applicable_skills(
            task=_make_task(),
            skill_enabled=True,
        )

    assert len(captured_query) == 1
    assert captured_query[0] == "扩展后的检索查询"  # 使用改写后的 query
    assert mock_client.chat_completions.call_count == 1  # LLM 被调用了
    assert result["skill_count"] >= 1


# ==================== LRU 缓存单元测试 ====================


def test_lru_cache_basic_get_put():
    """LRU 缓存基本 get/put 操作."""
    from riskagent_backend.skills.skill_injector import _QueryRewriteLRUCache

    cache = _QueryRewriteLRUCache(maxsize=3)

    cache.put(hash("a"), "rewritten_a")
    cache.put(hash("b"), "rewritten_b")

    assert cache.get(hash("a")) == "rewritten_a"
    assert cache.get(hash("b")) == "rewritten_b"
    assert cache.get(hash("c")) is None  # 未插入
    assert len(cache) == 2


def test_lru_cache_eviction():
    """LRU 缓存容量超限时淘汰最久未使用的条目."""
    from riskagent_backend.skills.skill_injector import _QueryRewriteLRUCache

    cache = _QueryRewriteLRUCache(maxsize=2)

    cache.put(hash("a"), "rewritten_a")
    cache.put(hash("b"), "rewritten_b")

    # 访问 a, 使 a 成为最近使用
    assert cache.get(hash("a")) == "rewritten_a"

    # 插入 c, 容量超限, 淘汰 b (最久未使用)
    cache.put(hash("c"), "rewritten_c")

    assert cache.get(hash("a")) == "rewritten_a"  # a 仍在
    assert cache.get(hash("b")) is None  # b 已被淘汰
    assert cache.get(hash("c")) == "rewritten_c"  # c 在
    assert len(cache) == 2


def test_lru_cache_overwrite_existing():
    """LRU 缓存覆写已存在的键时更新值并移到队尾 (MRU)."""
    from riskagent_backend.skills.skill_injector import _QueryRewriteLRUCache

    cache = _QueryRewriteLRUCache(maxsize=2)

    cache.put(hash("a"), "v1")
    cache.put(hash("b"), "v2")

    # 覆写 a, a 移到队尾 (MRU), b 变成 LRU
    cache.put(hash("a"), "v1_updated")

    # 插入 c, b 应被淘汰 (a 刚被覆写, 是 MRU)
    cache.put(hash("c"), "v3")

    assert cache.get(hash("a")) == "v1_updated"  # a 仍在, 值已更新
    assert cache.get(hash("b")) is None  # b 被淘汰
    assert cache.get(hash("c")) == "v3"  # c 在


def test_lru_cache_clear():
    """LRU 缓存清空."""
    from riskagent_backend.skills.skill_injector import _QueryRewriteLRUCache

    cache = _QueryRewriteLRUCache(maxsize=5)
    cache.put(hash("a"), "v1")
    cache.put(hash("b"), "v2")
    assert len(cache) == 2

    cache.clear()
    assert len(cache) == 0
    assert cache.get(hash("a")) is None


@pytest.mark.asyncio
async def test_rewrite_query_cache_eviction_integration(monkeypatch):
    """集成测试: LRU 缓存淘汰后, 被淘汰的 query 再次调用会触发 LLM."""
    from riskagent_backend.skills import SkillInjector, SkillStore

    # 设置小缓存容量
    monkeypatch.setenv("SKILL_QUERY_REWRITE_CACHE_SIZE", "2")

    store = SkillStore()
    call_count = [0]

    async def counting_chat(*args, **kwargs):
        call_count[0] += 1
        # 从 prompt 提取原始查询, 返回扩展版本
        messages = kwargs.get("messages", [])
        for msg in messages:
            if msg.get("role") == "user":
                content = msg.get("content", "")
                for line in content.split("\n"):
                    if line.strip().startswith("原始查询:"):
                        original = line.replace("原始查询:", "").strip()
                        return {
                            "choices": [{"message": {"content": f"扩展_{original}"}}]
                        }
        return {"choices": [{"message": {"content": "扩展"}}]}

    mock_client = MagicMock()
    mock_client.chat_completions = counting_chat

    injector = SkillInjector(store, llm_client=mock_client)

    # 插入 3 个不同的 query (容量=2, 第一个会被淘汰)
    await injector._rewrite_query("query1")
    await injector._rewrite_query("query2")
    await injector._rewrite_query("query3")
    assert call_count[0] == 3  # 3 次 LLM 调用

    # query1 已被淘汰, 再次调用会触发 LLM
    await injector._rewrite_query("query1")
    assert call_count[0] == 4  # 第 4 次 LLM 调用

    # query3 仍在缓存中 (最近使用), 不会触发 LLM
    await injector._rewrite_query("query3")
    assert call_count[0] == 4  # 仍为 4

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
