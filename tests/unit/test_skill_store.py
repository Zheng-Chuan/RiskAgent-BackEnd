"""SkillStore 单测."""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

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
    }
    base.update(kwargs)
    return base


# ==================== create + get ====================


@pytest.mark.asyncio
async def test_create_and_get_roundtrip():
    """测试 create + get 往返."""
    from riskagent_backend.skills import SkillStore

    store = SkillStore()
    created = await store.create(_make_skill())
    assert created["skill_id"].startswith("skill_")
    assert created["name"] == "交易台风险排查"
    assert created["status"] == "active"

    fetched = await store.get(created["skill_id"])
    assert fetched is not None
    assert fetched["name"] == "交易台风险排查"
    assert fetched["skill_id"] == created["skill_id"]


@pytest.mark.asyncio
async def test_get_nonexistent_returns_none():
    """测试 get 不存在的 skill_id 返回 None."""
    from riskagent_backend.skills import SkillStore

    store = SkillStore()
    assert await store.get("skill_nonexistent") is None


@pytest.mark.asyncio
async def test_create_invalid_skill_raises():
    """测试 create 非法 skill 抛出异常."""
    from riskagent_backend.skills import SkillStore

    store = SkillStore()
    with pytest.raises(ValueError, match="bad_name"):
        await store.create({"tags": ["x"]})


# ==================== update ====================


@pytest.mark.asyncio
async def test_update_partial_fields():
    """测试 update 部分字段."""
    from riskagent_backend.skills import SkillStore

    store = SkillStore()
    created = await store.create(_make_skill())
    updated = await store.update(
        created["skill_id"], {"confidence": 0.9, "tags": ["risk", "updated"]}
    )
    assert updated["confidence"] == 0.9
    assert "updated" in updated["tags"]
    assert updated["skill_id"] == created["skill_id"]
    assert updated["created_at"] == created["created_at"]
    assert updated["updated_at"] >= created["updated_at"]


@pytest.mark.asyncio
async def test_update_nonexistent_raises():
    """测试 update 不存在的 skill_id 抛出异常."""
    from riskagent_backend.skills import SkillStore

    store = SkillStore()
    with pytest.raises(KeyError):
        await store.update("skill_nonexistent", {"confidence": 0.9})


@pytest.mark.asyncio
async def test_update_invalid_patch_raises():
    """测试 update 非法 patch 抛出异常."""
    from riskagent_backend.skills import SkillStore

    store = SkillStore()
    created = await store.create(_make_skill())
    with pytest.raises(ValueError, match="unsupported_status"):
        await store.update(created["skill_id"], {"status": "unknown"})


# ==================== delete ====================


@pytest.mark.asyncio
async def test_delete():
    """测试 delete."""
    from riskagent_backend.skills import SkillStore

    store = SkillStore()
    created = await store.create(_make_skill())
    assert await store.delete(created["skill_id"]) is True
    assert await store.get(created["skill_id"]) is None


@pytest.mark.asyncio
async def test_delete_nonexistent_returns_false():
    """测试 delete 不存在的 skill_id 返回 False."""
    from riskagent_backend.skills import SkillStore

    store = SkillStore()
    assert await store.delete("skill_nonexistent") is False


# ==================== list_all ====================


@pytest.mark.asyncio
async def test_list_all_with_status_filter():
    """测试 list_all 带 status 过滤."""
    from riskagent_backend.skills import SkillStore

    store = SkillStore()
    await store.create(_make_skill(name="skill1"))
    await store.create(_make_skill(name="skill2", status="deprecated"))
    await store.create(_make_skill(name="skill3", status="archived"))

    all_skills = await store.list_all()
    assert len(all_skills) == 3

    active = await store.list_all(status="active")
    assert len(active) == 1
    assert active[0]["name"] == "skill1"

    deprecated = await store.list_all(status="deprecated")
    assert len(deprecated) == 1
    assert deprecated[0]["name"] == "skill2"

    archived = await store.list_all(status="archived")
    assert len(archived) == 1
    assert archived[0]["name"] == "skill3"


@pytest.mark.asyncio
async def test_list_all_with_tag_filter():
    """测试 list_all 带 tag 过滤."""
    from riskagent_backend.skills import SkillStore

    store = SkillStore()
    await store.create(_make_skill(name="skill1", tags=["risk", "trading"]))
    await store.create(_make_skill(name="skill2", tags=["compliance"]))
    await store.create(_make_skill(name="skill3", tags=["risk", "audit"]))

    risk_tagged = await store.list_all(tag="risk")
    assert len(risk_tagged) == 2

    trading_tagged = await store.list_all(tag="trading")
    assert len(trading_tagged) == 1
    assert trading_tagged[0]["name"] == "skill1"

    compliance_tagged = await store.list_all(tag="compliance")
    assert len(compliance_tagged) == 1
    assert compliance_tagged[0]["name"] == "skill2"


