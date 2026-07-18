"""Prometheus 感知数据源 - 通过 httpx 查询 Prometheus HTTP API."""

from __future__ import annotations

import logging
import os

from riskmonitor_multiagent.perception.signals import PerceptionSignal

logger = logging.getLogger(__name__)


class PrometheusDataSource:
    """
    Prometheus 感知数据源.

    通过 httpx 查询 Prometheus (9090) HTTP API, 采集:
    - connection_status: 连接状态
    - error_rate: 业务错误率
    - token_usage_rate: LLM Token 用量
    - orchestrator_runs_total: 编排器运行总数

    查询失败时降级为 unavailable 信号，不抛异常。
    """

    def __init__(self, base_url: str | None = None) -> None:
        self._base_url = base_url or os.getenv("PROMETHEUS_URL", "http://localhost:9090")
        self._client = None

    def _get_client(self):
        """获取 httpx 客户端（懒初始化）."""
        if self._client is not None:
            return self._client
        try:
            import httpx
            self._client = httpx.Client(timeout=5.0)
        except Exception as e:
            logger.warning(f"httpx init failed: {e}")
            return None
        return self._client

    def _query(self, promql: str) -> float | None:
        """执行 PromQL 查询."""
        client = self._get_client()
        if client is None:
            return None
        try:
            resp = client.get(f"{self._base_url}/api/v1/query", params={"query": promql})
            if resp.status_code != 200:
                return None
            data = resp.json()
            if data.get("status") == "success" and data.get("data", {}).get("result"):
                result = data["data"]["result"][0]
                value = result.get("value", [None, "0"])[1]
                return float(value)
        except Exception as e:
            logger.debug(f"Prometheus query '{promql}' failed: {e}")
        return None

    def collect(self) -> list[PerceptionSignal]:
        """采集 Prometheus 指标."""
        client = self._get_client()
        if client is None:
            return [
                PerceptionSignal(
                    source="prometheus",
                    metric="connection_status",
                    value="unavailable",
                    message="httpx 不可用",
                )
            ]

        # 测试连接
        test_val = self._query("up")
        if test_val is None:
            return [
                PerceptionSignal(
                    source="prometheus",
                    metric="connection_status",
                    value="unavailable",
                    message="Prometheus 查询失败",
                )
            ]

        signals = [PerceptionSignal(
            source="prometheus",
            metric="connection_status",
            value="available",
            message="Prometheus 连接正常",
        )]

        # 采集业务指标
        error_rate = self._query('rate(http_requests_total{status=~"5.."}[5m]) / rate(http_requests_total[5m])')
        if error_rate is not None:
            signals.append(PerceptionSignal(
                source="prometheus",
                metric="error_rate",
                value=error_rate,
            ))
        else:
            signals.append(PerceptionSignal(
                source="prometheus",
                metric="error_rate",
                value=0.0,
                context={"note": "no error rate data"},
            ))

        token_usage = self._query('increase(llm_token_total[1m])')
        if token_usage is not None:
            signals.append(PerceptionSignal(
                source="prometheus",
                metric="token_usage_rate",
                value=token_usage,
            ))

        runs_total = self._query('increase(orchestrator_runs_total[5m])')
        if runs_total is not None:
            signals.append(PerceptionSignal(
                source="prometheus",
                metric="orchestrator_runs",
                value=runs_total,
            ))

        return signals
