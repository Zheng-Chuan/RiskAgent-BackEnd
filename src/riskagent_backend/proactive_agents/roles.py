"""
主动 Agent 角色定义.

实现 5 种具备 BDI + ReAct + 后台监控的 Agent:
- ProactiveIntentAgent: 意图识别
- ProactiveOrchestratorAgent: 编排计划
- ProactiveCriticAgent: 计划评审
- ProactiveSystemEngineerAgent: 系统工程师分析
- ProactiveRiskAnalystAgent: 风险分析师评估
"""

from __future__ import annotations

import logging
import os
from typing import Any

from riskagent_backend.proactive_agents.base import (
    BaseProactiveAgent,
    ProactiveAgentResult,
)
from riskagent_backend.governance.versions import (
    PROMPT_VERSION_CRITIC,
    PROMPT_VERSION_INTENT,
    PROMPT_VERSION_ORCHESTRATOR,
    PROMPT_VERSION_RISK_ANALYST,
    PROMPT_VERSION_SYSTEM_ENGINEER,
    get_policy_version,
)
from riskagent_backend.contracts.intent_output import INTENT_OUTPUT_SCHEMA_VERSION
from riskagent_backend.prompts.agent_prompts import (
    INTENT_SYSTEM_PROMPT,
    ORCHESTRATOR_SYSTEM_PROMPT,
    CRITIC_SYSTEM_PROMPT,
    SYSTEM_ENGINEER_PROMPT,
    RISK_ANALYST_PROMPT,
)

logger = logging.getLogger(__name__)


class ProactiveIntentAgent(BaseProactiveAgent):
    """
    主动意图识别 Agent.
    
    具备:
    - 后台监控:主动感知用户输入模式
    - ReAct 循环:动态推理意图
    - BDI 模型:维护意图识别的信念和愿望
    """
    
    def __init__(self) -> None:
        super().__init__(
            name="intent",
            system_prompt=self._build_system_prompt(),
            prompt_version=PROMPT_VERSION_INTENT,
            policy_version=get_policy_version(),
            enable_background_monitor=True,
            monitor_interval_seconds=120,
        )
    
    def _build_system_prompt(self) -> str:
        return INTENT_SYSTEM_PROMPT

    def _init_desires(self) -> None:
        """初始化愿望."""
        self.add_desire("准确识别用户意图", priority=10)
        self.add_desire("识别潜在风险操作", priority=8)
        self.add_desire("提供清晰的意图解释", priority=6)

    async def _perceive_environment(self) -> None:
        """感知环境 - 监控业务指标异常."""
        try:
            from riskagent_backend.perception.data_sources import PrometheusDataSource
            filtered = self._collect_and_filter([PrometheusDataSource()])
            if not filtered:
                return
            for sig in filtered:
                self.add_belief(
                    content={
                        "source": sig.source,
                        "metric": sig.metric,
                        "value": sig.value,
                        "severity": sig.severity.value,
                    },
                    source="intent_perception",
                    confidence=0.7,
                )
        except Exception as e:
            logger.warning(f"[intent] 意图感知失败: {e}")

    async def recognize(
        self,
        *,
        task: dict[str, Any],
        metadata: dict[str, Any] | None = None,
    ) -> ProactiveAgentResult:
        """识别任务意图(使用 ReAct 循环)."""
        self.add_belief(
            content={"task_id": task.get("task_id"), "content": task.get("payload", {}).get("content", "")},
            source="user_input",
        )
        
        return await self.run_with_react(
            task=task,
            context={"metadata": metadata},
            max_tokens=None,  # 不限制 token 数,让 GPT-4.5 自由输出
            max_steps=5,
        )

    async def _generate_final_answer(self, task: dict[str, Any], history: list) -> dict[str, Any]:
        """生成意图识别结果(简化格式)."""
        from riskagent_backend.contracts import (
            INTENT_OUTPUT_SCHEMA_VERSION,
            normalize_intent_output,
        )
        
        payload = task.get("payload") if isinstance(task.get("payload"), dict) else {}
        content = payload.get("content") if isinstance(payload.get("content"), str) else ""
        
        # 简化的 prompt,只要求 4 个字段
        prompt = f"""Based on your ReAct reasoning, generate the final intent recognition result.

Task content: {content}

Your reasoning chain:
{history[-1].thought if history else ''}

Generate a SIMPLE JSON with ONLY these 4 fields:
- intent: the action type (e.g., "query_positions", "analyze_risk")
- slots: extracted entities as key-value pairs
- confidence: 0.0 to 1.0
- risk: "LOW", "MEDIUM", or "HIGH"

Example:
{{
  "intent": "query_positions",
  "slots": {{"trader_id": "TRADER-001"}},
  "confidence": 0.95,
  "risk": "LOW"
}}"""

        result = await self._base_agent.ask_json(
            user_prompt=prompt,
            max_tokens=None,  # 不限制 token 数
        )
        
        # 将简化格式转换为标准格式
        output = self._convert_to_standard_format(result.output if isinstance(result.output, dict) else {})
        return output
    
    def _convert_to_standard_format(self, simple_output: dict[str, Any]) -> dict[str, Any]:
        """将简化的 4 字段格式转换为标准格式."""
        # 提取简化的字段
        intent = simple_output.get("intent", "unknown")
        slots = simple_output.get("slots", {})
        confidence = simple_output.get("confidence", 0.5)
        risk = simple_output.get("risk", "MEDIUM")
        
        # 转换为标准格式
        return {
            "schema_version": INTENT_OUTPUT_SCHEMA_VERSION,
            "primary_intent_type": intent.split("_")[0] if "_" in intent else intent,  # "query_positions" -> "query"
            "intents": [
                {
                    "intent_type": intent,
                    "slots": slots,
                    "confidence": float(confidence) if isinstance(confidence, (int, float)) else 0.5
                }
            ],
            "risk_level": risk,
            "permission_requirements": {
                "side_effects": False,
                "requires_human_approval": risk == "HIGH",
                "allowed_tools": None,
            },
            "evidence": {
                "fields": ["task.payload.content"],
            },
        }