@pytest.mark.asyncio
async def test_list_all_with_status_and_tag_filter():
    """测试 list_all 同时带 status 和 tag 过滤."""
    from riskagent_backend.skills import SkillStore

    store = SkillStore()
    await store.create(_make_skill(name="skill1", tags=["risk"], status="active"))
    await store.create(_make_skill(name="skill2", tags=["risk"], status="deprecated"))

    active_risk = await store.list_all(status="active", tag="risk")
    assert len(active_risk) == 1
    assert active_risk[0]["name"] == "skill1"


# ==================== search ====================


@pytest.mark.asyncio
async def test_search_semantic():
    """测试 search 语义检索."""
    from riskagent_backend.skills import SkillStore

    store = SkillStore()
    await store.create(
        _make_skill(
            name="交易台风险排查",
            applicable_conditions=["延迟异常"],
            steps=[
                {"description": "查询持仓数据", "expected_outcome": "获取持仓"}
            ],
        )
    )
    await store.create(
        _make_skill(
            name="合规报告生成",
            tags=["compliance"],
            applicable_conditions=["季度审计"],
            steps=[
                {"description": "收集审计数据", "expected_outcome": "生成报告"}
            ],
        )
    )

    hits = await store.search("交易台持仓延迟异常排查")
    assert len(hits) >= 1
    assert hits[0]["name"] == "交易台风险排查"
    assert hits[0].get("semantic_score", 0.0) > 0.0


@pytest.mark.asyncio
async def test_search_filters_non_active():
    """测试 search 过滤非 active 的 Skill."""
    from riskagent_backend.skills import SkillStore

    store = SkillStore()
    await store.create(_make_skill(name="活跃技能", status="active", summary="风险排查活跃技能"))
    await store.create(_make_skill(name="废弃技能", status="deprecated", summary="风险排查废弃技能"))

    hits = await store.search("风险排查")
    names = [h["name"] for h in hits]
    assert "活跃技能" in names
    assert "废弃技能" not in names


@pytest.mark.asyncio
async def test_search_min_confidence_filter():
    """测试 search min_confidence 过滤."""
    from riskagent_backend.skills import SkillStore

    store = SkillStore()
    await store.create(_make_skill(name="低置信度技能", confidence=0.3, summary="风险排查低置信度"))
    await store.create(_make_skill(name="高置信度技能", confidence=0.9, summary="风险排查高置信度"))

    all_hits = await store.search("风险排查", min_confidence=0.0)
    assert len(all_hits) >= 2

    high_only = await store.search("风险排查", min_confidence=0.5)
    assert len(high_only) == 1
    assert high_only[0]["name"] == "高置信度技能"


@pytest.mark.asyncio
async def test_search_empty_query_returns_empty():
    """测试 search 空查询返回空列表."""
    from riskagent_backend.skills import SkillStore

    store = SkillStore()
    await store.create(_make_skill())
    hits = await store.search("")
    assert hits == []


@pytest.mark.asyncio
async def test_search_keyword_fallback_still_merges_when_semantic_hits_are_full():
    """测试 Hybrid 检索: 向量结果已满时 BM25 通道仍合并命中."""
    from riskagent_backend.skills import SkillStore

    store = SkillStore()
    target = await store.create(
        _make_skill(
            skill_id="skill_target",
            name="集成测试 Skill",
            summary="集成测试风险排查技能",
            tags=["risk", "integration"],
            applicable_conditions=["集成测试"],
        )
    )
    for index in range(5):
        await store.create(
            _make_skill(
                skill_id=f"skill_noise_{index}",
                name=f"噪声技能{index}",
                summary=f"噪声技能摘要{index}",
                tags=["noise"],
            )
        )

    async def fake_semantic_search(_query: str, limit: int = 5):
        hits = []
        for index in range(min(limit, 5)):
            noise = await store.get(f"skill_noise_{index}")
            assert noise is not None
            hits.append({"skill": noise, "semantic_score": 0.9 - (index * 0.01)})
        return hits

    store._indexer.search = fake_semantic_search  # type: ignore[method-assign]
    hits = await store.search("集成测试", limit=10)

    assert any(hit["skill_id"] == target["skill_id"] for hit in hits)


# ==================== find_similar ====================


