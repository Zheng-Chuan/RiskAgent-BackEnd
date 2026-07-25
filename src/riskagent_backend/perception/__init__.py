"""
感知过滤层模块.

提供 PerceptionSignal 标准化结构和阈值规则引擎，
用于前置过滤正常信号，仅将异常信号升级到 LLM 分析。
"""

from riskagent_backend.perception.signals import PerceptionSignal, SignalSeverity
from riskagent_backend.perception.rules import FilterRule, PerceptionFilterEngine
from riskagent_backend.perception.default_rules import get_default_rules
from riskagent_backend.perception.escalation import EscalationManager, SystemEvent
from riskagent_backend.perception.remediation import RemediationManager, RemediationAction, RemediationResult

__all__ = [
    "PerceptionSignal",
    "SignalSeverity",
    "FilterRule",
    "PerceptionFilterEngine",
    "get_default_rules",
    "EscalationManager",
    "SystemEvent",
    "RemediationManager",
    "RemediationAction",
    "RemediationResult",
]
