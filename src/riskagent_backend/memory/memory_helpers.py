"""
记忆系统辅助函数模块.

包含 Agent 身份解析、文本处理、快照构建等无状态辅助函数.
"""

from __future__ import annotations

import json
import re
from typing import Any

from riskagent_backend.memory.semantic_indexer import _make_json_safe


# ==================== 常量 ====================

_DEFAULT_PRIVATE_AGENT_IDS = (
    "orchestrator",
    "system_engineer",
    "risk_analyst",
    "critic",
)

_CANONICAL_AGENT_IDS = {
    "engineer": "system_engineer",
    "system_engineer": "system_engineer",
    "analyst": "risk_analyst",
    "risk_analyst": "risk_analyst",
    "orchestrator": "orchestrator",
    "critic": "critic",
    "intent": "intent",
}

_AGENT_PERSPECTIVES = {
    "system_engineer": "system_reliability",
    "risk_analyst": "business_risk",
    "orchestrator": "global_planning",
    "critic": "quality_gate",
    "intent": "intent_resolution",
}

_ASCII_TOKEN_PATTERN = re.compile(r"[a-z0-9_]{2,}")
_CJK_TOKEN_PATTERN = re.compile(r"[\u4e00-\u9fff]{2,}")
_STOPWORDS = {
    "and", "the", "for", "with", "from", "into", "then", "task", "risk", "query",
    "分析", "查询", "处理", "任务", "然后", "需要", "进行", "当前", "相关", "一个",
}


# ==================== Agent 身份解析 ====================


def canonical_agent_id(agent_id: Any) -> str | None:
    """解析 Agent 标准 ID."""
    if not isinstance(agent_id, str) or not agent_id.strip():
        return None
    return _CANONICAL_AGENT_IDS.get(agent_id.strip(), agent_id.strip())


def agent_perspective(agent_id: str) -> str:
    """获取 Agent 的视角标签."""
    cid = canonical_agent_id(agent_id) or "orchestrator"
    return _AGENT_PERSPECTIVES.get(cid, cid)


# ==================== 文本处理 ====================


def extract_content_text(task: dict[str, Any]) -> str:
    """从任务中提取内容文本."""
    payload = task.get("payload") if isinstance(task.get("payload"), dict) else {}
    content = payload.get("content")
    if isinstance(content, str) and content.strip():
        return content.strip()
    return str(task.get("task_id") or "").strip()


def extract_confidence(node_result: dict[str, Any] | None) -> float:
    """提取置信度."""
    if not isinstance(node_result, dict):
        return 1.0
    output = node_result.get("output") if isinstance(node_result.get("output"), dict) else {}
    value = output.get("confidence")
    if isinstance(value, (int, float)):
        return min(1.0, max(0.0, float(value)))
    return 1.0


