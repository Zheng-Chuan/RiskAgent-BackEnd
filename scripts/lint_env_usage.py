#!/usr/bin/env python3
"""
CI lint: 禁止在 config 层之外直接读取环境变量.

规则:
- ``os.getenv`` / ``os.environ`` 仅允许出现在配置归口文件中
  (``config.py`` / ``config_pydantic.py`` / ``hitl_policy.py``).
- 运行时/测试探测类 key 豁免 (它们不是业务配置):
  KUBERNETES_SERVICE_HOST, PYTEST_CURRENT_TEST, MYSQL_HEALTHCHECK_IN_TESTS.
- 其他模块需要读取环境变量时, 必须通过 ``riskagent_backend.config``
  提供的 getter 或 ``safe_env_int`` / ``safe_env_float`` / ``positive_env_int``.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src" / "riskagent_backend"

# 配置归口文件: 允许直接读取环境变量
ALLOWED_FILES = {
    "config.py",
    "config_pydantic.py",
    # fail-safe 语义: 非法值必须视为关闭人工介入豁免, 与 pydantic bool 不兼容
    "hitl_policy.py",
}

# 运行时/测试探测 key: 非业务配置, 允许就地读取
EXEMPT_KEYS = (
    "KUBERNETES_SERVICE_HOST",
    "PYTEST_CURRENT_TEST",
    "MYSQL_HEALTHCHECK_IN_TESTS",
)

ENV_ACCESS_PATTERN = re.compile(r"os\.(getenv|environ)")


def check_file(path: Path) -> list[str]:
    """返回该文件的违规描述列表 (空列表表示通过)."""
    violations: list[str] = []
    if path.name in ALLOWED_FILES:
        return violations
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not ENV_ACCESS_PATTERN.search(line):
            continue
        if any(key in line for key in EXEMPT_KEYS):
            continue
        violations.append(f"{path.relative_to(REPO_ROOT)}:{lineno}: {line.strip()}")
    return violations


def main() -> int:
    violations: list[str] = []
    for path in sorted(SRC_DIR.rglob("*.py")):
        violations.extend(check_file(path))
    if violations:
        print("环境变量读取越界 (必须收敛到 config 层):", file=sys.stderr)
        for item in violations:
            print(f"  {item}", file=sys.stderr)
        print(
            "\n修复方式: 在 config_pydantic.Settings 增加字段并在 config.py 暴露 getter, "
            "动态 key 请使用 safe_env_int / safe_env_float / positive_env_int.",
            file=sys.stderr,
        )
        return 1
    print("env-usage lint passed: 环境变量读取已收敛到 config 层.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
