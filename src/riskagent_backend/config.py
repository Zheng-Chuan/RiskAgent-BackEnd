"""向后兼容的配置 getter 包装层.

此模块保留历史 ``get_*`` 函数签名, 并将所有读取委托到
``riskagent_backend.config_pydantic.Settings``.

注意:
- 本模块与 ``config_pydantic.py`` 是仅有的允许直接读取 ``os.getenv`` 的
  位置 (动态配置 key 通过下方 ``safe_env_*`` 工具收敛), 其余模块一律
  经 ``Settings`` 字段或本层 getter 读取配置.
- 不再每次调用都加载 ``.env``.
- ``.env`` 的解析与加载由 Pydantic Settings 在实例化时完成.
- 每个 getter 通过 ``get_settings()`` 创建新的 ``Settings`` 实例,
  保证测试中使用 ``monkeypatch.setenv`` 修改环境变量后也能立即生效.
- 历史上若 getter 含有额外校验或派生逻辑 (例如校验必填、剥离尾部斜杠、
  根据仓库目录推导默认路径), 这些逻辑保留在本兼容层内.
"""

from __future__ import annotations

import os
from pathlib import Path

from riskagent_backend.config_pydantic import Settings, get_settings, settings


# ---- MySQL ----
def get_mysql_host() -> str:
    """获取 MySQL 主机地址, 默认为 localhost."""
    return get_settings().mysql_host or "localhost"


def get_mysql_port() -> int:
    """获取 MySQL 端口, 默认为 3306."""
    return int(get_settings().mysql_port or 3306)


def get_mysql_database() -> str:
    """获取 MySQL 数据库名, 默认为 riskagent."""
    return get_settings().mysql_database or "riskagent"


def get_mysql_user() -> str:
    """获取 MySQL 用户名, 默认为 admin."""
    return get_settings().mysql_user or "admin"


def get_mysql_password() -> str:
    """
    获取 MySQL 密码.
    必须设置 MYSQL_PASSWORD 环境变量.

    异常:
        ValueError: 如果未设置 MYSQL_PASSWORD.
    """
    password = (get_settings().mysql_password or "").strip()
    if not password:
        raise ValueError("MYSQL_PASSWORD is not set")
    return password


def get_mysql_connect_timeout_s() -> float:
    """获取数据库连接超时时间(秒), 默认为 3秒."""
    return float(get_settings().mysql_connect_timeout)


def get_mysql_read_timeout_s() -> float:
    """获取数据库读取超时时间(秒), 默认为 5秒."""
    return float(get_settings().mysql_read_timeout)


def get_mysql_write_timeout_s() -> float:
    """获取数据库写入超时时间(秒), 默认为 5秒."""
    return float(get_settings().mysql_write_timeout)


def get_mysql_pool_size() -> int:
    """获取数据库连接池大小, 默认为 5."""
    return int(get_settings().mysql_pool_size)


def get_mysql_max_overflow() -> int:
    """获取数据库连接池最大溢出数, 默认为 10."""
    return int(get_settings().mysql_pool_max_overflow)


def get_mysql_pool_recycle_s() -> int:
    """获取数据库连接回收时间(秒), 默认为 1800秒 (30分钟)."""
    return int(get_settings().mysql_pool_recycle)


# ---- LLM ----
def get_llm_api_key() -> str:
    """
    获取 LLM API Key.
    必须设置 LLM_API_KEY 环境变量.
    当前项目默认使用 DeepSeek 官方 API Key.

    异常:
        ValueError: 如果未设置 LLM_API_KEY.
    """
    api_key = (get_settings().llm_api_key or "").strip()
    if not api_key:
        raise ValueError("LLM_API_KEY is not set")
    return api_key


def get_llm_base_url() -> str:
    """获取 LLM 主机 Base URL. 当前项目默认使用 DeepSeek 官方 API."""
    value = (get_settings().llm_base_url or "").strip().rstrip("/")
    if not value:
        raise ValueError("LLM_BASE_URL is not set")
    return value


def get_llm_model() -> str:
    """获取 LLM 模型 ID;优先读 LLM_MODEL,默认 deepseek-v4-flash (DeepSeek 官方)."""
    value = (get_settings().llm_model or "").strip()
    return value or "deepseek-v4-flash"


def get_llm_http_referer() -> str:
    """获取 LLM HTTP-Referer(可选)."""
    return (get_settings().llm_http_referer or "").strip()


def get_llm_app_title() -> str:
    """获取 LLM X-Title(可选)."""
    return (get_settings().llm_app_title or "").strip()


def get_llm_resolve_ip() -> str:
    """
    获取 LLM API 的固定 IP 地址(可选).

    用于绕过 DNS 解析问题(如 Cloudflare 某些节点故障时).
    格式: IP 地址,例如 "104.26.9.9"
    """
    return (get_settings().llm_resolve_ip or "").strip()