class ProactiveOrchestratorAgent(BaseProactiveAgent):
    """
    主动编排 Agent.
    
    具备:
    - 后台监控:监控任务队列和系统状态
    - ReAct 循环:动态制定和调整计划
    - BDI 模型:维护任务规划信念
    """
    
    def __init__(self) -> None:
        super().__init__(
            name="orchestrator",
            system_prompt=self._build_system_prompt(),
            prompt_version=PROMPT_VERSION_ORCHESTRATOR,
            policy_version=get_policy_version(),
            enable_background_monitor=True,
            monitor_interval_seconds=60,
        )
    
    def _build_system_prompt(self) -> str:
        return ORCHESTRATOR_SYSTEM_PROMPT

    def _init_desires(self) -> None:
        """初始化愿望."""
        self.add_desire("制定高效执行计划", priority=10)
        self.add_desire("合理分配任务给专业 Agent", priority=8)
        self.add_desire("确保计划可执行且风险可控", priority=9)

    async def _perceive_environment(self) -> None:
        """主动感知 - 监控编排指标."""
        try:
            from riskagent_backend.perception.data_sources import PrometheusDataSource
            filtered = self._collect_and_filter([PrometheusDataSource()])
            if not filtered:
                return
            for sig in filtered:
                self.add_belief(
                    content={
                        "source": sig.source,
                        "metric": sig.metric,
                        "value": sig.value,
                        "severity": sig.severity.value,
                    },
                    source="orchestration_perception",
                    confidence=0.7,
                )
        except Exception as e:
            logger.warning(f"[orchestrator] 感知环境失败: {e}")

    async def orchestrate(
        self,
        *,
        task: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> ProactiveAgentResult:
        """编排任务(使用 ReAct 循环)."""
        self.add_belief(
            content={"task_id": task.get("task_id"), "context": context},
            source="orchestration_request",
        )
        
        return await self.run_with_react(
            task=task,
            context=context,
            max_tokens=1024,
            max_steps=5,
        )

    async def _generate_final_answer(self, task: dict[str, Any], history: list) -> dict[str, Any]:
        """生成编排计划."""
        from riskagent_backend.contracts import normalize_orchestrator_output
        
        steps_summary = "\n".join([
            f"Step {s.step_id}: {s.thought} -> {s.action_type}"
            for s in history
        ])
        
        prompt = f"""Based on your ReAct reasoning, generate the final orchestration plan.

Task: {task}

Your reasoning chain:
{steps_summary}

Generate JSON with:
- intent: object with type, confidence, slots
- plan_steps: list of steps with kind, step_id, reason, target_agent/instruction
- commands: list or null
- evidence"""

        result = await self._base_agent.ask_json(
            user_prompt=prompt,
            max_tokens=1024,
        )
        
        output = normalize_orchestrator_output(result.output if isinstance(result.output, dict) else {})
        return output


class ProactiveCriticAgent(BaseProactiveAgent):
    """
    主动评审 Agent.
    
    具备:
    - 后台监控:监控计划执行质量
    - ReAct 循环:动态评审和反馈
    - BDI 模型:维护评审标准信念
    """
    
    def __init__(self) -> None:
        super().__init__(
            name="critic",
            system_prompt=self._build_system_prompt(),
            prompt_version=PROMPT_VERSION_CRITIC,
            policy_version=get_policy_version(),
            enable_background_monitor=True,
            monitor_interval_seconds=90,
        )
    
    def _build_system_prompt(self) -> str:
        return CRITIC_SYSTEM_PROMPT

    def _init_desires(self) -> None:
        """初始化愿望."""
        self.add_desire("识别计划中的风险点", priority=10)
        self.add_desire("确保计划符合安全规范", priority=9)
        self.add_desire("提供有价值的改进建议", priority=7)

    async def _perceive_environment(self) -> None:
        """主动感知 - 监控计划执行质量."""
        try:
            from riskagent_backend.perception.data_sources import PrometheusDataSource
            filtered = self._collect_and_filter([PrometheusDataSource()])
            if not filtered:
                return
            for sig in filtered:
                self.add_belief(
                    content={
                        "source": sig.source,
                        "metric": sig.metric,
                        "value": sig.value,
                        "severity": sig.severity.value,
                    },
                    source="quality_perception",
                    confidence=0.7,
                )
        except Exception as e:
            logger.warning(f"[critic] 感知环境失败: {e}")

    async def review(
        self,
        *,
        task: dict[str, Any],
        orchestrator: dict[str, Any],
        receipts: list[dict[str, Any]] | None = None,
        final_output: dict[str, Any] | None = None,
        phase: str = "plan_review",
    ) -> ProactiveAgentResult:
        """评审计划(使用 ReAct 循环)."""
        self.add_belief(
            content={"plan": orchestrator.get("plan_steps", [])},
            source="orchestrator_plan",
        )

        if phase == "final_review":
            output = self._build_execution_review(
                task=task,
                orchestrator=orchestrator,
                receipts=receipts or [],
                final_output=final_output or {},
            )
            return ProactiveAgentResult(
                ok=bool(output.get("ok")),
                output=output,
                bdi_state=self.get_bdi_state(),
                llm_interactions=self.get_llm_interactions(),
            )

        return await self.run_with_react(
            task=task,
            context={
                "orchestrator_plan": orchestrator,
                "receipts": receipts or [],
                "final_output": final_output or {},
                "phase": phase,
            },
            max_tokens=512,
            max_steps=4,
        )

    def _build_execution_review(
        self,
        *,
        task: dict[str, Any],
        orchestrator: dict[str, Any],
        receipts: list[dict[str, Any]],
        final_output: dict[str, Any],
    ) -> dict[str, Any]:
        from riskagent_backend.contracts import normalize_critic_review

        valid_receipts = [receipt for receipt in receipts if isinstance(receipt, dict)]
        receipt_command_ids = [
            str(receipt.get("command_id"))
            for receipt in valid_receipts
            if isinstance(receipt.get("command_id"), str) and receipt.get("command_id")
        ]
        blocked = [receipt for receipt in valid_receipts if receipt.get("status") == "blocked"]
        failed = [
            receipt
            for receipt in valid_receipts
            if receipt.get("status") == "failed" and receipt.get("failure_classification") != "permission"
        ]
        issues: list[dict[str, Any]] = []
        for receipt in blocked:
            issues.append(
                {
                    "code": str(receipt.get("error") or "approval_blocked"),
                    "message": f"命令 {receipt.get('command_id')} 因审批或权限被阻断",
                    "severity": "HIGH",
                }
            )
        for receipt in failed:
            issues.append(
                {
                    "code": str(receipt.get("error") or "tool_failed"),
                    "message": f"命令 {receipt.get('command_id')} 执行失败",
                    "severity": "MEDIUM",
                }
            )

        ok = not issues
        risk_level = "LOW" if ok else ("HIGH" if blocked else "MEDIUM")
        return normalize_critic_review(
            {
                "schema_version": "critic_review.v1",
                "ok": ok,
                "risk_level": risk_level,
                "issues": issues,
                "require_human_approval": bool(blocked),
                "suggested_fixes": [
                    "补齐审批后重试阻断命令",
                    "修复失败工具的输入参数或依赖",
                ]
                if issues
                else [],
                "evidence": {
                    "fields": ["receipts", "final_output"],
                    "receipt_command_ids": receipt_command_ids,
                    "final_receipt_command_ids": final_output.get("receipt_command_ids", []),
                    "task_id": task.get("task_id"),
                    "plan_step_count": len(orchestrator.get("plan_steps", [])) if isinstance(orchestrator.get("plan_steps"), list) else 0,
                },
                "run_summary": {
                    "text": "执行后审查完成",
                    "key_points": [
                        f"receipt_count={len(valid_receipts)}",
                        f"blocked_count={len(blocked)}",
                        f"failed_count={len(failed)}",
                    ],
                    "receipt_command_ids": receipt_command_ids,
                },
            }
        )

    async def _generate_final_answer(self, task: dict[str, Any], history: list) -> dict[str, Any]:
        """生成评审结果."""
        from riskagent_backend.contracts import normalize_critic_review
        
        steps_summary = "\n".join([
            f"Thought: {s.thought}\nObservation: {s.observation}"
            for s in history
        ])
        
        prompt = f"""Based on your ReAct reasoning, generate the final review.

Task: {task}

Your reasoning chain:
{steps_summary}

Generate JSON with:
- ok: boolean
- risk_level: string
- issues: list
- require_human_approval: boolean
- suggested_fixes: list
- evidence: object"""

        result = await self._base_agent.ask_json(
            user_prompt=prompt,
            fallback={
                "schema_version": "critic_review.v1",
                "ok": True,
                "risk_level": "LOW",
                "issues": [],
                "require_human_approval": False,
                "suggested_fixes": [],
                "evidence": {"reviewed_plan": True},
            },
            max_tokens=512,
        )
        
        output = normalize_critic_review(result.output if isinstance(result.output, dict) else {})
        return output


class ProactiveSystemEngineerAgent(BaseProactiveAgent):
    """
    主动系统工程师 Agent.
    
    具备:
    - 后台监控:主动监控基础设施健康状态
    - ReAct 循环:动态分析系统问题
    - BDI 模型:维护系统状态信念
    """
    
    def __init__(self) -> None:
        super().__init__(
            name="system_engineer",
            system_prompt=self._build_system_prompt(),
            prompt_version=PROMPT_VERSION_SYSTEM_ENGINEER,
            policy_version=get_policy_version(),
            enable_background_monitor=True,
            monitor_interval_seconds=30,
        )
    
    def _build_system_prompt(self) -> str:
        return SYSTEM_ENGINEER_PROMPT

    def _init_desires(self) -> None:
        """初始化愿望."""
        self.add_desire("及时发现系统异常", priority=10)
        self.add_desire("准确诊断问题根因", priority=9)
        self.add_desire("提供可执行的修复建议", priority=8)

    async def _perceive_environment(self) -> None:
        """主动感知环境 - 通过 perception 数据源采集基础设施信号."""
        try:
            from riskagent_backend.perception.data_sources import (
                DockerDataSource,
                RedisDataSource,
                MySQLDataSource,
                PrometheusDataSource,
            )
            try:
                from riskagent_backend.perception.data_sources import K8sDataSource
            except ImportError:
                K8sDataSource = None

            # 环境检测: K8s 环境用 K8sDataSource, 否则用 DockerDataSource
            if K8sDataSource is not None and os.getenv("KUBERNETES_SERVICE_HOST"):
                infra_source = K8sDataSource()
            else:
                infra_source = DockerDataSource()

            filtered = self._collect_and_filter([
                infra_source,
                RedisDataSource(),
                MySQLDataSource(),
                PrometheusDataSource(),
            ])

            if not filtered:
                return

            # 升级检查
            event = self._escalation_manager.escalate(filtered)
            if event:
                self.add_belief(
                    content={
                        "event_id": event.event_id,
                        "severity": event.severity,
                        "source": event.source,
                        "description": event.description,
                        "signal_count": len(filtered),
                    },
                    source="perception_escalation",
                    confidence=0.9,
                )
                # critical 事件不再直接 remediate, 而是通过 _deliberate → _act →
                # start_from_event 走统一执行内核五道关卡路径
        except Exception as e:
            logger.warning(f"[system_engineer] 感知环境失败: {e}")

    async def analyze_task(
        self,
        *,
        task: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> ProactiveAgentResult:
        """分析任务(使用 ReAct 循环)."""
        return await self.run_with_react(
            task=task,
            context=context,
            max_tokens=512,
            max_steps=4,
        )

    async def _generate_final_answer(self, task: dict[str, Any], history: list) -> dict[str, Any]:
        """生成系统分析结果."""
        from riskagent_backend.contracts import (
            SYSTEM_ENGINEER_OUTPUT_SCHEMA_VERSION,
            normalize_system_engineer_output,
        )
        
        steps_summary = "\n".join([
            f"Thought: {s.thought}\nObservation: {s.observation}"
            for s in history
        ])
        
        prompt = f"""Based on your ReAct reasoning, generate the system analysis.

Task: {task}

Your reasoning chain:
{steps_summary}

Generate JSON with:
- system_issue: boolean
- reason: snake_case string
- summary: Chinese paragraph
- evidence: object
- findings: object
- recommendations: list"""

        result = await self._base_agent.ask_json(
            user_prompt=prompt,
            fallback={
                "schema_version": SYSTEM_ENGINEER_OUTPUT_SCHEMA_VERSION,
                "system_issue": False,
                "reason": "ok",
                "latency_ms": None,
                "summary": "系统状态正常",
                "evidence": {"fields": ["task"]},
                "findings": {},
                "recommendations": [],
            },
            max_tokens=512,
        )
        
        output = normalize_system_engineer_output(result.output if isinstance(result.output, dict) else {})
        return output


class ProactiveRiskAnalystAgent(BaseProactiveAgent):
    """
    主动风险分析师 Agent.
    
    具备:
    - 后台监控:主动监控风险指标
    - ReAct 循环:动态评估业务风险
    - BDI 模型:维护风险状态信念
    """
    
    def __init__(self) -> None:
        super().__init__(
            name="risk_analyst",
            system_prompt=self._build_system_prompt(),
            prompt_version=PROMPT_VERSION_RISK_ANALYST,
            policy_version=get_policy_version(),
            enable_background_monitor=True,
            monitor_interval_seconds=45,
        )
    
    def _build_system_prompt(self) -> str:
        return RISK_ANALYST_PROMPT

    def _init_desires(self) -> None:
        """初始化愿望."""
        self.add_desire("准确评估业务风险", priority=10)
        self.add_desire("识别关键风险因素", priority=9)
        self.add_desire("提供高置信度分析", priority=8)

    async def _perceive_environment(self) -> None:
        """主动感知环境 - 通过 MySQL 和 Prometheus 监控风险指标."""
        try:
            from riskagent_backend.perception.data_sources import (
                MySQLDataSource,
                PrometheusDataSource,
            )

            filtered = self._collect_and_filter([
                MySQLDataSource(),
                PrometheusDataSource(),
            ])

            if not filtered:
                return

            # 记录风险信号
            for sig in filtered:
                self.add_belief(
                    content={
                        "source": sig.source,
                        "metric": sig.metric,
                        "value": sig.value,
                        "severity": sig.severity.value,
                        "message": sig.message,
                    },
                    source="risk_perception",
                    confidence=0.8,
                )

            # 升级检查
            event = self._escalation_manager.escalate(filtered)
            if event:
                self.add_belief(
                    content={
                        "event_id": event.event_id,
                        "severity": event.severity,
                        "source": event.source,
                        "description": event.description,
                    },
                    source="risk_escalation",
                    confidence=0.9,
                )
        except Exception as e:
            logger.warning(f"[risk_analyst] 风险感知失败: {e}")

    async def analyze_task(
        self,
        *,
        task: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> ProactiveAgentResult:
        """分析任务(使用 ReAct 循环)."""
        return await self.run_with_react(
            task=task,
            context=context,
            max_tokens=512,
            max_steps=4,
        )

    async def _generate_final_answer(self, task: dict[str, Any], history: list) -> dict[str, Any]:
        """生成风险分析结果."""
        from riskagent_backend.contracts import (
            RISK_ANALYST_OUTPUT_SCHEMA_VERSION,
            normalize_risk_analyst_output,
        )
        
        steps_summary = "\n".join([
            f"Thought: {s.thought}\nObservation: {s.observation}"
            for s in history
        ])
        
        prompt = f"""Based on your ReAct reasoning, generate the risk analysis.

Task: {task}

Your reasoning chain:
{steps_summary}

Generate JSON with:
- report: Chinese paragraph
- key_facts: object
- confidence: number 0-1
- evidence: object"""

        result = await self._base_agent.ask_json(
            user_prompt=prompt,
            fallback={
                "schema_version": RISK_ANALYST_OUTPUT_SCHEMA_VERSION,
                "report": "风险分析已完成",
                "key_facts": {},
                "confidence": 0.7,
                "evidence": {"fields": ["task"]},
            },
            max_tokens=512,
        )
        
        output = normalize_risk_analyst_output(result.output if isinstance(result.output, dict) else {})
        return output


__all__ = [
    "ProactiveIntentAgent",
    "ProactiveOrchestratorAgent",
    "ProactiveCriticAgent",
    "ProactiveSystemEngineerAgent",
    "ProactiveRiskAnalystAgent",
]
