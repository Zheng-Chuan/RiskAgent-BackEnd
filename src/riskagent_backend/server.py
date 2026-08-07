#!/usr/bin/env python3
"""
RiskAgent-BackEnd 服务端
用于金融衍生品风险管理的 MCP 服务
"""

from __future__ import annotations

import json
import os
import signal
import time
from pathlib import Path

from dotenv import load_dotenv
from mcp.server import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse

from riskagent_backend.data_access.health_checks import check_mysql_ready
from riskagent_backend.services import readiness_service
from riskagent_backend.services.logging_service import configure_logging
from riskagent_backend.services.prometheus_metrics_service import (
    generate_prometheus_metrics,
)
from riskagent_backend.services.rest_bff_service import get_rest_bff_service
from riskagent_backend.services.auth_service import is_authorized
from riskagent_backend.resources.mcp_resources import register_resources
from riskagent_backend.prompts.mcp_prompts import register_prompts
from riskagent_backend.tools import mcp_tools as tools
from riskagent_backend.proactive_agents import (
    ProactiveIntentAgent,
    ProactiveOrchestratorAgent,
    ProactiveCriticAgent,
    ProactiveSystemEngineerAgent,
    ProactiveRiskAnalystAgent,
)
import asyncio
import logging

logger = logging.getLogger(__name__)

query_all_positions = tools.query_all_positions
query_positions_by_trader = tools.query_positions_by_trader
query_positions_by_desk = tools.query_positions_by_desk
calculate_total_delta = tools.calculate_total_delta
monitor_desk_exposure = tools.monitor_desk_exposure
get_service_metrics = tools.get_service_metrics


# 加载环境变量
# 从项目目录加载 .env, 不依赖当前工作目录
_repo_root = Path(__file__).resolve().parents[2]
load_dotenv(dotenv_path=_repo_root / ".env")

configure_logging()

_server_name = os.getenv("MCP_SERVER_NAME", "RiskAgent BackEnd").strip()
# 显式传入 host，确保 K8s 探针可通过 Pod IP 访问
# FastMCP.__init__ 默认 host="127.0.0.1"，会覆盖 FASTMCP_HOST 环境变量
_server_host = os.getenv("FASTMCP_HOST", "0.0.0.0").strip() or "0.0.0.0"
_server_port = int(os.getenv("FASTMCP_PORT", "8000").strip() or "8000")
mcp = FastMCP(
    _server_name or "RiskAgent BackEnd",
    host=_server_host,
    port=_server_port,
)
tools.register_tools(mcp)
register_resources(mcp)
register_prompts(mcp)

# P0: 常驻感知守护进程
_proactive_agents: list = []

async def start_proactive_monitors() -> None:
    """启动常驻感知守护进程 (P0 - Checkpoint 16.1.1)."""
    global _proactive_agents
    if _proactive_agents:
        logger.warning("Proactive monitors already started")
        return
    agent_classes = [
        ProactiveIntentAgent,
        ProactiveOrchestratorAgent,
        ProactiveCriticAgent,
        ProactiveSystemEngineerAgent,
        ProactiveRiskAnalystAgent,
    ]
    for cls in agent_classes:
        agent = cls()
        await agent.start_background_monitor()
        _proactive_agents.append(agent)
    logger.info(f"Started {len(_proactive_agents)} proactive background monitors")

async def stop_proactive_monitors() -> None:
    """停止常驻感知守护进程."""
    global _proactive_agents
    for agent in _proactive_agents:
        await agent.stop_background_monitor()
    _proactive_agents.clear()
    logger.info("All proactive background monitors stopped")


def get_proactive_monitors() -> list:
    """获取当前运行的 proactive agents 列表（用于测试和监控）."""
    return _proactive_agents


@mcp.custom_route("/health", methods=["GET"], include_in_schema=False)
async def health_check(request: Request) -> Response:
    """
    健康检查端点(存活探针).
    Kubernetes 用此端点判断容器是否存活.
    """
    del request
    return JSONResponse({"status": "ok"})