def get_llm_embedding_model() -> str:
    """获取 LLM embedding 模型名称;优先读 LLM_EMBEDDING_MODEL,默认 BAAI/bge-m3.

    用于 RFC-005 需求二: embedding (BAAI/bge-m3, 1024 维).
    """
    value = (get_settings().llm_embedding_model or "").strip()
    return value or "BAAI/bge-m3"


def get_llm_embedding_base_url() -> str:
    """获取 embedding 专用 Base URL;未设置时回退到主 LLM_BASE_URL.

    DeepSeek 官方 API 不提供 embeddings 端点, 故 embedding 需独立指向
    支持 embedding 的供应商 (如硅基流动); 未配置时回退主 Base URL.
    """
    value = (get_settings().llm_embedding_base_url or "").strip().rstrip("/")
    if value:
        return value
    return get_llm_base_url()


def get_llm_embedding_api_key() -> str:
    """获取 embedding 专用 API Key;未设置时回退到主 LLM_API_KEY."""
    value = (get_settings().llm_embedding_api_key or "").strip()
    if value:
        return value
    return get_llm_api_key()


# ---- Knowledge ----
def get_knowledge_db_path() -> str:
    """获取知识库 SQLite 文件路径, 默认为 repo_root/data/knowledge.sqlite."""
    value = (get_settings().knowledge_db_path or "").strip()
    if value:
        return value
    repo_root = Path(__file__).resolve().parents[2]
    return str(repo_root / "data" / "knowledge.sqlite")


# ---- Chroma ----
def get_chroma_host() -> str:
    return (get_settings().chroma_host or "").strip() or "localhost"


def get_chroma_port() -> int:
    return int(get_settings().chroma_port or 8001)


def get_chroma_collection() -> str:
    return (get_settings().chroma_collection or "").strip() or "riskagent-alerts"


def get_chroma_memory_collection() -> str:
    return (get_settings().chroma_memory_collection or "").strip() or "riskagent-memory"


def get_chroma_skills_collection() -> str:
    return (get_settings().chroma_skills_collection or "").strip() or "riskagent-skills"


def get_chroma_persist_dir() -> str:
    return (get_settings().chroma_persist_dir or "").strip()


# ---- Skill query rewrite (RFC-005 需求五) ----
def get_skill_query_rewrite_enabled() -> bool:
    """获取是否启用 query 改写, 默认 True.

    RFC-005 需求五: 在 _build_query() 之后、search() 之前,
    用 LLM 将短 query 扩展为检索导向 query.
    """
    return bool(get_settings().skill_query_rewrite_enabled)


def get_skill_query_rewrite_timeout() -> float:
    """获取 query 改写 LLM 调用超时时间(秒), 默认 3."""
    return float(get_settings().skill_query_rewrite_timeout)


def get_skill_query_rewrite_cache_size() -> int:
    """获取 query 改写 LRU 缓存容量, 默认 256."""
    return int(get_settings().skill_query_rewrite_cache_size)


# ---- Skill hybrid retrieval (RFC-005 需求四) ----
def get_skill_hybrid_vector_weight() -> float:
    """获取 Hybrid 检索向量权重 alpha, 默认 0.7.

    RFC-005 需求四: final_score = alpha * vector_score + (1-alpha) * bm25_score
    alpha=1.0 禁用 BM25 (纯向量), alpha=0.0 禁用向量 (纯 BM25).
    """
    return float(get_settings().skill_hybrid_vector_weight)


# ---- MCP Server ----
def get_mcp_server_name() -> str:
    """获取 MCP 服务名称."""
    return get_settings().mcp_server_name.strip() or "RiskAgent BackEnd"


def get_fastmcp_host() -> str:
    """获取 FastMCP 监听地址, 默认 0.0.0.0."""
    return get_settings().fastmcp_host.strip() or "0.0.0.0"


def get_fastmcp_port() -> int:
    """获取 FastMCP 监听端口, 默认 8000."""
    return int(get_settings().fastmcp_port or 8000)


# ---- 记忆行为 ----
def get_redis_url() -> str:
    """获取 Redis URL (显式 REDIS_URL 优先, 否则由 host/port/password 组装)."""
    return get_settings().redis_url


def get_memory_ttl_s() -> int:
    """获取记忆默认 TTL (秒), 默认 86400."""
    return int(get_settings().memory_ttl_s)


def get_memory_max_len() -> int:
    """获取记忆列表最大长度, 默认 2000."""
    return int(get_settings().memory_max_len)


