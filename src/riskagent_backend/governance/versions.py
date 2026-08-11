from __future__ import annotations

from riskagent_backend.config import get_policy_version


PROMPT_VERSION_SYSTEM_ENGINEER = "system_engineer_prompt.v1"
PROMPT_VERSION_RISK_ANALYST = "risk_analyst_prompt.v1"
PROMPT_VERSION_MANAGER = "manager_prompt.v1"
PROMPT_VERSION_INTENT = "intent_prompt.v1"
PROMPT_VERSION_ORCHESTRATOR = "orchestrator_prompt.v1"
PROMPT_VERSION_CRITIC = "critic_prompt.v1"

__all__ = ["get_policy_version"]
