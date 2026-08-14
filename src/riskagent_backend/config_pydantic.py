"""Pydantic Settings 配置管理(统一入口).

使用 pydantic-settings 统一管理配置, 提供类型安全、环境变量支持和 .env 文件加载.

兼容性:
- ``config.py`` 现在作为薄包装层, 委托到这里的 ``Settings``.
- 新代码可直接使用 ``settings`` 单例或 ``get_settings()`` 工厂.

使用示例:
```python
from riskagent_backend.config_pydantic import settings

model = settings.llm_model
host = settings.mysql_host
```

注意: 禁止将配置值打印到日志/stdout (可能包含主机地址等敏感信息).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _find_dotenv() -> Optional[str]:
    """向上查找 .env 文件.

    保持与原 ``config.py._try_load_repo_dotenv`` 一致的解析路径
    (仓库根目录 = ``Path(__file__).resolve().parents[2]``).
    """
    cur = Path(__file__).resolve()
    for parent in [cur] + list(cur.parents):
        dotenv = parent / ".env"
        if dotenv.is_file():
            return str(dotenv)
    return None


class Settings(BaseSettings):
    """统一配置类.

    配置来源优先级 (从高到低):
    1. 环境变量
    2. .env 文件 (启动时加载一次)
    3. 默认值
    """

    model_config = SettingsConfigDict(
        env_file=_find_dotenv(),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---- LLM 配置 ----
    llm_api_key: str = Field(default="", description="LLM API Key")
    llm_base_url: str = Field(default="", description="LLM API 基础 URL")
    llm_model: str = Field(default="deepseek-v4-flash", description="LLM 模型名称")
    llm_http_referer: str = Field(default="", description="LLM HTTP-Referer (可选)")
    llm_app_title: str = Field(default="", description="LLM X-Title (可选)")
    llm_resolve_ip: str = Field(default="", description="LLM API 固定 IP (可选)")
    llm_embedding_model: str = Field(
        default="BAAI/bge-m3",
        description="LLM embedding 模型名称 (默认 BAAI/bge-m3, 1024 维, 经硅基流动调用)",
    )
    llm_embedding_base_url: str = Field(
        default="",
        description="embedding 专用 Base URL;为空时回退 LLM_BASE_URL。DeepSeek 官方无 embeddings 端点,需独立指向支持 embedding 的供应商",
    )
    llm_embedding_api_key: str = Field(
        default="",
        description="embedding 专用 API Key;为空时回退 LLM_API_KEY",
    )

    # ---- MySQL 配置 ----
    mysql_host: str = Field(default="localhost", description="MySQL 主机")
    mysql_port: int = Field(default=3306, description="MySQL 端口")
    mysql_database: str = Field(default="riskagent", description="MySQL 数据库名")
    mysql_user: str = Field(default="admin", description="MySQL 用户")
    mysql_password: str = Field(default="", description="MySQL 密码")
    mysql_connect_timeout: float = Field(default=3.0, description="MySQL 连接超时(秒)")
    mysql_read_timeout: float = Field(default=5.0, description="MySQL 读取超时(秒)")
    mysql_write_timeout: float = Field(default=5.0, description="MySQL 写入超时(秒)")
    mysql_pool_size: int = Field(default=5, description="MySQL 连接池大小")
    mysql_pool_max_overflow: int = Field(default=10, description="MySQL 连接池最大溢出数")
    mysql_pool_recycle: int = Field(default=1800, description="MySQL 连接回收时间(秒)")

    # ---- Redis 配置 ----
    redis_host: str = Field(default="localhost", description="Redis 主机")
    redis_port: int = Field(default=6379, description="Redis 端口")
    redis_db: int = Field(default=0, description="Redis 数据库号")
    redis_password: Optional[str] = Field(default=None, description="Redis 密码")

    # ---- HITL 配置 ----
    hitl_redis_stream: str = Field(default="risk_monitor:approval", description="HITL Redis Stream 名称")
    hitl_auto_approve: bool = Field(
        default=False,
        description="是否自动审批 (安全默认关闭, 需显式开启 HITL_AUTO_APPROVE=1)",
    )

    # ---- MCP Server 配置 ----
    mcp_server_name: str = Field(default="RiskAgent BackEnd", description="MCP 服务名称")
    fastmcp_host: str = Field(default="0.0.0.0", description="FastMCP 监听地址")
    fastmcp_port: int = Field(default=8000, description="FastMCP 监听端口")

    # ---- 记忆行为配置 ----
    memory_ttl_s: int = Field(default=86400, description="记忆默认 TTL (秒)")
    memory_max_len: int = Field(default=2000, description="记忆列表最大长度")
    semantic_memory_enabled: Optional[str] = Field(
        default=None,
        description="语义记忆开关 (str 保留原始容错语义, 未设置时回退 PAGE_INDEX_ENABLED)",
    )
    page_index_enabled: Optional[str] = Field(
        default=None,
        description="旧版 PAGE_INDEX_ENABLED 开关 (仅作为 SEMANTIC_MEMORY_ENABLED 未设置时的回退)",
    )

    # ---- 感知采集配置 ----
    prometheus_url: str = Field(default="http://localhost:9090", description="Prometheus 地址")
    riskagent_namespace: str = Field(default="riskagent", description="K8s 命名空间")

    # ---- API 鉴权配置 (fail-closed) ----
    riskagent_api_token: str = Field(default="", description="REST/metrics/MCP Bearer Token")
    riskagent_allow_unauthenticated: Optional[str] = Field(
        default=None,
        description="未设置 Token 时是否放行 (str 保留容错语义, 仅本地开发/测试)",
    )

    # ---- 日志与观测配置 ----
    log_level: str = Field(default="INFO", description="日志级别")
    run_trace_dir: str = Field(default="results/run_traces", description="run trace 落盘目录")

    # ---- 治理配置 ----
    policy_version: str = Field(default="policy.v1", description="治理策略版本号")

    # ---- LLM 运行时开关 ----
    disable_llm: Optional[str] = Field(
        default=None,
        description="禁用 LLM 开关 (str 保留原始语义: 除 0/false/False 外一律视为禁用)",
    )
    rm_user_id: str = Field(default="", description="风控用户 ID (LLM 治理上下文回退值)")

    # ---- Chroma 配置 ----
    chroma_host: str = Field(default="localhost", description="Chroma 主机")
    chroma_port: int = Field(default=8001, description="Chroma 端口")
    chroma_collection: str = Field(default="riskagent-alerts", description="Chroma 默认集合名")
    chroma_memory_collection: str = Field(default="riskagent-memory", description="Chroma 记忆集合名")
    chroma_skills_collection: str = Field(default="riskagent-skills", description="Chroma Skill 语义检索集合名")
    chroma_persist_dir: str = Field(default="", description="Chroma 持久化目录(为空则使用 HTTP 客户端)")

    # ---- Knowledge 配置 ----
    knowledge_db_path: str = Field(default="", description="知识库 SQLite 路径(为空使用默认)")

    # ---- Skill governance 配置 ----
    skill_max_per_category: int = Field(default=10, description="每个分类最多 Skill 数")
    skill_min_confidence_injection: float = Field(default=0.3, description="注入最低置信度")
    skill_max_age_days: int = Field(default=90, description="Skill 最大年龄(天), 超期自动归档")
    skill_max_injection_tokens: int = Field(default=2000, description="Skill 注入 token 预算")

    # ---- Skill query rewrite 配置 (RFC-005 需求五) ----
    skill_query_rewrite_enabled: bool = Field(
        default=True, description="是否启用 query 改写 (LLM 检索导向查询扩展)"
    )
    skill_query_rewrite_timeout: float = Field(
        default=3.0, description="query 改写 LLM 调用超时(秒)"
    )
    skill_query_rewrite_cache_size: int = Field(
        default=256, description="query 改写 LRU 缓存容量"
    )

    # ---- Skill hybrid retrieval 配置 (RFC-005 需求四) ----
    skill_hybrid_vector_weight: float = Field(
        default=0.7,
        description="Hybrid 检索向量权重 alpha (0.0=纯BM25, 1.0=纯向量, 默认0.7)",
    )

    # ---- 派生属性 ----
    @property
    def mysql_dsn(self) -> str:
        """MySQL DSN."""
        return (
            f"mysql+pymysql://{self.mysql_user}:{self.mysql_password}"
            f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}"
            "?charset=utf8mb4"
        )

    @property
    def redis_url_override(self) -> str:
        """显式配置的 REDIS_URL.

        仅读取进程环境变量, 不读取 .env 文件 (保持历史 ``os.getenv``
        语义: 历史上消费方未 ``load_dotenv``, .env 中的 REDIS_URL 不生效).
        """
        return (os.getenv("REDIS_URL") or "").strip()

    @property
    def redis_url(self) -> str:
        """Redis URL (显式 REDIS_URL 优先, 否则由 host/port/password 组装)."""
        explicit = self.redis_url_override
        if explicit:
            return explicit
        if self.redis_password:
            return f"redis://:{self.redis_password}@{self.redis_host}:{self.redis_port}/{self.redis_db}"
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"


# 兼容旧名称
Config = Settings


def get_settings() -> Settings:
    """获取一个新的 ``Settings`` 实例.

    每次调用都会重新读取环境变量, 便于测试场景下使用
    ``monkeypatch.setenv`` 动态修改配置.
    """
    return Settings()


# 全局单例 (新代码推荐使用)
settings: Settings = Settings()

# 历史别名: 旧版本曾导出 ``config``, 保留以避免破坏可能存在的引用
config = settings


def get_config() -> Settings:
    """旧版工厂函数别名, 等价于 ``get_settings()``."""
    return get_settings()
