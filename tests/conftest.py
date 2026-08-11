import asyncio
import gc
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_SRC_ROOT = _PROJECT_ROOT / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

# 测试环境显式开启鉴权逃生舱 (鉴权默认 fail-closed, 见 services/auth_service.py)
# 鉴权行为本身的测试通过 monkeypatch 显式控制这两个环境变量
os.environ.setdefault("RISKAGENT_ALLOW_UNAUTHENTICATED", "1")
# 测试环境显式开启 HITL 自动审批 (安全默认关闭, 见 orchestration/hitl_policy.py)
# 审批行为本身的测试通过 monkeypatch 显式设置 HITL_AUTO_APPROVE
os.environ.setdefault("HITL_AUTO_APPROVE", "1")


@pytest.fixture(autouse=True, scope="function")
def _mock_skill_proposer_llm():
    """防止 SkillProposer 测试发起真实 LLM API 调用.

    通过 patching skill_proposer 模块中的 LlmClient 引用,
    使所有未注入 llm_client 的 SkillProposer 实例使用 mock 客户端.
    mock 会从 prompt 中提取任务意图, 返回包含意图的摘要, 确保不同任务得到不同 summary.
    需要测试真实 LLM 调用的测试应通过构造函数注入自定义 mock.
    """
    try:
        from riskagent_backend.skills import skill_proposer as sp_module

        async def _fake_chat_completions(*, messages, **kwargs):
            # 从 prompt 中提取任务意图, 确保不同任务得到不同 summary
            user_msg = ""
            for msg in messages:
                if msg.get("role") == "user":
                    user_msg = msg.get("content", "")
                    break
            # 提取 "任务意图:" 行的内容
            intent = ""
            for line in user_msg.split("\n"):
                if line.startswith("任务意图:"):
                    intent = line.replace("任务意图:", "").strip()
                    break
            summary = f"{intent}的可复用工作流模式" if intent else "从持仓查询到限额核对的完整风险排查工作流"
            return {
                "choices": [
                    {"message": {"content": summary}}
                ]
            }

        mock_client = MagicMock()
        mock_client.chat_completions = _fake_chat_completions

        original_llm_client = sp_module.LlmClient
        sp_module.LlmClient = lambda *a, **kw: mock_client  # type: ignore[assignment]
        yield
        sp_module.LlmClient = original_llm_client  # type: ignore[assignment]
    except ImportError:
        yield


@pytest.fixture(autouse=True, scope="function")
def _mock_skill_injector_llm():
    """防止 SkillInjector 测试发起真实 LLM API 调用 (RFC-005 需求五 query 改写).

    通过 patching skill_injector 模块中的 LlmClient 引用,
    使所有未注入 llm_client 的 SkillInjector 实例使用 mock 客户端.
    mock 从 prompt 中提取 "原始查询:" 后的内容原样返回, 确保不改变现有测试的检索行为.
    需要测试真实 query 改写的测试应通过构造函数注入自定义 mock.
    """
    try:
        from riskagent_backend.skills import skill_injector as si_module

        async def _fake_chat_completions(*, messages, **kwargs):
            # 从 prompt 中提取 "原始查询:" 后的内容, 原样返回 (不改变检索行为)
            for msg in messages:
                if msg.get("role") == "user":
                    content = msg.get("content", "")
                    for line in content.split("\n"):
                        if line.strip().startswith("原始查询:"):
                            original = line.replace("原始查询:", "").strip()
                            if original:
                                return {
                                    "choices": [
                                        {"message": {"content": original}}
                                    ]
                                }
            # fallback: 返回空, _rewrite_query 会 fallback 到原始 query
            return {"choices": [{"message": {"content": ""}}]}

        mock_client = MagicMock()
        mock_client.chat_completions = _fake_chat_completions

        original_llm_client = si_module.LlmClient
        si_module.LlmClient = lambda *a, **kw: mock_client  # type: ignore[assignment]
        yield
        si_module.LlmClient = original_llm_client  # type: ignore[assignment]
    except ImportError:
        yield


@pytest.fixture(autouse=True, scope="function")
def reset_memory_store():
    """在每个测试前清理 MemoryStore 的 Redis 数据."""
    # 设置测试环境变量
    os.environ.setdefault("REDIS_URL", "redis://:9s-R5At6itSHSWex6L8how@localhost:6379/0")

    # 清理全局 MemoryStore 实例,强制重新创建
    try:
        from riskagent_backend.memory.memory_store import _MEMORY_STORE, MemoryStore
        import riskagent_backend.memory.memory_store as ms_module

        if _MEMORY_STORE is not None:
            # 尝试关闭现有连接
            try:
                import asyncio

                loop = asyncio.new_event_loop()
                loop.run_until_complete(_MEMORY_STORE.close())
                loop.close()
            except Exception:
                pass
            # 重置全局变量
            ms_module._MEMORY_STORE = None
    except Exception:
        pass

    yield

    # 测试结束后清理 Redis
    try:
        from riskagent_backend.memory.memory_store import _MEMORY_STORE

        if _MEMORY_STORE is not None:
            import asyncio

            async def _clear():
                try:
                    r = await _MEMORY_STORE._ensure_connected()
                    await r.flushdb()
                except Exception:
                    pass

            loop = asyncio.new_event_loop()
            loop.run_until_complete(_clear())
            loop.close()
    except Exception:
        pass


def pytest_sessionfinish(session, exitstatus):
    try:
        from riskagent_backend.data_access.mysql_engine import dispose_engine

        dispose_engine()
    except Exception:
        pass

    try:
        from riskagent_backend.memory.stores import dispose_all_sql_memory_engines

        dispose_all_sql_memory_engines()
    except Exception:
        pass

    try:
        for obj in gc.get_objects():
            try:
                if isinstance(obj, asyncio.AbstractEventLoop) and not obj.is_closed():
                    obj.close()
            except Exception:
                pass
    except Exception:
        pass
