"""场景测试: 数据库连接池耗尽 -> 7x24 监控检测 -> 修复 -> run trace 记录.

模拟 MySQL 数据库连接池耗尽的完整链路:
1. MySQLDataSource 采集到 threads_connected 超阈值 (CRITICAL) + slow_queries 激增 (WARNING)
2. SystemEngineerAgent._perceive_environment 采集信号 (复用 _collect_and_filter + EscalationManager)
3. EscalationManager 升级为 critical SystemEvent
4. _deliberate 形成 intention (severity=critical -> priority=high)
5. _act 构造 proactive event (RISK_BREACH_DETECTED) 并调用 start_from_event
6. ProactiveWorkflow 处理事件, 记录 run trace
7. 验证 run trace 包含完整链路记录

依赖: 全部 mock, 不依赖真实 MySQL/Redis/ChromaDB/LLM API key.
"""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from typing import Any

import pytest

from riskmonitor_multiagent.contracts.event import EventType, new_event
from riskmonitor_multiagent.contracts.run_trace import (
    RUN_TRACE_SCHEMA_VERSION,
    validate_run_trace,
)
from riskmonitor_multiagent.observability.run_trace import (
    RunTraceStore,
    build_run_trace_snapshot,
)
from riskmonitor_multiagent.orchestration.proactive_workflow import (
    ProactiveMultiAgentWorkflow,
)
from riskmonitor_multiagent.perception.escalation import EscalationManager
from riskmonitor_multiagent.perception.rules import FilterRule, PerceptionFilterEngine
from riskmonitor_multiagent.perception.signals import PerceptionSignal, SignalSeverity
from riskmonitor_multiagent.proactive_agents.base import (
    BaseProactiveAgent,
    _PERCEPTION_SOURCES,
)
from riskmonitor_multiagent.skills import SkillProposer, SkillStore


# =====================================================================================
# 辅助: Mock MySQL 数据源
# =====================================================================================

class _MockMySQLDataSource:
    """模拟 MySQL 连接池耗尽的数据源.

    复刻真实 MySQLDataSource.collect() 的签名, 返回两条异常信号:
    - threads_connected=150 (超过阈值 100)
    - slow_queries=25 (超过阈值 10)

    信号初始 severity=INFO, 由 PerceptionFilterEngine 按规则标注最终级别.
    """

    def __init__(self, *, threads: int = 150, slow: int = 25) -> None:
        self._threads = threads
        self._slow = slow

    def collect(self) -> list[PerceptionSignal]:
        return [
            PerceptionSignal(
                source="mysql",
                metric="threads_connected",
                value=self._threads,
                threshold=100,
                severity=SignalSeverity.INFO,
                message="数据库连接池耗尽",
                context={
                    "pool_size": 10,
                    "max_overflow": 20,
                    "checkedout": self._threads,
                },
            ),
            PerceptionSignal(
                source="mysql",
                metric="slow_queries",
                value=self._slow,
                threshold=10,
                severity=SignalSeverity.INFO,
                message="慢查询激增",
                context={"avg_query_time_ms": 5000},
            ),
        ]


def _build_db_pool_rules() -> list[FilterRule]:
    """构建数据库连接池耗尽场景的过滤规则.

    与默认规则集的差异: threads_connected>100 升级为 CRITICAL
    (默认规则集中该指标仅 WARNING). slow_queries>10 保持 WARNING.
    message 留空以触发 fallback, fallback 会自动拼接 metric/value/threshold,
    便于在 trigger_evidence 中验证 MySQL 信号数据.
    """
    return [
        FilterRule(
            name="mysql_threads_connected_critical",
            source="mysql",
            metric="threads_connected",
            predicate=lambda v: isinstance(v, (int, float)) and v > 100,
            severity=SignalSeverity.CRITICAL,
            threshold=100,
            message="",
        ),
        FilterRule(
            name="mysql_slow_queries_warning",
            source="mysql",
            metric="slow_queries",
            predicate=lambda v: isinstance(v, (int, float)) and v > 10,
            severity=SignalSeverity.WARNING,
            threshold=10,
            message="",
        ),
    ]


