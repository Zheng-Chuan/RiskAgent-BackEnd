"""
Skill 存储系统.

提供 Skill 的 CRUD 和语义检索能力.

RFC-005 需求一: Skill 语义索引迁移至 Chroma riskagent-skills collection.
- 当注入 LLMClient + ChromaVectorStore 时, 使用 Chroma 做 ANN 检索.
- 未注入时, 降级到 SemanticIndexer + 关键词兜底 (向后兼容).
- SemanticIndexer 仅作为 fallback, 记忆系统仍独立使用它.

设计约束:
- 多Agent架构不变量: Skill 系统是增强每个 Agent 的基础设施, 不替代多 Agent 协作.
- search() 签名不变, 上层调用方无感知.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Optional

from riskagent_backend.config import get_skill_hybrid_vector_weight
from riskagent_backend.memory.persistence_backend import PersistenceBackend
from riskagent_backend.memory.semantic_indexer import SemanticIndexer
from riskagent_backend.skills.skill_contract import (
    new_skill_id,
    validate_skill,
)

logger = logging.getLogger(__name__)


class SkillStore:
    """Skill 存储.

    提供分层能力:
    1. 内存存储: dict[skill_id, skill_dict]
    2. 语义检索: Chroma ANN (注入时) 或 SemanticIndexer fallback
    3. MySQL 持久化: 可选

    Args:
        redis_url: Redis URL (可选, 未使用).
        llm_client: LLM 客户端, 用于 embed() 生成 1536 维向量.
        chroma_store: Chroma 向量存储, 用于 riskagent-skills collection.
    """

    def __init__(
        self,
        redis_url: str | None = None,
        *,
        llm_client: Optional[Any] = None,
        chroma_store: Optional[Any] = None,
    ) -> None:
        self._store: dict[str, dict[str, Any]] = {}
        self._indexer: SemanticIndexer = SemanticIndexer()
        self._redis_url = redis_url
        self._persistence: PersistenceBackend | None = None
        self._llm_client = llm_client
        self._chroma_store = chroma_store

    @property
    def _chroma_enabled(self) -> bool:
        """是否启用 Chroma 向量检索路径."""
        return self._llm_client is not None and self._chroma_store is not None

    @property
    def persistence(self) -> PersistenceBackend:
        """获取持久化后端实例 (惰性初始化)."""
        if self._persistence is None:
            self._persistence = PersistenceBackend()
        return self._persistence

    def _set_persistence(self, backend: PersistenceBackend | None) -> None:
        """注入持久化后端 (测试用)."""
        self._persistence = backend

    # ==================== 内部工具 ====================

    def _build_skill_text(self, skill: dict[str, Any]) -> str:
        """构建 Skill 的语义文本, 用于向量化检索.

        优先使用 summary 字段（语义锡点）;
        如果 summary 不存在或为空（防御性处理），fallback 到全字段拼接.
        """
        summary = skill.get("summary")
        if isinstance(summary, str) and summary.strip():
            return summary.strip()

        parts: list[str] = []
        name = skill.get("name")
        if isinstance(name, str) and name.strip():
            parts.append(name.strip())
        for tag in skill.get("tags") or []:
            if isinstance(tag, str) and tag.strip():
                parts.append(tag.strip())
        for cond in skill.get("applicable_conditions") or []:
            if isinstance(cond, str) and cond.strip():
                parts.append(cond.strip())
        for step in skill.get("steps") or []:
            if isinstance(step, dict):
                desc = step.get("description")
                if isinstance(desc, str) and desc.strip():
                    parts.append(desc.strip())
                outcome = step.get("expected_outcome")
                if isinstance(outcome, str) and outcome.strip():
                    parts.append(outcome.strip())
        fb = skill.get("failure_boundary")
        if isinstance(fb, str) and fb.strip():
            parts.append(fb.strip())
        return " ".join(parts)

    def _build_indexable(self, skill: dict[str, Any]) -> dict[str, Any]:
        """将 Skill 转换为 SemanticIndexer 可索引的条目 (fallback 路径)."""
        return {
            "entry_id": str(skill.get("skill_id")),
            "kind": "semantic_case",
            "memory_type": "semantic",
            "scope": "shared",
            "content": {
                "snapshot_text": self._build_skill_text(skill),
            },
            "skill": dict(skill),
        }

    def _build_skill_metadata(self, skill: dict[str, Any]) -> dict[str, Any]:
        """构建 Chroma metadata, 用于过滤."""
        return {
            "skill_id": str(skill.get("skill_id", "")),
            "name": str(skill.get("name", "")),
            "status": str(skill.get("status", "")),
            "confidence": float(skill.get("confidence", 0.0)),
        }

    async def _index_skill(self, skill: dict[str, Any]) -> None:
        """索引 Skill 到语义索引器.

        Chroma 路径: LLMClient.embed(summary) → ChromaVectorStore.upsert_skill_embedding().
        Fallback 路径: SemanticIndexer.index_entry().
        """
        if self._chroma_enabled:
            try:
                skill_id = str(skill.get("skill_id", ""))
                text = self._build_skill_text(skill)
                if not text.strip():
                    return
                embedding = await self._llm_client.embed(text)
                metadata = self._build_skill_metadata(skill)
                self._chroma_store.upsert_skill_embedding(
                    skill_id=skill_id,
                    embedding=embedding,
                    document=text,
                    metadata=metadata,
                )
                return
            except Exception as exc:
                logger.warning(
                    "Chroma upsert failed for skill %s, falling back to SemanticIndexer: %s",
                    skill.get("skill_id"),
                    exc,
                )
        # Fallback: SemanticIndexer
        await self._indexer.index_entry(self._build_indexable(skill))

    async def _reindex(self, skill: dict[str, Any]) -> None:
        """重新索引 Skill (更新时调用)."""
        await self._index_skill(skill)

    # ==================== CRUD ====================

    async def create(self, skill: dict[str, Any]) -> dict[str, Any]:
        """创建 Skill.

        流程: 验证 -> 生成 skill_id -> 存储 -> 索引 -> 异步落盘 -> 返回.
        """
        validated = validate_skill(skill)
        skill_id = validated["skill_id"]
        self._store[skill_id] = validated
        await self._index_skill(validated)
        # 异步落盘到 MySQL (fire-and-forget)
        asyncio.ensure_future(self.persistence.persist_skill(validated))
        return dict(validated)

    async def get(self, skill_id: str) -> dict[str, Any] | None:
        """获取 Skill."""
        skill = self._store.get(skill_id)
        return dict(skill) if skill is not None else None

    async def update(self, skill_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        """更新 Skill.

        合并 patch -> 保留 skill_id 和 created_at -> 刷新 updated_at -> 重新索引 -> 异步落盘.
        """
        existing = self._store.get(skill_id)
        if existing is None:
            raise KeyError(f"Skill not found: {skill_id}")
        merged = dict(existing)
        merged.update(patch)
        # 保留不可变字段
        merged["skill_id"] = skill_id
        merged["created_at"] = existing["created_at"]
        merged["updated_at"] = int(time.time() * 1000)
        # 防御性填充: 旧数据 summary 为空时, 用 name 作为 fallback,
        # 避免 summary 必填校验破坏 update() 操作 (RFC-005 兼容性修复)
        if not str(merged.get("summary") or "").strip():
            merged["summary"] = str(merged.get("name") or "unnamed_skill")
        validated = validate_skill(merged)
        self._store[skill_id] = validated
        await self._reindex(validated)
        # 异步落盘到 MySQL (fire-and-forget)
        asyncio.ensure_future(self.persistence.persist_skill(validated))
        return dict(validated)

    async def delete(self, skill_id: str) -> bool:
        """删除 Skill."""
        if skill_id not in self._store:
            return False
        del self._store[skill_id]
        self._indexer.index.pop(skill_id, None)
        # Chroma 路径: 同步删除向量
        if self._chroma_enabled:
            try:
                self._chroma_store.delete_skill_embedding(skill_id=skill_id)
            except Exception as exc:
                logger.warning("Chroma delete failed for skill %s: %s", skill_id, exc)
        return True

    async def list_all(
        self, *, status: str | None = None, tag: str | None = None
    ) -> list[dict[str, Any]]:
        """列出所有 Skill, 支持按 status 和 tag 过滤."""
        results: list[dict[str, Any]] = []
        for skill in self._store.values():
            if status is not None and skill.get("status") != status:
                continue
            if tag is not None and tag not in (skill.get("tags") or []):
                continue
            results.append(dict(skill))
        return results

    # ==================== 语义检索 ====================

    async def _semantic_search(self, query: str, *, limit: int = 10) -> list[dict[str, Any]]:
        """统一语义检索入口.

        Chroma 路径: LLMClient.embed(query) → ChromaVectorStore.query_skills() → 从内存查回 skill.
        Fallback 路径: SemanticIndexer.search().

        返回格式与 SemanticIndexer.search() 一致:
        [{"skill": skill_dict, "semantic_score": float, ...}]
        """
        if self._chroma_enabled:
            try:
                query_embedding = await self._llm_client.embed(query)
                similar_docs = self._chroma_store.query_skills(
                    query_embedding=query_embedding,
                    top_k=limit,
                )
                hits: list[dict[str, Any]] = []
                for doc in similar_docs:
                    skill = self._store.get(doc.doc_id)
                    if not isinstance(skill, dict):
                        continue
                    hits.append({
                        "skill": dict(skill),
                        "semantic_score": float(doc.similarity),
                    })
                return hits
            except Exception as exc:
                logger.warning("Chroma query failed, falling back to SemanticIndexer: %s", exc)
        # Fallback: SemanticIndexer
        return await self._indexer.search(query, limit=limit)

    # ==================== Hybrid 检索 (RFC-005 需求四) ====================

    @staticmethod
    def _normalize_scores(scores: list[float]) -> list[float]:
        """将分数列表归一化到 [0, 1] 区间.

        归一化方式: score / max_score (如果 max_score > 0), 否则所有分数为 0.
        """
        if not scores:
            return []
        max_score = max(scores)
        if max_score <= 0:
            return [0.0] * len(scores)
        return [s / max_score for s in scores]

    def _merge_hybrid_results(
        self,
        vector_hits: list[dict[str, Any]],
        bm25_hits: list[dict[str, Any]],
        alpha: float,
    ) -> list[dict[str, Any]]:
        """加权合并向量检索和 BM25 检索结果.

        final_score = alpha * norm_vector_score + (1-alpha) * norm_bm25_score
        去重: 以 skill_id 为 key, 合并两个通道的分数.
        """
        # 归一化向量分数
        vector_scores = self._normalize_scores(
            [float(h.get("semantic_score", 0.0)) for h in vector_hits]
        )
        # 归一化 BM25 分数
        bm25_scores = self._normalize_scores(
            [float(h.get("bm25_score", 0.0)) for h in bm25_hits]
        )

        merged: dict[str, dict[str, Any]] = {}

        # 处理向量检索结果
        for i, hit in enumerate(vector_hits):
            skill = hit.get("skill")
            if not isinstance(skill, dict):
                continue
            skill_id = str(skill.get("skill_id") or "")
            if not skill_id:
                continue
            norm_v = vector_scores[i]
            final = alpha * norm_v
            result = dict(skill)
            result["semantic_score"] = final
            result["vector_score"] = norm_v
            result["bm25_score"] = 0.0
            merged[skill_id] = result

        # 处理 BM25 检索结果
        for i, hit in enumerate(bm25_hits):
            skill_id = str(hit.get("skill_id") or "")
            if not skill_id:
                continue
            norm_b = bm25_scores[i]
            bm25_contribution = (1.0 - alpha) * norm_b
            existing = merged.get(skill_id)
            if existing is not None:
                # 同一 Skill 在两个通道都出现: 合并分数
                existing["bm25_score"] = norm_b
                existing["semantic_score"] = (
                    float(existing["semantic_score"]) + bm25_contribution
                )
            else:
                # 仅 BM25 通道命中
                result = dict(hit)
                result["semantic_score"] = bm25_contribution
                result["vector_score"] = 0.0
                result["bm25_score"] = norm_b
                merged[skill_id] = result

        return list(merged.values())

    async def search(
        self, query: str, *, limit: int = 5, min_confidence: float = 0.0
    ) -> list[dict[str, Any]]:
        """Hybrid 检索 Skill.

        RFC-005 需求四: 向量检索 + BM25 检索, 加权合并后排序返回.
        final_score = alpha * norm_vector_score + (1-alpha) * norm_bm25_score
        alpha 可通过 SKILL_HYBRID_VECTOR_WEIGHT 环境变量配置 (默认 0.7).
        alpha=1.0 禁用 BM25 (纯向量), alpha=0.0 禁用向量 (纯 BM25).
        过滤 status != "active" 和 confidence < min_confidence 的结果.
        """
        query_text = str(query or "").strip()
        if not query_text:
            return []

        alpha = get_skill_hybrid_vector_weight()
        # 钳制到 [0.0, 1.0]
        alpha = max(0.0, min(1.0, alpha))

        # 向量检索通道 (alpha=0.0 时禁用)
        vector_hits: list[dict[str, Any]] = []
        if alpha > 0.0:
            raw_vector_hits = await self._semantic_search(query_text, limit=limit)
            for hit in raw_vector_hits:
                skill = hit.get("skill")
                if not isinstance(skill, dict):
                    continue
                if skill.get("status") != "active":
                    continue
                if float(skill.get("confidence", 0.0)) < min_confidence:
                    continue
                vector_hits.append(hit)

        # BM25 检索通道 (alpha=1.0 时禁用)
        bm25_hits: list[dict[str, Any]] = []
        if alpha < 1.0:
            bm25_hits = self._keyword_fallback_search(
                query=query_text,
                limit=limit,
                min_confidence=min_confidence,
            )

        # 加权合并、排序、截断
        merged = self._merge_hybrid_results(vector_hits, bm25_hits, alpha)
        ranked_results = sorted(
            merged,
            key=lambda item: float(item.get("semantic_score", 0.0)),
            reverse=True,
        )
        return ranked_results[: max(0, limit)]

    async def find_similar(
        self, skill: dict[str, Any], threshold: float = 0.85
    ) -> list[dict[str, Any]]:
        """检查是否已存在语义相似的 Skill.

        用于 SkillProposer 决定创建还是更新.
        不排除任何 status 的 Skill (包括 deprecated/archived).
        """
        text = self._build_skill_text(skill)
        if not text.strip():
            return []
        hits = await self._semantic_search(text, limit=20)
        results: list[dict[str, Any]] = []
        for hit in hits:
            hit_skill = hit.get("skill")
            if not isinstance(hit_skill, dict):
                continue
            # 排除自身
            if hit_skill.get("skill_id") == skill.get("skill_id"):
                continue
            score = float(hit.get("semantic_score", 0.0))
            if score >= threshold:
                result = dict(hit_skill)
                result["semantic_score"] = score
                results.append(result)
        return results

    # ==================== 置信度更新 ====================

    async def update_confidence(
        self, skill_id: str, success: bool, *, delta: float = 0.05
    ) -> dict[str, Any]:
        """更新 Skill 置信度.

        成功: confidence = min(1.0, confidence + delta), usage_count += 1
        失败: confidence = max(0.0, confidence - delta), usage_count += 1
        重新计算 success_rate.
        如果 confidence < 0.3: status = "deprecated"
        如果 confidence < 0.15: status = "archived"
        """
        existing = self._store.get(skill_id)
        if existing is None:
            raise KeyError(f"Skill not found: {skill_id}")

        current_confidence = float(existing.get("confidence", 0.5))
        current_usage = int(existing.get("usage_count", 0))
        current_success_rate = float(existing.get("success_rate", 0.0))

        # 计算历史成功次数
        if current_usage > 0:
            historical_successes = round(current_success_rate * current_usage)
        else:
            historical_successes = 0

        new_usage = current_usage + 1
        new_successes = historical_successes + (1 if success else 0)
        new_success_rate = new_successes / new_usage

        if success:
            new_confidence = min(1.0, current_confidence + delta)
        else:
            new_confidence = max(0.0, current_confidence - delta)

        updated = dict(existing)
        updated["confidence"] = new_confidence
        updated["usage_count"] = new_usage
        updated["success_rate"] = new_success_rate
        updated["updated_at"] = int(time.time() * 1000)

        # 自动降级
        if new_confidence < 0.15:
            updated["status"] = "archived"
        elif new_confidence < 0.3:
            updated["status"] = "deprecated"

        self._store[skill_id] = updated
        await self._reindex(updated)
        return dict(updated)

    # ==================== 持久化 ====================

    async def flush_to_persistence(self) -> int:
        """批量落盘所有 Skill 到 MySQL.

        Returns:
            成功落盘的条目数
        """
        all_skills = list(self._store.values())
        if not all_skills:
            return 0
        count = 0
        for skill in all_skills:
            ok = await self.persistence.persist_skill(skill)
            if ok:
                count += 1
        return count

    async def restore_from_persistence(self) -> int:
        """从 MySQL 加载所有 Skill 到内存.

        Chroma 路径: 加载后重新生成 embedding 写入 Chroma (重建索引).
        Fallback 路径: 重建 SemanticIndexer 索引.

        Returns:
            恢复的 Skill 数量
        """
        skills = await self.persistence.load_skills()
        if not skills:
            return 0
        for skill in skills:
            skill_id = skill.get("skill_id")
            if skill_id:
                self._store[skill_id] = skill
                await self._index_skill(skill)
        return len(skills)

    def _keyword_fallback_search(
        self,
        *,
        query: str,
        limit: int,
        min_confidence: float,
    ) -> list[dict[str, Any]]:
        """BM25 关键词检索通道.

        RFC-005 需求四: 从"兜底补全"升级为 BM25 检索通道.
        输出归一化分数 (bm25_score), 范围 [0, 1].
        归一化方式: score / max_score (如果 max_score > 0), 否则所有分数为 0.
        """
        query_text = str(query or "").strip().lower()
        if not query_text:
            return []
        candidates: list[tuple[float, dict[str, Any]]] = []
        query_tokens = [token for token in query_text.split() if token]
        for skill_id, skill in self._store.items():
            if skill.get("status") != "active":
                continue
            if float(skill.get("confidence", 0.0)) < min_confidence:
                continue
            haystack = self._build_skill_text(skill).lower()
            if not haystack:
                continue
            score = 0.0
            if query_text in haystack:
                score += len(query_text) * 2
            for token in query_tokens:
                if token in haystack:
                    score += len(token)
            if score <= 0:
                continue
            result = dict(skill)
            result["bm25_score"] = score
            candidates.append((score, result))
        candidates.sort(key=lambda item: item[0], reverse=True)
        top_hits = [item[1] for item in candidates[: max(0, limit)]]

        # 归一化分数到 [0, 1] 区间
        raw_scores = [float(h.get("bm25_score", 0.0)) for h in top_hits]
        normalized_scores = self._normalize_scores(raw_scores)
        for i, hit in enumerate(top_hits):
            hit["bm25_score"] = normalized_scores[i]

        return top_hits

    # ==================== 健康检查 ====================

    async def health_check(self) -> bool:
        """健康检查."""
        return True
