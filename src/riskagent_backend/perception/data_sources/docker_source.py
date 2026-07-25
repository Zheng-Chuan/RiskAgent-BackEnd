"""Docker 感知数据源 - 采集容器状态和资源占用."""

from __future__ import annotations

import json
import logging
import subprocess
from typing import Any

from riskagent_backend.perception.signals import PerceptionSignal

logger = logging.getLogger(__name__)

# docker-compose.yml 中定义的容器名前缀
KNOWN_CONTAINERS = [
    "riskagent-mysql",
    "riskagent-redis",
    "riskagent-chroma",
    "riskagent-backend",
    "riskagent-prometheus",
    "riskagent-grafana",
    "riskagent-test",
    "riskagent-phpmyadmin",
]


class DockerDataSource:
    """
    Docker 感知数据源.

    通过 docker CLI 采集容器状态，产出 PerceptionSignal 列表。
    连接失败时降级为空列表而非抛异常。
    """

    def __init__(self, container_prefix: str = "riskagent-") -> None:
        self._container_prefix = container_prefix

    def _run_docker_ps(self) -> list[dict[str, Any]]:
        """执行 docker ps -a 获取容器列表."""
        try:
            result = subprocess.run(
                [
                    "docker", "ps", "-a",
                    "--format", "{{json .}}",
                    "--filter", f"name={self._container_prefix}",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                logger.warning(f"docker ps failed: {result.stderr.strip()}")
                return []

            containers = []
            for line in result.stdout.strip().split("\n"):
                line = line.strip()
                if line:
                    try:
                        containers.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
            return containers
        except FileNotFoundError:
            logger.warning("docker command not found, Docker perception unavailable")
            return []
        except subprocess.TimeoutExpired:
            logger.warning("docker ps timed out")
            return []
        except Exception as e:
            logger.warning(f"Docker perception error: {e}")
            return []

    def _run_docker_stats(self, container_name: str) -> dict[str, Any]:
        """获取单个容器的资源占用."""
        try:
            result = subprocess.run(
                [
                    "docker", "stats", container_name,
                    "--no-stream",
                    "--format", "{{json .}}",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                return {}
            line = result.stdout.strip()
            if line:
                return json.loads(line)
            return {}
        except Exception:
            return {}

    def _parse_cpu_percent(self, cpu_str: str) -> float | None:
        """解析 CPU 百分比字符串."""
        if not cpu_str:
            return None
        try:
            return float(cpu_str.rstrip("%"))
        except (ValueError, AttributeError):
            return None

    def _parse_memory_percent(self, mem_str: str) -> float | None:
        """解析内存百分比字符串."""
        if not mem_str:
            return None
        try:
            return float(mem_str.rstrip("%"))
        except (ValueError, AttributeError):
            return None

    def collect(self) -> list[PerceptionSignal]:
        """
        采集 Docker 容器状态，产出 PerceptionSignal 列表.

        每个容器产出 3 个信号:
        - container_status: 容器运行状态
        - cpu_percent: CPU 使用率
        - memory_percent: 内存使用率
        """
        containers = self._run_docker_ps()
        if not containers:
            # Docker 不可用时，产出一个 unavailable 信号
            return [
                PerceptionSignal(
                    source="docker",
                    metric="connection_status",
                    value="unavailable",
                    message="Docker CLI 不可用或无容器运行",
                )
            ]

        signals: list[PerceptionSignal] = []

        for container in containers:
            name = container.get("Names", "").lstrip("/")
            status = container.get("State", "unknown")
            container_id = container.get("ID", "")

            # 容器状态信号
            signals.append(PerceptionSignal(
                source="docker",
                metric="container_status",
                value=status,
                context={"container_name": name, "container_id": container_id},
            ))

            # 资源占用（仅对 running 容器）
            if status == "running":
                stats = self._run_docker_stats(name)
                cpu_str = stats.get("CPUPerc", "")
                mem_str = stats.get("MemPerc", "")

                cpu_val = self._parse_cpu_percent(cpu_str)
                if cpu_val is not None:
                    signals.append(PerceptionSignal(
                        source="docker",
                        metric="cpu_percent",
                        value=cpu_val,
                        context={"container_name": name},
                    ))

                mem_val = self._parse_memory_percent(mem_str)
                if mem_val is not None:
                    signals.append(PerceptionSignal(
                        source="docker",
                        metric="memory_percent",
                        value=mem_val,
                        context={"container_name": name},
                    ))

        logger.debug(f"Docker perception collected {len(signals)} signals from {len(containers)} containers")
        return signals

    def get_container_names(self) -> list[str]:
        """获取当前运行的容器名列表."""
        containers = self._run_docker_ps()
        return [c.get("Names", "").lstrip("/") for c in containers if c.get("Names")]