@pytest.mark.asyncio
async def test_find_similar_finds_match():
    """测试 find_similar 找到相似 Skill."""
    from riskagent_backend.skills import SkillStore

    store = SkillStore()
    await store.create(
        _make_skill(
            name="交易台风险排查流程",
            steps=[
                {"description": "查询持仓数据并核对限额", "expected_outcome": "确认风险"}
            ],
        )
    )

    candidate = _make_skill(
        name="交易台风险排查流程",
        steps=[
            {"description": "查询持仓数据并核对限额", "expected_outcome": "确认风险"}
        ],
    )
    similar = await store.find_similar(candidate, threshold=0.0)
    assert len(similar) >= 1
    assert similar[0]["name"] == "交易台风险排查流程"


@pytest.mark.asyncio
async def test_find_similar_excludes_self():
    """测试 find_similar 排除自身."""
    from riskagent_backend.skills import SkillStore

    store = SkillStore()
    created = await store.create(_make_skill(name="排查流程"))

    # 用已存储的 skill 查找相似, 应排除自身
    stored = await store.get(created["skill_id"])
    assert stored is not None
    similar = await store.find_similar(stored, threshold=0.0)
    assert all(s["skill_id"] != created["skill_id"] for s in similar)


@pytest.mark.asyncio
async def test_find_similar_high_threshold():
    """测试 find_similar 高阈值不匹配不相关 Skill."""
    from riskagent_backend.skills import SkillStore

    store = SkillStore()
    await store.create(
        _make_skill(
            name="交易台风险排查",
            steps=[{"description": "查持仓", "expected_outcome": "获取数据"}],
        )
    )
    candidate = _make_skill(
        name="合规报告生成",
        summary="合规审计报告生成与归档工作流",
        tags=["compliance"],
        steps=[{"description": "收集审计数据", "expected_outcome": "生成报告"}],
    )
    similar = await store.find_similar(candidate, threshold=0.99)
    assert len(similar) == 0


# ==================== update_confidence ====================


@pytest.mark.asyncio
async def test_update_confidence_success():
    """测试 update_confidence 成功场景."""
    from riskagent_backend.skills import SkillStore

    store = SkillStore()
    created = await store.create(_make_skill(confidence=0.5))
    updated = await store.update_confidence(created["skill_id"], True, delta=0.1)
    assert updated["confidence"] == pytest.approx(0.6)
    assert updated["usage_count"] == 1
    assert updated["success_rate"] == pytest.approx(1.0)
    assert updated["status"] == "active"


@pytest.mark.asyncio
async def test_update_confidence_failure():
    """测试 update_confidence 失败场景."""
    from riskagent_backend.skills import SkillStore

    store = SkillStore()
    created = await store.create(_make_skill(confidence=0.5))
    updated = await store.update_confidence(created["skill_id"], False, delta=0.1)
    assert updated["confidence"] == pytest.approx(0.4)
    assert updated["usage_count"] == 1
    assert updated["success_rate"] == pytest.approx(0.0)
    assert updated["status"] == "active"


@pytest.mark.asyncio
async def test_update_confidence_mixed():
    """测试 update_confidence 混合成功失败场景."""
    from riskagent_backend.skills import SkillStore

    store = SkillStore()
    created = await store.create(_make_skill(confidence=0.5))

    # 成功一次
    await store.update_confidence(created["skill_id"], True, delta=0.1)
    # 失败一次
    updated = await store.update_confidence(
        created["skill_id"], False, delta=0.1
    )
    assert updated["confidence"] == pytest.approx(0.5)
    assert updated["usage_count"] == 2
    assert updated["success_rate"] == pytest.approx(0.5)
    assert updated["status"] == "active"


@pytest.mark.asyncio
async def test_update_confidence_caps_at_1():
    """测试 update_confidence 上限为 1.0."""
    from riskagent_backend.skills import SkillStore

    store = SkillStore()
    created = await store.create(_make_skill(confidence=0.95))
    updated = await store.update_confidence(created["skill_id"], True, delta=0.1)
    assert updated["confidence"] == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_update_confidence_floors_at_0():
    """测试 update_confidence 下限为 0.0."""
    from riskagent_backend.skills import SkillStore

    store = SkillStore()
    created = await store.create(_make_skill(confidence=0.05))
    updated = await store.update_confidence(created["skill_id"], False, delta=0.1)
    assert updated["confidence"] == pytest.approx(0.0)


@pytest.mark.asyncio
async def test_low_confidence_deprecated():
    """测试低置信度自动降级到 deprecated."""
    from riskagent_backend.skills import SkillStore

    store = SkillStore()
    created = await store.create(_make_skill(confidence=0.3))
    updated = await store.update_confidence(created["skill_id"], False, delta=0.05)
    assert updated["confidence"] == pytest.approx(0.25)
    assert updated["status"] == "deprecated"