@mcp.custom_route("/ready", methods=["GET"], include_in_schema=False)
async def readiness_check(request: Request) -> Response:
    """
    就绪检查端点(就绪探针).
    Kubernetes 用此端点判断服务是否准备好接收流量.
    检查项:
    - 是否正在关闭(优雅退出)
    - 数据库连接是否正常
    """
    if not is_authorized(request.headers):
        return JSONResponse(
            {"error": {"code": "UNAUTHORIZED", "message": "unauthorized"}},
            status_code=401,
        )

    if readiness_service.is_shutting_down():
        return JSONResponse(
            {
                "status": "not_ready",
                "reason": readiness_service.shutdown_reason() or "shutting_down",
            },
            status_code=503,
        )

    # 本地演示场景下, 数据库就绪检查是可选的.
    # 如果环境变量不完整, 则跳过 MySQL 检查.
    mysql_password = os.getenv("MYSQL_PASSWORD")
    if mysql_password is None or not mysql_password.strip():
        return JSONResponse({"status": "ready", "checks": {"mysql": "skipped"}})

    ok, message, err = check_mysql_ready()
    if ok:
        return JSONResponse({"status": "ready", "checks": {"mysql": "ok"}})

    return JSONResponse(
        {
            "status": "not_ready",
            "checks": {
                "mysql": {
                    "status": "not_ready",
                    "message": message,
                    "code": getattr(err, "code", "DB_ERROR"),
                }
            },
        },
        status_code=503,
    )


@mcp.custom_route("/metrics", methods=["GET"], include_in_schema=False)
async def metrics_endpoint(request: Request) -> Response:
    """第 4 周: Prometheus 指标端点"""
    if not is_authorized(request.headers):
        return JSONResponse(
            {"error": {"code": "UNAUTHORIZED", "message": "unauthorized"}},
            status_code=401,
        )
    metrics_text = generate_prometheus_metrics()
    return Response(content=metrics_text, media_type="text/plain; version=0.0.4")


@mcp.custom_route("/api/llm/usage", methods=["GET"], include_in_schema=False)
async def llm_usage_endpoint(request: Request) -> Response:
    """LLM Token 用量摘要端点（内部监控，无需认证）.

    返回滑动窗口内的 token 累计用量、按模型分组的明细，
    以及当前的告警阈值与触发状态。tracker 为空（首次启动）时
    会返回各项为 0 的安全默认值。
    """
    del request
    try:
        from riskagent_backend.llm.token_tracker import get_token_tracker

        tracker = get_token_tracker()
        summary = tracker.summary()
    except Exception:  # pragma: no cover - 防御性兜底
        summary = {
            "window_hours": 1,
            "total_tokens": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "calls": 0,
            "by_model": {},
            "alert_threshold_hourly": 0,
            "alert_threshold_daily": 0,
            "hourly_alert_triggered": False,
            "daily_alert_triggered": False,
            "daily_total_tokens": 0,
        }
    return JSONResponse(summary)


@mcp.custom_route("/api/llm/cost-model", methods=["GET"], include_in_schema=False)
async def llm_cost_model_endpoint(request: Request) -> Response:
    """返回 LLM 成本预估表（5min / 1h / 24h / 7d 四窗口）.

    基于 TokenTracker 实测数据，推算不同时间窗口的总成本，
    同时提供启用去重（RFC-006）前后的对比预估。
    """
    del request
    try:
        from riskagent_backend.llm.cost_model import (
            generate_cost_estimate_table,
            get_pricing,
        )
        from riskagent_backend.llm.token_tracker import get_token_tracker

        summary = get_token_tracker().summary()
        table_no_dedup = generate_cost_estimate_table(summary, dedup_enabled=False)
        table_with_dedup = generate_cost_estimate_table(summary, dedup_enabled=True)
        result = {
            "baseline_5min": summary,
            "cost_estimate_no_dedup": table_no_dedup,
            "cost_estimate_with_dedup": table_with_dedup,
            "pricing": get_pricing("deepseek/deepseek-chat"),
        }
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse(
            {"error": str(e)},
            status_code=500,
        )


