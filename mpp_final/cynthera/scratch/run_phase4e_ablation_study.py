"""Phase 4E Ablation Study Runner.

Runs all evaluation configurations against the live benchmark dataset,
reporting BOTH evidence representation changes AND prediction changes separately.

Key principle: Ablation correctness = evidence component actually removed.
Prediction change is an experimental observation, not a correctness requirement.

Usage:
    python scratch/run_phase4e_ablation_study.py
"""
from __future__ import annotations
import sys
import os
import asyncio
import time
import io

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.evaluation.benchmark_runner import BenchmarkRunner
from backend.evaluation.benchmark_dataset import BENCHMARK_DATASET_V1, get_directionally_suitable_negatives
from backend.evaluation.benchmark_models import BenchmarkClass
from backend.evaluation.evaluation_config import EVALUATION_CONFIGS


def bar(label: str, value: str | int | float, width: int = 55) -> None:
    print(f"  {label:<50} {value}")


def section(title: str) -> None:
    print(f"\n{'═' * 70}")
    print(f"  {title}")
    print(f"{'═' * 70}")


async def run_ablation_study() -> None:
    print("\n" + "═" * 70)
    print("  CYNTHERA — Phase 4E Ablation Study")
    print(f"  Cases: {len(BENCHMARK_DATASET_V1)} total")
    print("═" * 70)

    runner = BenchmarkRunner()

    # Step 1: Full production run to populate package cache
    section("Step 1: Full Production Pipeline Run")
    print("  Running all benchmark cases through production pipeline...")
    t0 = time.time()
    report = await runner.run_benchmark(
        cases=BENCHMARK_DATASET_V1,
        bypass_cache=False,
        include_ablations=False,  # Run ablations manually below
    )
    elapsed = time.time() - t0
    print(f"  ✓ Completed in {elapsed:.1f}s")
    print(f"  Full pipeline accuracy: {report.full_4d_metrics.accuracy:.1%}" if report.full_4d_metrics.accuracy else "  Full pipeline accuracy: N/A")

    # Show per-case results
    section("Step 2: Full Pipeline Per-Case Results")
    print(f"  {'Case ID':<18} {'Drug':<18} {'Expected':<10} {'Predicted':<10} {'Correct'}")
    print(f"  {'-'*18} {'-'*18} {'-'*10} {'-'*10} {'-'*7}")
    for r in report.case_results:
        correct_str = "✓" if r.is_correct else "✗"
        print(f"  {r.case.case_id:<18} {r.case.drug:<18} {r.case.expected_class.value:<10} {r.predicted_class.value:<10} {correct_str}")

    # Step 2: Ablation configurations
    section("Step 3: Ablation Study (Evidence Representation vs Prediction Change)")
    print("  Running ablations using cached RetrievalPackages (no re-fetch)...")

    from backend.evaluation.ablation_runner import (
        run_ablation_no_open_targets,
        run_ablation_no_datts,
        run_ablation_no_drugmechdb,
        run_ablation_no_independence,
    )

    ablations = [
        ("NO_OPEN_TARGETS", run_ablation_no_open_targets(report.case_results, runner._package_cache)),
        ("NO_DATTS", run_ablation_no_datts(report.case_results, runner._package_cache)),
        ("NO_DRUGMECHDB", run_ablation_no_drugmechdb(report.case_results, runner._package_cache)),
        ("NO_INDEPENDENCE_GROUPING", run_ablation_no_independence(report.case_results, runner._package_cache)),
    ]

    for abl_name, abl_result in ablations:
        print(f"\n  ── {abl_name} ──")
        bar("  Description", abl_result.description)
        bar("  Evidence representation changed (cases)", abl_result.evidence_changed_count)
        bar("  Prediction changed (cases)", abl_result.prediction_changed_count)
        bar("  Ablated accuracy",
            f"{abl_result.metrics.accuracy:.1%}" if abl_result.metrics.accuracy else "N/A")

        if abl_result.verifications:
            print(f"\n  {'Case ID':<18} {'Ev. Changed':<12} {'Pred. Changed':<14} {'Ablated Pred':<12} {'Note'}")
            print(f"  {'-'*18} {'-'*12} {'-'*14} {'-'*12} {'-'*30}")
            for v in abl_result.verifications:
                ev_str = "YES ✓" if v.evidence_representation_changed else "no"
                pred_str = "YES" if v.prediction_changed else "no"
                note_short = v.verification_note[:35] if v.verification_note else ""
                print(f"  {v.case_id:<18} {ev_str:<12} {pred_str:<14} {v.ablated_prediction:<12} {note_short}")

    # Step 3: Weighting comparison (evaluation only)
    section("Step 4: Weighted vs Equal-Vote Comparison (Evaluation Only)")
    print("  NOTE: Production always uses equal-vote. Weighted is a comparator only.")
    print("  NOTE: WeightConfig values are INITIAL HEURISTICS — not calibrated.")
    from backend.evaluation.evidence_weights import WEIGHT_CONFIGS

    for cfg_name in ["WEIGHTED_4D_A", "WEIGHTED_4D_B", "WEIGHTED_4D_C"]:
        cfg = EVALUATION_CONFIGS.get(cfg_name)
        if cfg is None:
            continue
        wc = WEIGHT_CONFIGS.get(cfg.weight_config_name)
        if wc is None:
            continue

        print(f"\n  Config: {cfg_name} (direct={wc.direct}, curated={wc.curated}, inferred={wc.inferred})")
        from backend.evaluation.evaluation_runner import EvaluationRunner
        ev_runner = EvaluationRunner()

        agrees = 0
        for r in report.case_results:
            pkg = runner._package_cache.get(r.case.case_id)
            if pkg is None:
                continue
            try:
                w_res, _ = ev_runner.run_with_config(r.case, pkg, cfg, full_result=r)
                agrees_this = (w_res.predicted_class == r.predicted_class)
                if agrees_this:
                    agrees += 1
                status = "agree" if agrees_this else f"DIFF: equal={r.predicted_class.value} weighted={w_res.predicted_class.value}"
                print(f"    {r.case.case_id:<18} {status}")
            except Exception as exc:
                print(f"    {r.case.case_id:<18} ERROR: {exc}")

        total_w = len([r for r in report.case_results if runner._package_cache.get(r.case.case_id)])
        if total_w > 0:
            print(f"    Agreement rate: {agrees}/{total_w} ({agrees/total_w:.1%})")

    section("Summary")
    bar("Total cases evaluated", len(report.case_results))
    bar("Full pipeline accuracy", f"{report.full_4d_metrics.accuracy:.1%}" if report.full_4d_metrics.accuracy else "N/A")
    bar("Suitable negative cases", len(get_directionally_suitable_negatives()))
    print()
    print("  Ablation principle: Evidence representation change = VERIFIED ablation.")
    print("  Prediction change = experimental observation (not a correctness criterion).")
    print()


if __name__ == "__main__":
    asyncio.run(run_ablation_study())
