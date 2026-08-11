"""编排层纯函数契约测试 (workflow_events / workflow_result_builder)."""

from __future__ import annotations

from riskagent_backend.orchestration.workflow_events import (
    build_task_from_event,
    requires_manual_approval,
)
from riskagent_backend.orchestration.workflow_result_builder import (
    build_approval_trace_items,
    build_blocked_event_result,
    build_invalid_event_result,
    merge_final_with_critic,
    normalize_critic_final_output,
)


class TestBuildTaskFromEvent:
    def test_derives_defaults_from_event(self):
        event = {
            "event_id": "evt-1",
            "event_type": "risk_breach_detected",
            "source_agent": "system_engineer",
            "payload": {"content": "处理告警"},
        }
        task = build_task_from_event(
            event=event,
            route_decision={"reason": "risk route"},
        )
        assert task["task_id"] == "evt-1"
        assert task["session_id"] == "event_system_engineer"
        assert task["source"] == "system_event"
        assert task["payload"]["content"] == "处理告警"
        assert task["payload"]["trigger_event_id"] == "evt-1"
        assert task["payload"]["trigger_reason"] == "risk route"
        assert task["trigger_event_id"] == "evt-1"
        assert task["trigger_evidence"]["event_type"] == "risk_breach_detected"

    def test_prefers_payload_task_over_defaults(self):
        event = {
            "event_id": "evt-2",
            "payload": {
                "task": {"task_id": "custom-id", "payload": {"content": "已存在"}},
            },
        }
        task = build_task_from_event(event=event, route_decision={})
        assert task["task_id"] == "custom-id"
        assert task["payload"]["content"] == "已存在"
        assert task["source"] == "system_event"

    def test_missing_payload_falls_back_to_generic_content(self):
        event = {"event_id": "evt-3", "event_type": "task_created"}
        task = build_task_from_event(event=event, route_decision={})
        assert task["payload"]["content"] == "处理系统事件 task_created"


class TestRequiresManualApproval:
    def test_pending_approval_record_blocks(self):
        assert requires_manual_approval(
            critic_output={},
            receipts=None,
            approval_records=[{"approval_state": "pending"}],
        ) is True

    def test_approved_record_does_not_block(self):
        assert requires_manual_approval(
            critic_output={},
            receipts=None,
            approval_records=[{"approval_state": "approved"}],
        ) is False

    def test_rejected_receipt_blocks(self):
        assert requires_manual_approval(
            critic_output={},
            receipts=[{"approval_state": "rejected"}],
            approval_records=None,
        ) is True

    def test_approved_receipt_passes(self):
        assert requires_manual_approval(
            critic_output={},
            receipts=[{"approval_state": "approved"}],
            approval_records=None,
        ) is False

    def test_critic_require_human_respects_auto_approve_env(self, monkeypatch):
        monkeypatch.setenv("HITL_AUTO_APPROVE", "0")
        assert requires_manual_approval(
            critic_output={"require_human_approval": True},
            receipts=None,
            approval_records=None,
        ) is True
        monkeypatch.setenv("HITL_AUTO_APPROVE", "1")
        assert requires_manual_approval(
            critic_output={"require_human_approval": True},
            receipts=None,
            approval_records=None,
        ) is False


class TestEventResultBuilders:
    def test_blocked_result_contract(self):
        result = build_blocked_event_result(
            event={"event_id": "evt-9", "payload": {"content": "x"}},
            run_context={"run_id": "run-1", "entry_type": "event", "task_id": "t-1"},
            reason="budget_exceeded",
            budget_evidence={"active_runs": 3},
        )
        assert result["status"] == "blocked"
        assert result["run_id"] == "run-1"
        assert result["task"]["source"] == "system_event"
        assert result["errors"] == ["budget_exceeded"]
        assert result["trigger"]["event_id"] == "evt-9"
        assert result["governance"]["proactive_budget"]["allowed"] is False

    def test_invalid_result_contract(self):
        result = build_invalid_event_result(
            event={"event_id": "evt-8", "event_type": "unknown"},
            run_context={"run_id": "run-2"},
            reason="bad_event",
        )
        assert result["status"] == "failed"
        assert result["errors"] == ["bad_event"]
        assert result["trigger"]["evidence"] == {"event_type": "unknown"}


class TestApprovalTrace:
    def test_records_take_priority(self):
        items = build_approval_trace_items(
            approval_records=[
                {
                    "approval_id": "ap-1",
                    "level": "node",
                    "step_id": "s1",
                    "state": "pending",
                    "tool_name": "submit_alerts",
                }
            ],
            receipts=None,
        )
        assert len(items) == 1
        assert items[0]["approval_id"] == "ap-1"
        assert items[0]["approval_state"] == "pending"
        assert items[0]["approval_trace"]["current_state"] == "pending"

    def test_falls_back_to_side_effect_receipts(self):
        items = build_approval_trace_items(
            approval_records=None,
            receipts=[
                {"command_id": "cmd-1", "side_effect": True, "approval_state": "approved"},
                {"command_id": "cmd-2", "side_effect": False},
            ],
        )
        assert len(items) == 1
        assert items[0]["approval_id"] == "command:cmd-1"
        assert items[0]["approval_state"] == "approved"

    def test_empty_inputs_return_empty(self):
        assert build_approval_trace_items(approval_records=None, receipts=None) == []


class TestCriticFinalNormalization:
    def test_injects_receipt_ids_into_evidence_and_summary(self):
        normalized = normalize_critic_final_output(
            critic_output={"ok": True, "evidence": {"fields": ["a"]}},
            receipts=[{"command_id": "cmd-1"}, {"command_id": 42}],
        )
        assert normalized["evidence"]["receipt_command_ids"] == ["cmd-1"]
        assert normalized["run_summary"]["receipt_command_ids"] == ["cmd-1"]
        assert normalized["ok"] is True

    def test_defaults_missing_fields(self):
        normalized = normalize_critic_final_output(critic_output={}, receipts=None)
        assert normalized["ok"] is True
        assert normalized["issues"] == []
        assert normalized["suggested_fixes"] == []
        assert normalized["evidence"]["receipt_command_ids"] == []

    def test_merge_final_with_critic_carries_summary(self):
        merged = merge_final_with_critic(
            final_output={"answer": "done"},
            critic_final={
                "run_summary": {"text": "ok"},
                "evidence": {"receipt_command_ids": ["cmd-1"]},
            },
        )
        assert merged["answer"] == "done"
        assert merged["critic_run_summary"] == {"text": "ok"}
        assert merged["receipt_command_ids"] == ["cmd-1"]
