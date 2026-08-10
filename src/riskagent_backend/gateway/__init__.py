"""
多平台网关模块.

提供统一的消息收发接口.
新增平台只需实现 GatewayAdapter 即可.

注意: Slack 和企业微信适配器保留为兼容性实现, 但不作为对外交付承诺.
      核心抽象层 GatewayAdapter / GatewayMessage / GatewayRouter 保留,
      后续可按需实现新的平台适配器.
"""

from __future__ import annotations

from riskagent_backend.gateway.adapter import GatewayAdapter, GatewayMessage
from riskagent_backend.gateway.router import GatewayRouter

__all__ = [
    "GatewayAdapter",
    "GatewayMessage",
    "GatewayRouter",
]