class _DbPoolExhaustedAgent(BaseProactiveAgent):
    """模拟 SystemEngineerAgent, 使用 Mock MySQL 数据源 + 自定义过滤规则.

    覆盖 _filter_engine / _escalation_manager 属性以注入隔离实例,
    避免污染全局懒加载的单例. _perceive_environment 复刻
    ProactiveSystemEngineerAgent 的 escalate -> add_belief 路径,
    并额外携带原始信号列表用于 trace 证据.
    """

    def __init__(self) -> None:
        super().__init__(
            name="system_engineer",
            system_prompt="db pool exhausted scenario test",
            enable_background_monitor=False,
        )
        self._mock_mysql = _MockMySQLDataSource()
        self._custom_filter_engine = PerceptionFilterEngine(_build_db_pool_rules())
        self._custom_escalation = EscalationManager()
        self.last_filtered_signals: list[PerceptionSignal] = []
        self.last_event: Any = None

    @property
    def _filter_engine(self) -> PerceptionFilterEngine:
        return self._custom_filter_engine

    @property
    def _escalation_manager(self) -> EscalationManager:
        return self._custom_escalation

    async def _perceive_environment(self) -> None:
        filtered = self._collect_and_filter([self._mock_mysql])
        self.last_filtered_signals = list(filtered)
        if not filtered:
            return
        event = self._escalation_manager.escalate(filtered)
        self.last_event = event
        if event is None:
            return
        self.add_belief(
            content={
                "event_id": event.event_id,
                "severity": event.severity,
                "source": event.source,
                "description": event.description,
                "signal_count": len(filtered),
                "signals": [sig.to_log_dict() for sig in filtered],
            },
            source="perception_escalation",
            confidence=0.9,
        )


class _FakeWorkflow:
    """捕获 start_from_event 参数的假工作流, 返回 status=completed."""

    def __init__(self, captured: dict[str, Any]) -> None:
        self._captured = captured

    async def start_from_event(
        self,
        *,
        event: dict[str, Any],
        candidate_agents: list[str] | None = None,
    ) -> dict[str, Any]:
        self._captured["event"] = event
        self._captured["candidate_agents"] = list(candidate_agents or [])
        self._captured["event_type"] = event.get("event_type")
        self._captured["priority"] = event.get("priority")
        self._captured["source_agent"] = event.get("source_agent")
        self._captured["payload"] = event.get("payload")
        return {
            "status": "completed",
            "run_id": "scenario_db_pool_run",
            "entry_type": "system_event",
            "task_id": (event.get("payload") or {}).get("task_id"),
            "final_output": {"remediation": "expanded_connection_pool"},
            "errors": [],
        }


class _NoopPersistence:
    """空操作持久化后端, 避免 SkillStore.create 触发真实 MySQL 落盘."""

    async def persist_skill(self, skill: dict[str, Any]) -> bool:
        return True

    async def load_skills(self, *, status: str | None = None) -> list[dict[str, Any]]:
        return []

    async def persist_memory_entry(self, entry: dict[str, Any]) -> bool:
        return True

    async def batch_persist_memory(self, entries: list[dict[str, Any]]) -> int:
        return 0

    async def load_memory_entries(self, **kwargs: Any) -> list[dict[str, Any]]:
        return []

    async def health_check(self) -> bool:
        return True

    async def close(self) -> None:
        pass


def _build_db_pool_result(event: dict[str, Any]) -> dict[str, Any]:
    """构造一个模拟 workflow 完成后的 result dict, 用于 build_run_trace_snapshot."""
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    return {
        "status": "completed",
        "run_id": "scenario_db_pool_exhausted_run",
        "entry_type": "system_event",
        "task_id": payload.get("task_id") or "proactive_db_pool",
        "run_context": {
            "entry_type": "system_event",
            "trigger_event_id": event.get("event_id"),
            "trigger_reason": "db_pool_exhausted",
        },
        "route_decision": {
            "selected_agent": "system_engineer",
            "rule_name": "risk_breach_detected",
            "decision_source": "moderator",
            "timestamp_ms": int(time.time() * 1000),
        },
        "intent": {"primary_intent_type": "remediate"},
        "task_graph": {
            "schema_version": "task_graph.v1",
            "nodes": [
                {"step_id": "s1", "kind": "delegate"},
                {"step_id": "s2", "kind": "delegate", "parent_id": "s1"},
            ],
            "edges": [{"from_step_id": "s1", "to_step_id": "s2", "condition": "always"}],
        },
        "orchestrator_plan": {
            "plan_steps": [
                {
                    "step_id": "s1",
                    "kind": "delegate",
                    "target_agent": "system_engineer",
                    "instruction": "诊断 MySQL 连接池耗尽根因",
                    "expected_outcome": "root_cause_identified",
                },
                {
                    "step_id": "s2",
                    "kind": "delegate",
                    "target_agent": "risk_analyst",
                    "instruction": "评估连接池耗尽对业务的影响",
                    "expected_outcome": "business_impact_assessed",
                },
            ],
        },
        "critic_plan": {"ok": True, "issues": []},
        "task_graph_execution": {
            "status": "completed",
            "trace": [
                {
                    "step_id": "s1",
                    "kind": "delegate",
                    "status": "completed",
                    "started_at_ms": int(time.time() * 1000),
                    "finished_at_ms": int(time.time() * 1000) + 100,
                },
            ],
        },
        "receipts": [
            {
                "command_id": "cmd_db_pool_alert",
                "tool_name": "submit_alerts",
                "step_id": "s1",
                "status": "completed",
                "approval_state": "approved",
            },
        ],
        "approval_trace": [],
        "final_output": {
            "remediation": "expanded_connection_pool",
            "root_cause": "pool_exhaustion",
            "receipt_command_ids": ["cmd_db_pool_alert"],
        },
        "errors": [],
        "latency_ms": 1500.0,
        "tokens_total": 0,
    }


