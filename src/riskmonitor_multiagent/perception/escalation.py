"""异常升级触发 - 将 warning/critical 信号生成 system_event 进入统一执行内核."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from riskmonitor_multiagent.perception.signals import PerceptionSignal, SignalSeverity

logger = logging.getLogger(__name__)


class SystemEvent:
    """系统事件 - 感知升级产生的标准化事件，进入统一执行内核."""

    def __init__(
        self,
        *,
        event_id: str | None = None,
        event_type: str = "perception_alert",
        severity: str = "warning",
        source: str = "",
        description: str = "",
        signals: list[PerceptionSignal] | None = None,
        timestamp: datetime | None = None,
    ) -> None:
        self.event_id = event_id or str(uuid.uuid4())
        self.event_type = event_type
        self.severity = severity
        self.source = source
        self.description = description
        self.signals = signals or []
        self.timestamp = timestamp or datetime.now(timezone.utc)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "severity": self.severity,
            "source": self.source,
            "description": self.description,
            "timestamp": self.timestamp.isoformat(),
            "signals": [s.to_log_dict() for s in self.signals],
        }


class EscalationManager:
    """
    升级管理器.

    接收过滤后的升级信号 (warning / critical)，生成 system_event，
    路由进入统一执行内核 (ProactiveMultiAgentWorkflow.run())，不形成旁路。

    核心原则：所有升级事件必须经过统一执行内核，不存在绕过主链的旁路。
    """

    def __init__(self) -> None:
        self._pending_events: list[SystemEvent] = []
        self._total_escalated = 0
        self._total_critical = 0
        self._total_warning = 0

    def escalate(self, signals: list[PerceptionSignal]) -> SystemEvent | None:
        """
        将升级信号转换为 system_event.

        只处理 should_escalate() 为 True 的信号。
        如果没有升级信号，返回 None。
        """
        escalation_signals = [s for s in signals if s.should_escalate()]
        if not escalation_signals:
            return None

        # 按 severity 分组，critical 优先
        critical_signals = [s for s in escalation_signals if s.severity == SignalSeverity.CRITICAL]
        warning_signals = [s for s in escalation_signals if s.severity == SignalSeverity.WARNING]

        # 取最高级别
        if critical_signals:
            severity = "critical"
            primary_signals = critical_signals
        else:
            severity = "warning"
            primary_signals = warning_signals

        # 构建描述
        descriptions = [s.message or f"{s.source}.{s.metric}={s.value}" for s in primary_signals[:5]]
        description = "; ".join(descriptions)

        event = SystemEvent(
            event_type="perception_alert",
            severity=severity,
            source="perception_filter",
            description=description,
            signals=escalation_signals,
        )

        self._pending_events.append(event)
        self._total_escalated += 1
        if severity == "critical":
            self._total_critical += 1
        else:
            self._total_warning += 1

        logger.info(
            f"Escalation event created: {event.event_id} severity={severity} "
            f"signals={len(escalation_signals)} desc={description}"
        )

        return event

    def get_pending_events(self) -> list[SystemEvent]:
        """获取待处理的事件列表."""
        return list(self._pending_events)

    def consume_pending_events(self) -> list[SystemEvent]:
        """获取并清空待处理事件列表."""
        events = list(self._pending_events)
        self._pending_events.clear()
        return events

    def get_stats(self) -> dict[str, int]:
        """获取升级统计."""
        return {
            "total_escalated": self._total_escalated,
            "total_critical": self._total_critical,
            "total_warning": self._total_warning,
            "pending": len(self._pending_events),
        }
