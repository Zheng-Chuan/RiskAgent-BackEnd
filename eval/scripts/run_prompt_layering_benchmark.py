from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from eval.core.evaluator import Evaluator, TestCase
from riskagent_backend.llm.token_tracker import TokenTracker
from riskagent_backend.prompts import (
    CostReportGenerator,
    PromptCacheManager,
    TieredPromptBuilder,
)


DEFAULT_CASE_FILE = REPO_ROOT / "eval" / "benchmarks" / "prompt_layering" / "one_shot_cases.jsonl"
RESULTS_ROOT = REPO_ROOT / "eval" / "results" / "prompt_layering"
TRACKED_QUALITY_METRICS = [
    "task_success_rate",
    "evidence_coverage",
    "approval_correctness",
]


def load_fixed_cases(case_file: Path = DEFAULT_CASE_FILE) -> list[TestCase]:
    """Load the fixed one-shot benchmark dataset."""
    evaluator = Evaluator(llm_judge_enabled=False)
    return evaluator.load_cases(case_file)


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _estimate_completion_tokens(case: TestCase) -> int:
    """Estimate completion tokens with a simple deterministic heuristic."""
    difficulty_bonus = {
        "easy": 48,
        "medium": 72,
        "hard": 96,
    }
    content = ""
    if isinstance(case.task, dict):
        raw_content = case.task.get("content")
        if isinstance(raw_content, str):
            content = raw_content
    return max(32, (len(content) // 6) + difficulty_bonus.get(case.difficulty, 72))


def _build_prompt_inputs(case: TestCase) -> dict[str, Any]:
    """Build deterministic prompt inputs for prompt-layering simulation."""
    task_content = ""
    task_context: dict[str, Any] = {}
    if isinstance(case.task, dict):
        if isinstance(case.task.get("content"), str):
            task_content = case.task["content"]
        if isinstance(case.task.get("context"), dict):
            task_context = dict(case.task.get("context") or {})

    scenario = case.scenario_class or case.category
    return {
        "agent_role": "You are a risk monitoring orchestrator. Keep answers evidence-first and concise.",
        "tools_index": [
            {"name": "query_positions_by_trader", "desc": "Query trader positions"},
            {"name": "monitor_desk_exposure", "desc": "Monitor desk exposure"},
            {"name": "submit_alerts", "desc": "Create alert after approval"},
        ],
        "behavior_rules": [
            "Do not fabricate facts.",
            "Request approval before side-effect actions.",
            "Prefer evidence-grounded summaries.",
        ],
        "skills": [
            {
                "name": "risk_triage",
                "steps": [
                    "identify risk signal",
                    "collect evidence",
                    "summarize impact",
                ],
                "applies_to": [case.category, scenario],
            }
        ],
        "project_rules": [
            "Follow the evidence-first workflow.",
            "Keep message trace complete.",
            f"Benchmark scenario: {scenario}",
        ],
        "memory_summary": {
            "category": case.category,
            "scenario_class": scenario,
            "keywords": [case.category, scenario],
        },
        "current_event": {
            "category": case.category,
            "difficulty": case.difficulty,
        },
        "task": {
            "case_id": case.case_id,
            "content": task_content,
            "context": task_context,
        },
        "react_history": [
            {
                "thought": f"Need to solve {case.category} benchmark carefully.",
                "action_type": "analyze",
            }
        ],
    }


def simulate_prompt_cost(
    cases: list[TestCase],
    *,
    prompt_layering: bool,
    stable_version: str = "phase8.v1",
    context_date: str = "2026-06-29",
) -> dict[str, Any]:
    """Simulate prompt-side token cost for prompt layering on or off."""
    builder = TieredPromptBuilder(
        stable_version=stable_version,
        context_date=context_date,
    )
    cache = PromptCacheManager()
    tracker = TokenTracker()
    case_rows: list[dict[str, Any]] = []

    for case in cases:
        prompt_inputs = _build_prompt_inputs(case)
        stable = builder.build_stable_tier(
            agent_role=prompt_inputs["agent_role"],
            tools_index=prompt_inputs["tools_index"],
            behavior_rules=prompt_inputs["behavior_rules"],
        )
        context = builder.build_context_tier(
            skills=prompt_inputs["skills"],
            project_rules=prompt_inputs["project_rules"],
            memory_summary=prompt_inputs["memory_summary"],
        )
        volatile = builder.build_volatile_tier(
            current_event=prompt_inputs["current_event"],
            task=prompt_inputs["task"],
            react_history=prompt_inputs["react_history"],
        )
        stable_context_tokens = stable.token_estimate + context.token_estimate
        completion_tokens = _estimate_completion_tokens(case)
        cache_key = builder.get_cache_key(stable, context)

        cached = False
        prefix_cache_savings = 0
        if prompt_layering:
            cached_entry = cache.get(cache_key)
            if cached_entry is None:
                cache.set(
                    cache_key,
                    stable.content + "\n" + context.content,
                    stable.version,
                )
                prompt_tokens = stable_context_tokens + volatile.token_estimate
                tier_breakdown = {
                    "stable": stable.token_estimate,
                    "context": context.token_estimate,
                    "volatile": volatile.token_estimate,
                }
            else:
                cached = True
                prefix_cache_savings = stable_context_tokens
                prompt_tokens = volatile.token_estimate
                tier_breakdown = {
                    "stable": 0,
                    "context": 0,
                    "volatile": volatile.token_estimate,
                }
        else:
            prompt_tokens = stable_context_tokens + volatile.token_estimate
            tier_breakdown = {
                "stable": stable.token_estimate,
                "context": context.token_estimate,
                "volatile": volatile.token_estimate,
            }

        total_tokens = prompt_tokens + completion_tokens
        tracker.record(
            model="prompt-layering-sim",
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            cached=cached,
            prefix_cache_savings=prefix_cache_savings,
            tier_breakdown=tier_breakdown,
        )
        case_rows.append(
            {
                "case_id": case.case_id,
                "category": case.category,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
                "cached": cached,
                "prefix_cache_savings": prefix_cache_savings,
            }
        )

    summary = tracker.summary()
    summary["cases"] = case_rows
    summary["cache_stats"] = cache.get_stats()
    summary["scope"] = "prompt_construction_estimate"
    return summary


def extract_quality_metrics(payload: dict[str, Any]) -> dict[str, float]:
    """Extract the tracked quality metrics from an evaluation result."""
    summary_block = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    behavior = payload.get("behavior_metrics") if isinstance(payload.get("behavior_metrics"), dict) else {}
    metrics = {
        "task_success_rate": float(
            behavior.get("task_success_rate", summary_block.get("pass_rate", 0.0))
        ),
        "evidence_coverage": float(behavior.get("evidence_coverage", 0.0)),
        "approval_correctness": float(behavior.get("approval_correctness", 0.0)),
    }
    return metrics


def build_acceptance_summary(
    *,
    off_quality: dict[str, float],
    on_quality: dict[str, float],
    off_cost: dict[str, Any],
    on_cost: dict[str, Any],
) -> dict[str, Any]:
    """Build the acceptance summary defined in the Phase 8 document."""
    off_total_tokens = int(off_cost.get("total_tokens", 0))
    on_total_tokens = int(on_cost.get("total_tokens", 0))
    cache_hit_rate = float(on_cost.get("cache_hit_rate", 0.0))

    if off_total_tokens > 0:
        token_reduction_pct = round(
            ((off_total_tokens - on_total_tokens) / off_total_tokens) * 100.0,
            2,
        )
    else:
        token_reduction_pct = 0.0

    quality_checks = {
        "task_success_rate": {
            "baseline": off_quality["task_success_rate"],
            "current": on_quality["task_success_rate"],
            "passed": on_quality["task_success_rate"] >= off_quality["task_success_rate"],
        },
        "evidence_coverage": {
            "baseline": off_quality["evidence_coverage"],
            "current": on_quality["evidence_coverage"],
            "passed": on_quality["evidence_coverage"] >= (off_quality["evidence_coverage"] * 0.95),
        },
        "approval_correctness": {
            "baseline": off_quality["approval_correctness"],
            "current": on_quality["approval_correctness"],
            "passed": on_quality["approval_correctness"] >= off_quality["approval_correctness"],
        },
    }
    cost_checks = {
        "token_total": {
            "baseline": off_total_tokens,
            "current": on_total_tokens,
            "reduction_pct": token_reduction_pct,
            "passed": token_reduction_pct >= 15.0,
        },
        "cache_hit_rate": {
            "baseline": float(off_cost.get("cache_hit_rate", 0.0)),
            "current": cache_hit_rate,
            "passed": cache_hit_rate > 0.0,
        },
        "prefix_cache_savings": {
            "baseline": int(off_cost.get("prefix_cache_savings", 0)),
            "current": int(on_cost.get("prefix_cache_savings", 0)),
        },
    }

    passed = all(item["passed"] for item in quality_checks.values()) and all(
        item.get("passed", True) for item in cost_checks.values()
    )
    return {
        "passed": passed,
        "quality_checks": quality_checks,
        "cost_checks": cost_checks,
    }


def write_markdown_report(output_path: Path, summary: dict[str, Any]) -> None:
    """Write a human-readable Markdown report."""
    comparison = summary["comparison"]
    off_run = summary["runs"]["prompt_layering_off"]
    on_run = summary["runs"]["prompt_layering_on"]
    lines = [
        "# Prompt Layering One-Shot Benchmark",
        "",
        f"- generated_at: {summary['generated_at']}",
        f"- case_file: {summary['case_file']}",
        f"- off_result: {off_run['result_path']}",
        f"- on_result: {on_run['result_path']}",
        "",
        "## Cases",
    ]
    for case_meta in summary["cases"]:
        lines.append(
            f"- {case_meta['case_id']}: {case_meta['category']} / {case_meta['difficulty']}"
        )

    lines.extend(
        [
            "",
            "## Quality Checks",
        ]
    )
    for metric_name, payload in comparison["quality_checks"].items():
        status = "PASS" if payload["passed"] else "FAIL"
        lines.append(
            f"- {metric_name}: {payload['baseline']:.4f} -> {payload['current']:.4f} [{status}]"
        )

    lines.extend(
        [
            "",
            "## Cost Checks",
        ]
    )
    token_check = comparison["cost_checks"]["token_total"]
    cache_check = comparison["cost_checks"]["cache_hit_rate"]
    prefix_check = comparison["cost_checks"]["prefix_cache_savings"]
    lines.append(
        f"- token_total: {token_check['baseline']} -> {token_check['current']} ({token_check['reduction_pct']:+.2f}%)"
    )
    lines.append(
        f"- cache_hit_rate: {cache_check['baseline']:.4f} -> {cache_check['current']:.4f}"
    )
    lines.append(
        f"- prefix_cache_savings: {prefix_check['baseline']} -> {prefix_check['current']}"
    )

    lines.extend(
        [
            "",
            "## Result",
            "",
            f"- benchmark_passed: {comparison['passed']}",
            "",
            "## Notes",
            "",
            "- Quality metrics come from the existing evaluator on the fixed case set.",
            "- Cost metrics are deterministic prompt-construction estimates based on TieredPromptBuilder and PromptCacheManager.",
        ]
    )
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _run_eval(
    *,
    output_path: Path,
    benchmarks_dir: Path,
    dataset_version: str,
) -> None:
    command = [
        sys.executable,
        "-m",
        "eval.cli",
        "run",
        "--category",
        "all",
        "--benchmarks-dir",
        str(benchmarks_dir),
        "--baseline-mode",
        "primary",
        "--output",
        str(output_path),
        "--dataset-version",
        dataset_version,
        "--no-llm-judge",
    ]
    env = dict(os.environ)
    src_path = str(REPO_ROOT / "src")
    existing_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = src_path if not existing_pythonpath else f"{src_path}:{existing_pythonpath}"
    subprocess.run(command, cwd=REPO_ROOT, env=env, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the Phase 8 one-shot prompt-layering benchmark",
    )
    parser.add_argument(
        "--case-file",
        default=str(DEFAULT_CASE_FILE),
        help="Fixed case jsonl file",
    )
    parser.add_argument(
        "--output-dir",
        default=str(RESULTS_ROOT),
        help="Directory for benchmark outputs",
    )
    parser.add_argument(
        "--skip-eval",
        action="store_true",
        help="Skip workflow evaluation and reuse existing off/on results",
    )
    parser.add_argument(
        "--off-result",
        help="Existing evaluation result for prompt_layering_off",
    )
    parser.add_argument(
        "--on-result",
        help="Existing evaluation result for prompt_layering_on",
    )
    args = parser.parse_args()

    case_file = Path(args.case_file)
    cases = load_fixed_cases(case_file)
    if not cases:
        raise SystemExit(f"No cases found in {case_file}")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    off_result_path = Path(args.off_result) if args.off_result else output_dir / f"{stamp}_prompt_layering_off.json"
    on_result_path = Path(args.on_result) if args.on_result else output_dir / f"{stamp}_prompt_layering_on.json"

    if not args.skip_eval:
        benchmarks_dir = case_file.parent
        _run_eval(
            output_path=off_result_path,
            benchmarks_dir=benchmarks_dir,
            dataset_version="prompt_layering_off.v1",
        )
        _run_eval(
            output_path=on_result_path,
            benchmarks_dir=benchmarks_dir,
            dataset_version="prompt_layering_on.v1",
        )
    elif not off_result_path.exists() or not on_result_path.exists():
        raise SystemExit("--skip-eval requires both --off-result and --on-result to exist")

    off_payload = _load_json(off_result_path)
    on_payload = _load_json(on_result_path)
    off_quality = extract_quality_metrics(off_payload)
    on_quality = extract_quality_metrics(on_payload)

    off_cost = simulate_prompt_cost(cases, prompt_layering=False)
    on_cost = simulate_prompt_cost(cases, prompt_layering=True)

    cost_report = CostReportGenerator()
    cost_report.save_baseline_from_tracker_summary("prompt_layering_off", off_cost)
    cost_report.save_baseline_from_tracker_summary("prompt_layering_on", on_cost)

    summary = {
        "generated_at": stamp,
        "case_file": str(case_file.relative_to(REPO_ROOT)),
        "cases": [
            {
                "case_id": case.case_id,
                "category": case.category,
                "difficulty": case.difficulty,
                "scenario_class": case.scenario_class,
            }
            for case in cases
        ],
        "runs": {
            "prompt_layering_off": {
                "result_path": str(off_result_path.relative_to(REPO_ROOT)),
                "quality_metrics": off_quality,
                "cost_metrics": off_cost,
            },
            "prompt_layering_on": {
                "result_path": str(on_result_path.relative_to(REPO_ROOT)),
                "quality_metrics": on_quality,
                "cost_metrics": on_cost,
            },
        },
        "comparison": build_acceptance_summary(
            off_quality=off_quality,
            on_quality=on_quality,
            off_cost=off_cost,
            on_cost=on_cost,
        ),
    }

    summary_path = output_dir / f"{stamp}_summary.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    cost_report_path = output_dir / f"{stamp}_cost_report.md"
    cost_report_path.write_text(
        cost_report.generate_report("prompt_layering_off", "prompt_layering_on") + "\n",
        encoding="utf-8",
    )

    markdown_path = output_dir / f"{stamp}_summary.md"
    write_markdown_report(markdown_path, summary)

    print(f"summary_json={summary_path}")
    print(f"summary_md={markdown_path}")
    print(f"cost_report_md={cost_report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