# =====================================================================================
# 场景 1: 检测链路 - perceive -> deliberate -> act
# =====================================================================================

@pytest.mark.asyncio
async def test_db_pool_exhausted_detection(monkeypatch: pytest.MonkeyPatch) -> None:
    """验证 MySQL 连接池耗尽被检测并升级为 critical SystemEvent, 形成 high priority intention."""
    agent = _DbPoolExhaustedAgent()

    # _perceive_environment: 采集 -> 过滤 -> 升级
    await agent._perceive_environment()

    # 验证过滤后的信号: threads_connected=CRITICAL, slow_queries=WARNING
    filtered = agent.last_filtered_signals
    assert len(filtered) == 2
    threads_sig = next(s for s in filtered if s.metric == "threads_connected")
    slow_sig = next(s for s in filtered if s.metric == "slow_queries")
    assert threads_sig.severity == SignalSeverity.CRITICAL
    assert threads_sig.value == 150
    assert threads_sig.threshold == 100
    assert slow_sig.severity == SignalSeverity.WARNING
    assert slow_sig.value == 25
    assert slow_sig.threshold == 10

    # 验证 EscalationManager 升级为 critical SystemEvent
    event = agent.last_event
    assert event is not None
    assert event.severity == "critical"
    assert event.event_type == "perception_alert"
    # 描述只包含最高级别 (CRITICAL) 信号: threads_connected
    assert "threads_connected" in event.description
    assert "150" in event.description
    # WARNING 级别的 slow_queries 不在 critical-only 描述中, 但已被升级到 event.signals
    assert len(event.signals) == 2
    assert any(s.metric == "threads_connected" for s in event.signals)
    assert any(s.metric == "slow_queries" for s in event.signals)

    # 验证 belief 已注入, source 属于 _PERCEPTION_SOURCES
    beliefs = agent.get_beliefs(source="perception_escalation")
    assert len(beliefs) == 1
    assert beliefs[0].source in _PERCEPTION_SOURCES
    assert beliefs[0].content["severity"] == "critical"

    # _deliberate: severity=critical -> priority=high, 形成 intention
    await agent._deliberate()
    pending = agent.get_pending_intentions()
    assert len(pending) == 1
    intention = pending[0]
    assert intention.target_agent == "orchestrator"
    assert intention.tool_name == "submit_alerts"
    assert intention.tool_params["severity"] == "critical"
    assert intention.tool_params["priority"] == "high"
    assert "threads_connected" in intention.tool_params["message"]
    assert "150" in intention.tool_params["message"]
    # belief content 携带完整 MySQL 信号列表 (含 WARNING 的 slow_queries)
    belief_signals = beliefs[0].content["signals"]
    assert len(belief_signals) == 2
    assert any(s["metric"] == "slow_queries" and s["value"] == 25 for s in belief_signals)

    # _act: 构造 RISK_BREACH_DETECTED 事件, 通过 _FakeWorkflow 捕获
    captured: dict[str, Any] = {}
    monkeypatch.setattr(
        "riskmonitor_multiagent.orchestration.proactive_workflow.get_proactive_workflow",
        lambda: _FakeWorkflow(captured),
    )
    await agent._act()

    assert captured.get("event_type") == EventType.RISK_BREACH_DETECTED.value
    assert captured.get("priority") == "high"
    assert captured.get("source_agent") == "system_engineer"
    assert "orchestrator" in captured.get("candidate_agents", [])


# =====================================================================================
# 场景 2: 完整链路 + 事件结构验证
# =====================================================================================

