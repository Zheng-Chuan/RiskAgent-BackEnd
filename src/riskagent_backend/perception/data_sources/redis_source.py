"""Redis 感知数据源 - 采集连接数、内存使用、键空间命中率等."""

from __future__ import annotations

import logging
import os
from typing import Any

from riskagent_backend.perception.signals import PerceptionSignal

logger = logging.getLogger(__name__)


class RedisDataSource:
    """
    Redis 感知数据源.

    通过 redis-py 连接 Redis (6379), 采集:
    - connection_status: 连接状态 (available / unavailable)
    - memory_usage_percent: 内存使用率
    - keyspace_hit_rate: 键空间命中率
    - connected_clients: 连接客户端数
    - slow_query_count: 慢查询计数

    连接失败时降级为 unavailable 信号，不抛异常。
    """

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        db: int | None = None,
        password: str | None = None,
        redis_url: str | None = None,
    ) -> None:
        self._redis_url = (redis_url or os.getenv("REDIS_URL") or "").strip()
        self._host = (host or os.getenv("REDIS_HOST") or "localhost").strip()
        self._port = int(port or os.getenv("REDIS_PORT") or 6379)
        self._db = int(db or os.getenv("REDIS_DB") or 0)
        self._password = password if password is not None else os.getenv("REDIS_PASSWORD")
        self._client = None

    def _get_client(self):
        """获取 Redis 客户端（懒初始化）."""
        if self._client is not None:
            return self._client
        try:
            import redis
            if self._redis_url:
                self._client = redis.from_url(
                    self._redis_url,
                    decode_responses=True,
                    socket_timeout=5,
                    socket_connect_timeout=5,
                )
            else:
                self._client = redis.Redis(
                    host=self._host,
                    port=self._port,
                    db=self._db,
                    password=self._password,
                    decode_responses=True,
                    socket_timeout=5,
                    socket_connect_timeout=5,
                )
        except Exception as e:
            logger.warning("Redis client init failed: %s", e)
            return None
        return self._client

    def _parse_info(self, info: dict[str, Any]) -> list[PerceptionSignal]:
        """解析 Redis INFO 输出，产出 PerceptionSignal 列表."""
        signals: list[PerceptionSignal] = []

        # 连接状态
        signals.append(PerceptionSignal(
            source="redis",
            metric="connection_status",
            value="available",
            message="Redis 连接正常",
        ))

        # 内存使用率
        used_memory = info.get("used_memory", 0)
        max_memory = info.get("maxmemory", 0)
        if max_memory > 0:
            mem_percent = round((used_memory / max_memory) * 100, 2)
        else:
            # 无 maxmemory 限制时，用 used_memory_rss / system_memory 估算
            used_rss = info.get("used_memory_rss", 0)
            total_system = info.get("total_system_memory", 0)
            if total_system > 0:
                mem_percent = round((used_rss / total_system) * 100, 2)
            else:
                mem_percent = 0.0

        signals.append(PerceptionSignal(
            source="redis",
            metric="memory_usage_percent",
            value=mem_percent,
            context={
                "used_memory": used_memory,
                "used_memory_human": info.get("used_memory_human", ""),
                "maxmemory": max_memory,
            },
        ))

        # 键空间命中率
        hits = info.get("keyspace_hits", 0)
        misses = info.get("keyspace_misses", 0)
        total = hits + misses
        hit_rate = round(hits / total, 4) if total > 0 else 1.0
        signals.append(PerceptionSignal(
            source="redis",
            metric="keyspace_hit_rate",
            value=hit_rate,
            context={"hits": hits, "misses": misses},
        ))

        # 连接客户端数
        clients = info.get("connected_clients", 0)
        signals.append(PerceptionSignal(
            source="redis",
            metric="connected_clients",
            value=clients,
        ))

        # 慢查询计数
        slow_queries = info.get("slowlog_count", 0) if "slowlog_count" in info else 0
        # Redis INFO 不直接提供 slowlog count, 用 latest_fork_usec 代替
        signals.append(PerceptionSignal(
            source="redis",
            metric="slow_queries",
            value=slow_queries,
            context={"latest_fork_usec": info.get("latest_fork_usec", 0)},
        ))

        return signals

    def collect(self) -> list[PerceptionSignal]:
        """
        采集 Redis 指标，产出 PerceptionSignal 列表.

        连接失败时返回单个 unavailable 信号，不抛异常。
        """
        client = self._get_client()
        if client is None:
            return [
                PerceptionSignal(
                    source="redis",
                    metric="connection_status",
                    value="unavailable",
                    message="Redis 客户端初始化失败",
                )
            ]

        try:
            info = client.info()
            return self._parse_info(info)
        except Exception as e:
            logger.warning("Redis perception error: %s", e)
            return [
                PerceptionSignal(
                    source="redis",
                    metric="connection_status",
                    value="unavailable",
                    message=f"Redis 连接失败: {e}",
                )
            ]
        finally:
            # 不关闭 client，便于复用
            pass