@pytest.mark.asyncio
async def test_low_confidence_archived():
    """测试极低置信度自动降级到 archived."""
    from riskagent_backend.skills import SkillStore

    store = SkillStore()
    created = await store.create(_make_skill(confidence=0.2))
    updated = await store.update_confidence(created["skill_id"], False, delta=0.1)
    assert updated["confidence"] == pytest.approx(0.1)
    assert updated["status"] == "archived"


@pytest.mark.asyncio
async def test_update_confidence_nonexistent_raises():
    """测试 update_confidence 不存在的 skill_id 抛出异常."""
    from riskagent_backend.skills import SkillStore

    store = SkillStore()
    with pytest.raises(KeyError):
        await store.update_confidence("skill_nonexistent", True)


# ==================== _build_skill_text: summary 优先 ====================


@pytest.mark.asyncio
async def test_build_skill_text_uses_summary_when_present():
    """summary 存在且非空时，_build_skill_text 优先返回 summary."""
    from riskagent_backend.skills import SkillStore

    store = SkillStore()
    skill = _make_skill(summary="摘要文本优先使用")
    text = store._build_skill_text(skill)
    assert text == "摘要文本优先使用"


@pytest.mark.asyncio
async def test_build_skill_text_fallback_when_summary_empty():
    """summary 为空时，_build_skill_text fallback 到全字段拼接."""
    from riskagent_backend.skills import SkillStore

    store = SkillStore()
    skill = _make_skill(summary="")
    text = store._build_skill_text(skill)
    # fallback 包含 name, tags, conditions, steps 等
    assert "交易台风险排查" in text
    assert len(text) > len("交易台风险排查")
    # summary 为空时不只返回 summary
    assert text != ""


@pytest.mark.asyncio
async def test_build_skill_text_fallback_when_summary_missing():
    """summary 字段缺失时，_build_skill_text fallback 到全字段拼接."""
    from riskagent_backend.skills import SkillStore

    store = SkillStore()
    skill = _make_skill()
    del skill["summary"]
    text = store._build_skill_text(skill)
    assert "交易台风险排查" in text
    assert len(text) > len("交易台风险排查")


# ==================== health_check ====================


@pytest.mark.asyncio
async def test_health_check():
    """测试 health_check."""
    from riskagent_backend.skills import SkillStore

    store = SkillStore()
    assert await store.health_check() is True


# ==================== Chroma 向量检索路径 (RFC-005 需求一) ====================


def _make_mock_llm_client():
    """创建 mock LLMClient, embed() 返回 1536 维向量."""
    client = MagicMock()
    client.embed = AsyncMock(return_value=[0.1] * 1536)
    return client


def _make_mock_chroma_store():
    """创建 mock ChromaVectorStore."""
    store = MagicMock()
    store.upsert_skill_embedding = MagicMock()
    store.query_skills = MagicMock(return_value=[])
    store.delete_skill_embedding = MagicMock()
    return store


@pytest.mark.asyncio
async def test_index_skill_writes_to_chroma():
    """测试 _index_skill 通过 LLMClient.embed() 生成向量并写入 Chroma."""
    from riskagent_backend.skills import SkillStore

    llm_client = _make_mock_llm_client()
    chroma_store = _make_mock_chroma_store()
    store = SkillStore(llm_client=llm_client, chroma_store=chroma_store)

    created = await store.create(_make_skill())

    # 验证 embed 被调用 (传入 summary 文本)
    llm_client.embed.assert_called_once()
    called_text = llm_client.embed.call_args[0][0]
    assert "从持仓查询到限额核对的完整风险排查工作流" in called_text

    # 验证 upsert_skill_embedding 被调用
    chroma_store.upsert_skill_embedding.assert_called_once()
    call_kwargs = chroma_store.upsert_skill_embedding.call_args.kwargs
    assert call_kwargs["skill_id"] == created["skill_id"]
    assert call_kwargs["embedding"] == [0.1] * 1536
    assert call_kwargs["metadata"]["skill_id"] == created["skill_id"]
    assert call_kwargs["metadata"]["status"] == "active"


