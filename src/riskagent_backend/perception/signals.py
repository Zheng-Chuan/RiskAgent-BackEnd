"""PerceptionSignal 标准化结构."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class SignalSeverity(str, Enum):
    """信号严重级别."""

    INFO = "info"          # 正常信号，不升级到 LLM
    WARNING = "warning"   # 异常信号，需关注但不紧急
    CRITICAL = "critical"  # 严重异常，需立即处置


class PerceptionSignal(BaseModel):
    """
    标准化感知信号.

    由感知数据源产出，经规则引擎评估后标注 severity。
    正常信号 (info) 不升级到 LLM；异常信号 (warning/critical) 升级到统一执行内核。
    """

    source: str = Field(description="数据源: docker / redis / mysql / prometheus")
    metric: str = Field(description="指标名: container_status / memory_usage / slow_queries 等")
    value: Any = Field(description="当前值")
    threshold: Any | None = Field(default=None, description="阈值（命中规则时填充）")
    severity: SignalSeverity = Field(default=SignalSeverity.INFO, description="严重级别")
    message: str = Field(default="", description="人类可读描述")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    context: dict[str, Any] = Field(default_factory=dict, description="附加上下文")

    def should_escalate(self) -> bool:
        """是否应升级到 LLM 分析."""
        return self.severity in (SignalSeverity.WARNING, SignalSeverity.CRITICAL)

    def to_log_dict(self) -> dict[str, Any]:
        """转换为日志友好的字典."""
        return {
            "source": self.source,
            "metric": self.metric,
            "value": self.value,
            "threshold": self.threshold,
            "severity": self.severity.value,
            "message": self.message,
            "timestamp": self.timestamp.isoformat(),
        }
