"""
Agent 模块.

保留 BaseAgent 和 AgentResult 供其他模块使用.
主动 Agent 请使用 proactive_agents 模块.
"""

from riskagent_backend.agents.base import AgentResult, BaseAgent
from riskagent_backend.agents.registry import (
    AgentSpec,
    all_agents,
    candidate_agents_for_event,
    get_agent_by_role,
    register_agent,
)

__all__ = [
    "AgentResult",
    "AgentSpec",
    "BaseAgent",
    "all_agents",
    "candidate_agents_for_event",
    "get_agent_by_role",
    "register_agent",
]