@pytest.mark.asyncio
async def test_search_uses_chroma_ann():
    """测试 search() 调用 Chroma ANN 检索."""
    from riskagent_backend.knowledge.chroma_store import SimilarDoc
    from riskagent_backend.skills import SkillStore

    llm_client = _make_mock_llm_client()
    chroma_store = _make_mock_chroma_store()
    store = SkillStore(llm_client=llm_client, chroma_store=chroma_store)

    skill1 = await store.create(_make_skill(name="交易台风险排查", summary="风险排查工作流"))
    await store.create(_make_skill(name="合规报告", summary="合规审计工作流"))

    # Mock query_skills 返回 skill1
    chroma_store.query_skills = MagicMock(return_value=[
        SimilarDoc(
            doc_id=skill1["skill_id"],
            similarity=0.95,
            document="风险排查工作流",
            metadata={"skill_id": skill1["skill_id"], "status": "active"},
        ),
    ])

    hits = await store.search("风险排查", limit=5)

    # 验证 query_skills 被调用
    chroma_store.query_skills.assert_called_once()
    call_kwargs = chroma_store.query_skills.call_args.kwargs
    assert call_kwargs["query_embedding"] == [0.1] * 1536
    assert call_kwargs["top_k"] == 5

    # 验证结果 (Hybrid 检索: 向量归一化后 0.95→1.0, BM25 也命中同一 skill 归一化后 1.0)
    # final = 0.7 * 1.0 + 0.3 * 1.0 = 1.0
    assert len(hits) >= 1
    assert hits[0]["skill_id"] == skill1["skill_id"]
    assert hits[0]["semantic_score"] == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_search_fallback_to_keyword_when_chroma_query_fails():
    """测试 Chroma query 失败时 fallback 到关键词检索."""
    from riskagent_backend.skills import SkillStore

    llm_client = _make_mock_llm_client()
    chroma_store = _make_mock_chroma_store()
    chroma_store.query_skills = MagicMock(side_effect=RuntimeError("Chroma unavailable"))
    store = SkillStore(llm_client=llm_client, chroma_store=chroma_store)

    await store.create(_make_skill(name="风险排查", summary="风险排查工作流", tags=["risk"]))

    hits = await store.search("风险排查")
    assert len(hits) >= 1
    assert hits[0]["name"] == "风险排查"


@pytest.mark.asyncio
async def test_search_fallback_when_embed_fails():
    """测试 embed() 失败时 _index_skill fallback 到 SemanticIndexer."""
    from riskagent_backend.skills import SkillStore

    llm_client = MagicMock()
    llm_client.embed = AsyncMock(side_effect=RuntimeError("LLM unavailable"))
    chroma_store = _make_mock_chroma_store()
    store = SkillStore(llm_client=llm_client, chroma_store=chroma_store)

    # create 会 fallback 到 SemanticIndexer
    created = await store.create(_make_skill(name="风险排查", summary="风险排查工作流"))

    # Chroma upsert 不应被调用
    chroma_store.upsert_skill_embedding.assert_not_called()

    # SemanticIndexer 应该有索引
    assert created["skill_id"] in store._indexer.index

    # search 也会 fallback (embed 失败 → SemanticIndexer)
    hits = await store.search("风险排查")
    assert len(hits) >= 1


@pytest.mark.asyncio
async def test_delete_removes_from_chroma():
    """测试 delete 同步删除 Chroma 向量."""
    from riskagent_backend.skills import SkillStore

    llm_client = _make_mock_llm_client()
    chroma_store = _make_mock_chroma_store()
    store = SkillStore(llm_client=llm_client, chroma_store=chroma_store)

    created = await store.create(_make_skill())
    result = await store.delete(created["skill_id"])

    assert result is True
    chroma_store.delete_skill_embedding.assert_called_once()
    call_kwargs = chroma_store.delete_skill_embedding.call_args.kwargs
    assert call_kwargs["skill_id"] == created["skill_id"]


@pytest.mark.asyncio
async def test_restore_from_persistence_rebuilds_chroma_index():
    """测试 restore_from_persistence 重新生成 embedding 写入 Chroma."""
    from riskagent_backend.skills import SkillStore

    llm_client = _make_mock_llm_client()
    chroma_store = _make_mock_chroma_store()
    store = SkillStore(llm_client=llm_client, chroma_store=chroma_store)

    mock_persistence = MagicMock()
    mock_persistence.load_skills = AsyncMock(return_value=[
        _make_skill(skill_id="skill_restored_1", name="恢复技能1", summary="恢复技能1摘要"),
        _make_skill(skill_id="skill_restored_2", name="恢复技能2", summary="恢复技能2摘要"),
    ])
    store._set_persistence(mock_persistence)

    count = await store.restore_from_persistence()
    assert count == 2

    # 验证 embed 被调用 2 次 (每个 skill 一次)
    assert llm_client.embed.call_count == 2
    # 验证 upsert 被调用 2 次
    assert chroma_store.upsert_skill_embedding.call_count == 2


