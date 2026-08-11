"""HTTP 场景的鉴权辅助函数.

安全语义为 fail-closed:
- 配置了 RISKAGENT_API_TOKEN 时, 所有受保护端点必须携带匹配的 Bearer Token;
- 未配置 Token 时默认拒绝访问, 仅当显式设置
  RISKAGENT_ALLOW_UNAUTHENTICATED=1 时才放行(仅限本地开发/测试环境)。
"""

from __future__ import annotations

import hmac
import logging
from typing import Any, Mapping, Optional

from riskagent_backend.config import (
    get_riskagent_api_token,
    is_unauthenticated_allowed,
)

logger = logging.getLogger(__name__)


def _expected_token() -> Optional[str]:
    return get_riskagent_api_token()


def _allow_unauthenticated() -> bool:
    """开发/测试环境的显式逃生舱, 生产环境不应开启."""
    return is_unauthenticated_allowed()


def _extract_bearer(authorization: Optional[str]) -> Optional[str]:
    if authorization is None:
        return None
    value = authorization.strip()
    if not value:
        return None
    if value.lower().startswith("bearer "):
        return value[7:].strip() or None
    return None


def is_authorized(headers: Mapping[str, Any]) -> bool:
    """基于 Bearer Token 的最小鉴权校验 (fail-closed)."""
    expected = _expected_token()
    if expected is None:
        if _allow_unauthenticated():
            return True
        logger.warning(
            "RISKAGENT_API_TOKEN 未配置且未开启 RISKAGENT_ALLOW_UNAUTHENTICATED, "
            "按 fail-closed 策略拒绝请求"
        )
        return False
    auth = headers.get("authorization") or headers.get("Authorization")
    token = _extract_bearer(str(auth) if auth is not None else None)
    if token is None:
        return False
    return hmac.compare_digest(token, expected)


def get_headers_from_ctx(ctx: Any) -> dict[str, Any]:
    """从 FastMCP Context 中尽最大努力提取 HTTP headers."""
    request_context = getattr(ctx, "request_context", None)
    if request_context is None:
        return {}

    request = getattr(request_context, "request", None)
    headers = getattr(request, "headers", None)
    if headers is not None:
        try:
            return dict(headers)
        except Exception:  # pylint: disable=broad-except
            return {}

    headers = getattr(request_context, "headers", None)
    if headers is not None:
        try:
            return dict(headers)
        except Exception:  # pylint: disable=broad-except
            return {}

    return {}