@mcp.custom_route("/api/tasks", methods=["POST"], include_in_schema=False)
async def create_task_endpoint(request: Request) -> Response:
    """浏览器友好的任务提交端点."""
    try:
        payload = await request.json()
    except Exception:
        payload = {}

    description = payload.get("description") if isinstance(payload, dict) else None
    if not isinstance(description, str) or not description.strip():
        return JSONResponse(
            {"error": {"code": "BAD_REQUEST", "message": "description is required"}},
            status_code=400,
        )

    service = get_rest_bff_service()
    created = await service.submit_task(description=description)
    return JSONResponse(created, status_code=202)


@mcp.custom_route("/api/tasks/{task_id}/memory", methods=["GET"], include_in_schema=False)
async def get_task_memory_endpoint(request: Request) -> Response:
    """浏览器友好的任务记忆视图端点."""
    task_id = request.path_params.get("task_id")
    if not isinstance(task_id, str) or not task_id.strip():
        return JSONResponse(
            {"error": {"code": "BAD_REQUEST", "message": "task_id is required"}},
            status_code=400,
        )

    raw_limit = request.query_params.get("limit")
    try:
        limit = int(raw_limit) if raw_limit is not None else 30
    except ValueError:
        return JSONResponse(
            {"error": {"code": "BAD_REQUEST", "message": "limit must be integer"}},
            status_code=400,
        )

    service = get_rest_bff_service()
    try:
        payload = await service.get_task_memory(task_id=task_id, limit=limit)
    except KeyError:
        return JSONResponse(
            {"error": {"code": "NOT_FOUND", "message": "task not found"}},
            status_code=404,
        )
    return JSONResponse(payload)


@mcp.custom_route("/api/tasks/{task_id}", methods=["GET"], include_in_schema=False)
async def get_task_endpoint(request: Request) -> Response:
    """浏览器友好的任务详情端点."""
    task_id = request.path_params.get("task_id")
    if not isinstance(task_id, str) or not task_id.strip():
        return JSONResponse(
            {"error": {"code": "BAD_REQUEST", "message": "task_id is required"}},
            status_code=400,
        )

    service = get_rest_bff_service()
    try:
        task_detail = await service.get_task_detail(task_id=task_id)
    except KeyError:
        return JSONResponse(
            {"error": {"code": "NOT_FOUND", "message": "task not found"}},
            status_code=404,
        )
    return JSONResponse(task_detail)


@mcp.custom_route("/api/tasks/{task_id}/graph", methods=["GET"], include_in_schema=False)
async def get_task_graph_endpoint(request: Request) -> Response:
    """浏览器友好的任务图快照端点."""
    task_id = request.path_params.get("task_id")
    if not isinstance(task_id, str) or not task_id.strip():
        return JSONResponse(
            {"error": {"code": "BAD_REQUEST", "message": "task_id is required"}},
            status_code=400,
        )

    service = get_rest_bff_service()
    try:
        payload = await service.get_task_graph(task_id=task_id)
    except KeyError:
        return JSONResponse(
            {"error": {"code": "NOT_FOUND", "message": "task not found"}},
            status_code=404,
        )
    return JSONResponse(payload)


@mcp.custom_route("/api/memory", methods=["GET"], include_in_schema=False)
async def get_memory_endpoint(request: Request) -> Response:
    """浏览器友好的全局记忆快照端点."""
    raw_limit = request.query_params.get("limit")
    try:
        limit = int(raw_limit) if raw_limit is not None else 20
    except ValueError:
        return JSONResponse(
            {"error": {"code": "BAD_REQUEST", "message": "limit must be integer"}},
            status_code=400,
        )

    service = get_rest_bff_service()
    snapshot = await service.get_memory_snapshot(limit=limit)
    return JSONResponse(snapshot)