@pytest.mark.asyncio
async def test_find_similar_uses_chroma_search():
    """测试 find_similar 通过 Chroma 检索工作."""
    from riskagent_backend.knowledge.chroma_store import SimilarDoc
    from riskagent_backend.skills import SkillStore

    llm_client = _make_mock_llm_client()
    chroma_store = _make_mock_chroma_store()
    store = SkillStore(llm_client=llm_client, chroma_store=chroma_store)

    existing = await store.create(
        _make_skill(name="交易台风险排查", summary="风险排查工作流")
    )

    # Mock query_skills 返回已存储的 skill
    chroma_store.query_skills = MagicMock(return_value=[
        SimilarDoc(
            doc_id=existing["skill_id"],
            similarity=0.9,
            document="风险排查工作流",
            metadata={"skill_id": existing["skill_id"], "status": "active"},
        ),
    ])

    candidate = _make_skill(name="交易台风险排查", summary="风险排查工作流")
    similar = await store.find_similar(candidate, threshold=0.5)
    assert len(similar) >= 1
    assert similar[0]["skill_id"] == existing["skill_id"]


@pytest.mark.asyncio
async def test_chroma_enabled_property():
    """测试 _chroma_enabled 属性正确判断依赖注入状态."""
    from riskagent_backend.skills import SkillStore

    # 无依赖注入 → False
    store_no_chroma = SkillStore()
    assert store_no_chroma._chroma_enabled is False

    # 有依赖注入 → True
    llm_client = _make_mock_llm_client()
    chroma_store = _make_mock_chroma_store()
    store_with_chroma = SkillStore(llm_client=llm_client, chroma_store=chroma_store)
    assert store_with_chroma._chroma_enabled is True

    # 只有 LLMClient → False
    store_partial = SkillStore(llm_client=llm_client)
    assert store_partial._chroma_enabled is False


@pytest.mark.asyncio
async def test_search_empty_query_with_chroma():
    """测试 Chroma 路径下空查询返回空列表."""
    from riskagent_backend.skills import SkillStore

    llm_client = MagicMock()
    # embed 对空文本抛异常 (与真实 LlmClient 行为一致)
    llm_client.embed = AsyncMock(side_effect=ValueError("text 不能为空"))
    chroma_store = _make_mock_chroma_store()
    store = SkillStore(llm_client=llm_client, chroma_store=chroma_store)

    await store.create(_make_skill(name="风险排查", summary="风险排查工作流"))
    hits = await store.search("")
    assert hits == []
    # embed 抛异常后 fallback, query_skills 不应被调用
    chroma_store.query_skills.assert_not_called()


# ==================== Hybrid 检索 (RFC-005 需求四) ====================


@pytest.mark.asyncio
async def test_normalize_scores():
    """测试 _normalize_scores 归一化."""
    from riskagent_backend.skills import SkillStore

    # 正常归一化: max=4.0 → [0.25, 0.5, 1.0]
    assert SkillStore._normalize_scores([1.0, 2.0, 4.0]) == [0.25, 0.5, 1.0]
    # 空列表
    assert SkillStore._normalize_scores([]) == []
    # 全零分数
    assert SkillStore._normalize_scores([0.0, 0.0, 0.0]) == [0.0, 0.0, 0.0]
    # 单个分数 → 归一化为 1.0
    assert SkillStore._normalize_scores([5.0]) == [1.0]


@pytest.mark.asyncio
async def test_merge_hybrid_results_basic():
    """测试 _merge_hybrid_results 基本加权合并."""
    from riskagent_backend.skills import SkillStore

    store = SkillStore()
    vector_hits = [
        {"skill": {"skill_id": "s1", "name": "v1"}, "semantic_score": 0.9},
        {"skill": {"skill_id": "s2", "name": "v2"}, "semantic_score": 0.6},
    ]
    bm25_hits = [
        {"skill_id": "s2", "name": "v2", "bm25_score": 1.0},
        {"skill_id": "s3", "name": "v3", "bm25_score": 0.5},
    ]
    merged = store._merge_hybrid_results(vector_hits, bm25_hits, alpha=0.7)
    by_id = {r["skill_id"]: r for r in merged}

    # s1: only vector, norm_v=1.0 → final = 0.7 * 1.0 = 0.7
    assert by_id["s1"]["semantic_score"] == pytest.approx(0.7)
    # s2: both, norm_v=0.6/0.9, norm_b=1.0 → final = 0.7*(0.6/0.9) + 0.3*1.0
    assert by_id["s2"]["semantic_score"] == pytest.approx(0.7 * (0.6 / 0.9) + 0.3 * 1.0)
    assert by_id["s2"]["vector_score"] == pytest.approx(0.6 / 0.9)
    assert by_id["s2"]["bm25_score"] == pytest.approx(1.0)
    # s3: only BM25, norm_b=0.5 → final = 0.3 * 0.5 = 0.15
    assert by_id["s3"]["semantic_score"] == pytest.approx(0.3 * 0.5)


