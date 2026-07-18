"""
感知过滤层模块.

提供 PerceptionSignal 标准化结构和阈值规则引擎，
用于前置过滤正常信号，仅将异常信号升级到 LLM 分析。
"""

from riskmonitor_multiagent.perception.signals import PerceptionSignal, SignalSeverity
from riskmonitor_multiagent.perception.rules import FilterRule, PerceptionFilterEngine
from riskmonitor_multiagent.perception.default_rules import get_default_rules

__all__ = [
    "PerceptionSignal",
    "SignalSeverity",
    "FilterRule",
    "PerceptionFilterEngine",
    "get_default_rules",
]
