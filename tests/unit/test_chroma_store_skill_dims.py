"""ChromaVectorStore Skill 向量维度自愈测试.

embedding 模型切换导致维度变化 (如 1536→1024) 时,
upsert_skill_embedding 应删除并重建 collection 后重试一次.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest


_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SRC_ROOT = _PROJECT_ROOT / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

from riskagent_backend.knowledge.chroma_store import ChromaVectorStore  # noqa: E402


def _make_store(collections: list[MagicMock]) -> ChromaVectorStore:
    """构造 store, _skills_collection 依次返回给定 collection mock."""
    store = ChromaVectorStore()
    store._skills_collection = MagicMock(side_effect=collections)  # type: ignore[method-assign]
    client = MagicMock()
    store._client = MagicMock(return_value=client)  # type: ignore[method-assign]
    return store


def test_upsert_rebuilds_collection_on_dimension_mismatch() -> None:
    """维度不匹配时删除旧 collection 并用新 collection 重试成功."""
    old_col = MagicMock()
    old_col.upsert.side_effect = Exception(
        "Dimensionality of results (1024) does not match dimensionality of collection (1536)"
    )
    new_col = MagicMock()
    store = _make_store([old_col, new_col])

    store.upsert_skill_embedding(
        skill_id="skill-1",
        embedding=[0.1] * 1024,
        document="summary",
        metadata={"skill_id": "skill-1"},
    )

    # 旧 collection 尝试过一次, 新 collection 成功写入
    assert old_col.upsert.call_count == 1
    assert new_col.upsert.call_count == 1
    # 触发了 collection 删除重建
    store._client().delete_collection.assert_called_once()


def test_upsert_propagates_non_dimension_error() -> None:
    """非维度错误直接抛出, 不触发重建."""
    col = MagicMock()
    col.upsert.side_effect = RuntimeError("connection refused")
    store = _make_store([col])

    with pytest.raises(RuntimeError, match="connection refused"):
        store.upsert_skill_embedding(
            skill_id="skill-1",
            embedding=[0.1] * 4,
            document="summary",
            metadata={},
        )

    store._client().delete_collection.assert_not_called()


def test_upsert_success_without_rebuild() -> None:
    """正常写入不触发重建."""
    col = MagicMock()
    store = _make_store([col])

    store.upsert_skill_embedding(
        skill_id="skill-1",
        embedding=[0.1] * 1024,
        document="summary",
        metadata={"skill_id": "skill-1"},
    )

    assert col.upsert.call_count == 1
    store._client().delete_collection.assert_not_called()