@pytest.mark.asyncio
async def test_merge_hybrid_results_dedup():
    """测试去重: 同一 Skill 在两个通道都出现时合并分数."""
    from riskagent_backend.skills import SkillStore

    store = SkillStore()
    vector_hits = [
        {"skill": {"skill_id": "s1", "name": "skill1"}, "semantic_score": 0.8},
    ]
    bm25_hits = [
        {"skill_id": "s1", "name": "skill1", "bm25_score": 0.6},
    ]
    merged = store._merge_hybrid_results(vector_hits, bm25_hits, alpha=0.7)
    assert len(merged) == 1
    # norm_v=1.0, norm_b=1.0 → final = 0.7*1.0 + 0.3*1.0 = 1.0
    assert merged[0]["skill_id"] == "s1"
    assert merged[0]["semantic_score"] == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_merge_hybrid_results_empty_channels():
    """测试空通道处理."""
    from riskagent_backend.skills import SkillStore

    store = SkillStore()
    # 两个通道都空
    assert store._merge_hybrid_results([], [], alpha=0.7) == []
    # 只有向量
    vector_hits = [{"skill": {"skill_id": "s1"}, "semantic_score": 0.9}]
    merged = store._merge_hybrid_results(vector_hits, [], alpha=0.7)
    assert len(merged) == 1
    assert merged[0]["semantic_score"] == pytest.approx(0.7 * 1.0)
    # 只有 BM25
    bm25_hits = [{"skill_id": "s2", "bm25_score": 0.5}]
    merged = store._merge_hybrid_results([], bm25_hits, alpha=0.7)
    assert len(merged) == 1
    assert merged[0]["semantic_score"] == pytest.approx(0.3 * 1.0)


@pytest.mark.asyncio
async def test_search_hybrid_alpha_1_pure_vector(monkeypatch):
    """测试 alpha=1.0 时纯向量检索, BM25 被禁用."""
    from riskagent_backend.knowledge.chroma_store import SimilarDoc
    from riskagent_backend.skills import SkillStore

    monkeypatch.setenv("SKILL_HYBRID_VECTOR_WEIGHT", "1.0")

    llm_client = _make_mock_llm_client()
    chroma_store = _make_mock_chroma_store()
    store = SkillStore(llm_client=llm_client, chroma_store=chroma_store)

    skill1 = await store.create(_make_skill(name="向量匹配", summary="向量匹配工作流"))
    skill2 = await store.create(_make_skill(name="关键词匹配", summary="关键词匹配工作流"))

    chroma_store.query_skills = MagicMock(return_value=[
        SimilarDoc(doc_id=skill1["skill_id"], similarity=0.9, document="向量匹配工作流", metadata={}),
    ])

    hits = await store.search("向量匹配 关键词匹配", limit=5)

    # alpha=1.0: 只有向量结果, BM25 被禁用
    assert len(hits) == 1
    assert hits[0]["skill_id"] == skill1["skill_id"]
    # skill2 不应在结果中 (BM25 被禁用)
    assert all(h["skill_id"] != skill2["skill_id"] for h in hits)


@pytest.mark.asyncio
async def test_search_hybrid_alpha_0_pure_bm25(monkeypatch):
    """测试 alpha=0.0 时纯 BM25 检索, 向量被禁用."""
    from riskagent_backend.knowledge.chroma_store import SimilarDoc
    from riskagent_backend.skills import SkillStore

    monkeypatch.setenv("SKILL_HYBRID_VECTOR_WEIGHT", "0.0")

    llm_client = _make_mock_llm_client()
    chroma_store = _make_mock_chroma_store()
    store = SkillStore(llm_client=llm_client, chroma_store=chroma_store)

    skill1 = await store.create(_make_skill(name="向量匹配", summary="向量匹配工作流"))
    skill2 = await store.create(_make_skill(name="关键词匹配", summary="关键词匹配工作流"))

    chroma_store.query_skills = MagicMock(return_value=[
        SimilarDoc(doc_id=skill1["skill_id"], similarity=0.9, document="向量匹配工作流", metadata={}),
    ])

    hits = await store.search("关键词匹配", limit=5)

    # alpha=0.0: 只有 BM25 结果, 向量被禁用
    chroma_store.query_skills.assert_not_called()
    # skill2 通过 BM25 匹配
    assert any(h["skill_id"] == skill2["skill_id"] for h in hits)
    # skill1 不在 BM25 结果中
    assert all(h["skill_id"] != skill1["skill_id"] for h in hits)