@pytest.mark.asyncio
async def test_db_pool_exhausted_full_chain_with_trace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """完整链路 perceive -> deliberate -> act -> start_from_event, 验证事件结构."""
    agent = _DbPoolExhaustedAgent()
    captured: dict[str, Any] = {}
    monkeypatch.setattr(
        "riskmonitor_multiagent.orchestration.proactive_workflow.get_proactive_workflow",
        lambda: _FakeWorkflow(captured),
    )

    # 完整链路
    await agent._perceive_environment()
    await agent._deliberate()
    await agent._act()

    assert "event" in captured, "start_from_event 未被调用"
    event = captured["event"]

    # event_type / priority / source_agent
    assert event["event_type"] == EventType.RISK_BREACH_DETECTED.value
    assert event["priority"] == "high"
    assert event["source_agent"] == "system_engineer"
    assert event["target_agent"] == "orchestrator"

    # task_payload (event.payload) 结构
    payload = event["payload"]
    assert payload is not None
    assert payload["task_id"].startswith("proactive_")
    assert payload["session_id"] == "proactive_system_engineer"
    assert payload["target_agent"] == "orchestrator"
    assert payload["content"] == payload["trigger_reason"]

    # trigger_reason 包含 critical 信号异常描述
    assert "critical" in payload["trigger_reason"]
    assert "perception_escalation" in payload["trigger_reason"]

    # trigger_evidence 包含 MySQL 信号数据
    trigger_evidence = payload["trigger_evidence"]
    assert trigger_evidence["source_agent"] == "system_engineer"
    assert trigger_evidence["tool_name"] == "submit_alerts"
    tool_params = trigger_evidence["tool_params"]
    assert tool_params["severity"] == "critical"
    assert tool_params["priority"] == "high"
    assert tool_params["alert_type"] == "system_error"
    # message 内携带 MySQL 信号数据 (CRITICAL 级别的 threads_connected=150)
    # 注: EscalationManager 描述只含最高级别信号, slow_queries(WARNING) 在 belief.signals 中
    msg = tool_params["message"]
    assert "threads_connected" in msg
    assert "150" in msg

    # candidate_agents 去重且包含 orchestrator / critic
    assert "orchestrator" in captured["candidate_agents"]
    assert "critic" in captured["candidate_agents"]

    # 所有 intention 应已 completed
    pending = agent.get_pending_intentions()
    assert len(pending) == 0


# =====================================================================================
# 场景 3: 修复闭环 - SkillProposer 从成功处置中提取 skill 模式
# =====================================================================================

@pytest.mark.asyncio
async def test_db_pool_exhausted_remediation() -> None:
    """验证 SkillProposer 从成功处置中提取 skill 模式, pattern_key 含 mysql/threads_connected/critical."""
    skill_store = SkillStore()
    skill_store._set_persistence(_NoopPersistence())  # type: ignore[attr-defined]
    proposer = SkillProposer(skill_store, confidence_threshold=0.85)

    # 构造任务: tags 携带 mysql/threads_connected/critical 三个关键词
    task: dict[str, Any] = {
        "task_id": "proactive_db_pool_remediation",
        "intent": "db_connection_pool_remediation",
        # 不设置 category, 让 _build_tags 落到 tags 字段
        "content": {
            "tags": ["mysql", "threads_connected", "critical"],
            "applicable_conditions": ["mysql/threads_connected/critical"],
        },
        "payload": {"content": "数据库连接池耗尽处置"},
    }
    critic_final = {
        "ok": True,
        "confidence": 0.95,
        "risk_level": "LOW",
        "issues": [],
    }
    orchestrator_output = {
        "plan_steps": [
            {
                "step_id": "s1",
                "kind": "delegate",
                "target_agent": "system_engineer",
                "instruction": "诊断连接池耗尽根因",
                "expected_outcome": "root_cause_identified",
            },
            {
                "step_id": "s2",
                "kind": "delegate",
                "target_agent": "risk_analyst",
                "instruction": "评估业务影响",
                "expected_outcome": "business_impact_assessed",
            },
            {
                "step_id": "s3",
                "kind": "finalize",
                "instruction": "汇总修复结论",
                "expected_outcome": "remediation_completed",
            },
        ],
    }

    proposal = await proposer.propose(
        run_id="scenario_db_pool_remediation",
        task=task,
        critic_final=critic_final,
        orchestrator_output=orchestrator_output,
        receipts=[
            {
                "command_id": "cmd_db_pool_alert",
                "tool_name": "submit_alerts",
                "step_id": "s1",
                "status": "completed",
                "approval_state": "approved",
            },
        ],
    )

    # confidence=0.95 >= 阈值, 应创建或更新 skill
    assert proposal["action"] in {"created", "updated"}
    assert proposal["skill_id"] is not None

    skill = proposal["skill"]
    assert skill["name"] == "db_connection_pool_remediation"
    assert skill["confidence"] == 0.95
    assert skill["status"] == "active"

    # pattern_key 由 tags 拼接, 包含 mysql/threads_connected/critical
    pattern_key = "/".join(skill["tags"])
    assert "mysql" in pattern_key
    assert "threads_connected" in pattern_key
    assert "critical" in pattern_key
    assert "mysql/threads_connected/critical" == pattern_key

    # applicable_conditions 同样携带 pattern_key
    assert "mysql/threads_connected/critical" in skill["applicable_conditions"]

    # steps 从 orchestrator_output plan_steps 提取
    assert len(skill["steps"]) == 3
    descriptions = [s["description"] for s in skill["steps"]]
    assert "诊断连接池耗尽根因" in descriptions

    # failure_boundary 由 critic_final 推导
    assert skill["failure_boundary"]


