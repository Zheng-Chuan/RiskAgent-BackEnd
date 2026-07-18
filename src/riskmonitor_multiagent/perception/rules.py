"""阈值规则引擎 - 前置过滤正常信号，仅异常信号升级到 LLM."""

from __future__ import annotations

import logging
from typing import Any, Callable

from riskmonitor_multiagent.perception.signals import PerceptionSignal, SignalSeverity

logger = logging.getLogger(__name__)


class FilterRule:
    """
    单条过滤规则.

    每条规则包含:
    - name: 规则名称
    - source: 匹配的数据源
    - metric: 匹配的指标名
    - predicate: 判断函数 (value) -> bool, 返回 True 表示命中规则
    - severity: 命中后的严重级别
    - threshold: 阈值描述（用于日志和信号标注）
    - message: 命中时的人类可读描述
    """

    def __init__(
        self,
        *,
        name: str,
        source: str,
        metric: str,
        predicate: Callable[[Any], bool],
        severity: SignalSeverity,
        threshold: Any = None,
        message: str = "",
    ) -> None:
        self.name = name
        self.source = source
        self.metric = metric
        self.predicate = predicate
        self.severity = severity
        self.threshold = threshold
        self.message = message

    def matches(self, signal: PerceptionSignal) -> bool:
        """检查信号是否匹配此规则."""
        return (
            signal.source == self.source
            and signal.metric == self.metric
            and self.predicate(signal.value)
        )

    def apply(self, signal: PerceptionSignal) -> PerceptionSignal:
        """将规则应用到信号上，返回更新后的信号."""
        return signal.model_copy(update={
            "severity": self.severity,
            "threshold": self.threshold,
            "message": self.message or f"{self.name}: {signal.metric}={signal.value} threshold={self.threshold}",
            "context": {**signal.context, "rule": self.name},
        })


class PerceptionFilterEngine:
    """
    感知过滤引擎.

    接收原始感知信号，逐条匹配规则。
    - 命中规则：更新 severity 为规则定义的级别
    - 未命中任何规则：保持 INFO 级别（不升级）

    核心原则：正常信号不升级到 LLM，仅异常信号升级。
    """

    def __init__(self, rules: list[FilterRule] | None = None) -> None:
        self._rules: list[FilterRule] = rules or []

    def add_rule(self, rule: FilterRule) -> None:
        """添加规则."""
        self._rules.append(rule)
        logger.debug(f"Filter rule added: {rule.name}")

    def set_rules(self, rules: list[FilterRule]) -> None:
        """替换全部规则."""
        self._rules = list(rules)
        logger.info(f"Filter engine loaded {len(self._rules)} rules")

    def filter(self, signal: PerceptionSignal) -> PerceptionSignal:
        """
        过滤单个信号.

        按规则顺序匹配，首个命中的规则生效。
        未命中任何规则的信号保持 INFO 级别。
        """
        for rule in self._rules:
            if rule.matches(signal):
                logger.debug(
                    f"Signal matched rule '{rule.name}': {signal.source}.{signal.metric}={signal.value} -> {rule.severity.value}"
                )
                return rule.apply(signal)

        # 未命中任何规则，保持 INFO
        logger.debug(
            f"Signal passed through (no rule matched): {signal.source}.{signal.metric}={signal.value}"
        )
        return signal

    def filter_batch(self, signals: list[PerceptionSignal]) -> list[PerceptionSignal]:
        """批量过滤信号."""
        return [self.filter(s) for s in signals]

    def get_escalation_signals(self, signals: list[PerceptionSignal]) -> list[PerceptionSignal]:
        """从一批信号中筛选出需要升级的信号 (warning / critical)."""
        filtered = self.filter_batch(signals)
        return [s for s in filtered if s.should_escalate()]
