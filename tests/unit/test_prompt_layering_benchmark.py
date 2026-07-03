from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SRC_ROOT = _PROJECT_ROOT / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from eval.scripts.run_prompt_layering_benchmark import (
    DEFAULT_CASE_FILE,
    build_acceptance_summary,
    load_fixed_cases,
    simulate_prompt_cost,
)


def test_load_fixed_cases_covers_all_required_categories() -> None:
    cases = load_fixed_cases(DEFAULT_CASE_FILE)
    categories = {case.category for case in cases}
    assert len(cases) == 6
    assert categories == {
        "simple",
        "complex",
        "recovery",
        "approval",
        "memory",
        "safety",
    }


def test_simulate_prompt_cost_reduces_tokens_and_hits_cache() -> None:
    cases = load_fixed_cases(DEFAULT_CASE_FILE)

    off_summary = simulate_prompt_cost(cases, prompt_layering=False)
    on_summary = simulate_prompt_cost(cases, prompt_layering=True)

    assert off_summary["scope"] == "prompt_construction_estimate"
    assert on_summary["scope"] == "prompt_construction_estimate"
    assert int(on_summary["total_tokens"]) < int(off_summary["total_tokens"])
    assert float(on_summary["cache_hit_rate"]) > 0.0
    assert int(on_summary["prefix_cache_savings"]) > 0
    assert int(on_summary["cache_stats"]["hit_count"]) >= 1


def test_build_acceptance_summary_applies_phase8_thresholds() -> None:
    summary = build_acceptance_summary(
        off_quality={
            "task_success_rate": 1.0,
            "evidence_coverage": 1.0,
            "approval_correctness": 1.0,
        },
        on_quality={
            "task_success_rate": 1.0,
            "evidence_coverage": 0.96,
            "approval_correctness": 1.0,
        },
        off_cost={
            "total_tokens": 1000,
            "cache_hit_rate": 0.0,
            "prefix_cache_savings": 0,
        },
        on_cost={
            "total_tokens": 800,
            "cache_hit_rate": 0.5,
            "prefix_cache_savings": 200,
        },
    )

    assert summary["passed"] is True
    assert summary["quality_checks"]["evidence_coverage"]["passed"] is True
    assert summary["cost_checks"]["token_total"]["reduction_pct"] == 20.0
    assert summary["cost_checks"]["cache_hit_rate"]["passed"] is True
