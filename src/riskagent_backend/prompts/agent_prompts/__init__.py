"""Agent 系统提示词 - 从 roles.py 提取的独立提示词文件."""

from riskagent_backend.prompts.agent_prompts.intent_agent_prompt import INTENT_SYSTEM_PROMPT
from riskagent_backend.prompts.agent_prompts.orchestrator_agent_prompt import ORCHESTRATOR_SYSTEM_PROMPT
from riskagent_backend.prompts.agent_prompts.critic_agent_prompt import CRITIC_SYSTEM_PROMPT
from riskagent_backend.prompts.agent_prompts.system_engineer_prompt import SYSTEM_ENGINEER_PROMPT
from riskagent_backend.prompts.agent_prompts.risk_analyst_prompt import RISK_ANALYST_PROMPT

__all__ = [
    "INTENT_SYSTEM_PROMPT",
    "ORCHESTRATOR_SYSTEM_PROMPT",
    "CRITIC_SYSTEM_PROMPT",
    "SYSTEM_ENGINEER_PROMPT",
    "RISK_ANALYST_PROMPT",
]
