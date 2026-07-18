"""LLM 频率控制 - 感知链路独立预算治理和频控上限."""

from __future__ import annotations

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)


class PerceptionBudgetManager:
    """
    感知链路 LLM 预算管理器 (Checkpoint 16.3.3).

    对感知升级触发的 LLM 调用纳入预算治理:
    - 设置感知链路独立的 token budget
    - 设置频控上限 (每分钟最大调用次数)
    - 触发熔断后降级为纯规则处置，不再调用 LLM

    核心原则：感知链路 LLM 成本不超过总预算的 20%。
    """

    def __init__(
        self,
        *,
        max_tokens_per_hour: int = 50000,
        max_calls_per_minute: int = 10,
        max_tokens_per_call: int = 4000,
        circuit_breaker_threshold: int = 3,
    ) -> None:
        self._max_tokens_per_hour = max_tokens_per_hour
        self._max_calls_per_minute = max_calls_per_minute
        self._max_tokens_per_call = max_tokens_per_call
        self._circuit_breaker_threshold = circuit_breaker_threshold

        # 运行时状态
        self._tokens_used_this_hour = 0
        self._calls_this_minute: list[float] = []  # timestamps
        self._consecutive_failures = 0
        self._circuit_broken = False
        self._hour_start = time.time()

        # 统计
        self._total_tokens_used = 0
        self._total_calls = 0
        self._total_circuit_breaks = 0

    def can_call_llm(self) -> bool:
        """检查是否允许调用 LLM (预算和频控均未超限)."""
        if self._circuit_broken:
            logger.warning("Perception LLM circuit breaker is ON, degrading to rule-based")
            return False

        now = time.time()

        # 清理过期的一分钟窗口
        self._calls_this_minute = [t for t in self._calls_this_minute if now - t < 60]

        # 频控检查
        if len(self._calls_this_minute) >= self._max_calls_per_minute:
            logger.warning(f"Perception LLM frequency limit: {len(self._calls_this_minute)}/{self._max_calls_per_minute} per minute")
            return False

        # 小时预算检查
        if now - self._hour_start > 3600:
            # 新的一小时，重置
            self._tokens_used_this_hour = 0
            self._hour_start = now

        if self._tokens_used_this_hour >= self._max_tokens_per_hour:
            logger.warning(
                f"Perception LLM hourly budget exceeded: {self._tokens_used_this_hour}/{self._max_tokens_per_hour}"
            )
            self._trigger_circuit_breaker("hourly budget exceeded")
            return False

        return True

    def record_call(self, tokens_used: int, success: bool = True) -> None:
        """记录一次 LLM 调用的消耗."""
        now = time.time()
        self._calls_this_minute.append(now)
        self._tokens_used_this_hour += tokens_used
        self._total_tokens_used += tokens_used
        self._total_calls += 1

        if success:
            self._consecutive_failures = 0
        else:
            self._consecutive_failures += 1
            if self._consecutive_failures >= self._circuit_breaker_threshold:
                self._trigger_circuit_breaker(f"consecutive failures: {self._consecutive_failures}")

        logger.debug(
            f"Perception LLM call recorded: tokens={tokens_used} "
            f"hourly_total={self._tokens_used_this_hour}/{self._max_tokens_per_hour} "
            f"minute_calls={len(self._calls_this_minute)}/{self._max_calls_per_minute}"
        )

    def _trigger_circuit_breaker(self, reason: str) -> None:
        """触发熔断."""
        self._circuit_broken = True
        self._total_circuit_breaks += 1
        logger.error(
            f"Perception LLM circuit breaker triggered: {reason}. "
            f"Degrading to pure rule-based processing."
        )

    def reset_circuit_breaker(self) -> None:
        """手动重置熔断器."""
        self._circuit_broken = False
        self._consecutive_failures = 0
        logger.info("Perception LLM circuit breaker reset")

    def is_circuit_broken(self) -> bool:
        """熔断器是否开启."""
        return self._circuit_broken

    def get_stats(self) -> dict[str, Any]:
        """获取预算统计."""
        now = time.time()
        return {
            "total_calls": self._total_calls,
            "total_tokens_used": self._total_tokens_used,
            "hourly_tokens_used": self._tokens_used_this_hour,
            "hourly_token_limit": self._max_tokens_per_hour,
            "minute_calls": len([t for t in self._calls_this_minute if now - t < 60]),
            "minute_call_limit": self._max_calls_per_minute,
            "circuit_broken": self._circuit_broken,
            "consecutive_failures": self._consecutive_failures,
            "total_circuit_breaks": self._total_circuit_breaks,
        }