@mcp.custom_route("/api/agents", methods=["GET"], include_in_schema=False)
async def get_agents_endpoint(request: Request) -> Response:
    """浏览器友好的智能体快照端点."""
    del request
    service = get_rest_bff_service()
    snapshot = await service.get_agents_snapshot()
    return JSONResponse(snapshot)


def _format_sse_event(*, event: str, data: dict[str, object]) -> bytes:
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n".encode("utf-8")


@mcp.custom_route("/api/stream", methods=["GET"], include_in_schema=False)
async def get_stream_endpoint(request: Request) -> Response:
    """浏览器友好的 SSE 实时事件流端点."""
    service = get_rest_bff_service()
    task_id = request.query_params.get("task_id")
    include_agents = request.query_params.get("agents", "1") != "0"
    include_memory = request.query_params.get("memory", "1") != "0"
    include_graph = request.query_params.get("graph", "1") != "0"

    async def event_generator():
        previous_agents_payload: str | None = None
        previous_memory_payload: str | None = None
        previous_graph_payload: str | None = None
        heartbeat_every = 10
        ticks = 0

        yield b"retry: 1500\n\n"

        while True:
            if await request.is_disconnected():
                break

            try:
                if include_agents:
                    agents_snapshot = await service.get_agents_snapshot()
                    agents_event = {
                        "type": "agent_snapshot",
                        "updated_at": agents_snapshot.get("updated_at"),
                        "data": agents_snapshot,
                    }
                    agents_payload = json.dumps(agents_event, ensure_ascii=False, sort_keys=True)
                    if agents_payload != previous_agents_payload:
                        previous_agents_payload = agents_payload
                        yield _format_sse_event(event="agent_snapshot", data=agents_event)

                if include_memory:
                    if isinstance(task_id, str) and task_id.strip():
                        memory_snapshot = await service.get_task_memory(task_id=task_id, limit=30)
                    else:
                        memory_snapshot = await service.get_memory_snapshot(limit=20)
                    memory_event = {
                        "type": "memory_snapshot",
                        "updated_at": memory_snapshot.get("updated_at"),
                        "data": memory_snapshot,
                    }
                    memory_payload = json.dumps(memory_event, ensure_ascii=False, sort_keys=True)
                    if memory_payload != previous_memory_payload:
                        previous_memory_payload = memory_payload
                        yield _format_sse_event(event="memory_snapshot", data=memory_event)

                if include_graph and isinstance(task_id, str) and task_id.strip():
                    graph_snapshot = await service.get_task_graph(task_id=task_id)
                    graph_event = {
                        "type": "graph_snapshot",
                        "updated_at": graph_snapshot.get("updated_at"),
                        "data": graph_snapshot,
                    }
                    graph_payload = json.dumps(graph_event, ensure_ascii=False, sort_keys=True)
                    if graph_payload != previous_graph_payload:
                        previous_graph_payload = graph_payload
                        yield _format_sse_event(event="graph_snapshot", data=graph_event)

                ticks += 1
                if ticks % heartbeat_every == 0:
                    yield _format_sse_event(
                        event="heartbeat",
                        data={"type": "heartbeat", "ts": int(time.time() * 1000)},
                    )
            except KeyError:
                yield _format_sse_event(
                    event="error",
                    data={"type": "error", "code": "NOT_FOUND", "message": "task not found"},
                )
                break
            except Exception as exc:
                logger.exception("SSE stream failed: %s", exc)
                yield _format_sse_event(
                    event="error",
                    data={"type": "error", "code": "STREAM_ERROR", "message": str(exc)},
                )
                break

            await asyncio.sleep(1)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _install_signal_handlers() -> None:
    # 在收到退出信号时, 先将就绪状态置为 not_ready.
    def _handler(signum: int, frame: object) -> None:
        del frame
        readiness_service.mark_shutting_down(f"signal={signum}")

    signal.signal(signal.SIGTERM, _handler)
    signal.signal(signal.SIGINT, _handler)

_install_signal_handlers()