@pytest.mark.asyncio
async def test_search_hybrid_alpha_default(monkeypatch):
    """测试默认 alpha=0.7 时加权合并."""
    from riskagent_backend.knowledge.chroma_store import SimilarDoc
    from riskagent_backend.skills import SkillStore

    monkeypatch.delenv("SKILL_HYBRID_VECTOR_WEIGHT", raising=False)

    llm_client = _make_mock_llm_client()
    chroma_store = _make_mock_chroma_store()
    store = SkillStore(llm_client=llm_client, chroma_store=chroma_store)

    skill_v = await store.create(_make_skill(name="向量技能", summary="向量技能摘要"))
    skill_b = await store.create(_make_skill(name="关键词技能", summary="关键词技能摘要"))

    chroma_store.query_skills = MagicMock(return_value=[
        SimilarDoc(doc_id=skill_v["skill_id"], similarity=0.9, document="向量技能摘要", metadata={}),
    ])

    hits = await store.search("向量 关键词", limit=5)

    # 两个通道都应返回结果
    hit_ids = [h["skill_id"] for h in hits]
    assert skill_v["skill_id"] in hit_ids  # 来自向量通道
    assert skill_b["skill_id"] in hit_ids  # 来自 BM25 通道


@pytest.mark.asyncio
async def test_search_hybrid_filter_still_works(monkeypatch):
    """测试 Hybrid 检索仍然过滤 status 和 confidence."""
    monkeypatch.delenv("SKILL_HYBRID_VECTOR_WEIGHT", raising=False)

    from riskagent_backend.skills import SkillStore

    store = SkillStore()
    await store.create(_make_skill(name="活跃技能", confidence=0.9, summary="风险排查活跃技能"))
    await store.create(_make_skill(name="废弃技能", status="deprecated", summary="风险排查废弃技能"))
    await store.create(_make_skill(name="低置信度技能", confidence=0.1, summary="风险排查低置信度技能"))

    # min_confidence=0.0: 只过滤 status
    hits = await store.search("风险排查")
    names = [h["name"] for h in hits]
    assert "活跃技能" in names
    assert "废弃技能" not in names
    assert "低置信度技能" in names

    # min_confidence=0.5: 过滤低置信度
    high_hits = await store.search("风险排查", min_confidence=0.5)
    high_names = [h["name"] for h in high_hits]
    assert "活跃技能" in high_names
    assert "低置信度技能" not in high_names


@pytest.mark.asyncio
async def test_search_hybrid_empty_vector_channel():
    """测试向量通道返回空时不报错, BM25 仍返回结果."""
    from riskagent_backend.skills import SkillStore

    llm_client = _make_mock_llm_client()
    chroma_store = _make_mock_chroma_store()
    store = SkillStore(llm_client=llm_client, chroma_store=chroma_store)

    await store.create(_make_skill(name="风险排查", summary="风险排查工作流"))

    # Mock Chroma 返回空 (向量通道无命中)
    chroma_store.query_skills = MagicMock(return_value=[])

    hits = await store.search("风险排查", limit=5)
    assert len(hits) >= 1
    assert hits[0]["name"] == "风险排查"


@pytest.mark.asyncio
async def test_search_hybrid_empty_bm25_channel():
    """测试 BM25 通道返回空时不报错, 向量仍返回结果."""
    from riskagent_backend.knowledge.chroma_store import SimilarDoc
    from riskagent_backend.skills import SkillStore

    llm_client = _make_mock_llm_client()
    chroma_store = _make_mock_chroma_store()
    store = SkillStore(llm_client=llm_client, chroma_store=chroma_store)

    skill1 = await store.create(_make_skill(name="向量匹配", summary="向量匹配工作流"))

    chroma_store.query_skills = MagicMock(return_value=[
        SimilarDoc(doc_id=skill1["skill_id"], similarity=0.9, document="向量匹配工作流", metadata={}),
    ])

    # 查询不含任何 skill 文本中的关键词 → BM25 返回空
    hits = await store.search("完全不匹配的查询文本", limit=5)
    assert len(hits) >= 1


@pytest.mark.asyncio
async def test_keyword_fallback_search_returns_normalized_scores():
    """测试 _keyword_fallback_search 输出归一化分数."""
    from riskagent_backend.skills import SkillStore

    store = SkillStore()
    await store.create(_make_skill(skill_id="skill_a", name="风险排查A", summary="风险排查工作流A"))
    await store.create(_make_skill(skill_id="skill_b", name="风险排查B", summary="风险排查"))

    hits = store._keyword_fallback_search(query="风险排查", limit=5, min_confidence=0.0)

    assert len(hits) >= 1
    for hit in hits:
        score = float(hit.get("bm25_score", 0.0))
        assert 0.0 <= score <= 1.0
    max_score = max(float(h.get("bm25_score", 0.0)) for h in hits)
    assert max_score == pytest.approx(1.0)