# =====================================================================================
# 场景 4: run trace 持久化与校验
# =====================================================================================

@pytest.mark.asyncio
async def test_db_pool_exhausted_run_trace(tmp_path: Path) -> None:
    """使用真实 RunTraceStore (临时目录), 验证 trace 文件结构与内容."""
    # 通过 agent 感知->思考链路构造真实的 proactive event 作为 source_event
    agent = _DbPoolExhaustedAgent()
    await agent._perceive_environment()
    await agent._deliberate()
    pending = agent.get_pending_intentions()
    assert len(pending) == 1
    proactive_event = agent._build_proactive_event(intention=pending[0])

    # 模拟 workflow 完成后的 result
    result = _build_db_pool_result(proactive_event)

    # 使用临时目录的 RunTraceStore, 避免污染 results/run_traces/
    temp_store = RunTraceStore(base_dir=str(tmp_path))

    # 通过真实 ProactiveMultiAgentWorkflow._record_run_trace_snapshot 记录 trace
    # (复用 message_bus.get_related_event_history 的真实调用, 对未知 run_id 返回空)
    workflow = ProactiveMultiAgentWorkflow()
    workflow._run_trace_store = temp_store  # type: ignore[attr-defined]
    workflow._record_run_trace_snapshot(
        result=result,
        source_event=proactive_event,
    )

    # 验证 trace 文件写入临时目录
    run_id = result["run_id"]
    trace_path = temp_store.get_snapshot_path(run_id)
    assert trace_path.exists(), f"trace 文件未写入: {trace_path}"

    payload = json.loads(trace_path.read_text(encoding="utf-8"))

    # 验证 trace 内容
    assert payload["schema_version"] == RUN_TRACE_SCHEMA_VERSION
    assert payload["status"] in {"completed", "failed"}
    assert payload["status"] == "completed"
    assert payload["run_id"] == run_id
    assert payload["entry_type"] == "system_event"
    assert isinstance(payload["entries"], list) and len(payload["entries"]) > 0
    assert payload["summary"]["entry_count"] > 0

    # 验证 trace 通过契约校验
    is_valid, errors = validate_run_trace(payload)
    assert is_valid, f"run trace 校验失败: {errors}"

    # 验证关键 trace_type 存在
    trace_types = {entry["trace_type"] for entry in payload["entries"]}
    assert "task" in trace_types
    assert "version_snapshot" in trace_types
    assert "source_event" in trace_types
    assert "run_finished" in trace_types

    # source_event 条目应携带 RISK_BREACH_DETECTED
    source_entry = next(
        e for e in payload["entries"] if e["trace_type"] == "source_event"
    )
    assert source_entry["summary"]["event_type"] == EventType.RISK_BREACH_DETECTED.value
    assert source_entry["summary"]["source_agent"] == "system_engineer"

    # 将 trace 文件复制一份到 results/run_traces/ 供查看
    project_root = Path(__file__).resolve().parents[2]
    run_traces_dir = project_root / "results" / "run_traces"
    run_traces_dir.mkdir(parents=True, exist_ok=True)
    timestamp = int(time.time())
    dest_filename = f"scenario_db_pool_exhausted_{timestamp}.json"
    dest_path = run_traces_dir / dest_filename
    shutil.copyfile(trace_path, dest_path)

    print(f"\n[scenario] db pool exhausted run trace saved to: {dest_path}")
    print(f"[scenario] temp trace path: {trace_path}")
    assert dest_path.exists()