def is_semantic_memory_enabled() -> bool:
    """语义记忆是否启用.

    语义与原实现对齐: SEMANTIC_MEMORY_ENABLED 未设置时回退
    PAGE_INDEX_ENABLED, 两者均未设置时默认启用; 仅 "true" 视为启用.
    """
    s = get_settings()
    raw = s.semantic_memory_enabled
    if raw is None:
        raw = s.page_index_enabled if s.page_index_enabled is not None else "true"
    return str(raw).lower() == "true"


# ---- 感知采集 ----
def get_prometheus_url() -> str:
    """获取 Prometheus 地址, 默认 http://localhost:9090."""
    return get_settings().prometheus_url


def get_riskagent_namespace() -> str:
    """获取 K8s 命名空间, 默认 riskagent."""
    return get_settings().riskagent_namespace


# ---- API 鉴权 (fail-closed) ----
def get_riskagent_api_token() -> str | None:
    """获取 Bearer Token; 未设置或为空返回 None."""
    token = (get_settings().riskagent_api_token or "").strip()
    return token or None


def is_unauthenticated_allowed() -> bool:
    """未设置 Token 时是否放行请求 (开发/测试显式逃生舱).

    仅当 RISKAGENT_ALLOW_UNAUTHENTICATED 显式为 1/true/yes/on 时返回 True.
    """
    flag = get_settings().riskagent_allow_unauthenticated
    if flag is None:
        return False
    return flag.strip().lower() in {"1", "true", "yes", "on"}


# ---- 日志与观测 ----
def get_log_level() -> str:
    """获取日志级别, 默认 INFO."""
    return (get_settings().log_level or "INFO").upper()


def get_run_trace_dir() -> str:
    """获取 run trace 落盘目录, 默认 results/run_traces."""
    return get_settings().run_trace_dir


# ---- 治理 ----
def get_policy_version() -> str:
    """获取治理策略版本号, 默认 policy.v1."""
    return (get_settings().policy_version or "").strip() or "policy.v1"


# ---- LLM 运行时开关 ----
def is_llm_disabled() -> bool:
    """DISABLE_LLM 是否启用 (除 0/false/False 外一律视为禁用)."""
    raw = get_settings().disable_llm
    if raw is None:
        return False
    return raw.strip() not in {"0", "false", "False"}


def get_rm_user_id() -> str:
    """获取风控用户 ID 回退值, 默认空串."""
    return get_settings().rm_user_id or ""


# ---- 动态配置 key 读取工具 ----
# 仅限运行时才确定 key 名的场景 (如 per-agent 预算阈值);
# 静态配置必须使用上方 Settings 字段/getter.
def safe_env_int(name: str, default: int) -> int:
    """容错读取 int 环境变量: 未设置/非法值返回默认值."""
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        try:
            return int(float(raw))
        except (TypeError, ValueError):
            return default


def safe_env_float(name: str, default: float) -> float:
    """容错读取 float 环境变量: 未设置/非法值返回默认值."""
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def positive_env_int(name: str, default: int) -> int:
    """容错读取正整数环境变量: 未设置/非法值/非正数返回默认值."""
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


__all__ = [
    "Settings",
    "get_settings",
    "settings",
    "get_mysql_host",
    "get_mysql_port",
    "get_mysql_database",
    "get_mysql_user",
    "get_mysql_password",
    "get_mysql_connect_timeout_s",
    "get_mysql_read_timeout_s",
    "get_mysql_write_timeout_s",
    "get_mysql_pool_size",
    "get_mysql_max_overflow",
    "get_mysql_pool_recycle_s",
    "get_llm_api_key",
    "get_llm_base_url",
    "get_llm_model",
    "get_llm_http_referer",
    "get_llm_app_title",
    "get_llm_resolve_ip",
    "get_llm_embedding_model",
    "get_llm_embedding_base_url",
    "get_llm_embedding_api_key",
    "get_knowledge_db_path",
    "get_chroma_host",
    "get_chroma_port",
    "get_chroma_collection",
    "get_chroma_memory_collection",
    "get_chroma_skills_collection",
    "get_chroma_persist_dir",
    "get_skill_query_rewrite_enabled",
    "get_skill_query_rewrite_timeout",
    "get_skill_query_rewrite_cache_size",
    "get_skill_hybrid_vector_weight",
    "get_mcp_server_name",
    "get_fastmcp_host",
    "get_fastmcp_port",
    "get_redis_url",
    "get_memory_ttl_s",
    "get_memory_max_len",
    "is_semantic_memory_enabled",
    "get_prometheus_url",
    "get_riskagent_namespace",
    "get_riskagent_api_token",
    "is_unauthenticated_allowed",
    "get_log_level",
    "get_run_trace_dir",
    "get_policy_version",
    "is_llm_disabled",
    "get_rm_user_id",
    "safe_env_int",
    "safe_env_float",
    "positive_env_int",
]
