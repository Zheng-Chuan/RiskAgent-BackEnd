"""
契约定义包.

定义 Agent 输出、消息、记忆等数据结构的格式规范与验证.

采用 PEP 562 __getattr__ 实现懒加载, 避免导入时强制加载全部 9 个子模块.
仅在访问具体符号时才触发对应子模块的加载.
"""

from __future__ import annotations

from typing import Any

# 懒加载映射表: 符号名 -> (子模块路径, 符号名)
_LAZY_IMPORTS: dict[str, tuple[str, str]] = {
    # Agent 输出 - 版本常量
    "CRITIC_VERSION": ("contracts.agent_outputs", "CRITIC_VERSION"),
    "ORCHESTRATOR_VERSION": ("contracts.agent_outputs", "ORCHESTRATOR_VERSION"),
    "RISK_ANALYST_VERSION": ("contracts.agent_outputs", "RISK_ANALYST_VERSION"),
    "SYSTEM_ENGINEER_VERSION": ("contracts.agent_outputs", "SYSTEM_ENGINEER_VERSION"),
    # Agent 输出 - 验证函数
    "validate_system_engineer_output": ("contracts.agent_outputs", "validate_system_engineer_output"),
    "validate_risk_analyst_output": ("contracts.agent_outputs", "validate_risk_analyst_output"),
    "validate_orchestrator_output": ("contracts.agent_outputs", "validate_orchestrator_output"),
    "validate_critic_review": ("contracts.agent_outputs", "validate_critic_review"),
    # Agent 输出 - 归一化函数
    "normalize_system_engineer_output": ("contracts.agent_outputs", "normalize_system_engineer_output"),
    "normalize_risk_analyst_output": ("contracts.agent_outputs", "normalize_risk_analyst_output"),
    "normalize_orchestrator_output": ("contracts.agent_outputs", "normalize_orchestrator_output"),
    "normalize_critic_review": ("contracts.agent_outputs", "normalize_critic_review"),
    # Agent 消息
    "AGENT_COMMAND_SCHEMA_VERSION": ("contracts.agent_messages", "AGENT_COMMAND_SCHEMA_VERSION"),
    "AGENT_RECEIPT_SCHEMA_VERSION": ("contracts.agent_messages", "AGENT_RECEIPT_SCHEMA_VERSION"),
    "validate_agent_command": ("contracts.agent_messages", "validate_agent_command"),
    "validate_agent_receipt": ("contracts.agent_messages", "validate_agent_receipt"),
    # Approval
    "APPROVAL_REQUEST_SCHEMA_VERSION": ("contracts.approval", "APPROVAL_REQUEST_SCHEMA_VERSION"),
    "APPROVAL_RECORD_SCHEMA_VERSION": ("contracts.approval", "APPROVAL_RECORD_SCHEMA_VERSION"),
    "validate_approval_transition": ("contracts.approval", "validate_approval_transition"),
    "ensure_approval_transition": ("contracts.approval", "ensure_approval_transition"),
    "validate_approval_request": ("contracts.approval", "validate_approval_request"),
    "normalize_approval_request": ("contracts.approval", "normalize_approval_request"),
    "validate_approval_record": ("contracts.approval", "validate_approval_record"),
    "normalize_approval_record": ("contracts.approval", "normalize_approval_record"),
    "build_approval_summary_text": ("contracts.approval", "build_approval_summary_text"),
    # 意图输出
    "INTENT_OUTPUT_SCHEMA_VERSION": ("contracts.intent_output", "INTENT_OUTPUT_SCHEMA_VERSION"),
    "validate_intent_output": ("contracts.intent_output", "validate_intent_output"),
    "normalize_intent_output": ("contracts.intent_output", "normalize_intent_output"),
    # 记忆条目
    "MEMORY_ENTRY_SCHEMA_VERSION": ("contracts.memory_entry", "MEMORY_ENTRY_SCHEMA_VERSION"),
    "validate_memory_entry": ("contracts.memory_entry", "validate_memory_entry"),
    "normalize_memory_entry": ("contracts.memory_entry", "normalize_memory_entry"),
    # Event
    "EVENT_SCHEMA_VERSION": ("contracts.event", "EVENT_SCHEMA_VERSION"),
    "EventType": ("contracts.event", "EventType"),
    "validate_event": ("contracts.event", "validate_event"),
    "normalize_event": ("contracts.event", "normalize_event"),
    "new_event": ("contracts.event", "new_event"),
    # RunContext
    "RUN_CONTEXT_SCHEMA_VERSION": ("contracts.run_context", "RUN_CONTEXT_SCHEMA_VERSION"),
    "validate_run_context": ("contracts.run_context", "validate_run_context"),
    "normalize_run_context": ("contracts.run_context", "normalize_run_context"),
    "new_run_context": ("contracts.run_context", "new_run_context"),
    # RunTrace
    "RUN_TRACE_SCHEMA_VERSION": ("contracts.run_trace", "RUN_TRACE_SCHEMA_VERSION"),
    "validate_run_trace": ("contracts.run_trace", "validate_run_trace"),
    "normalize_run_trace": ("contracts.run_trace", "normalize_run_trace"),
    # TaskGraph
    "TASK_GRAPH_SCHEMA_VERSION": ("contracts.task_graph", "TASK_GRAPH_SCHEMA_VERSION"),
    "append_replan_subgraph": ("contracts.task_graph", "append_replan_subgraph"),
    "build_task_graph_from_plan_steps": ("contracts.task_graph", "build_task_graph_from_plan_steps"),
    "validate_task_graph": ("contracts.task_graph", "validate_task_graph"),
    "normalize_task_graph": ("contracts.task_graph", "normalize_task_graph"),
}

# 向后兼容的旧名称 -> 新名称
_LEGACY_ALIASES: dict[str, str] = {
    "CRITIC_REVIEW_SCHEMA_VERSION": "CRITIC_VERSION",
    "ORCHESTRATOR_OUTPUT_SCHEMA_VERSION": "ORCHESTRATOR_VERSION",
    "RISK_ANALYST_OUTPUT_SCHEMA_VERSION": "RISK_ANALYST_VERSION",
    "SYSTEM_ENGINEER_OUTPUT_SCHEMA_VERSION": "SYSTEM_ENGINEER_VERSION",
}

__all__ = list(_LAZY_IMPORTS.keys()) + list(_LEGACY_ALIASES.keys())


def __getattr__(name: str) -> Any:
    """PEP 562 懒加载: 仅在访问具体符号时才导入对应子模块."""
    if name in _LEGACY_ALIASES:
        canonical = _LEGACY_ALIASES[name]
        if canonical in _LAZY_IMPORTS:
            module_path, attr = _LAZY_IMPORTS[canonical]
            import importlib
            mod = importlib.import_module(f"riskagent_backend.{module_path}")
            return getattr(mod, attr)

    if name in _LAZY_IMPORTS:
        module_path, attr = _LAZY_IMPORTS[name]
        import importlib
        mod = importlib.import_module(f"riskagent_backend.{module_path}")
        return getattr(mod, attr)

    raise AttributeError(f"module 'riskagent_backend.contracts' has no attribute '{name}'")


def __dir__() -> list[str]:
    return list(_LAZY_IMPORTS.keys()) + list(_LEGACY_ALIASES.keys())
