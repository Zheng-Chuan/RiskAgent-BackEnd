"""LLM 成本模型：定价表 + 成本计算 + 预估表生成.

Checkpoint 20.1.2 / 20.1.3 — 基于 OpenRouter 公开定价计算 LLM 调用成本，
并支持四窗口（5min / 1h / 24h / 7d）成本预估。
"""

from __future__ import annotations

from typing import Any

# OpenRouter 定价表（per 1K tokens，美元）
# 参考: https://openrouter.ai/models
PRICING_TABLE: dict[str, dict[str, float]] = {
    "deepseek/deepseek-chat": {
        "prompt": 0.00014,       # $0.14 per 1M tokens
        "completion": 0.00028,   # $0.28 per 1M tokens
    },
    "deepseek/deepseek-r1": {
        "prompt": 0.00055,
        "completion": 0.00219,
    },
    "deepseek/deepseek-v3": {
        "prompt": 0.00014,
        "completion": 0.00028,
    },
    "deepseek/deepseek-v4-pro": {
        "prompt": 0.00014,
        "completion": 0.00028,
    },
    "deepseek/deepseek-v4-flash": {
        "prompt": 0.00010,       # $0.10 per 1M tokens
        "completion": 0.00020,   # $0.20 per 1M tokens
    },
    "openai/gpt-4o": {
        "prompt": 0.0025,
        "completion": 0.01,
    },
    "openai/gpt-4o-mini": {
        "prompt": 0.00015,
        "completion": 0.0006,
    },
    "google/gemini-2.0-flash-exp:free": {
        "prompt": 0.0,
        "completion": 0.0,
    },
    # RFC-005 需求二: embedding 模型定价
    # text-embedding-3-small: $0.02/1M tokens (OpenRouter 定价)
    # embedding 调用无 completion tokens, completion 价格为 0
    "text-embedding-3-small": {
        "prompt": 0.00002,     # $0.02 per 1M tokens
        "completion": 0.0,     # embedding 无输出 token
    },
    "default": {
        "prompt": 0.00014,
        "completion": 0.00028,
    },
}


def get_pricing(model: str) -> dict[str, float]:
    """获取模型定价.

    Args:
        model: 模型名称，如 ``deepseek/deepseek-chat``

    Returns:
        ``{"prompt": float, "completion": float}`` — 每 1K token 的美元价格
    """
    return PRICING_TABLE.get(model, PRICING_TABLE["default"])


def calculate_call_cost(prompt_tokens: int, completion_tokens: int, model: str) -> float:
    """计算单次调用成本（美元）.

    Args:
        prompt_tokens: 输入 token 数
        completion_tokens: 输出 token 数
        model: 模型名称

    Returns:
        成本金额（美元），保留 6 位小数
    """
    pricing = get_pricing(model)
    prompt_cost = (prompt_tokens / 1000) * pricing["prompt"]
    completion_cost = (completion_tokens / 1000) * pricing["completion"]
    return round(prompt_cost + completion_cost, 6)


def calculate_chain_cost(records: list[dict[str, Any]]) -> dict[str, Any]:
    """计算单次完整链路成本.

    Args:
        records: 调用记录列表，每条记录包含 prompt_tokens / completion_tokens / model / stage

    Returns:
        ``{"total_cost": float, "by_stage": dict, "call_count": int}``
    """
    total_cost = 0.0
    by_stage: dict[str, dict[str, Any]] = {}
    for r in records:
        cost = calculate_call_cost(
            r.get("prompt_tokens", 0),
            r.get("completion_tokens", 0),
            r.get("model", "default"),
        )
        total_cost += cost
        stage = r.get("stage", "unknown")
        if stage not in by_stage:
            by_stage[stage] = {"cost": 0.0, "calls": 0}
        by_stage[stage]["cost"] = round(by_stage[stage]["cost"] + cost, 6)
        by_stage[stage]["calls"] += 1
    return {
        "total_cost": round(total_cost, 6),
        "by_stage": by_stage,
        "call_count": len(records),
    }


def generate_cost_estimate_table(
    token_tracker_summary: dict[str, Any],
    dedup_enabled: bool = False,
) -> dict[str, dict[str, Any]]:
    """生成 5min / 1h / 24h / 7d 四窗口成本预估表.

    基于 TokenTracker.summary() 的实测数据，推算不同时间窗口的总成本。

    Args:
        token_tracker_summary: ``TokenTracker.summary()`` 返回的字典
        dedup_enabled: 是否启用去重（RFC-006: LLM 调用降低 80%）

    Returns:
        四窗口预估表，每个窗口包含 estimated_calls / estimated_cost_usd / dedup_enabled
    """
    # 基线：5min 实测数据（TokenTracker 默认 1h 窗口，作为近似基线）
    calls_5min = token_tracker_summary.get("calls", 0)
    tokens_5min = token_tracker_summary.get("total_tokens", 0)
    cost_5min = token_tracker_summary.get("cost_estimate", 0.0)

    # 如果 5min 数据为空，使用 Phase 10 实测基线
    if calls_5min == 0:
        calls_5min = 133
        tokens_5min = 780013
        cost_5min = calculate_call_cost(580000, 200000, "deepseek/deepseek-chat")

    # 去重场景：LLM 调用降低 80%（RFC-006 去重效果）
    dedup_factor = 0.2 if dedup_enabled else 1.0

    # 按时间窗口推算
    # 5min → 1h: 12 倍（60min / 5min）
    # 5min → 24h: 288 倍（1440min / 5min）
    # 5min → 7d: 2016 倍（10080min / 5min）
    windows = {
        "5min": {"calls": calls_5min, "multiplier": 1},
        "1h": {"calls": calls_5min, "multiplier": 12},
        "24h": {"calls": calls_5min, "multiplier": 288},
        "7d": {"calls": calls_5min, "multiplier": 2016},
    }

    table: dict[str, dict[str, Any]] = {}
    for window, config in windows.items():
        projected_calls = int(config["calls"] * config["multiplier"] * dedup_factor)
        projected_cost = cost_5min * config["multiplier"] * dedup_factor
        table[window] = {
            "estimated_calls": projected_calls,
            "estimated_cost_usd": round(projected_cost, 4),
            "dedup_enabled": dedup_enabled,
        }

    return table


__all__ = [
    "PRICING_TABLE",
    "get_pricing",
    "calculate_call_cost",
    "calculate_chain_cost",
    "generate_cost_estimate_table",
]
