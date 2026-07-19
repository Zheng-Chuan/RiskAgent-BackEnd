"""K8s 感知数据源 - 采集 Pod 状态和健康度."""

from __future__ import annotations

import json
import logging
import os
import subprocess
from typing import Any

from riskmonitor_multiagent.perception.signals import PerceptionSignal, SignalSeverity

logger = logging.getLogger(__name__)


class K8sDataSource:
    """
    K8s 感知数据源.

    通过 kubectl CLI 采集 Pod 状态，产出 PerceptionSignal 列表。
    kubectl 不可用时降级为 unavailable 信号，不抛异常（与 DockerDataSource 一致）。
    """

    def __init__(self, namespace: str | None = None) -> None:
        self._namespace = namespace or os.getenv("RISKMONITOR_NAMESPACE", "riskmonitor")

    def _run_kubectl_get_pods(self) -> list[dict[str, Any]]:
        """执行 kubectl get pods -o json 获取 Pod 列表."""
        try:
            result = subprocess.run(
                [
                    "kubectl", "get", "pods",
                    "-n", self._namespace,
                    "-o", "json",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                logger.warning(f"kubectl get pods failed: {result.stderr.strip()}")
                return []
            data = json.loads(result.stdout)
            return data.get("items", []) or []
        except FileNotFoundError:
            logger.warning("kubectl command not found, K8s perception unavailable")
            return []
        except subprocess.TimeoutExpired:
            logger.warning("kubectl get pods timed out")
            return []
        except Exception as e:
            logger.warning(f"K8s perception error: {e}")
            return []

    def collect(self) -> list[PerceptionSignal]:
        """
        采集 K8s Pod 状态，产出 PerceptionSignal 列表.

        产出信号:
        - container_status: Pod phase 非 Running 时，或容器 state 处于 waiting/terminated
        - restart_count: 容器重启次数 > 3 (warning)；> 10 (critical)
        - pod_health: 所有 Pod Running 时 value="healthy"
        """
        pods = self._run_kubectl_get_pods()
        if not pods:
            # kubectl 不可用时，产出一个 unavailable 信号
            return [
                PerceptionSignal(
                    source="k8s",
                    metric="connection_status",
                    value="unavailable",
                    message="kubectl CLI 不可用或无 Pod 运行",
                )
            ]

        signals: list[PerceptionSignal] = []
        all_running = True

        for pod in pods:
            metadata = pod.get("metadata", {}) or {}
            status = pod.get("status", {}) or {}
            name = metadata.get("name", "unknown")
            phase = status.get("phase", "Unknown")
            container_statuses = status.get("containerStatuses", []) or []

            # container_status 信号：phase 非 Running 时产出
            if phase != "Running":
                all_running = False
                severity = (
                    SignalSeverity.CRITICAL if phase == "Failed"
                    else SignalSeverity.WARNING
                )
                signals.append(PerceptionSignal(
                    source="k8s",
                    metric="container_status",
                    value=phase,
                    severity=severity,
                    context={"pod_name": name, "namespace": self._namespace},
                    message=f"Pod {name} phase={phase}",
                ))

            # 解析每个容器的状态
            for cs in container_statuses:
                container_name = cs.get("name", "")
                restart_count = cs.get("restartCount", 0)

                # restart_count 信号：重启次数 > 3 (warning)；> 10 (critical)
                if restart_count > 3:
                    severity = (
                        SignalSeverity.CRITICAL if restart_count > 10
                        else SignalSeverity.WARNING
                    )
                    signals.append(PerceptionSignal(
                        source="k8s",
                        metric="restart_count",
                        value=restart_count,
                        severity=severity,
                        threshold=3,
                        context={
                            "pod_name": name,
                            "container": container_name,
                            "namespace": self._namespace,
                        },
                        message=(
                            f"Pod {name} container {container_name} "
                            f"restarted {restart_count} times"
                        ),
                    ))

                # 读取 readiness probes 失败状态（containerStatuses[*].state）
                # state 仅含 waiting / running / terminated 三者之一
                state = cs.get("state", {}) or {}
                if "waiting" in state and state["waiting"]:
                    all_running = False
                    waiting = state["waiting"]
                    reason = waiting.get("reason", "")
                    signals.append(PerceptionSignal(
                        source="k8s",
                        metric="container_status",
                        value="waiting",
                        severity=SignalSeverity.WARNING,
                        context={
                            "pod_name": name,
                            "container": container_name,
                            "namespace": self._namespace,
                            "reason": reason,
                        },
                        message=(
                            f"Pod {name} container {container_name} "
                            f"waiting: {reason}"
                        ),
                    ))
                if "terminated" in state and state["terminated"]:
                    all_running = False
                    terminated = state["terminated"]
                    reason = terminated.get("reason", "")
                    signals.append(PerceptionSignal(
                        source="k8s",
                        metric="container_status",
                        value="terminated",
                        severity=SignalSeverity.CRITICAL,
                        context={
                            "pod_name": name,
                            "container": container_name,
                            "namespace": self._namespace,
                            "reason": reason,
                        },
                        message=(
                            f"Pod {name} container {container_name} "
                            f"terminated: {reason}"
                        ),
                    ))

        # pod_health 信号：所有 Pod Running 时产出 healthy
        if all_running and pods:
            signals.append(PerceptionSignal(
                source="k8s",
                metric="pod_health",
                value="healthy",
                context={"namespace": self._namespace, "pod_count": len(pods)},
                message=f"All {len(pods)} pods Running in {self._namespace}",
            ))

        logger.debug(
            f"K8s perception collected {len(signals)} signals from {len(pods)} pods"
        )
        return signals
