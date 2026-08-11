"""MySQL 感知数据源 - 复用 data_access 层采集连接/慢查询/表行数."""

from __future__ import annotations

import logging

from riskagent_backend.config import (
    get_mysql_database,
    get_mysql_host,
    get_mysql_port,
    get_mysql_user,
    get_settings,
)
from riskagent_backend.perception.signals import PerceptionSignal

logger = logging.getLogger(__name__)


class MySQLDataSource:
    """
    MySQL 感知数据源.

    复用 data_access 层连接 MySQL (地址经统一配置读取), 采集:
    - connection_status: 连接状态
    - slow_queries: 慢查询计数
    - threads_connected: 连接线程数
    - alerts_count: alerts 表行数

    连接失败时降级为 unavailable 信号，不抛异常。
    """

    def __init__(self) -> None:
        self._conn = None

    def _get_connection(self):
        """获取 MySQL 连接."""
        if self._conn is not None:
            return self._conn
        try:
            import pymysql
            host = get_mysql_host()
            port = get_mysql_port()
            user = get_mysql_user()
            # 密码必须通过环境变量提供, 不提供弱密码兜底 (未设置时连接失败并降级为 unavailable)
            password = get_settings().mysql_password
            database = get_mysql_database()
            self._conn = pymysql.connect(
                host=host, port=port, user=user,
                password=password, database=database,
                connect_timeout=5,
            )
        except Exception as e:
            logger.warning("MySQL connect failed: %s", e)
            return None
        return self._conn

    def collect(self) -> list[PerceptionSignal]:
        """采集 MySQL 指标."""
        conn = self._get_connection()
        if conn is None:
            return [
                PerceptionSignal(
                    source="mysql",
                    metric="connection_status",
                    value="unavailable",
                    message="MySQL 连接失败",
                )
            ]

        try:
            with conn.cursor() as cursor:
                # 连接状态
                signals = [PerceptionSignal(
                    source="mysql",
                    metric="connection_status",
                    value="available",
                    message="MySQL 连接正常",
                )]

                # 慢查询计数
                cursor.execute("SHOW GLOBAL STATUS LIKE 'Slow_queries'")
                row = cursor.fetchone()
                slow_q = int(row[1]) if row else 0
                signals.append(PerceptionSignal(
                    source="mysql",
                    metric="slow_queries",
                    value=slow_q,
                ))

                # 连接线程数
                cursor.execute("SHOW GLOBAL STATUS LIKE 'Threads_connected'")
                row = cursor.fetchone()
                threads = int(row[1]) if row else 0
                signals.append(PerceptionSignal(
                    source="mysql",
                    metric="threads_connected",
                    value=threads,
                ))

                # alerts 表行数
                try:
                    cursor.execute("SELECT COUNT(*) FROM alerts")
                    row = cursor.fetchone()
                    alerts_count = int(row[0]) if row else 0
                    signals.append(PerceptionSignal(
                        source="mysql",
                        metric="alerts_count",
                        value=alerts_count,
                    ))
                except Exception:
                    pass  # 表可能不存在

                return signals
        except Exception as e:
            logger.warning("MySQL perception error: %s", e)
            return [
                PerceptionSignal(
                    source="mysql",
                    metric="connection_status",
                    value="unavailable",
                    message=f"MySQL 查询失败: {e}",
                )
            ]
