"""自主处置链路 - 简单处置 + 人类升级 + 结果追踪与 Skill 沉淀 (16.4.1 + 16.4.2 + 16.4.3)."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from riskagent_backend.perception.signals import PerceptionSignal, SignalSeverity
from riskagent_backend.perception.escalation import SystemEvent

logger = logging.getLogger(__name__)


class RemediationAction(str, Enum):
    """处置动作类型."""
    LOG_ALERT = "log_alert"           # P6: 记录告警
    LOG_NOTIFICATION = "log_notification"  # P6: 记录通知
    RESTART_SUGGESTION = "restart_suggestion"  # P6: 重启建议
    ASK_HUMAN = "ask_human"           # P7: 人类升级
    NO_ACTION = "no_action"           # 无需处置


class RemediationResult:
    """处置结果记录 (P9: 追踪与沉淀)."""

    def __init__(
        self,
        *,
        result_id: str | None = None,
        action: RemediationAction = RemediationAction.NO_ACTION,
        event_id: str = "",
        success: bool = True,
        description: str = "",
        skill_created: bool = False,
        timestamp: datetime | None = None,
    ) -> None:
        self.result_id = result_id or str(uuid.uuid4())
        self.action = action
        self.event_id = event_id
        self.success = success
        self.description = description
        self.skill_created = skill_created
        self.timestamp = timestamp or datetime.now(timezone.utc)

    def to_dict(self) -> dict[str, Any]:
        return {
            "result_id": self.result_id,
            "action": self.action.value,
            "event_id": self.event_id,
            "success": self.success,
            "description": self.description,
            "skill_created": self.skill_created,
            "timestamp": self.timestamp.isoformat(),
        }


class RemediationManager:
    """
    自主处置管理器.

    P6 (16.4.1): 简单自主处置 - 低风险操作 (记录告警/通知/重启建议)
    P7 (16.4.2): 复杂问题人类升级 - 通过 ask_human 节点升级
    P9 (16.4.3): 处置结果追踪与 Skill 沉淀
    """

    def __init__(self) -> None:
        self._results: list[RemediationResult] = []
        self._total_actions = 0
        self._total_successful = 0
        self._total_human_escalations = 0
        self._total_skills_created = 0
        self._skill_patterns: dict[str, dict[str, Any]] = {}

    def remediate(self, event: SystemEvent) -> RemediationResult:
        """
        根据事件严重级别选择处置动作.

        - critical: 先尝试低风险自主处置，然后升级人类
        - warning: 低风险自主处置 (记录告警/通知)
        """
        self._total_actions += 1

        if event.severity == "critical":
            # P6: 先执行低风险自主处置
            result = self._execute_low_risk_action(event)
            # P7: 同时生成人类升级请求
            self._total_human_escalations += 1
            logger.info(
                f"Critical event {event.event_id} escalated to human. "
                f"Auto-action: {result.action.value}"
            )
            result.description = f"{result.description}; escalated to human for review"
            return result

        elif event.severity == "warning":
            # P6: 低风险自主处置
            result = self._execute_low_risk_action(event)
            return result

        else:
            result = RemediationResult(
                action=RemediationAction.NO_ACTION,
                event_id=event.event_id,
                description="No action needed",
            )
            self._results.append(result)
            return result

    def _execute_low_risk_action(self, event: SystemEvent) -> RemediationResult:
        """执行低风险自主处置 (P6: 16.4.1)."""
        # 根据信号来源选择动作
        signals = event.signals
        primary_signal = signals[0] if signals else None

        if primary_signal and primary_signal.source == "docker":
            if primary_signal.metric == "container_status" and primary_signal.value in ("exited", "dead"):
                action = RemediationAction.RESTART_SUGGESTION
                desc = f"Container {primary_signal.context.get('container_name', 'unknown')} exited. Suggesting restart."
            else:
                action = RemediationAction.LOG_ALERT
                desc = f"Docker alert: {primary_signal.metric}={primary_signal.value}"
        elif primary_signal and primary_signal.source == "redis":
            action = RemediationAction.LOG_ALERT
            desc = f"Redis alert: {primary_signal.metric}={primary_signal.value}"
        elif primary_signal and primary_signal.source == "mysql":
            action = RemediationAction.LOG_NOTIFICATION
            desc = f"MySQL alert: {primary_signal.metric}={primary_signal.value}"
        else:
            action = RemediationAction.LOG_ALERT
            desc = event.description

        result = RemediationResult(
            action=action,
            event_id=event.event_id,
            success=True,
            description=desc,
        )

        # 执行动作
        logger.info(f"Remediation action: {action.value} - {desc}")

        self._results.append(result)
        self._total_successful += 1

        # P9: 沉淀经验
        self._try_create_skill(event, result)

        return result

    def _try_create_skill(self, event: SystemEvent, result: RemediationResult) -> None:
        """P9 (16.4.3): 从成功的处置中提取 Skill 模式."""
        if not result.success:
            return

        # 以信号来源+指标作为模式 key
        primary = event.signals[0] if event.signals else None
        if not primary:
            return

        pattern_key = f"{primary.source}_{primary.metric}_{primary.value}"
        if pattern_key not in self._skill_patterns:
            self._skill_patterns[pattern_key] = {
                "source": primary.source,
                "metric": primary.metric,
                "value": primary.value,
                "action": result.action.value,
                "first_seen": result.timestamp.isoformat(),
                "occurrence_count": 0,
            }
            self._total_skills_created += 1
            logger.info(f"New skill pattern created: {pattern_key} -> {result.action.value}")

        self._skill_patterns[pattern_key]["occurrence_count"] += 1
        result.skill_created = True

    def get_results(self) -> list[RemediationResult]:
        """获取处置结果列表."""
        return list(self._results)

    def get_skill_patterns(self) -> dict[str, dict[str, Any]]:
        """获取沉淀的 Skill 模式."""
        return dict(self._skill_patterns)

    def get_stats(self) -> dict[str, Any]:
        """获取处置统计."""
        return {
            "total_actions": self._total_actions,
            "total_successful": self._total_successful,
            "total_human_escalations": self._total_human_escalations,
            "total_skills_created": self._total_skills_created,
            "skill_patterns_count": len(self._skill_patterns),
            "results_count": len(self._results),
        }
