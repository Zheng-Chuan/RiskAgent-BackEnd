"""
BDI 数据模型 - 信念(Belief)、愿望(Desire)、意图(Intention)、ReAct 步骤、执行结果.

从 proactive_agents/base.py 提取的纯数据容器类.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class Belief:
    """Agent 的信念:Agent 认为世界的状态."""
    
    content: Any
    source: str
    confidence: float = 1.0
    belief_id: str = field(default_factory=lambda: f"belief_{uuid.uuid4().hex[:8]}")
    timestamp_ms: int = field(default_factory=lambda: time.time_ns() // 1000000)


@dataclass
class Desire:
    """Agent 的愿望:Agent 想要达到的状态."""
    
    description: str
    priority: int = 0
    active: bool = True
    desire_id: str = field(default_factory=lambda: f"desire_{uuid.uuid4().hex[:8]}")


@dataclass
class Intention:
    """Agent 的意图:Agent 承诺要执行的行动."""
    
    description: str
    target_agent: Optional[str] = None
    tool_name: Optional[str] = None
    tool_params: Optional[dict[str, Any]] = None
    status: str = "pending"
    intention_id: str = field(default_factory=lambda: f"intention_{uuid.uuid4().hex[:8]}")
    created_timestamp_ms: int = field(default_factory=lambda: time.time_ns() // 1000000)


@dataclass
class ReActStep:
    """ReAct 循环的单个步骤(动态生成,非硬编码)."""
    
    step_id: str
    thought: str
    reasoning: str
    evidence: dict[str, Any]
    action_type: str
    action: dict[str, Any]
    observation: Optional[dict[str, Any]] = None
    timestamp_ms: int = field(default_factory=lambda: time.time_ns() // 1000000)


@dataclass
class ProactiveAgentResult:
    """主动 Agent 执行结果."""
    
    ok: bool
    output: dict[str, Any]
    usage: dict[str, Any] | None = None
    meta: dict[str, Any] | None = None
    react_steps: list[ReActStep] = field(default_factory=list)
    bdi_state: dict[str, Any] = field(default_factory=dict)
    llm_interactions: list[dict[str, Any]] = field(default_factory=list)


__all__ = [
    "Belief",
    "Desire",
    "Intention",
    "ReActStep",
    "ProactiveAgentResult",
]
