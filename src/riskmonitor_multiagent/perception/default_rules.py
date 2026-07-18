"""默认阈值规则定义 - 可配置，不硬编码到引擎中."""

from __future__ import annotations

from riskmonitor_multiagent.perception.rules import FilterRule
from riskmonitor_multiagent.perception.signals import SignalSeverity


def get_default_rules() -> list[FilterRule]:
    """
    获取默认阈值规则集.

    覆盖四类数据源的典型异常场景：
    - Docker: 容器退出、重启中
    - Redis: 内存使用率过高、连接失败
    - MySQL: 慢查询过多、连接失败
    - Prometheus: 业务指标异常波动
    """
    return [
        # === Docker 规则 ===
        FilterRule(
            name="docker_container_exited",
            source="docker",
            metric="container_status",
            predicate=lambda v: v in ("exited", "dead"),
            severity=SignalSeverity.CRITICAL,
            threshold="not running",
            message="Docker 容器已退出",
        ),
        FilterRule(
            name="docker_container_restarting",
            source="docker",
            metric="container_status",
            predicate=lambda v: v == "restarting",
            severity=SignalSeverity.WARNING,
            threshold="not restarting",
            message="Docker 容器正在重启",
        ),
        FilterRule(
            name="docker_cpu_high",
            source="docker",
            metric="cpu_percent",
            predicate=lambda v: isinstance(v, (int, float)) and v > 90.0,
            severity=SignalSeverity.WARNING,
            threshold=90.0,
            message="Docker 容器 CPU 使用率超过 90%",
        ),
        FilterRule(
            name="docker_memory_high",
            source="docker",
            metric="memory_percent",
            predicate=lambda v: isinstance(v, (int, float)) and v > 85.0,
            severity=SignalSeverity.WARNING,
            threshold=85.0,
            message="Docker 容器内存使用率超过 85%",
        ),

        # === Redis 规则 ===
        FilterRule(
            name="redis_memory_critical",
            source="redis",
            metric="memory_usage_percent",
            predicate=lambda v: isinstance(v, (int, float)) and v > 80.0,
            severity=SignalSeverity.CRITICAL,
            threshold=80.0,
            message="Redis 内存使用率超过 80%",
        ),
        FilterRule(
            name="redis_memory_warning",
            source="redis",
            metric="memory_usage_percent",
            predicate=lambda v: isinstance(v, (int, float)) and v > 60.0,
            severity=SignalSeverity.WARNING,
            threshold=60.0,
            message="Redis 内存使用率超过 60%",
        ),
        FilterRule(
            name="redis_connection_failed",
            source="redis",
            metric="connection_status",
            predicate=lambda v: v == "unavailable",
            severity=SignalSeverity.CRITICAL,
            threshold="available",
            message="Redis 连接失败",
        ),
        FilterRule(
            name="redis_keysapce_low",
            source="redis",
            metric="keyspace_hit_rate",
            predicate=lambda v: isinstance(v, (int, float)) and v < 0.5,
            severity=SignalSeverity.WARNING,
            threshold=0.5,
            message="Redis 键空间命中率低于 50%",
        ),

        # === MySQL 规则 ===
        FilterRule(
            name="mysql_slow_queries",
            source="mysql",
            metric="slow_queries",
            predicate=lambda v: isinstance(v, (int, float)) and v > 10,
            severity=SignalSeverity.WARNING,
            threshold=10,
            message="MySQL 慢查询数超过 10",
        ),
        FilterRule(
            name="mysql_connection_failed",
            source="mysql",
            metric="connection_status",
            predicate=lambda v: v == "unavailable",
            severity=SignalSeverity.CRITICAL,
            threshold="available",
            message="MySQL 连接失败",
        ),
        FilterRule(
            name="mysql_threads_high",
            source="mysql",
            metric="threads_connected",
            predicate=lambda v: isinstance(v, (int, float)) and v > 100,
            severity=SignalSeverity.WARNING,
            threshold=100,
            message="MySQL 连接数超过 100",
        ),

        # === Prometheus / 业务指标规则 ===
        FilterRule(
            name="prom_error_rate_high",
            source="prometheus",
            metric="error_rate",
            predicate=lambda v: isinstance(v, (int, float)) and v > 0.1,
            severity=SignalSeverity.CRITICAL,
            threshold=0.1,
            message="业务错误率超过 10%",
        ),
        FilterRule(
            name="prom_error_rate_warning",
            source="prometheus",
            metric="error_rate",
            predicate=lambda v: isinstance(v, (int, float)) and v > 0.05,
            severity=SignalSeverity.WARNING,
            threshold=0.05,
            message="业务错误率超过 5%",
        ),
        FilterRule(
            name="prom_token_usage_spike",
            source="prometheus",
            metric="token_usage_rate",
            predicate=lambda v: isinstance(v, (int, float)) and v > 100000,
            severity=SignalSeverity.WARNING,
            threshold=100000,
            message="LLM Token 用量异常飙升",
        ),
    ]
