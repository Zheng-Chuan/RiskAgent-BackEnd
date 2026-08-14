from __future__ import annotations

import math
import re
import time
import warnings
from dataclasses import dataclass
from typing import Any

from riskagent_backend import config
from riskagent_backend.observability.metrics import inc_counter, observe_ms

_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")


def _tokenize(text: str) -> list[str]:
    if not text:
        return []
    return [t.lower() for t in _TOKEN_RE.findall(text)]


def embed_text_dense(text: str, *, dims: int = 256) -> list[float]:
    tokens = _tokenize(text)
    vec = [0.0] * int(dims)
    if not tokens:
        return vec
    for tok in tokens:
        idx = hash(tok) % dims
        vec[idx] += 1.0
    norm = math.sqrt(sum(v * v for v in vec))
    if norm <= 0.0:
        return vec
    return [v / norm for v in vec]


@dataclass(frozen=True)
class SimilarDoc:
    doc_id: str
    similarity: float
    document: str
    metadata: dict[str, Any]


class ChromaVectorStore:
    def __init__(
        self,
        *,
        collection: str | None = None,
        dims: int = 256,
    ) -> None:
        self._dims = int(dims)
        self._collection_name = (collection or config.get_chroma_collection()).strip() or config.get_chroma_collection()

    def _client(self):
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                message=r"Deprecated call to `pkg_resources\.declare_namespace\(.+\)`\.",
                category=DeprecationWarning,
            )
            import chromadb

        persist_dir = config.get_chroma_persist_dir()
        if persist_dir:
            return chromadb.PersistentClient(path=persist_dir)
        return chromadb.HttpClient(host=config.get_chroma_host(), port=config.get_chroma_port())

    def _collection(self):
        client = self._client()
        return client.get_or_create_collection(
            name=self._collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def upsert_alert(self, *, alert_id: str, document: str, metadata: dict[str, Any]) -> None:
        started = time.monotonic()
        col = self._collection()
        embedding = embed_text_dense(document, dims=self._dims)
        col.upsert(
            ids=[alert_id],
            documents=[document],
            metadatas=[metadata],
            embeddings=[embedding],
        )
        observe_ms("rm_chroma_upsert", (time.monotonic() - started) * 1000.0, labels={"collection": self._collection_name})
        inc_counter("rm_chroma_upserts_total", labels={"collection": self._collection_name})

    def query_alerts(self, *, query_text: str, top_k: int = 5) -> list[SimilarDoc]:
        q = (query_text or "").strip()
        if not q:
            return []
        k = max(1, int(top_k))
        started = time.monotonic()
        qemb = embed_text_dense(q, dims=self._dims)
        col = self._collection()
        out = col.query(
            query_embeddings=[qemb],
            n_results=k,
            include=["metadatas", "documents", "distances"],
        )
        ids = (out.get("ids") or [[]])[0]
        docs = (out.get("documents") or [[]])[0]
        metas = (out.get("metadatas") or [[]])[0]
        dists = (out.get("distances") or [[]])[0]

        results: list[SimilarDoc] = []
        for i in range(min(len(ids), len(docs), len(metas), len(dists))):
            doc_id = str(ids[i])
            doc = str(docs[i] or "")
            meta = metas[i] if isinstance(metas[i], dict) else {}
            dist = float(dists[i]) if dists[i] is not None else 1.0
            similarity = max(0.0, min(1.0, 1.0 - dist))
            results.append(SimilarDoc(doc_id=doc_id, similarity=similarity, document=doc, metadata=meta))
        observe_ms("rm_chroma_query", (time.monotonic() - started) * 1000.0, labels={"collection": self._collection_name})
        inc_counter("rm_chroma_queries_total", labels={"collection": self._collection_name})
        inc_counter("rm_chroma_hits_total", labels={"collection": self._collection_name}, value=len(results))
        return results

    # ==================== Skill 向量存储 ====================

    def _skills_collection(self):
        """获取或创建 riskagent-skills collection."""
        client = self._client()
        skills_name = config.get_chroma_skills_collection()
        return client.get_or_create_collection(
            name=skills_name,
            metadata={"hnsw:space": "cosine"},
        )

    def upsert_skill_embedding(
        self,
        *,
        skill_id: str,
        embedding: list[float],
        document: str,
        metadata: dict[str, Any],
    ) -> None:
        """写入或更新 Skill 向量到 riskagent-skills collection.

        embedding 由外部 LLMClient.embed() 生成 (当前 BAAI/bge-m3 为 1024 维),
        非内部 embed_text_dense 计算.

        维度自愈: embedding 模型切换导致维度变化 (如 1536→1024) 时,
        旧 collection 与新向量维度不匹配, 删除并重建 collection 后重试一次.
        向量可从 MySQL 源数据经 restore_from_persistence() 全量重建, 无数据损失.
        """
        started = time.monotonic()
        col = self._skills_collection()
        try:
            col.upsert(
                ids=[skill_id],
                documents=[document],
                metadatas=[metadata],
                embeddings=[embedding],
            )
        except Exception as exc:  # noqa: BLE001 - 维度错误需自愈重试
            if "dimension" not in str(exc).lower():
                raise
            self._reset_skills_collection(reason=str(exc))
            col = self._skills_collection()
            col.upsert(
                ids=[skill_id],
                documents=[document],
                metadatas=[metadata],
                embeddings=[embedding],
            )
        skills_name = config.get_chroma_skills_collection()
        observe_ms("rm_chroma_upsert", (time.monotonic() - started) * 1000.0, labels={"collection": skills_name})
        inc_counter("rm_chroma_upserts_total", labels={"collection": skills_name})

    def _reset_skills_collection(self, *, reason: str) -> None:
        """删除并重建 riskagent-skills collection (维度不匹配时的自愈路径)."""
        client = self._client()
        skills_name = config.get_chroma_skills_collection()
        try:
            client.delete_collection(skills_name)
        except Exception:  # noqa: BLE001 - collection 不存在时忽略
            pass
        inc_counter("rm_chroma_collection_resets_total", labels={"collection": skills_name, "reason": "dimension_mismatch"})
        _ = reason  # 保留 reason 参数便于后续接入日志/告警

    def query_skills(
        self,
        *,
        query_embedding: list[float],
        top_k: int = 5,
    ) -> list[SimilarDoc]:
        """ANN 检索 riskagent-skills collection, 返回 Top-K 相似 Skill.

        query_embedding 由外部 LLMClient.embed() 生成.
        """
        k = max(1, int(top_k))
        started = time.monotonic()
        col = self._skills_collection()
        out = col.query(
            query_embeddings=[query_embedding],
            n_results=k,
            include=["metadatas", "documents", "distances"],
        )
        ids = (out.get("ids") or [[]])[0]
        docs = (out.get("documents") or [[]])[0]
        metas = (out.get("metadatas") or [[]])[0]
        dists = (out.get("distances") or [[]])[0]

        results: list[SimilarDoc] = []
        for i in range(min(len(ids), len(docs), len(metas), len(dists))):
            doc_id = str(ids[i])
            doc = str(docs[i] or "")
            meta = metas[i] if isinstance(metas[i], dict) else {}
            dist = float(dists[i]) if dists[i] is not None else 1.0
            similarity = max(0.0, min(1.0, 1.0 - dist))
            results.append(SimilarDoc(doc_id=doc_id, similarity=similarity, document=doc, metadata=meta))
        skills_name = config.get_chroma_skills_collection()
        observe_ms("rm_chroma_query", (time.monotonic() - started) * 1000.0, labels={"collection": skills_name})
        inc_counter("rm_chroma_queries_total", labels={"collection": skills_name})
        inc_counter("rm_chroma_hits_total", labels={"collection": skills_name}, value=len(results))
        return results

    def delete_skill_embedding(self, *, skill_id: str) -> None:
        """从 riskagent-skills collection 删除指定 Skill 向量."""
        started = time.monotonic()
        col = self._skills_collection()
        col.delete(ids=[skill_id])
        skills_name = config.get_chroma_skills_collection()
        observe_ms("rm_chroma_delete", (time.monotonic() - started) * 1000.0, labels={"collection": skills_name})
        inc_counter("rm_chroma_deletes_total", labels={"collection": skills_name})
