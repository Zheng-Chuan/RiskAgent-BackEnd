"""JSON 处理工具函数."""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


def safe_json_loads(text: str, default: Any = None) -> Any:
    """
    安全地解析 JSON 字符串.

    Args:
        text: JSON 字符串
        default: 解析失败时的默认值

    Returns:
        解析后的对象,或默认值
    """
    if not text or not isinstance(text, str):
        return default
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        logger.debug(f"JSON decode error: {e}")
        return default


def safe_json_dumps(obj: Any, default: str = "{}", ensure_ascii: bool = False) -> str:
    """
    安全地将对象转为 JSON 字符串.

    Args:
        obj: 要序列化的对象
        default: 序列化失败时的默认字符串
        ensure_ascii: 是否转义非 ASCII 字符

    Returns:
        JSON 字符串,或默认值
    """
    if obj is None:
        return default
    try:
        return json.dumps(obj, ensure_ascii=ensure_ascii, default=str)
    except (TypeError, ValueError) as e:
        logger.debug(f"JSON encode error: {e}")
        return default


_CIRCULAR_MARKER = "<circular>"
_CONTAINER_TYPES: tuple[type, ...] = (dict, list, set, tuple)


def _resolve_circular(value: Any, visited: set[int]) -> Any:
    """递归遍历对象,检测并打断循环引用.

    使用 visited set 追踪已访问的可变容器 id(),遇到循环引用时
    替换为 "<circular>" 字符串;非 JSON 原生类型对象转为 str 兜底.
    """
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, _CONTAINER_TYPES):
        value_id = id(value)
        if value_id in visited:
            return _CIRCULAR_MARKER
        visited.add(value_id)
        try:
            if isinstance(value, dict):
                return {str(k): _resolve_circular(v, visited) for k, v in value.items()}
            return [_resolve_circular(item, visited) for item in value]
        finally:
            visited.discard(value_id)
    # 非 JSON 原生类型对象,转字符串兜底
    return str(value)


def _safe_json_dumps(
    obj: Any,
    *,
    ensure_ascii: bool = False,
    indent: int | None = None,
    sort_keys: bool = False,
) -> str:
    """
    安全地将对象序列化为 JSON 字符串,自动检测并打断循环引用.

    通过递归遍历,使用 visited set 追踪已访问的可变容器
    (dict/list/set/tuple) 的 id(),遇到循环引用时替换为
    "<circular>" 字符串.同时启用 default=str 处理非 JSON 原生类型对象.

    用于兜底 proactive workflow 中 source_event 与 result 互相引用
    导致的 `ValueError: Circular reference detected`.

    Args:
        obj: 要序列化的对象
        ensure_ascii: 是否转义非 ASCII 字符
        indent: 缩进空格数
        sort_keys: 是否按键排序

    Returns:
        JSON 字符串
    """
    resolved = _resolve_circular(obj, set())
    return json.dumps(
        resolved,
        ensure_ascii=ensure_ascii,
        indent=indent,
        sort_keys=sort_keys,
        default=str,
    )
