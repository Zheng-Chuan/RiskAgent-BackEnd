"""成本熔断器：三级预算上限 + 超限降级.

Checkpoint 20.1.4 — 基于 TokenTracker 实测数据的三级成本熔断器。
超限后触发熔断，降级为纯规则处置（跳过 LLM 调用）。

三级预算:
- 5min:  50K tokens / $0.01
- 1h:   500K tokens / $0.10
- 24h: 10M  tokens / $2.00
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)


class CostCircuitBreaker:
    """三级成本熔断器（5min / 1h / 24h）.

    超限后触发熔断，降级为纯规则处置（跳过 LLM 调用）。
    线程安全：所有状态变更通过内部锁保护。
    """

    BUDGETS: dict[str, dict[str, float]] = {
        "5min": {"token_limit": 50000, "cost_limit": 0.01},
        "1h": {"token_limit": 500000, "cost_limit": 0.10},
        "24h": {"token_limit": 10000000, "cost_limit": 2.00},
    }

    def __init__(self, cooldown_s: int = 30) -> None:
        self._tripped: dict[str, bool] = {level: False for level in self.BUDGETS}
        self._tripped_at: dict[str, float] = {level: 0.0 for level in self.BUDGETS}
        self._cooldown_s = cooldown_s
        self._lock = threading.Lock()

    def check(self) -> dict[str, Any]:
        """检查是否应熔断.

        Returns:
            ``{"should_block": bool, "reason": str, "level": str}``
        """
        from riskagent_backend.llm.token_tracker import get_token_tracker

        try:
            summary = get_token_tracker().summary()
        except Exception:  # pragma: no cover - tracker 不可用时放行
            logger.debug("TokenTracker unavailable in cost breaker", exc_info=True)
            return {"should_block": False, "reason": "", "level": ""}

        now = time.time()

        with self._lock:
            for level, limits in self.BUDGETS.items():
                # 检查是否在冷却期
                if self._tripped[level]:
                    if now - self._tripped_at[level] < self._cooldown_s:
                        return {
                            "should_block": True,
                            "reason": f"cost_circuit_breaker_{level}",
                            "level": level,
                        }
                    else:
                        # 冷却结束，重置该级别
                        self._tripped[level] = False

                # 检查 token 限制
                if summary.get("total_tokens", 0) > limits["token_limit"]:
                    self._tripped[level] = True
                    self._tripped_at[level] = now
                    logger.warning(
                        "cost_circuit_breaker tripped level=%s reason=token_limit_exceeded "
                        "tokens=%d limit=%d",
                        level,
                        summary.get("total_tokens", 0),
                        limits["token_limit"],
                    )
                    return {
                        "should_block": True,
                        "reason": f"token_limit_exceeded_{level}",
                        "level": level,
                    }

                # 检查成本限制
                if summary.get("cost_estimate", 0.0) > limits["cost_limit"]:
                    self._tripped[level] = True
                    self._tripped_at[level] = now
                    logger.warning(
                        "cost_circuit_breaker tripped level=%s reason=cost_limit_exceeded "
                        "cost=%.6f limit=%.2f",
                        level,
                        summary.get("cost_estimate", 0.0),
                        limits["cost_limit"],
                    )
                    return {
                        "should_block": True,
                        "reason": f"cost_limit_exceeded_{level}",
                        "level": level,
                    }

        return {"should_block": False, "reason": "", "level": ""}

    def is_tripped(self) -> bool:
        """是否已熔断（任一级别）."""
        with self._lock:
            return any(self._tripped.values())

    def reset(self) -> None:
        """重置熔断状态."""
        with self._lock:
            for level in self.BUDGETS:
                self._tripped[level] = False
                self._tripped_at[level] = 0.0


# 全局单例
_cost_breaker: CostCircuitBreaker | None = None
_cost_breaker_lock = threading.Lock()


def get_cost_circuit_breaker() -> CostCircuitBreaker:
    """获取全局 CostCircuitBreaker 单例."""
    global _cost_breaker
    if _cost_breaker is None:
        with _cost_breaker_lock:
            if _cost_breaker is None:
                _cost_breaker = CostCircuitBreaker()
    return _cost_breaker


def reset_cost_circuit_breaker() -> None:
    """重置全局单例（测试用）."""
    global _cost_breaker
    with _cost_breaker_lock:
        _cost_breaker = None


__all__ = [
    "CostCircuitBreaker",
    "get_cost_circuit_breaker",
    "reset_cost_circuit_breaker",
]