def compact_output_text(payload: Any) -> str:
    """压缩输出为简短文本."""
    if isinstance(payload, dict):
        for key in ("summary", "report", "text", "reason"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return json.dumps(_make_json_safe(payload), ensure_ascii=False, sort_keys=True)[:200]
    if isinstance(payload, str):
        return payload[:200]
    return ""


def make_json_safe(value: Any) -> Any:
    """确保值可以安全 JSON 序列化(公开接口)."""
    return _make_json_safe(value)


# ==================== 快照构建 ====================


def build_private_task_snapshot(
    *,
    agent_id: str,
    task: dict[str, Any],
    trace_entry: dict[str, Any],
    node_result: dict[str, Any],
) -> dict[str, Any]:
    """构建 Agent 私有任务快照."""
    output = node_result.get("output") if isinstance(node_result.get("output"), dict) else {}
    current_progress = str(trace_entry.get("status") or "unknown")
    observation = compact_output_text(output) or compact_output_text(node_result)
    error = trace_entry.get("error") if isinstance(trace_entry.get("error"), str) else ""
    open_questions = [error] if error else []
    next_action = "continue"
    if current_progress == "blocked":
        next_action = "wait_for_resume"
    elif current_progress == "failed":
        next_action = "replan_or_retry"
    elif current_progress == "completed":
        next_action = "handoff_to_next_step"
    role = canonical_agent_id(agent_id) or agent_id
    task_goal = extract_content_text(task)
    recent_observations = [item for item in [observation] if item]
    snapshot_text = (
        f"role={role} goal={task_goal[:80]} progress={current_progress} "
        f"observation={(observation or 'none')[:120]} next={next_action}"
    )
    return {
        "role": role,
        "task_goal": task_goal,
        "current_progress": current_progress,
        "open_questions": open_questions,
        "recent_observations": recent_observations,
        "next_intended_action": next_action,
        "snapshot_text": snapshot_text,
    }


# ==================== 记忆摘要与分析 ====================


def build_planning_query(*, content: str, intent_type: str | None) -> str:
    """构建规划查询."""
    parts = [content.strip()]
    if isinstance(intent_type, str) and intent_type.strip():
        parts.append(intent_type.strip())
    return " ".join(part for part in parts if part)


def _tokenize_relevance_text(value: Any) -> set[str]:
    """提取轻量相关性 token."""
    if not isinstance(value, str) or not value.strip():
        return set()
    normalized = value.strip().lower()
    tokens = set(_ASCII_TOKEN_PATTERN.findall(normalized))
    tokens.update(_CJK_TOKEN_PATTERN.findall(value))
    return {token for token in tokens if token and token not in _STOPWORDS}


def _collect_hit_relevance_tokens(hit: dict[str, Any]) -> set[str]:
    """从记忆命中中提取相关性 token."""
    tokens: set[str] = set()
    for key in ("kind", "memory_type", "source", "agent_role", "agent_perspective"):
        tokens.update(_tokenize_relevance_text(str(hit.get(key) or "")))

    content = hit.get("content") if isinstance(hit.get("content"), dict) else {}
    for key in ("text", "decision_pattern", "snapshot_text"):
        tokens.update(_tokenize_relevance_text(content.get(key)))

    for key in ("applicable_conditions", "failure_boundary", "tags", "evidence_refs"):
        values = content.get(key)
        if not isinstance(values, list):
            values = hit.get(key)
        if isinstance(values, list):
            for item in values:
                tokens.update(_tokenize_relevance_text(str(item)))

    reusable_snippet = hit.get("reusable_snippet")
    if isinstance(reusable_snippet, dict):
        for value in reusable_snippet.values():
            if isinstance(value, list):
                for item in value:
                    tokens.update(_tokenize_relevance_text(str(item)))
            else:
                tokens.update(_tokenize_relevance_text(str(value)))
    return tokens


def annotate_memory_hits_for_planning(
    *,
    hits: list[dict[str, Any]],
    content: str,
    intent_type: str | None,
    session_id: str | None,
) -> list[dict[str, Any]]:
    """为规划阶段命中增加相关性评分与使用决策."""
    query_tokens = _tokenize_relevance_text(content)
    if isinstance(intent_type, str) and intent_type.strip():
        query_tokens.update(_tokenize_relevance_text(intent_type))

    annotated: list[dict[str, Any]] = []
    for raw_hit in hits:
        hit = dict(raw_hit)
        hit_tokens = _collect_hit_relevance_tokens(hit)
        overlap = sorted(query_tokens & hit_tokens)
        score = 0.0
        reasons: list[str] = []

        if overlap:
            score += min(0.55, 0.18 * len(overlap))
            reasons.append(f"keyword_overlap:{','.join(overlap[:4])}")

        if isinstance(intent_type, str) and intent_type.strip():
            lowered_intent = intent_type.strip().lower()
            if lowered_intent in {token.lower() for token in hit_tokens}:
                score += 0.25
                reasons.append(f"intent_match:{intent_type}")

        if session_id and hit.get("session_id") == session_id:
            score += 0.12
            reasons.append("same_session")

        semantic_score = hit.get("semantic_score")
        if isinstance(semantic_score, (int, float)) and semantic_score > 0:
            score += min(0.2, float(semantic_score) * 0.2)
            reasons.append("semantic_score")

        score = round(min(1.0, score), 4)
        threshold = 0.3
        hit["relevance_score"] = score
        hit["relevance_reasons"] = reasons
        hit["used_for_planning"] = score >= threshold
        hit["relevance_bucket"] = (
            "high" if score >= 0.6 else "medium" if score >= threshold else "low"
        )
        annotated.append(hit)

    annotated.sort(
        key=lambda item: (
            float(item.get("relevance_score") or 0.0),
            float(item.get("semantic_score") or 0.0),
        ),
        reverse=True,
    )
    return annotated


def dedupe_memory_hits(hits: list[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    """对记忆命中去重."""
    seen: set[str] = set()
    results: list[dict[str, Any]] = []
    for hit in hits:
        entry_id = hit.get("entry_id")
        if not isinstance(entry_id, str) or not entry_id:
            continue
        if entry_id in seen:
            continue
        seen.add(entry_id)
        results.append(hit)
        if len(results) >= limit:
            break
    return results


def summarize_hits(hits: list[dict[str, Any]]) -> dict[str, Any]:
    """汇总记忆命中."""
    lines: list[str] = []
    for hit in hits:
        kind = hit.get("kind", "unknown")
        memory_type = hit.get("memory_type", "episodic")
        content = hit.get("content") if isinstance(hit.get("content"), dict) else {}
        text = content.get("text")
        if not isinstance(text, str) or not text.strip():
            text = str(content)[:120]
        lines.append(f"[{memory_type}/{kind}] {text[:120]}")
    return {
        "hit_count": len(hits),
        "texts": lines,
        "memory_hits": [
            {
                "entry_id": hit.get("entry_id"),
                "memory_type": hit.get("memory_type"),
                "kind": hit.get("kind"),
                "trace_ref": hit.get("trace_ref"),
                "semantic_score": hit.get("semantic_score"),
                "reusable_snippet": hit.get("reusable_snippet"),
                "relevance_score": hit.get("relevance_score"),
                "relevance_bucket": hit.get("relevance_bucket"),
                "used_for_planning": hit.get("used_for_planning"),
            }
            for hit in hits
        ],
    }


def to_shared_board_row(entry: dict[str, Any]) -> dict[str, Any] | None:
    """将条目转换为共享面板行."""
    if str(entry.get("scope") or "shared") != "shared":
        return None
    content = entry.get("content") if isinstance(entry.get("content"), dict) else {}
    text = content.get("text")
    if not isinstance(text, str) or not text.strip():
        text = compact_output_text(content)
    agent_role = canonical_agent_id(entry.get("agent_role") or entry.get("agent_id"))
    if not agent_role:
        return None
    return {
        "entry_id": entry.get("entry_id"),
        "agent_role": agent_role,
        "agent_perspective": entry.get("agent_perspective") or agent_perspective(agent_role),
        "task_phase": entry.get("task_phase") or "execution",
        "confidence": float(entry.get("confidence") or 0.0),
        "trace_ref": entry.get("trace_ref") if isinstance(entry.get("trace_ref"), dict) else {},
        "summary_text": text[:160] if isinstance(text, str) else "",
        "kind": entry.get("kind"),
        "memory_type": entry.get("memory_type"),
    }


def summarize_shared_board(board: list[dict[str, Any]]) -> dict[str, Any]:
    """汇总共享面板."""
    by_role: dict[str, int] = {}
    for row in board:
        role = str(row.get("agent_role") or "unknown")
        by_role[role] = by_role.get(role, 0) + 1
    return {
        "item_count": len(board),
        "by_role": by_role,
        "latest": board[:5],
    }


def summarize_private_memory(
    private_memory_state: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    """汇总私有记忆状态."""
    summary: dict[str, Any] = {}
    for agent_id_key, entries in private_memory_state.items():
        latest = entries[0] if entries else {}
        content = latest.get("content") if isinstance(latest.get("content"), dict) else {}
        summary[agent_id_key] = {
            "count": len(entries),
            "role": content.get("role") or agent_id_key,
            "current_progress": content.get("current_progress"),
            "next_intended_action": content.get("next_intended_action"),
        }
    return summary


def estimate_role_drift(
    *,
    shared_board: list[dict[str, Any]],
    private_memory_state: dict[str, list[dict[str, Any]]],
) -> float:
    """估算角色漂移率."""
    total = 0
    drift = 0
    for row in shared_board:
        total += 1
        role = canonical_agent_id(row.get("agent_role"))
        perspective = row.get("agent_perspective")
        if role and perspective != agent_perspective(role):
            drift += 1
    for aid, entries in private_memory_state.items():
        for entry in entries:
            total += 1
            content = entry.get("content") if isinstance(entry.get("content"), dict) else {}
            if canonical_agent_id(content.get("role")) != canonical_agent_id(aid):
                drift += 1
    return round(drift / total, 4) if total else 0.0


def estimate_memory_cross_talk(
    *,
    private_memory_state: dict[str, list[dict[str, Any]]],
) -> float:
    """估算记忆串扰率."""
    total = 0
    cross_talk = 0
    for aid, entries in private_memory_state.items():
        for entry in entries:
            total += 1
            if canonical_agent_id(entry.get("agent_id")) != canonical_agent_id(aid):
                cross_talk += 1
    return round(cross_talk / total, 4) if total else 0.0


def extract_few_shot_examples(hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """从命中中提取 few-shot 示例."""
    examples: list[dict[str, Any]] = []
    for hit in hits:
        snippet = hit.get("reusable_snippet")
        if not isinstance(snippet, dict):
            continue
        examples.append(
            {
                "entry_id": hit.get("entry_id"),
                "decision_pattern": snippet.get("decision_pattern"),
                "failure_boundary": snippet.get("failure_boundary"),
                "applicable_conditions": snippet.get("applicable_conditions"),
            }
        )
    return examples


def derive_summary_text(*, final_output: dict[str, Any]) -> str:
    """从最终输出推导摘要文本."""
    summary = final_output.get("summary")
    if isinstance(summary, str) and summary.strip():
        return summary.strip()
    return json.dumps(final_output, ensure_ascii=False, sort_keys=True)[:200]
